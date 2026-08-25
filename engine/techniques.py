"""
Predictive techniques: transit, secondary progression, solar arc direction,
solar return, and annual/monthly profections.

Each function accepts an already-built natal context (subject/raw) so that
callers doing many events per candidate (e.g. rectif_scan) only pay the cost
of building the natal chart once, not once per event.
"""

from typing import Optional, Dict, Any
from datetime import date, datetime, timedelta
import math

from .chart import build_subject, recompute_sign_fields
from .constants import DEFAULT_POINTS, ANGLE_KEYS, HOUSE_KEYS, TRADITIONAL_RULERS, SIGN_ORDER


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
        for a in ANGLE_KEYS + HOUSE_KEYS:
            if a in prog_raw:
                computed[a] = prog_raw[a]
    elif angle_method == "solar_arc_naibod":
        natal_sun = natal_raw["sun"]["abs_pos"]
        prog_sun = prog_raw["sun"]["abs_pos"]
        arc = (prog_sun - natal_sun) % 360
        for a in ANGLE_KEYS + HOUSE_KEYS:
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
    for key in DEFAULT_POINTS + ANGLE_KEYS + HOUSE_KEYS:
        if key in natal_raw:
            base = dict(natal_raw[key])
            base = recompute_sign_fields(base, base["abs_pos"] + arc)
            base["speed"] = 1.0
            computed[key] = base

    return computed, natal_points, {
        "elapsed_years": round(elapsed_years, 4),
        "solar_arc_deg": round(arc, 4),
    }


def technique_symbolic_direction(
    natal_year, natal_month, natal_day, natal_hour, natal_minute, natal_second,
    natal_lat, natal_lng, fixed_offset,
    house_system, zodiac_type,
    natal_raw: Dict[str, Any],
    natal_points: Dict[str, Dict[str, Any]],
    target_year, target_month, target_day,
    rate_deg_per_year: float = 1.0,
):
    """
    Whole-chart symbolic direction at a FLAT rate (degrees advanced =
    elapsed_years * rate_deg_per_year), as opposed to technique_solar_arc's
    astronomically-derived arc (actual motion of the transiting Sun). Two
    documented rates use this same mechanism under different names:
    - rate_deg_per_year=1.0: the classical "degree for a year" symbolic
      direction.
    - rate_deg_per_year=30.0: "perfection" / "fast progression"
      (Zaprjagaev's "method of annual revolution"; Shestopalov-school
      usage) - one whole sign per year, returning to the natal position
      every 12 years.
    Neither is tied to where the real Sun actually is on the target date -
    that distinction is what separates this from technique_solar_arc.

    Also usable at rate_deg_per_year=365.2425/365.2425*1 ... i.e. any rate;
    two further documented speeds from B. Israitel's classification map
    onto this same mechanism: rate=1/365.2425*360 (~0.9856, "degree for a
    day", ~1-year cycle) and rate=1/30*360=12.0 ("degree for a month",
    ~30-year Saturn-linked cycle). Pass the rate explicitly for either.
    """
    natal_civil_date = date(natal_year, natal_month, natal_day)
    target_civil_date = date(target_year, target_month, target_day)
    elapsed_years = (target_civil_date - natal_civil_date).days / 365.2425
    arc = (elapsed_years * rate_deg_per_year) % 360

    computed = {}
    for key in DEFAULT_POINTS + ANGLE_KEYS + HOUSE_KEYS:
        if key in natal_raw:
            base = dict(natal_raw[key])
            base = recompute_sign_fields(base, base["abs_pos"] + arc)
            base["speed"] = 1.0
            computed[key] = base

    return computed, natal_points, {
        "elapsed_years": round(elapsed_years, 4),
        "rate_deg_per_year": rate_deg_per_year,
        "arc_deg": round(arc, 4),
    }


