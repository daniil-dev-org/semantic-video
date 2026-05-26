"""Validation engine — rolling walk-forward backtest and final holdout for hypothesis testing."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

import pandas as pd
import numpy as np

from .config import ValidationConfig
from .hypothesis import HypothesisSpec, apply_filter

logger = logging.getLogger("stp.validation")


@dataclass
    
class ValidationWindowResult:
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    total_test_samples: int
    filter_passed_samples: int
    baseline_precision_at_10: float
    baseline_precision_at_50: float
    filter_precision_at_10: float
    filter_precision_at_50: float
    lift: float


@dataclass
class HypothesisResult:
    hypothesis_id: str
    name: str
    verdict: str  # ACCEPTED, DEMO_ACCEPTED, REJECTED, INCONCLUSIVE, PARTIAL, INVALID
    verdict_reason: str
    rolling_results: list[ValidationWindowResult] = field(default_factory=list)
    holdout_result: ValidationWindowResult | None = None
    
    # Aggregated metrics over rolling windows
    avg_lift: float = 0.0
    avg_precision_at_10: float = 0.0
    avg_precision_at_50: float = 0.0
    avg_recall_at_50: float = 0.0
    total_sample_size: int = 0
    
    # Feature contribution tracking
    video_incremental_lift: float = 0.0


def _compute_metrics(
    df: pd.DataFrame, 
    target_col: str, 
    score_col: str,
    mask: pd.Series,
) -> tuple[float, float, float]:
    """Compute P@10, P@50, Recall@50 for a subset of data."""
    subset = df[mask].copy()
    if len(subset) == 0:
        return 0.0, 0.0, 0.0
        
    subset = subset.sort_values(score_col, ascending=False)
    
    total_positives = subset[target_col].sum()
    if total_positives == 0:
        return 0.0, 0.0, 0.0
        
    p10 = subset.head(10)[target_col].mean() if len(subset) >= 10 else subset[target_col].mean()
    p50 = subset.head(50)[target_col].mean() if len(subset) >= 50 else subset[target_col].mean()
    
    r50 = subset.head(50)[target_col].sum() / total_positives if total_positives > 0 else 0.0
    
    return p10, p50, r50


def validate_hypothesis(
    df: pd.DataFrame,
    hyp: HypothesisSpec,
    cfg: ValidationConfig,
    dataset_mode: str = "unknown",
    passed_data_quality: bool = True,
    is_preregistered: bool = False,
) -> HypothesisResult:
    """Run full validation including walk-forward rolling test and final holdout."""
    from .leakage_checks import check_feature_table_leakage
    
    # 1. Leakage checks
    leak_res = check_feature_table_leakage(df)
    if not leak_res["passed"]:
        return HypothesisResult(
            hypothesis_id=hyp.hypothesis_id,
            name=hyp.name,
            verdict="INVALID",
            verdict_reason="Data leakage detected."
        )

    df_sorted = df.sort_values("collected_at").copy()
    
    min_time = df_sorted["collected_at"].min()
    max_time = df_sorted["collected_at"].max()
    total_duration = max_time - min_time
    
    holdout_duration = total_duration * cfg.final_holdout_ratio
    rolling_end_time = max_time - holdout_duration
    
    target_col = hyp.target.name
    if target_col not in df.columns:
        return HypothesisResult(
            hypothesis_id=hyp.hypothesis_id, name=hyp.name, 
            verdict="INVALID", verdict_reason=f"Target {target_col} missing"
        )
        
    # We assume 'metadata_plus_video_ml_score' is our main score column if it exists,
    # otherwise fallback to momentum_baseline or popularity_baseline
    score_col = "metadata_plus_video_ml_score"
    if score_col not in df.columns:
        score_col = "momentum_baseline" if "momentum_baseline" in df.columns else "views_now"
        
    base_score_col = "metadata_only_ml_score"
    if base_score_col not in df.columns:
        base_score_col = score_col

    rolling_results = []
    
    # Generate Walk-forward windows
    current_train_start = min_time
    while True:
        train_end = current_train_start + timedelta(days=cfg.train_window_days)
        test_start = train_end
        test_end = test_start + timedelta(hours=hyp.prediction_horizon_hours)
        
        if test_end > rolling_end_time:
            break
            
        train_mask = (df_sorted["collected_at"] >= current_train_start) & (df_sorted["collected_at"] < train_end)
        test_mask = (df_sorted["collected_at"] >= test_start) & (df_sorted["collected_at"] < test_end)
        
        test_df = df_sorted[test_mask]
        
        if len(test_df) < 10:
            current_train_start += timedelta(days=cfg.step_days)
            continue
            
        hyp_mask = apply_filter(test_df, hyp.filter)
        
        # Baseline metrics (all test data)
        b_p10, b_p50, _ = _compute_metrics(test_df, target_col, score_col, pd.Series(True, index=test_df.index))
        
        # Filtered metrics (only data matching hypothesis filter)
        f_p10, f_p50, _ = _compute_metrics(test_df, target_col, score_col, hyp_mask)
        
        lift = f_p50 / b_p50 if b_p50 > 0 else 0.0
        
        res = ValidationWindowResult(
            train_start=current_train_start.isoformat(),
            train_end=train_end.isoformat(),
            test_start=test_start.isoformat(),
            test_end=test_end.isoformat(),
            total_test_samples=len(test_df),
            filter_passed_samples=int(hyp_mask.sum()),
            baseline_precision_at_10=b_p10,
            baseline_precision_at_50=b_p50,
            filter_precision_at_10=f_p10,
            filter_precision_at_50=f_p50,
            lift=lift
        )
        rolling_results.append(res)
        
        current_train_start += timedelta(days=cfg.step_days)

    # Calculate aggregate metrics over rolling
    total_samples = sum(r.filter_passed_samples for r in rolling_results)
    if rolling_results and total_samples > 0:
        avg_lift = np.mean([r.lift for r in rolling_results if r.filter_passed_samples > 0])
        avg_p10 = np.mean([r.filter_precision_at_10 for r in rolling_results if r.filter_passed_samples > 0])
        avg_p50 = np.mean([r.filter_precision_at_50 for r in rolling_results if r.filter_passed_samples > 0])
    else:
        avg_lift, avg_p10, avg_p50 = 0.0, 0.0, 0.0

    # Holdout Validation
    holdout_mask = df_sorted["collected_at"] >= rolling_end_time
    holdout_df = df_sorted[holdout_mask]
    holdout_res = None
    holdout_passed = False
    
    if len(holdout_df) > 10:
        h_hyp_mask = apply_filter(holdout_df, hyp.filter)
        hb_p10, hb_p50, _ = _compute_metrics(holdout_df, target_col, score_col, pd.Series(True, index=holdout_df.index))
        hf_p10, hf_p50, _ = _compute_metrics(holdout_df, target_col, score_col, h_hyp_mask)
        hlift = hf_p50 / hb_p50 if hb_p50 > 0 else 0.0
        
        holdout_res = ValidationWindowResult(
            train_start=min_time.isoformat(),
            train_end=rolling_end_time.isoformat(),
            test_start=rolling_end_time.isoformat(),
            test_end=max_time.isoformat(),
            total_test_samples=len(holdout_df),
            filter_passed_samples=int(h_hyp_mask.sum()),
            baseline_precision_at_10=hb_p10,
            baseline_precision_at_50=hb_p50,
            filter_precision_at_10=hf_p10,
            filter_precision_at_50=hf_p50,
            lift=hlift
        )
        
        if (holdout_res.filter_passed_samples >= hyp.success_criteria.min_sample_size and
            hlift >= hyp.success_criteria.min_lift and
            hf_p50 >= hyp.success_criteria.min_precision_at_50):
            holdout_passed = True
            
    # Calculate feature incremental lift on holdout
    video_incremental_lift = 1.0
    if holdout_df is not None and score_col != base_score_col:
        _, h_base_p50, _ = _compute_metrics(holdout_df, target_col, base_score_col, pd.Series(True, index=holdout_df.index))
        _, h_vid_p50, _ = _compute_metrics(holdout_df, target_col, score_col, pd.Series(True, index=holdout_df.index))
        if h_base_p50 > 0:
            video_incremental_lift = h_vid_p50 / h_base_p50

    # Determine Verdict
    verdict = "INCONCLUSIVE"
    reason = "Insufficient data or failed criteria"
    
    if not rolling_results:
        reason = "No valid walk-forward windows"
    elif total_samples < hyp.success_criteria.min_sample_size:
        reason = f"Sample size {total_samples} < min {hyp.success_criteria.min_sample_size}"
    elif avg_lift < hyp.success_criteria.min_lift:
        verdict = "REJECTED"
        reason = f"Lift {avg_lift:.2f} < min {hyp.success_criteria.min_lift}"
    elif avg_p50 < hyp.success_criteria.min_precision_at_50:
        verdict = "REJECTED"
        reason = f"P@50 {avg_p50:.2f} < min {hyp.success_criteria.min_precision_at_50}"
    else:
        # Rolling passed. Check holdout.
        if cfg.require_holdout_pass and not holdout_passed:
            verdict = "REJECTED"
            reason = "Passed rolling but failed final holdout validation."
        elif cfg.require_preregistered_for_accept and not is_preregistered:
            verdict = "DISCOVERY_ONLY"
            reason = "Passed all checks but was not preregistered."
        else:
            verdict = "ACCEPTED"
            reason = "Passed rolling validation and holdout criteria."

    # Dataset Mode Gating
    if dataset_mode == "synthetic":
        if verdict == "ACCEPTED":
            verdict = "DEMO_ACCEPTED"
        elif verdict == "DISCOVERY_ONLY":
            verdict = "DEMO_ONLY"
        reason = f"[{dataset_mode.upper()}] {reason}"
    elif dataset_mode == "mixed" and verdict == "ACCEPTED":
        verdict = "PARTIAL"
        reason = "[MIXED] " + reason
    elif not passed_data_quality and verdict == "ACCEPTED":
        verdict = "PARTIAL"
        reason = "[FAILED_THRESHOLDS] " + reason

    return HypothesisResult(
        hypothesis_id=hyp.hypothesis_id,
        name=hyp.name,
        verdict=verdict,
        verdict_reason=reason,
        rolling_results=rolling_results,
        holdout_result=holdout_res,
        avg_lift=avg_lift,
        avg_precision_at_10=avg_p10,
        avg_precision_at_50=avg_p50,
        total_sample_size=total_samples,
        video_incremental_lift=video_incremental_lift
    )
