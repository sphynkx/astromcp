"""
Rectification pipeline orchestrator.

Runs the FULL mandatory rectification sequence from help_texts/rectification.md
server-side in one call, returning structured data for every event × every
applicable technique. The Claude side submits a prepared event list and
receives a complete result matrix — no per-event round-trips needed.

Design:
  - All heavy computation (chart building, technique dispatch, criteria scans,
    intersection logic) happens here, inside the server process.
  - Concurrency: events within a single technique-pass are independent and run
    in a thread pool (chart/ephemeris calculations release the GIL via the C
    extension in pyswisseph).
  - The returned structure mirrors the "Mandatory final report format" from
    the methodology doc: per-event technique matrix + global auxiliary checks +
    intersection/surviving candidates + raw data for final verification.
  - No scoring, weighting, or ranking is invented — only documented methods'
    own literal outputs are reported (qualifying windows, aspect lists, orbs).
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from typing import Optional, List, Dict, Any

from . import config
from .chart import build_subject, natal_points_dict, subject_raw, resolve_fixed_offset_minutes
from .houses import get_house_element_names
from .techniques import (
    technique_transit, technique_secondary_progression, technique_solar_arc,
    technique_solar_return, technique_lunar_return, technique_profection,
)
from .aspects import compute_aspects
from .constants import DEFAULT_POINTS, LUMINARY_NAMES, ANGLE_KEYS, HOUSE_KEYS
from .criteria import run_three_movements_scan, run_timoshenko_scan, run_bonatti_scan, run_herich_scan
from .clustering import collect_transiting_degrees, build_degree_histogram, find_time_for_angle
from .trutina import run_trutina_hermetis

logger = logging.getLogger("astromcp")

# Max parallel workers for per-event technique computation.
# Each worker builds ephemeris charts (CPU-bound C code via pyswisseph),
# so more workers than CPU cores gives diminishing returns.
_MAX_WORKERS = 6


# ---------------------------------------------------------------------------
# Helper: build natal chart for a candidate time
# ---------------------------------------------------------------------------

def _build_natal(natal, cand_hour, cand_minute, cand_second, fixed_offset):
    """Build natal subject + raw + points for one candidate time."""
    subj, _, _ = build_subject(
        "natal", natal["year"], natal["month"], natal["day"],
        cand_hour, cand_minute, cand_second,
        natal["lat"], natal["lng"], None, fixed_offset,
        natal["house_system"], natal.get("zodiac_type", "Tropic"),
    )
    return subj, subject_raw(subj), natal_points_dict(subj)


# ---------------------------------------------------------------------------
# Helper: resolve event date fields based on precision
# ---------------------------------------------------------------------------

class _EventTooImprecise(Exception):
    """Raised when an event's precision is too coarse for the technique."""
    pass


def _resolve_event_date(ev, require_day=True):
    """
    Return (year, month, day) from an event dict, applying sensible defaults
    based on its ``precision`` field:

    - ``"date"`` / ``"datetime"``: year, month, day must all be present.
    - ``"month"``: year and month present; day defaults to 15.
    - ``"year"``: only year present.
        - If *require_day* is True (SA, SP, movements, transits),
          raise ``_EventTooImprecise`` — a ±6-month uncertainty exceeds
          the direction orb, making the result meaningless.
        - If *require_day* is False (future use / lenient mode),
          default to month=7, day=1.
    """
    year = ev["year"]
    precision = ev.get("precision", "date")

    if precision in ("date", "datetime"):
        return year, ev["month"], ev["day"]

    if precision == "month":
        return year, ev["month"], ev.get("day", 15)

    # precision == "year"
    if require_day:
        raise _EventTooImprecise(
            f"precision={precision!r}: year-only events are too imprecise "
            f"for direction / movement techniques (±6 months ≈ ±0.5° solar arc)"
        )
    return year, ev.get("month", 7), ev.get("day", 1)


# ---------------------------------------------------------------------------
# Per-event technique runners
# ---------------------------------------------------------------------------

