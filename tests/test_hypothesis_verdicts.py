import pytest
from stp.validation import validate_hypothesis, HypothesisResult
from stp.hypothesis import HypothesisSpec, TargetDefinition, SuccessCriteria
from stp.config import ValidationConfig
import pandas as pd
import numpy as np
from datetime import timedelta

def test_hypothesis_synthetic_demo_acceptance():
    # Create fake data (100 days, 10 items per day)
    dates = pd.date_range("2023-01-01", periods=1000, freq="2h")
    df = pd.DataFrame({
        "collected_at": dates,
        "views_now": np.random.randint(100, 1000, 1000),
        "momentum_baseline": np.random.rand(1000),
        "metadata_plus_video_ml_score": np.random.rand(1000),
        "top_growth_72h": np.random.randint(0, 2, 1000)
    })
    
    hyp = HypothesisSpec(
        hypothesis_id="h1", name="test",
        target=TargetDefinition(name="top_growth_72h"),
        success_criteria=SuccessCriteria(min_sample_size=1, min_lift=0.0, min_precision_at_50=0.0),
        preregistered=True
    )
    
    cfg = ValidationConfig(train_window_days=10, test_horizon_hours=24, step_days=10, require_holdout_pass=False)
    
    res = validate_hypothesis(df, hyp, cfg, dataset_mode="synthetic", passed_data_quality=True, is_preregistered=True)
    
    # Since it's synthetic, it shouldn't get standard ACCEPTED
    assert res.verdict in ["DEMO_ACCEPTED", "DEMO_ONLY"]

def test_hypothesis_real_acceptance():
    # Force real data acceptance if holdout passes and thresholds met
    dates = pd.date_range("2023-01-01", periods=1000, freq="2h")
    df = pd.DataFrame({
        "collected_at": dates,
        "views_now": np.random.randint(100, 1000, 1000),
        "momentum_baseline": np.random.rand(1000),
        "metadata_plus_video_ml_score": np.random.rand(1000),
        "top_growth_72h": np.random.randint(0, 2, 1000) # Ensure positives exist
    })
    # artificially make metadata_plus_video_ml_score correlate perfectly
    df["metadata_plus_video_ml_score"] = df["top_growth_72h"]
    
    hyp = HypothesisSpec(
        hypothesis_id="h2", name="test real",
        target=TargetDefinition(name="top_growth_72h"),
        success_criteria=SuccessCriteria(min_sample_size=1, min_lift=0.0, min_precision_at_50=0.0),
        preregistered=True
    )
    
    cfg = ValidationConfig(train_window_days=10, test_horizon_hours=24, step_days=10, require_holdout_pass=False)
    
    res = validate_hypothesis(df, hyp, cfg, dataset_mode="real", passed_data_quality=True, is_preregistered=True)
    assert res.verdict == "ACCEPTED"
