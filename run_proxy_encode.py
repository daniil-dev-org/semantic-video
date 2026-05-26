"""
run_proxy_encode.py  -  Encode source video into 144p analysis proxy.

Usage:
  python run_proxy_encode.py --input samples/input/videos/post_001.mp4 --output samples/output/post_001
  python run_proxy_encode.py --input samples/input/videos/post_001.mp4 --output samples/output/post_001 --height 144 --fps 5
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from stp.config import load_config
from stp.ffmpeg_tools import probe_video
from stp.proxy_encoder import encode_proxy
from stp.utils import setup_logging

logger = logging.getLogger("stp.run_proxy_encode")


def main() -> None:
    parser = argparse.ArgumentParser(description="STP  -  Encode 144p analysis proxy")
    parser.add_argument("--input", "-i", type=Path, required=True,
                        help="Path to source video file")
    parser.add_argument("--output", "-o", type=Path, required=True,
                        help="Output directory for proxy bundle")
    parser.add_argument("--config", "-c", type=Path, default=None,
                        help="Path to config.yaml")
    parser.add_argument("--height", type=int, default=None,
                        help="Proxy height in pixels (default: from config)")
    parser.add_argument("--fps", type=int, default=None,
                        help="Proxy FPS (default: from config)")
    args = parser.parse_args()

    setup_logging()
    cfg = load_config(args.config)

    # CLI overrides
    if args.height:
        cfg.proxy.height = args.height
    if args.fps:
        cfg.proxy.fps = args.fps

    input_path = args.input.resolve()
    if not input_path.exists():
        logger.error("Input file not found: %s", input_path)
        raise SystemExit(1)

    output_dir = args.output.resolve()

    logger.info("=" * 60)
    logger.info("STP Proxy Encoder")
    logger.info("  Input:  %s", input_path)
    logger.info("  Output: %s", output_dir)
    logger.info("  Height: %d  FPS: %d  CRF: %d", cfg.proxy.height, cfg.proxy.fps, cfg.proxy.crf)
    logger.info("=" * 60)

    meta = probe_video(input_path)
    proxy_path, manifest = encode_proxy(input_path, output_dir, cfg.proxy, meta)

    logger.info("=" * 60)
    logger.info("[OK] Proxy created: %s", proxy_path)
    logger.info("  Source: %dx%d @ %.1f fps", meta.width, meta.height, meta.fps)
    logger.info("  Proxy:  %dx%d @ %d fps", manifest["proxy"]["width"], manifest["proxy"]["height"], manifest["proxy"]["fps"])
    logger.info("  Size:   %.3f MB -> %.3f MB (%.1fx compression)",
                manifest["source"]["size_mb"], manifest["proxy"]["size_mb"],
                manifest["compression_ratio"])
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
