"""
Trutine of Hermes (Trutina Hermetis) - classical birth-time rectification
via the reciprocal Moon/Ascendant relationship between the birth chart and
the theoretical conception (epoch) chart.

Primary source for the branching logic: Jan Kefer, "Prakticka Astrologie"
(1939; Russian edition "Практическая астрология", Moscow, 1991, ISBN
5-86452-004-7), Chapter 6 section 1. Kefer's original formulation treats
the Moon's horizon position (above/below) and its phase (waxing/waning) as
TWO INDEPENDENT conditions, giving four cases - not two, as a simplified
two-branch version (Moon above/below horizon only) sometimes seen
elsewhere would suggest. Working through Kefer's four cases algebraically:
the reciprocal target (birth Moon <-> conception Ascendant, or birth Moon
<-> conception Descendant) is determined by phase ALONE (Ascendant when
waxing, Descendant when waning); horizon position only affects whether the
starting gestation-length estimate should be nudged shorter or longer than
the 273-day mean. All four combinations are run as separate branches here,
since the different starting estimates can converge to genuinely different
fixed points even when two branches share the same reciprocal target.

The day-count adjustment magnitude (arc distance / 12 degrees per day) is
the refinement documented by W. Lilly (Christian Astrology, pp.502-505)
and independently by A. Grishchenyuk (1996) - Kefer's own text gives only
the direction (shorter/longer than 273 days), not this magnitude, but the
combination is consistent with both sources and only affects the starting
guess for the iterative search below, not its correctness.

Optional refinement: the "Jonas Rule" (Dr. Eugen Jonas, cited via S.
Kudyanov's discussion of A. Kolesnikov's and V. Tkachenko's articles,
"Astrolog" bulletin, 1994) - conception is estimated as the moment when the
transiting Sun-Moon angular separation equals that of the MOTHER's own
natal chart. This resolves the classical method's biggest weakness: within
the ~9-month gestation window there are roughly ten dates where the Moon
crosses the required degree, and nothing in the classical method alone
picks the right one. If the mother's natal data is supplied, this module
uses it to fix the conception DATE directly (searching for a matching
elongation near the classical estimate) before solving for the precise
time of day via the usual Ascendant-matching step - instead of leaving the
date itself part of the fixed-point iteration.

Known limitations of the classical method itself (not this implementation):
- Assumes conception took place at the same location as birth.
- Assumes a natural (non medically altered) gestation.
- Without the Jonas refinement, the day/night+phase branch and the
  specific conception date within the gestation window cannot be
  determined without already knowing the birth time being solved for -
  this module returns all four branches rather than guessing, and picking
  between them requires other evidence.
- The classical whole-day gestation table can put the true fixed point
  right on an integer-day boundary, causing the iteration to cycle between
  2-3 nearby candidate times instead of converging. This is a real,
  previously-documented property of the classical method (see e.g.
  astrological forum discussions describing multiple candidate times from
  the same chart) - not an artifact of this implementation. Rather than
  silently returning whichever value the iteration happened to land on
  after max_iterations, this implementation detects the cycle and reports
  all of its distinct members.
"""

from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timedelta

from .chart import build_subject, resolve_fixed_offset_minutes, offset_minutes_to_tz_str


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


def _signed_elongation(moon_abs_pos: float, sun_abs_pos: float) -> float:
    """Moon's position relative to the Sun, 0-360 degrees (not folded to 0-180)."""
    return (moon_abs_pos - sun_abs_pos) % 360


def _is_waxing(moon_abs_pos: float, sun_abs_pos: float) -> bool:
    """Waxing = Moon between new (0 deg elongation) and full (180 deg)."""
    return _signed_elongation(moon_abs_pos, sun_abs_pos) < 180


