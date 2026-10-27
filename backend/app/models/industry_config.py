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

_CONFIG_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "config", "industry_profiles.json"
)


def load_profiles() -> None:
    """Load industry profiles from JSON config. Called at app startup."""
    global _PROFILES
    config_path = os.path.abspath(_CONFIG_PATH)
    with open(config_path, "r", encoding="utf-8") as f:
        _PROFILES = json.load(f)


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