def _find_solar_return_utc(
    natal_month: int, natal_day: int,
    natal_sun_abs_pos: float,
    target_year: int,
    max_iterations: int = 15,
    tolerance_deg: float = 1e-6,
) -> datetime:
    """
    Finds the exact UTC datetime in target_year at which the transiting Sun's
    ecliptic longitude exactly equals natal_sun_abs_pos (the solar return
    moment). Uses Newton-style iteration on the Sun's near-linear motion
    (~0.9856 deg/day) starting from the calendar birthday in target_year -
    the true return can fall up to about a day before/after that date due to
    leap-year drift, hence the search rather than assuming the exact date.

    Location is irrelevant for the Sun's geocentric longitude, so the search
    itself is done at an arbitrary point (0,0) with a fixed UTC offset;
    only the final chart (built by the caller with the returned datetime)
    needs the real location, for house cusps.
    """
    guess_dt = datetime(target_year, natal_month, natal_day, 12, 0, 0)
    for _ in range(max_iterations):
        subj, _, _ = build_subject(
            "sr_search", guess_dt.year, guess_dt.month, guess_dt.day,
            guess_dt.hour, guess_dt.minute, guess_dt.second,
            0.0, 0.0, None, 0, "P", "Tropic",
        )
        raw = subj.model_dump(mode="json")
        cur_sun = raw["sun"]["abs_pos"]
        speed = raw["sun"]["speed"] or 0.9856
        diff = (natal_sun_abs_pos - cur_sun + 180) % 360 - 180  # signed, in [-180, 180)
        if abs(diff) < tolerance_deg:
            break
        delta_days = diff / speed
        guess_dt = guess_dt + timedelta(days=delta_days)
    return guess_dt


def technique_solar_return(
    natal_month: int, natal_day: int,
    natal_raw: Dict[str, Any],
    natal_points: Dict[str, Dict[str, Any]],
    house_system: str, zodiac_type: str,
    target_year: int,
    sr_lat: float, sr_lng: float,
):
    """
    Solar return: builds the chart for the exact moment the transiting Sun
    returns to its natal position in target_year, at (sr_lat, sr_lng)
    (defaults to the natal location if the caller doesn't relocate it).
    Angles are included in computed_points (unlike plain transits) since SR
    ASC/MC are a standard part of solar return analysis.
    """
    natal_sun_abs_pos = natal_raw["sun"]["abs_pos"]
    sr_utc_dt = _find_solar_return_utc(natal_month, natal_day, natal_sun_abs_pos, target_year)

    sr_subject, _, _ = build_subject(
        "solar_return", sr_utc_dt.year, sr_utc_dt.month, sr_utc_dt.day,
        sr_utc_dt.hour, sr_utc_dt.minute, sr_utc_dt.second,
        sr_lat, sr_lng, None, 0, house_system, zodiac_type,
    )
    sr_raw = sr_subject.model_dump(mode="json")

    computed = {p: sr_raw[p] for p in DEFAULT_POINTS if p in sr_raw}
    for a in ANGLE_KEYS:
        if a in sr_raw:
            computed[a] = sr_raw[a]

    return computed, natal_points, {
        "solar_return_utc": sr_utc_dt.isoformat(),
        "solar_return_location": {"lat": sr_lat, "lng": sr_lng},
    }


