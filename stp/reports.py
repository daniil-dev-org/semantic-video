"""Report generator  -  builds Markdown and JSON validation reports."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .validation import HypothesisResult
from .data_quality import DatasetMode, PredictionValidity

logger = logging.getLogger("stp.reports")


def generate_report(
    results: list[HypothesisResult],
    output_dir: Path,
    dataset_mode: str,
    coverage_report: dict[str, Any],
    leakage_passed: bool,
    model_comparison_data: list[dict[str, Any]],
    include_charts: bool = False,
) -> dict[str, Path]:
    """Generate Markdown report for the validation run."""
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {}

    md_path = output_dir / "report.md"
    _write_markdown(
        md_path, results, dataset_mode, coverage_report, 
        leakage_passed, model_comparison_data
    )
    paths["markdown"] = md_path

    logger.info("Reports saved to %s", output_dir)
    return paths


def _write_markdown(
    path: Path, 
    results: list[HypothesisResult],
    dataset_mode: str,
    coverage_report: dict[str, Any],
    leakage_passed: bool,
    model_comparison_data: list[dict[str, Any]]
) -> None:
    lines = [
        "# STP Validation Report",
        f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        "",
        "## 1. Executive Summary",
        ""
    ]

    if dataset_mode == "synthetic":
        lines.append("> [!WARNING]")
        lines.append("> **This run is a technical pipeline validation, not a valid trend prediction experiment.**")
        lines.append("> The dataset mode is synthetic. Results reflect pipeline mechanics only.")
    elif coverage_report and not coverage_report.get("passed_thresholds"):
        lines.append("> [!CAUTION]")
        lines.append("> **Data is real, but insufficient for strong conclusions.**")
        lines.append("> Several data quality thresholds were not met.")
    else:
        lines.append("Validation run completed on a real dataset meeting all minimum thresholds.")

    acc = sum(1 for r in results if r.verdict in ("ACCEPTED", "DEMO_ACCEPTED"))
    rej = sum(1 for r in results if r.verdict == "REJECTED")
    inc = sum(1 for r in results if r.verdict == "INCONCLUSIVE")
    disc = sum(1 for r in results if r.verdict in ("DISCOVERY_ONLY", "DEMO_ONLY"))

    lines.extend([
        "",
        f"- **Total Hypotheses:** {len(results)}",
        f"- **Accepted:** {acc}",
        f"- **Rejected:** {rej}",
        f"- **Inconclusive:** {inc}",
        f"- **Discovery Only:** {disc}",
        ""
    ])

    lines.extend([
        "## 2. Dataset Validity",
        f"- **Dataset Mode:** {dataset_mode.upper()}",
        f"- **Prediction Validity:** {DatasetMode(dataset_mode).name if dataset_mode in [m.value for m in DatasetMode] else 'UNKNOWN'}",
        ""
    ])

    lines.append("## 3. Data Coverage")
    if coverage_report and coverage_report.get("metrics"):
        m = coverage_report["metrics"]
        lines.extend([
            f"- **Posts:** {m.get('posts_count', 0)}",
            f"- **Snapshots:** {m.get('snapshots_count', 0)}",
            f"- **Days Covered:** {m.get('days_covered', 0)}",
            f"- **Median Snapshots/Post:** {m.get('median_snapshots_per_post', 0):.1f}",
            ""
        ])
        fails = coverage_report.get("failed_thresholds", [])
        if fails:
            lines.append("**Failed Thresholds:**")
            for f in fails:
                lines.append(f"- {f}")
            lines.append("")

    lines.extend([
        "## 4. Leakage Check",
        f"**Status:** {'✅ PASSED' if leakage_passed else '❌ FAILED'}",
        ""
    ])

    lines.append("## 5. Model Comparison")
    lines.append("| Model | Precision@50 | Lift |")
    lines.append("|---|---|---|")
    for row in model_comparison_data:
        lines.append(f"| {row['model']} | {row['p50']:.4f} | {row['lift']:.4f} |")
    lines.append("")

    lines.append("## 6. Video Feature Contribution")
    video_lift = 1.0
    for r in results:
        if r.video_incremental_lift > 0:
            video_lift = max(video_lift, r.video_incremental_lift)
            
    lines.append(f"**Incremental Lift from Video Features:** {video_lift:.4f}x")
    if video_lift < 1.05 and dataset_mode != "synthetic":
        lines.append("> [!WARNING]")
        lines.append("> Video sidecar features did not add meaningful predictive lift over metadata-only model.")
    lines.append("")

    lines.append("## 7. Hypothesis Results")
    for r in results:
        emoji = "✅" if "ACCEPTED" in r.verdict else "❌" if r.verdict == "REJECTED" else "❓"
        lines.extend([
            f"### {r.hypothesis_id}: {r.name}",
            f"- **Verdict:** {emoji} **{r.verdict}**",
            f"- **Reason:** {r.verdict_reason}",
            f"- **Rolling Lift:** {r.avg_lift:.4f}",
            f"- **Rolling P@50:** {r.avg_precision_at_50:.4f}",
            f"- **Holdout Lift:** {f'{r.holdout_result.lift:.4f}' if r.holdout_result is not None else 'N/A'}",
            ""
        ])

    lines.extend([
        "## 8. Multiple Testing Warnings",
        "- **Exploratory Tests:** " + str(sum(1 for r in results if "DISCOVERY" in r.verdict)),
        ""
    ])

    lines.extend([
        "## 9. Limitations",
        "- This is a technical Proof of Concept.",
        "- Features are bounded by what is visible in 144p proxies.",
        "",
        "## 10. Next Actions",
        "- Replace synthetic data with a real dataset.",
        "- Run `run_import_dataset.py` with the appropriate adapter."
    ])

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
