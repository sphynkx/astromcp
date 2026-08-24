"""
Trutine of Hermes (Trutina Hermetis) - classical birth-time rectification
via the reciprocal Moon/Ascendant relationship between the birth chart and
the theoretical conception (epoch) chart.

Implements the method as documented by William Lilly (Christian Astrology,
pp.502-505), consistent with the summary in Ptolemy's Tetrabiblos Centiloquy
51: the Moon's degree at birth becomes the Ascendant's degree at conception;
the Moon's degree AT that conception moment then becomes the rectified
Ascendant at birth. See also:
https://kerykeion.net/content/learn-astrology/prenatal-conception-chart

This is a documented historical technique with a well-defined numeric
procedure, not an invented heuristic - see the worked example ("Lilly's
rectification of the Merchant's chart") this implementation was checked
against.

Known limitations of the method itself (not this implementation):
- Assumes conception took place at the same location as birth.
- Assumes a natural (non medically altered) gestation.
- The day/night (Moon above/below horizon at birth) branch cannot be
  determined without already knowing the birth time being solved for -
  this module returns both branches rather than guessing, and picking
  between them requires other evidence.
- The classical gestation-length table uses a WHOLE number of days per 12
  degrees of Moon-Ascendant arc (per Lilly's worked example). When the true
  fixed point sits close to one of these integer-day boundaries, the
  fixed-point iteration can fail to settle on a single instant and instead
  enters a small limit cycle between 2-3 nearby candidate times, each with
  a different gestation-day count. This is a real, previously-documented
  property of the classical method itself (see e.g. astrological forum
  discussions describing multiple candidate times from the same chart) -
  not an artifact of this implementation. Rather than silently returning
  whichever value the iteration happened to land on after max_iterations,
  this implementation detects the cycle and reports all of its distinct
  members, so the person using the result can see the genuine ambiguity.
"""

from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timedelta

from .chart import build_subject, resolve_fixed_offset_minutes, offset_minutes_to_tz_str

HOUSE_NAME_TO_NUM = {
    "First_House": 1, "Second_House": 2, "Third_House": 3, "Fourth_House": 4,
    "Fifth_House": 5, "Sixth_House": 6, "Seventh_House": 7, "Eighth_House": 8,
    "Ninth_House": 9, "Tenth_House": 10, "Eleventh_House": 11, "Twelfth_House": 12,
}


def _find_ascendant_datetime(
    target_asc_deg: float,
    year: int, month: int, day: int,
    lat: float, lng: float, fixed_offset_minutes: int,
    house_system: str, zodiac_type: str,
    start_hour: int = 12, start_minute: int = 0, start_second: int = 0,
    max_iterations: int = 20,
    tolerance_deg: float = 1e-5,
) -> datetime:
    """
    Finds the civil datetime (at fixed_offset_minutes) on the given calendar
    date at which the real Ascendant equals target_asc_deg. The Ascendant
    completes a full 360-degree cycle roughly once per sidereal day, so for
    any given date there is exactly one such moment near a given starting
    guess - this is a direct Newton-style solve, not a multi-day search.
    """
    guess_dt = datetime(year, month, day, start_hour, start_minute, start_second)
    for _ in range(max_iterations):
        subj, _, _ = build_subject(
            "trutina_search", guess_dt.year, guess_dt.month, guess_dt.day,
            guess_dt.hour, guess_dt.minute, guess_dt.second,
            lat, lng, None, fixed_offset_minutes, house_system, zodiac_type,
        )
        raw = subj.model_dump(mode="json")
        cur_asc = raw["ascendant"]["abs_pos"]
        speed = raw["ascendant"]["speed"] or 360.0
        diff = (target_asc_deg - cur_asc + 180) % 360 - 180
        if abs(diff) < tolerance_deg:
            break
        delta_days = diff / speed
        guess_dt = guess_dt + timedelta(days=delta_days)
    return guess_dt


