"""
Rectification scan engine: sweeps a range of candidate birth times and, for
each candidate, runs a set of events (each with its own technique) against
it - returning the REAL aspects found, not a score.

REWRITTEN to remove an invented scoring/ranking mechanism (summing per-
event "hits" into a weighted total_score, then ranking candidates by that
sum) that directly contradicted help_texts/rectification.md's "Absolute
rule: never invent a scoring or weighting scheme" - the old code combined
heterogeneous events into one made-up joint number and sorted by it, which
is exactly what that rule prohibits, and even include_full_table=True only
ever returned counts, never the real angle/orb/point data a person would
need to actually verify a candidate.

What this returns now, per candidate: the REAL matched aspects for every
event (point_a, point_b, aspect_deg, exact_orb, status - the same shape
`rectif_technique` returns), plus a single navigational aid,
`tightest_real_orb_deg` - the single closest REAL aspect found for that
candidate, across whichever one event happened to produce it. This is not
a combined/weighted score: it is not a sum, not multiplied by any weight,
and does not combine unlike things into one made-up quantity - it is
literally "the tightest angular orb this candidate actually showed",
directly meaningful in degrees on its own terms, the same way any single
`rectif_technique` result's tightest aspect is. It exists purely so a
person or LLM sweeping hundreds of candidates has somewhere reasonable to
look first; it is NOT evidence of anything by itself and must still be
read via the real per-event aspect data (or re-verified with an individual
`rectif_technique`/`rectif_movements_scan` call) before any candidate is
treated as confirmed - exactly the same "convenience sweep only" status
rectification.md already assigns this tool.

Supports second-level precision via step_seconds (falls back to
step_minutes * 60 if step_seconds is not given), for narrowing a candidate
window down from minutes to seconds once a broad region has been found.

Each event may specify `target_houses` (a list of house numbers, 1-12)
instead of (or alongside) `target_points`. When given, the natal-side
targets for that event are computed dynamically per candidate as the
"elements of house" (ruler, co-ruler, occupying planets - see
engine/houses.py) for those houses, per the Shestopalov/Aizin school
documented in help_texts/rectification.md. This must be recomputed per
candidate because house cusps (and therefore rulers/co-rulers/occupants)
shift with birth time.
"""

from typing import Optional, List, Dict, Any

from . import config
from .chart import build_subject, natal_points_dict, subject_raw, resolve_fixed_offset_minutes
from .houses import get_house_element_names
from .techniques import (
    technique_transit, technique_secondary_progression, technique_solar_arc,
    technique_solar_return, technique_lunar_return, technique_profection,
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

        per_event: Dict[str, Any] = {}
        tightest_orb: Optional[float] = None
        tightest_detail: Optional[Dict[str, Any]] = None

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

            elif technique == "lunar_return":
                computed, natal_pts, meta = technique_lunar_return(
                    n_raw, n_points,
                    house_system, zodiac_type,
                    ev["target_year"], ev["target_month"], ev["target_day"],
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
            ev_orb_threshold = ev.get("orb_threshold", orb_threshold)

            if technique == "profection":
                # Profections make a narrow, specific claim (just the Lord of
                # Year/Month/profected Ascendant) - natal_pts is already
                # narrowed to exactly those points by technique_profection,
                # so every aspect within orb is relevant, not just ones
                # matching target_houses/target_points.
                matched = [a for a in aspects if a["exact_orb"] <= ev_orb_threshold]
            else:
                if "target_houses" in ev:
                    ev_target_points = get_house_element_names(n_raw, ev["target_houses"])
                else:
                    ev_target_points = ev.get("target_points", list(target_points))
                matched = [
                    a for a in aspects
                    if a["point_b"] in ev_target_points and a["exact_orb"] <= ev_orb_threshold
                ]

            # Real data only - the actual aspects that matched, not a count.
            per_event[name] = {"technique": technique, "matched_aspects": matched}

            for a in matched:
                if tightest_orb is None or a["exact_orb"] < tightest_orb:
                    tightest_orb = a["exact_orb"]
                    tightest_detail = {"event": name, "technique": technique, **a}

        results.append({
            "hour": cand_hour,
            "minute": cand_minute,
            "second": cand_second,
            "tightest_real_orb_deg": tightest_orb,
            "tightest_real_orb_detail": tightest_detail,
            "per_event": per_event,
        })

    # Sort ONLY by the single tightest real aspect a candidate produced -
    # navigational convenience over one real measurement, never a combined/
    # weighted score across events. Candidates with no matched aspect at
    # all (tightest_real_orb_deg is None) sort last, listed separately
    # below rather than silently dropped.
    with_hits = [r for r in results if r["tightest_real_orb_deg"] is not None]
    without_hits = [r for r in results if r["tightest_real_orb_deg"] is None]
    with_hits.sort(key=lambda r: r["tightest_real_orb_deg"])

    out = {
        "candidates_tested": len(results),
        "step_seconds": step,
        "note": (
            "top_by_tightest_single_aspect is sorted by tightest_real_orb_deg "
            "- the single closest REAL aspect each candidate produced across "
            "all events - NOT a summed/weighted score across events (this "
            "tool no longer computes one; see help_texts/rectification.md's "
            "'Absolute rule: never invent a scoring or weighting scheme'). "
            "Read per_event.matched_aspects (or tightest_real_orb_detail) for "
            "the actual angle/orb/point data before treating any candidate "
            "as confirmed - this ordering is where to look first, not a "
            "verdict. Re-verify a promising candidate with an individual "
            "rectif_technique or rectif_movements_scan call."
        ),
        "candidates_with_no_matched_aspect": len(without_hits),
        "top_by_tightest_single_aspect": with_hits[:top_n],
    }
    if include_full_table:
        out["full_table"] = results
    return out
