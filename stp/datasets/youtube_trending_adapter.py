"""YouTube Trending Kaggle dataset adapter."""

import pandas as pd
from pathlib import Path
import logging

logger = logging.getLogger("stp.datasets.youtube")

def import_youtube_trending(input_path: Path, output_path: Path) -> None:
    """
    Adapter for the standard Kaggle YouTube Trending Video Dataset.
    Expects CSV with columns like video_id, trending_date, publish_time, views, likes, etc.
    """
    logger.info("Importing YouTube Trending dataset from %s", input_path)
    
    if input_path.is_dir():
        # Read all CSVs in dir
        dfs = []
        for f in input_path.glob("*.csv"):
            try:
                # Use pyarrow or python engine to handle mixed types gracefully
                df_part = pd.read_csv(f, engine="python", on_bad_lines='skip')
                dfs.append(df_part)
            except Exception as e:
                logger.warning(f"Failed to read {f}: {e}")
        if not dfs:
            raise FileNotFoundError("No valid CSVs found in input directory")
        df = pd.concat(dfs, ignore_index=True)
    else:
        df = pd.read_csv(input_path, engine="python", on_bad_lines='skip')
        
    logger.info("Loaded %d raw rows", len(df))
    
    # Map columns
    mapping = {
        "video_id": "post_id",
        "trending_date": "collected_at",
        "publish_time": "published_at",
        "publishedAt": "published_at",
        "categoryId": "category",
        "channelId": "author_id",
        "tags": "hashtags",
        "description": "caption",
        "view_count": "views",
        "comment_count": "comments"
    }
    
    df = df.rename(columns={k: v for k, v in mapping.items() if k in df.columns})
    
    # Clean dates
    if "collected_at" in df.columns:
        # Some formats are YY.DD.MM
        try:
            df["collected_at"] = pd.to_datetime(df["collected_at"], format="%y.%d.%m", utc=True)
        except ValueError:
            df["collected_at"] = pd.to_datetime(df["collected_at"], errors="coerce", utc=True)
    if "published_at" in df.columns:
        df["published_at"] = pd.to_datetime(df["published_at"], errors="coerce", utc=True)
        
    df["platform"] = "youtube"
    df["dataset_source"] = "youtube_trending_kaggle"
    df["is_synthetic"] = False
    
    # Ensure numeric types
    for col in ["views", "likes", "comments"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype("int64")
            
    df = df.dropna(subset=["post_id", "collected_at"])
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    logger.info("Saved normalized YouTube dataset to %s (%d rows)", output_path, len(df))