def _gestation_days(moon_abs_pos: float, asc_abs_pos: float, moon_above_horizon: bool) -> int:
    """
    Classical Lilly gestation-length table: 1 day per 12 degrees of arc
    between Moon and Ascendant, baseline 273 days - added if the birth
    Moon is below the horizon, subtracted if above.
    """
    if moon_above_horizon:
        distance = (asc_abs_pos - moon_abs_pos) % 360
        return 273 - int(distance // 12)
    else:
        distance = (moon_abs_pos - asc_abs_pos) % 360
        return 273 + int(distance // 12)


def _run_branch(
    natal_year: int, natal_month: int, natal_day: int,
    natal_lat: float, natal_lng: float, fixed_offset_minutes: int,
    house_system: str, zodiac_type: str,
    start_hour: int, start_minute: int, start_second: int,
    force_above_horizon: bool,
    max_iterations: int,
    cycle_tolerance_seconds: float = 90.0,
) -> Dict[str, Any]:
    guess_h, guess_m, guess_s = start_hour, start_minute, start_second
    history: List[Dict[str, Any]] = []
    seen_states: List[Tuple[float, Dict[str, Any]]] = []  # sliding window, most recent last
    window_size = 10  # enough to span a couple of periods of a period-3 cycle
    converged = False
    cycle_detected = False
    cycle_start_iteration = None
    conception_dt = None
    gestation_days = None

    def total_seconds_of_day(h, m, s):
        return h * 3600 + m * 60 + s

    for i in range(max_iterations):
        base_subject, _, _ = build_subject(
            "trutina_base", natal_year, natal_month, natal_day, guess_h, guess_m, guess_s,
            natal_lat, natal_lng, None, fixed_offset_minutes, house_system, zodiac_type,
        )
        base_raw = base_subject.model_dump(mode="json")
        moon_abs = base_raw["moon"]["abs_pos"]
        asc_abs = base_raw["ascendant"]["abs_pos"]

        above_horizon = force_above_horizon
        gestation_days = _gestation_days(moon_abs, asc_abs, above_horizon)

        conception_date_guess = datetime(natal_year, natal_month, natal_day, guess_h, guess_m, guess_s) \
            - timedelta(days=gestation_days)

        target_conception_asc = moon_abs  # Trutine rule: birth Moon -> conception Ascendant

        conception_dt = _find_ascendant_datetime(
            target_conception_asc,
            conception_date_guess.year, conception_date_guess.month, conception_date_guess.day,
            natal_lat, natal_lng, fixed_offset_minutes, house_system, zodiac_type,
        )

        conception_subject, _, _ = build_subject(
            "trutina_conception", conception_dt.year, conception_dt.month, conception_dt.day,
            conception_dt.hour, conception_dt.minute, conception_dt.second,
            natal_lat, natal_lng, None, fixed_offset_minutes, house_system, zodiac_type,
        )
        conception_raw = conception_subject.model_dump(mode="json")
        conception_moon_abs = conception_raw["moon"]["abs_pos"]

        target_birth_asc = conception_moon_abs  # reciprocal rule: conception Moon -> birth Ascendant

        new_birth_dt = _find_ascendant_datetime(
            target_birth_asc,
            natal_year, natal_month, natal_day,
            natal_lat, natal_lng, fixed_offset_minutes, house_system, zodiac_type,
            start_hour=guess_h, start_minute=guess_m, start_second=guess_s,
        )

        snapshot = {
            "iteration": i,
            "guess": f"{guess_h:02d}:{guess_m:02d}:{guess_s:02d}",
            "gestation_days": gestation_days,
            "conception_datetime_civil": conception_dt.isoformat(),
            "new_guess": f"{new_birth_dt.hour:02d}:{new_birth_dt.minute:02d}:{new_birth_dt.second:02d}",
        }
        history.append(snapshot)

        new_total_sec = total_seconds_of_day(new_birth_dt.hour, new_birth_dt.minute, new_birth_dt.second)

        # Cycle detection: has this (or a near-identical) new_guess state
        # occurred recently? Only check a sliding window of the last few
        # iterations, not the entire history - otherwise a coincidental
        # proximity to some early transient value (still on the way toward
        # convergence, not yet cycling) would falsely trigger detection.
        # Record exactly which prior iteration matched, so that if a cycle
        # is found, only the genuine cycle segment (from the match onward)
        # is reported - not the whole trailing window.
        for prev_total_sec, prev_snapshot in seen_states:
            if abs(new_total_sec - prev_total_sec) < cycle_tolerance_seconds:
                cycle_detected = True
                cycle_start_iteration = prev_snapshot["iteration"]
                break
        seen_states.append((new_total_sec, snapshot))
        if len(seen_states) > window_size:
            seen_states.pop(0)

        delta_seconds = abs(
            (new_birth_dt - datetime(natal_year, natal_month, natal_day, guess_h, guess_m, guess_s)).total_seconds()
        )
        guess_h, guess_m, guess_s = new_birth_dt.hour, new_birth_dt.minute, new_birth_dt.second

        if delta_seconds < 1.0:
            converged = True
            break
        if cycle_detected:
            break

    result = {
        "converged": converged,
        "cycle_detected": cycle_detected,
        "iterations_used": len(history),
        "rectified_hour": guess_h,
        "rectified_minute": guess_m,
        "rectified_second": guess_s,
        "moon_above_horizon_assumed": force_above_horizon,
        "conception_datetime_civil": conception_dt.isoformat() if conception_dt else None,
        "gestation_days_final": gestation_days,
        "history": history,
    }

    if cycle_detected and not converged:
        # Report the distinct candidate times the cycle is bouncing between,
        # deduplicated, so the ambiguity is visible rather than hidden
        # behind an arbitrary last value.
        # Only the genuine cycle segment - from where the repeat was first
        # matched, to the end - not the whole trailing window, which would
        # still include earlier transient (still-converging) values.
        cycle_segment = [h for h in history if h["iteration"] >= cycle_start_iteration] if cycle_start_iteration is not None else history[-3:]
        unique_states = []
        seen_rounded = set()
        for snap in cycle_segment:
            hh, mm, ss = (int(x) for x in snap["new_guess"].split(":"))
            total_sec = hh * 3600 + mm * 60 + ss
            key = round(total_sec / cycle_tolerance_seconds)
            if key not in seen_rounded:
                seen_rounded.add(key)
                unique_states.append({
                    "time": snap["new_guess"],
                    "gestation_days": snap["gestation_days"],
                })
        result["cycle_candidates"] = unique_states
        result["note"] = (
            "This branch did not converge to a single instant - it settled into a "
            "small cycle between a few nearby candidate times (see cycle_candidates), "
            "because the true fixed point sits close to a boundary in the classical "
            "whole-day gestation table. This is a documented property of the classical "
            "method on some charts, not a computation error. Treat cycle_candidates as "
            "the plausible range for this branch."
        )

    return result


def run_trutina_hermetis(
    natal_year: int, natal_month: int, natal_day: int,
    natal_lat: float, natal_lng: float,
    natal_tz_str: Optional[str], natal_tz_offset_minutes: Optional[int],
    house_system: str, zodiac_type: str,
    initial_guess_hour: int = 12, initial_guess_minute: int = 0, initial_guess_second: int = 0,
    max_iterations: int = 30,
) -> Dict[str, Any]:
    fixed_offset = resolve_fixed_offset_minutes(
        natal_tz_str, natal_tz_offset_minutes,
        natal_year, natal_month, natal_day, initial_guess_hour, initial_guess_minute, initial_guess_second,
    )

    branch_below = _run_branch(
        natal_year, natal_month, natal_day, natal_lat, natal_lng, fixed_offset,
        house_system, zodiac_type,
        initial_guess_hour, initial_guess_minute, initial_guess_second,
        force_above_horizon=False, max_iterations=max_iterations,
    )
    branch_above = _run_branch(
        natal_year, natal_month, natal_day, natal_lat, natal_lng, fixed_offset,
        house_system, zodiac_type,
        initial_guess_hour, initial_guess_minute, initial_guess_second,
        force_above_horizon=True, max_iterations=max_iterations,
    )

    return {
        "method": "trutina_hermetis",
        "tz_used": offset_minutes_to_tz_str(fixed_offset),
        "fixed_offset_minutes": fixed_offset,
        "note": (
            "Two branches are returned because whether the Moon is above or "
            "below the horizon at birth cannot be known without already "
            "knowing the birth time being solved for. Use other evidence "
            "(rough time-of-day testimony, or agreement with rectif_scan "
            "results from actual life events) to choose between them. "
            "Conception location is approximated as the birth location - "
            "a documented limitation of the classical method itself. If a "
            "branch shows cycle_detected=true, see that branch's own note "
            "and cycle_candidates field."
        ),
        "branch_moon_below_horizon_at_birth": branch_below,
        "branch_moon_above_horizon_at_birth": branch_above,
    }
