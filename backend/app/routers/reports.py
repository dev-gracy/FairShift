"""
FairShift — Anonymous reporting router
Feature F2: Threshold-gated k-anonymous safety & grievance reports.

DESIGN INVARIANT:
- Reports are stored with NO user_id (enforced at schema level in models.py)
- Reports are silently aggregated; admin sees NOTHING below threshold k
- Only when k independent reports on the same (category, site, week) arrive
  does is_surfaced flip to True and appear on the admin dashboard
- A single worker cannot be identified from a surfaced report cluster
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

UTC = timezone.utc

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_admin, require_worker
from app.models.database import get_db
from app.models.models import Report, User
from app.models.industry_config import get_report_threshold, get_profile

router = APIRouter(prefix="/reports", tags=["reports"])


def _make_window_key(industry_id: str, site_id: str, category: str) -> str:
    """
    Create a weekly window key for threshold grouping.
    Format: "industry:site:category:YYYY-WNN"
    Reports in the same week+site+category group together.
    """
    now = datetime.now(UTC)
    week_str = now.strftime("%Y-W%W")
    return f"{industry_id}:{site_id}:{category}:{week_str}"


def _check_and_surface(db: Session, window_key: str, industry_id: str) -> bool:
    """
    Count reports in this window. If count >= threshold k, surface all of them.
    Returns True if surfaced in this call.
    """
    threshold = get_report_threshold(industry_id)
    count = db.query(func.count(Report.id)).filter(
        Report.window_key == window_key
    ).scalar()

    if count >= threshold:
        # Surface all reports in this window (they were held silently until now)
        db.query(Report).filter(
            Report.window_key == window_key,
            Report.is_surfaced == False  # noqa: E712
        ).update({"is_surfaced": True})
        db.commit()
        return True
    return False


class ReportRequest(BaseModel):
    report_type: str       # "safety" | "grievance"
    category: str          # from industry config hazard/grievance categories
    description: str = ""  # optional — voice transcript or typed text
    site_id: str = "site_a"


class ReportResponse(BaseModel):
    message: str
    report_id: str
    is_surfaced: bool


@router.post("/submit", response_model=ReportResponse)
def submit_report(
    req: ReportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_worker),
):
    """
    Submit an anonymous safety or grievance report.
    The current user's identity is NOT stored with the report.
    """
    profile = get_profile(current_user.industry_id)
    if not profile:
        raise HTTPException(status_code=400, detail="Invalid industry profile")

    if req.report_type not in ("safety", "grievance"):
        raise HTTPException(status_code=400, detail="report_type must be 'safety' or 'grievance'")

    window_key = _make_window_key(current_user.industry_id, req.site_id, req.category)

    report = Report(
        id=str(uuid.uuid4()),
        industry_id=current_user.industry_id,
        site_id=req.site_id,
        report_type=req.report_type,
        category=req.category,
        description=req.description[:1000] if req.description else "",  # cap length
        window_key=window_key,
        is_surfaced=False,
        created_at=datetime.now(UTC).replace(tzinfo=None),
        # NOTE: No user_id stored — intentional k-anonymity design
    )
    db.add(report)
    db.commit()

    # Check threshold and surface if reached
    surfaced = _check_and_surface(db, window_key, current_user.industry_id)

    return ReportResponse(
        report_id=report.id,
        message=(
            "Report recorded. It will surface to your admin once enough colleagues "
            "report the same issue — your identity is never shared."
        ),
        is_surfaced=surfaced,
    )


@router.get("/surfaced")
def get_surfaced_reports(
    industry_id: str = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Admin-only: Return all surfaced (threshold-reached) reports.
    Only aggregated information is returned — no individual user data.
    """
    query = db.query(Report).filter(Report.is_surfaced == True)  # noqa: E712
    if industry_id:
        query = query.filter(Report.industry_id == industry_id)
    else:
        query = query.filter(Report.industry_id == current_user.industry_id)

    reports = query.order_by(Report.created_at.desc()).all()

    # Group by window_key to show cluster counts
    clusters: dict = {}
    for r in reports:
        key = r.window_key
        if key not in clusters:
            parts = key.split(":")
            clusters[key] = {
                "window_key": key,
                "industry_id": r.industry_id,
                "site_id": r.site_id,
                "category": r.category,
                "report_type": r.report_type,
                "week": parts[-1] if len(parts) >= 4 else "unknown",
                "report_count": 0,
                "sample_descriptions": [],
                "first_reported": r.created_at.isoformat(),
            }
        clusters[key]["report_count"] += 1
        if len(clusters[key]["sample_descriptions"]) < 3 and r.description:
            clusters[key]["sample_descriptions"].append(r.description)

    return {
        "surfaced_clusters": list(clusters.values()),
        "total_clusters": len(clusters),
        "threshold_info": "Reports only appear here after the minimum anonymity threshold is reached",
    }


@router.get("/count-pending")
def count_pending(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Admin: Count of reports still below threshold (not surfaced)."""
    count = db.query(func.count(Report.id)).filter(
        Report.industry_id == current_user.industry_id,
        Report.is_surfaced == False  # noqa: E712
    ).scalar()
    threshold = get_report_threshold(current_user.industry_id)
    return {
        "pending_count": count,
        "threshold": threshold,
        "message": f"These reports are held silently until {threshold} are received for the same issue.",
    }