def _run_solar_arc_for_event(natal, cand_h, cand_m, cand_s, fixed_offset, n_raw, n_points, ev):
    """Solar arc direction for one event at one candidate time. Returns aspects list."""
    ev_year, ev_month, ev_day = _resolve_event_date(ev)
    computed, natal_pts, meta = technique_solar_arc(
        natal["year"], natal["month"], natal["day"], cand_h, cand_m, cand_s,
        natal["lat"], natal["lng"], fixed_offset,
        natal["house_system"], natal.get("zodiac_type", "Tropic"),
        n_raw, n_points,
        ev_year, ev_month, ev_day,
    )
    asp_set = config.DEFAULT_ASPECT_SET
    orb_tbl = config.DEFAULT_ORB_TABLE_DIRECTION
    bonus = config.LUMINARY_ORB_BONUS_DIRECTION
    aspects = compute_aspects(computed, natal_pts, asp_set, orb_tbl, bonus, LUMINARY_NAMES)
    return {
        "technique": "solar_arc",
        "meta": meta,
        "aspects": aspects,
    }


def _run_secondary_progression_for_event(natal, cand_h, cand_m, cand_s, fixed_offset, n_raw, n_points, ev):
    ev_year, ev_month, ev_day = _resolve_event_date(ev)
    computed, natal_pts, meta = technique_secondary_progression(
        natal["year"], natal["month"], natal["day"], cand_h, cand_m, cand_s,
        natal["lat"], natal["lng"], fixed_offset,
        natal["house_system"], natal.get("zodiac_type", "Tropic"),
        n_raw, n_points,
        ev_year, ev_month, ev_day,
        "solar_arc_naibod",
    )
    aspects = compute_aspects(
        computed, natal_pts, config.DEFAULT_ASPECT_SET,
        config.DEFAULT_ORB_TABLE_DIRECTION, config.LUMINARY_ORB_BONUS_DIRECTION, LUMINARY_NAMES,
    )
    return {
        "technique": "secondary_progression",
        "meta": meta,
        "aspects": aspects,
    }


def _run_transit_for_event(natal, n_raw, n_points, ev):
    # event_tz_str/event_tz_offset_minutes/event_lat/event_lng are the field
    # names used everywhere else (scan.py, the technique functions, the MCP
    # tool params) - this used to read the wrong key ("tz_offset_minutes")
    # and ignore location entirely, silently defaulting to UTC+0 at the
    # natal birthplace for every event regardless of what was supplied.
    ev_tz_str = ev.get("event_tz_str")
    ev_tz_off = ev.get("event_tz_offset_minutes")
    if ev_tz_str is None and ev_tz_off is None:
        ev_tz_off = 0
    ev_year, ev_month, ev_day = _resolve_event_date(ev)
    computed, natal_pts, meta = technique_transit(
        n_raw, n_points,
        ev_year, ev_month, ev_day,
        ev.get("hour", 12), ev.get("minute", 0), ev.get("second", 0),
        ev.get("event_lat", natal["lat"]), ev.get("event_lng", natal["lng"]),
        ev_tz_str, ev_tz_off,
        natal["house_system"], natal.get("zodiac_type", "Tropic"),
    )
    aspects = compute_aspects(
        computed, natal_pts, config.DEFAULT_ASPECT_SET,
        config.DEFAULT_ORB_TABLE_TRANSIT, config.LUMINARY_ORB_BONUS_TRANSIT, LUMINARY_NAMES,
    )
    return {
        "technique": "transit",
        "meta": meta,
        "aspects": aspects,
    }


def _run_profection_for_event(natal, n_raw, n_points, ev):
    ev_tz_str = ev.get("event_tz_str")
    ev_tz_off = ev.get("event_tz_offset_minutes")
    if ev_tz_str is None and ev_tz_off is None:
        ev_tz_off = 0
    ev_year, ev_month, ev_day = _resolve_event_date(ev)
    computed, natal_pts, meta = technique_profection(
        natal["year"], natal["month"], natal["day"],
        n_raw, n_points,
        natal["house_system"], natal.get("zodiac_type", "Tropic"),
        ev_year, ev_month, ev_day,
        ev.get("hour", 12), ev.get("minute", 0), ev.get("second", 0),
        ev.get("event_lat", natal["lat"]), ev.get("event_lng", natal["lng"]),
        ev_tz_str, ev_tz_off,
    )
    aspects = compute_aspects(
        computed, natal_pts, config.DEFAULT_ASPECT_SET,
        config.DEFAULT_ORB_TABLE_TRANSIT, config.LUMINARY_ORB_BONUS_TRANSIT, LUMINARY_NAMES,
    )
    return {
        "technique": "profection",
        "meta": meta,
        "aspects": aspects,
    }


