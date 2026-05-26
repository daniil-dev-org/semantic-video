"""Proxy encoder  -  creates 144p analysis proxy via FFmpeg."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from .config import ProxyConfig
from .ffmpeg_tools import VideoMeta, probe_video
from .utils import ensure_dir, file_size_mb, find_ffmpeg, run_subprocess, sha256_file

logger = logging.getLogger("stp.proxy_encoder")


def compute_proxy_width(source_width: int, source_height: int, target_height: int) -> int:
    """Compute target width preserving aspect ratio (divisible by 2)."""
    if source_height == 0:
        return target_height  # square fallback
    ratio = target_height / source_height
    w = int(source_width * ratio)
    return w if w % 2 == 0 else w + 1


def encode_proxy(
    input_path: Path,
    output_dir: Path,
    cfg: ProxyConfig,
    meta: VideoMeta | None = None,
) -> tuple[Path, dict]:
    """
    Encode input video to a 144p proxy for feature extraction.

    Returns (proxy_path, manifest_dict).
    """
    ensure_dir(output_dir)
    ffmpeg = find_ffmpeg()

    if meta is None:
        meta = probe_video(input_path)

    proxy_width = compute_proxy_width(meta.width, meta.height, cfg.height)
    proxy_path = output_dir / "proxy_144p.mp4"

    t0 = time.perf_counter()

    cmd = [
        ffmpeg, "-y",
        "-i", str(input_path),
        "-c:v", cfg.codec,
        "-preset", cfg.preset,
        "-crf", str(cfg.crf),
        "-r", str(cfg.fps),
        "-vf", f"scale={proxy_width}:{cfg.height}",
        "-pix_fmt", "yuv420p",
    ]

    if not cfg.keep_audio:
        cmd.append("-an")

    cmd.append(str(proxy_path))

    logger.info(
        "Encoding proxy: %dx%d -> %dx%d  CRF=%d  preset=%s  fps=%d",
        meta.width, meta.height, proxy_width, cfg.height,
        cfg.crf, cfg.preset, cfg.fps,
    )
    run_subprocess(cmd, desc="ffmpeg proxy encode")

    elapsed = time.perf_counter() - t0

    proxy_mb = file_size_mb(proxy_path) if proxy_path.exists() else 0
    original_mb = meta.file_size_bytes / (1024 * 1024) if meta.file_size_bytes else 0

    manifest = {
        "stp_version": "0.1",
        "source": {
            "name": input_path.name,
            "width": meta.width,
            "height": meta.height,
            "fps": meta.fps,
            "duration_ms": meta.duration_ms,
            "size_mb": round(original_mb, 3),
            "sha256": sha256_file(input_path),
        },
        "proxy": {
            "filename": "proxy_144p.mp4",
            "width": proxy_width,
            "height": cfg.height,
            "fps": cfg.fps,
            "codec": cfg.codec,
            "crf": cfg.crf,
            "preset": cfg.preset,
            "size_mb": round(proxy_mb, 3),
            "sha256": sha256_file(proxy_path) if proxy_path.exists() else "",
            "purpose": "feature_extraction",
        },
        "encoding_time_sec": round(elapsed, 2),
        "compression_ratio": round(original_mb / proxy_mb, 1) if proxy_mb > 0 else 0,
    }

    # Save manifest
    manifest_path = output_dir / "proxy_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    logger.info(
        "Proxy encoded: %s  %.2f MB -> %.2f MB  (%.1fx)  %.1fs",
        proxy_path.name, original_mb, proxy_mb,
        manifest["compression_ratio"], elapsed,
    )
    return proxy_path, manifest
