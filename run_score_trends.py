"""
run_score_trends.py  -  Run baseline + ML trend scoring.

Usage:
  python run_score_trends.py --features samples/output/features.parquet --target top_growth_72h --output samples/output/predictions.csv
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import pandas as pd

from stp.config import load_config
from stp.trend_scoring import score_all
from stp.utils import setup_logging

logger = logging.getLogger("stp.run_score_trends")


def main() -> None:
    parser = argparse.ArgumentParser(description="STP  -  Trend scoring")
    parser.add_argument("--features", "-f", type=Path, required=True,
                        help="Path to features.parquet or features.csv")
    parser.add_argument("--target", "-t", type=str, default="top_growth_72h",
                        help="Target column name")
    parser.add_argument("--output", "-o", type=Path, required=True,
                        help="Output path for predictions CSV")
    parser.add_argument("--config", "-c", type=Path, default=None,
                        help="Path to config.yaml")
    args = parser.parse_args()

    setup_logging()
    cfg = load_config(args.config)

    logger.info("=" * 60)
    logger.info("STP Trend Scoring")
    logger.info("  Features: %s", args.features)
    logger.info("  Target:   %s", args.target)
    logger.info("  Output:   %s", args.output)
    logger.info("=" * 60)

    # Load features
    features_path = args.features.resolve()
    if features_path.suffix == ".parquet":
        df = pd.read_parquet(features_path)
    else:
        df = pd.read_csv(features_path, parse_dates=["published_at", "collected_at"])

    logger.info("Loaded %d rows x %d columns", len(df), len(df.columns))

    if args.target not in df.columns:
        logger.error("Target column '%s' not found. Available: %s",
                      args.target, [c for c in df.columns if "growth" in c or "target" in c])
        raise SystemExit(1)

    # Run scoring
    predictions = score_all(df, args.target, cfg.scoring)

    # Save
    output_path = args.output.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    predictions.to_csv(output_path, index=False)

    # Summary
    test_preds = predictions[predictions["split"] == "test"]
    logger.info("=" * 60)
    logger.info("[OK] Predictions saved: %s", output_path)
    logger.info("  Total rows:  %d", len(predictions))
    logger.info("  Test rows:   %d", len(test_preds))
    if len(test_preds) > 0 and "target" in test_preds.columns:
        pos = test_preds["target"].sum()
        logger.info("  Test positives: %d (%.1f%%)", pos, pos / len(test_preds) * 100)

        # Quick ranking check for each scorer
        for scorer_name in ["popularity_baseline", "momentum_baseline",
                            "metadata_only_ml_score", "video_only_ml_score", "metadata_plus_video_ml_score"]:
            if scorer_name in test_preds.columns:
                top50 = test_preds.nlargest(min(50, len(test_preds)), scorer_name)
                p_at_50 = top50["target"].mean() if len(top50) > 0 else 0
                logger.info("  %s P@50: %.2f", scorer_name, p_at_50)
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
