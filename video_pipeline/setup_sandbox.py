"""
setup_sandbox.py — Prepare the video_pipeline sandbox environment.

Creates directory structure, generates a cinematic 3D LUT (.cube) file,
and copies a sample video from the main project for testing.

Usage:
    python video_pipeline/setup_sandbox.py
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent

INPUT_DIR = SCRIPT_DIR / "input"
OUTPUT_DIR = SCRIPT_DIR / "output"
ASSETS_DIR = SCRIPT_DIR / "assets"

SAMPLE_VIDEO = PROJECT_ROOT / "samples" / "input" / "videos" / "post_001.mp4"
TARGET_VIDEO = INPUT_DIR / "test_video.mp4"
LUT_PATH = ASSETS_DIR / "cinematic.cube"

LUT_SIZE = 17  # 17x17x17 grid — standard quality for color grading


def _generate_cinematic_lut(path: Path, size: int = LUT_SIZE) -> None:
    """
    Generate a warm cinematic (teal-and-orange) 3D LUT in Adobe .cube format.

    The LUT applies:
      - Warm lift to highlights (slight orange push)
      - Teal shift in shadows
      - Gentle S-curve contrast boost
      - Slight desaturation of greens
    """
    import math

    lines: list[str] = [
        "# Cinematic Warm LUT — auto-generated for A/B testing pipeline",
        f'TITLE "Cinematic Warm"',
        f"LUT_3D_SIZE {size}",
        "",
    ]

    for b_idx in range(size):
        for g_idx in range(size):
            for r_idx in range(size):
                r = r_idx / (size - 1)
                g = g_idx / (size - 1)
                b = b_idx / (size - 1)

                # --- S-curve contrast (smooth sigmoid) ---
                def s_curve(x: float) -> float:
                    return 1.0 / (1.0 + math.exp(-8 * (x - 0.5)))

                r = s_curve(r)
                g = s_curve(g)
                b = s_curve(b)

                # --- Luminance for shadow/highlight split ---
                lum = 0.2126 * r + 0.7152 * g + 0.0722 * b

                # --- Teal shadows: push blue up, red down in darks ---
                shadow_strength = max(0.0, 1.0 - lum * 2.5)
                r -= 0.04 * shadow_strength
                b += 0.06 * shadow_strength

                # --- Warm highlights: push red/yellow up in brights ---
                highlight_strength = max(0.0, lum * 2.0 - 1.0)
                r += 0.05 * highlight_strength
                g += 0.02 * highlight_strength
                b -= 0.04 * highlight_strength

                # --- Slight green desaturation ---
                if g > r and g > b:
                    excess = (g - (r + b) / 2) * 0.15
                    g -= excess

                # Clamp to [0, 1]
                r = max(0.0, min(1.0, r))
                g = max(0.0, min(1.0, g))
                b = max(0.0, min(1.0, b))

                lines.append(f"{r:.6f} {g:.6f} {b:.6f}")

    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    print("=" * 60)
    print("  Video Pipeline — Sandbox Setup")
    print("=" * 60)

    # 1. Create directories
    for d in (INPUT_DIR, OUTPUT_DIR, ASSETS_DIR):
        d.mkdir(parents=True, exist_ok=True)
        print(f"  [OK] Directory: {d.relative_to(PROJECT_ROOT)}")

    # 2. Generate LUT
    _generate_cinematic_lut(LUT_PATH)
    lut_kb = LUT_PATH.stat().st_size / 1024
    print(f"  [OK] Generated LUT: {LUT_PATH.name}  ({lut_kb:.1f} KB, {LUT_SIZE}x{LUT_SIZE}x{LUT_SIZE} grid)")

    # 3. Copy sample video
    if TARGET_VIDEO.exists():
        print(f"  [OK] Test video already present: {TARGET_VIDEO.name}")
    elif SAMPLE_VIDEO.exists():
        shutil.copy2(SAMPLE_VIDEO, TARGET_VIDEO)
        size_mb = TARGET_VIDEO.stat().st_size / (1024 * 1024)
        print(f"  [OK] Copied test video: {SAMPLE_VIDEO.name} -> {TARGET_VIDEO.name}  ({size_mb:.2f} MB)")
    else:
        print(f"  [!!] Sample video not found: {SAMPLE_VIDEO}")
        print(f"       Please place a test video manually at: {TARGET_VIDEO}")

    print()
    print("  Sandbox ready!  Run video_processor.py to generate variations.")
    print("=" * 60)


if __name__ == "__main__":
    main()
