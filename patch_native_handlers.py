import re

with open("max_bot/native_handlers.py", "r") as f:
    text = f.read()

text = text.replace(
    "def _enqueue_external_audio(user_id: int, audio_path: str, filename: str, file_size_mb: Optional[float], duration_minutes: Optional[float], source_url: Optional[str]):",
    "def _enqueue_external_audio(user_id: int, audio_path: str, filename: str, file_size_mb: Optional[float], duration_minutes: Optional[float], source_url: Optional[str], chat_id: Optional[str] = None):"
)
text = text.replace(
    '''            "source_url": source_url,
            "source_type": "external",
        },
    )''',
    '''            "source_url": source_url,
            "source_type": "external",
            "platform": "max",
            "chat_id": chat_id,
        },
    )'''
)
text = text.replace(
    "_enqueue_external_audio(user.id, str(compressed), filename, file_size_mb, duration_minutes, att.url)",
    "_enqueue_external_audio(user.id, str(compressed), filename, file_size_mb, duration_minutes, att.url, chat_id=event.chat_id)"
)
with open("max_bot/native_handlers.py", "w") as f:
    f.write(text)
print("done")
