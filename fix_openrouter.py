import requests
import json
import base64

def test_transcribe():
    # Use same logic as openrouter.py
    audio_format = "ogg"
    with open("/home/cyberkitty/audio_2026-05-14_11-31-32.ogg", "rb") as f:
        base64_audio = base64.b64encode(f.read()).decode("utf-8")
        
    payload = {
        "model": "openai/whisper-large-v3-turbo",
        "input_audio": {
            "data": base64_audio,
            "format": audio_format
        }
    }
    
    import os
    headers = {
        "Authorization": f"Bearer {os.environ.get('OPENROUTER_API_KEY')}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://transkribator.local",
        "X-Title": "CyberKitty"
    }
    
    resp = requests.post("https://openrouter.ai/api/v1/audio/transcriptions", headers=headers, data=json.dumps(payload))
    print(resp.status_code)
    print(resp.text)

test_transcribe()
