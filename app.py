"""
astromcp - MCP service entry point.

This module only registers MCP tools and wires them to the implementations
in engine/tools.py. It intentionally contains no astrological or scoring
logic itself - that all lives under engine/, so it can be read, tested, and
modified independently of the MCP transport plumbing.
"""

import logging
from typing import Optional, List, Dict, Any

from dotenv import load_dotenv
load_dotenv()

import warnings
warnings.filterwarnings("ignore", message=".*Field 'lifespan' has an incomplete definition.*")

from mcp.server.fastmcp import FastMCP

from engine import config
from engine import tools

logging.basicConfig(level=getattr(logging, config.LOG_LEVEL, logging.INFO))
logger = logging.getLogger("astromcp")

mcp = FastMCP("astromcp", host=config.HOST, port=config.PORT)


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
    technique: str = "transit",  # secondary_progression | solar_arc | solar_return | profection | transit
    target_year: int = 2000, target_month: int = 1, target_day: int = 1,
    target_hour: int = 12, target_minute: int = 0, target_second: int = 0,
    angle_method: str = "solar_arc_naibod",  # for secondary_progression
    event_lat: Optional[float] = None, event_lng: Optional[float] = None,
    event_tz_str: Optional[str] = None, event_tz_offset_minutes: Optional[int] = None,
    compute_aspects_flag: bool = True,
    aspect_set: Optional[List[float]] = None,
    orb_table: Optional[Dict[str, float]] = None,
    luminary_orb_bonus: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Computes a predictive technique (secondary progression, solar arc
    direction, solar return, annual/monthly profection, or transit) for a
    natal chart, and optionally the aspects it forms to the natal chart.
    This is the core engine for rectification: run it once per candidate
    event, per candidate birth time.

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

    Default orbs are technique-aware: transits, solar returns, and
    profections use wide classical orbs, while progressions/directions use
    tight ~1 degree orbs (since 1 degree of arc corresponds to roughly 1
    year of life, a wide orb there directly translates into years of
    dating error). Pass orb_table/luminary_orb_bonus explicitly to
    override; defaults are also tunable via .env.
    """
    return tools.rectif_technique(
        natal_year, natal_month, natal_day, natal_hour, natal_minute, natal_second,
        natal_lat, natal_lng, natal_tz_str, natal_tz_offset_minutes,
        house_system, zodiac_type, technique,
        target_year, target_month, target_day, target_hour, target_minute, target_second,
        angle_method, event_lat, event_lng, event_tz_str, event_tz_offset_minutes,
        compute_aspects_flag, aspect_set, orb_table, luminary_orb_bonus,
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
    weight?, aspect_set?, orb_table?, target_points?, orb_threshold?}. For
    technique="solar_return", only target_year is used. For
    technique="profection", target_points is ignored (the technique fixes
    its own natal-side targets: lord of the year/month, profected Asc).
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
) -> Dict[str, Any]:
    """
    Trutine of Hermes (Trutina Hermetis): classical fast rectification via
    the reciprocal Moon/Ascendant relationship between the birth chart and
    the theoretical conception (epoch) chart - see William Lilly, Christian
    Astrology pp.502-505. Unlike rectif_scan, this does NOT need any life
    events at all and does NOT brute-force many candidates - it solves
    directly (a handful of chart builds via fixed-point iteration from
    initial_guess_*), so it's fast and can be used as a first, resource-
    light starting point even when nothing whatsoever is known about the
    birth time.

    Returns TWO branches (branch_moon_below_horizon_at_birth and
    branch_moon_above_horizon_at_birth), because whether the Moon was above
    or below the horizon at birth is itself part of what's being solved
    for and can't be assumed. Compare both against any other evidence you
    have (rough time-of-day testimony, or agreement with rectif_scan /
    rectif_technique results from actual life events) to pick between them.

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
    )


@mcp.tool()
def ping(message: str = "world") -> str:
    """Simple connectivity test."""
    return tools.ping(message)


if __name__ == "__main__":
    try:
        mcp.run(transport="streamable-http")
    except KeyboardInterrupt:
        logger.info("Shutdown requested via Ctrl+C, exiting cleanly")
