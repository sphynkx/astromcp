"""
astromcp - MCP service for natal chart rectification.
Engine: kerykeion (Swiss Ephemeris under the hood).
"""

import os
import math
import logging
from typing import Optional, List, Dict, Any
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from kerykeion import AstrologicalSubjectFactory

import warnings
warnings.filterwarnings("ignore", message=".*Field 'lifespan' has an incomplete definition.*")

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("astromcp")

HOST = os.getenv("ASTROMCP_HOST", "0.0.0.0")
PORT = int(os.getenv("ASTROMCP_PORT", "8765"))

mcp = FastMCP("astromcp", host=HOST, port=PORT)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_POINTS = [
    "sun", "moon", "mercury", "venus", "mars", "jupiter", "saturn",
    "uranus", "neptune", "pluto", "mean_node", "true_node", "chiron",
    "mean_lilith",
]

HOUSE_KEYS = [
    "first_house", "second_house", "third_house", "fourth_house",
    "fifth_house", "sixth_house", "seventh_house", "eighth_house",
    "ninth_house", "tenth_house", "eleventh_house", "twelfth_house",
]

ANGLE_KEYS = ["ascendant", "descendant", "medium_coeli", "imum_coeli"]

SIGN_ORDER = ["Ari", "Tau", "Gem", "Can", "Leo", "Vir", "Lib", "Sco", "Sag", "Cap", "Aqu", "Pis"]

DEFAULT_ASPECT_SET = [0, 30, 45, 60, 90, 120, 135, 150, 180]

# Transits move fast (days/weeks) - wide orbs are fine.
DEFAULT_ORB_TABLE_TRANSIT = {0: 8.0, 30: 2.0, 45: 2.0, 60: 4.0, 90: 6.0,
                              120: 6.0, 135: 2.0, 150: 3.0, 180: 8.0}

# Directions/progressions: 1 degree of arc is roughly 1 year of life, so a
# wide orb here translates directly into years of dating error. Keep tight.
DEFAULT_ORB_TABLE_DIRECTION = {0: 1.0, 30: 1.0, 45: 1.0, 60: 1.0, 90: 1.0,
                                120: 1.0, 135: 1.0, 150: 1.0, 180: 1.0}

LUMINARY_ORB_BONUS_TRANSIT = 1.0
LUMINARY_ORB_BONUS_DIRECTION = 0.5
LUMINARY_NAMES = {"sun", "moon"}


# ---------------------------------------------------------------------------
# Timezone helpers
# ---------------------------------------------------------------------------

def offset_minutes_to_tz_str(offset_minutes: int) -> str:
    """
    Converts a whole-hour UTC offset into a fixed IANA zone of the form Etc/GMT+-N.
    IMPORTANT: Etc/GMT sign convention is INVERTED relative to common usage:
    Etc/GMT-8 means UTC+8, and Etc/GMT+5 means UTC-5.
    Only works for whole-hour offsets. For half-hour/quarter-hour offsets,
    pass tz_str as an explicit IANA zone instead.
    """
    if offset_minutes % 60 != 0:
        raise ValueError(
            f"offset_minutes={offset_minutes} is not a multiple of 60 - "
            "Etc/GMT does not support half-hour offsets, pass tz_str directly"
        )
    hours = offset_minutes // 60
    sign = "-" if hours >= 0 else "+"
    return f"Etc/GMT{sign}{abs(hours)}"