def _run_lunar_return_for_event(natal, n_raw, n_points, ev):
    ev_year, ev_month, ev_day = _resolve_event_date(ev)
    computed, natal_pts, meta = technique_lunar_return(
        n_raw, n_points,
        natal["house_system"], natal.get("zodiac_type", "Tropic"),
        ev_year, ev_month, ev_day,
        ev.get("event_lat", natal["lat"]), ev.get("event_lng", natal["lng"]),
    )
    aspects = compute_aspects(
        computed, natal_pts, config.DEFAULT_ASPECT_SET,
        config.DEFAULT_ORB_TABLE_TRANSIT, config.LUMINARY_ORB_BONUS_TRANSIT, LUMINARY_NAMES,
    )
    return {
        "technique": "lunar_return",
        "meta": meta,
        "aspects": aspects,
    }


# ---------------------------------------------------------------------------
# Extract angular aspects (the key discriminator for rectification)
# ---------------------------------------------------------------------------

_ANGULAR_POINT_NAMES = set(ANGLE_KEYS + HOUSE_KEYS)


def _extract_angular_aspects(aspects, max_orb=1.0):
    """Filter aspects where at least one side is an angle/cusp, within max_orb."""
    result = []
    for a in aspects:
        if a["exact_orb"] > max_orb:
            continue
        if a["point_a"] in _ANGULAR_POINT_NAMES or a["point_b"] in _ANGULAR_POINT_NAMES:
            result.append(a)
    return sorted(result, key=lambda x: x["exact_orb"])


def _best_angular_aspect(aspects):
    """Return the single tightest angular aspect, or None."""
    angular = _extract_angular_aspects(aspects, max_orb=2.0)
    return angular[0] if angular else None


# ---------------------------------------------------------------------------
# Process one event across the full technique stack at a fixed candidate time
# ---------------------------------------------------------------------------

def _process_event_for_candidate(natal, fixed_offset, n_raw, n_points, cand_h, cand_m, cand_s, ev):
    """
    Run all applicable techniques for one event at one candidate birth time.
    Returns a dict of technique_name -> result summary.
    """
    results = {}
    precision = ev.get("precision", "date")  # "datetime", "date", "month", "year"

    # Solar arc — needs at least month-level precision
    try:
        sa = _run_solar_arc_for_event(natal, cand_h, cand_m, cand_s, fixed_offset, n_raw, n_points, ev)
        best = _best_angular_aspect(sa["aspects"])
        results["solar_arc"] = {
            "best_angular_aspect": best,
            "total_aspects": len(sa["aspects"]),
            "angular_aspects_under_1deg": len(_extract_angular_aspects(sa["aspects"], 1.0)),
            "meta": sa["meta"],
        }
    except _EventTooImprecise as e:
        results["solar_arc"] = {"error": str(e)}
    except Exception as e:
        results["solar_arc"] = {"error": str(e)}

    # Secondary progression — needs at least month-level precision
    try:
        sp = _run_secondary_progression_for_event(natal, cand_h, cand_m, cand_s, fixed_offset, n_raw, n_points, ev)
        best = _best_angular_aspect(sp["aspects"])
        results["secondary_progression"] = {
            "best_angular_aspect": best,
            "total_aspects": len(sp["aspects"]),
            "angular_aspects_under_1deg": len(_extract_angular_aspects(sp["aspects"], 1.0)),
        }
    except _EventTooImprecise as e:
        results["secondary_progression"] = {"error": str(e)}
    except Exception as e:
        results["secondary_progression"] = {"error": str(e)}

    # Transit — only when event has a known clock time
    if precision == "datetime":
        try:
            tr = _run_transit_for_event(natal, n_raw, n_points, ev)
            best = _best_angular_aspect(tr["aspects"])
            results["transit"] = {
                "best_angular_aspect": best,
                "total_aspects": len(tr["aspects"]),
                "angular_aspects_under_1deg": len(_extract_angular_aspects(tr["aspects"], 1.0)),
            }
        except Exception as e:
            results["transit"] = {"error": str(e)}

    # Profection — for date-level and above
    if precision in ("date", "datetime"):
        try:
            pf = _run_profection_for_event(natal, n_raw, n_points, ev)
            best = _best_angular_aspect(pf["aspects"])
            results["profection"] = {
                "best_angular_aspect": best,
                "total_aspects": len(pf["aspects"]),
            }
        except Exception as e:
            results["profection"] = {"error": str(e)}

    # Lunar return — for date-level and above
    if precision in ("date", "datetime"):
        try:
            lr = _run_lunar_return_for_event(natal, n_raw, n_points, ev)
            best = _best_angular_aspect(lr["aspects"])
            results["lunar_return"] = {
                "best_angular_aspect": best,
                "total_aspects": len(lr["aspects"]),
                "meta": lr["meta"],
            }
        except Exception as e:
            results["lunar_return"] = {"error": str(e)}

    return results


