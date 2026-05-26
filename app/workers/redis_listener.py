"""
Redis Stream listener for integration with Go video-pipeline service.

Connects to the shared Redis instance and reads from the 'video:process' stream.
For each incoming message, creates a job in the SQLite database and triggers
the background worker for execution.

Gracefully degrades: if REDIS_ADDR is empty, this module does nothing.
"""

import threading
import time
import json

from ..core.config import (
    REDIS_ADDR, REDIS_STREAM_PROCESS, REDIS_CONSUMER_GROUP, REDIS_CONSUMER_NAME,
)
from ..core.logging import setup_logger
from ..db.repository import SQLRepository
from .worker import trigger_worker_wakeup

logger = setup_logger("app.workers.redis_listener")

_listener_thread = None
_stop_event = threading.Event()


def _ensure_consumer_group(rdb) -> None:
    """Create consumer group if it does not already exist."""
    try:
        rdb.xgroup_create(
            name=REDIS_STREAM_PROCESS,
            groupname=REDIS_CONSUMER_GROUP,
            id="0",
            mkstream=True,
        )
        logger.info(
            f"Created Redis consumer group '{REDIS_CONSUMER_GROUP}' "
            f"on stream '{REDIS_STREAM_PROCESS}'"
        )
    except Exception as e:
        # BUSYGROUP means group already exists — that's fine
        if "BUSYGROUP" in str(e):
            logger.info(f"Consumer group '{REDIS_CONSUMER_GROUP}' already exists.")
        else:
            raise


def _generate_job_id_from_redis() -> str:
    """Generate a sequential job ID for Redis-sourced tasks."""
    from datetime import datetime, timezone
    from ..db.repository import db_connection

    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        with db_connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as count FROM jobs WHERE id LIKE ?",
                (f"{today_str}-%",),
            ).fetchone()
            count = row["count"] if row else 0
    except Exception:
        count = 0
    return f"{today_str}-{count + 1:03d}"


def _listener_loop() -> None:
    """Main loop: XREADGROUP from Redis, create SQLite jobs, wake worker."""
    import redis as redis_lib

    rdb = redis_lib.Redis.from_url(f"redis://{REDIS_ADDR}", decode_responses=True)

    # Wait for Redis to become available
    for attempt in range(30):
        try:
            rdb.ping()
            logger.info(f"Connected to Redis at {REDIS_ADDR}")
            break
        except Exception:
            if _stop_event.is_set():
                return
            logger.warning(
                f"Redis not reachable at {REDIS_ADDR}, retrying ({attempt+1}/30)..."
            )
            time.sleep(2)
    else:
        logger.error("Failed to connect to Redis after 30 attempts. Listener exiting.")
        return

    _ensure_consumer_group(rdb)

    logger.info("Redis listener loop started. Waiting for messages...")

    while not _stop_event.is_set():
        try:
            # Block for up to 5 seconds waiting for new messages
            results = rdb.xreadgroup(
                groupname=REDIS_CONSUMER_GROUP,
                consumername=REDIS_CONSUMER_NAME,
                streams={REDIS_STREAM_PROCESS: ">"},
                count=1,
                block=5000,
            )

            if not results:
                continue

            for stream_name, messages in results:
                for msg_id, fields in messages:
                    try:
                        _handle_message(rdb, msg_id, fields)
                    except Exception as e:
                        logger.exception(
                            f"Failed to handle Redis message {msg_id}: {e}"
                        )
                        # Still ACK to avoid infinite reprocessing;
                        # the error is logged and can be investigated
                        rdb.xack(
                            REDIS_STREAM_PROCESS, REDIS_CONSUMER_GROUP, msg_id
                        )

        except Exception as e:
            if _stop_event.is_set():
                break
            logger.exception(f"Redis listener error: {e}")
            time.sleep(5)

    rdb.close()
    logger.info("Redis listener loop stopped.")


def _handle_message(rdb, msg_id: str, fields: dict) -> None:
    """Process a single message from the video:process stream."""
    filename = fields.get("filename", "")
    local_path = fields.get("local_path", "")
    profile = fields.get("profile", "light_ab_test")
    variants = int(fields.get("variants", "4"))
    correlation_id = fields.get("correlation_id", "")
    go_job_id = fields.get("job_id", "")

    logger.info(
        f"Received Redis message {msg_id}: "
        f"file={filename}, path={local_path}, profile={profile}, "
        f"variants={variants}, correlation_id={correlation_id}"
    )

    # Create a job in the SQLite database
    job_id = _generate_job_id_from_redis()

    SQLRepository.create_job(
        job_id=job_id,
        input_path=local_path,
        profile=profile,
        variants=variants,
        extract_features=True,
        generate_proxy=True,
    )

    logger.info(
        f"Created job {job_id} from Redis message "
        f"(go_job_id={go_job_id}, correlation_id={correlation_id})"
    )

    # ACK the message in Redis
    rdb.xack(REDIS_STREAM_PROCESS, REDIS_CONSUMER_GROUP, msg_id)
    rdb.xdel(REDIS_STREAM_PROCESS, msg_id)

    # Wake up the background worker
    trigger_worker_wakeup()


def start_redis_listener() -> None:
    """Start the Redis listener thread if REDIS_ADDR is configured."""
    global _listener_thread

    if not REDIS_ADDR:
        logger.info("REDIS_ADDR not set — Redis listener disabled (SQLite-only mode).")
        return

    if _listener_thread is not None and _listener_thread.is_alive():
        logger.warning("Redis listener thread is already running.")
        return

    _stop_event.clear()
    _listener_thread = threading.Thread(
        target=_listener_loop, name="RedisListener", daemon=True
    )
    _listener_thread.start()
    logger.info(f"Started Redis listener thread (stream={REDIS_STREAM_PROCESS}).")


def stop_redis_listener() -> None:
    """Stop the Redis listener thread gracefully."""
    global _listener_thread
    if _listener_thread is None:
        return

    logger.info("Signaling Redis listener thread to stop...")
    _stop_event.set()
    _listener_thread.join(timeout=10.0)
    logger.info("Redis listener thread stopped.")
