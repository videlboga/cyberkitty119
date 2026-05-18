from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from .config import DATABASE_URL

_engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, expire_on_commit=False, bind=_engine)

def get_engine():
    return _engine

from sqlalchemy.orm import declarative_base
Base = declarative_base()
