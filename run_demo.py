"""
run_demo.py  -  End-to-end STP demo pipeline.

Runs the full pipeline:
  1. Create 144p proxy for each video
  2. Extract features + build sidecar
  3. Load/generate metadata snapshots
  4. Build feature table
  5. Run trend scoring
  6. Validate hypotheses
  7. Generate report

Usage:
  python run_demo.py
  python run_demo.py --config config.yaml
"""

from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path

import pandas as pd

from stp.config import load_config
from stp.ffmpeg_tools import probe_video
from stp.proxy_encoder import encode_proxy
from stp.video_features import extract_features, select_keyframes, save_keyframes
from stp.sidecar_schema import build_sidecar, save_sidecar
from stp.metadata_loader import load_metadata, generate_synthetic_metadata
from stp.feature_builder import (
    build_feature_table,
    compute_targets,
    save_feature_table,
    save_feature_dictionary,
)
from stp.trend_scoring import score_all
from stp.hypothesis import load_hypotheses
from stp.validation import validate_hypothesis
from stp.reports import generate_report
from stp.utils import setup_logging, sha256_file, ensure_dir
from stp.data_quality import determine_dataset_mode, generate_coverage_report
from stp.leakage_checks import check_feature_table_leakage

logger = logging.getLogger("stp.run_demo")

# Project paths
PROJECT_ROOT = Path(__file__).parent.resolve()
SAMPLES_INPUT = PROJECT_ROOT / "samples" / "input"
SAMPLES_OUTPUT = PROJECT_ROOT / "samples" / "output"
VIDEOS_DIR = SAMPLES_INPUT / "videos"
METADATA_PATH = SAMPLES_INPUT / "metadata_snapshots.csv"
HYPOTHESES_PATH = SAMPLES_INPUT / "hypotheses.yaml"


