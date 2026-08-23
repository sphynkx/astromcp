"""
Tool implementations (business logic). app.py wraps these as MCP tools via
@mcp.tool() decorators. This module has no dependency on the mcp/FastMCP
package itself, so it can in principle be tested or reused without a running
MCP server.
"""

import logging
from typing import Optional, List, Dict, Any

from . import config
from .chart import build_subject, serialize_subject, natal_points_dict, subject_raw, resolve_fixed_offset_minutes
from .aspects import compute_aspects
from .techniques import technique_transit, technique_secondary_progression, technique_solar_arc
from .scan import run_scan
from .constants import DEFAULT_POINTS, LUMINARY_NAMES
from .display import print_chart_result, print_technique_result, print_scan_result

logger = logging.getLogger("astromcp")


def rectif_chart(
    year: int, month: int, day: int,
    hour: int, minute: int, second: int = 0,
    lat: float = 0.0, lng: float = 0.0,
    tz_str: Optional[str] = None,
    tz_offset_minutes: Optional[int] = None,
    house_system: Optional[str] = None,
    zodiac_type: Optional[str] = None,
    points: Optional[List[str]] = None,
    include_raw: bool = False,
    name: str = "subject",
) -> Dict[str, Any]:
    house_system = house_system or config.DEFAULT_HOUSE_SYSTEM
    zodiac_type = zodiac_type or config.DEFAULT_ZODIAC_TYPE
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
        if config.CONSOLE_RESULT_PREVIEW:
            print_chart_result(data)
        return data
    except Exception as e:
        logger.exception("rectif_chart failed")
        return {"error": str(e)}


