#!/usr/bin/env python3
"""
Integration Test: GPU Transcription via Worker Pipeline
Tests that TranscribeClient GPU adapter works with job worker pipeline.
"""

import sys
import os
from pathlib import Path

# Set env vars BEFORE imports
os.environ['BOT_TOKEN'] = 'test_token:abc123'
os.environ['DATABASE_URL'] = 'sqlite:///test_integration.db'
os.environ['LOG_LEVEL'] = 'INFO'
os.environ['TRANSCRIBE_DEFAULT_MODE'] = 'gpu'  # ← Use GPU adapter

sys.path.insert(0, '/home/cyberkitty/Projects/Cyberkitty119')


def print_section(title: str):
    """Print formatted section."""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)


def test_gpu_adapter():
    """Test GPU adapter directly."""
    
    print_section("🧪 TEST 1: GPU Adapter Direct")
    
    from transcribe_client import TranscribeClient
    
    # Find test file
    media_file = Path("/home/cyberkitty/Projects/Cyberkitty119/sample_mono_16k.wav")
    if not media_file.exists():
        print(f"❌ Test file not found: {media_file}")
        return False
    
    print(f"Media file: {media_file.name} ({media_file.stat().st_size / 1024:.1f} KB)")
    
    # Create client with GPU adapter
    print("Creating TranscribeClient with mode='gpu'...")
    client = TranscribeClient(default_mode="gpu")
    
    # Transcribe
    print("Calling transcribe()...")
    result = client.transcribe(str(media_file))
    
    # Check result
    if result.get("status") != "ok":
        print(f"❌ Transcription failed: {result.get('meta')}")
        return False
    
    print(f"✓ Status: {result['status']}")
    print(f"✓ Model: {result['model']}")
    print(f"✓ Text length: {len(result['text'])} chars")
    print(f"✓ Segments: {len(result['segments'])} segments")
    print(f"✓ Meta keys: {', '.join(result['meta'].keys())}")
    
    # Check important meta fields
    meta = result['meta']
    if 'job_id' in meta:
        print(f"✓ Job ID: {meta['job_id']}")
    if 'total_time' in meta:
        print(f"✓ Total time: {meta['total_time']:.2f}s")
    
    return True


def test_adapter_resolution():
    """Test that _resolve_default_adapter returns GPU adapter."""
    
    print_section("🧪 TEST 2: Adapter Resolution")
    
    from transcribe_client import _resolve_default_adapter
    
    print("Testing _resolve_default_adapter(default_mode='gpu')...")
    
    # Resolve adapter with explicit GPU mode
    adapter = _resolve_default_adapter(default_mode="gpu")
    
    print(f"✓ Adapter type: {type(adapter).__name__}")
    print(f"✓ Adapter module: {type(adapter).__module__}")
    
    # Check it's GPU adapter
    if "GPUAdapter" not in type(adapter).__name__:
        print(f"❌ Expected GPUAdapter but got {type(adapter).__name__}")
        return False
    
    print("✓ GPU adapter correctly resolved!")
    return True


def main():
    """Run all tests."""
    
    print_section("🚀 INTEGRATION TEST: GPU Transcription Pipeline")
    
    try:
        # Test 1: Direct GPU adapter
        test1_ok = test_gpu_adapter()
        
        # Test 2: Adapter resolution
        test2_ok = test_adapter_resolution()
        
        # Summary
        print_section("📊 TEST SUMMARY")
        print(f"Test 1 (GPU Adapter): {'✅ PASS' if test1_ok else '❌ FAIL'}")
        print(f"Test 2 (Adapter Resolution): {'✅ PASS' if test2_ok else '❌ FAIL'}")
        
        if test1_ok and test2_ok:
            print_section("✅ ALL TESTS PASSED")
            print("GPU integration with worker pipeline is working!")
            return 0
        else:
            print_section("❌ SOME TESTS FAILED")
            return 1
    
    except Exception as e:
        print_section("❌ TEST ERROR")
        print(f"Exception: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
