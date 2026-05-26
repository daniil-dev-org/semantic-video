FROM python:3.12-slim

# Install system dependencies: FFmpeg, OpenCV runtime libs, and build essentials
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all source files
COPY . .

# Create storage directories inside the container
RUN mkdir -p storage/uploads storage/jobs storage/outputs

# Expose API port
EXPOSE 8000

# Environment defaults (overridden by podman run / docker-compose)
ENV PYTHONUNBUFFERED=1
ENV THREAD_LIMIT=1
ENV JOB_TIMEOUT_SEC=600
ENV MAX_UPLOAD_SIZE_MB=500

# Redis is disabled by default (SQLite-only mode).
# Set REDIS_ADDR=host:port to enable Redis Stream listener.
ENV REDIS_ADDR=""

# CMD to launch Uvicorn hosting the FastAPI application
CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
