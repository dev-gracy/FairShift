"""
FairShift — Auth & user management router
Handles login, registration, and user profile queries.
"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import (
    hash_password, verify_password, create_access_token,
    get_current_user
)
from app.models.database import get_db
from app.models.models import User
from app.models.industry_config import get_profile, get_all_profiles

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    role: str
    name: str
    industry_id: str
    language_pref: str


class RegisterRequest(BaseModel):
    name: str                           # display name
    username: str
    password: str
    role: str              # "worker" | "admin"
    industry_id: str       # "construction" | "hospital"
    site_id: Optional[str] = "site_a"
    language_pref: Optional[str] = "en"


@router.post("/login", response_model=LoginResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.name == req.username).first()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    token = create_access_token(user.id, user.role, user.industry_id)
    return LoginResponse(
        access_token=token,
        token_type="bearer",
        role=user.role,
        name=user.name,
        industry_id=user.industry_id,
        language_pref=user.language_pref,
    )


@router.post("/register")
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    """Self-service user registration. Open for demo; in production gate this behind invite tokens."""
    import re

    # --- Input validation ---
    if len(req.username) < 3:
        raise HTTPException(status_code=400, detail="Username must be at least 3 characters")
    if not re.match(r'^[a-zA-Z0-9_]+$', req.username):
        raise HTTPException(status_code=400, detail="Username can only contain letters, numbers and underscores")
    if len(req.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    if not req.name or not req.name.strip():
        raise HTTPException(status_code=400, detail="Full name is required")

    # Validate industry
    if not get_profile(req.industry_id):
        valid = list(get_all_profiles().keys())
        raise HTTPException(status_code=400, detail=f"Invalid industry_id. Valid: {valid}")

    if req.role not in ("worker", "admin"):
        raise HTTPException(status_code=400, detail="role must be 'worker' or 'admin'")

    # Check username uniqueness
    existing = db.query(User).filter(User.name == req.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username already taken")

    user = User(
        id=str(uuid.uuid4()),
        name=req.username,
        role=req.role,
        industry_id=req.industry_id,
        site_id=req.site_id or "site_a",
        language_pref=req.language_pref or "en",
        password_hash=hash_password(req.password),
    )
    db.add(user)
    db.commit()
    return {"message": "User created", "user_id": user.id, "role": user.role, "username": user.name}


@router.get("/me")
def get_me(current_user: User = Depends(get_current_user)):
    profile = get_profile(current_user.industry_id)
    return {
        "id": current_user.id,
        "name": current_user.name,
        "role": current_user.role,
        "industry_id": current_user.industry_id,
        "industry_name": profile["display_name_en"] if profile else current_user.industry_id,
        "site_id": current_user.site_id,
        "language_pref": current_user.language_pref,
    }


@router.get("/industries")
def list_industries():
    """Public: List all available industries for the login screen selector."""
    profiles = get_all_profiles()
    return {
        "industries": [
            {
                "id": pid,
                "name": p["display_name_en"],
                "name_hi": p["display_name_hi"],
                "name_ta": p["display_name_ta"],
                "default_locale": p["default_locale"],
            }
            for pid, p in profiles.items()
        ]
    }