def main() -> None:
    parser = argparse.ArgumentParser(description="STP  -  Full demo pipeline")
    parser.add_argument("--config", "-c", type=Path, default=None)
    args = parser.parse_args()

    setup_logging()
    cfg = load_config(args.config)

    t_start = time.perf_counter()

    logger.info("=" * 60)
    logger.info("  +========================================+")
    logger.info("  |  STP v0.1  -  Semantic Trend PoC Demo  |")
    logger.info("  +========================================+")
    logger.info("=" * 60)

    ensure_dir(SAMPLES_OUTPUT)
    ensure_dir(VIDEOS_DIR)

    is_synthetic = False

    # ── Step 1-2: Process videos ──
    video_files = list(VIDEOS_DIR.glob("*.mp4")) + list(VIDEOS_DIR.glob("*.webm")) + list(VIDEOS_DIR.glob("*.avi"))

    if not video_files:
        logger.info("No videos found in %s  -  generating synthetic video", VIDEOS_DIR)
        video_files = _generate_synthetic_video(VIDEOS_DIR)

    post_ids = []
    for vf in video_files:
        post_id = vf.stem
        post_ids.append(post_id)
        out_dir = SAMPLES_OUTPUT / post_id

        logger.info("=" * 60)
        logger.info("Processing video: %s -> %s", vf.name, out_dir)

        try:
            meta = probe_video(vf)

            # Proxy
            proxy_path, _ = encode_proxy(vf, out_dir, cfg.proxy, meta)

            # Features
            metrics = extract_features(vf, cfg.video_features, meta.fps, meta.duration_ms)
            kf_indices = select_keyframes(metrics, cfg.video_features.keyframe_count)
            kf_files = save_keyframes(vf, metrics, kf_indices, out_dir / "keyframes", meta.fps)

            # Sidecar
            sidecar_doc = build_sidecar(
                asset_id=post_id,
                source_name=vf.name,
                meta=meta,
                metrics=metrics,
                proxy_cfg=cfg.proxy,
                feat_cfg=cfg.video_features,
                keyframe_files=kf_files,
            )
            sidecar_doc.integrity.source_sha256 = sha256_file(vf)
            if proxy_path.exists():
                sidecar_doc.integrity.proxy_sha256 = sha256_file(proxy_path)

            sidecar_path = out_dir / "video_metrics_sidecar.json"
            save_sidecar(sidecar_doc, sidecar_path)
            sidecar_doc.integrity.sidecar_sha256 = sha256_file(sidecar_path)
            save_sidecar(sidecar_doc, sidecar_path)

            # Quick metrics
            import json
            quick_metrics = {
                "asset_id": post_id,
                "sampled_frames": sidecar_doc.video_features.global_features.sampled_frames,
                "cut_count": sidecar_doc.video_features.global_features.cut_count,
                "face_presence_ratio": sidecar_doc.video_features.global_features.face_presence_ratio,
                "avg_motion_score": sidecar_doc.video_features.global_features.avg_motion_score,
            }
            with open(out_dir / "metrics.json", "w") as f:
                json.dump(quick_metrics, f, indent=2)

            logger.info("[OK] %s processed  -  %d frames, %d cuts",
                        post_id,
                        sidecar_doc.video_features.global_features.sampled_frames,
                        sidecar_doc.video_features.global_features.cut_count)

        except Exception as e:
            logger.error("Failed to process %s: %s", vf.name, e)

    # ── Step 3: Load or generate metadata ──
    logger.info("=" * 60)
    logger.info("Step 3  -  Loading metadata snapshots")

    if METADATA_PATH.exists():
        meta_df = load_metadata(METADATA_PATH)
        logger.info("Loaded real metadata: %d rows", len(meta_df))
    else:
        logger.info("metadata_snapshots.csv not found  -  generating synthetic data")
        is_synthetic = True
        # Generate for actual post_ids + extra synthetic ones
        all_post_ids = post_ids.copy()
        for i in range(max(0, 30 - len(post_ids))):
            all_post_ids.append(f"synth_post_{i + 1:03d}")
        meta_df = generate_synthetic_metadata(all_post_ids, num_snapshots=10)
        meta_df.to_csv(METADATA_PATH, index=False)
        logger.info("Synthetic metadata saved: %s (%d rows)", METADATA_PATH, len(meta_df))

    # ── Step 4: Build features ──
    logger.info("=" * 60)
    logger.info("Step 4  -  Building feature table")

    features_df = build_feature_table(meta_df, SAMPLES_OUTPUT, cfg.dataset)
    features_df = compute_targets(features_df, horizons=[24, 48, 72])

    features_path = SAMPLES_OUTPUT / "features.parquet"
    try:
        save_feature_table(features_df, features_path, "parquet")
    except Exception:
        features_path = SAMPLES_OUTPUT / "features.csv"
        save_feature_table(features_df, features_path, "csv")

    save_feature_dictionary(features_df, SAMPLES_OUTPUT / "feature_dictionary.json")

    # ── Step 5: Trend scoring ──
    logger.info("=" * 60)
    logger.info("Step 5  -  Running trend scoring")

    target_col = "top_growth_72h"
    if target_col not in features_df.columns:
        logger.warning("Target '%s' not available  -  skipping scoring", target_col)
        predictions = pd.DataFrame()
    else:
        predictions = score_all(features_df, target_col, cfg.scoring)
        pred_path = SAMPLES_OUTPUT / "predictions.csv"
        predictions.to_csv(pred_path, index=False)
        logger.info("Predictions saved: %s (%d rows)", pred_path, len(predictions))

    # ── Step 6: Hypothesis validation ──
    logger.info("=" * 60)
    logger.info("Step 6  -  Validating hypotheses")

    if HYPOTHESES_PATH.exists():
        hypotheses = load_hypotheses(HYPOTHESES_PATH)
    else:
        logger.info("hypotheses.yaml not found  -  using built-in demo hypotheses")
        from stp.hypothesis import HypothesisSpec, FilterCondition, TargetDefinition, SuccessCriteria
        hypotheses = [
            HypothesisSpec(
                hypothesis_id="h_001",
                name="High motion videos grow faster",
                filter={"avg_motion_score": FilterCondition(op=">", value=0.05)},
                signal_window_hours=24,
                prediction_horizon_hours=72,
                target=TargetDefinition(name="top_growth_72h"),
                success_criteria=SuccessCriteria(min_sample_size=10, min_lift=1.1, min_precision_at_50=0.15),
            ),
            HypothesisSpec(
                hypothesis_id="h_002",
                name="Fast cuts correlate with breakout",
                filter={"cuts_per_second": FilterCondition(op=">", value=0.3)},
                signal_window_hours=24,
                prediction_horizon_hours=72,
                target=TargetDefinition(name="top_growth_72h"),
                success_criteria=SuccessCriteria(min_sample_size=10, min_lift=1.1, min_precision_at_50=0.15),
            ),
            HypothesisSpec(
                hypothesis_id="h_003",
                name="Face-present videos outperform no-face",
                filter={"face_presence_ratio": FilterCondition(op=">", value=0.1)},
                signal_window_hours=24,
                prediction_horizon_hours=72,
                target=TargetDefinition(name="top_growth_72h"),
                success_criteria=SuccessCriteria(min_sample_size=10, min_lift=1.1, min_precision_at_50=0.15),
            ),
        ]

    dataset_mode = determine_dataset_mode(features_df).value
    if dataset_mode == "synthetic":
        logger.info("Adjusting validation config for small synthetic dataset")
        cfg.validation.train_window_days = 5
        cfg.validation.step_days = 1
        cfg.validation.test_horizon_hours = 24
        
    coverage = generate_coverage_report(features_df, cfg.data_quality)
    leakage_res = check_feature_table_leakage(features_df)

    results = []
    for hyp in hypotheses:
        logger.info("Validating: %s  -  %s", hyp.hypothesis_id, hyp.name)
        result = validate_hypothesis(
            df=features_df, 
            hyp=hyp, 
            cfg=cfg.validation,
            dataset_mode=dataset_mode,
            passed_data_quality=coverage.get("passed_thresholds", False),
            is_preregistered=getattr(hyp, "preregistered", False)
        )
        results.append(result)
        emoji = {"ACCEPTED": "[+]", "DEMO_ACCEPTED": "[D]", "REJECTED": "[-]", "INCONCLUSIVE": "[!]", "PARTIAL": "[P]", "INVALID": "[X]", "DEMO_ONLY": "[?]"}
        e = emoji.get(result.verdict, "[?]")
        logger.info("  -> %s %s (lift=%.2f, samples=%d)",
                     e, result.verdict, result.avg_lift, result.total_sample_size)

    # Generate model comparison data
    mc_data = []
    target_col = "top_growth_72h"
    if target_col in features_df.columns:
        for model in ["metadata_only_ml_score", "video_only_ml_score", "metadata_plus_video_ml_score", "popularity_baseline", "momentum_baseline"]:
            if model in features_df.columns:
                df_sorted = features_df.sort_values(model, ascending=False)
                total_pos = features_df[target_col].sum()
                if total_pos > 0:
                    p50 = df_sorted.head(50)[target_col].mean()
                    b_p50 = features_df[target_col].mean()
                    lift = p50 / b_p50 if b_p50 > 0 else 0.0
                    mc_data.append({"model": model, "p50": p50, "lift": lift})

    # ── Step 7: Generate report ──
    logger.info("=" * 60)
    logger.info("Step 7  -  Generating report")

    report_dir = SAMPLES_OUTPUT / "validation_report"
    outputs = generate_report(
        results=results, 
        output_dir=report_dir, 
        dataset_mode=dataset_mode,
        coverage_report=coverage,
        leakage_passed=leakage_res.get("passed", False),
        model_comparison_data=mc_data,
        include_charts=True
    )

    # ── Summary ──
    elapsed = time.perf_counter() - t_start

    logger.info("")
    logger.info("=" * 60)
    logger.info("  +========================================+")
    logger.info("  |          DEMO COMPLETE                 |")
    logger.info("  +========================================+")
    logger.info("=" * 60)
    logger.info("")
    logger.info("  Videos processed:   %d", len(post_ids))
    logger.info("  Metadata rows:      %d", len(meta_df))
    logger.info("  Feature rows:       %d x %d", len(features_df), len(features_df.columns))
    logger.info("  Hypotheses tested:  %d", len(results))
    logger.info("    Accepted:         %d", sum(1 for r in results if r.verdict == "ACCEPTED"))
    logger.info("    Rejected:         %d", sum(1 for r in results if r.verdict == "REJECTED"))
    logger.info("    Inconclusive:     %d", sum(1 for r in results if r.verdict == "INCONCLUSIVE"))
    logger.info("  Total time:         %.1f sec", elapsed)
    logger.info("")

    if is_synthetic:
        logger.info("  [!]  SYNTHETIC DATA  -  results are for pipeline demo only.")
        logger.info("  [!]  Do NOT draw real conclusions from synthetic data.")
        logger.info("")

    logger.info("  Output directory:   %s", SAMPLES_OUTPUT)
    logger.info("  Validation report:  %s", report_dir / "report.md")
    logger.info("=" * 60)


