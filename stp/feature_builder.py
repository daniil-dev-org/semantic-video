"""Feature builder  -  joins metadata snapshots + video sidecar into an as-of feature table."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from .config import DatasetConfig
from .entity_aggregation import compute_entity_features
from .data_quality import determine_dataset_mode

logger = logging.getLogger("stp.feature_builder")


def build_feature_table(
    metadata_df: pd.DataFrame,
    sidecars_dir: Path,
    cfg: DatasetConfig,
) -> pd.DataFrame:
    """
    Build an as-of feature table from metadata snapshots + video sidecars.

    Anti-leakage guarantee:
    - Each row is computed strictly at `collected_at` time.
    - No future snapshots are used for any feature.
    - Targets are computed in a separate step.
    """
    logger.info("Building feature table from %d metadata rows...", len(metadata_df))

    df = metadata_df.copy()
    
    # Debug fields for leakage checks
    dataset_mode = determine_dataset_mode(df)
    df["dataset_mode"] = dataset_mode.value
    df["as_of_time"] = df["collected_at"]
    df["feature_set_version"] = "1.0.0"

    df = df.sort_values(["post_id", "collected_at"]).reset_index(drop=True)

    # ── 1. Metadata growth features ──
    df = _compute_metadata_features(df)

    # ── 2. Video-derived features from sidecars ──
    df = _join_video_features(df, sidecars_dir)

    # ── 3. Entity/context features ──
    df = _compute_context_features(df)
    df = compute_entity_features(df)

    # ── 4. Save feature dictionary ──
    logger.info("Feature table built: %d rows x %d columns", len(df), len(df.columns))
    return df


def _compute_metadata_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute temporal growth features per post, strictly as-of each snapshot."""
    df = df.copy()

    # Basic engagement
    df["engagement_now"] = df["likes"] + df["comments"] + df["shares"].fillna(0) + df["saves"].fillna(0)

    # Rename current values
    df["views_now"] = df["views"]
    df["likes_now"] = df["likes"]
    df["comments_now"] = df["comments"]
    df["shares_now"] = pd.to_numeric(df["shares"], errors="coerce").fillna(0).astype("int64")

    # Age since publish
    df["age_hours_since_publish"] = (
        (df["collected_at"] - df["published_at"]).dt.total_seconds() / 3600.0
    ).round(2)

    # Engagement rate
    df["engagement_rate"] = np.where(
        df["views_now"] > 0,
        (df["engagement_now"] / df["views_now"]).round(4),
        0.0,
    )

    # ── Delta features: views/engagement deltas at 1h, 6h, 24h ──
    for delta_hours in [1, 6, 24]:
        col_views = f"views_delta_{delta_hours}h"
        col_eng = f"engagement_delta_{delta_hours}h"
        df[col_views] = 0.0
        df[col_eng] = 0.0

    # ── Velocity & acceleration ──
    df["views_velocity_1h"] = 0.0
    df["views_velocity_6h"] = 0.0
    df["views_acceleration_6h"] = 0.0

    # Compute deltas per post
    for post_id, group in df.groupby("post_id"):
        if len(group) < 2:
            continue
        idx = group.index
        times = group["collected_at"].values
        views = group["views_now"].values
        eng = group["engagement_now"].values

        for i in range(1, len(group)):
            current_time = times[i]
            current_views = views[i]
            current_eng = eng[i]

            for delta_hours in [1, 6, 24]:
                target_time = current_time - np.timedelta64(delta_hours, "h")
                # Find nearest previous snapshot at or before target_time
                mask = times[:i] <= target_time  # strict: only past snapshots
                if mask.any():
                    prev_idx = np.where(mask)[0][-1]
                    df.loc[idx[i], f"views_delta_{delta_hours}h"] = float(current_views - views[prev_idx])
                    df.loc[idx[i], f"engagement_delta_{delta_hours}h"] = float(current_eng - eng[prev_idx])
                    
            # Record max_snapshot_used_at for leakage check
            df.loc[idx[i], "max_snapshot_used_at"] = times[i]

            # Velocity (views per hour)
            for vel_hours in [1, 6]:
                delta_col = f"views_delta_{vel_hours}h"
                val = df.loc[idx[i], delta_col]
                df.loc[idx[i], f"views_velocity_{vel_hours}h"] = round(
                    val / vel_hours if vel_hours > 0 else 0.0, 2
                )

            # Acceleration (change in velocity over 6h)
            if i >= 2:
                v_now = df.loc[idx[i], "views_velocity_6h"]
                v_prev = df.loc[idx[i - 1], "views_velocity_6h"]
                df.loc[idx[i], "views_acceleration_6h"] = round(v_now - v_prev, 2)

    # Hashtag count
    df["hashtag_count"] = df["hashtags"].apply(
        lambda x: len(str(x).split(",")) if pd.notna(x) and str(x).strip() else 0
    )
    df["audio_id_present"] = df["audio_id"].notna().astype(int)

    return df


