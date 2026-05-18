#!/usr/bin/env python3
"""
Whisper Transcription Pipeline Orchestrator

Handles the complete flow:
1. Receive file path
2. Audio preparation (FFmpeg extraction & compression)
3. Whisper GPU transcription
4. Result delivery and cleanup
"""

import os
import sys
import json
import time
import subprocess
import logging
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime
from dataclasses import dataclass, asdict
from enum import Enum

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
BASE_DIR = Path("/home/cyberkitty/Projects/Cyberkitty119")
MEDIA_DIR = BASE_DIR / "media"
INCOMING_DIR = MEDIA_DIR / "incoming"
PROCESSING_DIR = MEDIA_DIR / "processing"
RESULTS_DIR = MEDIA_DIR / "results"

# Docker images
AUDIO_PREP_IMAGE = "di_worker:latest"  # Built from tools/di_worker/Dockerfile
WHISPER_GPU_IMAGE = "whisper-gpu:latest"  # Already built

# FFmpeg command for audio preparation
FFMPEG_CMD = [
    "ffmpeg", "-i", "{input}", "-q:a", "5", "-acodec", "libmp3lame",
    "-ar", "16000", "-ac", "1", "-y", "{output}"
]

class JobStatus(Enum):
    PENDING = "pending"
    PREPARING = "preparing"
    TRANSCRIBING = "transcribing"
    COMPLETED = "completed"
    FAILED = "failed"

@dataclass
class TranscriptionJob:
    job_id: str
    input_file: Path
    status: JobStatus
    start_time: float
    preparation_time: Optional[float] = None
    transcription_time: Optional[float] = None
    error: Optional[str] = None
    
    @property
    def total_time(self) -> Optional[float]:
        if self.preparation_time and self.transcription_time:
            return self.preparation_time + self.transcription_time
        return None

