from datetime import datetime
from typing import Optional
from pydantic import BaseModel

class JobModel(BaseModel):
    id: str
    input_path: str
    profile: str
    variants: int
    extract_features: bool
    generate_proxy: bool
    status: str
    progress: float = 0.0
    created_at: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    error_message: Optional[str] = None

class JobOutputModel(BaseModel):
    id: Optional[int] = None
    job_id: str
    type: str  # proxy, variant, sidecar, quality_report
    path: str
    size_mb: float
    sha256: str
    duration_ms: Optional[int] = None
