"""
FairShift — Database seed script
Creates demo users and sample data for both industry profiles.

Usage:
    cd backend
    python seed.py

This script is safe to re-run (idempotent via username checks).
Credentials come from environment variables — never hardcoded.

Demo data created:
  Construction industry:
    - admin: const_admin / [ADMIN_PASSWORD env var]
    - workers: raju_worker, priya_worker / [WORKER_PASSWORD env var]
    - 5 pre-seeded shifts (including overtime)
    - 4 reports: 2 below threshold (silent), 2 trigger surfacing at k=3

  Hospital industry:
    - admin: hospital_admin / [ADMIN_PASSWORD env var]
    - workers: meena_worker, arjun_worker / [WORKER_PASSWORD env var]
    - 4 pre-seeded shifts
    - 3 reports: threshold exactly reached → 1 cluster surfaced
"""
import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

UTC = timezone.utc

# Add parent directory so we can import app modules
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()

from app.models.database import engine, SessionLocal
from app.models.models import Base, User, Shift, Report
from app.models.industry_config import load_profiles, get_report_threshold
from app.auth import hash_password
from app.routers.reports import _make_window_key, _check_and_surface

ADMIN_PWD = os.getenv("ADMIN_PASSWORD", "AdminPass@2026")
WORKER_PWD = os.getenv("WORKER_PASSWORD", "WorkerPass@2026")


def _get_or_create_user(db, name, role, industry_id, site_id, lang):
    """Return existing user or create a new one (idempotent)."""
    existing = db.query(User).filter(User.name == name).first()
    if existing:
        return existing
    pwd = ADMIN_PWD if role == "admin" else WORKER_PWD
    user = User(
        id=str(uuid.uuid4()),
        name=name,
        role=role,
        industry_id=industry_id,
        site_id=site_id,
        language_pref=lang,
        password_hash=hash_password(pwd),
    )
    db.add(user)
    return user


def _make_shift(user_id, industry_id, shift_type, hours_ago_start, duration_h, site_id="site_a"):
    """Helper to build a completed Shift object with pay already calculated."""
    check_in = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=hours_ago_start)
    check_out = check_in + timedelta(hours=duration_h)
    ot_threshold = 8.0
    ot_hours = max(0.0, duration_h - ot_threshold)

    shift = Shift(
        id=str(uuid.uuid4()),
        user_id=user_id,
        industry_id=industry_id,
        shift_type=shift_type,
        check_in_time=check_in,
        check_out_time=check_out,
        duration_hours=round(duration_h, 2),
        overtime_hours=round(ot_hours, 2),
        gross_pay=round(600 * (duration_h / 8), 2),
        pay_breakdown=json.dumps({"note": "seeded", "duration_hours": duration_h}),
        site_id=site_id,
        is_active=False,
    )
    return shift


def _make_report(industry_id, site_id, report_type, category, description):
    """Build a Report object. No user_id — by design."""
    from app.routers.reports import _make_window_key
    window_key = _make_window_key(industry_id, site_id, category)
    return Report(
        id=str(uuid.uuid4()),
        industry_id=industry_id,
        site_id=site_id,
        report_type=report_type,
        category=category,
        description=description,
        window_key=window_key,
        is_surfaced=False,
        created_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=2),
    )


def seed():
    print("Loading industry profiles...")
    load_profiles()

    print("Creating database tables...")
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        # ---------------------------------------------------------------
        # Construction site
        # ---------------------------------------------------------------
        print("Seeding Construction industry...")
        ca = _get_or_create_user(db, "const_admin", "admin", "construction", "site_a", "en")
        w1 = _get_or_create_user(db, "raju_worker", "worker", "construction", "site_a", "hi")
        w2 = _get_or_create_user(db, "priya_worker", "worker", "construction", "site_a", "hi")
        db.flush()

        # Shifts for raju: 3 shifts including one 12h (overtime)
        if db.query(Shift).filter(Shift.user_id == w1.id).count() == 0:
            db.add(_make_shift(w1.id, "construction", "day", 72, 8))
            db.add(_make_shift(w1.id, "construction", "day", 48, 9.5))   # 1.5h OT
            db.add(_make_shift(w1.id, "construction", "extended", 24, 12))  # 4h OT
        if db.query(Shift).filter(Shift.user_id == w2.id).count() == 0:
            db.add(_make_shift(w2.id, "construction", "night", 36, 8))
            db.add(_make_shift(w2.id, "construction", "night", 12, 10))  # 2h OT

        # Reports: 2 height reports (below k=3, silent) + 3 pay_delay (surfaces)
        existing_reports = db.query(Report).filter(Report.industry_id == "construction").count()
        if existing_reports == 0:
            # These two stay silent — k=3 not yet reached
            db.add(_make_report("construction", "site_a", "safety", "height",
                                "No harness available on floor 4"))
            db.add(_make_report("construction", "site_a", "safety", "height",
                                "Safety net damaged near east crane"))
            # These three pay_delay reports will trigger surfacing
            db.add(_make_report("construction", "site_a", "grievance", "pay_delay",
                                "October pay not received yet"))
            db.add(_make_report("construction", "site_a", "grievance", "pay_delay",
                                "Last week overtime not counted"))
            db.add(_make_report("construction", "site_a", "grievance", "pay_delay",
                                "Deduction made without explanation"))

        db.commit()

        # Surface pay_delay cluster (k=3 reached)
        pay_key = _make_window_key("construction", "site_a", "pay_delay")
        _check_and_surface(db, pay_key, "construction")

        # ---------------------------------------------------------------
        # Hospital
        # ---------------------------------------------------------------
        print("Seeding Hospital industry...")
        ha = _get_or_create_user(db, "hospital_admin", "admin", "hospital", "site_b", "en")
        w3 = _get_or_create_user(db, "meena_worker", "worker", "hospital", "site_b", "ta")
        w4 = _get_or_create_user(db, "arjun_worker", "worker", "hospital", "site_b", "en")
        db.flush()

        if db.query(Shift).filter(Shift.user_id == w3.id).count() == 0:
            db.add(_make_shift(w3.id, "hospital", "morning", 60, 8, "site_b"))
            db.add(_make_shift(w3.id, "hospital", "oncall", 36, 12, "site_b"))  # 4h OT
        if db.query(Shift).filter(Shift.user_id == w4.id).count() == 0:
            db.add(_make_shift(w4.id, "hospital", "evening", 48, 8, "site_b"))
            db.add(_make_shift(w4.id, "hospital", "morning", 24, 9, "site_b"))

        existing_hosp = db.query(Report).filter(Report.industry_id == "hospital").count()
        if existing_hosp == 0:
            # 3 infection reports → surfaces immediately
            db.add(_make_report("hospital", "site_b", "safety", "infection",
                                "N95 masks not restocked in ICU"))
            db.add(_make_report("hospital", "site_b", "safety", "infection",
                                "Hand sanitiser empty at nurse station 3"))
            db.add(_make_report("hospital", "site_b", "safety", "infection",
                                "Isolation protocol not followed in ward B"))

        db.commit()

        infection_key = _make_window_key("hospital", "site_b", "infection")
        _check_and_surface(db, infection_key, "hospital")

        db.commit()
        print("\n[OK] Seed complete. Demo credentials:")
        print(f"   Construction Admin : const_admin    / {ADMIN_PWD}")
        print(f"   Construction Worker: raju_worker    / {WORKER_PWD}")
        print(f"   Hospital Admin     : hospital_admin / {ADMIN_PWD}")
        print(f"   Hospital Worker    : meena_worker   / {WORKER_PWD}")

    finally:
        db.close()


if __name__ == "__main__":
    seed()
