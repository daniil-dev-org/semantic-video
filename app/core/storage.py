import hashlib
import shutil
from pathlib import Path
from .config import STORAGE_DIR, UPLOADS_DIR, JOBS_DIR, OUTPUTS_DIR
from .logging import setup_logger

logger = setup_logger("app.core.storage")

def init_storage() -> None:
    """Initialize necessary local storage directories."""
    for directory in [STORAGE_DIR, UPLOADS_DIR, JOBS_DIR, OUTPUTS_DIR]:
        directory.mkdir(parents=True, exist_ok=True)
        logger.info(f"Initialized directory: {directory.relative_to(directory.parent.parent) if directory.parent else directory}")

def calculate_sha256(path: Path) -> str:
    """Compute the SHA-256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(8192):
            sha256.update(chunk)
    return sha256.hexdigest()

def get_file_size_mb(path: Path) -> float:
    """Get file size in megabytes."""
    if not path.exists():
        return 0.0
    return round(path.stat().st_size / (1024 * 1024), 2)

def cleanup_path(path: Path) -> None:
    """Safely delete a file or directory tree."""
    if not path.exists():
        return
    try:
        if path.is_file():
            path.unlink()
        elif path.is_dir():
            shutil.rmtree(path)
        logger.info(f"Cleaned up path: {path}")
    except Exception as e:
        logger.error(f"Failed to cleanup path {path}: {e}")