class WhisperPipeline:
    """Orchestrate the complete transcription pipeline."""
    
    def __init__(self):
        self.jobs: Dict[str, TranscriptionJob] = {}
        self._ensure_directories()
    
    def _ensure_directories(self):
        """Ensure all required directories exist."""
        for directory in [INCOMING_DIR, PROCESSING_DIR, RESULTS_DIR]:
            directory.mkdir(parents=True, exist_ok=True)
            logger.info(f"✓ Directory ready: {directory}")
    
    def prepare_audio(self, input_file: Path, job_id: str) -> Optional[Path]:
        """
        Extract and compress audio from media file.
        
        Returns: Path to prepared MP3 file, or None on failure
        """
        logger.info(f"[Job {job_id}] Starting audio preparation...")
        
        output_file = PROCESSING_DIR / f"{job_id}_prepared.mp3"
        
        try:
            start = time.time()
            
            # Use FFmpeg directly (no Docker for now, simpler)
            cmd = [
                "ffmpeg", "-i", str(input_file),
                "-q:a", "5", "-acodec", "libmp3lame",
                "-ar", "16000", "-ac", "1", "-y", str(output_file)
            ]
            
            result = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True, 
                timeout=300
            )
            
            if result.returncode != 0:
                error_msg = f"FFmpeg failed: {result.stderr[-200:]}"
                logger.error(f"[Job {job_id}] {error_msg}")
                return None
            
            prep_time = time.time() - start
            output_size = output_file.stat().st_size / 1024**2
            
            logger.info(f"[Job {job_id}] ✓ Audio prepared: {output_size:.1f}MB in {prep_time:.2f}s")
            
            # Update job
            if job_id in self.jobs:
                self.jobs[job_id].preparation_time = prep_time
                self.jobs[job_id].status = JobStatus.TRANSCRIBING
            
            return output_file
        
        except subprocess.TimeoutExpired:
            error_msg = "Audio preparation timeout (>5 min)"
            logger.error(f"[Job {job_id}] {error_msg}")
            if job_id in self.jobs:
                self.jobs[job_id].error = error_msg
            return None
        except Exception as e:
            error_msg = f"Audio preparation failed: {str(e)}"
            logger.error(f"[Job {job_id}] {error_msg}")
            if job_id in self.jobs:
                self.jobs[job_id].error = error_msg
            return None
    
    def transcribe_audio(self, audio_file: Path, job_id: str) -> Optional[Dict]:
        """
        Transcribe audio using Whisper GPU.
        
        Returns: Transcription result dict, or None on failure
        """
        logger.info(f"[Job {job_id}] Starting Whisper transcription...")
        
        try:
            start = time.time()
            
            # Use Docker to run Whisper
            docker_cmd = [
                "docker", "run", "--rm", "--gpus", "all",
                "-v", f"{str(audio_file)}:/input.mp3:ro",
                "-v", f"{str(RESULTS_DIR)}:/output",
                WHISPER_GPU_IMAGE,
                "python3", "-c",
                f"""
import whisper
import json
import sys

model = whisper.load_model("base", device="cuda")
result = model.transcribe("/input.mp3", language="ru", verbose=False)
json.dump(result, open("/output/{job_id}_result.json", "w"), ensure_ascii=False, indent=2)
print("OK")
"""
            ]
            
            result = subprocess.run(
                docker_cmd,
                capture_output=True,
                text=True,
                timeout=300
            )
            
            trans_time = time.time() - start
            
            if result.returncode != 0:
                error_msg = f"Whisper failed: {result.stderr[-200:]}"
                logger.error(f"[Job {job_id}] {error_msg}")
                return None
            
            # Load result
            result_file = RESULTS_DIR / f"{job_id}_result.json"
            if not result_file.exists():
                error_msg = "Whisper produced no output"
                logger.error(f"[Job {job_id}] {error_msg}")
                return None
            
            with open(result_file) as f:
                transcription = json.load(f)
            
            logger.info(f"[Job {job_id}] ✓ Transcription complete in {trans_time:.2f}s")
            
            # Update job
            if job_id in self.jobs:
                self.jobs[job_id].transcription_time = trans_time
                self.jobs[job_id].status = JobStatus.COMPLETED
            
            return transcription
        
        except subprocess.TimeoutExpired:
            error_msg = "Transcription timeout (>5 min)"
            logger.error(f"[Job {job_id}] {error_msg}")
            if job_id in self.jobs:
                self.jobs[job_id].error = error_msg
            return None
        except Exception as e:
            error_msg = f"Transcription failed: {str(e)}"
            logger.error(f"[Job {job_id}] {error_msg}")
            if job_id in self.jobs:
                self.jobs[job_id].error = error_msg
            return None
    
    def generate_report(self, job_id: str, transcription: Dict, 
                       prep_time: float, trans_time: float) -> Path:
        """Generate processing report."""
        report_path = RESULTS_DIR / f"{job_id}_report.txt"
        
        text = transcription.get("text", "")
        segments = transcription.get("segments", [])
        audio_duration = sum(s["end"] for s in segments) if segments else 0
        
        report = f"""================================================================================
TRANSCRIPTION PROCESSING REPORT
================================================================================

Job ID: {job_id}
Timestamp: {datetime.now().isoformat()}

PROCESSING TIMES

  Audio extraction: {prep_time:.2f}s
  Whisper transcription: {trans_time:.2f}s
  Total: {prep_time + trans_time:.2f}s
  
TRANSCRIPTION RESULTS

  Text length: {len(text)} characters
  Segments: {len(segments)}
  Audio duration: {audio_duration:.1f}s
  Real-time factor: {audio_duration / trans_time:.1f}x
  
TOP SEGMENTS (first 10)

"""
        for i, seg in enumerate(segments[:10]):
            report += f"{i+1:2d}. [{seg['start']:6.1f}s - {seg['end']:6.1f}s] {seg['text']}\n"
        
        report += f"""
FULL TRANSCRIPTION TEXT

{text}

================================================================================
"""
        
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(report)
        
        logger.info(f"[Job {job_id}] Report saved: {report_path}")
        return report_path
    
    def process(self, input_file: Path, job_id: Optional[str] = None) -> Dict:
        """
        Process a media file through the complete pipeline.
        
        Args:
            input_file: Path to input media file
            job_id: Unique job identifier (auto-generated if None)
        
        Returns:
            Status dict with paths and results
        """
        if job_id is None:
            job_id = f"job_{int(time.time() * 1000)}"
        
        # Validate input
        if not input_file.exists():
            return {
                "status": "error",
                "error": f"Input file not found: {input_file}"
            }
        
        # Create job record
        job = TranscriptionJob(
            job_id=job_id,
            input_file=input_file,
            status=JobStatus.PREPARING,
            start_time=time.time()
        )
        self.jobs[job_id] = job
        
        logger.info(f"[Job {job_id}] Starting pipeline for {input_file.name}")
        
        # Step 1: Audio preparation
        audio_file = self.prepare_audio(input_file, job_id)
        if not audio_file:
            job.status = JobStatus.FAILED
            return {
                "status": "error",
                "error": job.error or "Audio preparation failed"
            }
        
        # Step 2: Transcription
        transcription = self.transcribe_audio(audio_file, job_id)
        if not transcription:
            job.status = JobStatus.FAILED
            return {
                "status": "error",
                "error": job.error or "Transcription failed"
            }
        
        # Step 3: Report generation
        report_file = self.generate_report(
            job_id, transcription,
            job.preparation_time or 0,
            job.transcription_time or 0
        )
        
        result_file = RESULTS_DIR / f"{job_id}_result.json"
        
        # Return results
        total_time = time.time() - job.start_time
        return {
            "status": "success",
            "job_id": job_id,
            "total_time": total_time,
            "preparation_time": job.preparation_time,
            "transcription_time": job.transcription_time,
            "result_file": str(result_file),
            "report_file": str(report_file),
            "transcription_text": transcription.get("text", "")[:500] + "...",
            "segments": len(transcription.get("segments", [])),
            "audio_duration": sum(s["end"] for s in transcription.get("segments", [])),
        }

def main():
    """Test the pipeline."""
    if len(sys.argv) < 2:
        print("Usage: python3 orchestrator.py <input_file>")
        sys.exit(1)
    
    input_file = Path(sys.argv[1])
    
    pipeline = WhisperPipeline()
    result = pipeline.process(input_file)
    
    print("\n" + "="*70)
    print("PIPELINE RESULT")
    print("="*70)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print("="*70)

if __name__ == "__main__":
    main()
