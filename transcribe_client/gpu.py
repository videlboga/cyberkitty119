"""GPU Whisper adapter for transcribe_client - uses pipeline_orchestrator."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

# Add project root to path for pipeline_orchestrator import
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from pipeline_orchestrator import WhisperPipeline


class GPUAdapter:
    """Adapter that uses local GPU Whisper via pipeline_orchestrator."""
    
    def __init__(self):
        self.pipeline = WhisperPipeline()
        self.device = "cuda"
    
    def transcribe(self, file_uri: str, mode: Optional[str] = None) -> dict:
        """Transcribe using GPU Whisper pipeline.
        
        Args:
            file_uri: Path to media file
            mode: Unused (for compatibility with other adapters)
        
        Returns:
            TranscriptionResult dict with keys: status, text, segments, meta
        """
        try:
            file_path = Path(file_uri)
            if not file_path.exists():
                return {
                    "status": "error",
                    "text": "",
                    "segments": [],
                    "model": "gpu-whisper",
                    "meta": {"error": f"File not found: {file_uri}"},
                }
            
            # Run GPU pipeline
            result = self.pipeline.process(file_path)
            
            if result.get("status") != "success":
                return {
                    "status": "error",
                    "text": "",
                    "segments": [],
                    "model": "gpu-whisper",
                    "meta": {"error": result.get("error", "Unknown error")},
                }
            
            # Parse result
            transcript_text = result.get("transcription_text", "")
            
            # Build segments from result (if available)
            segments = []
            if "result_file" in result:
                try:
                    import json
                    result_file = Path(result["result_file"])
                    if result_file.exists():
                        with open(result_file) as f:
                            whisper_result = json.load(f)
                            segments = whisper_result.get("segments", [])
                except Exception as e:
                    # Fallback if we can't parse segments
                    pass
            
            # If no segments, create a single segment from full text
            if not segments and transcript_text:
                segments = [{
                    "start": 0.0,
                    "end": result.get("audio_duration", 0),
                    "text": transcript_text,
                    "confidence": 0.95,
                }]
            
            return {
                "status": "ok",
                "text": transcript_text,
                "segments": segments,
                "model": "gpu-whisper-base",
                "meta": {
                    "file_uri": file_uri,
                    "job_id": result.get("job_id"),
                    "total_time": result.get("total_time"),
                    "preparation_time": result.get("preparation_time"),
                    "transcription_time": result.get("transcription_time"),
                    "audio_duration": result.get("audio_duration"),
                    "result_file": result.get("result_file"),
                    "report_file": result.get("report_file"),
                },
            }
        
        except Exception as e:
            return {
                "status": "error",
                "text": "",
                "segments": [],
                "model": "gpu-whisper",
                "meta": {"error": str(e)},
            }
