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
    transits, progressions and directions are computed on top of this tool's
    output.

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
    technique: str = "transit",  # secondary_progression | solar_arc | transit
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
    Computes a predictive technique (secondary progression, solar arc direction,
    or transit) for a natal chart on a given target date, and optionally the
    aspects it forms to the natal chart. This is the core engine for
    rectification: run it once per candidate event, per candidate birth time.

    Default orbs are technique-aware: transits use wide classical orbs,
    while progressions/directions use tight ~1 degree orbs (since 1 degree
    of arc corresponds to roughly 1 year of life, a wide orb here directly
    translates into years of dating error). Pass orb_table/luminary_orb_bonus
    explicitly to override; defaults are also tunable via .env.
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
) -> Dict[str, Any]:
    """
    Sweeps candidate birth times across [scan_start, scan_end] on the given
    birth date, in step_minutes increments. For each candidate, builds the
    natal chart once, then evaluates every event in `events` (each with its
    own technique/target date, scored by aspect hits to target_points),
    sums the scores, and returns the top_n candidates ranked by total score.

    Each event dict: {name, technique: "transit"|"secondary_progression"|"solar_arc",
    target_year, target_month, target_day, target_hour?, target_minute?, target_second?,
    event_lat?, event_lng?, event_tz_str?, event_tz_offset_minutes?,
    angle_method?, weight?, aspect_set?, orb_table?, target_points?, orb_threshold?}

    WARNING: cost scales as candidates x events. A 2-hour range at 1-minute
    steps with 20 events is ~2400 chart builds - expect tens of seconds.
    """
    return tools.rectif_scan(
        natal_year, natal_month, natal_day, natal_lat, natal_lng,
        natal_tz_str, natal_tz_offset_minutes, house_system, zodiac_type,
        scan_start_hour, scan_start_minute, scan_end_hour, scan_end_minute,
        step_minutes, events, target_points, aspect_set, orb_threshold,
        top_n, include_full_table,
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
