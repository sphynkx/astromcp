"""
astromcp - MCP service entry point.

This module only registers MCP tools and wires them to the implementations
in engine/tools.py. It intentionally contains no astrological or scoring
logic itself - that all lives under engine/, so it can be read, tested, and
modified independently of the MCP transport plumbing.
"""

import logging
import urllib.parse
from typing import Optional, List, Dict, Any

from dotenv import load_dotenv
load_dotenv()

import warnings
warnings.filterwarnings("ignore", message=".*Field 'lifespan' has an incomplete definition.*")

from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from engine import config
from engine import tools
from engine import public_api
from engine import svg_chart
from engine import photo_fetch
from engine.geocode import GeocodeError

logging.basicConfig(level=getattr(logging, config.LOG_LEVEL, logging.INFO))
logger = logging.getLogger("astromcp")

mcp = FastMCP(
    "astromcp",
    host=config.HOST,
    port=config.PORT,
    instructions=(
        "Before doing any rectification (or other astrological analysis) "
        "work with this service, call help() with no arguments first. It "
        "returns an overview of the available tools and points to deeper "
        "topics (e.g. help('rectification')) covering methodology this "
        "service expects you to follow - technique priority order, an "
        "explicit rule against inventing subjective event weights, and "
        "other lessons from real sessions that are not obvious from the "
        "tool signatures alone."
    ),
)


@mcp.tool()
def rectif_chart(
    year: int, month: int, day: int,
    hour: int, minute: int, second: int = 0,
    lat: float = 0.0, lng: float = 0.0,
    tz_str: Optional[str] = None,
    tz_offset_minutes: Optional[int] = None,
    house_system: str = config.DEFAULT_HOUSE_SYSTEM,
    zodiac_type: str = config.DEFAULT_ZODIAC_TYPE,
    points: Optional[List[str]] = None,
    include_raw: bool = False,
    name: str = "subject",
) -> Dict[str, Any]:
    """
    Builds a chart (planet positions, house cusps, ASC/MC angles) for an
    arbitrary date/time/place. Used as the base primitive for rectification:
    transits, progressions, directions, profections and solar returns are
    computed on top of this tool's output.

    tz_str - IANA zone (e.g. "Asia/Novosibirsk"). Or instead of it,
    tz_offset_minutes - an explicit whole-hour UTC offset (e.g. 480 for UTC+8),
    for cases where auto-resolving via current zone boundaries would be
    historically incorrect.
    house_system - single-letter kerykeion house system code (P=Placidus,
    K=Koch, W=Whole Sign, R=Regiomontanus, E=Equal, ...). Default is
    configurable via ASTROMCP_HOUSE_SYSTEM in .env.
    """
    return tools.rectif_chart(
        year, month, day, hour, minute, second, lat, lng,
        tz_str, tz_offset_minutes, house_system, zodiac_type,
        points, include_raw, name,
    )


