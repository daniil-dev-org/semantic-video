from pydantic import BaseModel, Field
from typing import Optional, List

class JobCreateRequest(BaseModel):
    input_path: str = Field(..., description="Path to source video file relative to workspace, or absolute path.")
    profile: str = Field("light_ab_test", description="Processing profile to use.")
    variants: int = Field(4, ge=1, le=10, description="Number of variations to generate.")
    extract_features: bool = Field(True, description="Whether to extract video features and generate an STP-0.1 sidecar.")
    generate_proxy: bool = Field(True, description="Whether to generate a 144p analysis proxy.")

class JobCreateResponse(BaseModel):
    job_id: str
    status: str

class JobOutputSchema(BaseModel):
    id: int
    job_id: str
    type: str
    path: str
    size_mb: float
    sha256: str
    duration_ms: Optional[int] = None

class JobDetailsResponse(BaseModel):
    id: str
    input_path: str
    profile: str
    variants: int
    extract_features: bool
    generate_proxy: bool
    status: str
    progress: float
    created_at: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    error_message: Optional[str] = None
