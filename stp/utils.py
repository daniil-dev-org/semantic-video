"""Shared utilities  -  subprocess wrappers, hashing, logging, ffmpeg/ffprobe discovery."""

from __future__ import annotations

import hashlib
import logging
import shutil
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger("stp")


def setup_logging(level: int = logging.INFO) -> None:
    """Configure console logging."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("[%(levelname)s] %(name)s - %(message)s"))
    root = logging.getLogger("stp")
    root.setLevel(level)
    if not root.handlers:
        root.addHandler(handler)


# ── FFmpeg / FFprobe discovery ──

def find_ffmpeg() -> Path:
    """Locate ffmpeg binary.  Raises RuntimeError if not found."""
    path = shutil.which("ffmpeg")
    if path:
        return Path(path)
    for candidate in [
        Path(r"C:\ffmpeg\bin\ffmpeg.exe"),
        Path(r"C:\Program Files\ffmpeg\bin\ffmpeg.exe"),
        Path(__file__).parent.parent / "ffmpeg" / "ffmpeg.exe",
    ]:
        if candidate.exists():
            return candidate
    try:
        import imageio_ffmpeg
        return Path(imageio_ffmpeg.get_ffmpeg_exe())
    except ImportError:
        pass
    raise RuntimeError(
        "ffmpeg not found.  Install FFmpeg and add it to PATH.  "
        "See README.md for instructions."
    )


def find_ffprobe() -> Path:
    """Locate ffprobe binary.  Raises RuntimeError if not found."""
    path = shutil.which("ffprobe")
    if path:
        return Path(path)
    for candidate in [
        Path(r"C:\ffmpeg\bin\ffprobe.exe"),
        Path(r"C:\Program Files\ffmpeg\bin\ffprobe.exe"),
        Path(__file__).parent.parent / "ffmpeg" / "ffprobe.exe",
    ]:
        if candidate.exists():
            return candidate
    try:
        import imageio_ffmpeg
        ffmpeg_path = Path(imageio_ffmpeg.get_ffmpeg_exe())
        probe = ffmpeg_path.parent / ffmpeg_path.name.replace("ffmpeg", "ffprobe")
        if probe.exists():
            return probe
        return ffmpeg_path  # fallback  -  probe.py handles this
    except ImportError:
        pass
    raise RuntimeError(
        "ffprobe not found.  Install FFmpeg and add it to PATH.  "
        "See README.md for instructions."
    )


# ── Subprocess ──

def run_subprocess(
    cmd: list[str],
    desc: str = "command",
    capture: bool = True,
) -> subprocess.CompletedProcess:
    """Run a subprocess with error handling."""
    logger.debug("Running %s: %s", desc, " ".join(str(c) for c in cmd))
    try:
        result = subprocess.run(
            [str(c) for c in cmd],
            capture_output=capture,
            text=True,
            check=True,
        )
        return result
    except subprocess.CalledProcessError as e:
        logger.error(
            "%s failed (exit %d):\nstdout: %s\nstderr: %s",
            desc, e.returncode,
            (e.stdout or "")[:500], (e.stderr or "")[:500],
        )
        raise RuntimeError(f"{desc} failed: {(e.stderr or '')[:500]}") from e
    except FileNotFoundError as e:
        raise RuntimeError(f"{desc}: executable not found  -  {e}") from e


# ── Hashing ──

def sha256_file(path: Path) -> str:
    """Compute SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


# ── Misc ──

def file_size_mb(path: Path) -> float:
    """Return file size in megabytes."""
    return path.stat().st_size / (1024 * 1024)


def ensure_dir(path: Path) -> Path:
    """Create directory if it doesn't exist and return it."""
    path.mkdir(parents=True, exist_ok=True)
    return path