# ---------------------------------------------------------------------------
# Main pipeline entry point
# ---------------------------------------------------------------------------

def run_rectification_pipeline(
    natal_year: int, natal_month: int, natal_day: int,
    natal_lat: float, natal_lng: float,
    natal_tz_str: Optional[str],
    natal_tz_offset_minutes: Optional[int],
    house_system: str,
    zodiac_type: str,
    scan_start_hour: int, scan_start_minute: int,
    scan_end_hour: int, scan_end_minute: int,
    step_minutes: int,
    events: List[Dict[str, Any]],
    mother_year: Optional[int] = None, mother_month: Optional[int] = None, mother_day: Optional[int] = None,
    mother_hour: Optional[int] = None, mother_minute: Optional[int] = None, mother_second: Optional[int] = None,
    mother_lat: Optional[float] = None, mother_lng: Optional[float] = None,
    mother_tz_str: Optional[str] = None, mother_tz_offset_minutes: Optional[int] = None,
    initial_guess_hour: Optional[int] = None, initial_guess_minute: Optional[int] = None,
    direction_orb_deg: float = 0.5,
    transit_orb_deg: float = 1.5,
    candidate_times: Optional[List[Dict[str, int]]] = None,
) -> Dict[str, Any]:
    """
    Full rectification pipeline. Accepts birth data + annotated event list,
    returns a structured result covering every step of the mandatory sequence.

    Each event in `events` is a dict with:
      - name (str): human-readable label
      - year, month, day (int): event date
      - hour, minute, second (int, optional): event time if known
      - precision (str): "datetime" | "date" | "month" | "year"
      - target_houses (list[int]): houses relevant to this event
      - category (str): "personal" | "career" | "minor"
      - tz_offset_minutes (int, optional): event timezone offset

    `candidate_times` (optional): specific times to verify via solar_arc
      direct check, e.g. [{"hour": 10, "minute": 0, "second": 0}, ...].
      If not given, candidates are derived from scan range center + top
      movements_scan intersections.

    Returns a dict with:
      - trutina: Trutina Hermetis results
      - movements_scan: per-event qualifying windows
      - movements_intersection: intersection of all events' windows
      - candidate_verification: per-candidate × per-event solar_arc results
      - auxiliary: Bonatti, Herich, degree_clustering results
      - summary: counts and completeness check
      - elapsed_seconds: total computation time
    """
    t0 = time.time()

    natal = {
        "year": natal_year, "month": natal_month, "day": natal_day,
        "lat": natal_lat, "lng": natal_lng,
        "house_system": house_system, "zodiac_type": zodiac_type,
    }

    fixed_offset = resolve_fixed_offset_minutes(
        natal_tz_str, natal_tz_offset_minutes,
        natal_year, natal_month, natal_day,
        scan_start_hour, scan_start_minute, 0,
    )

    result = {
        "natal": natal,
        "fixed_offset_minutes": fixed_offset,
        "scan_range": {
            "start": f"{scan_start_hour:02d}:{scan_start_minute:02d}",
            "end": f"{scan_end_hour:02d}:{scan_end_minute:02d}",
            "step_minutes": step_minutes,
        },
        "events_count": len(events),
    }

    # -----------------------------------------------------------------------
    # Step 2: Trutina Hermetis
    # -----------------------------------------------------------------------
    logger.info("pipeline: running Trutina Hermetis...")
    try:
        guess_h = initial_guess_hour if initial_guess_hour is not None else (scan_start_hour + scan_end_hour) // 2
        guess_m = initial_guess_minute if initial_guess_minute is not None else (scan_start_minute + scan_end_minute) // 2
        trutina = run_trutina_hermetis(
            natal_year, natal_month, natal_day, natal_lat, natal_lng,
            natal_tz_str, natal_tz_offset_minutes, "P", zodiac_type,
            guess_h, guess_m, 0, 30,
            mother_year, mother_month, mother_day,
            mother_hour, mother_minute, mother_second,
            mother_lat, mother_lng, mother_tz_str, mother_tz_offset_minutes,
        )
        result["trutina"] = trutina
    except Exception as e:
        logger.exception("pipeline: trutina failed")
        result["trutina"] = {"error": str(e)}

    # -----------------------------------------------------------------------
    # Steps 4-7: Movements scan for every event (parallelized)
    # -----------------------------------------------------------------------
    logger.info("pipeline: running movements_scan for %d events...", len(events))
    movements_results = {}

    def _run_movements_for_event(ev):
        name = ev["name"]
        try:
            ev_year, ev_month, ev_day = _resolve_event_date(ev)
            r = run_three_movements_scan(
                natal_year, natal_month, natal_day, natal_lat, natal_lng,
                natal_tz_str, natal_tz_offset_minutes, house_system, zodiac_type,
                scan_start_hour, scan_start_minute, scan_end_hour, scan_end_minute,
                step_minutes,
                ev_year, ev_month, ev_day,
                ev.get("hour", 12), ev.get("minute", 0), ev.get("second", 0),
                ev.get("target_houses"), None,
                direction_orb_deg, transit_orb_deg,
                event_lat=ev.get("event_lat"), event_lng=ev.get("event_lng"),
                event_tz_str=ev.get("event_tz_str"), event_tz_offset_minutes=ev.get("event_tz_offset_minutes"),
            )
            return name, r
        except _EventTooImprecise as e:
            logger.info("pipeline: movements_scan skipped for %s (%s)", name, e)
            return name, {"skipped": True, "reason": str(e)}
        except Exception as e:
            logger.exception("pipeline: movements_scan failed for %s", name)
            return name, {"error": str(e)}

    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
        futures = {pool.submit(_run_movements_for_event, ev): ev for ev in events}
        for future in as_completed(futures):
            name, r = future.result()
            movements_results[name] = r
            qc = r.get("candidates_qualifying_raw_count", "?")
            ct = r.get("candidates_tested", "?")
            logger.info("  movements_scan [%s]: %s/%s qualify", name, qc, ct)

    result["movements_scan"] = movements_results

    # -----------------------------------------------------------------------
    # Step 8: Intersection of qualifying windows
    # -----------------------------------------------------------------------
    logger.info("pipeline: computing intersection...")
    intersection = _compute_intersection(movements_results, step_minutes * 60)
    result["movements_intersection"] = intersection

    # -----------------------------------------------------------------------
    # Step 9: Auxiliary checks (Bonatti, Herich, degree_clustering)
    # -----------------------------------------------------------------------
    logger.info("pipeline: running auxiliary scans...")
    auxiliary = {}

    try:
        auxiliary["bonatti"] = run_bonatti_scan(
            natal_year, natal_month, natal_day, natal_lat, natal_lng,
            natal_tz_str, natal_tz_offset_minutes, house_system, zodiac_type,
            scan_start_hour, scan_start_minute, scan_end_hour, scan_end_minute,
            step_minutes,
        )
    except Exception as e:
        auxiliary["bonatti"] = {"error": str(e)}

    try:
        auxiliary["herich"] = run_herich_scan(
            natal_year, natal_month, natal_day, natal_lat, natal_lng,
            natal_tz_str, natal_tz_offset_minutes, house_system, zodiac_type,
            scan_start_hour, scan_start_minute, scan_end_hour, scan_end_minute,
            step_minutes, orb_deg=3.0,
        )
    except Exception as e:
        auxiliary["herich"] = {"error": str(e)}

    # Degree clustering — needs enough events with exact dates
    dated_events = []
    for ev in events:
        try:
            y, m, d = _resolve_event_date(ev)
            dated_events.append({"year": y, "month": m, "day": d})
        except _EventTooImprecise:
            pass  # year-only events excluded from clustering
    if len(dated_events) >= 10:
        try:
            auxiliary["degree_clustering"] = {
                "method": "degree_clustering",
                "data": _run_degree_clustering(
                    dated_events, natal_year, natal_month, natal_day,
                    natal_lat, natal_lng, natal_tz_str, natal_tz_offset_minutes,
                    house_system, zodiac_type,
                ),
            }
        except Exception as e:
            auxiliary["degree_clustering"] = {"error": str(e)}
    else:
        auxiliary["degree_clustering"] = {
            "skipped": True,
            "reason": f"Only {len(dated_events)} dated events, need >=10 for Israitel/Brady method",
        }

    result["auxiliary"] = auxiliary

    # -----------------------------------------------------------------------
    # Step 11: Direct verification of candidate times via solar_arc
    # -----------------------------------------------------------------------
    # Build candidate list from: explicitly provided, intersection peaks,
    # most-corroborated-individual-events, scan midpoint (last resort) -
    # see _build_candidate_list's own tiering and _most_corroborated_
    # candidates' docstring for why the midpoint is no longer the first
    # fallback once the intersections are empty.
    cands, candidate_fallback_tier = _build_candidate_list(
        candidate_times, intersection, movements_results, step_minutes * 60,
        scan_start_hour, scan_start_minute, scan_end_hour, scan_end_minute,
    )
    result["candidate_selection_tier"] = candidate_fallback_tier
    logger.info(
        "pipeline: verifying %d candidate times against all events (selection tier: %s)...",
        len(cands), candidate_fallback_tier,
    )

    verification = {}
    for cand in cands:
        cand_label = f"{cand['hour']:02d}:{cand['minute']:02d}:{cand.get('second', 0):02d}"
        ch, cm, cs = cand["hour"], cand["minute"], cand.get("second", 0)

        _, n_raw, n_points = _build_natal(natal, ch, cm, cs, fixed_offset)
        per_event = {}

        for ev in events:
            per_event[ev["name"]] = _process_event_for_candidate(
                natal, fixed_offset, n_raw, n_points, ch, cm, cs, ev
            )

        verification[cand_label] = per_event
        logger.info("  verified candidate %s against %d events", cand_label, len(events))

    result["candidate_verification"] = verification


    # -----------------------------------------------------------------------
    # Summary / completeness
    # -----------------------------------------------------------------------
    total_cells = 0
    filled_cells = 0
    for cand_label, per_event in verification.items():
        for ev_name, techs in per_event.items():
            for tech_name, tech_result in techs.items():
                total_cells += 1
                if "error" not in tech_result:
                    filled_cells += 1

    result["summary"] = {
        "events_processed": len(events),
        "candidates_verified": len(cands),
        "total_technique_cells": total_cells,
        "filled_cells": filled_cells,
        "personal_events": sum(1 for e in events if e.get("category") == "personal"),
        "career_events": sum(1 for e in events if e.get("category") == "career"),
        "minor_events": sum(1 for e in events if e.get("category") == "minor"),
    }

    elapsed = time.time() - t0
    result["elapsed_seconds"] = round(elapsed, 1)
    logger.info("pipeline: completed in %.1f seconds", elapsed)

    return result


