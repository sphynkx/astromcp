"""
Literal reproductions of documented rectification decision rules.

These are NOT scoring/ranking tools. engine/scan.py sums an arbitrary
hit-count across many events - a heuristic invented for this service, not
a documented method, and should be treated as exploratory only (see
help_texts/rectification.md). The functions here instead test ONE event
against ONE named author's exact, published rule and report which
candidate times satisfy it - full stop. Where an author states a
threshold ("3 of 3 movements concordant means ~100% probability"), that
threshold is reproduced verbatim; nothing is added, weighted, or combined
across events by this module. Combining evidence across several events is
done by set intersection (only keep candidates that qualify for EVERY
event checked), matching the iterative-narrowing practice documented by
A. Budarovsky and S. Aizin - not by summing anything.
"""

from typing import Optional, List, Dict, Any

from . import config
from .chart import build_subject, natal_points_dict, subject_raw, resolve_fixed_offset_minutes
from .houses import get_house_element_names
from .techniques import technique_transit, technique_secondary_progression, technique_symbolic_direction
from .aspects import compute_aspects
from .constants import LUMINARY_NAMES

HARD_ASPECTS = (0, 90, 180)


def _has_hit(computed, natal_pts, targets, orb_deg) -> bool:
    orb_table = {deg: orb_deg for deg in HARD_ASPECTS}
    aspects = compute_aspects(computed, natal_pts, HARD_ASPECTS, orb_table, 0.0, LUMINARY_NAMES)
    return any(a["point_b"] in targets and a["exact_orb"] <= orb_deg for a in aspects)


def run_three_movements_scan(
    natal_year: int, natal_month: int, natal_day: int,
    natal_lat: float, natal_lng: float,
    natal_tz_str: Optional[str], natal_tz_offset_minutes: Optional[int],
    house_system: str, zodiac_type: str,
    scan_start_hour: int, scan_start_minute: int,
    scan_end_hour: int, scan_end_minute: int,
    step_minutes: int,
    target_year: int, target_month: int, target_day: int,
    target_houses: Optional[List[int]] = None,
    target_points: Optional[List[str]] = None,
    direction_orb_deg: float = 1.0,
    transit_orb_deg: float = 3.0,
    scan_start_second: int = 0, scan_end_second: int = 59,
    step_seconds: Optional[int] = None,
) -> Dict[str, Any]:
    """
    A. Grishchenyuk (1996), transcribing the Zaprjagaev -> Vronsky ->
    Shestopalov method (St. Petersburg Academy of Astrology): a life event
    is considered confirmed at a candidate birth time when at least 2 of 3
    independent "movements" - secondary progression, "perfection" (whole-
    chart symbolic direction at 30 deg/year), and transit - each produce
    at least one hard aspect (conjunction/square/opposition) to that
    event's house elements (ruler, co-ruler, occupying planets). The
    source states this threshold explicitly: 3-of-3 concordance means
    ~100% probability the event maps to this candidate time, 2-of-3 means
    ~66%. Below 2, the source does not consider the event confirmed at
    that time at all.

    This function reproduces exactly that rule - it does not sum, weight,
    or rank anything. It reports which of the three movements hit for
    every candidate, and returns only the candidates meeting the author's
    own >=2-of-3 threshold, listed in chronological order (not by any
    score). house_system should be Koch ("K") to match the source's own
    stated requirement for this technique.
    """
    fixed_offset = resolve_fixed_offset_minutes(
        natal_tz_str, natal_tz_offset_minutes,
        natal_year, natal_month, natal_day, scan_start_hour, scan_start_minute, scan_start_second,
    )
    start_total_sec = scan_start_hour * 3600 + scan_start_minute * 60 + scan_start_second
    end_total_sec = scan_end_hour * 3600 + scan_end_minute * 60 + scan_end_second
    if end_total_sec < start_total_sec:
        end_total_sec += 24 * 3600
    step = step_seconds if step_seconds is not None else step_minutes * 60
    if step <= 0:
        raise ValueError("step must be positive (step_seconds, or step_minutes * 60)")
    candidates = list(range(start_total_sec, end_total_sec + 1, step))

    qualifying = []
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

        if target_houses:
            targets = get_house_element_names(n_raw, target_houses)
        else:
            targets = target_points or list(config.DEFAULT_SCAN_TARGET_POINTS)

        prog_computed, prog_natal, _ = technique_secondary_progression(
            natal_year, natal_month, natal_day, cand_hour, cand_minute, cand_second,
            natal_lat, natal_lng, fixed_offset, house_system, zodiac_type,
            n_raw, n_points, target_year, target_month, target_day,
            "direct_progressed_angles",
        )
        progression_hit = _has_hit(prog_computed, prog_natal, targets, direction_orb_deg)

        perf_computed, perf_natal, _ = technique_symbolic_direction(
            natal_year, natal_month, natal_day, cand_hour, cand_minute, cand_second,
            natal_lat, natal_lng, fixed_offset, house_system, zodiac_type,
            n_raw, n_points, target_year, target_month, target_day, 30.0,
        )
        perfection_hit = _has_hit(perf_computed, perf_natal, targets, direction_orb_deg)

        transit_computed, transit_natal, _ = technique_transit(
            n_raw, n_points, target_year, target_month, target_day, 12, 0, 0,
            natal_lat, natal_lng, None, 0, house_system, zodiac_type,
        )
        transit_hit = _has_hit(transit_computed, transit_natal, targets, transit_orb_deg)

        movements_hit = int(progression_hit) + int(perfection_hit) + int(transit_hit)
        if movements_hit >= 2:
            qualifying.append({
                "hour": cand_hour, "minute": cand_minute, "second": cand_second,
                "secondary_progression_hit": progression_hit,
                "perfection_hit": perfection_hit,
                "transit_hit": transit_hit,
                "movements_hit": movements_hit,
            })

    windows = _collapse_to_windows(qualifying, step)

    return {
        "method": "three_movements",
        "source": "A. Grishchenyuk (1996), Zaprjagaev/Vronsky/Shestopalov lineage",
        "candidates_tested": len(candidates),
        "candidates_qualifying_raw_count": len(qualifying),
        "qualifying_windows": windows,
        "note": (
            "qualifying_windows collapses consecutive qualifying candidates into "
            "contiguous [start, end] ranges (each labeled with the concordance "
            "level - 3_of_3 or 2_of_3 - the source's own stated threshold, not a "
            "score) instead of listing every single candidate - this is not a "
            "ranking, just a compact representation of the same pass/fail result. "
            "If a very large fraction of the day qualifies (check "
            "candidates_qualifying_raw_count vs candidates_tested), the orbs are "
            "probably too loose to be useful for narrowing on this event alone - "
            "tighten direction_orb_deg/transit_orb_deg, or rely on intersecting "
            "with other events instead. To combine evidence across multiple "
            "events, intersect the qualifying windows from separate calls (one "
            "per event) rather than summing or averaging anything."
        ),
    }


