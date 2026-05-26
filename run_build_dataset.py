"""
run_build_dataset.py  -  Build as-of feature table from metadata snapshots + video sidecars.

Usage:
  python run_build_dataset.py --metadata samples/input/metadata_snapshots.csv --sidecars samples/output --output samples/output/features.parquet
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from stp.config import load_config
from stp.metadata_loader import load_metadata
from stp.feature_builder import (
    build_feature_table,
    compute_targets,
    save_feature_table,
    save_feature_dictionary,
)
from stp.utils import setup_logging

logger = logging.getLogger("stp.run_build_dataset")


def main() -> None:
    parser = argparse.ArgumentParser(description="STP  -  Build feature dataset")
    parser.add_argument("--metadata", "-m", type=Path, required=True,
                        help="Path to metadata_snapshots.csv")
    parser.add_argument("--sidecars", "-s", type=Path, required=True,
                        help="Directory containing video sidecar JSONs")
    parser.add_argument("--output", "-o", type=Path, required=True,
                        help="Output path for feature table (parquet or csv)")
    parser.add_argument("--config", "-c", type=Path, default=None,
                        help="Path to config.yaml")
    args = parser.parse_args()

    setup_logging()
    cfg = load_config(args.config)

    logger.info("=" * 60)
    logger.info("STP Dataset Builder")
    logger.info("  Metadata:  %s", args.metadata)
    logger.info("  Sidecars:  %s", args.sidecars)
    logger.info("  Output:    %s", args.output)
    logger.info("=" * 60)

    # Load metadata
    meta_df = load_metadata(args.metadata.resolve())

    # Build feature table
    features_df = build_feature_table(
        meta_df,
        args.sidecars.resolve(),
        cfg.dataset,
    )

    # Compute targets
    features_df = compute_targets(features_df, horizons=[24, 48, 72])

    # Determine format
    output_path = args.output.resolve()
    fmt = "parquet" if output_path.suffix == ".parquet" else "csv"

    # Save
    save_feature_table(features_df, output_path, fmt)

    # Feature dictionary
    dict_path = output_path.parent / "feature_dictionary.json"
    save_feature_dictionary(features_df, dict_path)

    logger.info("=" * 60)
    logger.info("[OK] Dataset built")
    logger.info("  Rows:     %d", len(features_df))
    logger.info("  Columns:  %d", len(features_df.columns))
    logger.info("  Output:   %s", output_path)
    logger.info("  Dict:     %s", dict_path)

    # Target summary
    for h in [24, 48, 72]:
        col = f"top_growth_{h}h"
        if col in features_df.columns:
            pos = features_df[col].sum()
            rate = pos / len(features_df) if len(features_df) > 0 else 0
            logger.info("  Target %s: %d positive (%.1f%%)", col, pos, rate * 100)
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