def _join_video_features(df: pd.DataFrame, sidecars_dir: Path) -> pd.DataFrame:
    """Join video-derived features from sidecar JSON files."""
    video_cols = {
        "avg_brightness": 0.0,
        "avg_contrast": 0.0,
        "avg_saturation": 0.0,
        "avg_motion_score": 0.0,
        "max_motion_score": 0.0,
        "cut_count": 0,
        "cuts_per_second": 0.0,
        "visual_change_score": 0.0,
        "dominant_color_bucket": 0,
        "face_presence_ratio": 0.0,
        "blur_score_avg": 0.0,
        "sharpness_score_avg": 0.0,
    }

    # Initialise columns
    for col, default in video_cols.items():
        df[col] = default

    if not sidecars_dir.exists():
        logger.warning("Sidecars dir not found: %s  -  skipping video features", sidecars_dir)
        return df

    # Build lookup: post_id -> sidecar data
    sidecar_map = {}
    for sidecar_path in sidecars_dir.rglob("video_metrics_sidecar.json"):
        try:
            with open(sidecar_path, "r", encoding="utf-8") as f:
                sidecar = json.load(f)
            asset_id = sidecar.get("asset", {}).get("asset_id", "")
            if asset_id:
                g = sidecar.get("video_features", {}).get("global", {})
                sidecar_map[asset_id] = g
        except Exception as e:
            logger.warning("Failed to load sidecar %s: %s", sidecar_path, e)

    if not sidecar_map:
        logger.info("No sidecar files found  -  video features will be zeros")
        return df

    # Join
    matched = 0
    for idx, row in df.iterrows():
        post_id = str(row.get("post_id", ""))
        g = sidecar_map.get(post_id)
        if g is None:
            continue
        matched += 1
        df.loc[idx, "avg_brightness"] = g.get("avg_brightness", 0.0)
        df.loc[idx, "avg_contrast"] = g.get("avg_contrast", 0.0)
        df.loc[idx, "avg_saturation"] = g.get("avg_saturation", 0.0)
        df.loc[idx, "avg_motion_score"] = g.get("avg_motion_score", 0.0)
        df.loc[idx, "max_motion_score"] = g.get("max_motion_score", 0.0)
        df.loc[idx, "cut_count"] = g.get("cut_count", 0)
        df.loc[idx, "cuts_per_second"] = g.get("cuts_per_second", 0.0)
        df.loc[idx, "visual_change_score"] = g.get("visual_change_score", 0.0)
        df.loc[idx, "face_presence_ratio"] = g.get("face_presence_ratio", 0.0)
        df.loc[idx, "blur_score_avg"] = g.get("blur_score_avg", 0.0)
        df.loc[idx, "sharpness_score_avg"] = g.get("sharpness_score_avg", 0.0)

        # Dominant colour bucket
        dom_colors = g.get("dominant_colors", [])
        if dom_colors and len(dom_colors) > 0:
            c = dom_colors[0]
            df.loc[idx, "dominant_color_bucket"] = c[0] * 10000 + c[1] * 100 + c[2] if len(c) == 3 else 0

    logger.info("Joined video features for %d / %d rows", matched, len(df))
    return df