def _collapse_to_windows(qualifying: List[Dict[str, Any]], step_seconds: int) -> List[Dict[str, Any]]:
    """
    Groups consecutive qualifying candidates (adjacent by exactly one scan
    step) that share the same movements_hit count into a single
    [start, end] window, instead of one entry per candidate. Purely a
    compact representation of the same qualify/don't-qualify result - not
    an aggregation or a score.
    """
    if not qualifying:
        return []

    def total_seconds(c):
        return c["hour"] * 3600 + c["minute"] * 60 + c["second"]

    def fmt(c):
        return f"{c['hour']:02d}:{c['minute']:02d}:{c['second']:02d}"

    windows = []
    window_start = qualifying[0]
    window_prev = qualifying[0]

    for cand in qualifying[1:]:
        contiguous = total_seconds(cand) - total_seconds(window_prev) == step_seconds
        same_tier = cand["movements_hit"] == window_prev["movements_hit"]
        if contiguous and same_tier:
            window_prev = cand
            continue
        windows.append(_make_window(window_start, window_prev))
        window_start = cand
        window_prev = cand
    windows.append(_make_window(window_start, window_prev))
    return windows


def _make_window(start: Dict[str, Any], end: Dict[str, Any]) -> Dict[str, Any]:
    movements = start["movements_hit"]
    return {
        "start": f"{start['hour']:02d}:{start['minute']:02d}:{start['second']:02d}",
        "end": f"{end['hour']:02d}:{end['minute']:02d}:{end['second']:02d}",
        "movements_hit": movements,
        "concordance": "3_of_3 (source states ~100% probability)" if movements == 3
                       else "2_of_3 (source states ~66% probability)",
        "secondary_progression_hit": start["secondary_progression_hit"],
        "perfection_hit": start["perfection_hit"],
        "transit_hit": start["transit_hit"],
    }
