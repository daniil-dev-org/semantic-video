import threading
import time
from datetime import datetime, timezone

from ..core.logging import setup_logger
from ..db.repository import SQLRepository
from .processor import JobProcessor

logger = setup_logger("app.workers.worker")

# Thread controls
_worker_thread = None
_stop_event = threading.Event()
_wakeup_condition = threading.Condition()

def _worker_loop():
    """Continuous worker loop executing FIFO queued jobs with condition-based sleeping."""
    logger.info("Background worker loop started.")
    
    while not _stop_event.is_set():
        try:
            # 1. Fetch next queued job
            job = SQLRepository.get_next_queued_job()
            
            if not job:
                # No job queued, wait on condition variable
                with _wakeup_condition:
                    logger.info("Worker sleeping. Waiting for new jobs...")
                    # wait returns True if it was notified, or False if it timed out (we check every 30s as safety heartbeat)
                    _wakeup_condition.wait(timeout=30.0)
                continue
                
            # Double check if server has shutdown while waiting
            if _stop_event.is_set():
                break
                
            logger.info(f"Worker woke up. Starting execution of job {job.id}...")
            
            # 2. Process the job
            processor = JobProcessor(job)
            processor.process()
            
        except Exception as e:
            logger.exception(f"Unhandled exception in worker loop: {e}")
            time.sleep(5.0)  # simple cooldown on database or file system error

    logger.info("Background worker loop finished.")


def start_worker() -> None:
    """Start the background worker thread."""
    global _worker_thread
    if _worker_thread is not None and _worker_thread.is_alive():
        logger.warning("Worker thread is already running.")
        return
        
    _stop_event.clear()
    _worker_thread = threading.Thread(target=_worker_loop, name="BackgroundWorker", daemon=True)
    _worker_thread.start()
    logger.info("Started background worker thread.")


def stop_worker() -> None:
    """Stop the background worker thread gracefully on application exit."""
    global _worker_thread
    if _worker_thread is None:
        return
        
    logger.info("Signaling background worker thread to stop...")
    _stop_event.set()
    
    # Wake up thread from wait condition
    with _wakeup_condition:
        _wakeup_condition.notify_all()
        
    _worker_thread.join(timeout=5.0)
    logger.info("Background worker thread stopped.")


def trigger_worker_wakeup() -> None:
    """Notify the worker thread immediately when a new job is queued."""
    with _wakeup_condition:
        _wakeup_condition.notify_all()
    logger.info("Notified background worker thread of new job.")
