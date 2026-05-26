"""YouTube API snapshot adapter."""

import pandas as pd
from pathlib import Path
import logging

logger = logging.getLogger("stp.datasets.youtube_api")

def import_youtube_api_snapshot(input_path: Path, output_path: Path) -> None:
    """
    Adapter for snapshots from YouTube Data API (e.g., videos.list).
    Expects CSV with columns like id, snippet.publishedAt, statistics.viewCount, etc.
    """
    logger.info("Importing YouTube API snapshot dataset from %s", input_path)
    
    if input_path.is_dir():
        dfs = []
        for f in input_path.glob("*.csv"):
            try:
                # Add a collected_at column based on file modification time if missing
                df_part = pd.read_csv(f, engine="python", on_bad_lines='skip')
                if "collected_at" not in df_part.columns:
                    import os
                    from datetime import datetime, timezone
                    mtime = os.path.getmtime(f)
                    dt = datetime.fromtimestamp(mtime, tz=timezone.utc)
                    df_part["collected_at"] = dt
                dfs.append(df_part)
            except Exception as e:
                logger.warning(f"Failed to read {f}: {e}")
        if not dfs:
            raise FileNotFoundError("No valid CSVs found in input directory")
        df = pd.concat(dfs, ignore_index=True)
    else:
        df = pd.read_csv(input_path, engine="python", on_bad_lines='skip')
        if "collected_at" not in df.columns:
            import os
            from datetime import datetime, timezone
            mtime = os.path.getmtime(input_path)
            dt = datetime.fromtimestamp(mtime, tz=timezone.utc)
            df["collected_at"] = dt
        
    logger.info("Loaded %d raw rows", len(df))
    
    # Map common YouTube API columns to STP format
    mapping = {
        "id": "post_id",
        "snippet.publishedAt": "published_at",
        "snippet.categoryId": "category",
        "snippet.channelId": "author_id",
        "snippet.tags": "hashtags",
        "snippet.description": "caption",
        "statistics.viewCount": "views",
        "statistics.likeCount": "likes",
        "statistics.commentCount": "comments"
    }
    
    df = df.rename(columns={k: v for k, v in mapping.items() if k in df.columns})
    
    # Clean dates
    if "collected_at" in df.columns:
        df["collected_at"] = pd.to_datetime(df["collected_at"], errors="coerce", utc=True)
    if "published_at" in df.columns:
        df["published_at"] = pd.to_datetime(df["published_at"], errors="coerce", utc=True)
        
    df["platform"] = "youtube"
    df["dataset_source"] = "youtube_api_snapshot"
    df["is_synthetic"] = False
    
    # Ensure numeric types
    for col in ["views", "likes", "comments"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype("int64")
            
    df = df.dropna(subset=["post_id", "collected_at"])
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    logger.info("Saved normalized YouTube API dataset to %s (%d rows)", output_path, len(df))
