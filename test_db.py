import os
import sys
import json
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from transkribator_modules.config import DATABASE_URL
from transkribator_modules.db.models import ProcessingJob

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
db = SessionLocal()
job = db.query(ProcessingJob).order_by(ProcessingJob.id.desc()).first()
if job:
    print(f"JobID: {job.id}")
    print(json.dumps(job.payload, indent=2))
    print(job.status)
else:
    print("No jobs found")
