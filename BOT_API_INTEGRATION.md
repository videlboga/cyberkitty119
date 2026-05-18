# Bot-API Integration Guide for GPU Pipeline

## 📊 Current State

### ✅ What's Ready
1. **GPU Pipeline** (`pipeline_orchestrator.py`)
   - Full orchestration from file → audio prep → transcription → results
   - Performance: 57.35s for 21-min audio (8.56s prep + 48.79s transcription)
   - GPU memory: 3.49GB peak usage (safe on 7.7GB VRAM)

2. **API Endpoint** (`api_server.py`)
   - `POST /api/v1/transcribe-gpu` - GPU transcription endpoint
   - `GET /api/v1/pipeline-status` - GPU status check
   - Response format: Validated with Pydantic models

3. **Telegram Bot** (`cyberkitty_modular.py` + modules)
   - Media message handling in `transkribator_modules/bot/handlers.py`
   - Queue system via `transkribator_modules/jobs/media.py`
   - Database integration for tracking

### ⚠️ Integration Points

The bot currently:
- Downloads files via Telegram Bot API
- Processes through `transkribator_modules/transcribe/transcriber_v4.py` (DeepInfra API)
- Stores results in database
- Sends results back to user

To integrate GPU pipeline, we need to:
1. ✏️ Modify message handler to support GPU transcription option
2. ✏️ Add GPU processing to queue system
3. ✏️ Update result delivery to use pipeline outputs

---

## 🔄 Integration Flow

```
User sends video/audio
        ↓
Bot downloads file to media/incoming/
        ↓
Check transcription method:
  ├─ /transcribe-gpu → USE GPU PIPELINE
  └─ /transcribe     → USE DEEPINFRA API
        ↓
For GPU path:
  1. Call POST /api/v1/transcribe-gpu with file path
  2. Wait for result (could add async polling)
  3. Read result JSON and report from media/results/
  4. Send formatted response to user
        ↓
Send result to user + options menu
```

---

## 📝 Code Changes Needed

### 1. Update Message Handler (`transkribator_modules/bot/handlers.py`)

**Current behavior**: All files go through DeepInfra API

**Need to add**:
```python
# Option 1: New /transcribe-gpu command
@CommandHandler("transcribe_gpu", transcribe_gpu_command)

# Option 2: Auto-detect based on file size
# Files > 50MB always use GPU
# Files < 50MB ask user which method

# Option 3: User preference in database
# Add gpu_transcription_enabled to User model
```

### 2. Create GPU Handler Function

**Location**: `transkribator_modules/bot/handlers.py` or new file

**Responsibilities**:
1. Download file from Telegram
2. Save to `media/incoming/`
3. Call `/api/v1/transcribe-gpu` endpoint
4. Poll for results (if async needed)
5. Read output files from `media/results/`
6. Format and send to user

### 3. Update Queue System (Optional)

**Location**: `transkribator_modules/jobs/media.py`

**Current**: Uses DeepInfra API in parallel

**Enhancement**: 
- Detect GPU availability via `/api/v1/pipeline-status`
- Route to GPU if available and file suitable
- Rate-limit to 5 concurrent GPU tasks

### 4. Database Schema Update (Optional)

**Add to User model**:
```python
gpu_transcription_enabled: bool = False
preferred_transcription_method: str = "auto"  # "auto" | "gpu" | "deepinfra"
```

**Add to Transcription model**:
```python
transcription_method: str = "deepinfra"  # "deepinfra" | "gpu"
gpu_job_id: str = None  # Track GPU pipeline job
```

---

## 🚀 Implementation Priority

### Phase 1: Basic Integration (30 minutes)
✅ Create `/transcribe-gpu` command
✅ Implement simple file → API → result flow
✅ Send results to user
⏭️ No queue system changes
⏭️ No database schema changes

### Phase 2: Auto-Detection (30 minutes)
✏️ Detect file size and route automatically
✏️ Large files → GPU, Small files → DeepInfra
✏️ Add user setting for preference

### Phase 3: Advanced Queueing (1 hour)
✏️ Integrate with existing queue system
✏️ Rate-limit GPU tasks to 5 concurrent
✏️ Database tracking for all transcriptions

---

## 📋 API Contract Review

### Endpoint: `POST /api/v1/transcribe-gpu`

**Request**:
```json
{
  "file_path": "/path/to/media/file.mp3",
  "language": "ru"
}
```

