"""
FairShift — Shift tracking router
Feature F1: Config-driven shift check-in/check-out with automatic pay calculation.
The pay formula reads from industry_profiles.json, not hardcoded logic.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
UTC = timezone.utc
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_worker
from app.models.database import get_db
from app.models.models import User, Shift
from app.models.industry_config import get_profile

router = APIRouter(prefix="/shifts", tags=["shifts"])


class CheckInRequest(BaseModel):
    shift_type: str           # e.g. "day", "morning", "oncall"
    site_id: Optional[str] = "site_a"


class CheckInResponse(BaseModel):
    shift_id: str
    message: str
    shift_label: str
    check_in_time: str


class CheckOutResponse(BaseModel):
    shift_id: str
    duration_hours: float
    overtime_hours: float
    gross_pay: float
    pay_breakdown: dict
    message: str


def _compute_pay(profile: dict, shift_type: str, duration_hours: float) -> tuple[float, float, dict]:
    """
    Compute gross pay and overtime from industry config.
    Returns: (gross_pay, overtime_hours, breakdown_dict)
    """
    pay = profile["pay_structure"]
    base_rate = pay["base_daily_rate"]
    ot_multiplier = pay["overtime_multiplier"]
    ot_threshold = pay["overtime_threshold_hours"]
    allowances = pay.get("allowances", {})

    regular_hours = min(duration_hours, ot_threshold)
    overtime_hours = max(0.0, duration_hours - ot_threshold)

    hourly_rate = base_rate / ot_threshold
    regular_pay = regular_hours * hourly_rate
    overtime_pay = overtime_hours * hourly_rate * ot_multiplier

    # Allowances based on shift type
    allowance_pay = 0.0
    allowance_details = {}

    if shift_type in ("night", "oncall") and "night" in allowances:
        allowance_pay += allowances["night"]
        allowance_details["Night/On-call Allowance"] = allowances["night"]
    if shift_type in ("oncall",) and "oncall" in allowances:
        allowance_pay += allowances["oncall"]
        allowance_details["On-call Allowance"] = allowances["oncall"]
    if "infection_risk" in allowances and shift_type in ("morning", "evening", "oncall"):
        allowance_pay += allowances["infection_risk"]
        allowance_details["Infection Risk Allowance"] = allowances["infection_risk"]

    gross = regular_pay + overtime_pay + allowance_pay
    breakdown = {
        "regular_hours": round(regular_hours, 2),
        "regular_pay": round(regular_pay, 2),
        "overtime_hours": round(overtime_hours, 2),
        "overtime_pay": round(overtime_pay, 2),
        "allowances": allowance_details,
        "total_allowances": round(allowance_pay, 2),
        "gross_pay": round(gross, 2),
        "currency": pay["currency"],
    }
    return round(gross, 2), round(overtime_hours, 2), breakdown


@router.post("/checkin", response_model=CheckInResponse)
def check_in(
    req: CheckInRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_worker),
):
    """Worker checks in for a shift. Only one active shift allowed at a time."""
    # Check for already-active shift
    active = db.query(Shift).filter(
        Shift.user_id == current_user.id,
        Shift.is_active == True  # noqa: E712
    ).first()
    if active:
        raise HTTPException(status_code=400, detail="Already checked in. Check out first.")

    profile = get_profile(current_user.industry_id)
    if not profile:
        raise HTTPException(status_code=400, detail="Invalid industry profile")

    # Validate shift type exists in config
    shift_types = {s["id"]: s for s in profile["shift_types"]}
    if req.shift_type not in shift_types:
        valid = list(shift_types.keys())
        raise HTTPException(status_code=400, detail=f"Invalid shift type. Valid: {valid}")

    shift_label = shift_types[req.shift_type].get(
        f"label_{current_user.language_pref}", shift_types[req.shift_type]["label_en"]
    )

    shift = Shift(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        industry_id=current_user.industry_id,
        shift_type=req.shift_type,
        check_in_time=datetime.now(UTC).replace(tzinfo=None),
        site_id=req.site_id or current_user.site_id,
        is_active=True,
    )
    db.add(shift)
    db.commit()
    db.refresh(shift)

    return CheckInResponse(
        shift_id=shift.id,
        message="Checked in successfully",
        shift_label=shift_label,
        check_in_time=shift.check_in_time.isoformat(),
    )


@router.post("/checkout", response_model=CheckOutResponse)
def check_out(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_worker),
):
    """Worker checks out. Computes duration, overtime, and pay automatically."""
    shift = db.query(Shift).filter(
        Shift.user_id == current_user.id,
        Shift.is_active == True  # noqa: E712
    ).first()
    if not shift:
        raise HTTPException(status_code=400, detail="No active shift found. Check in first.")

    profile = get_profile(current_user.industry_id)
    if not profile:
        raise HTTPException(status_code=500, detail="Industry config missing")

    now = datetime.now(UTC).replace(tzinfo=None)
    duration_hours = (now - shift.check_in_time).total_seconds() / 3600

    gross_pay, overtime_hours, breakdown = _compute_pay(
        profile, shift.shift_type, duration_hours
    )

    shift.check_out_time = now
    shift.duration_hours = round(duration_hours, 2)
    shift.overtime_hours = overtime_hours
    shift.gross_pay = gross_pay
    shift.pay_breakdown = json.dumps(breakdown)
    shift.is_active = False
    db.commit()

    return CheckOutResponse(
        shift_id=shift.id,
        duration_hours=round(duration_hours, 2),
        overtime_hours=overtime_hours,
        gross_pay=gross_pay,
        pay_breakdown=breakdown,
        message="Checked out successfully. Pay calculated.",
    )


@router.get("/my-shifts")
def get_my_shifts(
    limit: int = 10,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_worker),
):
    """Return recent shifts for the logged-in worker."""
    shifts = (
        db.query(Shift)
        .filter(Shift.user_id == current_user.id)
        .order_by(Shift.created_at.desc())
        .limit(limit)
        .all()
    )
    result = []
    for s in shifts:
        breakdown = json.loads(s.pay_breakdown) if s.pay_breakdown else {}
        result.append({
            "id": s.id,
            "shift_type": s.shift_type,
            "check_in_time": s.check_in_time.isoformat() if s.check_in_time else None,
            "check_out_time": s.check_out_time.isoformat() if s.check_out_time else None,
            "duration_hours": s.duration_hours,
            "overtime_hours": s.overtime_hours,
            "gross_pay": s.gross_pay,
            "pay_breakdown": breakdown,
            "is_active": s.is_active,
            "site_id": s.site_id,
        })
    return {"shifts": result, "total": len(result)}


@router.get("/payslip/latest")
def get_latest_payslip(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_worker),
):
    """Return the most recent completed shift as a payslip."""
    shift = (
        db.query(Shift)
        .filter(Shift.user_id == current_user.id, Shift.is_active == False)  # noqa: E712
        .order_by(Shift.check_out_time.desc())
        .first()
    )
    if not shift:
        return {"message": "No completed shifts yet", "payslip": None}

    breakdown = json.loads(shift.pay_breakdown) if shift.pay_breakdown else {}
    profile = get_profile(current_user.industry_id)
    industry_name = profile["display_name_en"] if profile else current_user.industry_id

    return {
        "payslip": {
            "worker_name": current_user.name,
            "industry": industry_name,
            "site_id": shift.site_id,
            "shift_type": shift.shift_type,
            "date": shift.check_in_time.strftime("%d %b %Y") if shift.check_in_time else "-",
            "check_in": shift.check_in_time.strftime("%H:%M") if shift.check_in_time else "-",
            "check_out": shift.check_out_time.strftime("%H:%M") if shift.check_out_time else "-",
            "duration_hours": shift.duration_hours,
            "breakdown": breakdown,
        }
    }
