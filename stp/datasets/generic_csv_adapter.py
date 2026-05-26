"""Generic CSV adapter."""

import pandas as pd
from pathlib import Path
import logging

logger = logging.getLogger("stp.datasets.generic")

def import_generic_csv(input_path: Path, output_path: Path, mapping: dict[str, str]) -> None:
    logger.info("Importing generic CSV from %s", input_path)
    df = pd.read_csv(input_path)
    
    # Rename columns based on mapping
    df = df.rename(columns=mapping)
    
    # Ensure required columns exist
    df["dataset_source"] = "generic_csv"
    df["is_synthetic"] = False
    
    if "platform" not in df.columns:
        df["platform"] = "unknown"
        
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    logger.info("Saved normalized generic dataset to %s (%d rows)", output_path, len(df))
