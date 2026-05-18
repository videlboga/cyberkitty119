#!/usr/bin/env python3
"""
GPU-specialized worker for transcription tasks.

This worker processes jobs of type 'media_gpu_transcription' using
local Whisper model on GPU (CUDA). It loads the model once and processes
jobs sequentially to avoid CUDA cache conflicts.

Usage:
    python gpu_worker.py --worker-id gpu-worker-1 --poll-interval 2
"""

from __future__ import annotations

import argparse
import os
import signal
import sys
import time
import torch
import whisper

from dataclasses import dataclass
from typing import Optional

from transkribator_modules.config import logger
from transkribator_modules.db import init_db
from transkribator_modules.db.models import ProcessingJob
from transkribator_modules.jobs import (
    acquire_job,
    complete_job,
    fail_job,
    release_job,
)
from transkribator_modules.jobs.handlers import dispatch_job
from transkribator_modules.jobs.queue import mark_job_progress
from transkribator_modules.jobs.bootstrap import register_builtin_handlers


class GracefulExit(SystemExit):
    """Sentinel exception used to break out of the worker loop."""


@dataclass(frozen=True)
class GPUWorkerConfig:
    worker_id: str
    poll_interval: float = 2.0
    run_once: bool = False
    dry_run: bool = False
    max_jobs: Optional[int] = None
    backoff_min: float = 1.0
    backoff_max: float = 30.0
    # GPU-specific settings
    model_name: str = "base"
    cuda_device: int = 0
    max_concurrent_gpu_jobs: int = 1  # Always 1 for Whisper (sequential processing)