def _generate_synthetic_video(output_dir: Path) -> list[Path]:
    """Generate a simple synthetic test video using OpenCV."""
    import cv2
    import numpy as np

    output_dir.mkdir(parents=True, exist_ok=True)

    videos = []
    for i in range(3):
        post_id = f"vid_{i + 1:04d}"
        path = output_dir / f"{post_id}.mp4"

        # Create a simple test video with moving shapes
        fps = 24
        duration_sec = 5
        width, height = 640, 480
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(str(path), fourcc, fps, (width, height))

        rng = np.random.RandomState(42 + i)
        base_color = rng.randint(30, 200, size=3).tolist()

        for frame_i in range(fps * duration_sec):
            frame = np.full((height, width, 3), base_color, dtype=np.uint8)

            # Moving circle
            cx = int(width * (0.2 + 0.6 * abs(np.sin(frame_i / fps * 2))))
            cy = int(height * (0.3 + 0.4 * abs(np.cos(frame_i / fps * 1.5))))
            radius = 30 + int(20 * np.sin(frame_i / fps))
            cv2.circle(frame, (cx, cy), radius, (255, 255, 255), -1)

            # Simulated face region (square)
            if i % 2 == 0:  # only some videos have "faces"
                fx = width // 3
                fy = height // 4
                fw = width // 5
                fh = int(fw * 1.3)
                cv2.rectangle(frame, (fx, fy), (fx + fw, fy + fh), (200, 180, 170), -1)
                cv2.circle(frame, (fx + fw//3, fy + fh//3), 8, (60, 60, 60), -1)
                cv2.circle(frame, (fx + 2*fw//3, fy + fh//3), 8, (60, 60, 60), -1)
                cv2.ellipse(frame, (fx + fw//2, fy + 2*fh//3), (15, 8), 0, 0, 180, (60, 60, 60), 2)

            # Add noise
            noise = rng.randint(-10, 10, frame.shape, dtype=np.int16)
            frame = np.clip(frame.astype(np.int16) + noise, 0, 255).astype(np.uint8)

            # Scene cut simulation (at second 2)
            if frame_i == fps * 2:
                frame = rng.randint(0, 255, (height, width, 3), dtype=np.uint8)

            writer.write(frame)

        writer.release()
        videos.append(path)
        logger.info("Generated synthetic video: %s (%d sec)", path.name, duration_sec)

    return videos


if __name__ == "__main__":
    main()
