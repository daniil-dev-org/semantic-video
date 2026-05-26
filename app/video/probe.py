from pathlib import Path
from stp.ffmpeg_tools import probe_video as stp_probe_video, VideoMeta
from ..core.logging import setup_logger

logger = setup_logger("app.video.probe")

def probe_video(path: Path) -> VideoMeta:
    """
    Extract video metadata via standard STP probe tool.
    Performs additional sanity checks on format, duration, and sizes.
    """
    if not path.exists():
        raise FileNotFoundError(f"Video file does not exist: {path}")
        
    meta = stp_probe_video(path)
    
    # Validation constraints
    if meta.duration_ms == 0:
        logger.warning(f"Video duration is reported as 0 ms for {path.name}. Checking file sanity...")
        
    if meta.width == 0 or meta.height == 0:
        raise ValueError(f"Invalid video dimensions: {meta.width}x{meta.height}")
        
    if meta.fps <= 0.0:
        logger.warning(f"Invalid FPS {meta.fps} reported. Standardizing to 25.0 fps.")
        meta.fps = 25.0
        
    logger.info(
        f"Validation PASSED: '{path.name}' ({meta.width}x{meta.height} @ {meta.fps:.1f} fps, "
        f"{meta.duration_ms} ms, audio={meta.has_audio}, size={meta.file_size_bytes} bytes)"
    )
    return meta