**Response (Success)**:
```json
{
  "status": "success",
  "job_id": "job_1773649631615",
  "total_time": 57.35921359062195,
  "preparation_time": 8.56324052810669,
  "transcription_time": 48.78582048416138,
  "result_file": "/path/to/media/results/job_1773649631615_result.json",
  "report_file": "/path/to/media/results/job_1773649631615_report.txt",
  "segments": 239,
  "audio_duration": 129061.32
}
```

**Response (Error)**:
```json
{
  "status": "error",
  "job_id": "",
  "error": "File not found: /path/to/file.mp3"
}
```

### Endpoint: `GET /api/v1/pipeline-status`

**Response**:
```json
{
  "status": "available",
  "gpu": {
    "available": true,
    "name": "NVIDIA RTX 3070 Ti",
    "memory": {
      "total_gb": 7.7,
      "free_gb": 4.2,
      "used_percent": 45.6
    }
  },
  "performance": {
    "single_file_time": "~57 seconds",
    "parallel_capacity": "5 concurrent",
    "throughput": "5.27 files/min max"
  }
}
```

---

## 🐛 Known Limitations

1. **Synchronous Processing**: Current API endpoint is blocking
   - Waits for full transcription (57s)
   - For production: Consider async with polling

2. **File Size**: Max 1GB per request
   - Typical video file: 100-500MB
   - Not a practical limitation

3. **Language**: Hardcoded to Russian (ru) by default
   - Can add language parameter if needed
   - Whisper BASE is multilingual

4. **Concurrent Tasks**: Max 5 parallel
   - Beyond 5: Model cache conflicts
   - 5 tasks = 145.95s = 5.27 files/min throughput

5. **GPU-Only**: Requires NVIDIA GPU with CUDA
   - Fallback to CPU: Not implemented yet
   - Add flag to enable if needed

---

## 🎯 Testing Checklist

- [ ] Test `/transcribe-gpu` endpoint directly with cURL
- [ ] Test pipeline status endpoint
- [ ] Test bot → file download → API call flow
- [ ] Test result parsing and formatting
- [ ] Test error handling (missing file, API down)
- [ ] Test with various file sizes (1MB, 10MB, 100MB, 500MB)
- [ ] Test with different audio formats (MP3, WAV, M4A, WebM)
- [ ] Verify result quality matches test execution
- [ ] Verify no memory leaks during concurrent tasks

---

## 📊 Performance Expectations

| Task | Time | GPU Usage | Notes |
|------|------|-----------|-------|
| Single file (21 min) | ~57s | 3.49GB | 4x faster than CPU |
| 5 concurrent files | ~146s | 3.49GB | 3.5x speedup |
| Audio prep (244MB video) | 8.56s | CPU-bound | FFmpeg processing |
| Whisper transcription (5 files) | ~48s each | GPU-bound | Parallel execution |

---

## 🔧 Recommended Changes Priority

1. **MUST HAVE** (30 min):
   - ✅ Create `/transcribe-gpu` command
   - ✅ Implement GPU handler
   - ✅ Send results to user

2. **SHOULD HAVE** (1 hour):
   - ✏️ Auto-detect based on file size
   - ✏️ User preference setting
   - ✏️ Better error messages

3. **NICE TO HAVE** (2+ hours):
   - ⏳ Async processing with polling
   - ⏳ Advanced queue management
   - ⏳ Monitoring dashboard

---

## 📞 Quick Start for Integration

**Step 1**: Verify API is running
```bash
curl http://localhost:8000/api/v1/pipeline-status
```

**Step 2**: Test with sample file
```bash
curl -X POST http://localhost:8000/api/v1/transcribe-gpu \
  -H "Content-Type: application/json" \
  -d '{
    "file_path": "/home/cyberkitty/Projects/Cyberkitty119/media/incoming/test.mp3",
    "language": "ru"
  }'
```

**Step 3**: Check result files
```bash
ls -lh /home/cyberkitty/Projects/Cyberkitty119/media/results/
```

**Step 4**: Add to bot handler (next phase)

---

## 🎉 Success Criteria

- [ ] GPU endpoint responding successfully
- [ ] Bot can send files to GPU pipeline
- [ ] Results delivered to user within 60s (including prep + transcription)
- [ ] Quality matches manual test execution
- [ ] All error cases handled gracefully
- [ ] No memory leaks after multiple runs
- [ ] GPU memory released after job completes