@mcp.tool()
def rectif_chart_batch(requests: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Batch version of rectif_chart: accepts a list of objects with the same
    fields as rectif_chart, returns a list of results in the same order.
    """
    return tools.rectif_chart_batch(requests)


@mcp.tool()
def rectif_technique(
    natal_year: int, natal_month: int, natal_day: int,
    natal_hour: int, natal_minute: int, natal_second: int,
    natal_lat: float, natal_lng: float,
    natal_tz_str: Optional[str] = None,
    natal_tz_offset_minutes: Optional[int] = None,
    house_system: str = config.DEFAULT_HOUSE_SYSTEM,
    zodiac_type: str = config.DEFAULT_ZODIAC_TYPE,
    technique: str = "transit",  # secondary_progression | solar_arc | solar_return | profection | primary_direction_zodiacal | relocated_transit | transit
    target_year: int = 2000, target_month: int = 1, target_day: int = 1,
    target_hour: int = 12, target_minute: int = 0, target_second: int = 0,
    angle_method: str = "solar_arc_naibod",  # for secondary_progression
    event_lat: Optional[float] = None, event_lng: Optional[float] = None,
    event_tz_str: Optional[str] = None, event_tz_offset_minutes: Optional[int] = None,
    compute_aspects_flag: bool = True,
    aspect_set: Optional[List[float]] = None,
    orb_table: Optional[Dict[str, float]] = None,
    luminary_orb_bonus: Optional[float] = None,
    relocate_lat: Optional[float] = None, relocate_lng: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Computes a predictive technique (secondary progression, solar arc
    direction, solar return, annual/monthly profection, zodiacal primary
    direction, relocated-chart transit, or transit) for a natal chart, and
    optionally the aspects it forms to the natal chart. This is the core
    engine for rectification: run it once per candidate event, per
    candidate birth time.

    technique="primary_direction_zodiacal": Jan Kefer's zodiacal primary
    direction (Prakticka Astrologie, 1939) - the Ptolemaic key (1 year =
    1 degree of arc) applied via right ascension to the Midheaven, then
    compared to natal points as ordinary zodiacal (ecliptic) aspects.
    Directs the MC/IC only - other points would need each their own
    oblique-ascension-under-the-pole calculation, not implemented here
    (see the function's docstring in engine/techniques.py). Uses the
    tight ~1 degree "direction" orb by default, like solar_arc.

    technique="relocated_transit": B. Hammerslaf's relocated-chart
    technique - for an event far from the birth location, rebuilds the
    natal chart's angles at (relocate_lat, relocate_lng) - same birth
    instant, different place - and checks ordinary transiting planets for
    the event date/time against THOSE relocated angles instead of the
    birth-location ones. If relocate_lat/lng aren't given, defaults to
    event_lat/lng (i.e. relocate to the event's own location, the most
    common case per the source).

    technique="profection": Hellenistic annual/monthly profections. The
    natal Ascendant symbolically advances one whole sign per completed year
    of age (and, within that year, one more sign per completed month); the
    traditional ruler of the resulting sign is the "Lord of the
    Year"/"Lord of the Month". Unlike other techniques, the natal-side
    target set here is narrowed by the technique itself to just
    {lord_of_year, lord_of_month, profected_ascendant} - target_points/
    aspect_set still apply to filter which transiting planets/aspects
    count as hits, but the natal targets are fixed by the technique, not
    by the caller. target_hour/minute/second are used for the event's exact
    transit moment as usual; only target_year/month/day (plus the natal
    date) determine the profected sign itself.

    technique="solar_return": builds the chart for the exact moment the
    transiting Sun returns to its natal degree in target_year (found by
    iterative search, not assumed to fall on the calendar birthday - it can
    drift up to about a day either way). Only target_year is used from the
    target_* fields. event_lat/event_lng relocate the return chart (defaults
    to the natal location - a "radix" solar return - if not given). This
    search is several times more expensive than the other techniques (a
    handful of chart builds per call instead of one) - for scanning many
    candidates with solar_return, prefer rectif_scan_start over rectif_scan.

    Default orbs are technique-aware: transits, solar returns, profections,
    and relocated transits use wide classical orbs, while progressions/
    directions (including primary_direction_zodiacal) use tight ~1 degree
    orbs (since 1 degree of arc corresponds to roughly 1 year of life, a
    wide orb there directly translates into years of dating error). Pass
    orb_table/luminary_orb_bonus explicitly to override; defaults are also
    tunable via .env.
    """
    return tools.rectif_technique(
        natal_year, natal_month, natal_day, natal_hour, natal_minute, natal_second,
        natal_lat, natal_lng, natal_tz_str, natal_tz_offset_minutes,
        house_system, zodiac_type, technique,
        target_year, target_month, target_day, target_hour, target_minute, target_second,
        angle_method, event_lat, event_lng, event_tz_str, event_tz_offset_minutes,
        compute_aspects_flag, aspect_set, orb_table, luminary_orb_bonus,
        relocate_lat, relocate_lng,
    )


@mcp.tool()
def rectif_technique_batch(requests: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Batch version of rectif_technique. Same fields per item, list in -> list out."""
    return tools.rectif_technique_batch(requests)


@mcp.tool()
def rectif_scan(
    natal_year: int, natal_month: int, natal_day: int,
    natal_lat: float, natal_lng: float,
    natal_tz_str: Optional[str] = None,
    natal_tz_offset_minutes: Optional[int] = None,
    house_system: str = config.DEFAULT_HOUSE_SYSTEM,
    zodiac_type: str = config.DEFAULT_ZODIAC_TYPE,
    scan_start_hour: int = 0, scan_start_minute: int = 0,
    scan_end_hour: int = 23, scan_end_minute: int = 59,
    step_minutes: int = 2,
    events: Optional[List[Dict[str, Any]]] = None,
    target_points: Optional[List[str]] = None,
    aspect_set: Optional[List[float]] = None,
    orb_threshold: float = config.DEFAULT_SCAN_ORB_THRESHOLD,
    top_n: int = 20,
    include_full_table: bool = False,
    scan_start_second: int = 0,
    scan_end_second: int = 59,
    step_seconds: Optional[int] = None,
) -> Dict[str, Any]:
    """
    EXPLORATORY / HEURISTIC ONLY - this tool's scoring (summing a hit-count
    across events into total_score, then ranking candidates by that number)
    is NOT a documented rectification method from any surveyed source. It
    was invented for this service and should not be presented as
    "confirmed" or "the most likely time" on its own. Prefer
    rectif_movements_scan (Grishchenyuk's literal 2-of-3 movements rule)
    or another criterion-based tool for anything you intend to draw a
    conclusion from; use this one only to get a rough sense of where to
    aim a real criterion-based check, per help_texts/rectification.md.

    Synchronous scan: sweeps candidate birth times across [scan_start,
    scan_end] on the given birth date (in step_minutes, or step_seconds for
    sub-minute precision), scores every event in `events` per candidate, and
    returns the top_n candidates ranked by total score. Blocks until done -
    fine for small scans, but a wide range with many events and/or
    technique="solar_return" can take long enough to hit MCP/proxy timeouts.
    For those, use rectif_scan_start + rectif_scan_result instead.

    Each event dict: {name, technique: "transit"|"secondary_progression"|
    "solar_arc"|"solar_return"|"profection", target_year, target_month,
    target_day, target_hour?, target_minute?, target_second?, event_lat?,
    event_lng?, event_tz_str?, event_tz_offset_minutes?, angle_method?,
    weight?, aspect_set?, orb_table?, target_points?, target_houses?,
    orb_threshold?}. For technique="solar_return", only target_year is
    used. For technique="profection", target_points/target_houses are
    ignored (the technique fixes its own natal-side targets: lord of the
    year/month, profected Asc).

    target_houses (list of house numbers, 1-12) is an alternative to
    target_points: instead of a fixed point list, the natal-side targets
    for that event become the "elements" of those houses (ruler, co-ruler,
    occupying planets - recomputed fresh for every candidate, since house
    rulership shifts with birth time) - see the Shestopalov/Aizin-school
    methodology in help_texts/rectification.md for how to pick which
    houses apply to a given event. If both target_points and target_houses
    are given, target_houses takes precedence for that event.
    """
    return tools.rectif_scan(
        natal_year, natal_month, natal_day, natal_lat, natal_lng,
        natal_tz_str, natal_tz_offset_minutes, house_system, zodiac_type,
        scan_start_hour, scan_start_minute, scan_end_hour, scan_end_minute,
        step_minutes, events, target_points, aspect_set, orb_threshold,
        top_n, include_full_table,
        scan_start_second, scan_end_second, step_seconds,
    )


@mcp.tool()
def rectif_scan_start(
    natal_year: int, natal_month: int, natal_day: int,
    natal_lat: float, natal_lng: float,
    natal_tz_str: Optional[str] = None,
    natal_tz_offset_minutes: Optional[int] = None,
    house_system: str = config.DEFAULT_HOUSE_SYSTEM,
    zodiac_type: str = config.DEFAULT_ZODIAC_TYPE,
    scan_start_hour: int = 0, scan_start_minute: int = 0,
    scan_end_hour: int = 23, scan_end_minute: int = 59,
    step_minutes: int = 2,
    events: Optional[List[Dict[str, Any]]] = None,
    target_points: Optional[List[str]] = None,
    aspect_set: Optional[List[float]] = None,
    orb_threshold: float = config.DEFAULT_SCAN_ORB_THRESHOLD,
    top_n: int = 20,
    include_full_table: bool = False,
    scan_start_second: int = 0,
    scan_end_second: int = 59,
    step_seconds: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Async scan: same parameters as rectif_scan, but returns immediately with
    a {job_id, status: "running"} instead of blocking. The scan runs in a
    background thread on the server. Poll rectif_scan_result(job_id) to
    retrieve the outcome once it's done. Use this for anything large: wide
    time ranges, many events, or technique="solar_return" (which is several
    times more expensive per event than the other techniques).
    """
    return tools.rectif_scan_start(
        natal_year, natal_month, natal_day, natal_lat, natal_lng,
        natal_tz_str, natal_tz_offset_minutes, house_system, zodiac_type,
        scan_start_hour, scan_start_minute, scan_end_hour, scan_end_minute,
        step_minutes, events, target_points, aspect_set, orb_threshold,
        top_n, include_full_table,
        scan_start_second, scan_end_second, step_seconds,
    )


@mcp.tool()
def rectif_scan_result(job_id: str) -> Dict[str, Any]:
    """
    Polls the status/result of a scan started with rectif_scan_start.
    Returns {status: "running"} while still in progress (with
    elapsed_seconds), {status: "done", result: <same shape as rectif_scan's
    return value>, elapsed_seconds} once finished, or {status: "error",
    error: <message>} if the scan raised an exception. {status: "not_found"}
    if job_id is unknown (e.g. after a service restart - jobs are in-memory
    only and don't survive one).
    """
    return tools.rectif_scan_result(job_id)


@mcp.tool()
def rectif_trutina(
    natal_year: int, natal_month: int, natal_day: int,
    natal_lat: float, natal_lng: float,
    natal_tz_str: Optional[str] = None,
    natal_tz_offset_minutes: Optional[int] = None,
    house_system: str = config.DEFAULT_HOUSE_SYSTEM,
    zodiac_type: str = config.DEFAULT_ZODIAC_TYPE,
    initial_guess_hour: int = 12, initial_guess_minute: int = 0, initial_guess_second: int = 0,
    max_iterations: int = 30,
    mother_year: Optional[int] = None, mother_month: Optional[int] = None, mother_day: Optional[int] = None,
    mother_hour: Optional[int] = None, mother_minute: Optional[int] = None, mother_second: Optional[int] = None,
    mother_lat: Optional[float] = None, mother_lng: Optional[float] = None,
    mother_tz_str: Optional[str] = None, mother_tz_offset_minutes: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Trutine of Hermes (Trutina Hermetis): classical fast rectification via
    the reciprocal Moon/Ascendant relationship between the birth chart and
    the theoretical conception (epoch) chart - see Jan Kefer, Prakticka
    Astrologie (1939), and W. Lilly, Christian Astrology pp.502-505 for the
    gestation-length day-count refinement. Unlike rectif_scan, this does
    NOT need any life events at all and does NOT brute-force many
    candidates - it solves directly (a handful of chart builds via
    fixed-point iteration from initial_guess_*), so it's fast and can be
    used as a first, resource-light starting point even when nothing
    whatsoever is known about the birth time.

    Returns FOUR branches (Kefer's original formulation treats Moon
    above/below horizon and waxing/waning as two independent conditions,
    not one condition with two states), because none of this can be known
    without already knowing the birth time being solved for. Compare all
    four against any other evidence you have (rough time-of-day testimony,
    or agreement with rectif_scan / rectif_technique results from actual
    life events) to pick between them.

    Optional Jonas Rule refinement: if the mother's own birth data is
    supplied (mother_year etc.), the conception DATE is fixed directly by
    finding when the transiting Sun-Moon angular separation matches the
    mother's natal Sun-Moon separation (Dr. Eugen Jonas's rule, medically
    documented) - this removes the classical method's biggest weakness,
    the ~10 candidate conception dates within the gestation window that
    the classical rule alone cannot distinguish between. Worth asking for
    if at all available.

    Documented limitations of the classical method itself (not this
    implementation): assumes conception occurred at the birth location,
    and assumes a natural (non medically altered) gestation length. On
    some charts a branch will not settle to a single instant at all -
    the classical whole-day gestation table can put the true fixed point
    right on an integer-day boundary, causing the iteration to cycle
    between a few nearby candidate times instead of converging. When this
    happens the branch reports cycle_detected=true and a cycle_candidates
    list of the times involved, rather than an arbitrary single answer.
    Traditionally used as a fast preliminary estimate or cross-check
    alongside other techniques, not a sole source of truth.
    """
    return tools.rectif_trutina(
        natal_year, natal_month, natal_day, natal_lat, natal_lng,
        natal_tz_str, natal_tz_offset_minutes, house_system, zodiac_type,
        initial_guess_hour, initial_guess_minute, initial_guess_second, max_iterations,
        mother_year, mother_month, mother_day, mother_hour, mother_minute, mother_second,
        mother_lat, mother_lng, mother_tz_str, mother_tz_offset_minutes,
    )


@mcp.tool()
def rectif_movements_scan(
    natal_year: int, natal_month: int, natal_day: int,
    natal_lat: float, natal_lng: float,
    natal_tz_str: Optional[str] = None,
    natal_tz_offset_minutes: Optional[int] = None,
    house_system: str = config.DEFAULT_HOUSE_SYSTEM,
    zodiac_type: str = config.DEFAULT_ZODIAC_TYPE,
    scan_start_hour: int = 0, scan_start_minute: int = 0,
    scan_end_hour: int = 23, scan_end_minute: int = 59,
    step_minutes: int = 2,
    target_year: int = 2000, target_month: int = 1, target_day: int = 1,
    target_houses: Optional[List[int]] = None,
    target_points: Optional[List[str]] = None,
    direction_orb_deg: float = 1.0,
    transit_orb_deg: float = 3.0,
    scan_start_second: int = 0, scan_end_second: int = 59,
    step_seconds: Optional[int] = None,
) -> Dict[str, Any]:
    """
    A. Grishchenyuk (1996), transcribing the Zaprjagaev -> Vronsky ->
    Shestopalov method (St. Petersburg Academy of Astrology), reproduced
    literally - NOT a score. For ONE event (given by target_year/month/day
    and either target_houses or target_points), checks at every candidate
    birth time whether at least 2 of 3 independent "movements" -
    secondary progression, "perfection" (whole-chart symbolic direction
    at 30 deg/year), and transit - each produce at least one hard aspect
    (conjunction/square/opposition, within direction_orb_deg for the two
    directed movements and transit_orb_deg for the transit) to the
    event's targets. The source states this threshold explicitly:
    3-of-3 concordant movements means ~100% probability the event maps to
    that candidate time; 2-of-3 means ~66%. Below that, the source does
    not consider the time confirmed at all.

    Returns qualifying_windows: contiguous [start, end] time ranges meeting
    the >=2-of-3 threshold, each labeled with which movements hit and the
    source's own stated concordance level (3-of-3 or 2-of-3) - grouped
    from consecutive qualifying candidates rather than listed one by one,
    purely to keep the result compact; NOT ranked or scored. Check
    candidates_qualifying_raw_count against candidates_tested - if a large
    fraction of the day qualifies, the orbs are too loose to narrow
    anything on this event alone; tighten direction_orb_deg/
    transit_orb_deg, or rely on intersecting with other events instead.
    To combine evidence across several events (the real rectification
    workflow - see help_texts/rectification.md), call this once per event
    and intersect the qualifying windows by hand (only keep times that
    qualify for every event checked), the way A. Budarovsky's worked
    example does it - narrow with one event, then re-check only the
    surviving window with the next. Do not sum or average results across
    events.

    house_system should be Koch ("K") - the source is explicit that this
    technique is tied to Koch houses specifically.
    """
    return tools.rectif_movements_scan(
        natal_year, natal_month, natal_day, natal_lat, natal_lng,
        natal_tz_str, natal_tz_offset_minutes, house_system, zodiac_type,
        scan_start_hour, scan_start_minute, scan_end_hour, scan_end_minute,
        step_minutes, target_year, target_month, target_day,
        target_houses, target_points, direction_orb_deg, transit_orb_deg,
        scan_start_second, scan_end_second, step_seconds,
    )


@mcp.tool()
def rectif_timoshenko_scan(
    natal_year: int, natal_month: int, natal_day: int,
    natal_lat: float, natal_lng: float,
    natal_tz_str: Optional[str] = None,
    natal_tz_offset_minutes: Optional[int] = None,
    house_system: str = config.DEFAULT_HOUSE_SYSTEM,
    zodiac_type: str = config.DEFAULT_ZODIAC_TYPE,
    scan_start_hour: int = 0, scan_start_minute: int = 0,
    scan_end_hour: int = 23, scan_end_minute: int = 59,
    step_minutes: int = 2,
    target_year: int = 2000, target_month: int = 1, target_day: int = 1,
    house_num: int = 1,
    orb_deg: float = 1.0,
    scan_start_second: int = 0, scan_end_second: int = 59,
    step_seconds: Optional[int] = None,
) -> Dict[str, Any]:
    """
    I. Timoshenko's rectification method (VALIRAN astrological center,
    2001), reproduced literally - NOT a score. For ONE house at ONE event
    date, checks at every candidate birth time whether FOUR conditions
    ALL hold simultaneously (an AND, not a threshold like Grishchenyuk's
    2-of-3): the solar-arc-DIRECTED ruler of house_num sends a hard aspect
    to a natal element of that house (ruler/co-ruler/occupants); the
    DIRECTED cusp of house_num likewise sends one; the NATAL ruler
    receives a hard aspect from some directed element of the house; the
    NATAL cusp likewise receives one.

    Returns qualifying_windows: contiguous [start, end] ranges where all
    four conditions held at once, grouped from consecutive candidates -
    NOT ranked or scored. Check candidates_qualifying_raw_count against
    candidates_tested - if very few or very many candidates qualify,
    adjust orb_deg. To combine evidence across several events, call this
    once per event/house and intersect the qualifying windows by hand,
    same as rectif_movements_scan - do not sum or average anything.

    The source claims this test, combined with its own interval-
    intersection search (narrowing across ~10 points, not fully
    reproduced by this brute-force scan), reaches 10-30 second precision
    on real charts. That precision claim has not been independently
    re-verified here - only the four-condition test itself is faithfully
    reproduced. house_system should probably be Koch ("K") for
    consistency with the rest of this lineage's methodology, though the
    source's own house-system requirement was not confirmed as explicitly
    as Grishchenyuk's.
    """
    return tools.rectif_timoshenko_scan(
        natal_year, natal_month, natal_day, natal_lat, natal_lng,
        natal_tz_str, natal_tz_offset_minutes, house_system, zodiac_type,
        scan_start_hour, scan_start_minute, scan_end_hour, scan_end_minute,
        step_minutes, target_year, target_month, target_day, house_num, orb_deg,
        scan_start_second, scan_end_second, step_seconds,
    )


@mcp.tool()
def rectif_bonatti_scan(
    natal_year: int, natal_month: int, natal_day: int,
    natal_lat: float, natal_lng: float,
    natal_tz_str: Optional[str] = None,
    natal_tz_offset_minutes: Optional[int] = None,
    house_system: str = config.DEFAULT_HOUSE_SYSTEM,
    zodiac_type: str = config.DEFAULT_ZODIAC_TYPE,
    scan_start_hour: int = 0, scan_start_minute: int = 0,
    scan_end_hour: int = 23, scan_end_minute: int = 59,
    step_minutes: int = 2,
    orb_deg: float = 1.0,
    affliction_orb_deg: float = 8.0,
    scan_start_second: int = 0, scan_end_second: int = 59,
    step_seconds: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Guido Bonatti's method (via Jan Kefer, Prakticka Astrologie, 1939),
    reproduced literally. NOT a primary technique - the source explicitly
    says to use this only in combination with another correction, never
    alone. No life events needed: for every candidate, checks the Sun's
    condition (afflicted by hard aspect to Saturn/Uranus/Mars, within
    affliction_orb_deg, or not) and the corresponding rule - if
    unafflicted, some angle (ASC/DSC/MC/IC) is the midpoint of the Sun and
    some planet; if afflicted, some angle is in conjunction with some
    planet - within orb_deg.

    Returns qualifying_windows (contiguous ranges where the rule holds) -
    NOT ranked or scored. Given the source's own caution, treat this as a
    weak auxiliary signal: intersect with a stronger technique's
    qualifying windows rather than relying on it by itself.
    """
    return tools.rectif_bonatti_scan(
        natal_year, natal_month, natal_day, natal_lat, natal_lng,
        natal_tz_str, natal_tz_offset_minutes, house_system, zodiac_type,
        scan_start_hour, scan_start_minute, scan_end_hour, scan_end_minute,
        step_minutes, orb_deg, affliction_orb_deg,
        scan_start_second, scan_end_second, step_seconds,
    )


@mcp.tool()
def rectif_degree_clustering(
    events: List[Dict[str, Any]],
    natal_year: int, natal_month: int, natal_day: int,
    natal_lat: float, natal_lng: float,
    natal_tz_str: Optional[str] = None,
    natal_tz_offset_minutes: Optional[int] = None,
    house_system: str = config.DEFAULT_HOUSE_SYSTEM,
    zodiac_type: str = config.DEFAULT_ZODIAC_TYPE,
    round_to_deg: float = 1.0,
    exclude_natal_occupied_deg_tolerance: float = 2.0,
    top_n: int = 10,
    convert_top_peaks_to_times: bool = True,
) -> Dict[str, Any]:
    """
    B. Israitel's "condensation method" / B. Brady's "graphic
    rectification" (see BIBLIOGRAPHY.md) - a fundamentally different
    approach from every other tool in this service: it does NOT scan
    candidate birth times at all. Instead, it collects the positions of
    slower transiting planets (Mars through Pluto, plus the nodes - fast
    personal planets are deliberately excluded as too imprecise for this)
    across MANY life events, and finds which zodiacal degrees recur most
    often. A recurring degree with no natal planet already there is a
    hypothesis for where an ANGULAR house cusp sits.

    events: list of {year, month, day, hour?, minute?, second?, lat?,
    lng?, tz_str?, tz_offset_minutes?} - one per life event, no birth
    time needed for any of them (only the event's own date/time). Both
    sources want a large number: Brady specifically recommends ~15
    ANGULAR events (relationship/birth/death of close people - NOT
    arbitrary events) for 80-100 data points; Israitel similarly wants a
    large volume. Both sources also say this method is only reliable once
    birth-time uncertainty is already under 20-30 minutes - it's a
    refinement tool, not a wide-open search technique like rectif_scan
    or rectif_movements_scan.

    Returns peaks_excluding_natal_planet_degrees: degrees sorted by raw
    recurrence count (the method's own frequency tally - not an invented
    score), each with candidate birth times (as_ascendant_time and
    as_medium_coeli_time) that would place that degree on the Ascendant
    or Midheaven respectively, via convert_top_peaks_to_times - since a
    peak degree alone doesn't say which angle it represents.
    """
    return tools.rectif_degree_clustering(
        events, natal_year, natal_month, natal_day, natal_lat, natal_lng,
        natal_tz_str, natal_tz_offset_minutes, house_system, zodiac_type,
        round_to_deg, exclude_natal_occupied_deg_tolerance, top_n, convert_top_peaks_to_times,
    )


@mcp.tool()
def rectif_herich_scan(
    natal_year: int, natal_month: int, natal_day: int,
    natal_lat: float, natal_lng: float,
    natal_tz_str: Optional[str] = None,
    natal_tz_offset_minutes: Optional[int] = None,
    house_system: str = config.DEFAULT_HOUSE_SYSTEM,
    zodiac_type: str = config.DEFAULT_ZODIAC_TYPE,
    scan_start_hour: int = 0, scan_start_minute: int = 0,
    scan_end_hour: int = 23, scan_end_minute: int = 59,
    step_minutes: int = 2,
    orb_deg: float = 8.0,
    check_all_house_cusps: bool = False,
    scan_start_second: int = 0, scan_end_second: int = 59,
    step_seconds: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Herich's number (Paul von Gerich, 1929/1930 article - see
    BIBLIOGRAPHY.md), reproduced literally. NOT a primary technique - a
    weak auxiliary check the source's own author acknowledges can be off
    by up to 8 degrees. No life events needed: taking pairwise midpoints
    of Sun, Moon, and Saturn in a chained formula (a = midpoint of
    midpoint(Moon,Sun) and midpoint(Saturn,Sun); b = midpoint of a and
    midpoint(Moon,Saturn)), checks whether b falls within orb_deg of the
    Ascendant or Midheaven (the source's primary claim; pass
    check_all_house_cusps=True for its weaker secondary claim that b may
    coincide with any house cusp).

    Returns qualifying_windows (contiguous ranges where the rule holds) -
    NOT ranked or scored. Given the source's own stated uncertainty,
    treat this as a weak auxiliary signal: intersect with a stronger
    technique's qualifying windows rather than relying on it alone.
    """
    return tools.rectif_herich_scan(
        natal_year, natal_month, natal_day, natal_lat, natal_lng,
        natal_tz_str, natal_tz_offset_minutes, house_system, zodiac_type,
        scan_start_hour, scan_start_minute, scan_end_hour, scan_end_minute,
        step_minutes, orb_deg, check_all_house_cusps,
        scan_start_second, scan_end_second, step_seconds,
    )


ASTRO_HELP_DOC = {
    "title": "astromcp /astro - available parameters",
    "content": (
        "GET /astro returns a full natal chart (planets, houses, aspects, "
        "fixed stars, Arabic Part of Fortune) as flat JSON, meant for "
        "MediaWiki's External Data extension or any other plain HTTP JSON "
        "caller. Requires at least 'date' plus a location (lat+lon, or "
        "city). GET /astro/chart.svg takes the same params (plus name/"
        "place/filename) and returns the same chart rendered as an SVG "
        "wheel instead of JSON."
    ),
    "params": {
        "date": "required. DD.MM.YYYY",
        "time": "optional. HH:MM or HH:MM:SS, default 12:00",
        "lat, lon": "decimal degrees ('lng' also accepted as an alias for 'lon')",
        "city": (
            "city name. English, or Russian (both a curated exonym table "
            "for cases like Москва/Moscow, and Cyrillic spellings "
            "geonamescache already carries as alternate names, plus a "
            "transliteration fallback) - resolved offline, only used if "
            "lat/lon are not given"
        ),
        "country_code": (
            "optional, disambiguates a common city name. ISO 3166-1 "
            "alpha-2 (e.g. UA), OR a country name in English or Russian "
            "(e.g. Ukraine / Украина)"
        ),
        "tz": "IANA timezone name, e.g. Europe/Kyiv",
        "tz_offset": (
            "whole-hour UTC offset in minutes, e.g. 180 for UTC+3; overrides "
            "'tz' if both are given. If neither tz nor tz_offset is given, "
            "falls back to timezonefinder's MODERN zone lookup - not safe "
            "for historical dates, pass one explicitly for those"
        ),
        "house_system": (
            "single-letter kerykeion code, default from ASTROMCP_HOUSE_SYSTEM "
            "(P=Placidus, K=Koch, W=Whole Sign, E=Equal, R=Regiomontanus, "
            "C=Campanus, O=Porphyry, M=Morinus). One system per call"
        ),
        "no_aspects": "=1 to omit the 'aspects' section (JSON endpoint only)",
        "no_house_cusp_aspects": "=1 to compute aspects for planets/angles only, excluding the 12 house cusps as targets (JSON endpoint only)",
        "no_stars": "=1 to omit 'fixed_stars' / 'fixed_star_conjunctions' (JSON endpoint only)",
        "no_parts": "=1 to omit 'arabic_parts' (JSON endpoint only)",
        "name": "SVG endpoint only - person's name for the chart header (free text)",
        "place": "SVG endpoint only - place name for the chart header, overrides the resolved city name",
        "filename": (
            "SVG endpoint only - suggested filename for the response's "
            "Content-Disposition header (e.g. from a MediaWiki page title) "
            "- affects what a browser's 'save as' proposes, not the image itself"
        ),
        "photo_url": "SVG endpoint only - absolute URL to a portrait image, drawn in the chart header if given",
    },
    "examples": [
        "GET /astro?date=23.11.1993&time=14:30&lat=50.45&lon=30.52",
        "GET /astro?date=23.11.1993&time=14:30&city=Kyiv",
        "GET /astro?date=23.11.1993&time=14:30&city=Kyiv&house_system=K",
        "GET /astro/chart.svg?date=23.11.1993&time=14:30&city=Kyiv&name=Test+Person",
    ],
}


def _astro_error(message: str, status_code: int) -> JSONResponse:
    """
    Every error response from /astro carries the same 'help' block as a
    bare request with no params does (see astro_report below) - so a
    typo'd param or a missing 'date' doesn't send the caller hunting
    through README.md, whether they're at a curl prompt or parsing this
    from a MediaWiki External Data call.
    """
    return JSONResponse({"error": message, "help": ASTRO_HELP_DOC}, status_code=status_code)


def _parse_astro_query(q) -> dict:
    """
    Shared parameter parsing for /astro and /astro/chart.svg - both need
    the same date/time/location/timezone/house_system inputs, just render
    them differently (JSON report vs. SVG wheel). Raises ValueError with a
    caller-safe message on any bad/missing input; GeocodeError propagates
    from build_full_report unchanged. Returns kwargs ready to splat into
    public_api.build_full_report().
    """
    date_str = q.get("date")
    if not date_str:
        raise ValueError("missing required 'date' param (DD.MM.YYYY)")
    try:
        day, month, year = (int(x) for x in date_str.split("."))
    except ValueError:
        raise ValueError(f"invalid 'date' value '{date_str}' - expected DD.MM.YYYY")

    time_str = q.get("time", "12:00")
    try:
        time_parts = time_str.split(":")
        hour, minute = int(time_parts[0]), int(time_parts[1])
        second = int(time_parts[2]) if len(time_parts) > 2 else 0
    except (ValueError, IndexError):
        raise ValueError(f"invalid 'time' value '{time_str}' - expected HH:MM or HH:MM:SS")

    try:
        lat = float(q["lat"]) if "lat" in q else None
        lng = float(q["lon"]) if "lon" in q else (float(q["lng"]) if "lng" in q else None)
    except ValueError:
        raise ValueError("invalid 'lat'/'lon' value - expected decimal degrees")
    city = q.get("city")
    country_code = q.get("country_code")

    if lat is None and lng is None and not city:
        raise ValueError("provide either lat+lon, or a city name")

    tz_str = q.get("tz")
    try:
        tz_offset = int(q["tz_offset"]) if "tz_offset" in q else None
    except ValueError:
        raise ValueError("invalid 'tz_offset' value - expected whole minutes, e.g. 180")

    house_system = q.get("house_system")

    return dict(
        year=year, month=month, day=day, hour=hour, minute=minute, second=second,
        lat=lat, lng=lng, city=city, country_code=country_code,
        tz_str=tz_str, tz_offset_minutes=tz_offset, house_system=house_system,
    )


@mcp.custom_route("/astro", methods=["GET"])
async def astro_report(request: Request) -> JSONResponse:
    """
    Plain HTTP GET endpoint, separate from the MCP tool protocol above -
    meant for MediaWiki's External Data extension or any other non-MCP
    JSON caller. Lives on the same host/port as the MCP endpoint (no new
    infra, no nginx changes) via Starlette's custom_route mechanism.

    GET /astro with no query params at all returns ASTRO_HELP_DOC directly
    (status 200, not an error) - a bare request is discovery, not a
    mistake. Any request that has params but is invalid or incomplete
    returns {"error": ..., "help": ASTRO_HELP_DOC} instead, so the same
    parameter reference is always one field away rather than only living
    in README.md.

    GET /astro?date=23.11.1993&time=14:30&lat=50.45&lon=30.52
    GET /astro?date=23.11.1993&time=14:30&city=Kyiv

    See ASTRO_HELP_DOC above for the full parameter list - kept in one
    place so the docstring here and the runtime help response can't drift
    apart. See also GET /astro/chart.svg for the SVG wheel rendering of
    the same data.
    """
    q = request.query_params
    if len(q) == 0:
        return JSONResponse({"help": ASTRO_HELP_DOC})

    try:
        params = _parse_astro_query(q)
        result = public_api.build_full_report(
            **params,
            include_aspects=(q.get("no_aspects") != "1"),
            include_house_cusp_aspects=(q.get("no_house_cusp_aspects") != "1"),
            include_fixed_stars=(q.get("no_stars") != "1"),
            include_arabic_parts=(q.get("no_parts") != "1"),
        )
        return JSONResponse(result)

    except GeocodeError as e:
        return _astro_error(str(e), 404)
    except ValueError as e:
        return _astro_error(str(e), 400)
    except Exception as e:
        logger.exception("astro_report failed")
        return _astro_error(str(e), 500)


@mcp.custom_route("/astro/chart.svg", methods=["GET"])
async def astro_chart_svg(request: Request) -> Response:
    """
    Same date/time/location/timezone/house_system params as /astro (see
    ASTRO_HELP_DOC), rendered as an SVG natal chart wheel instead of JSON -
    see engine/svg_chart.py for the drawing itself and the design notes
    behind its color/layout choices.

    GET /astro/chart.svg?date=23.11.1993&time=14:30&city=Kyiv
      &name=Displayed+person+name        (optional, header line 1)
      &place=Displayed+place+name        (optional, header line 3 -
                                          overrides the resolved city name)
      &filename=Some_name.svg            (optional - sets Content-Disposition
                                          so "save as" suggests this name,
                                          e.g. from a MediaWiki page title;
                                          does NOT affect the response body)

    Errors return a small SVG containing the error text (status code still
    set correctly) rather than JSON - an <img>/external-image consumer
    like MediaWiki has nowhere to show JSON error text, so a broken image
    with visible text is more useful than a broken image with none.
    """
    q = request.query_params
    try:
        params = _parse_astro_query(q)
        report = public_api.build_full_report(
            **params,
            include_aspects=True,
            include_house_cusp_aspects=True,
            include_fixed_stars=True,
            include_arabic_parts=False,
        )
        photo_data_uri = photo_fetch.fetch_photo_as_data_uri(q.get("photo_url"))
        svg_text = svg_chart.build_natal_chart_svg(
            report,
            person_name=q.get("name"),
            place_label=q.get("place"),
            photo_url=photo_data_uri,
        )
        headers = {}
        filename = q.get("filename")
        if filename:
            # RFC 6266 - filename* is required for non-ASCII (Cyrillic)
            # names; filename= fallback keeps older clients from choking.
            quoted = urllib.parse.quote(filename)
            headers["Content-Disposition"] = f"inline; filename=\"chart.svg\"; filename*=UTF-8''{quoted}"
        return Response(svg_text, media_type="image/svg+xml", headers=headers)

    except GeocodeError as e:
        return _astro_svg_error(str(e), 404)
    except ValueError as e:
        return _astro_svg_error(str(e), 400)
    except Exception as e:
        logger.exception("astro_chart_svg failed")
        return _astro_svg_error(str(e), 500)


def _astro_svg_error(message: str, status_code: int) -> Response:
    safe = message.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="480" height="120">'
        '<rect width="480" height="120" fill="#fff0f0" stroke="#c23b3b"/>'
        f'<text x="12" y="30" font-size="13" fill="#a03030">astromcp /astro/chart.svg error:</text>'
        f'<text x="12" y="55" font-size="12" fill="#333">{safe}</text>'
        '</svg>'
    )
    return Response(svg, media_type="image/svg+xml", status_code=status_code)


@mcp.tool()
def ping(message: str = "world") -> str:
    """Simple connectivity test."""
    return tools.ping(message)


@mcp.tool()
def help(topic: str = "overview") -> str:
    """
    Returns a help/methodology text for the given topic, read from this
    service's help_texts/ directory. Call with no arguments (topic=
    "overview") first, before doing rectification or other astrological
    analysis work - it explains what tools are available and points to
    deeper topics (e.g. help("rectification")) covering hard-won
    methodology (technique priority order, an explicit rule against
    inventing subjective event weights, timezone/coordinate handling
    advice, etc.) that isn't obvious from tool signatures alone. If the
    given topic doesn't exist, returns a list of the topics that do.
    """
    return tools.help(topic)


if __name__ == "__main__":
    try:
        mcp.run(transport="streamable-http")
    except KeyboardInterrupt:
        logger.info("Shutdown requested via Ctrl+C, exiting cleanly")