# ---------------------------------------------------------------------------
# Intersection logic
# ---------------------------------------------------------------------------

def _time_to_seconds(time_str: str) -> int:
    """Parse "HH:MM:SS" to total seconds."""
    parts = time_str.split(":")
    return int(parts[0]) * 3600 + int(parts[1]) * 60 + (int(parts[2]) if len(parts) > 2 else 0)


def _seconds_to_time(total_sec: int) -> str:
    h = (total_sec // 3600) % 24
    m = (total_sec % 3600) // 60
    s = total_sec % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def _windows_to_second_set(windows, concordance_min=2):
    """Convert qualifying_windows to a set of second-values for intersection."""
    seconds = set()
    for w in windows:
        if w.get("movements_hit", 0) < concordance_min:
            continue
        start = _time_to_seconds(w["start"])
        end = _time_to_seconds(w["end"])
        # windows are inclusive [start, end], step is unknown here so we
        # just add start and end; for finer intersection we'd need the step
        seconds.add(start)
        seconds.add(end)
        # Also add all minutes in between for 1-min step assumption
        for s in range(start, end + 1, 60):
            seconds.add(s)
    return seconds


def _compute_intersection(movements_results, step_seconds):
    """
    Intersect qualifying windows across all events.
    Returns windows that survive at various concordance thresholds.
    """
    # Collect per-event second sets at 3/3 and 2/3 levels
    all_3of3 = []
    all_2of3 = []

    for name, r in movements_results.items():
        if "error" in r or r.get("skipped"):
            continue
        windows = r.get("qualifying_windows", [])
        s3 = _windows_to_second_set(windows, concordance_min=3)
        s2 = _windows_to_second_set(windows, concordance_min=2)
        if s3:
            all_3of3.append({"name": name, "seconds": s3})
        if s2:
            all_2of3.append({"name": name, "seconds": s2})

    # Strict intersection: all events at 3/3
    if all_3of3:
        strict = all_3of3[0]["seconds"]
        for item in all_3of3[1:]:
            strict = strict & item["seconds"]
        strict_times = sorted(strict)
    else:
        strict_times = []

    # Relaxed intersection: all events at >=2/3
    if all_2of3:
        relaxed = all_2of3[0]["seconds"]
        for item in all_2of3[1:]:
            relaxed = relaxed & item["seconds"]
        relaxed_times = sorted(relaxed)
    else:
        relaxed_times = []

    # Per-event selectivity (how many candidates qualify out of total)
    selectivity = {}
    for name, r in movements_results.items():
        if "error" in r:
            continue
        selectivity[name] = {
            "qualifying": r.get("candidates_qualifying_raw_count", 0),
            "tested": r.get("candidates_tested", 0),
            "ratio": round(r.get("candidates_qualifying_raw_count", 0) / max(r.get("candidates_tested", 1), 1), 3),
        }

    return {
        "strict_3of3_intersection": [_seconds_to_time(s) for s in strict_times],
        "relaxed_2of3_intersection": [_seconds_to_time(s) for s in relaxed_times],
        "events_contributing_3of3": len(all_3of3),
        "events_contributing_2of3": len(all_2of3),
        "per_event_selectivity": selectivity,
    }


# ---------------------------------------------------------------------------
# Candidate list builder
# ---------------------------------------------------------------------------

def _most_corroborated_candidates(movements_results, step_seconds, top_n=10):
    """
    Fallback used when NEITHER the strict (all-events, 3-of-3) nor the
    relaxed (all-events, >=2-of-3) intersection has any surviving
    candidate at all - which happens whenever even one event's
    qualifying windows fail to overlap with the rest (a real, common
    outcome with a large, heterogeneous event list, not a bug).

    Finds the time(s) corroborated by the largest NUMBER of separate
    events' own 3-of-3 windows. This is not an invented score: it is a
    direct tally of how many independent applications of the same
    documented method (Grishchenyuk's own 3-of-3 threshold, applied once
    per event) agree on a given candidate - the same kind of counting
    the strict/relaxed intersection above already does, just relaxed
    from "agreement across ALL events" to "agreement across the most
    events available" when unanimous agreement doesn't exist. Ties are
    all returned, sorted chronologically, capped at top_n.

    This is a STARTING POINT for step 11's direct verification, not a
    result on its own - replaces the previous fallback (the bare scan-
    range midpoint), which carried no evidential weight at all.
    """
    from collections import defaultdict
    counts: Dict[int, int] = defaultdict(int)
    for name, r in movements_results.items():
        if "error" in r:
            continue
        seen_for_this_event = set()
        for w in r.get("qualifying_windows", []):
            if w.get("movements_hit", 0) < 3:
                continue
            start, end = _time_to_seconds(w["start"]), _time_to_seconds(w["end"])
            for s in range(start, end + 1, max(step_seconds, 1)):
                seen_for_this_event.add(s)
        for s in seen_for_this_event:
            counts[s] += 1
    if not counts:
        return []
    max_count = max(counts.values())
    top_seconds = sorted(s for s, c in counts.items() if c == max_count)
    return [
        {
            "hour": s // 3600, "minute": (s % 3600) // 60, "second": s % 60,
            "corroborating_events": max_count,
        }
        for s in top_seconds[:top_n]
    ]


def _build_candidate_list(
    explicit_candidates, intersection, movements_results, step_seconds,
    start_h, start_m, end_h, end_m,
):
    """Build the list of candidate times to verify."""
    cands = []
    fallback_tier = None

    # 1. Explicitly provided candidates
    if explicit_candidates:
        for c in explicit_candidates:
            cands.append({"hour": c["hour"], "minute": c["minute"], "second": c.get("second", 0)})
        if cands:
            fallback_tier = "explicit_candidates"

    # 2. From intersection results — pick representative times
    for time_str in intersection.get("strict_3of3_intersection", [])[:10]:
        parts = time_str.split(":")
        c = {"hour": int(parts[0]), "minute": int(parts[1]), "second": int(parts[2]) if len(parts) > 2 else 0}
        if not _cand_in_list(c, cands):
            cands.append(c)
            fallback_tier = fallback_tier or "strict_3of3_intersection"

    # 3. From relaxed intersection (if strict is empty)
    if not intersection.get("strict_3of3_intersection"):
        for time_str in intersection.get("relaxed_2of3_intersection", [])[:10]:
            parts = time_str.split(":")
            c = {"hour": int(parts[0]), "minute": int(parts[1]), "second": int(parts[2]) if len(parts) > 2 else 0}
            if not _cand_in_list(c, cands):
                cands.append(c)
                fallback_tier = fallback_tier or "relaxed_2of3_intersection"

    # 4. Most-corroborated-by-individual-events fallback, when BOTH
    #    intersections above are empty - see _most_corroborated_candidates'
    #    own docstring for why this is not invented scoring. Far more
    #    informative than falling straight to the scan-range midpoint.
    if not cands:
        for c in _most_corroborated_candidates(movements_results, step_seconds):
            if not _cand_in_list(c, cands):
                cands.append(c)
                fallback_tier = fallback_tier or "most_corroborated_individual_events"

    # 5. Scan range midpoint - absolute last resort, only when there is
    #    truly no signal anywhere (e.g. every single event errored out).
    if not cands:
        mid_h = (start_h + end_h) // 2
        mid_m = (start_m + end_m) // 2
        cands.append({"hour": mid_h, "minute": mid_m, "second": 0})
        fallback_tier = "scan_range_midpoint_no_signal"

    return cands, fallback_tier


def _cand_in_list(c, cands):
    for existing in cands:
        if existing["hour"] == c["hour"] and existing["minute"] == c["minute"] and existing.get("second", 0) == c.get("second", 0):
            return True
    return False



# ---------------------------------------------------------------------------
# Degree clustering helper
# ---------------------------------------------------------------------------

def _run_degree_clustering(dated_events, natal_year, natal_month, natal_day,
                           natal_lat, natal_lng, natal_tz_str, natal_tz_offset_minutes,
                           house_system, zodiac_type):
    records = collect_transiting_degrees(dated_events, 1.0)
    histogram = build_degree_histogram(
        records, natal_year, natal_month, natal_day, natal_lat, natal_lng, 1.0, 2.0,
    )
    top_peaks = histogram["peaks_excluding_natal_planet_degrees"][:10]

    fixed_offset = resolve_fixed_offset_minutes(
        natal_tz_str, natal_tz_offset_minutes,
        natal_year, natal_month, natal_day, 12, 0, 0,
    )
    for peak in top_peaks:
        peak["as_ascendant_time"] = find_time_for_angle(
            peak["degree"], natal_year, natal_month, natal_day,
            natal_lat, natal_lng, fixed_offset, house_system, zodiac_type, "ascendant",
        )["candidate_time"]
        peak["as_medium_coeli_time"] = find_time_for_angle(
            peak["degree"], natal_year, natal_month, natal_day,
            natal_lat, natal_lng, fixed_offset, house_system, zodiac_type, "medium_coeli",
        )["candidate_time"]

    histogram["peaks_excluding_natal_planet_degrees"] = top_peaks
    return histogram
