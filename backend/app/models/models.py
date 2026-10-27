from __future__ import annotations

"""
FairShift — Database models
All models use SQLAlchemy ORM with SQLite.
SECURITY: The Report model intentionally has NO user_id field.
This enforces k-anonymity at the schema level, not just the UI layer.
"""
from datetime import datetime
from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime, Text, ForeignKey
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True)  # UUID
    name = Column(String(100), nullable=False)
    role = Column(String(10), nullable=False)   # "worker" | "admin"
    industry_id = Column(String(50), nullable=False)  # "construction" | "hospital"
    site_id = Column(String(50), nullable=False, default="site_a")
    language_pref = Column(String(5), nullable=False, default="en")  # "en"|"hi"|"ta"
    password_hash = Column(String(200), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    shifts = relationship("Shift", back_populates="user", cascade="all, delete-orphan")


class Shift(Base):
    __tablename__ = "shifts"

    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    industry_id = Column(String(50), nullable=False)
    shift_type = Column(String(30), nullable=False)   # e.g. "day", "morning"
    check_in_time = Column(DateTime, nullable=True)
    check_out_time = Column(DateTime, nullable=True)
    duration_hours = Column(Float, nullable=True)     # computed on checkout
    overtime_hours = Column(Float, default=0.0)       # hours beyond threshold
    gross_pay = Column(Float, nullable=True)          # computed on checkout
    pay_breakdown = Column(Text, nullable=True)       # JSON string with breakdown
    site_id = Column(String(50), nullable=False, default="site_a")
    is_active = Column(Boolean, default=True)         # True = not yet checked out
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="shifts")


class Report(Base):
    """
    Anonymous safety & grievance reports.
    CRITICAL: No user_id column — intentional by design.
    This table must NEVER be joined to the users table.
    Individual reports stay unattributed; only aggregated (surfaced)
    reports are shown to admins once threshold k is reached.
    """
    __tablename__ = "reports"

    id = Column(String(36), primary_key=True)
    industry_id = Column(String(50), nullable=False)
    site_id = Column(String(50), nullable=False)
    report_type = Column(String(20), nullable=False)  # "safety" | "grievance"
    category = Column(String(50), nullable=False)     # from industry config
    description = Column(Text, nullable=True)
    window_key = Column(String(100), nullable=False)  # "industry:site:category:week"
    is_surfaced = Column(Boolean, default=False)      # True once k threshold reached
    created_at = Column(DateTime, default=datetime.utcnow)


class RiskScore(Base):
    """
    Explainable cohort-level risk scores.
    Scores are per (industry_id, site_id) cohort — never per individual worker.
    reasons is a JSON array of human-readable contributing factors.
    """
    __tablename__ = "risk_scores"

    id = Column(String(36), primary_key=True)
    industry_id = Column(String(50), nullable=False)
    site_id = Column(String(50), nullable=False)
    score = Column(Float, nullable=False)             # 0–100
    risk_level = Column(String(10), nullable=False)   # "low"|"medium"|"high"
    reasons = Column(Text, nullable=False)            # JSON array of strings
    computed_at = Column(DateTime, default=datetime.utcnow)
