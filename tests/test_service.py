import os
import time
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from app.core.config import BASE_DIR, STORAGE_DIR, UPLOADS_DIR, OUTPUTS_DIR
from app.core.storage import init_storage, calculate_sha256, cleanup_path
from app.db.repository import SQLRepository, db_connection
from app.api.main import app
from app.video.profiles import load_profile
from app.video.variants import generate_variants_config, compile_filters
from app.video.quality import compare_videos

# Initialize storage and DB before testing
@pytest.fixture(scope="session", autouse=True)
def setup_test_env():
    init_storage()
    SQLRepository.init_db()
    SQLRepository.fail_stuck_jobs()
    yield
    # Cleanup DB test jobs
    try:
        with db_connection() as conn:
            conn.execute("DELETE FROM jobs WHERE id LIKE 'test-%'")
    except Exception:
        pass

def test_sqlite_repository():
    """Test standard database repository writes and reads."""
    job_id = f"test-rep-{int(time.time())}"
    job = SQLRepository.create_job(
        job_id=job_id,
        input_path="uploads/dummy.mp4",
        profile="light_ab_test",
        variants=2,
        extract_features=True,
        generate_proxy=True
    )
    
    assert job is not None
    assert job.id == job_id
    assert job.status == "QUEUED"
    assert job.progress == 0.0
    
    # Update status
    SQLRepository.update_job_status(job_id, "RUNNING", started_at="2026-05-26T10:00:00")
    job = SQLRepository.get_job(job_id)
    assert job.status == "RUNNING"
    assert job.started_at == "2026-05-26T10:00:00"
    
    # Add output
    out = SQLRepository.add_job_output(
        job_id=job_id,
        output_type="proxy",
        path="storage/outputs/dummy_proxy.mp4",
        size_mb=1.5,
        sha256="abc123sha",
        duration_ms=5000
    )
    assert out.id is not None
    assert out.sha256 == "abc123sha"
    
    outputs = SQLRepository.get_job_outputs(job_id)
    assert len(outputs) == 1
    assert outputs[0].type == "proxy"

def test_profile_loading():
    """Test YAML profile parsing."""
    profile = load_profile("light_ab_test")
    assert profile is not None
    assert "speed" in profile
    assert profile["speed"]["enabled"] is True
    assert "factor_min" in profile["speed"]

def test_deterministic_variants():
    """Test repeatable variant parameters generation using seed."""
    profile = load_profile("light_ab_test")
    job_id = "test-job-seed"
    
    variants1 = generate_variants_config(job_id, profile, 3)
    variants2 = generate_variants_config(job_id, profile, 3)
    
    # Assert deterministic equality
    assert len(variants1) == 3
    assert len(variants2) == 3
    for i in range(3):
        assert variants1[i]["speed"] == variants2[i]["speed"]
        assert variants1[i]["crop_percent"] == variants2[i]["crop_percent"]
        assert variants1[i]["brightness"] == variants2[i]["brightness"]
        assert variants1[i]["contrast"] == variants2[i]["contrast"]
        assert variants1[i]["noise_strength"] == variants2[i]["noise_strength"]
        
    # Compile filters checks
    vf, af = compile_filters(variants1[0], has_audio=True)
    assert len(vf) > 0
    assert len(af) > 0

def test_fastapi_client():
    """Test FastAPI endpoint responses using TestClient."""
    client = TestClient(app)
    
    # Root check
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["service"] == "Semantic Video Processing API"
    
    # Post job with invalid input path
    response = client.post("/api/jobs", json={
        "input_path": "uploads/non_existent_file.mp4",
        "profile": "light_ab_test",
        "variants": 2
    })
    assert response.status_code == 400
    assert "non_existent_file.mp4" in response.json()["detail"]

def test_integration_pipeline():
    """
    E2E integration test: submits a real video job using test_video.mp4,
    polls background execution, and asserts correct database outputs & served sidecar content.
    """
    client = TestClient(app)
    
    # Use TestClient with lifespan events enabled to trigger worker thread startup/shutdown
    with TestClient(app) as test_client:
        input_file = "video_pipeline/input/test_video.mp4"
        
        # 1. Post job
        response = test_client.post("/api/jobs", json={
            "input_path": input_file,
            "profile": "light_ab_test",
            "variants": 2,
            "extract_features": True,
            "generate_proxy": True
        })
        
        assert response.status_code == 200
        data = response.json()
        assert "job_id" in data
        job_id = data["job_id"]
        assert data["status"] == "QUEUED"
        
        # 2. Poll until complete or timed out (max 45 seconds)
        completed = False
        for _ in range(45):
            time.sleep(1.0)
            status_resp = test_client.get(f"/api/jobs/{job_id}")
            assert status_resp.status_code == 200
            status_data = status_resp.json()
            
            if status_data["status"] == "DONE":
                completed = True
                break
            elif status_data["status"] == "FAILED":
                pytest.fail(f"Job failed during background processing: {status_data.get('error_message')}")
                
        assert completed, f"Job {job_id} did not finish within 45s timeout (stuck at status {status_data['status']})"
        
        # 3. Verify outputs
        outputs_resp = test_client.get(f"/api/jobs/{job_id}/outputs")
        assert outputs_resp.status_code == 200
        outputs = outputs_resp.json()
        
        # We expect: 1 proxy, 2 variants, 1 sidecar, 1 quality_report
        output_types = [o["type"] for o in outputs]
        assert "proxy" in output_types
        assert "sidecar" in output_types
        assert "quality_report" in output_types
        assert output_types.count("variant") == 2
        
        # Check files exist on disk and size > 0
        for out in outputs:
            path = Path(out["path"])
            assert path.exists(), f"Output file does not exist on disk: {path}"
            assert path.stat().st_size > 0
            assert len(out["sha256"]) == 64
            
        # 4. Check sidecar serving
        sidecar_resp = test_client.get(f"/api/jobs/{job_id}/sidecar")
        assert sidecar_resp.status_code == 200
        sidecar_data = sidecar_resp.json()
        assert sidecar_data["stp_version"] == "0.1"
        assert "video_features" in sidecar_data
        assert "global" in sidecar_data["video_features"]