def resolve_fixed_offset_minutes(tz_str: Optional[str], tz_offset_minutes: Optional[int],
                                  year: int, month: int, day: int,
                                  hour: int, minute: int, second: int) -> int:
    """Resolves a fixed UTC offset (in minutes) for a given civil datetime."""
    if tz_offset_minutes is not None:
        return tz_offset_minutes
    dt = datetime(year, month, day, hour, minute, second, tzinfo=ZoneInfo(tz_str))
    return int(dt.utcoffset().total_seconds() // 60)


# ---------------------------------------------------------------------------
# Subject construction / serialization
# ---------------------------------------------------------------------------

def build_subject(
    name: str,
    year: int, month: int, day: int,
    hour: int, minute: int, second: int,
    lat: float, lng: float,
    tz_str: Optional[str] = None,
    tz_offset_minutes: Optional[int] = None,
    house_system: str = "P",
    zodiac_type: str = "Tropic",
):
    if tz_str is None and tz_offset_minutes is None:
        raise ValueError("Either tz_str or tz_offset_minutes must be provided")

    resolved_tz = tz_str if tz_str else offset_minutes_to_tz_str(tz_offset_minutes)
    tz_source = f"explicit:{tz_str}" if tz_str else f"offset_override:{tz_offset_minutes}min"

    subject = AstrologicalSubjectFactory.from_birth_data(
        name=name,
        year=year, month=month, day=day,
        hour=hour, minute=minute,
        lat=lat, lng=lng,
        tz_str=resolved_tz,
        houses_system_identifier=house_system,
        zodiac_type=zodiac_type,
        online=False,
    )
    return subject, resolved_tz, tz_source


def serialize_subject(subject, points: List[str], include_raw: bool = False) -> Dict[str, Any]:
    try:
        raw = subject.model_dump(mode="json")
    except AttributeError:
        raw = {k: v for k, v in vars(subject).items()}

    def dump_point(key: str):
        val = raw.get(key)
        if val is None:
            return None
        if isinstance(val, dict):
            return val
        try:
            return val.model_dump(mode="json")
        except AttributeError:
            return str(val)

    result = {
        "points": {p: dump_point(p) for p in points if dump_point(p) is not None},
        "houses": {h: dump_point(h) for h in HOUSE_KEYS if dump_point(h) is not None},
        "angles": {a: dump_point(a) for a in ANGLE_KEYS if dump_point(a) is not None},
    }
    if include_raw:
        result["raw"] = raw
    return result


def natal_points_dict(subject) -> Dict[str, Dict[str, Any]]:
    raw = subject.model_dump(mode="json")
    out = {}
    for key in DEFAULT_POINTS + ANGLE_KEYS:
        val = raw.get(key)
        if val is not None:
            out[key] = val
    return out


def recompute_sign_fields(point_dict: Dict[str, Any], new_abs_pos: float) -> Dict[str, Any]:
    """
    After manually shifting a point's abs_pos (e.g. solar arc direction),
    the sign/sign_num/position fields do NOT update themselves - they must
    be recomputed from the new absolute longitude. Mutates and returns the
    same dict for convenience.
    """
    new_abs_pos = new_abs_pos % 360
    idx = int(new_abs_pos // 30)
    point_dict["abs_pos"] = new_abs_pos
    point_dict["position"] = new_abs_pos - idx * 30
    point_dict["sign"] = SIGN_ORDER[idx]
    point_dict["sign_num"] = idx
    return point_dict


# ---------------------------------------------------------------------------
# Aspect calculation
# ---------------------------------------------------------------------------

def angular_separation(pos_a: float, pos_b: float) -> float:
    """Shortest angular distance between two ecliptic longitudes, 0..180."""
    diff = abs(pos_a - pos_b) % 360
    return diff if diff <= 180 else 360 - diff


def aspect_status(moving_pos: float, moving_speed: float, target_pos: float,
                   aspect_deg: float, current_orb: float) -> str:
    """
    Determines applying / separating / exact by numerically projecting the
    moving point forward by a small time step and checking whether the orb
    shrinks or grows. Works uniformly for direct/retrograde motion and for
    solar arc (nominal forward speed).
    """
    if abs(current_orb) < 0.0167:  # under 1 arcminute counts as exact
        return "exact"
    dt = 1.0
    future_pos = (moving_pos + moving_speed * dt) % 360
    future_sep = angular_separation(future_pos, target_pos)
    future_orb = abs(future_sep - aspect_deg)
    if future_orb < current_orb:
        return "applying"
    elif future_orb > current_orb:
        return "separating"
    return "static"


def compute_aspects(
    computed_points: Dict[str, Dict[str, Any]],
    natal_points: Dict[str, Dict[str, Any]],
    aspect_set: List[float],
    orb_table: Dict[float, float],
    luminary_bonus: float,
) -> List[Dict[str, Any]]:
    results = []
    for name_a, pa in computed_points.items():
        pos_a = pa.get("abs_pos")
        speed_a = pa.get("speed", 0.0) or 0.0
        if pos_a is None:
            continue
        for name_b, pb in natal_points.items():
            pos_b = pb.get("abs_pos")
            if pos_b is None:
                continue
            sep = angular_separation(pos_a, pos_b)
            for asp_deg in aspect_set:
                allowed_orb = orb_table.get(asp_deg, 4.0)
                if name_a in LUMINARY_NAMES or name_b in LUMINARY_NAMES:
                    allowed_orb += luminary_bonus
                orb = abs(sep - asp_deg)
                if orb <= allowed_orb:
                    status = aspect_status(pos_a, speed_a, pos_b, asp_deg, orb)
                    results.append({
                        "point_a": name_a,
                        "point_b": name_b,
                        "aspect_deg": asp_deg,
                        "exact_orb": round(orb, 4),
                        "status": status,
                    })
    return results


# ---------------------------------------------------------------------------
# Techniques
# ---------------------------------------------------------------------------

def technique_secondary_progression(
    natal_year, natal_month, natal_day, natal_hour, natal_minute, natal_second,
    natal_lat, natal_lng, natal_tz_str, natal_tz_offset_minutes,
    house_system, zodiac_type,
    target_year, target_month, target_day,
    angle_method: str,
):
    fixed_offset = resolve_fixed_offset_minutes(
        natal_tz_str, natal_tz_offset_minutes,
        natal_year, natal_month, natal_day, natal_hour, natal_minute, natal_second,
    )

    natal_subject, resolved_tz, tz_source = build_subject(
        "natal", natal_year, natal_month, natal_day, natal_hour, natal_minute, natal_second,
        natal_lat, natal_lng, None, fixed_offset, house_system, zodiac_type,
    )

    natal_civil_date = date(natal_year, natal_month, natal_day)
    target_civil_date = date(target_year, target_month, target_day)
    elapsed_days_calendar = (target_civil_date - natal_civil_date).days
    elapsed_years = elapsed_days_calendar / 365.2425
    progression_days_to_add = elapsed_years  # day-for-a-year

    prog_dt = datetime(natal_year, natal_month, natal_day, natal_hour, natal_minute, natal_second) \
        + timedelta(days=progression_days_to_add)

    prog_subject, _, _ = build_subject(
        "progressed", prog_dt.year, prog_dt.month, prog_dt.day,
        prog_dt.hour, prog_dt.minute, prog_dt.second,
        natal_lat, natal_lng, None, fixed_offset, house_system, zodiac_type,
    )

    natal_raw = natal_subject.model_dump(mode="json")
    prog_raw = prog_subject.model_dump(mode="json")

    computed = {p: prog_raw[p] for p in DEFAULT_POINTS if p in prog_raw}

    if angle_method == "direct_progressed_angles":
        for a in ANGLE_KEYS:
            if a in prog_raw:
                computed[a] = prog_raw[a]
    elif angle_method == "solar_arc_naibod":
        natal_sun = natal_raw["sun"]["abs_pos"]
        prog_sun = prog_raw["sun"]["abs_pos"]
        arc = (prog_sun - natal_sun) % 360
        for a in ANGLE_KEYS:
            if a in natal_raw:
                base = dict(natal_raw[a])
                base = recompute_sign_fields(base, base["abs_pos"] + arc)
                base["speed"] = 1.0  # nominal forward direction for applying/separating calc
                computed[a] = base
    else:
        raise ValueError(f"Unknown angle_method: {angle_method}")

    return computed, natal_points_dict(natal_subject), {
        "elapsed_years": round(elapsed_years, 4),
        "progressed_date": prog_dt.isoformat(),
        "tz_used": resolved_tz,
        "tz_source": tz_source,
        "angle_method": angle_method,
    }


def technique_solar_arc(
    natal_year, natal_month, natal_day, natal_hour, natal_minute, natal_second,
    natal_lat, natal_lng, natal_tz_str, natal_tz_offset_minutes,
    house_system, zodiac_type,
    target_year, target_month, target_day,
):
    fixed_offset = resolve_fixed_offset_minutes(
        natal_tz_str, natal_tz_offset_minutes,
        natal_year, natal_month, natal_day, natal_hour, natal_minute, natal_second,
    )
    natal_subject, resolved_tz, tz_source = build_subject(
        "natal", natal_year, natal_month, natal_day, natal_hour, natal_minute, natal_second,
        natal_lat, natal_lng, None, fixed_offset, house_system, zodiac_type,
    )
    natal_civil_date = date(natal_year, natal_month, natal_day)
    target_civil_date = date(target_year, target_month, target_day)
    elapsed_years = (target_civil_date - natal_civil_date).days / 365.2425

    prog_dt = datetime(natal_year, natal_month, natal_day, natal_hour, natal_minute, natal_second) \
        + timedelta(days=elapsed_years)
    prog_sun_subject, _, _ = build_subject(
        "sun_only", prog_dt.year, prog_dt.month, prog_dt.day,
        prog_dt.hour, prog_dt.minute, prog_dt.second,
        natal_lat, natal_lng, None, fixed_offset, house_system, zodiac_type,
    )

    natal_raw = natal_subject.model_dump(mode="json")
    prog_sun_pos = prog_sun_subject.model_dump(mode="json")["sun"]["abs_pos"]
    natal_sun_pos = natal_raw["sun"]["abs_pos"]
    arc = (prog_sun_pos - natal_sun_pos) % 360

    computed = {}
    for key in DEFAULT_POINTS + ANGLE_KEYS:
        if key in natal_raw:
            base = dict(natal_raw[key])
            base = recompute_sign_fields(base, base["abs_pos"] + arc)
            base["speed"] = 1.0
            computed[key] = base

    return computed, natal_points_dict(natal_subject), {
        "elapsed_years": round(elapsed_years, 4),
        "solar_arc_deg": round(arc, 4),
        "tz_used": resolved_tz,
        "tz_source": tz_source,
    }


def technique_transit(
    natal_year, natal_month, natal_day, natal_hour, natal_minute, natal_second,
    natal_lat, natal_lng, natal_tz_str, natal_tz_offset_minutes,
    house_system, zodiac_type,
    target_year, target_month, target_day, target_hour, target_minute, target_second,
    event_lat, event_lng, event_tz_str, event_tz_offset_minutes,
):
    natal_subject, resolved_tz, tz_source = build_subject(
        "natal", natal_year, natal_month, natal_day, natal_hour, natal_minute, natal_second,
        natal_lat, natal_lng, natal_tz_str, natal_tz_offset_minutes, house_system, zodiac_type,
    )
    ev_lat = event_lat if event_lat is not None else natal_lat
    ev_lng = event_lng if event_lng is not None else natal_lng

    # Priority: explicit event tz_str > explicit event offset > natal's tz info.
    # An explicit event_tz_offset_minutes must win over a tz_str that would
    # otherwise only be present because it was inherited from natal defaults -
    # otherwise build_subject's tz_str-wins-over-offset rule silently discards
    # the caller's explicit offset.
    if event_tz_str is not None:
        ev_tz_str = event_tz_str
        ev_tz_off = None
    elif event_tz_offset_minutes is not None:
        ev_tz_str = None
        ev_tz_off = event_tz_offset_minutes
    else:
        ev_tz_str = natal_tz_str
        ev_tz_off = natal_tz_offset_minutes

    transit_subject, ev_resolved_tz, ev_tz_source = build_subject(
        "transit", target_year, target_month, target_day,
        target_hour, target_minute, target_second,
        ev_lat, ev_lng, ev_tz_str, ev_tz_off, house_system, zodiac_type,
    )
    transit_raw = transit_subject.model_dump(mode="json")
    computed = {p: transit_raw[p] for p in DEFAULT_POINTS if p in transit_raw}

    return computed, natal_points_dict(natal_subject), {
        "event_tz_used": ev_resolved_tz,
        "event_tz_source": ev_tz_source,
    }


# ---------------------------------------------------------------------------
# MCP tools
# ---------------------------------------------------------------------------

@mcp.tool()
def rectif_chart(
    year: int, month: int, day: int,
    hour: int, minute: int, second: int = 0,
    lat: float = 0.0, lng: float = 0.0,
    tz_str: Optional[str] = None,
    tz_offset_minutes: Optional[int] = None,
    house_system: str = "P",
    zodiac_type: str = "Tropic",
    points: Optional[List[str]] = None,
    include_raw: bool = False,
    name: str = "subject",
) -> Dict[str, Any]:
    """
    Builds a chart (planet positions, house cusps, ASC/MC angles) for an
    arbitrary date/time/place. Used as the base primitive for rectification:
    transits, progressions and directions are computed on top of this tool's
    output.

    tz_str - IANA zone (e.g. "Asia/Novosibirsk"). Or instead of it,
    tz_offset_minutes - an explicit whole-hour UTC offset (e.g. 480 for UTC+8),
    for cases where auto-resolving via current zone boundaries would be
    historically incorrect.
    house_system - single-letter kerykeion house system code (P=Placidus,
    K=Koch, W=Whole Sign, R=Regiomontanus, E=Equal, ...).
    """
    try:
        subject, resolved_tz, tz_source = build_subject(
            name, year, month, day, hour, minute, second,
            lat, lng, tz_str, tz_offset_minutes, house_system, zodiac_type,
        )
        pts = points if points else DEFAULT_POINTS
        data = serialize_subject(subject, pts, include_raw)
        data["meta"] = {
            "tz_used": resolved_tz,
            "tz_source": tz_source,
            "house_system": house_system,
            "zodiac_type": zodiac_type,
            "input_datetime": f"{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:{second:02d}",
        }
        return data
    except Exception as e:
        logger.exception("rectif_chart failed")
        return {"error": str(e)}


@mcp.tool()
def rectif_chart_batch(requests: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Batch version of rectif_chart: accepts a list of objects with the same
    fields as rectif_chart, returns a list of results in the same order.
    """
    results = []
    for i, req in enumerate(requests):
        try:
            results.append(rectif_chart(**req))
        except Exception as e:
            logger.exception(f"rectif_chart_batch item {i} failed")
            results.append({"error": str(e), "index": i})
    return results


@mcp.tool()
def rectif_technique(
    natal_year: int, natal_month: int, natal_day: int,
    natal_hour: int, natal_minute: int, natal_second: int,
    natal_lat: float, natal_lng: float,
    natal_tz_str: Optional[str] = None,
    natal_tz_offset_minutes: Optional[int] = None,
    house_system: str = "P",
    zodiac_type: str = "Tropic",
    technique: str = "transit",  # secondary_progression | solar_arc | transit
    target_year: int = 2000, target_month: int = 1, target_day: int = 1,
    target_hour: int = 12, target_minute: int = 0, target_second: int = 0,
    angle_method: str = "solar_arc_naibod",  # for secondary_progression
    event_lat: Optional[float] = None, event_lng: Optional[float] = None,
    event_tz_str: Optional[str] = None, event_tz_offset_minutes: Optional[int] = None,
    compute_aspects_flag: bool = True,
    aspect_set: Optional[List[float]] = None,
    orb_table: Optional[Dict[str, float]] = None,
    luminary_orb_bonus: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Computes a predictive technique (secondary progression, solar arc direction,
    or transit) for a natal chart on a given target date, and optionally the
    aspects it forms to the natal chart. This is the core engine for
    rectification: run it once per candidate event, per candidate birth time.

    Default orbs are technique-aware: transits use wide classical orbs,
    while progressions/directions use tight ~1 degree orbs (since 1 degree
    of arc corresponds to roughly 1 year of life, a wide orb here directly
    translates into years of dating error). Pass orb_table/luminary_orb_bonus
    explicitly to override.
    """
    try:
        if technique == "secondary_progression":
            computed, natal_pts, meta = technique_secondary_progression(
                natal_year, natal_month, natal_day, natal_hour, natal_minute, natal_second,
                natal_lat, natal_lng, natal_tz_str, natal_tz_offset_minutes,
                house_system, zodiac_type,
                target_year, target_month, target_day, angle_method,
            )
        elif technique == "solar_arc":
            computed, natal_pts, meta = technique_solar_arc(
                natal_year, natal_month, natal_day, natal_hour, natal_minute, natal_second,
                natal_lat, natal_lng, natal_tz_str, natal_tz_offset_minutes,
                house_system, zodiac_type,
                target_year, target_month, target_day,
            )
        elif technique == "transit":
            computed, natal_pts, meta = technique_transit(
                natal_year, natal_month, natal_day, natal_hour, natal_minute, natal_second,
                natal_lat, natal_lng, natal_tz_str, natal_tz_offset_minutes,
                house_system, zodiac_type,
                target_year, target_month, target_day, target_hour, target_minute, target_second,
                event_lat, event_lng, event_tz_str, event_tz_offset_minutes,
            )
        else:
            return {"error": f"Unknown technique: {technique}"}

        result = {
            "technique": technique,
            "computed_points": computed,
            "natal_points_echo": natal_pts,
            "meta": meta,
        }

        if compute_aspects_flag:
            asp_set = aspect_set if aspect_set else DEFAULT_ASPECT_SET

            if orb_table:
                orb_tbl = {float(k): v for k, v in orb_table.items()}
            elif technique == "transit":
                orb_tbl = DEFAULT_ORB_TABLE_TRANSIT
            else:
                orb_tbl = DEFAULT_ORB_TABLE_DIRECTION

            if luminary_orb_bonus is not None:
                bonus = luminary_orb_bonus
            elif technique == "transit":
                bonus = LUMINARY_ORB_BONUS_TRANSIT
            else:
                bonus = LUMINARY_ORB_BONUS_DIRECTION

            result["aspects"] = compute_aspects(computed, natal_pts, asp_set, orb_tbl, bonus)

        return result
    except Exception as e:
        logger.exception("rectif_technique failed")
        return {"error": str(e)}


@mcp.tool()
def rectif_technique_batch(requests: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Batch version of rectif_technique. Same fields per item, list in -> list out."""
    results = []
    for i, req in enumerate(requests):
        try:
            results.append(rectif_technique(**req))
        except Exception as e:
            logger.exception(f"rectif_technique_batch item {i} failed")
            results.append({"error": str(e), "index": i})
    return results


@mcp.tool()
def ping(message: str = "world") -> str:
    """Simple connectivity test."""
    return f"pong: {message} (from astromcp, kerykeion engine loaded)"


if __name__ == "__main__":
    try:
        mcp.run(transport="streamable-http")
    except KeyboardInterrupt:
        logger.info("Shutdown requested via Ctrl+C, exiting cleanly")