class GPUJobWorker:
    """GPU-specialized worker for transcription tasks."""

    def __init__(self, config: GPUWorkerConfig) -> None:
        self.config = config
        self._shutdown = False
        self._current_job_id: Optional[int] = None
        self._processed_jobs = 0
        self._failed_jobs = 0
        self._total_job_time = 0.0
        self._start_monotonic = time.monotonic()
        self._last_idle_log = time.monotonic()
        self._current_backoff = max(config.backoff_min, 0.1)
        
        # GPU model (loaded once)
        self._model = None
        self._device = None

    def _setup_gpu(self) -> bool:
        """Initialize GPU and load Whisper model."""
        try:
            # Check GPU availability
            if not torch.cuda.is_available():
                logger.error("CUDA is not available on this system")
                return False
            
            device_count = torch.cuda.device_count()
            if self.config.cuda_device >= device_count:
                logger.error(
                    f"CUDA device {self.config.cuda_device} not found. "
                    f"Available devices: {device_count}"
                )
                return False
            
            # Set device
            self._device = f"cuda:{self.config.cuda_device}"
            torch.cuda.set_device(self.config.cuda_device)
            
            # Log GPU info
            gpu_name = torch.cuda.get_device_name(self.config.cuda_device)
            props = torch.cuda.get_device_properties(self.config.cuda_device)
            total_memory = props.total_memory / 1024**3
            
            logger.info(
                f"GPU Device: {gpu_name}",
                extra={
                    "device": self._device,
                    "total_memory_gb": round(total_memory, 1),
                },
            )
            
            # Load model
            logger.info(
                f"Loading Whisper {self.config.model_name} model on {self._device}...",
                extra={"device": self._device},
            )
            start_time = time.monotonic()
            self._model = whisper.load_model(self.config.model_name, device=self._device)
            load_time = time.monotonic() - start_time
            
            logger.info(
                f"Whisper model loaded successfully in {load_time:.2f}s",
                extra={
                    "model": self.config.model_name,
                    "device": self._device,
                    "load_time_seconds": round(load_time, 2),
                },
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to setup GPU: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    def _get_gpu_memory_info(self) -> dict:
        """Get current GPU memory usage."""
        try:
            if torch.cuda.is_available():
                props = torch.cuda.get_device_properties(self.config.cuda_device)
                total = props.total_memory / 1024**3
                free, _ = torch.cuda.mem_get_info()
                used = (props.total_memory - free) / 1024**3
                used_percent = (used / total * 100) if total > 0 else 0
                return {
                    "total_gb": round(total, 2),
                    "used_gb": round(used, 2),
                    "free_gb": round(free / 1024**3, 2),
                    "used_percent": round(used_percent, 1),
                }
        except Exception as e:
            logger.warning(f"Failed to get GPU memory info: {e}")
        return {}

    def start(self) -> None:
        """Start the GPU worker loop."""
        logger.info(
            "GPU Worker starting",
            extra={
                "worker_id": self.config.worker_id,
                "poll_interval": self.config.poll_interval,
                "model": self.config.model_name,
                "cuda_device": self.config.cuda_device,
            },
        )
        
        # Setup GPU and load model
        if not self._setup_gpu():
            logger.error("Failed to initialize GPU. Exiting.")
            sys.exit(1)
        
        self._start_monotonic = time.monotonic()
        
        try:
            while not self._shutdown:
                # Only process media_gpu_transcription jobs
                job = acquire_job(
                    worker_id=self.config.worker_id,
                    job_types=["media_gpu_transcription"],
                )
                
                if not job:
                    self._sleep()
                    continue
                
                self._current_job_id = job.id
                self._reset_backoff()
                job_started_at = time.monotonic()
                
                try:
                    duration = self._process(job)
                    if not self.config.dry_run:
                        complete_job(job.id)
                    else:
                        logger.info(
                            "Dry run enabled; job left in-progress",
                            extra={"job_id": job.id},
                        )
                    self._record_success(duration)
                    
                except GracefulExit:
                    raise
                except Exception as exc:
                    failure_duration = time.monotonic() - job_started_at
                    self._record_failure(failure_duration)
                    self._handle_failure(job, exc)
                finally:
                    self._current_job_id = None
                
                if self.config.run_once:
                    logger.info("Processed single job; stopping as requested.")
                    break
                if self.config.max_jobs and self._processed_jobs >= self.config.max_jobs:
                    logger.info(
                        "Max jobs reached; stopping worker",
                        extra={
                            "worker_id": self.config.worker_id,
                            "max_jobs": self.config.max_jobs,
                        },
                    )
                    break
                    
        except GracefulExit:
            logger.info("GPU Worker received shutdown request.")
        finally:
            self._release_current_job()
            self._log_summary()
            self._cleanup_gpu()

    def _sleep(self) -> None:
        """Sleep with exponential backoff."""
        timeout = self._current_backoff
        time.sleep(timeout)
        self._increase_backoff()
        now = time.monotonic()
        if now - self._last_idle_log >= max(timeout * 5, 30):
            mem_info = self._get_gpu_memory_info()
            logger.debug(
                "GPU Worker idle",
                extra={
                    "worker_id": self.config.worker_id,
                    "idle_seconds": round(now - self._last_idle_log, 1),
                    "gpu_memory": mem_info,
                },
            )
            self._last_idle_log = now

    def _increase_backoff(self) -> None:
        next_value = min(
            self._current_backoff * 2,
            max(self.config.backoff_max, self.config.backoff_min),
        )
        self._current_backoff = max(next_value, self.config.backoff_min)

    def _reset_backoff(self) -> None:
        self._current_backoff = max(self.config.backoff_min, 0.1)

    def _process(self, job: ProcessingJob) -> float:
        """Process a single GPU transcription job."""
        logger.info(
            "Processing GPU transcription job",
            extra={
                "job_id": job.id,
                "job_type": job.job_type,
                "user_id": job.user_id,
            },
        )
        
        # Log GPU memory before
        mem_before = self._get_gpu_memory_info()
        logger.debug("GPU memory before job", extra={"memory": mem_before})
        
        mark_job_progress(job.id, progress=0)
        started = time.monotonic()
        
        try:
            if not self.config.dry_run:
                dispatch_job(job)
            else:
                logger.info(
                    "Dry run: skipping dispatch",
                    extra={"job_id": job.id, "job_type": job.job_type},
                )
            
            duration = time.monotonic() - started
            
            # Log GPU memory after
            mem_after = self._get_gpu_memory_info()
            logger.debug("GPU memory after job", extra={"memory": mem_after})
            
            logger.info(
                "GPU transcription job processed",
                extra={
                    "job_id": job.id,
                    "duration_seconds": round(duration, 2),
                    "gpu_memory_used": mem_after.get("used_gb"),
                },
            )
            return duration
            
        except Exception as e:
            logger.error(f"Error processing GPU job: {e}")
            import traceback
            logger.error(traceback.format_exc())
            raise

    def _handle_failure(self, job: ProcessingJob, exc: Exception) -> None:
        """Handle job failure."""
        import traceback
        error_message = "".join(
            traceback.format_exception(type(exc), exc, exc.__traceback__)
        )
        logger.exception(
            "GPU job failed",
            extra={"job_id": job.id, "worker_id": self.config.worker_id},
        )
        fail_job(job.id, error_message=error_message)

    def _release_current_job(self) -> None:
        """Release in-progress job on shutdown."""
        if self._current_job_id is None:
            return
        logger.info(
            "Releasing in-progress GPU job due to shutdown",
            extra={"job_id": self._current_job_id},
        )
        release_job(self._current_job_id)
        self._current_job_id = None

    def _record_success(self, duration: float) -> None:
        self._processed_jobs += 1
        self._total_job_time += duration

    def _record_failure(self, duration: float) -> None:
        self._failed_jobs += 1
        self._total_job_time += duration

    def request_shutdown(self) -> None:
        """Request graceful shutdown."""
        self._shutdown = True

    def _cleanup_gpu(self) -> None:
        """Clean up GPU resources."""
        try:
            if self._model is not None:
                logger.info("Cleaning up GPU model")
                del self._model
                self._model = None
            torch.cuda.empty_cache()
            logger.info("GPU cleaned up successfully")
        except Exception as e:
            logger.warning(f"Error cleaning up GPU: {e}")

    def _log_summary(self) -> None:
        """Log worker summary."""
        runtime = time.monotonic() - self._start_monotonic
        total_jobs = self._processed_jobs + self._failed_jobs
        avg_duration = (
            self._total_job_time / total_jobs if total_jobs else 0.0
        )
        
        mem_info = self._get_gpu_memory_info()
        
        logger.info(
            "GPU Worker summary",
            extra={
                "worker_id": self.config.worker_id,
                "uptime_seconds": round(runtime, 1),
                "processed_jobs": self._processed_jobs,
                "failed_jobs": self._failed_jobs,
                "avg_duration_seconds": round(avg_duration, 2),
                "gpu_memory": mem_info,
            },
        )


def _signal_handler(worker: GPUJobWorker) -> None:
    """Handle SIGTERM and SIGINT."""
    def handler(signum, frame):
        logger.info(f"Received signal {signum}, requesting shutdown")
        worker.request_shutdown()
    return handler


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="GPU-specialized job worker")
    parser.add_argument("--worker-id", default="gpu-worker-1", help="Worker ID")
    parser.add_argument("--poll-interval", type=float, default=2.0, help="Poll interval in seconds")
    parser.add_argument("--run-once", action="store_true", help="Process one job and exit")
    parser.add_argument("--dry-run", action="store_true", help="Don't actually process jobs")
    parser.add_argument("--max-jobs", type=int, help="Max jobs to process before exiting")
    parser.add_argument("--model", default="base", help="Whisper model to use (tiny, base, small, medium, large)")
    parser.add_argument("--cuda-device", type=int, default=0, help="CUDA device index")
    parser.add_argument("--backoff-min", type=float, default=1.0, help="Min backoff seconds")
    parser.add_argument("--backoff-max", type=float, default=30.0, help="Max backoff seconds")
    
    args = parser.parse_args()
    
    # Initialize database
    init_db()
    
    # Register builtin handlers (including media_gpu_transcription)
    register_builtin_handlers()
    
    config = GPUWorkerConfig(
        worker_id=args.worker_id,
        poll_interval=args.poll_interval,
        run_once=args.run_once,
        dry_run=args.dry_run,
        max_jobs=args.max_jobs,
        model_name=args.model,
        cuda_device=args.cuda_device,
        backoff_min=args.backoff_min,
        backoff_max=args.backoff_max,
    )
    
    worker = GPUJobWorker(config)
    
    # Setup signal handlers
    signal.signal(signal.SIGTERM, _signal_handler(worker))
    signal.signal(signal.SIGINT, _signal_handler(worker))
    
    # Start worker
    worker.start()


if __name__ == "__main__":
    main()
