import json
import time
import os
from datetime import datetime, timezone
from pathlib import Path

from ..core.config import UPLOADS_DIR, JOBS_DIR, OUTPUTS_DIR
from ..core.storage import calculate_sha256, get_file_size_mb, cleanup_path
from ..core.logging import setup_logger
from ..db.repository import SQLRepository
from ..db.models import JobModel

from ..video.probe import probe_video
from ..video.profiles import load_profile
from ..video.variants import generate_variants_config, compile_filters
from ..video.ffmpeg_runner import FFmpegRunner
from ..video.quality import compare_videos

# STP Bridges
from ..stp_bridge.proxy import encode_proxy_bridge
from ..stp_bridge.features import extract_features_bridge

logger = setup_logger("app.workers.processor")

class JobProcessor:
    """Coordinates the entire life-cycle of a single video processing job."""

    def __init__(self, job: JobModel) -> None:
        self.job = job
        self.job_dir = JOBS_DIR / job.id
        self.output_dir = OUTPUTS_DIR / job.id
        self.runner = FFmpegRunner(job.id)

    def _is_cancelled(self) -> bool:
        """Query the database to check if the user has requested a cancellation."""
        current_job = SQLRepository.get_job(self.job.id)
        return current_job.status == "CANCELLED" if current_job else False

    def process(self) -> None:
        t0 = time.perf_counter()
        logger.info(f"Processing job {self.job.id} (input: {self.job.input_path})")
        
        try:
            # Create job specific directories
            self.job_dir.mkdir(parents=True, exist_ok=True)
            self.output_dir.mkdir(parents=True, exist_ok=True)
            
            # Transition to RUNNING
            SQLRepository.update_job_status(
                self.job.id, "RUNNING", started_at=datetime.now(timezone.utc).isoformat()
            )
            SQLRepository.update_job_progress(self.job.id, 10.0)
            
            # ────────────────────────────────────────────────────────
            # Step 1: Probe & Validate Input Video
            # ────────────────────────────────────────────────────────
            if self._is_cancelled():
                raise InterruptedError("Job cancelled by user.")
                
            input_path = Path(self.job.input_path)
            meta = probe_video(input_path)
            has_audio = meta.has_audio
            logger.info(f"Probed source metadata: {meta.width}x{meta.height} @ {meta.fps} fps, audio={has_audio}")
            
            # Save original file size in DB job outputs if desired (as a reference)
            SQLRepository.update_job_progress(self.job.id, 20.0)
            
            # ────────────────────────────────────────────────────────
            # Step 2: Proxy Encoding (if enabled)
            # ────────────────────────────────────────────────────────
            if self._is_cancelled():
                raise InterruptedError("Job cancelled by user.")
                
            proxy_path = None
            if self.job.generate_proxy:
                logger.info("Encoding lightweight analysis proxy...")
                # We save proxy in output folder
                proxy_path = self.output_dir / "proxy_144p.mp4"
                
                # Execute stp proxy encoder via bridge
                encode_proxy_bridge(input_path, self.output_dir, meta)
                
                if proxy_path.exists():
                    SQLRepository.add_job_output(
                        job_id=self.job.id,
                        output_type="proxy",
                        path=str(proxy_path),
                        size_mb=get_file_size_mb(proxy_path),
                        sha256=calculate_sha256(proxy_path),
                        duration_ms=meta.duration_ms
                    )
                SQLRepository.update_job_status(self.job.id, "PROXY_DONE")
                
            SQLRepository.update_job_progress(self.job.id, 30.0)
            
            # ────────────────────────────────────────────────────────
            # Step 3: Dynamic A/B Variations Generation
            # ────────────────────────────────────────────────────────
            if self._is_cancelled():
                raise InterruptedError("Job cancelled by user.")
                
            logger.info(f"Loading profile '{self.job.profile}'...")
            profile_data = load_profile(self.job.profile)
            
            logger.info(f"Generating deterministic variations config...")
            variants_cfgs = generate_variants_config(self.job.id, profile_data, self.job.variants)
            
            # Build list of variant outputs and compile their filters
            variant_paths = []
            compiled_filters = []
            for v_cfg in variants_cfgs:
                out_path = self.output_dir / f"variant_{v_cfg['name']}.mp4"
                variant_paths.append(out_path)
                
                vf, af = compile_filters(v_cfg, has_audio)
                compiled_filters.append((vf, af))
                
            # Execute variation encoding (Try Single-Pass, Fallback to Sequential)
            try:
                self.runner.run_single_pass(input_path, variant_paths, compiled_filters, has_audio)
            except Exception as ef:
                logger.warning(f"Single-pass FFmpeg compilation failed ({ef}). Trying sequential fallback...")
                # Clean up any partial files
                for vp in variant_paths:
                    cleanup_path(vp)
                # Sequential encode
                self.runner.run_sequential(input_path, variant_paths, compiled_filters, has_audio)
                
            # Verify outputs and record them in DB
            for idx, vp in enumerate(variant_paths):
                if vp.exists():
                    SQLRepository.add_job_output(
                        job_id=self.job.id,
                        output_type="variant",
                        path=str(vp),
                        size_mb=get_file_size_mb(vp),
                        sha256=calculate_sha256(vp),
                        duration_ms=meta.duration_ms # standard duration approximation
                    )
            
            SQLRepository.update_job_status(self.job.id, "VARIANTS_DONE")
            SQLRepository.update_job_progress(self.job.id, 70.0)
            
            # ────────────────────────────────────────────────────────
            # Step 4: OpenCV Feature Extraction (if enabled)
            # ────────────────────────────────────────────────────────
            if self._is_cancelled():
                raise InterruptedError("Job cancelled by user.")
                
            if self.job.extract_features:
                logger.info("Extracting OpenCV video features and sidecar...")
                sidecar_path = self.output_dir / "video_metrics_sidecar.json"
                
                # Extract features using stp code via bridge
                extract_features_bridge(input_path, self.output_dir, meta)
                
                if sidecar_path.exists():
                    SQLRepository.add_job_output(
                        job_id=self.job.id,
                        output_type="sidecar",
                        path=str(sidecar_path),
                        size_mb=get_file_size_mb(sidecar_path),
                        sha256=calculate_sha256(sidecar_path)
                    )
                SQLRepository.update_job_status(self.job.id, "FEATURES_DONE")
                
            SQLRepository.update_job_progress(self.job.id, 90.0)
            
            # ────────────────────────────────────────────────────────
            # Step 5: Quality Assessment Comparing Original & Variants
            # ────────────────────────────────────────────────────────
            if self._is_cancelled():
                raise InterruptedError("Job cancelled by user.")
                
            logger.info("Running quality assessment verification...")
            qa_reports = []
            for idx, vp in enumerate(variant_paths):
                if vp.exists():
                    report = compare_videos(input_path, vp, sample_frames=5)
                    qa_reports.append(report)
                    
            # Save final composite quality report as a job output file
            quality_report_path = self.output_dir / "quality_report.json"
            with open(quality_report_path, "w", encoding="utf-8") as f:
                json.dump({"job_id": self.job.id, "qa_verifications": qa_reports}, f, indent=2)
                
            SQLRepository.add_job_output(
                job_id=self.job.id,
                output_type="quality_report",
                path=str(quality_report_path),
                size_mb=get_file_size_mb(quality_report_path),
                sha256=calculate_sha256(quality_report_path)
            )
            
            # Finalize job to DONE
            finished_at = datetime.now(timezone.utc).isoformat()
            SQLRepository.update_job_status(self.job.id, "DONE", finished_at=finished_at)
            SQLRepository.update_job_progress(self.job.id, 100.0)
            
            elapsed = time.perf_counter() - t0
            logger.info(f"Successfully finished job {self.job.id} in {elapsed:.1f}s")
            
        except InterruptedError as ei:
            logger.warning(f"Job {self.job.id} processing was explicitly cancelled: {ei}")
            # Ensure DB is canceled if we caught cancellation in loop
            finished_at = datetime.now(timezone.utc).isoformat()
            SQLRepository.update_job_status(self.job.id, "CANCELLED", error_message=str(ei), finished_at=finished_at)
            self._cleanup_outputs()
            
        except Exception as e:
            logger.exception(f"Job {self.job.id} processing failed: {e}")
            finished_at = datetime.now(timezone.utc).isoformat()
            SQLRepository.update_job_status(self.job.id, "FAILED", error_message=str(e), finished_at=finished_at)
            self._cleanup_outputs()
            
        finally:
            # Clean up the temporary workspace directory
            cleanup_path(self.job_dir)

    def _cleanup_outputs(self) -> None:
        """Clean up generated files in outputs in case of failure or cancellation."""
        logger.info(f"Cleaning up partial outputs for job {self.job.id}...")
        cleanup_path(self.output_dir)
