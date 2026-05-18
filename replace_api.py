import re

with open("api_server.py", "r", encoding="utf-8") as f:
    content = f.read()

# 1. Insert core_transcribe_router near core_ingest_router
include_stmt = """from core_api.api.v1 import ingest as core_ingest_router
app.include_router(core_ingest_router.router, prefix="/api/v1/ingest")

from core_api.api.v1.transcribe import router as core_transcribe_router
app.include_router(core_transcribe_router, tags=["Transcription"])
"""
content = re.sub(
    r"from core_api\.api\.v1 import ingest as core_ingest_router.*?\napp\.include_router.*?\n",
    include_stmt,
    content,
    flags=re.MULTILINE
)

# 2. Delete TranscriptionResult class
content = re.sub(
    r"class TranscriptionResult\(BaseModel\):\s+task_id: str\s+filename: str\s+file_size_mb: float\s+audio_duration_minutes: float\s+raw_transcript: str\s+formatted_transcript: str\s+transcript_length: int\s+processing_time_seconds: float\s+formatted_with_llm: bool\n+",
    "",
    content,
    flags=re.MULTILINE
)

# 3. Delete @app.post("/transcribe") up to if __name__ == "__main__":
content = re.sub(
    r"@app\.post\(\"/transcribe\", response_model=TranscriptionResult\).*?if __name__ == \"__main__\":",
    'if __name__ == "__main__":',
    content,
    flags=re.DOTALL
)

with open("api_server.py", "w", encoding="utf-8") as f:
    f.write(content)

print("done")
