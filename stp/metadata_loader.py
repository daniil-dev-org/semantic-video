"""Metadata loader  -  reads metadata_snapshots.csv and builds time-indexed DataFrames."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger("stp.metadata_loader")

REQUIRED_COLUMNS = [
    "platform", "post_id", "published_at", "collected_at",
    "views", "likes", "comments",
]

OPTIONAL_COLUMNS = [
    "entity_type", "entity_id", "author_id",
    "shares", "saves",
    "caption", "hashtags", "audio_id",
    "category", "language", "country",
    "video_path", "dataset_source", "is_synthetic"
]


def load_metadata(path: Path) -> pd.DataFrame:
    """
    Load metadata_snapshots.csv.

    Parses dates, sorts by post_id + collected_at,
    and validates required columns.
    """
    if not path.exists():
        raise FileNotFoundError(f"Metadata file not found: {path}")

    df = pd.read_csv(path, parse_dates=["published_at", "collected_at"])

    # Validate required columns
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns in metadata: {missing}")

    # Fill optional columns with defaults
    for col in OPTIONAL_COLUMNS:
        if col not in df.columns:
            if col == "is_synthetic":
                df[col] = False  # Assume real if not specified, but dataset_source might override
            else:
                df[col] = None

    # Ensure numeric types
    for col in ["views", "likes", "comments", "shares", "saves"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

    # Sort for temporal ordering
    df = df.sort_values(["post_id", "collected_at"]).reset_index(drop=True)

    logger.info(
        "Loaded metadata: %d rows, %d unique posts, date range %s -> %s",
        len(df),
        df["post_id"].nunique(),
        df["collected_at"].min(),
        df["collected_at"].max(),
    )
    return df


def generate_synthetic_metadata(
    post_ids: list[str],
    num_snapshots: int = 10,
    seed: int = 42,
) -> pd.DataFrame:
    """
    Generate synthetic metadata_snapshots for demo purposes.

    Creates realistic-looking growth curves for each post.
    WARNING: synthetic data  -  real conclusions cannot be drawn.
    """
    import numpy as np

    rng = np.random.RandomState(seed)
    rows = []

    categories = ["entertainment", "education", "music", "comedy", "sports", "tech"]
    languages = ["en", "ru", "es", "pt"]
    countries = ["US", "RU", "BR", "DE", "IN"]
    platforms = ["tiktok", "youtube_shorts", "instagram_reels"]

    for post_id in post_ids:
        platform = rng.choice(platforms)
        category = rng.choice(categories)
        language = rng.choice(languages)
        country = rng.choice(countries)
        author_id = f"author_{rng.randint(1, 200):04d}"
        audio_id = f"audio_{rng.randint(1, 50):04d}" if rng.random() > 0.3 else None

        # Generate hashtags
        n_tags = rng.randint(0, 8)
        hashtags = ",".join([f"#tag{rng.randint(1, 100)}" for _ in range(n_tags)])

        # Publish time  -  random within last 14 days
        publish_offset_hours = rng.uniform(0, 14 * 24)
        published_at = pd.Timestamp.now() - pd.Timedelta(hours=publish_offset_hours)
        published_at = published_at.floor("min")

        # Growth model: exponential with noise
        is_viral = rng.random() < 0.15  # 15% go viral
        base_views = rng.randint(50, 500)
        growth_rate = rng.uniform(0.02, 0.08) if not is_viral else rng.uniform(0.08, 0.2)
        engagement_mult = rng.uniform(0.03, 0.15)

        for snap_i in range(num_snapshots):
            hours_since = snap_i * (72 / num_snapshots)  # spread over 72h
            collected_at = published_at + pd.Timedelta(hours=hours_since)

            views = int(min(base_views * np.exp(growth_rate * hours_since) + rng.normal(0, 20), 10_000_000))
            views = max(0, views)
            likes = max(0, int(views * engagement_mult * rng.uniform(0.5, 1.5)))
            comments = max(0, int(likes * rng.uniform(0.05, 0.3)))
            shares = max(0, int(likes * rng.uniform(0.02, 0.15)))
            saves = max(0, int(likes * rng.uniform(0.01, 0.1)))

            rows.append({
                "platform": platform,
                "post_id": post_id,
                "entity_type": "post",
                "entity_id": post_id,
                "author_id": author_id,
                "published_at": published_at,
                "collected_at": collected_at,
                "views": views,
                "likes": likes,
                "comments": comments,
                "shares": shares,
                "saves": saves,
                "caption": f"Demo caption for {post_id}",
                "hashtags": hashtags,
                "audio_id": audio_id,
                "category": category,
                "language": language,
                "country": country,
                "video_path": f"{post_id}.mp4",
                "dataset_source": "synthetic_demo",
                "is_synthetic": True,
            })

    df = pd.DataFrame(rows)
    df["published_at"] = pd.to_datetime(df["published_at"])
    df["collected_at"] = pd.to_datetime(df["collected_at"])

    logger.info(
        "Generated synthetic metadata: %d rows, %d posts",
        len(df), len(post_ids),
    )
    return df
