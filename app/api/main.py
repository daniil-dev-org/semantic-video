from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from ..core.logging import setup_logger
from ..core.storage import init_storage
from ..db.repository import SQLRepository
from .routes_jobs import router as jobs_router

logger = setup_logger("app.api.main")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup sequence
    logger.info("Starting Semantic Video Service...")
    
    # 1. Initialize folders
    init_storage()
    
    # 2. Initialize Database tables
    SQLRepository.init_db()
    
    # 3. Clean up stuck jobs (e.g. from crash or hard restart)
    SQLRepository.fail_stuck_jobs()
    
    # 4. Start background worker thread
    from ..workers.worker import start_worker, stop_worker
    start_worker()
    
    # 5. Start Redis listener (optional — only if REDIS_ADDR is set)
    from ..workers.redis_listener import start_redis_listener, stop_redis_listener
    start_redis_listener()
    
    yield
    
    # Shutdown sequence
    logger.info("Stopping Semantic Video Service...")
    stop_redis_listener()
    stop_worker()

app = FastAPI(
    title="Semantic Video A/B Processing Service",
    description="FastAPI service for video proxy encoding, dynamic A/B variation generation, and OpenCV feature extraction sidecars.",
    version="1.0.0",
    lifespan=lifespan
)

# CORS configurations
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routes
app.include_router(jobs_router, prefix="/api")

@app.get("/")
def read_root():
    return {
        "service": "Semantic Video Processing API",
        "version": "1.0.0",
        "docs_url": "/docs",
        "status": "healthy"
    }
