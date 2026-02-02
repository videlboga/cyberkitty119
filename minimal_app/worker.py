import time
import logging
from .queue import acquire_job, complete_job, fail_job
from .downloader import download_file
from .transcriber import transcribe_file
from .db import SessionLocal
from .models import Transcription

logger = logging.getLogger(__name__)


def run_once(worker_id: str):
    job = acquire_job(worker_id=worker_id)
    if not job:
        return None
    logger.info(f"Worker {worker_id} processing job {job.id}")
    try:
        # download
        file_ref = (job.payload or {}).get("file_ref")
        local_path = download_file(file_ref) if file_ref else None

        # transcribe
        transcript = transcribe_file(local_path or "")

        # persist transcription (ensure we commit so the record is durable)
        with SessionLocal() as session:
            tr = Transcription(job_id=job.id, user_id=job.user_id, raw_transcript=transcript)
            session.add(tr)
            session.flush()
            session.commit()

        # mark job completed
        complete_job(job.id)
        logger.info(f"Worker {worker_id} completed job {job.id}")
        return job.id
    except Exception as e:
        logger.exception("Job failed")
        fail_job(job.id, str(e))
        return job.id


def loop(worker_id: str, *, poll_interval: float = 0.5):
    while True:
        processed = run_once(worker_id)
        if not processed:
            time.sleep(poll_interval)
