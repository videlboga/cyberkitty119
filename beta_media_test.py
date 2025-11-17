import asyncio
import tempfile
from pathlib import Path
import subprocess
import requests
import yt_dlp
import gdown

from transkribator_modules.db.database import SessionLocal, UserService
from transkribator_modules.db.models import NoteStatus
from transkribator_modules.beta.content_processor import ContentProcessor
from transkribator_modules.transcribe.transcriber_v4 import transcribe_audio

USER_TELEGRAM_ID = 648981358
USER_USERNAME = "Like_a_duck"
USER_FIRST_NAME = "QA"
USER_LAST_NAME = "Tester"

WORKSPACE_PREFIX = "beta_media_test_"

FORWARDED_AUDIO_URL = "https://github.com/Jakobovski/free-spoken-digit-dataset/blob/master/recordings/0_jackson_0.wav?raw=1"
FORWARDED_CAPTION = "Forwarded voice note about the marketing call summary"

VIDEO_SOURCES = [
    {
        "label": "direct_http",
        "url": "https://filesamples.com/samples/video/mp4/sample_640x360.mp4",
        "type": "http",
    },
    {
        "label": "gdrive",
        "url": "https://drive.google.com/uc?id=1Mfd0pniS3pSkeCZMt2rt7NmBGG99nmCa&confirm=t",
        "type": "gdrive",
    },
    {
        "label": "youtube",
        "url": "https://www.youtube.com/watch?v=2Vf1D-rUMwE",
        "type": "youtube",
    },
]


def download_file(url: str, dest: Path) -> Path:
    if dest.exists():
        dest.unlink()
    print(f"HTTP download {url}")
    with requests.get(url, stream=True, timeout=60) as response:
        response.raise_for_status()
        with open(dest, "wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 256):
                if chunk:
                    handle.write(chunk)
    return dest


def download_gdrive(url: str, dest: Path) -> Path:
    if dest.exists():
        dest.unlink()
    print(f"gdown download {url}")
    gdown.download(url, str(dest), quiet=False)
    return dest


def download_youtube(url: str, dest: Path) -> Path:
    if dest.exists():
        dest.unlink()
    print(f"yt_dlp download {url}")
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": str(dest),
        "quiet": True,
        "no_warnings": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
    if dest.exists():
        return dest
    for file in dest.parent.glob(dest.name + ".*"):
        return file
    raise FileNotFoundError("YouTube download failed")


def convert_to_wav(input_path: Path) -> Path:
    output_path = input_path.with_suffix(".wav")
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-ac",
        "1",
        "-ar",
        "16000",
        str(output_path),
    ]
    print(f"Running ffmpeg {' '.join(cmd)}")
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return output_path


def cleanup_workspace(path: Path) -> None:
    for item in sorted(path.glob("**/*"), reverse=True):
        try:
            if item.is_file() or item.is_symlink():
                item.unlink()
            elif item.is_dir():
                item.rmdir()
        except FileNotFoundError:
            continue
    try:
        path.rmdir()
    except Exception:
        pass


async def transcribe_and_store(user, audio_path: Path, description: str, note_caption: str, tags=None):
    print(f"Transcribing {description}: {audio_path}")
    transcript = await transcribe_audio(str(audio_path))
    if not transcript:
        print(f"⚠️ Transcript empty for {description}")
        text_content = note_caption
    else:
        text_content = f"{note_caption}\n\n{transcript.strip()}"
    processor = ContentProcessor()
    result = await processor.process(
        user,
        text=text_content,
        type_hint="media",
        preset=None,
        status=NoteStatus.INGESTED.value,
        tags=tags or [],
        summary=note_caption,
    )
    note_id = result.get("note_id")
    print(f"✅ Created/updated note #{note_id} for {description}")
    return note_id, transcript


async def main():
    session = SessionLocal()
    user_service = UserService(session)
    user = user_service.get_or_create_user(
        telegram_id=USER_TELEGRAM_ID,
        username=USER_USERNAME,
        first_name=USER_FIRST_NAME,
        last_name=USER_LAST_NAME,
    )
    print(f"Using user id {user.id}")

    workspace = Path(tempfile.mkdtemp(prefix=WORKSPACE_PREFIX))
    print(f"Workspace: {workspace}")

    created_notes = []

    try:
        forwarded_path = workspace / "forwarded_note.mp3"
        print(f"Downloading forwarded audio to {forwarded_path}")
        download_file(FORWARDED_AUDIO_URL, forwarded_path)
        forwarded_wav = convert_to_wav(forwarded_path)
        note_id, transcript = await transcribe_and_store(
            user,
            forwarded_wav,
            "forwarded_audio_with_caption",
            FORWARDED_CAPTION,
            tags=["forwarded", "audio"],
        )
        created_notes.append(("forwarded_audio", note_id, len(transcript or "")))

        for item in VIDEO_SOURCES:
            label = item["label"]
            url = item["url"]
            target = workspace / f"{label}.mp4"
            print(f"\nDownloading video ({label}) from {url}")
            try:
                if item["type"] == "http":
                    download_file(url, target)
                elif item["type"] == "gdrive":
                    download_gdrive(url, target)
                elif item["type"] == "youtube":
                    downloaded = download_youtube(url, target)
                    target = downloaded
                else:
                    raise ValueError(f"Unknown type {item['type']}")
            except Exception as exc:
                print(f"❌ Failed to download {label}: {exc}")
                continue

            try:
                audio_path = convert_to_wav(target)
            except subprocess.CalledProcessError as exc:
                print(f"❌ ffmpeg failed for {label}: {exc}")
                continue

            caption = f"Автообработка видео ({label})"
            note_id, transcript = await transcribe_and_store(
                user,
                audio_path,
                f"video_source_{label}",
                caption,
                tags=["video", label],
            )
            created_notes.append((label, note_id, len(transcript or "")))

        print("\nSummary:")
        for label, note_id, length in created_notes:
            print(f" - {label}: note #{note_id}, transcript length {length}")
    finally:
        cleanup_workspace(workspace)
        session.close()

if __name__ == "__main__":
    asyncio.run(main())