def rectif_chart_batch(requests: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    results = []
    for i, req in enumerate(requests):
        try:
            results.append(rectif_chart(**req))
        except Exception as e:
            logger.exception(f"rectif_chart_batch item {i} failed")
            results.append({"error": str(e), "index": i})
    return results


def rectif_technique(
    natal_year: int, natal_month: int, natal_day: int,
    natal_hour: int, natal_minute: int, natal_second: int,
    natal_lat: float, natal_lng: float,
    natal_tz_str: Optional[str] = None,
    natal_tz_offset_minutes: Optional[int] = None,
    house_system: Optional[str] = None,
    zodiac_type: Optional[str] = None,
    technique: str = "transit",
    target_year: int = 2000, target_month: int = 1, target_day: int = 1,
    target_hour: int = 12, target_minute: int = 0, target_second: int = 0,
    angle_method: str = "solar_arc_naibod",
    event_lat: Optional[float] = None, event_lng: Optional[float] = None,
    event_tz_str: Optional[str] = None, event_tz_offset_minutes: Optional[int] = None,
    compute_aspects_flag: bool = True,
    aspect_set: Optional[List[float]] = None,
    orb_table: Optional[Dict[str, float]] = None,
    luminary_orb_bonus: Optional[float] = None,
) -> Dict[str, Any]:
    house_system = house_system or config.DEFAULT_HOUSE_SYSTEM
    zodiac_type = zodiac_type or config.DEFAULT_ZODIAC_TYPE
    try:
        natal_subject, resolved_tz, tz_source = build_subject(
            "natal", natal_year, natal_month, natal_day, natal_hour, natal_minute, natal_second,
            natal_lat, natal_lng, natal_tz_str, natal_tz_offset_minutes, house_system, zodiac_type,
        )
        n_raw = subject_raw(natal_subject)
        n_points = natal_points_dict(natal_subject)

        if technique == "secondary_progression":
            fixed_offset = resolve_fixed_offset_minutes(
                natal_tz_str, natal_tz_offset_minutes,
                natal_year, natal_month, natal_day, natal_hour, natal_minute, natal_second,
            )
            computed, natal_pts, meta = technique_secondary_progression(
                natal_year, natal_month, natal_day, natal_hour, natal_minute, natal_second,
                natal_lat, natal_lng, fixed_offset, house_system, zodiac_type,
                n_raw, n_points, target_year, target_month, target_day, angle_method,
            )
        elif technique == "solar_arc":
            fixed_offset = resolve_fixed_offset_minutes(
                natal_tz_str, natal_tz_offset_minutes,
                natal_year, natal_month, natal_day, natal_hour, natal_minute, natal_second,
            )
            computed, natal_pts, meta = technique_solar_arc(
                natal_year, natal_month, natal_day, natal_hour, natal_minute, natal_second,
                natal_lat, natal_lng, fixed_offset, house_system, zodiac_type,
                n_raw, n_points, target_year, target_month, target_day,
            )
        elif technique == "transit":
            ev_tz_str = event_tz_str
            ev_tz_off = event_tz_offset_minutes
            if ev_tz_str is None and ev_tz_off is None:
                ev_tz_str, ev_tz_off = natal_tz_str, natal_tz_offset_minutes
            computed, natal_pts, meta = technique_transit(
                n_raw, n_points,
                target_year, target_month, target_day, target_hour, target_minute, target_second,
                event_lat if event_lat is not None else natal_lat,
                event_lng if event_lng is not None else natal_lng,
                ev_tz_str, ev_tz_off, house_system, zodiac_type,
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
            asp_set = aspect_set if aspect_set else config.DEFAULT_ASPECT_SET

            if orb_table:
                orb_tbl = {float(k): v for k, v in orb_table.items()}
            elif technique == "transit":
                orb_tbl = config.DEFAULT_ORB_TABLE_TRANSIT
            else:
                orb_tbl = config.DEFAULT_ORB_TABLE_DIRECTION

            if luminary_orb_bonus is not None:
                bonus = luminary_orb_bonus
            elif technique == "transit":
                bonus = config.LUMINARY_ORB_BONUS_TRANSIT
            else:
                bonus = config.LUMINARY_ORB_BONUS_DIRECTION

            result["aspects"] = compute_aspects(computed, natal_pts, asp_set, orb_tbl, bonus, LUMINARY_NAMES)

        if config.CONSOLE_RESULT_PREVIEW:
            print_technique_result(result)
        return result
    except Exception as e:
        logger.exception("rectif_technique failed")
        return {"error": str(e)}


def rectif_technique_batch(requests: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    results = []
    for i, req in enumerate(requests):
        try:
            results.append(rectif_technique(**req))
        except Exception as e:
            logger.exception(f"rectif_technique_batch item {i} failed")
            results.append({"error": str(e), "index": i})
    return results


def rectif_scan(
    natal_year: int, natal_month: int, natal_day: int,
    natal_lat: float, natal_lng: float,
    natal_tz_str: Optional[str] = None,
    natal_tz_offset_minutes: Optional[int] = None,
    house_system: Optional[str] = None,
    zodiac_type: Optional[str] = None,
    scan_start_hour: int = 0, scan_start_minute: int = 0,
    scan_end_hour: int = 23, scan_end_minute: int = 59,
    step_minutes: int = 2,
    events: Optional[List[Dict[str, Any]]] = None,
    target_points: Optional[List[str]] = None,
    aspect_set: Optional[List[float]] = None,
    orb_threshold: Optional[float] = None,
    top_n: int = 20,
    include_full_table: bool = False,
) -> Dict[str, Any]:
    house_system = house_system or config.DEFAULT_HOUSE_SYSTEM
    zodiac_type = zodiac_type or config.DEFAULT_ZODIAC_TYPE
    try:
        if not events:
            return {"error": "events list is required and must be non-empty"}
        result = run_scan(
            natal_year, natal_month, natal_day, natal_lat, natal_lng,
            natal_tz_str, natal_tz_offset_minutes, house_system, zodiac_type,
            scan_start_hour, scan_start_minute, scan_end_hour, scan_end_minute,
            step_minutes, events,
            target_points=target_points,
            aspect_set=aspect_set,
            orb_threshold=orb_threshold,
            top_n=top_n,
            include_full_table=include_full_table,
        )
        if config.CONSOLE_RESULT_PREVIEW:
            print_scan_result(result)
        return result
    except Exception as e:
        logger.exception("rectif_scan failed")
        return {"error": str(e)}


def ping(message: str = "world") -> str:
    return f"pong: {message} (from astromcp, kerykeion engine loaded)"
