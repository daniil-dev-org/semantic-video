"""FFmpeg / FFprobe tools  -  probing, encoding helpers."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from pydantic import BaseModel

from .utils import find_ffprobe, run_subprocess

logger = logging.getLogger("stp.ffmpeg_tools")


class VideoMeta(BaseModel):
    """Metadata extracted from a video file via ffprobe / OpenCV."""
    duration_ms: int = 0
    width: int = 0
    height: int = 0
    fps: float = 0.0
    has_audio: bool = False
    codec: str = "unknown"
    file_size_bytes: int = 0


def probe_video(path: Path) -> VideoMeta:
    """Extract video metadata.  Tries ffprobe first, falls back to OpenCV."""
    if not path.exists():
        raise FileNotFoundError(f"Input video not found: {path}")

    try:
        return _probe_ffprobe(path)
    except Exception as e:
        logger.warning("ffprobe failed, falling back to OpenCV: %s", e)

    return _probe_opencv(path)


def _probe_ffprobe(path: Path) -> VideoMeta:
    ffprobe = find_ffprobe()
    cmd = [
        ffprobe, "-v", "quiet",
        "-print_format", "json",
        "-show_format", "-show_streams",
        str(path),
    ]
    result = run_subprocess(cmd, desc="ffprobe")
    data = json.loads(result.stdout)

    video_stream = None
    has_audio = False
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video" and video_stream is None:
            video_stream = stream
        if stream.get("codec_type") == "audio":
            has_audio = True

    if video_stream is None:
        raise RuntimeError(f"No video stream found in {path}")

    width = int(video_stream["width"])
    height = int(video_stream["height"])
    codec = video_stream.get("codec_name", "unknown")

    fps_str = video_stream.get("r_frame_rate", "24/1")
    if "/" in fps_str:
        num, den = fps_str.split("/")
        fps = float(num) / float(den) if float(den) != 0 else 24.0
    else:
        fps = float(fps_str)

    duration_sec = float(data.get("format", {}).get("duration", 0))
    if duration_sec == 0:
        duration_sec = float(video_stream.get("duration", 0))
    duration_ms = int(duration_sec * 1000)

    file_size = int(data.get("format", {}).get("size", 0))

    meta = VideoMeta(
        duration_ms=duration_ms, width=width, height=height,
        fps=round(fps, 3), has_audio=has_audio,
        codec=codec, file_size_bytes=file_size,
    )
    logger.info(
        "Probed (ffprobe) %s: %dx%d @ %.2f fps, %d ms, audio=%s",
        path.name, meta.width, meta.height, meta.fps,
        meta.duration_ms, meta.has_audio,
    )
    return meta


def _probe_opencv(path: Path) -> VideoMeta:
    import cv2

    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video with OpenCV: {path}")

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration_ms = int((frame_count / fps) * 1000) if fps > 0 else 0
    cap.release()

    file_size = path.stat().st_size

    meta = VideoMeta(
        duration_ms=duration_ms, width=width, height=height,
        fps=round(fps, 3), has_audio=True, codec="unknown",
        file_size_bytes=file_size,
    )
    logger.info(
        "Probed (OpenCV) %s: %dx%d @ %.2f fps, %d ms",
        path.name, meta.width, meta.height, meta.fps, meta.duration_ms,
    )
    return meta
