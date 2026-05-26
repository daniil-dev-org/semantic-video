"""Trend scoring — baseline heuristics + simple ML model + feature contribution test."""

from __future__ import annotations

import logging
from typing import Dict, Any

import pandas as pd
import numpy as np

from .config import ScoringConfig

logger = logging.getLogger("stp.trend_scoring")

METADATA_FEATURES = [
    "views_now", "likes_now", "comments_now", "shares_now", "engagement_now",
    "views_delta_1h", "views_delta_6h", "views_delta_24h",
    "engagement_delta_1h", "engagement_delta_6h", "engagement_delta_24h",
    "views_velocity_1h", "views_velocity_6h", "views_acceleration_6h",
    "engagement_rate", "age_hours_since_publish", "hashtag_count",
    "audio_id_present", "category_percentile_views_now", "category_percentile_growth_24h",
    "author_previous_posts_count"
]

VIDEO_FEATURES = [
    "avg_brightness", "avg_contrast", "avg_saturation", 
    "avg_motion_score", "max_motion_score", "cut_count", "cuts_per_second",
    "visual_change_score", "dominant_color_bucket", "face_presence_ratio",
    "blur_score_avg", "sharpness_score_avg", "edge_density_avg",
    "text_like_region_ratio", "hook_motion_0_1s", "hook_motion_0_3s", "hook_motion_0_5s",
    "hook_cut_count_0_3s", "hook_brightness_delta_0_3s", "hook_saturation_delta_0_3s",
    "first_second_visual_change", "avg_shot_length_sec", "median_shot_length_sec"
]


def score_all(df: pd.DataFrame, target_col: str, cfg: ScoringConfig) -> pd.DataFrame:
    """Run all scoring models and return predictions dataframe."""
    df = df.copy()
    
    # Check what features actually exist in the df
    meta_cols = [c for c in METADATA_FEATURES if c in df.columns]
    video_cols = [c for c in VIDEO_FEATURES if c in df.columns]
    
    # A. Popularity Baseline
    if "views_now" in df.columns:
        df["popularity_baseline"] = df["views_now"]
    
    # B. Momentum Baseline
    if "views_velocity_6h" in df.columns:
        df["momentum_baseline"] = df["views_velocity_6h"]
    elif "views_delta_24h" in df.columns:
        df["momentum_baseline"] = df["views_delta_24h"]
        
    # ML Models preparation
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.model_selection import train_test_split
    
    # Use temporal split for evaluation during scoring phase
    # (Note: proper walk-forward uses validation.py, this is just for feature contribution analysis)
    df_sorted = df.sort_values("collected_at")
    train_size = int(len(df_sorted) * 0.7)
    train_df = df_sorted.iloc[:train_size]
    test_df = df_sorted.iloc[train_size:]
    
    y_train = train_df[target_col]
    y_test = test_df[target_col] if not test_df.empty else None
    
    def train_and_score(features, prefix):
        if not features or len(np.unique(y_train)) < 2:
            df[f"{prefix}_score"] = 0.0
            return
            
        X_train = train_df[features].fillna(0)
        X_all = df[features].fillna(0)
        
        clf = HistGradientBoostingClassifier(
            max_iter=cfg.max_iter, 
            learning_rate=cfg.learning_rate,
            random_state=42
        )
        clf.fit(X_train, y_train)
        df[f"{prefix}_score"] = clf.predict_proba(X_all)[:, 1]
        
    # C. Metadata-only ML
    train_and_score(meta_cols, "metadata_only_ml")
    
    # D. Video-only ML
    train_and_score(video_cols, "video_only_ml")
    
    # E. Metadata + Video ML
    train_and_score(meta_cols + video_cols, "metadata_plus_video_ml")
    
    # Tag split
    df["split"] = "train"
    if not test_df.empty:
        df.loc[test_df.index, "split"] = "test"
        
    df["target"] = df[target_col]
    
    return df