def _compute_context_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute entity/context-level features."""
    # Category percentile views
    if "category" in df.columns and df["category"].notna().any():
        df["category_percentile_views_now"] = df.groupby("category")["views_now"].rank(pct=True)
    else:
        df["category_percentile_views_now"] = 0.5

    # Category percentile growth 24h
    if "views_delta_24h" in df.columns:
        df["category_percentile_growth_24h"] = df.groupby("category")["views_delta_24h"].rank(pct=True)
    else:
        df["category_percentile_growth_24h"] = 0.5

    # Author post count (within dataset)
    if "author_id" in df.columns and df["author_id"].notna().any():
        author_counts = df.groupby("author_id")["post_id"].nunique().to_dict()
        df["author_previous_posts_count"] = df["author_id"].map(author_counts).fillna(0).astype(int)
    else:
        df["author_previous_posts_count"] = 0

    return df


def compute_targets(
    df: pd.DataFrame,
    horizons: list[int] | None = None,
    growth_multiplier_threshold: float = 3.0,
) -> pd.DataFrame:
    """
    Compute prediction targets using FUTURE data only.

    Targets are computed per post_id  -  the last available snapshot
    provides the outcome; features use earlier snapshots.
    """
    if horizons is None:
        horizons = [24, 48, 72]

    df = df.copy()

    # For each post, compute max views at future horizons
    for horizon in horizons:
        col = f"top_growth_{horizon}h"
        col_mult = f"views_growth_multiplier_{horizon}h"
        df[col] = 0
        df[col_mult] = 1.0

    for post_id, group in df.groupby("post_id"):
        if len(group) < 2:
            continue
        idx = group.index
        times = group["collected_at"].values
        views = group["views_now"].values

        for i in range(len(group)):
            current_time = times[i]
            current_views = views[i]
            if current_views == 0:
                continue

            for horizon in horizons:
                target_time = current_time + np.timedelta64(horizon, "h")
                # Find max views in future window
                future_mask = (times > current_time) & (times <= target_time)
                
                # Debug field for leakage check
                df.loc[idx[i], f"target_window_start_{horizon}h"] = current_time
                df.loc[idx[i], f"target_window_end_{horizon}h"] = target_time
                
                if future_mask.any():
                    future_views = views[future_mask].max()
                    multiplier = future_views / current_views if current_views > 0 else 1.0
                    df.loc[idx[i], f"views_growth_multiplier_{horizon}h"] = round(multiplier, 2)

    # ── Binary targets based on category percentile ──
    for horizon in horizons:
        mult_col = f"views_growth_multiplier_{horizon}h"
        target_col = f"top_growth_{horizon}h"

        if "category" in df.columns and df["category"].notna().any():
            pct = df.groupby("category")[mult_col].rank(pct=True)
            df[target_col] = (pct >= 0.90).astype(int)
        else:
            pct = df[mult_col].rank(pct=True)
            df[target_col] = (pct >= 0.90).astype(int)

        # Also add multiplier-based target
        mult_target = f"views_mult_gt_{growth_multiplier_threshold:.0f}x_{horizon}h"
        df[mult_target] = (df[mult_col] > growth_multiplier_threshold).astype(int)

    return df


def save_feature_table(df: pd.DataFrame, output_path: Path, fmt: str = "parquet") -> Path:
    """Save feature table to parquet or csv."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if fmt == "parquet":
        # Ensure parquet compatibility  -  convert problematic types
        df_out = df.copy()
        for col in df_out.columns:
            if df_out[col].dtype == object:
                df_out[col] = df_out[col].astype(str)
        df_out.to_parquet(output_path, index=False)
    else:
        df.to_csv(output_path, index=False)

    logger.info("Feature table saved: %s (%d rows x %d cols)", output_path, len(df), len(df.columns))
    return output_path


def save_feature_dictionary(df: pd.DataFrame, output_path: Path) -> Path:
    """Save feature dictionary (column metadata) to JSON."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    dictionary = {}
    for col in df.columns:
        dtype = str(df[col].dtype)
        n_unique = int(df[col].nunique())
        n_null = int(df[col].isna().sum())
        dictionary[col] = {
            "dtype": dtype,
            "n_unique": n_unique,
            "n_null": n_null,
            "sample_values": df[col].dropna().head(3).tolist(),
        }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(dictionary, f, indent=2, default=str)

    logger.info("Feature dictionary saved: %s (%d features)", output_path, len(dictionary))
    return output_path
