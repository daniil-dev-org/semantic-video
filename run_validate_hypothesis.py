"""
run_validate_hypothesis.py  -  Validate trend hypotheses using walk-forward backtesting.

Usage:
  python run_validate_hypothesis.py --features samples/output/features.parquet --hypotheses samples/input/hypotheses.yaml --output samples/output/validation_report
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import pandas as pd

from stp.config import load_config
from stp.hypothesis import load_hypotheses
from stp.validation import validate_hypothesis
from stp.reports import generate_report
from stp.utils import setup_logging
from stp.data_quality import determine_dataset_mode, generate_coverage_report
from stp.leakage_checks import check_feature_table_leakage

logger = logging.getLogger("stp.run_validate_hypothesis")


def main() -> None:
    parser = argparse.ArgumentParser(description="STP  -  Hypothesis validation")
    parser.add_argument("--features", "-f", type=Path, required=True,
                        help="Path to features.parquet or features.csv")
    parser.add_argument("--hypotheses", type=Path, required=True,
                        help="Path to hypotheses.yaml")
    parser.add_argument("--output", "-o", type=Path, required=True,
                        help="Output directory for validation report")
    parser.add_argument("--config", "-c", type=Path, default=None,
                        help="Path to config.yaml")
    args = parser.parse_args()

    setup_logging()
    cfg = load_config(args.config)

    logger.info("=" * 60)
    logger.info("STP Hypothesis Validation")
    logger.info("  Features:    %s", args.features)
    logger.info("  Hypotheses:  %s", args.hypotheses)
    logger.info("  Output:      %s", args.output)
    logger.info("=" * 60)

    # Load features
    features_path = args.features.resolve()
    if features_path.suffix == ".parquet":
        df = pd.read_parquet(features_path)
    else:
        df = pd.read_csv(features_path, parse_dates=["published_at", "collected_at"])

    # Ensure datetime types
    for col in ["published_at", "collected_at"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col])

    logger.info("Loaded features: %d rows x %d columns", len(df), len(df.columns))
    
    dataset_mode = determine_dataset_mode(df).value
    coverage = generate_coverage_report(df, cfg.data_quality)
    leakage_res = check_feature_table_leakage(df)
    
    logger.info("Dataset Mode: %s", dataset_mode)
    logger.info("Coverage thresholds passed: %s", coverage.get("passed_thresholds"))

    # Load hypotheses
    hypotheses = load_hypotheses(args.hypotheses.resolve())

    # Validate each hypothesis
    results = []
    for hyp in hypotheses:
        logger.info("Validating: %s  -  %s", hyp.hypothesis_id, hyp.name)
        result = validate_hypothesis(
            df=df,
            hyp=hyp,
            cfg=cfg.validation,
            dataset_mode=dataset_mode,
            passed_data_quality=coverage.get("passed_thresholds", False),
            is_preregistered=hyp.preregistered
        )
        results.append(result)
        emoji = {"ACCEPTED": "[+]", "DEMO_ACCEPTED": "[D]", "REJECTED": "[-]", "INCONCLUSIVE": "[!]", "PARTIAL": "[P]", "INVALID": "[X]", "DEMO_ONLY": "[?]"}
        e = emoji.get(result.verdict, "[?]")
        logger.info("  -> %s %s (lift=%.2f, P@50=%.2f, samples=%d)",
                     e, result.verdict, result.avg_lift,
                     result.avg_precision_at_50, result.total_sample_size)
                     
    # Generate model comparison data
    mc_data = []
    target_col = "top_growth_72h"
    if target_col in df.columns:
        for model in ["metadata_only_ml_score", "video_only_ml_score", "metadata_plus_video_ml_score", "popularity_baseline", "momentum_baseline"]:
            if model in df.columns:
                df_sorted = df.sort_values(model, ascending=False)
                total_pos = df[target_col].sum()
                if total_pos > 0:
                    p50 = df_sorted.head(50)[target_col].mean()
                    b_p50 = df[target_col].mean()
                    lift = p50 / b_p50 if b_p50 > 0 else 0.0
                    mc_data.append({"model": model, "p50": p50, "lift": lift})

    # Generate report
    output_dir = args.output.resolve()
    outputs = generate_report(
        results=results,
        output_dir=output_dir,
        dataset_mode=dataset_mode,
        coverage_report=coverage,
        leakage_passed=leakage_res.get("passed", False),
        model_comparison_data=mc_data,
        include_charts=cfg.reports.include_charts
    )

    logger.info("=" * 60)
    logger.info("[OK] Validation complete")
    logger.info("  Hypotheses:   %d", len(results))
    logger.info("  Accepted:     %d", sum(1 for r in results if r.verdict in ("ACCEPTED", "DEMO_ACCEPTED", "PARTIAL")))
    logger.info("  Rejected:     %d", sum(1 for r in results if r.verdict == "REJECTED"))
    logger.info("  Inconclusive: %d", sum(1 for r in results if r.verdict == "INCONCLUSIVE"))
    for key, path in outputs.items():
        if isinstance(path, Path):
            logger.info("  Report (%s): %s", key, path)
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
