import json
import shutil
from pathlib import Path
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, BackgroundTasks, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse
from typing import List

from ..core.logging import setup_logger
from ..core.config import BASE_DIR, STORAGE_DIR
from ..db.repository import SQLRepository, db_connection
from .schemas import JobCreateRequest, JobCreateResponse, JobDetailsResponse, JobOutputSchema

logger = setup_logger("app.api.routes_jobs")
router = APIRouter(prefix="/jobs", tags=["Jobs"])

def generate_job_id() -> str:
    """Generate job ID in format YYYY-MM-DD-XXX based on today's count."""
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        with db_connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as count FROM jobs WHERE id LIKE ?",
                (f"{today_str}-%",)
            ).fetchone()
            count = row["count"] if row else 0
    except Exception as e:
        logger.error(f"Error querying job count for ID generation: {e}")
        count = 0
    return f"{today_str}-{count + 1:03d}"

# Global registry of active FFmpeg/analysis processes for cancellation support
ACTIVE_PROCESSES = {}

def register_process(job_id: str, popen_obj) -> None:
    if job_id not in ACTIVE_PROCESSES:
        ACTIVE_PROCESSES[job_id] = []
    ACTIVE_PROCESSES[job_id].append(popen_obj)

def unregister_processes(job_id: str) -> None:
    if job_id in ACTIVE_PROCESSES:
        ACTIVE_PROCESSES.pop(job_id, None)

def kill_job_processes(job_id: str) -> bool:
    """Kill all active subprocesses registered for a job ID."""
    processes = ACTIVE_PROCESSES.get(job_id, [])
    if not processes:
        return False
    
    logger.info(f"Killing active processes for job {job_id}...")
    for p in processes:
        try:
            p.terminate()
            p.wait(timeout=2.0)
        except Exception as e:
            logger.warning(f"Error terminating process: {e}. Trying hard kill...")
            try:
                p.kill()
            except Exception as ek:
                logger.error(f"Failed to kill process: {ek}")
    ACTIVE_PROCESSES.pop(job_id, None)
    return True


@router.post("", response_model=JobCreateResponse)
def create_job(request: JobCreateRequest, background_tasks: BackgroundTasks):
    """
    Queue a new video processing job.
    Validates that the input path exists before queuing.
    """
    input_path = Path(request.input_path)
    
    # Resolve relative paths relative to workspace root
    if not input_path.is_absolute():
        input_path = (BASE_DIR / input_path).resolve()
        
    if not input_path.exists():
        raise HTTPException(
            status_code=400,
            detail=f"Input video file does not exist: {request.input_path}"
        )
        
    # Generate job ID and register in database
    job_id = generate_job_id()
    try:
        job = SQLRepository.create_job(
            job_id=job_id,
            input_path=str(input_path),
            profile=request.profile,
            variants=request.variants,
            extract_features=request.extract_features,
            generate_proxy=request.generate_proxy
        )
    except Exception as e:
        logger.error(f"Failed to create job in DB: {e}")
        raise HTTPException(status_code=500, detail="Database write failure.")
        
    logger.info(f"Queued new job {job_id} with profile '{request.profile}'")
    
    # Import and notify background worker loop to wake up and process
    from ..workers.worker import trigger_worker_wakeup
    background_tasks.add_task(trigger_worker_wakeup)
    
    return JobCreateResponse(job_id=job_id, status=job.status)


@router.get("/{job_id}", response_model=JobDetailsResponse)
def get_job(job_id: str):
    """Retrieve details and status for a specific job."""
    job = SQLRepository.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")
    return job


@router.get("/{job_id}/outputs", response_model=List[JobOutputSchema])
def get_job_outputs(job_id: str):
    """Retrieve list of generated outputs for a specific job."""
    job = SQLRepository.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")
    return SQLRepository.get_job_outputs(job_id)


