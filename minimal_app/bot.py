"""Minimal bot stub: receives a 'file' and enqueues a transcribe job."""
from .queue import enqueue_job


def handle_upload(user_id: int, file_ref: str):
    payload = {"file_ref": file_ref}
    job = enqueue_job(user_id=user_id, job_type="transcribe", payload=payload)
    return job
