#!/usr/bin/env python3
"""
Minimal GPU Pipeline Test - No .env Required
Tests pipeline_orchestrator.py directly, bypassing config.
"""

import sys
import os
from pathlib import Path
import time

# Set minimal env vars BEFORE imports
os.environ['BOT_TOKEN'] = 'test_token_12345:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefg'
os.environ['DATABASE_URL'] = 'sqlite:///test.db'
os.environ['LOG_LEVEL'] = 'INFO'

# Add project to path
sys.path.insert(0, '/home/cyberkitty/Projects/Cyberkitty119')

from pipeline_orchestrator import WhisperPipeline


def print_section(title: str):
    """Print formatted section header."""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)


def test_pipeline(media_file: Path):
    """Test GPU pipeline directly."""
    
    print_section("🚀 GPU PIPELINE TEST (Direct)")
    
    # Validate file
    if not media_file.exists():
        print(f"❌ File not found: {media_file}")
        return False
    
    file_size_mb = media_file.stat().st_size / 1024**2
    print(f"\n📁 Media File:")
    print(f"   Path: {media_file.name}")
    print(f"   Size: {file_size_mb:.1f} MB")
    print(f"   Format: {media_file.suffix}")
    
    # Initialize pipeline
    print(f"\n🔧 Initializing Pipeline...")
    try:
        pipeline = WhisperPipeline()
        print(f"   ✓ Pipeline created")
    except Exception as e:
        print(f"   ❌ Failed to initialize: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Process file
    print(f"\n⏱️  Starting Processing...")
    start_time = time.time()
    
    try:
        result = pipeline.process(media_file)
    except Exception as e:
        print(f"   ❌ Processing failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    elapsed = time.time() - start_time
    
    # Display results
    print_section("📊 RESULTS")
    
    if result.get("status") != "success":
        print(f"❌ Pipeline failed: {result.get('error')}")
        return False
    
    print(f"\n✅ Status: {result['status'].upper()}")
    print(f"   Job ID: {result['job_id']}")
    
    print(f"\n⏱️  Timing:")
    print(f"   Total: {result['total_time']:.2f}s")
    print(f"   - Audio Prep: {result['preparation_time']:.2f}s")
    print(f"   - GPU Transcription: {result['transcription_time']:.2f}s")
    
    # Performance metrics
    audio_duration_min = result['audio_duration'] / 60
    speedup = result['audio_duration'] / result['transcription_time'] if result['transcription_time'] > 0 else 0
    throughput = 3600 / result['total_time']  # files per hour
    
    print(f"\n📈 Performance:")
    print(f"   Audio Duration: {audio_duration_min:.2f} minutes")
    print(f"   GPU Speedup: {speedup:.2f}x (vs real-time)")
    print(f"   Throughput: {throughput:.2f} files/hour")
    print(f"   Segments: {result['segments']}")
    
    # File paths
    print(f"\n📄 Output Files:")
    result_file = Path(result['result_file'])
    report_file = Path(result['report_file'])
    
    if result_file.exists():
        result_size_mb = result_file.stat().st_size / 1024**2
        print(f"   ✓ Result JSON: {result_file.name} ({result_size_mb:.1f} MB)")
    else:
        print(f"   ⚠️  Result file path: {result_file}")
    
    if report_file.exists():
        report_size_kb = report_file.stat().st_size / 1024
        print(f"   ✓ Report TXT: {report_file.name} ({report_size_kb:.1f} KB)")
    else:
        print(f"   ⚠️  Report file path: {report_file}")
    
    # Sample transcript
    if 'transcription_text' in result and result['transcription_text']:
        text = result['transcription_text'][:150]
        print(f"\n📝 Transcript Sample (first 150 chars):")
        print(f"   {text}...")
    
    print_section("✅ TEST PASSED")
    print(f"\n✓ Pipeline executed successfully!")
    print(f"✓ Results saved to: {result_file.parent}")
    print(f"✓ Test completed in {elapsed:.2f}s")
    
    return True


def find_media_file() -> Path | None:
    """Find a suitable media file for testing."""
    
    candidates = [
        Path("/home/cyberkitty/Projects/Cyberkitty119/sample_mono_16k.wav"),
        Path("/home/cyberkitty/Projects/Cyberkitty119/sample.wav"),
        Path("/home/cyberkitty/Projects/Cyberkitty119/tone.wav"),
    ]
    
    for candidate in candidates:
        if candidate.exists():
            return candidate
    
    return None


def main():
    """Main test function."""
    
    print_section("GPU PIPELINE SYSTEM TEST")
    print("\nThis test verifies:")
    print("  1. Pipeline initialization")
    print("  2. Audio file processing")
    print("  3. GPU Whisper transcription")
    print("  4. Result output generation")
    print("  5. Performance metrics")
    
    # Get media file
    if len(sys.argv) > 1:
        media_file = Path(sys.argv[1])
    else:
        media_file = find_media_file()
    
    if not media_file:
        print("\n❌ No media file found")
        print("\nUsage:")
        print("  python3 test_gpu_direct.py /path/to/audio.wav")
        print("\nExample:")
        print("  python3 test_gpu_direct.py /home/cyberkitty/Projects/Cyberkitty119/sample.wav")
        sys.exit(1)
    
    # Run test
    try:
        success = test_pipeline(media_file)
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n❌ Test interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n\n❌ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
