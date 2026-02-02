from sqlalchemy import Column, Integer, String, DateTime, JSON, Text
from sqlalchemy import func
from .db import Base

class ProcessingJob(Base):
    __tablename__ = "processing_jobs"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=True)
    job_type = Column(String(50), nullable=False)
    status = Column(String(32), nullable=False, default="queued")
    payload = Column(JSON, nullable=True)
    progress = Column(Integer, nullable=True)
    attempts = Column(Integer, nullable=False, default=0)
    locked_by = Column(String(64), nullable=True)
    locked_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    error = Column(Text, nullable=True)

    def __repr__(self):
        return f"ProcessingJob(id={self.id}, type={self.job_type}, status={self.status})"


class Transcription(Base):
    __tablename__ = "transcriptions"

    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, nullable=False)
    user_id = Column(Integer, nullable=True)
    raw_transcript = Column(Text, nullable=True)
    formatted_transcript = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    def __repr__(self):
        return f"Transcription(id={self.id}, job_id={self.job_id})"
