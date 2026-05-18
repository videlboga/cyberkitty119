import os
import sys
import json
from dotenv import load_dotenv

# Load env file to get OPENROUTER_API_KEY
load_dotenv(".env")
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from transcribe_client import TranscribeClient

print("Using OPENROUTER_API_KEY:", os.getenv("OPENROUTER_API_KEY")[:10] + "...")

client = TranscribeClient(default_mode="openrouter")
print(f"Adapter: {type(client._adapter).__name__}")
print(f"Model configured: {client._adapter.model}")
print(f"Sending audio chunk (test_audio.ogg) to OpenRouter...")

try:
    res = client.transcribe("test_audio.ogg")
    
    print("\n--- Result ---")
    print("Status:", res.get("status"))
    print("Model:", res.get("model"))
    print("\nText snippet:")
    print("=" * 40)
    print(res.get("text", "")[:1000])
    print("=" * 40)
    
except Exception as e:
    print(f"Error: {e}")