def _gestation_days_adjustment(moon_abs_pos: float, asc_abs_pos: float, moon_above_horizon: bool) -> int:
    """
    Lilly/Grishchenyuk gestation-length table: 1 day per 12 degrees of arc
    between Moon and Ascendant, baseline 273 days - added if the birth
    Moon is below the horizon, subtracted if above. This gives only the
    STARTING GUESS for the search below; Kefer's own text specifies the
    direction (shorter/longer) but not this particular magnitude formula.
    """
    if moon_above_horizon:
        distance = (asc_abs_pos - moon_abs_pos) % 360
        return 273 - int(distance // 12)
    else:
        distance = (moon_abs_pos - asc_abs_pos) % 360
        return 273 + int(distance // 12)


def _find_jonas_conception_datetime(
    target_elongation: float,
    center_year: int, center_month: int, center_day: int,
    half_window_days: int = 20,
    max_iterations: int = 20,
    tolerance_deg: float = 1e-4,
) -> Optional[datetime]:
    """
    Jonas Rule refinement: searches for the UTC-equivalent moment nearest
    the classical gestation-length estimate at which the transiting Sun-
    Moon signed elongation equals target_elongation (the mother's own natal
    value). Location is irrelevant for this geocentric angle, so the search
    uses an arbitrary point.

    The elongation increases monotonically (mod 360) at roughly 12.2
    deg/day (one full cycle per synodic month, ~29.5 days), so within a
    +/-half_window_days search there is typically exactly one crossing;
    this returns the one closest to the window's center. Returns None if
    no crossing is found in the window (should not normally happen for a
    window of 20+ days, comfortably wider than one synodic month).
    """
    center_dt = datetime(center_year, center_month, center_day, 12, 0, 0)
    step_days = 1.0
    n_steps = int(2 * half_window_days / step_days) + 1

    samples = []
    for i in range(n_steps):
        dt = center_dt - timedelta(days=half_window_days) + timedelta(days=i * step_days)
        subj, _, _ = build_subject(
            "jonas_search", dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second,
            0.0, 0.0, None, 0, "P", "Tropic",
        )
        raw = subj.model_dump(mode="json")
        elong = _signed_elongation(raw["moon"]["abs_pos"], raw["sun"]["abs_pos"])
        samples.append((dt, elong))

    # Unwrap the elongation sequence to be monotonically increasing, so a
    # simple sign change of (unwrapped - target - 360*k) finds crossings
    # without the 360-degree wraparound masking them.
    unwrapped = [samples[0][1]]
    for i in range(1, len(samples)):
        prev = unwrapped[-1]
        cur = samples[i][1]
        while cur < prev - 1e-6:
            cur += 360
        unwrapped.append(cur)

    # Find all crossings of any target + 360*k within the unwrapped range,
    # keep the one nearest the window center.
    best_dt = None
    best_center_distance = None
    for k in range(-1, 3):
        target_k = target_elongation + 360 * k
        for i in range(1, len(unwrapped)):
            lo, hi = unwrapped[i - 1], unwrapped[i]
            if lo <= target_k <= hi and hi > lo:
                frac = (target_k - lo) / (hi - lo)
                dt_lo, dt_hi = samples[i - 1][0], samples[i][0]
                crossing_dt = dt_lo + (dt_hi - dt_lo) * frac

                # Refine with a few Newton iterations for arcsecond precision.
                guess = crossing_dt
                for _ in range(max_iterations):
                    subj, _, _ = build_subject(
                        "jonas_refine", guess.year, guess.month, guess.day,
                        guess.hour, guess.minute, guess.second,
                        0.0, 0.0, None, 0, "P", "Tropic",
                    )
                    raw = subj.model_dump(mode="json")
                    cur_elong = _signed_elongation(raw["moon"]["abs_pos"], raw["sun"]["abs_pos"])
                    diff = (target_elongation - cur_elong + 180) % 360 - 180
                    if abs(diff) < tolerance_deg:
                        break
                    rel_speed = (raw["moon"]["speed"] or 13.2) - (raw["sun"]["speed"] or 0.9856)
                    guess = guess + timedelta(days=diff / rel_speed)

                distance_from_center = abs((guess - center_dt).total_seconds())
                if best_center_distance is None or distance_from_center < best_center_distance:
                    best_center_distance = distance_from_center
                    best_dt = guess

    return best_dt


def _run_branch(
    natal_year: int, natal_month: int, natal_day: int,
    natal_lat: float, natal_lng: float, fixed_offset_minutes: int,
    house_system: str, zodiac_type: str,
    start_hour: int, start_minute: int, start_second: int,
    force_above_horizon: bool,
    force_waxing: bool,
    max_iterations: int,
    mother_sun_moon_elongation: Optional[float] = None,
    cycle_tolerance_seconds: float = 90.0,
) -> Dict[str, Any]:
    guess_h, guess_m, guess_s = start_hour, start_minute, start_second
    history: List[Dict[str, Any]] = []
    seen_states: List[Tuple[float, Dict[str, Any]]] = []
    window_size = 10
    converged = False
    cycle_detected = False
    cycle_start_iteration = None
    conception_dt = None
    gestation_days = None
    use_ascendant = force_waxing  # per Kefer: Ascendant when waxing, Descendant when waning

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
        dsc_abs = base_raw["descendant"]["abs_pos"]

        gestation_days = _gestation_days_adjustment(moon_abs, asc_abs, force_above_horizon)
        conception_date_guess = datetime(natal_year, natal_month, natal_day, guess_h, guess_m, guess_s) \
            - timedelta(days=gestation_days)

        target_conception_asc = moon_abs  # Trutine rule: birth Moon -> conception Asc/Dsc

        if mother_sun_moon_elongation is not None:
            jonas_dt = _find_jonas_conception_datetime(
                mother_sun_moon_elongation,
                conception_date_guess.year, conception_date_guess.month, conception_date_guess.day,
            )
            conception_search_date = jonas_dt if jonas_dt is not None else conception_date_guess
        else:
            conception_search_date = conception_date_guess

        conception_dt = _find_ascendant_datetime(
            target_conception_asc if use_ascendant else (target_conception_asc - 180) % 360,
            conception_search_date.year, conception_search_date.month, conception_search_date.day,
            natal_lat, natal_lng, fixed_offset_minutes, house_system, zodiac_type,
        )

        conception_subject, _, _ = build_subject(
            "trutina_conception", conception_dt.year, conception_dt.month, conception_dt.day,
            conception_dt.hour, conception_dt.minute, conception_dt.second,
            natal_lat, natal_lng, None, fixed_offset_minutes, house_system, zodiac_type,
        )
        conception_raw = conception_subject.model_dump(mode="json")
        conception_moon_abs = conception_raw["moon"]["abs_pos"]

        target_birth_asc = conception_moon_abs  # reciprocal: conception Moon -> birth Asc/Dsc

        new_birth_dt = _find_ascendant_datetime(
            target_birth_asc if use_ascendant else (target_birth_asc - 180) % 360,
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
        "moon_waxing_assumed": force_waxing,
        "reciprocal_target": "ascendant" if use_ascendant else "descendant",
        "conception_datetime_civil": conception_dt.isoformat() if conception_dt else None,
        "gestation_days_final": gestation_days,
        "jonas_rule_applied": mother_sun_moon_elongation is not None,
        "history": history,
    }

    if cycle_detected and not converged:
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
    mother_year: Optional[int] = None, mother_month: Optional[int] = None, mother_day: Optional[int] = None,
    mother_hour: Optional[int] = None, mother_minute: Optional[int] = None, mother_second: Optional[int] = None,
    mother_lat: Optional[float] = None, mother_lng: Optional[float] = None,
    mother_tz_str: Optional[str] = None, mother_tz_offset_minutes: Optional[int] = None,
) -> Dict[str, Any]:
    fixed_offset = resolve_fixed_offset_minutes(
        natal_tz_str, natal_tz_offset_minutes,
        natal_year, natal_month, natal_day, initial_guess_hour, initial_guess_minute, initial_guess_second,
    )

    mother_elongation = None
    if mother_year is not None:
        mother_subject, _, _ = build_subject(
            "mother_natal", mother_year, mother_month, mother_day,
            mother_hour, mother_minute, mother_second,
            mother_lat, mother_lng, mother_tz_str, mother_tz_offset_minutes, house_system, zodiac_type,
        )
        mother_raw = mother_subject.model_dump(mode="json")
        mother_elongation = _signed_elongation(mother_raw["moon"]["abs_pos"], mother_raw["sun"]["abs_pos"])

    branches = {}
    for horizon_label, above_horizon in (("below_horizon", False), ("above_horizon", True)):
        for phase_label, waxing in (("waxing", True), ("waning", False)):
            key = f"branch_moon_{horizon_label}_{phase_label}_at_birth"
            branches[key] = _run_branch(
                natal_year, natal_month, natal_day, natal_lat, natal_lng, fixed_offset,
                house_system, zodiac_type,
                initial_guess_hour, initial_guess_minute, initial_guess_second,
                force_above_horizon=above_horizon, force_waxing=waxing,
                max_iterations=max_iterations,
                mother_sun_moon_elongation=mother_elongation,
            )

    return {
        "method": "trutina_hermetis",
        "source": "Jan Kefer, Prakticka Astrologie (1939); day-count magnitude per W. Lilly / A. Grishchenyuk",
        "tz_used": offset_minutes_to_tz_str(fixed_offset),
        "fixed_offset_minutes": fixed_offset,
        "jonas_rule_applied": mother_elongation is not None,
        "note": (
            "Four branches are returned (Kefer's original formulation treats Moon "
            "above/below horizon and waxing/waning as two independent conditions, "
            "not one) because neither can be known without already knowing the "
            "birth time being solved for. Use other evidence (rough time-of-day "
            "testimony, or agreement with rectif_scan results from actual life "
            "events) to choose between them. Conception location is approximated "
            "as the birth location - a documented limitation of the classical "
            "method itself. If mother's birth data was supplied, the Jonas Rule "
            "was used to fix the conception date directly instead of leaving it "
            "part of the fixed-point search - this substantially reduces the "
            "classical method's biggest source of ambiguity. If a branch shows "
            "cycle_detected=true, see that branch's own note and cycle_candidates "
            "field."
        ),
        **branches,
    }
