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
    # require_day=False: per help_texts/rectification.md "Directions are
    # mandatory for imprecise dates, not optional" - solar arc moves
    # about 1 deg/year, so even a full +/-6 month uncertainty (a year-only
    # event defaulted to July 1) is well inside normal orb tolerances and
    # still contributes real evidence. Only transit genuinely needs an
    # exact date.
    ev_year, ev_month, ev_day = _resolve_event_date(ev, require_day=False)
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
    # require_day=False - see _run_solar_arc_for_event's comment above;
    # secondary progression is likewise a year-scale technique.
    ev_year, ev_month, ev_day = _resolve_event_date(ev, require_day=False)
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
    # require_day=False - profection is an annual/monthly technique keyed
    # by elapsed whole years, not sensitive to which day within a year an
    # imprecise event is defaulted to.
    ev_year, ev_month, ev_day = _resolve_event_date(ev, require_day=False)
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
    # require_day=False - the lunar return nearest a defaulted mid-year
    # date is still a real, if slightly less targeted, lunar return; far
    # better than refusing to run the technique at all for a year-only
    # event.
    ev_year, ev_month, ev_day = _resolve_event_date(ev, require_day=False)
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


def _event_relevant_points(n_raw, ev):
    """
    The set of point names that legitimately matter for THIS event, per
    the same "elements of house" reasoning (see engine/houses.py and
    help_texts/rectification.md "Reasoning about which houses apply to an
    event") that run_three_movements_scan already uses for movements_scan:
    the event's own target_houses cusps themselves, their ruler/co-ruler/
    occupying planets (via get_house_element_names - the exact function
    movements_scan calls, previously imported here but never wired up to
    candidate_verification), plus the four angles (ASC/DSC/MC/IC), which
    are always legitimate rectification significators on their own.

    Falls back to ALL 12 house cusps + the 4 angles when an event carries
    no target_houses at all, so events without house reasoning aren't
    silently dropped from candidate_verification.

    Why this matters: without this restriction, "best_angular_aspect"
    searched every one of a candidate's directed/progressed house cusps
    and angles against every natal point, for every event, regardless of
    which houses were actually reasoned as relevant to that specific
    event. With 12 houses x ~14 points x the full aspect set x 4
    techniques, that search space is wide enough that almost ANY
    candidate time shows a sub-0.1 degree "hit" somewhere - a real,
    observed effect (a full-day rectification run showed 9 of 11 tested
    candidates with 6-7 of 7 personal events under 0.1 degree, which
    doesn't discriminate between candidates at all). Restricting the
    search to the event's own reasoned significators - the same
    restriction movements_scan already applies - makes a "hit" mean what
    the methodology says it should mean, and, as a side effect, sharply
    cuts how much unused near-miss data candidate_verification returns.
    """
    target_houses = ev.get("target_houses")
    relevant = set(ANGLE_KEYS)
    if not target_houses:
        return relevant | set(HOUSE_KEYS)
    for h in target_houses:
        if isinstance(h, int) and 1 <= h <= 12:
            relevant.add(HOUSE_KEYS[h - 1])
    relevant.update(get_house_element_names(n_raw, target_houses))
    return relevant


def _extract_angular_aspects(aspects, max_orb=1.0, relevant_points=None, exclude_self=None):
    """
    Filter aspects where at least one side is a relevant point, within
    max_orb. relevant_points defaults to _ANGULAR_POINT_NAMES (all 12
    house cusps + the 4 angles) for callers outside the per-event
    candidate_verification path; pass the event-specific set from
    _event_relevant_points to restrict the search to that event's own
    reasoned significators instead.

    exclude_self, when given a point name (e.g. "moon"), drops any aspect
    where BOTH sides are that same point. This exists for technique="
    lunar_return" specifically: a lunar return chart is, by its own
    definition, the moment the transiting Moon returns to (approximately)
    its natal degree - so a moon/moon conjunction near 0deg is structurally
    guaranteed on every lunar return, for every candidate birth time,
    contributing zero actual evidence about which candidate is correct.
    Confirmed directly: without this exclusion, whenever "moon" happened
    to be one of an event's own reasoned significators (e.g. ruler of a
    Cancer house cusp), this trivial self-match dominated
    best_angular_aspect for every candidate tested, silently defeating
    the _event_relevant_points restriction above for that event. The
    equivalent solar/sun self-match isn't excluded here because
    technique="solar_return" is not currently invoked by
    _process_event_for_candidate at all - only lunar_return is - but the
    same exclusion would apply if that changes.
    """
    points = relevant_points if relevant_points is not None else _ANGULAR_POINT_NAMES
    result = []
    for a in aspects:
        if a["exact_orb"] > max_orb:
            continue
        if exclude_self and a["point_a"] == exclude_self and a["point_b"] == exclude_self:
            continue
        if a["point_a"] in points or a["point_b"] in points:
            result.append(a)
    return sorted(result, key=lambda x: x["exact_orb"])


