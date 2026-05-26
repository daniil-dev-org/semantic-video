"""
run_extract_features.py  -  Extract rich video features + build STP-0.1 sidecar.

Usage:
  python run_extract_features.py --input samples/input/videos/post_001.mp4 --output samples/output/post_001
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path

from stp.config import load_config
from stp.ffmpeg_tools import probe_video
from stp.proxy_encoder import encode_proxy
from stp.video_features import extract_features, select_keyframes, save_keyframes
from stp.sidecar_schema import build_sidecar, save_sidecar
from stp.utils import setup_logging, sha256_file, file_size_mb

logger = logging.getLogger("stp.run_extract_features")


def main() -> None:
    parser = argparse.ArgumentParser(description="STP  -  Extract video features + build sidecar")
    parser.add_argument("--input", "-i", type=Path, required=True,
                        help="Path to source video file")
    parser.add_argument("--output", "-o", type=Path, required=True,
                        help="Output directory")
    parser.add_argument("--config", "-c", type=Path, default=None,
                        help="Path to config.yaml")
    parser.add_argument("--skip-proxy", action="store_true",
                        help="Skip proxy encoding (use existing proxy)")
    args = parser.parse_args()

    setup_logging()
    cfg = load_config(args.config)

    input_path = args.input.resolve()
    if not input_path.exists():
        logger.error("Input file not found: %s", input_path)
        raise SystemExit(1)

    output_dir = args.output.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    t_start = time.perf_counter()
    asset_id = input_path.stem

    # ── Step 1: Probe ──
    logger.info("=" * 60)
    logger.info("Step 1/5  -  Probing source video")
    meta = probe_video(input_path)

    # ── Step 2: Encode proxy ──
    proxy_path = output_dir / "proxy_144p.mp4"
    if not args.skip_proxy or not proxy_path.exists():
        logger.info("=" * 60)
        logger.info("Step 2/5  -  Encoding 144p proxy")
        proxy_path, proxy_manifest = encode_proxy(input_path, output_dir, cfg.proxy, meta)
    else:
        logger.info("Step 2/5  -  Skipping proxy (exists)")

    # ── Step 3: Extract features from source ──
    logger.info("=" * 60)
    logger.info("Step 3/5  -  Extracting video features")
    metrics = extract_features(input_path, cfg.video_features, meta.fps, meta.duration_ms)

    # ── Step 4: Select & save keyframes ──
    logger.info("=" * 60)
    logger.info("Step 4/5  -  Selecting keyframes")
    kf_dir = output_dir / "keyframes"
    kf_indices = select_keyframes(metrics, cfg.video_features.keyframe_count)
    kf_files = save_keyframes(input_path, metrics, kf_indices, kf_dir, meta.fps)

    # ── Step 5: Build sidecar ──
    logger.info("=" * 60)
    logger.info("Step 5/5  -  Building STP-0.1 sidecar")
    sidecar_doc = build_sidecar(
        asset_id=asset_id,
        source_name=input_path.name,
        meta=meta,
        metrics=metrics,
        proxy_cfg=cfg.proxy,
        feat_cfg=cfg.video_features,
        keyframe_files=kf_files,
    )

    # Integrity hashes
    sidecar_doc.integrity.source_sha256 = sha256_file(input_path)
    if proxy_path.exists():
        sidecar_doc.integrity.proxy_sha256 = sha256_file(proxy_path)

    sidecar_path = output_dir / "video_metrics_sidecar.json"
    save_sidecar(sidecar_doc, sidecar_path)

    # Update sidecar hash (self-referential)
    sidecar_doc.integrity.sidecar_sha256 = sha256_file(sidecar_path)
    save_sidecar(sidecar_doc, sidecar_path)

    # ── Metrics summary ──
    elapsed = time.perf_counter() - t_start

    gf = sidecar_doc.video_features.global_features
    summary_metrics = {
        "asset_id": asset_id,
        "source_name": input_path.name,
        "duration_ms": meta.duration_ms,
        "source_resolution": f"{meta.width}x{meta.height}",
        "sampled_frames": gf.sampled_frames,
        "cut_count": gf.cut_count,
        "avg_brightness": gf.avg_brightness,
        "avg_motion_score": gf.avg_motion_score,
        "face_presence_ratio": gf.face_presence_ratio,
        "keyframes_saved": len(kf_files),
        "processing_time_sec": round(elapsed, 2),
        "proxy_size_mb": round(file_size_mb(proxy_path), 3) if proxy_path.exists() else 0,
        "sidecar_size_kb": round(sidecar_path.stat().st_size / 1024, 1),
    }

    metrics_path = output_dir / "metrics.json"
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(summary_metrics, f, indent=2)

    logger.info("=" * 60)
    logger.info("[OK] Features extracted: %s", output_dir)
    logger.info("  Sampled frames:   %d", gf.sampled_frames)
    logger.info("  Scene cuts:       %d (%.2f/sec)", gf.cut_count, gf.cuts_per_second)
    logger.info("  Avg brightness:   %.3f", gf.avg_brightness)
    logger.info("  Avg motion:       %.3f", gf.avg_motion_score)
    logger.info("  Face presence:    %.1f%%", gf.face_presence_ratio * 100)
    logger.info("  Keyframes:        %d", len(kf_files))
    logger.info("  Sidecar:          %.1f KB", sidecar_path.stat().st_size / 1024)
    logger.info("  Time:             %.1f sec", elapsed)
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
