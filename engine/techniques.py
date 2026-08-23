"""
Predictive techniques: transit, secondary progression, solar arc direction.

Each function accepts an already-built natal context (subject/raw) so that
callers doing many events per candidate (e.g. rectif_scan) only pay the cost
of building the natal chart once, not once per event.
"""

from typing import Optional, Dict, Any
from datetime import date, datetime, timedelta

from .chart import build_subject, recompute_sign_fields
from .constants import DEFAULT_POINTS, ANGLE_KEYS


def technique_transit(
    natal_raw: Dict[str, Any],
    natal_points: Dict[str, Dict[str, Any]],
    target_year, target_month, target_day, target_hour, target_minute, target_second,
    event_lat, event_lng, event_tz_str, event_tz_offset_minutes,
    house_system, zodiac_type,
):
    transit_subject, ev_resolved_tz, ev_tz_source = build_subject(
        "transit", target_year, target_month, target_day,
        target_hour, target_minute, target_second,
        event_lat, event_lng, event_tz_str, event_tz_offset_minutes, house_system, zodiac_type,
    )
    transit_raw = transit_subject.model_dump(mode="json")
    computed = {p: transit_raw[p] for p in DEFAULT_POINTS if p in transit_raw}

    return computed, natal_points, {
        "event_tz_used": ev_resolved_tz,
        "event_tz_source": ev_tz_source,
    }


def technique_secondary_progression(
    natal_year, natal_month, natal_day, natal_hour, natal_minute, natal_second,
    natal_lat, natal_lng, fixed_offset,
    house_system, zodiac_type,
    natal_raw: Dict[str, Any],
    natal_points: Dict[str, Dict[str, Any]],
    target_year, target_month, target_day,
    angle_method: str,
):
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
                base["speed"] = 1.0
                computed[a] = base
    else:
        raise ValueError(f"Unknown angle_method: {angle_method}")

    return computed, natal_points, {
        "elapsed_years": round(elapsed_years, 4),
        "progressed_date": prog_dt.isoformat(),
        "angle_method": angle_method,
    }


def technique_solar_arc(
    natal_year, natal_month, natal_day, natal_hour, natal_minute, natal_second,
    natal_lat, natal_lng, fixed_offset,
    house_system, zodiac_type,
    natal_raw: Dict[str, Any],
    natal_points: Dict[str, Dict[str, Any]],
    target_year, target_month, target_day,
):
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

    return computed, natal_points, {
        "elapsed_years": round(elapsed_years, 4),
        "solar_arc_deg": round(arc, 4),
    }