def _best_angular_aspect(aspects, relevant_points=None, exclude_self=None):
    """Return the single tightest relevant aspect, or None."""
    angular = _extract_angular_aspects(aspects, max_orb=2.0, relevant_points=relevant_points, exclude_self=exclude_self)
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
    relevant_points = _event_relevant_points(n_raw, ev)

    # Solar arc — runs for every precision level, year-only included
    # (see _run_solar_arc_for_event's own comment)
    try:
        sa = _run_solar_arc_for_event(natal, cand_h, cand_m, cand_s, fixed_offset, n_raw, n_points, ev)
        best = _best_angular_aspect(sa["aspects"], relevant_points)
        results["solar_arc"] = {
            "best_angular_aspect": best,
            "total_aspects": len(sa["aspects"]),
            "angular_aspects_under_1deg": len(_extract_angular_aspects(sa["aspects"], 1.0, relevant_points)),
            "meta": sa["meta"],
        }
    except _EventTooImprecise as e:
        results["solar_arc"] = {"error": str(e)}
    except Exception as e:
        results["solar_arc"] = {"error": str(e)}

    # Secondary progression — runs for every precision level, year-only included
    try:
        sp = _run_secondary_progression_for_event(natal, cand_h, cand_m, cand_s, fixed_offset, n_raw, n_points, ev)
        best = _best_angular_aspect(sp["aspects"], relevant_points)
        results["secondary_progression"] = {
            "best_angular_aspect": best,
            "total_aspects": len(sp["aspects"]),
            "angular_aspects_under_1deg": len(_extract_angular_aspects(sp["aspects"], 1.0, relevant_points)),
        }
    except _EventTooImprecise as e:
        results["secondary_progression"] = {"error": str(e)}
    except Exception as e:
        results["secondary_progression"] = {"error": str(e)}

    # Transit — only when event has a known clock time
    if precision == "datetime":
        try:
            tr = _run_transit_for_event(natal, n_raw, n_points, ev)
            best = _best_angular_aspect(tr["aspects"], relevant_points)
            results["transit"] = {
                "best_angular_aspect": best,
                "total_aspects": len(tr["aspects"]),
                "angular_aspects_under_1deg": len(_extract_angular_aspects(tr["aspects"], 1.0, relevant_points)),
            }
        except Exception as e:
            results["transit"] = {"error": str(e)}

    # Profection — runs for every precision level (year-only events are
    # defaulted to a mid-year date inside _run_profection_for_event; per
    # rectification.md step 5, the full direction stack applies to every
    # event without a known clock time, not just date-precision ones)
    try:
        pf = _run_profection_for_event(natal, n_raw, n_points, ev)
        best = _best_angular_aspect(pf["aspects"], relevant_points)
        results["profection"] = {
            "best_angular_aspect": best,
            "total_aspects": len(pf["aspects"]),
        }
    except Exception as e:
        results["profection"] = {"error": str(e)}

    # Lunar return — same reasoning as profection above. exclude_self=
    # "moon": see _extract_angular_aspects' docstring - a lunar return's
    # own defining feature (transiting Moon = natal Moon) is not evidence
    # about the candidate birth time and must not be allowed to win here.
    try:
        lr = _run_lunar_return_for_event(natal, n_raw, n_points, ev)
        best = _best_angular_aspect(lr["aspects"], relevant_points, exclude_self="moon")
        results["lunar_return"] = {
            "best_angular_aspect": best,
            "total_aspects": len(lr["aspects"]),
            "meta": lr["meta"],
        }
    except Exception as e:
        results["lunar_return"] = {"error": str(e)}

    return results


# ---------------------------------------------------------------------------
# Compact digest of candidate_verification
# ---------------------------------------------------------------------------

_TECHNIQUES_ORDER = ("solar_arc", "secondary_progression", "profection", "lunar_return", "transit")


