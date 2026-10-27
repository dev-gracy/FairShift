"""
FairShift — Database session and engine configuration
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    # On Vercel / AWS Lambda, root directory is read-only; use /tmp for SQLite
    if os.getenv("VERCEL") or os.path.exists("/var/task"):
        DATABASE_URL = "sqlite:////tmp/fairshift.db"
    else:
        DATABASE_URL = "sqlite:///./fairshift.db"
elif DATABASE_URL.startswith("postgres://"):
    # SQLAlchemy requires postgresql:// instead of postgres://
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# SQLite: check_same_thread=False required for multi-threaded FastAPI
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """FastAPI dependency for database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
