#!/usr/bin/env python3
"""
Test script for GPU transcription API endpoint.

Usage:
    python3 test_gpu_endpoint.py <file_path>
    
Example:
    python3 test_gpu_endpoint.py /path/to/video.webm
"""

import asyncio
import json
import sys
from pathlib import Path

# Добавляем текущую директорию в path
sys.path.insert(0, '/home/cyberkitty/Projects/Cyberkitty119')

from pipeline_orchestrator import WhisperPipeline


async def test_gpu_endpoint(file_path: str) -> None:
    """Test the GPU transcription pipeline."""
    
    file_path = Path(file_path)
    
    if not file_path.exists():
        print(f"❌ File not found: {file_path}")
        sys.exit(1)
    
    file_size_mb = file_path.stat().st_size / 1024**2
    print(f"\n📹 Testing GPU Transcription Endpoint")
    print(f"{'='*60}")
    print(f"File: {file_path.name}")
    print(f"Size: {file_size_mb:.1f} MB")
    print(f"{'='*60}")
    
    # Initialize pipeline
    print("\n🔧 Initializing pipeline...")
    pipeline = WhisperPipeline()
    
    # Process file
    print("⏱️  Starting transcription (this may take a few minutes)...")
    result = pipeline.process(file_path)
    
    # Display results
    print(f"\n{'='*60}")
    print("✅ RESULTS")
    print(f"{'='*60}")
    print(f"Status: {result['status']}")
    print(f"Job ID: {result['job_id']}")
    print(f"Total Time: {result['total_time']:.2f}s")
    print(f"  - Preparation: {result['preparation_time']:.2f}s")
    print(f"  - Transcription: {result['transcription_time']:.2f}s")
    print(f"Segments: {result['segments']}")
    print(f"Audio Duration: {result['audio_duration']:.0f}s ({result['audio_duration']/60:.1f} min)")
    
    # Calculate performance metrics
    speedup = (result['audio_duration'] / result['transcription_time'])
    throughput = 60 / result['total_time']
    print(f"\n📊 Performance Metrics")
    print(f"{'='*60}")
    print(f"GPU Speedup: {speedup:.2f}x faster than real-time")
    print(f"File Throughput: {throughput:.2f} files/minute")
    print(f"Result File: {result['result_file']}")
    print(f"Report File: {result['report_file']}")
    
    # Show snippet of transcription
    if 'transcription_text' in result:
        text = result['transcription_text'][:200]
        print(f"\n📝 First 200 chars of transcription:")
        print(f"{'='*60}")
        print(f"{text}...")
    
    print(f"\n{'='*60}")
    print("✓ Test completed successfully!")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 test_gpu_endpoint.py <file_path>")
        print("Example: python3 test_gpu_endpoint.py /path/to/video.webm")
        sys.exit(1)
    
    file_path = sys.argv[1]
    asyncio.run(test_gpu_endpoint(file_path))
