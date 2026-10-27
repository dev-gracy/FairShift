"""
FairShift — Industry config router
Provides frontend with config data (shift types, hazard categories, locales)
so the UI renders dynamically without hardcoded industry logic.
"""
from fastapi import APIRouter, HTTPException

from app.models.industry_config import get_profile, get_all_profiles

router = APIRouter(prefix="/config", tags=["config"])


@router.get("/{industry_id}")
def get_industry_config(industry_id: str):
    """Return full industry config for a given industry ID."""
    profile = get_profile(industry_id)
    if not profile:
        valid = list(get_all_profiles().keys())
        raise HTTPException(
            status_code=404,
            detail=f"Industry '{industry_id}' not found. Valid: {valid}"
        )
    return profile


@router.get("/{industry_id}/shift-types")
def get_shift_types(industry_id: str):
    profile = get_profile(industry_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Industry not found")
    return {"shift_types": profile["shift_types"]}


@router.get("/{industry_id}/hazards")
def get_hazard_categories(industry_id: str):
    profile = get_profile(industry_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Industry not found")
    return {"hazard_categories": profile["hazard_categories"]}


@router.get("/{industry_id}/grievances")
def get_grievance_categories(industry_id: str):
    profile = get_profile(industry_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Industry not found")
    return {"grievance_categories": profile["grievance_categories"]}