@router.get("/{job_id}/sidecar")
def get_job_sidecar(job_id: str):
    """Return the generated video_metrics_sidecar.json file if features were extracted."""
    job = SQLRepository.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")
        
    outputs = SQLRepository.get_job_outputs(job_id)
    sidecar_output = next((o for o in outputs if o.type == "sidecar"), None)
    
    if not sidecar_output:
        if job.status in ["QUEUED", "PENDING", "RUNNING"]:
            raise HTTPException(status_code=202, detail="Job is still processing.")
        raise HTTPException(
            status_code=404, 
            detail="No sidecar output found for this job. Ensure extract_features was enabled."
        )
        
    sidecar_path = Path(sidecar_output.path)
    if not sidecar_path.exists():
        raise HTTPException(status_code=500, detail="Sidecar file recorded in DB but missing on disk.")
        
    # Read and return JSON content directly
    try:
        with open(sidecar_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return JSONResponse(content=data)
    except Exception as e:
        logger.error(f"Failed to read sidecar file: {e}")
        raise HTTPException(status_code=500, detail="Failed to read sidecar file content.")


@router.post("/{job_id}/cancel")
def cancel_job(job_id: str):
    """Cancel a queued or currently running job and clean up active processes."""
    job = SQLRepository.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")
        
    if job.status in ["DONE", "FAILED", "CANCELLED"]:
        return {"status": job.status, "message": f"Job is already finished with state {job.status}"}
        
    # Mark as cancelled in DB
    finished_at = datetime.now(timezone.utc).isoformat()
    SQLRepository.update_job_status(
        job_id=job_id,
        status="CANCELLED",
        error_message="Job canceled by user request.",
        finished_at=finished_at
    )
    
    # Kill running processes if running
    killed = kill_job_processes(job_id)
    
    logger.info(f"Job {job_id} canceled successfully (subprocesses killed: {killed})")
    return {"status": "CANCELLED", "message": f"Job {job_id} cancelled successfully."}


@router.get("/nextcloud/files")
def list_nextcloud_files():
    """List available files in the Nextcloud staging folder (uploads/accepted)."""
    from ..core.config import UPLOADS_DIR
    accepted_dir = UPLOADS_DIR / "accepted"
    files = []
    if accepted_dir.exists():
        for f in accepted_dir.glob("*.mp4"):
            size_mb = f.stat().st_size / (1024 * 1024)
            files.append({
                "name": f.name,
                "path": f"storage/uploads/accepted/{f.name}",
                "size_mb": round(size_mb, 2)
            })
    return files


@router.post("/upload", response_model=JobCreateResponse)
def upload_and_start_job(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    profile: str = Form("light_ab_test"),
    variants: int = Form(4),
    extract_features: bool = Form(True),
    generate_proxy: bool = Form(True)
):
    """Upload a raw video file and immediately trigger a processing job."""
    from ..core.config import UPLOADS_DIR
    accepted_dir = UPLOADS_DIR / "accepted"
    accepted_dir.mkdir(parents=True, exist_ok=True)
    
    # Save the uploaded file
    target_path = accepted_dir / file.filename
    try:
        with target_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        logger.error(f"Failed to save uploaded file {file.filename}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save uploaded file: {str(e)}")
        
    input_path = f"storage/uploads/accepted/{file.filename}"
    resolved_path = (BASE_DIR / input_path).resolve()
    
    # Generate job ID and register in database
    job_id = generate_job_id()
    try:
        job = SQLRepository.create_job(
            job_id=job_id,
            input_path=str(resolved_path),
            profile=profile,
            variants=variants,
            extract_features=extract_features,
            generate_proxy=generate_proxy
        )
    except Exception as e:
        logger.error(f"Failed to create job in DB: {e}")
        raise HTTPException(status_code=500, detail="Database write failure.")
        
    logger.info(f"Uploaded {file.filename} and queued job {job_id}")
    
    # Wake up worker
    from ..workers.worker import trigger_worker_wakeup
    background_tasks.add_task(trigger_worker_wakeup)
    
    return JobCreateResponse(job_id=job_id, status=job.status)
