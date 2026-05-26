"""Data Quality — Dataset mode gate and coverage reports."""

from __future__ import annotations

import logging
from enum import Enum
from typing import Dict, Any

import pandas as pd

from .config import DataQualityConfig

logger = logging.getLogger("stp.data_quality")


class DatasetMode(str, Enum):
    SYNTHETIC = "synthetic"
    REAL = "real"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class PredictionValidity(str, Enum):
    VALID = "VALID"
    DEMO_ONLY = "DEMO_ONLY"
    PARTIAL = "PARTIAL"
    UNKNOWN = "UNKNOWN"


def determine_dataset_mode(df: pd.DataFrame) -> DatasetMode:
    """
    Determine the dataset mode (synthetic, real, mixed, unknown) based on
    the `dataset_source` and `is_synthetic` columns.
    """
    if df.empty:
        return DatasetMode.UNKNOWN

    if "is_synthetic" in df.columns:
        synth_flags = df["is_synthetic"].unique()
        if len(synth_flags) == 1 and synth_flags[0]:
            return DatasetMode.SYNTHETIC
        if len(synth_flags) == 1 and not synth_flags[0]:
            return DatasetMode.REAL
        if len(synth_flags) > 1:
            return DatasetMode.MIXED

    # Fallback heuristics
    if "dataset_source" in df.columns:
        sources = df["dataset_source"].unique()
        has_synth = any("synth" in str(s).lower() for s in sources)
        has_real = any("synth" not in str(s).lower() for s in sources)
        if has_synth and not has_real:
            return DatasetMode.SYNTHETIC
        if has_real and not has_synth:
            return DatasetMode.REAL
        if has_real and has_synth:
            return DatasetMode.MIXED

    # Check for demo run patterns
    if "post_id" in df.columns:
        if all(str(x).startswith("synth_post") for x in df["post_id"].unique()):
            return DatasetMode.SYNTHETIC

    return DatasetMode.UNKNOWN


def get_prediction_validity(mode: DatasetMode) -> PredictionValidity:
    if mode == DatasetMode.SYNTHETIC:
        return PredictionValidity.DEMO_ONLY
    elif mode == DatasetMode.REAL:
        return PredictionValidity.VALID
    elif mode == DatasetMode.MIXED:
        return PredictionValidity.PARTIAL
    return PredictionValidity.UNKNOWN


def generate_coverage_report(df: pd.DataFrame, cfg: DataQualityConfig) -> Dict[str, Any]:
    """Generate metrics about the dataset coverage and check thresholds."""
    if df.empty:
        return {"passed_thresholds": False, "metrics": {}}

    metrics: Dict[str, Any] = {}
    metrics["snapshots_count"] = len(df)
    metrics["posts_count"] = df["post_id"].nunique()
    
    for col in ["platform", "category", "country", "language", "author_id", "audio_id", "hashtags"]:
        if col in df.columns:
            metrics[f"{col}s_count"] = df[col].nunique()

    # Time coverage
    date_min = df["collected_at"].min()
    date_max = df["collected_at"].max()
    metrics["date_min"] = date_min.isoformat() if pd.notnull(date_min) else None
    metrics["date_max"] = date_max.isoformat() if pd.notnull(date_max) else None
    days_covered = (date_max - date_min).days if pd.notnull(date_min) and pd.notnull(date_max) else 0
    metrics["days_covered"] = days_covered

    # Snapshots per post
    snaps_per_post = df.groupby("post_id").size()
    metrics["median_snapshots_per_post"] = snaps_per_post.median()
    metrics["p10_snapshots_per_post"] = snaps_per_post.quantile(0.1)
    metrics["p90_snapshots_per_post"] = snaps_per_post.quantile(0.9)

    # Missing metrics
    for col in ["views", "likes", "comments", "shares"]:
        if col in df.columns:
            metrics[f"missing_{col}_percent"] = round((df[col].isnull().sum() / len(df)) * 100, 2)

    # Threshold checks
    failed_thresholds = []
    if days_covered < cfg.min_days_covered:
        failed_thresholds.append(f"days_covered ({days_covered} < {cfg.min_days_covered})")
    if metrics["posts_count"] < cfg.min_posts:
        failed_thresholds.append(f"posts_count ({metrics['posts_count']} < {cfg.min_posts})")
    if metrics["snapshots_count"] < cfg.min_snapshots:
        failed_thresholds.append(f"snapshots_count ({metrics['snapshots_count']} < {cfg.min_snapshots})")
    if metrics["median_snapshots_per_post"] < cfg.min_median_snapshots_per_post:
        failed_thresholds.append(f"median_snapshots ({metrics['median_snapshots_per_post']} < {cfg.min_median_snapshots_per_post})")

    passed = len(failed_thresholds) == 0

    return {
        "metrics": metrics,
        "passed_thresholds": passed,
        "failed_thresholds": failed_thresholds
    }
