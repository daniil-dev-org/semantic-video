import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List

from ..core.config import DB_PATH
from ..core.logging import setup_logger
from .models import JobModel, JobOutputModel

logger = setup_logger("app.db.repository")

@contextmanager
def db_connection():
    """Provides a thread-safe connection context manager for SQLite with WAL mode."""
    conn = sqlite3.connect(str(DB_PATH), timeout=30.0)
    conn.row_factory = sqlite3.Row
    try:
        # Enable Write-Ahead Logging (WAL) and foreign keys support
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

class SQLRepository:
    """Encapsulates raw SQLite CRUD operations for jobs and job outputs."""

    @staticmethod
    def init_db() -> None:
        """Create tables if they do not exist."""
        with db_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    input_path TEXT NOT NULL,
                    profile TEXT NOT NULL,
                    variants INTEGER NOT NULL,
                    extract_features BOOLEAN NOT NULL,
                    generate_proxy BOOLEAN NOT NULL,
                    status TEXT NOT NULL,
                    progress REAL NOT NULL DEFAULT 0.0,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    error_message TEXT
                );
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS job_outputs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    type TEXT NOT NULL,
                    path TEXT NOT NULL,
                    size_mb REAL NOT NULL,
                    sha256 TEXT NOT NULL,
                    duration_ms INTEGER,
                    FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
                );
            """)
        logger.info("Database tables initialized successfully.")

    @staticmethod
    def create_job(
        job_id: str,
        input_path: str,
        profile: str,
        variants: int,
        extract_features: bool,
        generate_proxy: bool
    ) -> JobModel:
        created_at = datetime.now(timezone.utc).isoformat()
        with db_connection() as conn:
            conn.execute(
                """
                INSERT INTO jobs (id, input_path, profile, variants, extract_features, generate_proxy, status, progress, created_at)
                VALUES (?, ?, ?, ?, ?, ?, 'QUEUED', 0.0, ?)
                """,
                (job_id, input_path, profile, variants, int(extract_features), int(generate_proxy), created_at)
            )
        return SQLRepository.get_job(job_id)

    @staticmethod
    def get_job(job_id: str) -> Optional[JobModel]:
        with db_connection() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if not row:
                return None
            return JobModel(
                id=row["id"],
                input_path=row["input_path"],
                profile=row["profile"],
                variants=row["variants"],
                extract_features=bool(row["extract_features"]),
                generate_proxy=bool(row["generate_proxy"]),
                status=row["status"],
                progress=row["progress"],
                created_at=row["created_at"],
                started_at=row["started_at"],
                finished_at=row["finished_at"],
                error_message=row["error_message"]
            )

    @staticmethod
    def update_job_status(
        job_id: str,
        status: str,
        error_message: Optional[str] = None,
        started_at: Optional[str] = None,
        finished_at: Optional[str] = None
    ) -> None:
        with db_connection() as conn:
            if started_at:
                conn.execute("UPDATE jobs SET status = ?, started_at = ? WHERE id = ?", (status, started_at, job_id))
            elif finished_at:
                conn.execute(
                    "UPDATE jobs SET status = ?, finished_at = ?, error_message = ? WHERE id = ?",
                    (status, finished_at, error_message, job_id)
                )
            else:
                conn.execute(
                    "UPDATE jobs SET status = ?, error_message = ? WHERE id = ?",
                    (status, error_message, job_id)
                )
        logger.info(f"Job {job_id} status updated to {status}")

    @staticmethod
    def update_job_progress(job_id: str, progress: float) -> None:
        with db_connection() as conn:
            conn.execute("UPDATE jobs SET progress = ? WHERE id = ?", (round(progress, 2), job_id))

    @staticmethod
    def add_job_output(
        job_id: str,
        output_type: str,
        path: str,
        size_mb: float,
        sha256: str,
        duration_ms: Optional[int] = None
    ) -> JobOutputModel:
        with db_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO job_outputs (job_id, type, path, size_mb, sha256, duration_ms)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (job_id, output_type, path, size_mb, sha256, duration_ms)
            )
            inserted_id = cursor.lastrowid
        return JobOutputModel(
            id=inserted_id,
            job_id=job_id,
            type=output_type,
            path=path,
            size_mb=size_mb,
            sha256=sha256,
            duration_ms=duration_ms
        )

    @staticmethod
    def get_job_outputs(job_id: str) -> List[JobOutputModel]:
        with db_connection() as conn:
            rows = conn.execute("SELECT * FROM job_outputs WHERE job_id = ?", (job_id,)).fetchall()
            return [
                JobOutputModel(
                    id=row["id"],
                    job_id=row["job_id"],
                    type=row["type"],
                    path=row["path"],
                    size_mb=row["size_mb"],
                    sha256=row["sha256"],
                    duration_ms=row["duration_ms"]
                ) for row in rows
            ]

    @staticmethod
    def get_next_queued_job() -> Optional[JobModel]:
        with db_connection() as conn:
            row = conn.execute(
                "SELECT * FROM jobs WHERE status = 'QUEUED' ORDER BY created_at ASC LIMIT 1"
            ).fetchone()
            if not row:
                return None
            return JobModel(
                id=row["id"],
                input_path=row["input_path"],
                profile=row["profile"],
                variants=row["variants"],
                extract_features=bool(row["extract_features"]),
                generate_proxy=bool(row["generate_proxy"]),
                status=row["status"],
                progress=row["progress"],
                created_at=row["created_at"],
                started_at=row["started_at"],
                finished_at=row["finished_at"],
                error_message=row["error_message"]
            )

    @staticmethod
    def fail_stuck_jobs() -> None:
        """Mark any jobs left in RUNNING status on server startup as FAILED."""
        finished_at = datetime.now(timezone.utc).isoformat()
        with db_connection() as conn:
            conn.execute(
                "UPDATE jobs SET status = 'FAILED', finished_at = ?, error_message = 'Job interrupted by server restart.' WHERE status = 'RUNNING'",
                (finished_at,)
            )
        logger.info("Checked and cleaned up stuck jobs from database.")
