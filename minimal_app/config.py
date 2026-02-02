import os

DATABASE_URL = os.environ.get("MINIMAL_DATABASE_URL", "sqlite:///./minimal.db")
JOB_LOCK_TIMEOUT_SECONDS = int(os.environ.get("MINIMAL_JOB_LOCK_TIMEOUT_SECONDS", "600"))
