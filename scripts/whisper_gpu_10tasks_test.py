#!/usr/bin/env python3
"""
Test 10 parallel Whisper transcriptions on GPU
"""
import os
import time
import subprocess
import sys

INPUT_FILE = "/app/audio/audio_prepared.mp3"
OUTPUT_DIR = "/app/audio"

os.makedirs(OUTPUT_DIR, exist_ok=True)

print("="*70)
print("GPU WHISPER PARALLEL TEST - 10 CONCURRENT TASKS")
print("="*70)

import torch
print(f"\n🔧 System Information:")
print(f"   CUDA device: {torch.cuda.get_device_name(0)}")
props = torch.cuda.get_device_properties(0)
print(f"   Total GPU memory: {props.total_memory / 1024**3:.1f}GB")

# Create worker script
worker_script = """
import sys
import time
import torch
import whisper

task_id = int(sys.argv[1])
input_file = sys.argv[2]

try:
    model = whisper.load_model("base", device="cuda")
    start = time.time()
    result = model.transcribe(input_file, language="ru", verbose=False)
    elapsed = time.time() - start
    print(f"TASK_{task_id}_OK|{elapsed:.2f}|{len(result['text'])}", flush=True)
except Exception as e:
    print(f"TASK_{task_id}_ERROR|{str(e)}", flush=True)
"""

worker_path = "/tmp/whisper_worker_10.py"
with open(worker_path, 'w') as f:
    f.write(worker_script)

print(f"\n[TEST] Running 10 transcriptions in parallel...\n")

parallel_start = time.time()
processes = []
results = {}

for task_id in range(1, 11):
    cmd = ["python3", worker_path, str(task_id), INPUT_FILE]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    processes.append((task_id, proc))
    print(f"   [Task {task_id:2d}] Started")

print()
for task_id, proc in processes:
    stdout, stderr = proc.communicate()
    
    if stdout.strip():
        parts = stdout.strip().split("|")
        if len(parts) >= 2 and "OK" in parts[0]:
            elapsed = float(parts[1])
            text_len = int(parts[2]) if len(parts) > 2 else 0
            results[task_id] = {'task_id': task_id, 'time': elapsed, 'status': 'success'}
            print(f"   [Task {task_id:2d}] ✓ {elapsed:6.2f}s")
        else:
            error = parts[1] if len(parts) > 1 else "Unknown"
            results[task_id] = {'task_id': task_id, 'status': 'error'}
            print(f"   [Task {task_id:2d}] ✗ Error")

parallel_total = time.time() - parallel_start

successful = [r for r in results.values() if r['status'] == 'success']

print(f"\n{'='*70}")
print(f"RESULTS: {len(successful)}/10 successful")
print(f"{'='*70}\n")

if successful:
    times = [r['time'] for r in successful]
    print(f"Task times: {min(times):.2f}s - {max(times):.2f}s (avg {sum(times)/len(times):.2f}s)")
    print(f"Wall-clock time: {parallel_total:.2f}s")
    
    sequential_est = sum(times)
    speedup = sequential_est / parallel_total
    
    print(f"\nSequential estimate: {sequential_est:.2f}s")
    print(f"Parallel time: {parallel_total:.2f}s")
    print(f"Speedup: {speedup:.2f}x")
    
    print(f"\n📊 Comparison:")
    print(f"  5 tasks:  3.50x speedup")
    print(f"  10 tasks: {speedup:.2f}x speedup")
    
    if speedup > 3.5:
        print(f"\n✓ 10 tasks BETTER than 5 tasks ({speedup:.2f}x > 3.50x)")
        print(f"  GPU can handle more parallelism!")
    elif speedup < 3.5:
        print(f"\n⚠️  10 tasks WORSE than 5 tasks ({speedup:.2f}x < 3.50x)")
        print(f"  GPU reached its limit around 5-7 tasks")
    else:
        print(f"\n≈ Similar performance to 5 tasks")
