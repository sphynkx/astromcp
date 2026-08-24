"""
Rectification scan engine: sweeps a range of candidate birth times, applies
a set of events (each with its own technique) to each candidate, scores
aspect hits, and returns a ranked table of candidates.

Supports second-level precision via step_seconds (falls back to
step_minutes * 60 if step_seconds is not given), for narrowing a candidate
window down from minutes to seconds once a broad region has been found.
"""

from typing import Optional, List, Dict, Any

from . import config
from .chart import build_subject, natal_points_dict, subject_raw, resolve_fixed_offset_minutes
from .techniques import (
    technique_transit, technique_secondary_progression, technique_solar_arc,
    technique_solar_return, technique_profection,
)
from .aspects import compute_aspects
from .constants import LUMINARY_NAMES


def run_scan(
    natal_year: int, natal_month: int, natal_day: int,
    natal_lat: float, natal_lng: float,
    natal_tz_str: Optional[str], natal_tz_offset_minutes: Optional[int],
    house_system: str, zodiac_type: str,
    scan_start_hour: int, scan_start_minute: int,
    scan_end_hour: int, scan_end_minute: int,
    step_minutes: int,
    events: List[Dict[str, Any]],
    target_points: Optional[List[str]] = None,
    aspect_set: Optional[List[float]] = None,
    orb_threshold: Optional[float] = None,
    top_n: int = 20,
    include_full_table: bool = False,
    scan_start_second: int = 0,
    scan_end_second: int = 59,
    step_seconds: Optional[int] = None,
) -> Dict[str, Any]:
    if target_points is None:
        target_points = config.DEFAULT_SCAN_TARGET_POINTS
    if aspect_set is None:
        aspect_set = config.DEFAULT_SCAN_ASPECT_SET
    if orb_threshold is None:
        orb_threshold = config.DEFAULT_SCAN_ORB_THRESHOLD

    fixed_offset = resolve_fixed_offset_minutes(
        natal_tz_str, natal_tz_offset_minutes,
        natal_year, natal_month, natal_day, scan_start_hour, scan_start_minute, scan_start_second,
    )

    start_total_sec = scan_start_hour * 3600 + scan_start_minute * 60 + scan_start_second
    end_total_sec = scan_end_hour * 3600 + scan_end_minute * 60 + scan_end_second
    if end_total_sec < start_total_sec:
        end_total_sec += 24 * 3600  # allow wrap past midnight

    step = step_seconds if step_seconds is not None else step_minutes * 60
    if step <= 0:
        raise ValueError("step must be positive (step_seconds, or step_minutes * 60)")

    candidates = list(range(start_total_sec, end_total_sec + 1, step))

    results = []
    for total_sec in candidates:
        cand_hour = (total_sec // 3600) % 24
        cand_minute = (total_sec % 3600) // 60
        cand_second = total_sec % 60

        natal_subject, _, _ = build_subject(
            "natal", natal_year, natal_month, natal_day, cand_hour, cand_minute, cand_second,
            natal_lat, natal_lng, None, fixed_offset, house_system, zodiac_type,
        )
        n_raw = subject_raw(natal_subject)
        n_points = natal_points_dict(natal_subject)

        per_event = {}
        total_score = 0.0

        for ev in events:
            name = ev["name"]
            technique = ev["technique"]

            if technique == "transit":
                ev_tz_str = ev.get("event_tz_str")
                ev_tz_off = ev.get("event_tz_offset_minutes")
                if ev_tz_str is None and ev_tz_off is None:
                    ev_tz_off = 0
                computed, natal_pts, meta = technique_transit(
                    n_raw, n_points,
                    ev["target_year"], ev["target_month"], ev["target_day"],
                    ev.get("target_hour", 12), ev.get("target_minute", 0), ev.get("target_second", 0),
                    ev.get("event_lat", natal_lat), ev.get("event_lng", natal_lng),
                    ev_tz_str, ev_tz_off,
                    house_system, zodiac_type,
                )
                orb_tbl = ev.get("orb_table", config.DEFAULT_ORB_TABLE_TRANSIT)
                bonus = ev.get("luminary_orb_bonus", config.LUMINARY_ORB_BONUS_TRANSIT)

            elif technique == "secondary_progression":
                computed, natal_pts, meta = technique_secondary_progression(
                    natal_year, natal_month, natal_day, cand_hour, cand_minute, cand_second,
                    natal_lat, natal_lng, fixed_offset, house_system, zodiac_type,
                    n_raw, n_points,
                    ev["target_year"], ev["target_month"], ev["target_day"],
                    ev.get("angle_method", "direct_progressed_angles"),
                )
                orb_tbl = ev.get("orb_table", config.DEFAULT_ORB_TABLE_DIRECTION)
                bonus = ev.get("luminary_orb_bonus", config.LUMINARY_ORB_BONUS_DIRECTION)

            elif technique == "solar_arc":
                computed, natal_pts, meta = technique_solar_arc(
                    natal_year, natal_month, natal_day, cand_hour, cand_minute, cand_second,
                    natal_lat, natal_lng, fixed_offset, house_system, zodiac_type,
                    n_raw, n_points,
                    ev["target_year"], ev["target_month"], ev["target_day"],
                )
                orb_tbl = ev.get("orb_table", config.DEFAULT_ORB_TABLE_DIRECTION)
                bonus = ev.get("luminary_orb_bonus", config.LUMINARY_ORB_BONUS_DIRECTION)

            elif technique == "solar_return":
                computed, natal_pts, meta = technique_solar_return(
                    natal_month, natal_day,
                    n_raw, n_points,
                    house_system, zodiac_type,
                    ev["target_year"],
                    ev.get("event_lat", natal_lat), ev.get("event_lng", natal_lng),
                )
                orb_tbl = ev.get("orb_table", config.DEFAULT_ORB_TABLE_TRANSIT)
                bonus = ev.get("luminary_orb_bonus", config.LUMINARY_ORB_BONUS_TRANSIT)

            elif technique == "profection":
                ev_tz_str = ev.get("event_tz_str")
                ev_tz_off = ev.get("event_tz_offset_minutes")
                if ev_tz_str is None and ev_tz_off is None:
                    ev_tz_off = 0
                computed, natal_pts, meta = technique_profection(
                    natal_year, natal_month, natal_day,
                    n_raw, n_points, house_system, zodiac_type,
                    ev["target_year"], ev["target_month"], ev["target_day"],
                    ev.get("target_hour", 12), ev.get("target_minute", 0), ev.get("target_second", 0),
                    ev.get("event_lat", natal_lat), ev.get("event_lng", natal_lng),
                    ev_tz_str, ev_tz_off,
                )
                orb_tbl = ev.get("orb_table", config.DEFAULT_ORB_TABLE_TRANSIT)
                bonus = ev.get("luminary_orb_bonus", config.LUMINARY_ORB_BONUS_TRANSIT)

            else:
                per_event[name] = {"error": f"unknown technique {technique}"}
                continue

            asp_set = ev.get("aspect_set", list(aspect_set))
            aspects = compute_aspects(computed, natal_pts, asp_set, orb_tbl, bonus, LUMINARY_NAMES)

            if technique == "profection":
                # Profections make a narrow, specific claim (just the Lord of
                # Year/Month/profected Ascendant) - score against ALL of
                # natal_pts (which technique_profection already narrowed to
                # exactly those points), not the caller's general
                # target_points list (which is built for angle/luminary
                # scanning and would silently score 0 here otherwise).
                ev_orb_threshold = ev.get("orb_threshold", orb_threshold)
                score = sum(1 for a in aspects if a["exact_orb"] <= ev_orb_threshold)
            else:
                ev_target_points = ev.get("target_points", list(target_points))
                ev_orb_threshold = ev.get("orb_threshold", orb_threshold)
                score = sum(
                    1 for a in aspects
                    if a["point_b"] in ev_target_points and a["exact_orb"] <= ev_orb_threshold
                )

            weight = ev.get("weight", 1.0)
            weighted_score = score * weight
            total_score += weighted_score
            per_event[name] = {"score": score, "weighted_score": weighted_score}

        results.append({
            "hour": cand_hour,
            "minute": cand_minute,
            "second": cand_second,
            "total_score": round(total_score, 4),
            "per_event": per_event,
        })

    results_sorted = sorted(results, key=lambda r: -r["total_score"])

    out = {
        "candidates_tested": len(results),
        "step_seconds": step,
        "top_results": results_sorted[:top_n],
    }
    if include_full_table:
        out["full_table"] = results
    return out
