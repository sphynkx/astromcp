"""
Central configuration. All values are read from environment variables
(populated from .env by python-dotenv in app.py) with sensible built-in
defaults, so the service runs out of the box with no .env file at all.

To override a default, set the corresponding ASTROMCP_* variable in .env -
see .env.example for the full list with explanations.
"""

import os
import json
from typing import Dict, List


def _get_str(key: str, default: str) -> str:
    return os.getenv(key, default)


def _get_int(key: str, default: int) -> int:
    val = os.getenv(key)
    return int(val) if val is not None else default


def _get_float(key: str, default: float) -> float:
    val = os.getenv(key)
    return float(val) if val is not None else default


def _get_bool(key: str, default: bool) -> bool:
    val = os.getenv(key)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _get_json_orb_table(key: str, default: Dict[float, float]) -> Dict[float, float]:
    val = os.getenv(key)
    if val is None:
        return default
    parsed = json.loads(val)
    return {float(k): float(v) for k, v in parsed.items()}


def _get_json_list(key: str, default: List) -> List:
    val = os.getenv(key)
    if val is None:
        return default
    return json.loads(val)


# --- Network ---
HOST = _get_str("ASTROMCP_HOST", "0.0.0.0")
PORT = _get_int("ASTROMCP_PORT", 8765)
LOG_LEVEL = _get_str("ASTROMCP_LOG_LEVEL", "INFO")

# --- Astrological defaults ---
DEFAULT_HOUSE_SYSTEM = _get_str("ASTROMCP_HOUSE_SYSTEM", "P")
DEFAULT_ZODIAC_TYPE = _get_str("ASTROMCP_ZODIAC_TYPE", "Tropic")

# --- Orb tables: aspect degree -> allowed orb in degrees ---
# Transits move fast (days/weeks) - wide orbs are fine.
DEFAULT_ORB_TABLE_TRANSIT = _get_json_orb_table(
    "ASTROMCP_ORB_TABLE_TRANSIT",
    {0: 8.0, 30: 2.0, 45: 2.0, 60: 4.0, 90: 6.0, 120: 6.0, 135: 2.0, 150: 3.0, 180: 8.0},
)

# Directions/progressions: 1 degree of arc is roughly 1 year of life, so a
# wide orb here translates directly into years of dating error. Keep tight.
DEFAULT_ORB_TABLE_DIRECTION = _get_json_orb_table(
    "ASTROMCP_ORB_TABLE_DIRECTION",
    {0: 1.0, 30: 1.0, 45: 1.0, 60: 1.0, 90: 1.0, 120: 1.0, 135: 1.0, 150: 1.0, 180: 1.0},
)

LUMINARY_ORB_BONUS_TRANSIT = _get_float("ASTROMCP_LUMINARY_BONUS_TRANSIT", 1.0)
LUMINARY_ORB_BONUS_DIRECTION = _get_float("ASTROMCP_LUMINARY_BONUS_DIRECTION", 0.5)

DEFAULT_ASPECT_SET = _get_json_list(
    "ASTROMCP_ASPECT_SET", [0, 30, 45, 60, 90, 120, 135, 150, 180]
)

# --- rectif_scan defaults ---
DEFAULT_SCAN_TARGET_POINTS = tuple(_get_json_list(
    "ASTROMCP_SCAN_TARGET_POINTS",
    ["ascendant", "medium_coeli", "descendant", "imum_coeli", "sun", "moon"],
))
DEFAULT_SCAN_ASPECT_SET = tuple(_get_json_list("ASTROMCP_SCAN_ASPECT_SET", [0, 90, 180]))
DEFAULT_SCAN_ORB_THRESHOLD = _get_float("ASTROMCP_SCAN_ORB_THRESHOLD", 1.5)

# --- Console output ---
# When true, every tool call also prints a human-readable summary of its
# result to the server console/journal (in addition to the MCP response),
# so an operator watching the logs can see what's happening at a glance.
CONSOLE_RESULT_PREVIEW = _get_bool("ASTROMCP_CONSOLE_RESULT_PREVIEW", True)