def _best_of_event(techs):
    """
    Across the (up to 5) technique results stored for one event at one
    candidate, return {orb_deg, technique, point_a, point_b, aspect_deg}
    for whichever technique produced the single tightest
    best_angular_aspect, or None if none of them produced one.
    """
    best = None
    best_tech = None
    for tech in _TECHNIQUES_ORDER:
        t = techs.get(tech)
        if not t:
            continue
        baa = t.get("best_angular_aspect")
        if baa is None or baa.get("exact_orb") is None:
            continue
        if best is None or baa["exact_orb"] < best["exact_orb"]:
            best = baa
            best_tech = tech
    if best is None:
        return None
    return {
        "orb_deg": round(best["exact_orb"], 4),
        "technique": best_tech,
        "point_a": best["point_a"],
        "point_b": best["point_b"],
        "aspect_deg": best["aspect_deg"],
    }


def _build_digest(verification, events):
    """
    A compact, candidate-by-candidate summary of `candidate_verification`,
    built for the common case where a caller wants to see which
    candidates are actually worth pulling the full (large) per-technique
    detail for, without first downloading that full detail.

    For each candidate: per-event best orb for PERSONAL events only (per
    help_texts/rectification.md "Personal events take priority" - these
    are the events worth showing in full here), plus sub-0.1/sub-0.5
    degree counts for both personal and career/minor events, and the
    candidate's own "tier"/"corroborating_events" (see
    _build_candidate_list) - always check this before reading a high
    sub_0.1deg count as independent confirmation: a candidate tagged
    "initial_guess_vicinity" was tested only because it sits near the
    supplied seed time, not because any data pointed there, so a tight
    score there is not on the same footing as one from
    "strict_3of3_intersection" or "most_corroborated_individual_events".

    This is explicitly NOT a ranking. Candidates are listed in the same
    order candidate_verification itself returned them (whatever order
    _build_candidate_list produced - never resorted by any count here).
    The sub-0.1/sub-0.5 counts are a direct tally of a real, documented
    quantity (orb tightness against each event's own reasoned
    significators, after the _event_relevant_points restriction above) -
    not an invented combined score - but per the project's standing rule
    against inventing scoring/ranking schemes, this digest does not sum
    those counts across candidates into a single number, and does not
    order or flag any candidate as a "winner". Use it alongside
    movements_intersection and the auxiliary checks, per the mandatory
    sequence, to reach a conclusion - not as a replacement for them.
    """
    events_by_name = {e["name"]: e for e in events}
    personal_names = [n for n, e in events_by_name.items() if e.get("category") == "personal"]
    other_names = [n for n, e in events_by_name.items() if e.get("category") != "personal"]

    candidates = []
    for cand_label, per_event in verification.items():
        personal_events_out = []
        personal_sub01 = personal_sub05 = 0
        other_sub01 = other_sub05 = 0

        for name in personal_names:
            techs = per_event.get(name, {})
            b = _best_of_event(techs)
            if b is not None:
                personal_events_out.append({"name": name, **b})
                if b["orb_deg"] < 0.1:
                    personal_sub01 += 1
                if b["orb_deg"] < 0.5:
                    personal_sub05 += 1

        for name in other_names:
            techs = per_event.get(name, {})
            b = _best_of_event(techs)
            if b is not None:
                if b["orb_deg"] < 0.1:
                    other_sub01 += 1
                if b["orb_deg"] < 0.5:
                    other_sub05 += 1

        candidates.append({
            "time": cand_label,
            "tier": per_event.get("_tier"),
            "corroborating_events": per_event.get("_corroborating_events"),
            "personal_events_total": len(personal_names),
            "personal_sub_0.1deg": personal_sub01,
            "personal_sub_0.5deg": personal_sub05,
            "career_minor_events_total": len(other_names),
            "career_minor_sub_0.1deg": other_sub01,
            "career_minor_sub_0.5deg": other_sub05,
            "personal_events": personal_events_out,
        })

    return {
        "method": "candidate_verification_digest",
        "note": (
            "Compact summary of candidate_verification: for each candidate, "
            "the single tightest angular aspect per PERSONAL event (career/"
            "minor events are reduced to counts only, to keep this section "
            "small - fetch the full candidate_verification section, "
            "optionally with the REST endpoints for large results, for "
            "their detail). Best-aspect search is restricted to each "
            "event's own reasoned target_houses elements plus the four "
            "angles (see _event_relevant_points) - not all 12 houses - so "
            "these numbers should discriminate between candidates rather "
            "than being tight for almost all of them. Each candidate also "
            "carries its own 'tier' (see candidate_selection_tiers / "
            "_build_candidate_list) - a run often verifies candidates from "
            "more than one tier at once (e.g. the always-included "
            "initial_guess_vicinity plus a movements-derived fallback), so "
            "a tight score is independent confirmation only when its tier "
            "is data-driven (strict/relaxed intersection or "
            "most_corroborated_individual_events) - a seed-anchored "
            "initial_guess_vicinity candidate was tested BECAUSE it's near "
            "the supplied guess, not because anything pointed there. This "
            "is NOT a ranking: candidates are listed in candidate_"
            "verification's own order, and the sub_0.1/sub_0.5 counts are "
            "a direct tally of a real measured quantity, never summed into "
            "one combined score or used here to pick a 'winner' - see "
            "help_texts/rectification.md's no-scoring rule and 'Personal "
            "events take priority'. Use alongside movements_intersection "
            "and the auxiliary checks, per the mandatory sequence."
        ),
        "candidates": candidates,
    }


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
      - movements_scan: per-event qualifying windows (large - usually not
        needed directly, since movements_intersection already carries its
        per-event selectivity ratios and movements_coverage_heatmap
        already carries the ranked overlap; fetch this only for a
        detailed per-event audit)
      - movements_intersection: intersection of all events' windows
      - auxiliary: Bonatti, Herich, degree_clustering results
      - movements_coverage_heatmap: ranked overlap across events
      - candidate_selection_tier: name of the FIRST tier that
        contributed a candidate (explicit_candidates,
        initial_guess_vicinity, strict/relaxed intersection, ...) -
        kept for back-compat; see candidate_selection_tiers for the
        full picture, since a run often blends more than one tier
      - candidate_selection_tiers: {tier_name: count} breakdown of the
        WHOLE candidate list - a run frequently draws candidates from
        more than one tier at once (e.g. the always-included
        initial_guess vicinity plus a movements-derived fallback when
        the intersection is empty), which the single
        candidate_selection_tier name alone hides
      - candidate_verification: full per-candidate x per-event x
        per-technique detail (large - see "digest" below for a compact
        summary of the same data; fetch this section, or a REST call for
        one candidate, only once specific candidates need closer study).
        Each candidate's entry also carries "_tier" (and
        "_corroborating_events" when applicable) identifying which tier
        that specific candidate came from
      - digest: compact per-candidate summary of candidate_verification,
        including each candidate's own tier - RECOMMENDED as the first
        thing to fetch after movements_intersection, before reaching for
        the full candidate_verification section
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
    # Step 2: Trutina Hermetis  (SUPPLEMENTARY ONLY)
    #   Trutina is often inapplicable (mother's birth time rarely known)
    #   and empirically unreliable in isolation.  Results are reported for
    #   informational purposes only — NOT used in candidate selection or
    #   any decision-making logic downstream.
    # -----------------------------------------------------------------------
    logger.info("pipeline: running Trutina Hermetis (supplementary)...")
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
        trutina["_status"] = "supplementary_only"
        trutina["_note"] = (
            "Trutina Hermetis is reported for informational purposes only. "
            "It is NOT used in candidate selection or scoring. "
            "Mother's birth time is rarely available, and the method's "
            "empirical reliability is low in isolation."
        )
        result["trutina"] = trutina
    except Exception as e:
        logger.exception("pipeline: trutina failed")
        result["trutina"] = {"error": str(e), "_status": "supplementary_only"}

    # -----------------------------------------------------------------------
    # Steps 4-7: Movements scan for every event (parallelized)
    # -----------------------------------------------------------------------
    logger.info("pipeline: running movements_scan for %d events...", len(events))
    movements_results = {}

    def _run_movements_for_event(ev):
        name = ev["name"]
        try:
            # require_day=False - two of Grishchenyuk's three movements
            # (secondary progression, "perfection") are year-scale and
            # insensitive to a defaulted day; only the transit component
            # is date-sensitive, and the method's own >=2-of-3 threshold
            # already tolerates one weaker movement. Excluding year-only
            # events from movements_scan entirely contradicted
            # rectification.md step 6 ("run for every event").
            ev_year, ev_month, ev_day = _resolve_event_date(ev, require_day=False)
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
    # Step 10b: Movements coverage heatmap
    # -----------------------------------------------------------------------
    heatmap = _movements_coverage_heatmap(movements_results, step_minutes * 60)
    result["movements_coverage_heatmap"] = heatmap

    # -----------------------------------------------------------------------
    # Step 11: Direct verification of candidate times via solar_arc
    # -----------------------------------------------------------------------
    # Build candidate list from:
    #   A. Explicitly provided candidate_times
    #   B. Initial-guess vicinity (±15 min) — ALWAYS, to ensure stated
    #      time is verified even when movements points elsewhere
    #   C. Movements intersection peaks
    #   D. Most-corroborated-individual-events (fallback)
    #   E. Scan range midpoint (last resort)
    cands, candidate_tier_counts = _build_candidate_list(
        candidate_times, intersection, movements_results, step_minutes * 60,
        scan_start_hour, scan_start_minute, scan_end_hour, scan_end_minute,
        initial_guess_hour=initial_guess_hour,
        initial_guess_minute=initial_guess_minute,
    )
    # Back-compat: candidate_selection_tier stays the single tier name of
    # the FIRST tier that contributed any candidate (previous behaviour),
    # for any existing consumer that expects a bare string. It is NOT a
    # summary of the whole candidate list - see candidate_selection_tiers
    # and each candidate's own "tier" field (echoed into
    # candidate_verification and digest below) for that, since a run
    # frequently blends candidates from more than one tier at once (e.g.
    # the always-included initial_guess vicinity plus a data-driven
    # fallback when the intersection came back empty) and collapsing
    # that mix into one name made every candidate look equally
    # seed-anchored or equally data-driven, whichever fired first.
    first_tier = next(iter(candidate_tier_counts), None)
    result["candidate_selection_tier"] = first_tier
    result["candidate_selection_tiers"] = candidate_tier_counts
    logger.info(
        "pipeline: verifying %d candidate times against all events (tiers: %s)...",
        len(cands), candidate_tier_counts,
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

        # "_tier"/"_corroborating_events" are metadata about the candidate
        # itself, not another event - underscore-prefixed so they can't
        # collide with an event named e.g. "tier" and so downstream code
        # can distinguish them from per_event keys by a simple prefix
        # check rather than a hardcoded key list. _build_digest below
        # only ever looks up specific event names via events_by_name, so
        # it's unaffected by these extra keys; the summary loop further
        # down explicitly skips them.
        per_event["_tier"] = cand.get("tier")
        if "corroborating_events" in cand:
            per_event["_corroborating_events"] = cand["corroborating_events"]

        verification[cand_label] = per_event
        logger.info("  verified candidate %s against %d events (tier: %s)", cand_label, len(events), cand.get("tier"))

    result["candidate_verification"] = verification
    result["digest"] = _build_digest(verification, events)


    # -----------------------------------------------------------------------
    # Summary / completeness
    # -----------------------------------------------------------------------
    total_cells = 0
    filled_cells = 0
    for cand_label, per_event in verification.items():
        for ev_name, techs in per_event.items():
            # "_tier"/"_corroborating_events" are per-candidate metadata
            # (see where they're set above), not an event -> technique-dict
            # entry, so they don't have .items() to iterate; skip them.
            if ev_name.startswith("_"):
                continue
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
# Movements coverage heatmap
# ---------------------------------------------------------------------------

def _movements_coverage_heatmap(movements_results, step_seconds, top_n=30):
    """
    For each scanned minute, count how many events have qualifying
    windows (at >=2/3 concordance) covering that minute.

    Unlike the strict/relaxed intersection (which requires ALL events
    to agree), this produces a "soft" score — the time(s) where the
    MOST events' qualifying windows overlap.  Reported as a ranked
    list so the human can compare movements-favored times against the
    stated time, even when the strict intersection is empty.

    Returns: list of {"time": "HH:MM:SS", "events_covering": N}
    sorted by events_covering desc, then chronologically, top_n items.
    """
    from collections import defaultdict
    coverage: Dict[int, int] = defaultdict(int)

    for name, r in movements_results.items():
        if "error" in r or r.get("skipped"):
            continue
        seen = set()
        for w in r.get("qualifying_windows", []):
            if w.get("movements_hit", 0) < 2:
                continue
            start = _time_to_seconds(w["start"])
            end = _time_to_seconds(w["end"])
            for s in range(start, end + 1, max(step_seconds, 60)):
                seen.add(s)
        for s in seen:
            coverage[s] += 1

    if not coverage:
        return []

    # Sort by coverage desc, then time asc
    ranked = sorted(coverage.items(), key=lambda x: (-x[1], x[0]))
    return [
        {"time": _seconds_to_time(s), "events_covering": c}
        for s, c in ranked[:top_n]
    ]


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
    initial_guess_hour=None, initial_guess_minute=None,
):
    """
    Build the list of candidate times to verify.

    ALWAYS includes the initial_guess zone (±15 min at 5-min steps) when
    an initial guess is provided, regardless of whether movements covers
    it.  This ensures the stated/documented birth time is always directly
    verified by SA/SP target-house analysis, preventing false rejections
    when movements points elsewhere due to dataset-size effects.

    Movements-derived candidates are ALSO included so both zones get a
    head-to-head comparison in a single pipeline run.

    Each returned candidate dict carries its own "tier" field recording
    which tier first contributed it (tiers are applied in priority order
    A-F and a candidate keeps whichever tier added it first, via
    _cand_in_list dedup). This matters because a single run routinely
    draws from MORE THAN ONE tier at once - e.g. the always-included
    initial_guess vicinity (tier B) plus a data-driven fallback (tier E)
    when the intersection is empty. Reporting only the first tier that
    fired as one flat string (the previous behaviour) hid that mix: a
    human/LLM reading the result would see e.g. "initial_guess_vicinity"
    and reasonably assume EVERY candidate was seed-anchored, when some
    were actually independent, data-driven fallback candidates - or
    vice versa, wrongly trust a seed-anchored candidate as if it were
    data-driven. The second return value is now a {tier: count} tally
    of the whole list, not a single tier name, so the mix is visible;
    the per-candidate "tier" tag is the authoritative source and is
    threaded into candidate_verification and digest below, rather than
    re-derived from candidate order.
    """
    cands = []
    tier_counts: Dict[str, int] = {}

    def _add(c, tier):
        if _cand_in_list(c, cands):
            return
        tagged = {"hour": c["hour"], "minute": c["minute"], "second": c.get("second", 0), "tier": tier}
        if "corroborating_events" in c:
            tagged["corroborating_events"] = c["corroborating_events"]
        cands.append(tagged)
        tier_counts[tier] = tier_counts.get(tier, 0) + 1

    # ----- A. Explicitly provided candidate_times (from the caller) --------
    if explicit_candidates:
        for c in explicit_candidates:
            _add(c, "explicit_candidates")

    # ----- B. Initial-guess vicinity (ALWAYS included when provided) -------
    #   Verifies stated/documented time ±15 min so the human always sees
    #   how the source-time zone compares to whatever movements found.
    if initial_guess_hour is not None and initial_guess_minute is not None:
        guess_sec = initial_guess_hour * 3600 + initial_guess_minute * 60
        for delta in [-15, -10, -5, 0, 5, 10, 15]:
            sec = guess_sec + delta * 60
            if sec < 0:
                sec += 86400
            sec = sec % 86400
            _add({"hour": sec // 3600, "minute": (sec % 3600) // 60, "second": 0}, "initial_guess_vicinity")

    # ----- C. From strict 3/3 intersection --------------------------------
    for time_str in intersection.get("strict_3of3_intersection", [])[:10]:
        parts = time_str.split(":")
        _add(
            {"hour": int(parts[0]), "minute": int(parts[1]), "second": int(parts[2]) if len(parts) > 2 else 0},
            "strict_3of3_intersection",
        )

    # ----- D. From relaxed 2/3 intersection (if strict empty) -------------
    if not intersection.get("strict_3of3_intersection"):
        for time_str in intersection.get("relaxed_2of3_intersection", [])[:10]:
            parts = time_str.split(":")
            _add(
                {"hour": int(parts[0]), "minute": int(parts[1]), "second": int(parts[2]) if len(parts) > 2 else 0},
                "relaxed_2of3_intersection",
            )

    # ----- E. Most-corroborated individual events fallback ----------------
    if len(cands) < 10:
        for c in _most_corroborated_candidates(movements_results, step_seconds):
            _add(c, "most_corroborated_individual_events")
            if len(cands) >= 20:
                break

    # ----- F. Scan range midpoint (absolute last resort) ------------------
    if not cands:
        mid_h = (start_h + end_h) // 2
        mid_m = (start_m + end_m) // 2
        _add({"hour": mid_h, "minute": mid_m, "second": 0}, "scan_range_midpoint_no_signal")

    return cands, tier_counts


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
