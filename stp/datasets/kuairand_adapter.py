"""KuaiRand/KuaiRec dataset adapter."""

import pandas as pd
from pathlib import Path
import logging

logger = logging.getLogger("stp.datasets.kuairand")

def import_kuairand(input_path: Path, output_path: Path) -> None:
    """
    Adapter for Kuaishou KuaiRand/KuaiRec recommendation datasets.
    Maps recommendation interactions to time-series trend data.
    Note: These are interaction logs, not true public trend snapshots,
    but they can be aggregated into hourly/daily view counts.
    """
    logger.info("Importing KuaiRand interaction dataset from %s", input_path)
    
    if input_path.is_dir():
        dfs = []
        for f in input_path.glob("*.csv"):
            try:
                df_part = pd.read_csv(f, engine="python", on_bad_lines='skip')
                dfs.append(df_part)
            except Exception as e:
                logger.warning(f"Failed to read {f}: {e}")
        if not dfs:
            raise FileNotFoundError("No valid CSVs found in input directory")
        df = pd.concat(dfs, ignore_index=True)
    else:
        df = pd.read_csv(input_path, engine="python", on_bad_lines='skip')
        
    logger.info("Loaded %d raw interactions", len(df))
    
    # KuaiRand typically has: video_id, user_id, is_click, is_like, is_comment, is_forward, time_ms
    mapping = {
        "video_id": "post_id",
        "time_ms": "timestamp",
        "is_click": "views",
        "is_like": "likes",
        "is_comment": "comments",
        "is_forward": "shares"
    }
    df = df.rename(columns={k: v for k, v in mapping.items() if k in df.columns})
    
    if "post_id" not in df.columns or "timestamp" not in df.columns:
        raise ValueError("KuaiRand data must contain video_id and time_ms columns.")
        
    # Convert timestamp to datetime
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit='ms', utc=True)
    
    # Floor to nearest hour for snapshots
    df["collected_at"] = df["timestamp"].dt.floor('H')
    
    # Aggregate interactions by post_id and collected_at to form snapshots
    logger.info("Aggregating interactions into snapshots...")
    agg_dict = {}
    for col in ["views", "likes", "comments", "shares"]:
        if col in df.columns:
            agg_dict[col] = "sum"
            
    snapshots = df.groupby(["post_id", "collected_at"]).agg(agg_dict).reset_index()
    
    # KuaiRand interactions are incremental. We need to calculate cumulative sums for STP.
    logger.info("Calculating cumulative metrics...")
    snapshots = snapshots.sort_values(["post_id", "collected_at"])
    for col in agg_dict.keys():
        snapshots[col] = snapshots.groupby("post_id")[col].cumsum()
        
    # Published_at is not always available, estimate as first seen timestamp
    first_seen = snapshots.groupby("post_id")["collected_at"].min().reset_index()
    first_seen = first_seen.rename(columns={"collected_at": "published_at"})
    snapshots = snapshots.merge(first_seen, on="post_id")
    
    snapshots["platform"] = "kuaishou"
    snapshots["dataset_source"] = "kuairand_interactions"
    snapshots["is_synthetic"] = False
    
    snapshots = snapshots.dropna(subset=["post_id", "collected_at"])
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    snapshots.to_csv(output_path, index=False)
    logger.info("Saved normalized KuaiRand dataset to %s (%d snapshots)", output_path, len(snapshots))
