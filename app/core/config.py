import os
from pathlib import Path

# Base Paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent
STORAGE_DIR = BASE_DIR / "storage"
PROFILES_DIR = BASE_DIR / "profiles"

# Sub-storage paths
UPLOADS_DIR = STORAGE_DIR / "uploads"
JOBS_DIR = STORAGE_DIR / "jobs"
OUTPUTS_DIR = STORAGE_DIR / "outputs"

# SQLite DB Path
DB_PATH = STORAGE_DIR / "jobs.db"

# Limits & Concurrency
THREAD_LIMIT = int(os.environ.get("THREAD_LIMIT", 2))
MAX_UPLOAD_SIZE_MB = int(os.environ.get("MAX_UPLOAD_SIZE_MB", 500))
JOB_TIMEOUT_SEC = int(os.environ.get("JOB_TIMEOUT_SEC", 600))

# Redis (optional — empty string disables Redis listener, uses SQLite-only mode)
REDIS_ADDR = os.environ.get("REDIS_ADDR", "")
REDIS_STREAM_PROCESS = os.environ.get("REDIS_STREAM_PROCESS", "video:process")
REDIS_CONSUMER_GROUP = os.environ.get("REDIS_CONSUMER_GROUP", "semantic-workers")
REDIS_CONSUMER_NAME = os.environ.get("REDIS_CONSUMER_NAME", "semantic-worker-1")
