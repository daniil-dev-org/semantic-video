import os
import sys
import subprocess
import time
from pathlib import Path
from typing import List, Dict, Any, Tuple

from ..core.config import THREAD_LIMIT, JOB_TIMEOUT_SEC
from ..core.logging import setup_logger
from stp.utils import find_ffmpeg

logger = setup_logger("app.video.ffmpeg_runner")

class FFmpegRunner:
    """
    Orchestrates execution of FFmpeg commands.
    Supports advanced single-pass filter_complex pipelines and process priority control.
    """

    def __init__(self, job_id: str) -> None:
        self.job_id = job_id
        self.ffmpeg_bin = str(find_ffmpeg())
        logger.info(f"FFmpegRunner initialized for job {job_id} using FFmpeg: {self.ffmpeg_bin}")

    def run_single_pass(
        self,
        input_video: Path,
        output_paths: List[Path],
        compiled_filters: List[Tuple[List[str], List[str]]],
        has_audio: bool
    ) -> None:
        """
        Execute multiple variant encodes in a single FFmpeg invocation using a split filter_complex.
        This decodes the input video exactly once, resulting in major speedups.
        """
        t0 = time.perf_counter()
        N = len(output_paths)
        
        # 1. Compile filter_complex parts
        filter_complex_parts = []
        
        # Video split
        v_splits = "".join(f"[v_s{i}]" for i in range(N))
        filter_complex_parts.append(f"[0:v]split={N}{v_splits}")
        
        # Audio split (if present)
        if has_audio:
            a_splits = "".join(f"[a_s{i}]" for i in range(N))
            filter_complex_parts.append(f"[0:a]asplit={N}{a_splits}")
            
        # Add transformation chains
        for i in range(N):
            vf_list, af_list = compiled_filters[i]
            
            # Chain video filters
            vf_chain = ",".join(vf_list)
            filter_complex_parts.append(f"[v_s{i}]{vf_chain}[v_o{i}]")
            
            # Chain audio filters
            if has_audio:
                af_chain = ",".join(af_list)
                filter_complex_parts.append(f"[a_s{i}]{af_chain}[a_o{i}]")
                
        filter_complex_str = "; ".join(filter_complex_parts)
        
        # 2. Build final command
        cmd = [
            self.ffmpeg_bin, "-y",
            "-i", str(input_video),
            "-filter_complex", filter_complex_str
        ]
        
        # Map streams to each individual output
        for i in range(N):
            cmd.extend(["-map", f"[v_o{i}]"])
            if has_audio:
                cmd.extend(["-map", f"[a_o{i}]"])
                
            cmd.extend([
                "-c:v", "libx264",
                "-crf", "18",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                "-b:a", "192k",
                "-threads", str(THREAD_LIMIT),
                "-preset", "veryfast",
                str(output_paths[i])
            ])
            
        # 3. Execute subprocess with low priority
        logger.info(f"Running single-pass FFmpeg for job {self.job_id} generating {N} variants...")
        self._run_subprocess(cmd)
        
        elapsed = time.perf_counter() - t0
        logger.info(f"Successfully completed single-pass variation compile in {elapsed:.1f}s")

    def run_sequential(
        self,
        input_video: Path,
        output_paths: List[Path],
        compiled_filters: List[Tuple[List[str], List[str]]],
        has_audio: bool
    ) -> None:
        """
        Fallback sequential generator. Processes each variant one-by-one.
        Used if single-pass fails or is disabled due to memory pressure.
        """
        t0 = time.perf_counter()
        logger.warning(f"Falling back to sequential variation processing for job {self.job_id}")
        
        for i, out_path in enumerate(output_paths):
            vt0 = time.perf_counter()
            vf_list, af_list = compiled_filters[i]
            
            cmd = [
                self.ffmpeg_bin, "-y",
                "-i", str(input_video),
                "-vf", ",".join(vf_list)
            ]
            
            cmd.extend([
                "-c:v", "libx264",
                "-crf", "18",
                "-pix_fmt", "yuv420p",
            ])
            
            if has_audio and af_list:
                cmd.extend([
                    "-c:a", "aac",
                    "-b:a", "192k",
                    "-af", ",".join(af_list)
                ])
            elif not has_audio:
                cmd.append("-an")
                
            cmd.extend([
                "-threads", str(THREAD_LIMIT),
                "-preset", "veryfast",
                str(out_path)
            ])
            
            logger.info(f"Encoding variant {i+1}/{len(output_paths)} -> {out_path.name}...")
            self._run_subprocess(cmd)
            logger.info(f"Finished variant {i+1} in {time.perf_counter() - vt0:.1f}s")
            
        logger.info(f"Sequential variation compile finished in {time.perf_counter() - t0:.1f}s")

    def _run_subprocess(self, cmd: List[str]) -> None:
        """Execute a command list in a subprocess with priority controls and cancellation support."""
        creation_flags = 0
        preexec_fn = None
        
        # Apply platform-specific background priority controls
        if sys.platform == "win32":
            # CREATE_NO_WINDOW (0x08000000) + IDLE_PRIORITY_CLASS (0x00000040)
            creation_flags = 0x08000000 | 0x00000040
        else:
            # Lower CPU scheduling priority on Unix
            preexec_fn = lambda: os.nice(19)
            
        try:
            # Start process
            p = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=creation_flags,
                preexec_fn=preexec_fn
            )
            
            # Register process in API global registry for live cancellation support
            from ..api.routes_jobs import register_process, unregister_processes
            register_process(self.job_id, p)
            
            try:
                stdout, stderr = p.communicate(timeout=float(JOB_TIMEOUT_SEC))
            except subprocess.TimeoutExpired:
                p.kill()
                stdout, stderr = p.communicate()
                raise TimeoutError(f"FFmpeg processing timed out after {JOB_TIMEOUT_SEC} seconds.")
            finally:
                unregister_processes(self.job_id)
                
            if p.returncode != 0:
                err_msg = stderr.decode("utf-8", errors="replace")[-1000:]
                logger.error(f"FFmpeg failed with exit code {p.returncode}: {err_msg}")
                raise RuntimeError(f"FFmpeg compilation failed: {err_msg}")
                
        except Exception as e:
            logger.error(f"Failed to execute FFmpeg command: {e}")
            raise
