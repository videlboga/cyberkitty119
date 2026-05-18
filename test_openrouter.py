import requests
import base64
import json
import os

api_key = os.getenv("OPENROUTER_API_KEY")

with open("/home/cyberkitty/audio_2026-05-14_11-31-32.ogg", "rb") as f:
  base64_audio = base64.b64encode(f.read()).decode("utf-8")

response = requests.post(
  url="https://openrouter.ai/api/v1/audio/transcriptions",
  headers={
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json",
  },
  data=json.dumps({
    "model": "openai/whisper-large-v3-turbo",
    "input_audio": {
      "data": base64_audio,
      "format": "ogg"
    }
  })
)

print(response.status_code)
print(response.text)