def technique_profection(
    natal_year: int, natal_month: int, natal_day: int,
    natal_raw: Dict[str, Any],
    natal_points: Dict[str, Dict[str, Any]],
    house_system: str, zodiac_type: str,
    target_year: int, target_month: int, target_day: int,
    target_hour: int, target_minute: int, target_second: int,
    event_lat: float, event_lng: float,
    event_tz_str: Optional[str], event_tz_offset_minutes: Optional[int],
):
    """
    Annual and monthly profections (Hellenistic technique): the natal
    Ascendant symbolically advances one whole sign (30 degrees) per
    completed year of age. The ruler of the resulting ("profected") sign is
    the "Lord of the Year" - traditionally considered activated whenever it
    receives transits. The same logic applied within the profected year,
    one sign per completed month, gives the "Lord of the Month".

    This is scored the same way a transit is: the technique returns the
    transiting planetary positions for the event date (so aspects to the
    natal Lord of the Year / Lord of the Month / profected Ascendant degree
    can be checked by the caller's normal aspect machinery), but the
    natal-side target set is narrowed to just those two-or-three points
    instead of the full natal chart, since profections make a specific,
    falsifiable claim about which few points should be activated - not a
    general claim about the whole chart.

    Traditional (not modern/outer-planet) sign rulerships are used, since
    that is the doctrine profections are historically computed with - see
    constants.TRADITIONAL_RULERS.
    """
    natal_civil_date = date(natal_year, natal_month, natal_day)
    target_civil_date = date(target_year, target_month, target_day)
    elapsed_days = (target_civil_date - natal_civil_date).days
    age_years_completed = elapsed_days // 365 if elapsed_days >= 0 else -((-elapsed_days) // 365 + 1)
    # Completed months into the current profected year (0-11), used for the
    # monthly sub-profection. Approximated via a 30.44-day average month,
    # which is standard practice for this technique (profections are a
    # whole-sign/whole-month scheme, not a degree-precise one).
    days_into_profected_year = elapsed_days - age_years_completed * 365.2425
    month_index = int(days_into_profected_year // 30.44) % 12

    natal_asc_sign_num = natal_raw["ascendant"]["sign_num"]
    natal_asc_abs_pos = natal_raw["ascendant"]["abs_pos"]

    annual_sign_num = (natal_asc_sign_num + age_years_completed) % 12
    monthly_sign_num = (annual_sign_num + month_index) % 12

    annual_lord = TRADITIONAL_RULERS[annual_sign_num]
    monthly_lord = TRADITIONAL_RULERS[monthly_sign_num]

    profected_asc_abs_pos = (natal_asc_abs_pos + age_years_completed * 30) % 360

    transit_subject, ev_resolved_tz, ev_tz_source = build_subject(
        "profection_transit", target_year, target_month, target_day,
        target_hour, target_minute, target_second,
        event_lat, event_lng, event_tz_str, event_tz_offset_minutes, house_system, zodiac_type,
    )
    transit_raw = transit_subject.model_dump(mode="json")
    computed = {p: transit_raw[p] for p in DEFAULT_POINTS if p in transit_raw}

    profection_targets = {}
    if annual_lord in natal_raw:
        profection_targets[f"lord_of_year_{annual_lord}"] = natal_raw[annual_lord]
    if monthly_lord in natal_raw and monthly_lord != annual_lord:
        profection_targets[f"lord_of_month_{monthly_lord}"] = natal_raw[monthly_lord]
    else:
        profection_targets[f"lord_of_month_{monthly_lord}"] = natal_raw[monthly_lord]
    profection_targets["profected_ascendant"] = {
        "abs_pos": profected_asc_abs_pos,
        "sign": SIGN_ORDER[annual_sign_num],
    }

    return computed, profection_targets, {
        "age_years_completed": age_years_completed,
        "annual_profected_sign": SIGN_ORDER[annual_sign_num],
        "lord_of_year": annual_lord,
        "monthly_profected_sign": SIGN_ORDER[monthly_sign_num],
        "lord_of_month": monthly_lord,
        "profected_ascendant_abs_pos": round(profected_asc_abs_pos, 4),
        "event_tz_used": ev_resolved_tz,
        "event_tz_source": ev_tz_source,
    }


def _mean_obliquity_deg(year: int) -> float:
    """
    Mean obliquity of the ecliptic for the given year, linear
    approximation (IAU 1980-style, accurate to ~1 arcsecond over a few
    centuries around J2000 - more than sufficient for the zodiacal
    primary direction use case below).
    """
    centuries_from_j2000 = (year - 2000) / 100.0
    return 23.4392911 - 0.0130042 * centuries_from_j2000


def technique_primary_direction_zodiacal(
    natal_year: int, natal_month: int, natal_day: int,
    natal_raw: Dict[str, Any],
    natal_points: Dict[str, Dict[str, Any]],
    target_year: int, target_month: int, target_day: int,
):
    """
    Jan Kefer's "zodiacal primary direction" (Prakticka Astrologie, 1939,
    section on primary directions - see BIBLIOGRAPHY.md): the classical
    Ptolemaic key (1 year of age = 1 degree of arc; 1 month = 5
    arcminutes; 6 days = 1 arcminute - all the same rate, just expressed
    at different granularities for manual calculation) applied via RIGHT
    ASCENSION rather than ecliptic longitude directly, to the Midheaven.

    Scope note: this directs the MC ONLY. Kefer's fuller primary-direction
    method also directs other points (notably the Ascendant) via each
    point's own oblique ascension under the local pole - genuine
    spherical-trigonometry machinery (semi-arcs proportional to
    geographic latitude and the point's declination) that is NOT
    implemented here. Directing the MC alone is well-defined or a single,
    unambiguous formula (the MC's ecliptic longitude and its right
    ascension are related purely by the ecliptic's obliquity, with no
    dependency on geographic latitude), which is why it's implemented on
    its own rather than approximated for other points with a formula that
    would not be Kefer's real method. The resulting directed MC's
    ECLIPTIC longitude is then compared to natal points with ordinary
    zodiacal aspects, same as any other direction technique in this
    engine - that "zodiacal" comparison step is what gives the technique
    its name, as opposed to a fully "mundane" primary direction.
    """
    natal_civil_date = date(natal_year, natal_month, natal_day)
    target_civil_date = date(target_year, target_month, target_day)
    elapsed_years = (target_civil_date - natal_civil_date).days / 365.2425

    obliquity_deg = _mean_obliquity_deg(natal_year)
    eps = math.radians(obliquity_deg)

    natal_mc_lambda = math.radians(natal_raw["medium_coeli"]["abs_pos"])
    natal_ramc = math.degrees(math.atan2(
        math.cos(eps) * math.sin(natal_mc_lambda), math.cos(natal_mc_lambda)
    )) % 360

    directed_ramc = (natal_ramc + elapsed_years * 1.0) % 360
    alpha = math.radians(directed_ramc)
    directed_mc_lambda = math.degrees(math.atan2(
        math.sin(alpha), math.cos(alpha) * math.cos(eps)
    )) % 360

    computed = {}
    mc_base = dict(natal_raw["medium_coeli"])
    mc_base = recompute_sign_fields(mc_base, directed_mc_lambda)
    mc_base["speed"] = 1.0
    computed["medium_coeli"] = mc_base

    ic_base = dict(natal_raw["imum_coeli"])
    ic_base = recompute_sign_fields(ic_base, (directed_mc_lambda + 180) % 360)
    ic_base["speed"] = 1.0
    computed["imum_coeli"] = ic_base

    return computed, natal_points, {
        "elapsed_years": round(elapsed_years, 4),
        "obliquity_deg": round(obliquity_deg, 6),
        "natal_ramc_deg": round(natal_ramc, 4),
        "directed_ramc_deg": round(directed_ramc, 4),
        "directed_mc_ecliptic_lon_deg": round(directed_mc_lambda, 4),
        "scope": "MC/IC only - see docstring for why other points are not directed here",
    }


def technique_relocated_transit(
    natal_year, natal_month, natal_day, natal_hour, natal_minute, natal_second,
    fixed_offset,
    relocate_lat: float, relocate_lng: float,
    house_system, zodiac_type,
    target_year, target_month, target_day, target_hour, target_minute, target_second,
    event_lat, event_lng, event_tz_str, event_tz_offset_minutes,
):
    """
    B. Hammerslaf's relocated-chart technique (see BIBLIOGRAPHY.md): for an
    event happening far from the birth location, the person may respond to
    transits hitting the ANGLES OF THE CHART RELOCATED TO WHERE THEY WERE
    ACTUALLY LIVING/PRESENT at the time, rather than (or in addition to)
    the birth-location angles. This rebuilds the natal chart at the same
    birth instant but a different (relocate_lat, relocate_lng) - which
    shifts the houses/angles but leaves the planets' zodiacal positions
    unchanged - then returns ordinary transiting planets for the event
    date, to be compared against these RELOCATED angles instead of the
    birth-location natal_points.

    fixed_offset is the birth location's own fixed UTC offset (from
    resolve_fixed_offset_minutes on the real birth data) - relocation
    keeps the same universal instant, so the same offset value is reused
    here rather than looking up the new location's own historical
    timezone (which would shift the instant, not just the angles).
    """
    relocated_natal_subject, _, _ = build_subject(
        "relocated_natal", natal_year, natal_month, natal_day,
        natal_hour, natal_minute, natal_second,
        relocate_lat, relocate_lng, None, fixed_offset, house_system, zodiac_type,
    )
    relocated_raw = relocated_natal_subject.model_dump(mode="json")
    relocated_points = {}
    for key in ANGLE_KEYS + HOUSE_KEYS:
        if key in relocated_raw:
            relocated_points[key] = relocated_raw[key]

    transit_subject, ev_resolved_tz, ev_tz_source = build_subject(
        "transit", target_year, target_month, target_day,
        target_hour, target_minute, target_second,
        event_lat, event_lng, event_tz_str, event_tz_offset_minutes, house_system, zodiac_type,
    )
    transit_raw = transit_subject.model_dump(mode="json")
    computed = {p: transit_raw[p] for p in DEFAULT_POINTS if p in transit_raw}

    return computed, relocated_points, {
        "relocated_to": {"lat": relocate_lat, "lng": relocate_lng},
        "event_tz_used": ev_resolved_tz,
        "event_tz_source": ev_tz_source,
    }
