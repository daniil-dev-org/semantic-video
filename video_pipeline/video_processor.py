"""
video_processor.py — Sequential video variation generator for A/B testing.

Uses ffmpeg-python to create 4 variations of a source video:
  1. Speedup (5%)
  2. Horizontal mirror
  3. LUT color grading
  4. Light noise injection

Designed for low-resource environments: all processing is sequential,
and FFmpeg is hard-limited to 2 threads per invocation.

Usage:
    python video_pipeline/video_processor.py
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

import ffmpeg

# ── Add project root to sys.path so we can import stp utilities ──
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from stp.ffmpeg_tools import probe_video  # noqa: E402
from stp.utils import find_ffmpeg         # noqa: E402

logger = logging.getLogger("video_pipeline")

# ── Constants ──
THREAD_LIMIT = 2


class VideoVariator:
    """
    Creates video variations from a single source file.

    All operations are sequential and thread-limited for low-resource servers.
    Audio presence is auto-detected; audio filters are skipped when absent.
    """

    def __init__(self, input_path: Path | str, output_dir: Path | str) -> None:
        self.input_path = Path(input_path).resolve()
        self.output_dir = Path(output_dir).resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)

        if not self.input_path.exists():
            raise FileNotFoundError(f"Input video not found: {self.input_path}")

        # Discover FFmpeg binary via project utilities
        self._ffmpeg_bin = str(find_ffmpeg())
        logger.info("FFmpeg binary: %s", self._ffmpeg_bin)

        # Probe video to determine audio presence
        self._meta = probe_video(self.input_path)
        self._has_audio = self._meta.has_audio
        logger.info(
            "Input: %s  (%dx%d @ %.1f fps, %d ms, audio=%s)",
            self.input_path.name,
            self._meta.width, self._meta.height,
            self._meta.fps, self._meta.duration_ms,
            self._has_audio,
        )

        self._stem = self.input_path.stem

    def _output_path(self, suffix: str) -> Path:
        return self.output_dir / f"{self._stem}_{suffix}.mp4"

    def _run_ffmpeg(self, stream, output_path: Path, description: str) -> Path:
        """Execute an ffmpeg-python stream with error handling and timing."""
        t0 = time.perf_counter()
        logger.info("[START] %s -> %s", description, output_path.name)

        try:
            stream.output(
                str(output_path),
                threads=THREAD_LIMIT,
                **{"y": None},  # overwrite
            ).run(cmd=self._ffmpeg_bin, quiet=True)
        except ffmpeg.Error as e:
            stderr_text = ""
            if e.stderr:
                stderr_text = e.stderr.decode("utf-8", errors="replace")[-500:]
            logger.error("[FAIL] %s: %s\n%s", description, e, stderr_text)
            raise

        elapsed = time.perf_counter() - t0
        size_mb = output_path.stat().st_size / (1024 * 1024) if output_path.exists() else 0
        logger.info("[DONE] %s  (%.1f s, %.2f MB)", description, elapsed, size_mb)
        return output_path

    # ── Variation methods ──

    def generate_speedup(self) -> Path:
        """
        Speed up video by 5%.

        Video: setpts=PTS/1.05 (≈ 0.95238*PTS)
        Audio: atempo=1.05
        """
        output_path = self._output_path("speedup")

        inp = ffmpeg.input(str(self.input_path))
        video = inp.video.filter("setpts", "PTS/1.05")

        if self._has_audio:
            audio = inp.audio.filter("atempo", 1.05)
            stream = ffmpeg.concat(video, audio, v=1, a=1)
        else:
            stream = video

        return self._run_ffmpeg(stream, output_path, "Speedup 5%")

    def generate_mirrored(self) -> Path:
        """Horizontal flip (mirror) of the video."""
        output_path = self._output_path("mirrored")

        inp = ffmpeg.input(str(self.input_path))
        video = inp.video.filter("hflip")

        if self._has_audio:
            stream = ffmpeg.output(video, inp.audio, str(output_path),
                                   threads=THREAD_LIMIT, **{"y": None})
            # Use direct .run() since we already built the full output node
            t0 = time.perf_counter()
            logger.info("[START] Mirror (hflip) → %s", output_path.name)
            try:
                stream.run(cmd=self._ffmpeg_bin, quiet=True)
            except ffmpeg.Error as e:
                stderr_text = ""
                if e.stderr:
                    stderr_text = e.stderr.decode("utf-8", errors="replace")[-500:]
                logger.error("[FAIL] Mirror: %s\n%s", e, stderr_text)
                raise
            elapsed = time.perf_counter() - t0
            size_mb = output_path.stat().st_size / (1024 * 1024) if output_path.exists() else 0
            logger.info("[DONE] Mirror (hflip)  (%.1f s, %.2f MB)", elapsed, size_mb)
            return output_path
        else:
            return self._run_ffmpeg(video, output_path, "Mirror (hflip)")

    def generate_color_graded(self, lut_path: Path | str) -> Path:
        """
        Apply a 3D LUT file for cinematic color grading.

        Uses the lut3d filter.
        """
        lut_path = Path(lut_path).resolve()
        if not lut_path.exists():
            raise FileNotFoundError(f"LUT file not found: {lut_path}")

        output_path = self._output_path("color_graded")

        inp = ffmpeg.input(str(self.input_path))
        video = inp.video.filter("lut3d", file=str(lut_path))

        if self._has_audio:
            stream = ffmpeg.output(video, inp.audio, str(output_path),
                                   threads=THREAD_LIMIT, **{"y": None})
            t0 = time.perf_counter()
            logger.info("[START] Color grading (LUT: %s) → %s", lut_path.name, output_path.name)
            try:
                stream.run(cmd=self._ffmpeg_bin, quiet=True)
            except ffmpeg.Error as e:
                stderr_text = ""
                if e.stderr:
                    stderr_text = e.stderr.decode("utf-8", errors="replace")[-500:]
                logger.error("[FAIL] Color grading: %s\n%s", e, stderr_text)
                raise
            elapsed = time.perf_counter() - t0
            size_mb = output_path.stat().st_size / (1024 * 1024) if output_path.exists() else 0
            logger.info("[DONE] Color grading  (%.1f s, %.2f MB)", elapsed, size_mb)
            return output_path
        else:
            return self._run_ffmpeg(video, output_path, f"Color grading (LUT: {lut_path.name})")

    def generate_noisy(self) -> Path:
        """
        Add light grain/noise to defeat hash-based duplicate filters.

        Uses the noise filter with low intensity temporal+uniform noise.
        """
        output_path = self._output_path("noisy")

        inp = ffmpeg.input(str(self.input_path))
        video = inp.video.filter("noise", alls=5, allf="t+u")

        if self._has_audio:
            stream = ffmpeg.output(video, inp.audio, str(output_path),
                                   threads=THREAD_LIMIT, **{"y": None})
            t0 = time.perf_counter()
            logger.info("[START] Noise injection → %s", output_path.name)
            try:
                stream.run(cmd=self._ffmpeg_bin, quiet=True)
            except ffmpeg.Error as e:
                stderr_text = ""
                if e.stderr:
                    stderr_text = e.stderr.decode("utf-8", errors="replace")[-500:]
                logger.error("[FAIL] Noise: %s\n%s", e, stderr_text)
                raise
            elapsed = time.perf_counter() - t0
            size_mb = output_path.stat().st_size / (1024 * 1024) if output_path.exists() else 0
            logger.info("[DONE] Noise injection  (%.1f s, %.2f MB)", elapsed, size_mb)
            return output_path
        else:
            return self._run_ffmpeg(video, output_path, "Noise injection")

    def run_all(self, lut_path: Path | str) -> list[Path]:
        """
        Run all variation generators sequentially.

        Returns a list of paths to successfully created files.
        """
        results: list[Path] = []
        total_t0 = time.perf_counter()
        logger.info("=" * 60)
        logger.info("Starting full variation pipeline for: %s", self.input_path.name)
        logger.info("=" * 60)

        methods = [
            ("Speedup", lambda: self.generate_speedup()),
            ("Mirror", lambda: self.generate_mirrored()),
            ("Color Grading", lambda: self.generate_color_graded(lut_path)),
            ("Noise", lambda: self.generate_noisy()),
        ]

        for name, method in methods:
            try:
                path = method()
                results.append(path)
            except Exception:
                logger.exception("Variation '%s' failed — skipping", name)

        total_elapsed = time.perf_counter() - total_t0
        logger.info("=" * 60)
        logger.info(
            "Pipeline complete: %d / %d variations in %.1f s",
            len(results), len(methods), total_elapsed,
        )
        for p in results:
            logger.info("  [OK] %s  (%.2f MB)", p.name, p.stat().st_size / (1024 * 1024))
        logger.info("=" * 60)

        return results


# ── CLI entry point ──

def _setup_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("[%(levelname)s] %(name)s — %(message)s"))
    root = logging.getLogger("video_pipeline")
    root.setLevel(logging.INFO)
    if not root.handlers:
        root.addHandler(handler)
    # Also enable stp loggers for probe output
    stp_root = logging.getLogger("stp")
    stp_root.setLevel(logging.INFO)
    if not stp_root.handlers:
        stp_root.addHandler(handler)


def main() -> None:
    _setup_logging()

    script_dir = Path(__file__).resolve().parent
    input_video = script_dir / "input" / "test_video.mp4"
    output_dir = script_dir / "output"
    lut_file = script_dir / "assets" / "cinematic.cube"

    if not input_video.exists():
        logger.error("Test video not found: %s", input_video)
        logger.error("Run setup_sandbox.py first!")
        raise SystemExit(1)

    if not lut_file.exists():
        logger.error("LUT file not found: %s", lut_file)
        logger.error("Run setup_sandbox.py first!")
        raise SystemExit(1)

    variator = VideoVariator(input_video, output_dir)
    created = variator.run_all(lut_file)

    if not created:
        logger.error("No variations were created successfully.")
        raise SystemExit(1)

    print(f"\n  All done! {len(created)} variations saved to: {output_dir}\n")


if __name__ == "__main__":
    main()
