"""Entity-level trend aggregation — builds features for audios, hashtags, and visual tokens."""

from __future__ import annotations

import logging
from typing import Optional

import pandas as pd
import numpy as np

logger = logging.getLogger("stp.entity_aggregation")


def generate_visual_token(row: pd.Series) -> str:
    """Create a discrete visual token from bucketed video features."""
    if pd.isna(row.get("avg_motion_score")):
        return "no_video"
    
    m = row["avg_motion_score"]
    motion_bucket = "high_motion" if m > 0.15 else ("med_motion" if m > 0.05 else "low_motion")
    
    c = row.get("cuts_per_second", 0)
    cuts_bucket = "fast_cuts" if c > 0.5 else "slow_cuts"
    
    f = row.get("face_presence_ratio", 0)
    face_bucket = "has_face" if f > 0.3 else "no_face"
    
    b = row.get("avg_brightness", 0.5)
    bright_bucket = "bright" if b > 0.6 else ("dark" if b < 0.3 else "med_bright")
    
    return f"{motion_bucket}_{cuts_bucket}_{face_bucket}_{bright_bucket}"


def compute_entity_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute aggregate features for entities (audio, hashtag, visual_token)
    at the exact point in time (as_of_time).
    
    Returns original dataframe merged with entity features.
    """
    if df.empty:
        return df

    logger.info("Computing entity-level aggregations...")
    df = df.copy()
    
    # Generate visual tokens
    if "visual_token" not in df.columns:
        df["visual_token"] = df.apply(generate_visual_token, axis=1)

    # We must compute aggregations strictly looking backward from each row's collected_at.
    # To do this efficiently, we sort by collected_at.
    df_sorted = df.sort_values("collected_at")
    
    # Audio aggregation
    if "audio_id" in df.columns:
        # A simple rolling count approximation for performance in MVP:
        # Just group by audio_id and use expanding window if needed, but for true as-of
        # we'd need a self-join. For PoC, we approximate by calculating cumulative counts.
        # In a real DW, this is done via window functions.
        audio_counts = df_sorted.groupby("audio_id").cumcount() + 1
        df_sorted["audio_posts_count_lifetime"] = audio_counts
    
    # Hashtags (we might have comma-separated, so we just take the first for simplicity in MVP)
    if "hashtags" in df.columns:
        df_sorted["primary_hashtag"] = df_sorted["hashtags"].astype(str).str.split(",").str[0]
        hash_counts = df_sorted.groupby("primary_hashtag").cumcount() + 1
        df_sorted["hashtag_posts_count_lifetime"] = hash_counts

    # Visual Token
    vt_counts = df_sorted.groupby("visual_token").cumcount() + 1
    df_sorted["visual_token_posts_count_lifetime"] = vt_counts

    # Re-sort to original index
    df_result = df_sorted.sort_index()
    
    return df_result
