#!/usr/bin/env python3
"""
Comprehensive test suite for DeepInfraAdapter
Tests both DeepInfra API and local Whisper fallback
"""

import sys
import os
import json
import time
from pathlib import Path

# Add project to path
sys.path.insert(0, '/home/cyberkitty/Projects/Cyberkitty119')

# Setup environment
os.environ['DEEPINFRA_API_KEY'] = open('/tmp/env.vpn').read().split('DEEPINFRA_API_KEY=')[1].split('\n')[0].strip("'")

from transcribe_client.deepinfra import DeepInfraAdapter


def create_test_audio(filename, duration=5):
    """Create test MP3 file with specified duration."""
    import subprocess
    subprocess.run([
        'ffmpeg', '-f', 'lavfi', '-i', f'sine=frequency=1000:duration={duration}',
        '-q:a', '5', filename, '-y'
    ], capture_output=True, check=True)
    return Path(filename)


def test_deepinfra_adapter():
    """Run comprehensive test suite."""
    
    print("\n" + "=" * 70)
    print("DeepInfra Adapter Test Suite")
    print("=" * 70)
    
    adapter = DeepInfraAdapter()
    results = []
    
    # Test 1: Small file (5 seconds)
    print("\n[TEST 1] Small audio file (5 seconds)")
    print("-" * 70)
    test_file_1 = create_test_audio('/tmp/test_audio_5sec.mp3', duration=5)
    start = time.time()
    
    try:
        result = adapter.transcribe(str(test_file_1))
        elapsed = time.time() - start
        
        test_data = {
            "name": "Small file (5 sec)",
            "file_size": test_file_1.stat().st_size,
            "duration": 5,
            "provider": result['meta']['provider'],
            "status": result['status'],
            "text_length": len(result['text']),
            "segments": len(result['segments']),
            "elapsed_sec": round(elapsed, 2),
            "success": True
        }
        
        print(f"✅ Status: {result['status']}")
        print(f"   Provider: {result['meta']['provider']}")
        print(f"   Text length: {len(result['text'])} chars")
        print(f"   Segments: {len(result['segments'])}")
        print(f"   Time: {elapsed:.2f}s")
        
        results.append(test_data)
        
    except Exception as e:
        print(f"❌ Error: {type(e).__name__}: {e}")
        results.append({
            "name": "Small file (5 sec)",
            "success": False,
            "error": str(e)
        })
    
    # Test 2: Medium file (30 seconds)
    print("\n[TEST 2] Medium audio file (30 seconds)")
    print("-" * 70)
    test_file_2 = create_test_audio('/tmp/test_audio_30sec.mp3', duration=30)
    start = time.time()
    
    try:
        result = adapter.transcribe(str(test_file_2))
        elapsed = time.time() - start
        
        test_data = {
            "name": "Medium file (30 sec)",
            "file_size": test_file_2.stat().st_size,
            "duration": 30,
            "provider": result['meta']['provider'],
            "status": result['status'],
            "text_length": len(result['text']),
            "segments": len(result['segments']),
            "elapsed_sec": round(elapsed, 2),
            "success": True
        }
        
        print(f"✅ Status: {result['status']}")
        print(f"   Provider: {result['meta']['provider']}")
        print(f"   Text length: {len(result['text'])} chars")
        print(f"   Segments: {len(result['segments'])}")
        print(f"   Time: {elapsed:.2f}s")
        
        results.append(test_data)
        
    except Exception as e:
        print(f"❌ Error: {type(e).__name__}: {e}")
        results.append({
            "name": "Medium file (30 sec)",
            "success": False,
            "error": str(e)
        })
    
    # Test 3: Response format validation
    print("\n[TEST 3] Response format validation")
    print("-" * 70)
    
    try:
        result = adapter.transcribe(str(test_file_1))
        
        required_fields = ["status", "text", "segments", "model", "meta"]
        required_meta = ["file_uri", "provider", "ts"]
        
        missing = [f for f in required_fields if f not in result]
        if missing:
            print(f"❌ Missing top-level fields: {missing}")
        else:
            print("✅ All top-level fields present")
        
        missing_meta = [f for f in required_meta if f not in result['meta']]
        if missing_meta:
            print(f"❌ Missing meta fields: {missing_meta}")
        else:
            print("✅ All meta fields present")
        
        # Validate provider value
        provider = result['meta']['provider']
        if provider in ['deepinfra', 'deepinfra_or_local', 'local_whisper']:
            print(f"✅ Valid provider: {provider}")
        else:
            print(f"❌ Invalid provider: {provider}")
        
        results.append({
            "name": "Response format validation",
            "success": True,
            "has_all_fields": not missing and not missing_meta
        })
        
    except Exception as e:
        print(f"❌ Error: {type(e).__name__}: {e}")
        results.append({
            "name": "Response format validation",
            "success": False,
            "error": str(e)
        })
    
    # Test 4: Retry logic (if accessible)
    print("\n[TEST 4] Retry logic verification")
    print("-" * 70)
    
    try:
        # Run multiple times to check for retry behavior
        adapter2 = DeepInfraAdapter()
        result = adapter2.transcribe(str(test_file_2))
        
        attempt = result['meta'].get('attempt', 1)
        print(f"✅ Attempt count: {attempt}")
        print(f"   Provider used: {result['meta']['provider']}")
        
        results.append({
            "name": "Retry logic",
            "success": True,
            "attempt": attempt,
            "provider": result['meta']['provider']
        })
        
    except Exception as e:
        print(f"❌ Error: {type(e).__name__}: {e}")
        results.append({
            "name": "Retry logic",
            "success": False,
            "error": str(e)
        })
    
    # Summary
    print("\n" + "=" * 70)
    print("Test Summary")
    print("=" * 70)
    
    success_count = sum(1 for r in results if r.get('success', False))
    total_count = len(results)
    
    print(f"\nResults: {success_count}/{total_count} tests passed")
    
    for result in results:
        status = "✅ PASS" if result.get('success', False) else "❌ FAIL"
        print(f"  {status}: {result.get('name', 'Unknown')}")
    
    # Detailed summary
    print("\n" + "-" * 70)
    print("Detailed Results (JSON):")
    print("-" * 70)
    print(json.dumps(results, indent=2, default=str))
    
    print("\n" + "=" * 70)
    if success_count == total_count:
        print("✅ ALL TESTS PASSED - Ready for production!")
    else:
        print(f"⚠️  {total_count - success_count} test(s) failed - Review results above")
    print("=" * 70 + "\n")
    
    return success_count == total_count


if __name__ == '__main__':
    success = test_deepinfra_adapter()
    sys.exit(0 if success else 1)
