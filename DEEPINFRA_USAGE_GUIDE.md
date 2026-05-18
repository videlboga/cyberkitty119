# DeepInfra Whisper API - Usage Guide

## Quick Start

### 1. Installation

```bash
pip install requests openai-whisper
```

### 2. Environment Setup

```bash
export DEEPINFRA_API_KEY="sk-..."
export DEEPINFRA_LANGUAGE="ru"  # Russian
export DEEPINFRA_TASK="transcribe"
export DEEPINFRA_TEMPERATURE="0"
```

### 3. Basic Usage

```python
from transcribe_client.deepinfra import DeepInfraAdapter

# Create adapter
adapter = DeepInfraAdapter()

# Transcribe audio file
result = adapter.transcribe('/path/to/audio.mp3')

# Use result
print(result['text'])  # Transcribed text
print(result['meta']['provider'])  # 'deepinfra' or 'local_whisper'
print(result['segments'])  # Detailed segments with timing
```

## Response Structure

```python
{
    "status": "ok",
    "text": "Полный транскрибированный текст",
    "segments": [
        {
            "id": 0,
            "start": 0.0,
            "end": 5.2,
            "text": "Первый сегмент",
            "tokens": [...],
            "temperature": 0.0,
            "avg_logprob": -0.523,
            "compression_ratio": 1.2,
            "no_speech_prob": 0.001
        },
        ...
    ],
    "model": "openai/whisper-large-v3-turbo",
    "meta": {
        "file_uri": "/path/to/audio.mp3",
        "provider": "deepinfra",  # or "local_whisper" if fallback
        "ts": 1234567890.123,
        "mode": null
    }
}
```

## Provider Selection

The adapter automatically:

1. **Tries DeepInfra first** (faster, remote)
2. **Retries once** if timeout (waits 1-2 seconds)
3. **Falls back to local Whisper** if DeepInfra fails (slower, local)

You can see which provider was used from `result['meta']['provider']`:

```python
if result['meta']['provider'] == 'deepinfra':
    print("✓ Used remote DeepInfra API")
else:
    print("⚠ Used local Whisper (DeepInfra unavailable)")
```

## Error Handling

```python
try:
    result = adapter.transcribe('audio.mp3')
except FileNotFoundError:
    print("Audio file not found")
except Exception as e:
    print(f"Transcription failed: {e}")
```

## Configuration Options

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DEEPINFRA_API_KEY` | (required) | Your API key |
| `DEEPINFRA_MODEL` | `openai/whisper-large-v3-turbo` | Model to use |
| `DEEPINFRA_TASK` | `transcribe` | Task type |
| `DEEPINFRA_LANGUAGE` | `ru` | Language code |
| `DEEPINFRA_TEMPERATURE` | `0` | Temperature (0=deterministic) |
| `DEEPINFRA_REQUEST_TIMEOUT_SEC` | `1800` | Timeout in seconds (30min) |

### Programmatic Configuration

```python
adapter = DeepInfraAdapter(
    api_key="sk-...",
    model="openai/whisper-large-v3-turbo",
    request_timeout=(60, 300)  # (connect_timeout, read_timeout)
)
```

## Supported Languages

The adapter is configured for Russian (`ru`), but supports any language:

```python
# Transcribe English
adapter = DeepInfraAdapter()
# Change language via environment or directly in code
os.environ['DEEPINFRA_LANGUAGE'] = 'en'
result = adapter.transcribe('english_audio.mp3')
```

Supported codes: `en`, `ru`, `es`, `fr`, `de`, `ja`, `zh`, etc.

## Performance Tips

### For Faster Results
- Use **shorter audio clips** (under 1 minute)
- Ensure **good internet connection**
- Use **MP3 format** (most optimized)
- Keep **background noise low**

### For Better Accuracy
- Use **higher quality audio** (44.1kHz, 16-bit)
- Use **English or major languages** (better training data)
- Split **long recordings** into segments
- Use **clear speech** without overlaps

### For Cost Optimization
- **Batch processing**: Process multiple files in parallel
- **Monitor fallbacks**: Log when local Whisper is used (saves API cost)
- **Compress audio**: Reduce file size (64kbps MP3 is good)

## Troubleshooting

### "DEEPINFRA_API_KEY is required"
```bash
# Make sure API key is set
export DEEPINFRA_API_KEY="sk-xxxxx"
echo $DEEPINFRA_API_KEY  # Verify
```

### "whisper library not installed"
```bash
pip install openai-whisper
```

### "Failed to load audio"
Make sure ffmpeg is installed:
```bash
# Ubuntu/Debian
sudo apt-get install ffmpeg

# Arch
sudo pacman -S ffmpeg

# macOS
brew install ffmpeg
```

### Slow transcription (30+ seconds)
This likely means you're using the fallback local Whisper:
- Check logs for `[WARNING] DeepInfra failed`
- Verify internet connection
- Check DeepInfra API status

### Empty result (no text)
Could be:
- Audio is silence or white noise
- Language detection failed
- File is corrupted

## Logging

Enable logging to see what's happening:

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Now run
result = adapter.transcribe('audio.mp3')
```

You'll see:
```
[*] Retry 1/1...
[*] DeepInfra timeout/connection error (attempt 1), retrying in 1s...
[WARNING] DeepInfra failed after 2 attempts, falling back to local Whisper...
[*] Loading local Whisper model (size=base)...
[*] Transcribing audio.mp3 with local Whisper...
```

## Testing

Run comprehensive test suite:

```bash
python3 test_deepinfra_adapter.py
```

Expected output:
```
======================================================================
✅ ALL TESTS PASSED - Ready for production!
======================================================================
```

## Common Use Cases

### 1. Transcribe User-Uploaded Audio
```python
@app.route('/transcribe', methods=['POST'])
def transcribe_audio():
    file = request.files['audio']
    file.save('temp.mp3')
    
    adapter = DeepInfraAdapter()
    result = adapter.transcribe('temp.mp3')
    
    return {
        'text': result['text'],
        'provider': result['meta']['provider']
    }
```

### 2. Batch Process Audio Files
```python
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

adapter = DeepInfraAdapter()
audio_files = list(Path('/audio').glob('*.mp3'))

def transcribe(file):
    return adapter.transcribe(str(file))

with ThreadPoolExecutor(max_workers=3) as executor:
    results = list(executor.map(transcribe, audio_files))
```

### 3. Monitor Provider Usage
```python
import json

adapter = DeepInfraAdapter()
result = adapter.transcribe('audio.mp3')

log_entry = {
    'timestamp': result['meta']['ts'],
    'provider': result['meta']['provider'],
    'file': result['meta']['file_uri'],
    'text_length': len(result['text'])
}

print(json.dumps(log_entry))
```

## Support

For issues or questions:
1. Check `DEEPINFRA_FIX_REPORT.md` for technical details
2. Review logs for error messages
3. Run `test_deepinfra_adapter.py` to verify setup
4. Check [DeepInfra documentation](https://deepinfra.com/docs)

---

**Last Updated**: 2024-11-06  
**Status**: Production Ready
