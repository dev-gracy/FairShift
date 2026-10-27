"""
FairShift — Industry profile loader
Reads industry_profiles.json once at startup and provides typed access.
This config-driven approach is the core architectural proof point:
one codebase serves multiple industries by swapping the config.
"""
import json
import os
from typing import Dict, Any, Optional

_PROFILES: Dict[str, Any] = {}

_CANDIDATE_PATHS = [
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "config", "industry_profiles.json"),
    os.path.join(os.path.dirname(__file__), "..", "..", "config", "industry_profiles.json"),
    os.path.join(os.path.dirname(__file__), "..", "config", "industry_profiles.json"),
    os.path.join(os.getcwd(), "config", "industry_profiles.json"),
    os.path.join(os.getcwd(), "..", "config", "industry_profiles.json"),
]


def load_profiles() -> None:
    """Load industry profiles from JSON config. Called at app startup."""
    global _PROFILES
    for path in _CANDIDATE_PATHS:
        abs_p = os.path.abspath(path)
        if os.path.isfile(abs_p):
            with open(abs_p, "r", encoding="utf-8") as f:
                _PROFILES = json.load(f)
                return
    # If no file found, keep default minimal profiles
    if not _PROFILES:
        _PROFILES = {
            "construction": {
                "id": "construction", "name": "Construction Site",
                "default_locale": "hi", "supported_locales": ["en", "hi", "ta"],
                "report_threshold_k": 3,
                "pay_structure": {"currency": "INR", "base_daily_rate": 600, "overtime_multiplier": 1.5, "overtime_threshold_hours": 8, "allowances": {"hazard": 50, "night": 75}}
            },
            "hospital": {
                "id": "hospital", "name": "Hospital / Healthcare",
                "default_locale": "ta", "supported_locales": ["en", "hi", "ta"],
                "report_threshold_k": 3,
                "pay_structure": {"currency": "INR", "base_daily_rate": 900, "overtime_multiplier": 2.0, "overtime_threshold_hours": 8, "allowances": {"infection_risk": 100, "oncall": 150}}
            }
        }


def get_profile(industry_id: str) -> Optional[Dict[str, Any]]:
    """Return the full config dict for a given industry_id, or None."""
    return _PROFILES.get(industry_id)


def get_all_profiles() -> Dict[str, Any]:
    """Return all loaded industry profiles."""
    return _PROFILES


def get_report_threshold(industry_id: str) -> int:
    """Return the k-anonymity threshold for a given industry."""
    profile = get_profile(industry_id)
    return profile["report_threshold_k"] if profile else 3
