#!/usr/bin/env python3
"""
End-to-End System Test: Direct GPU Worker Processing
Tests the complete pipeline without going through Telegram bot.
"""

import sys
import os
from pathlib import Path
from datetime import datetime

# Add project to path
sys.path.insert(0, '/home/cyberkitty/Projects/Cyberkitty119')

# Set required env vars for testing
os.environ['DATABASE_URL'] = os.environ.get('DATABASE_URL', 'sqlite:///test_jobs.db')
os.environ['LOG_LEVEL'] = 'DEBUG'
os.environ['JOB_POLL_INTERVAL'] = '1'

from transkribator_modules.config import logger
from transkribator_modules.db import init_db
from transkribator_modules.db.models import ProcessingJob, User
from transkribator_modules.db.database import SessionLocal, init_database
from transkribator_modules.jobs.media import (
    MediaJobPayload, 
    enqueue_media_job,
    process_media_gpu_job
)
from transkribator_modules.jobs.pipeline import (
    MediaPipelineContext,
    run_media_pipeline,
)
from transkribator_modules.jobs.stages import (
    PrepareEnvironmentStage,
    DownloadMediaStage,
    TranscribeMediaGPUStage,
    FinalizeNoteStage,
    DeliverResultsStage,
    CleanupStage,
)
from transkribator_modules.jobs.services import (
    default_prepare_environment,
    default_download_media,
    default_transcribe_media_gpu,
    default_finalize_note,
    default_deliver_results,
    default_cleanup,
    MediaPipelineServices,
)
from transkribator_modules.jobs.progress import JobNotifier


def print_header(text: str):
    """Print formatted header."""
    print("\n" + "=" * 80)
    print(f"  {text}")
    print("=" * 80)


def setup_test_environment():
    """Initialize database and create test user."""
    print_header("SETUP: Initializing Test Environment")
    
    try:
        init_database()
        logger.info("✓ Database initialized")
    except Exception as e:
        logger.warning(f"Database already initialized or warning: {e}")
    
    # Create test user
    db = SessionLocal()
    try:
        test_user = db.query(User).filter(User.id == 9999).first()
        if not test_user:
            test_user = User(
                id=9999,
                telegram_id=9999999,
                username="test_user",
                first_name="Test",
                last_name="User",
            )
            db.add(test_user)
            db.commit()
            logger.info("✓ Test user created (ID: 9999)")
        else:
            logger.info("✓ Test user already exists (ID: 9999)")
    except Exception as e:
        logger.error(f"Failed to create test user: {e}")
        db.rollback()
    finally:
        db.close()


def create_test_media_job(media_file: Path) -> ProcessingJob:
    """Create a media job in the queue."""
    print_header("STEP 1: Creating Media Job in Queue")
    
    if not media_file.exists():
        logger.error(f"❌ Media file not found: {media_file}")
        sys.exit(1)
    
    file_size_mb = media_file.stat().st_size / 1024**2
    logger.info(f"Media file: {media_file.name} ({file_size_mb:.1f} MB)")
    
    # Create job payload
    payload = MediaJobPayload(
        file_id=f"test_file_{datetime.now().timestamp()}",
        message_id=None,
        file_unique_id=None,
        note_id=None,
        extra={
            "audio_path": str(media_file),  # Pre-downloaded path
            "source": "direct_test",
        }
    )
    
    # Enqueue job
    job = enqueue_media_job(
        user_id=9999,
        payload=payload,
    )
    
    logger.info(f"✓ Job created: ID={job.id}, type={job.job_type}, status={job.status}")
    return job


def execute_gpu_pipeline(job: ProcessingJob) -> dict:
    """Execute GPU pipeline directly (simulate worker)."""
    print_header("STEP 2: Executing GPU Pipeline")
    
    logger.info(f"Processing job ID={job.id}, type={job.job_type}")
    
    try:
        # Call the GPU job handler directly
        process_media_gpu_job(job)
        logger.info(f"✓ Job completed successfully")
        return {"status": "success", "job_id": job.id}
    except Exception as e:
        logger.error(f"❌ Job failed: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "failed", "job_id": job.id, "error": str(e)}


def check_results(job_id: int):
    """Check job results in database."""
    print_header("STEP 3: Checking Results")
    
    db = SessionLocal()
    try:
        job = db.query(ProcessingJob).filter(ProcessingJob.id == job_id).first()
        if not job:
            logger.error(f"❌ Job not found in database")
            return
        
        logger.info(f"Job Status: {job.status}")
        logger.info(f"Job Type: {job.job_type}")
        logger.info(f"User ID: {job.user_id}")
        logger.info(f"Payload: {job.payload}")
        
        if job.status == "succeeded":
            logger.info("✅ Job succeeded!")
        elif job.status == "failed":
            logger.error(f"❌ Job failed: {job.error_message}")
        else:
            logger.warning(f"⚠️  Job status: {job.status}")
    
    finally:
        db.close()


def main():
    """Main test function."""
    print_header("🚀 END-TO-END SYSTEM TEST (GPU Worker Pipeline)")
    
    # Check for test media file
    media_file = Path("/home/cyberkitty/Загрузки/Запись встречи 13.03.2026 10-28-31 - запись.webm")
    
    if not media_file.exists():
        # Try alternative paths
        alternatives = [
            Path("/home/cyberkitty/Projects/Cyberkitty119/sample.wav"),
            Path("/home/cyberkitty/Projects/Cyberkitty119/sample_mono_16k.wav"),
            Path("/home/cyberkitty/Projects/Cyberkitty119/tone.wav"),
        ]
        
        for alt_file in alternatives:
            if alt_file.exists():
                media_file = alt_file
                break
        
        if not media_file.exists():
            logger.error("❌ No test media file found!")
            logger.error(f"Expected: {alternatives[0]}")
            print("\nTo run this test, provide a media file:")
            print(f"  python3 test_gpu_system.py /path/to/media.mp3")
            sys.exit(1)
    
    try:
        # Setup
        setup_test_environment()
        
        # Step 1: Create job
        job = create_test_media_job(media_file)
        
        # Step 2: Execute GPU pipeline
        result = execute_gpu_pipeline(job)
        
        # Step 3: Check results
        check_results(job.id)
        
        # Summary
        print_header("TEST SUMMARY")
        if result["status"] == "success":
            print("✅ TEST PASSED: GPU pipeline executed successfully!")
            print(f"\nJob Details:")
            print(f"  - Job ID: {result['job_id']}")
            print(f"  - Status: SUCCESS")
            print(f"  - Check database for results")
        else:
            print("❌ TEST FAILED: GPU pipeline encountered error")
            print(f"\nError: {result.get('error')}")
        
    except Exception as e:
        logger.exception("Test failed with exception")
        print_header("TEST FAILED")
        print(f"❌ {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
