"""
Public REST report builder for MediaWiki's External Data extension (or any
other plain-HTTP JSON caller).

This is deliberately a SEPARATE module from tools.py: tools.py's functions
are shaped around the rectification workflow (one technique/one candidate
at a time, MCP-tool argument shapes). This module instead answers "give me
everything the ephemeris knows about this date/time/place" in one call,
in a FLAT shape External Data can path into directly
(planets.sun.abs_pos, houses.mc.sign, aspects[0].point_a, ...) without the
caller needing to know kerykeion's internal field names.

House system: ONE per request (config.DEFAULT_HOUSE_SYSTEM unless the
caller overrides it), not several at once - per discussion, mixing several
house systems' cusps into one flat "houses" dict would make ambiguous
which system a given cusp/aspect belongs to. If a wiki page genuinely
needs two systems side by side, call this endpoint twice with different
house_system values rather than asking one response to carry both.

build_full_report() is transport-agnostic (no Starlette/FastAPI/MCP
imports) - see app.py for the actual HTTP route that calls it.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from . import config
from .chart import build_subject
from .aspects import compute_aspects, angular_separation
from .constants import DEFAULT_POINTS, ANGLE_KEYS, HOUSE_KEYS, LUMINARY_NAMES
from .arabic_parts import is_day_birth
from .lots import compute_all_lots
from .fixed_stars import compute_fixed_stars, stars_conjunct_points
from . import geocode

logger = logging.getLogger("astromcp")

# angle_key -> short name used in the flat "houses" dict, so callers get
# "asc"/"mc" instead of having to know kerykeion's "ascendant"/
# "medium_coeli" field names.
ANGLE_SHORT_NAMES = {
    "ascendant": "asc",
    "medium_coeli": "mc",
    "descendant": "dsc",
    "imum_coeli": "ic",
}

# house_key -> short name: "first_house" -> "house_1", etc.
HOUSE_SHORT_NAMES = {h: f"house_{i+1}" for i, h in enumerate(HOUSE_KEYS)}


def _natal_self_aspects(
    natal_points: Dict[str, Dict[str, Any]],
    aspect_set: List[float],
    orb_table: Dict[float, float],
    luminary_bonus: float,
    identity_epsilon_deg: float = 0.05,
) -> List[Dict[str, Any]]:
    """
    Full aspect grid of natal_points against itself, de-duplicated (A-B
    kept, B-A dropped) and with "aspects" between two names that happen to
    sit at the identical degree (e.g. Ascendant and House 1 cusp under a
    quadrant house system - same point, two names) filtered out as
    non-information rather than reported as a spurious 0-orb conjunction.
    """
    raw = compute_aspects(natal_points, natal_points, aspect_set, orb_table,
                           luminary_bonus, LUMINARY_NAMES)
    seen = set()
    deduped = []
    for a in raw:
        name_a, name_b = a["point_a"], a["point_b"]
        if name_a == name_b:
            continue
        pos_a = natal_points[name_a]["abs_pos"]
        pos_b = natal_points[name_b]["abs_pos"]
        if angular_separation(pos_a, pos_b) < identity_epsilon_deg:
            continue  # same point under two names, not a real aspect
        key = frozenset((name_a, name_b, a["aspect_deg"]))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(a)
    return deduped


def _resolve_location(
    lat: Optional[float], lng: Optional[float], city: Optional[str],
    country_code: Optional[str],
) -> tuple:
    """
    Returns (lat, lng, location_source, resolved_city_name_or_None).
    Prefers explicit lat/lng; falls back to geonamescache city lookup
    otherwise. See geocode.py for the offline dataset and its caveats.
    """
    if lat is not None and lng is not None:
        return lat, lng, "explicit_coordinates", None
    if city:
        # country_code may be an ISO2 code, or an English/Russian country
        # name - geocode.lookup_city resolves it via resolve_country_code
        # internally, so pass it through as given.
        c_lat, c_lng, resolved_name = geocode.lookup_city(city, country_code)
        return c_lat, c_lng, "geonamescache", resolved_name
    raise ValueError("Provide either lat+lng, or a city name")


def build_full_report(
    year: int, month: int, day: int,
    hour: int, minute: int, second: int = 0,
    lat: Optional[float] = None, lng: Optional[float] = None,
    city: Optional[str] = None,
    country_code: Optional[str] = None,
    tz_str: Optional[str] = None,
    tz_offset_minutes: Optional[int] = None,
    house_system: Optional[str] = None,
    zodiac_type: Optional[str] = None,
    include_aspects: bool = True,
    include_house_cusp_aspects: bool = True,
    include_fixed_stars: bool = True,
    include_arabic_parts: bool = True,
    lots: Optional[List[str]] = None,
    aspect_set: Optional[List[float]] = None,
    orb_table: Optional[Dict[float, float]] = None,
    name: str = "subject",
) -> Dict[str, Any]:
    """
    Everything the ephemeris can produce for one date/time/place, in a
    flat shape meant for MediaWiki's External Data extension: all planets
    + nodes + Chiron + Lilith, houses (angles + all 12 cusps, one house
    system per call), the full natal aspect grid (optionally including
    house cusps as aspect targets, not just planets/angles), any
    requested Lots/Arabic Parts (see engine/lots.py - each gets house
    placement and aspects the same as a planet, not just a bare
    longitude), and fixed-star positions with any conjunctions to chart
    points.

    Location: either lat+lng, or a city name resolved via the offline
    geonamescache dataset (see geocode.py - NOT a live external geocoding
    call, but also not a guarantee for ambiguous/small place names; pass
    lat+lng directly whenever precision matters).

    Timezone: tz_str/tz_offset_minutes as usual. If NEITHER is given and
    coordinates are available (explicit or resolved from a city), this
    falls back to timezonefinder's MODERN zone-boundary lookup as a
    convenience default - this is explicitly flagged in the response's
    meta.tz_source as "auto_modern_only" so the caller can tell the
    difference. For historical dates, always pass tz_str/tz_offset_minutes
    explicitly instead of relying on this fallback (see geocode.py and
    help_texts/rectification.md's timezone notes - the same Soviet
    decree-time pitfall applies here).

    lots - which registered Lots (engine/lots.LOT_REGISTRY) to compute,
    when include_arabic_parts is True. Defaults to just "part_of_fortune"
    - the one universally unambiguous Lot - if not given. Unknown names
    raise ValueError (via engine/lots.compute_lot) naming what IS
    registered, rather than silently skipping a typo.
    """
    house_system = house_system or config.DEFAULT_HOUSE_SYSTEM
    zodiac_type = zodiac_type or config.DEFAULT_ZODIAC_TYPE
    aspect_set = aspect_set if aspect_set is not None else config.DEFAULT_ASPECT_SET
    orb_table = orb_table or config.DEFAULT_ORB_TABLE_TRANSIT
    lots = lots if lots is not None else ["part_of_fortune"]

    resolved_lat, resolved_lng, location_source, resolved_city_name = \
        _resolve_location(lat, lng, city, country_code)

    tz_note = "explicit"
    if tz_str is None and tz_offset_minutes is None:
        auto_tz = geocode.timezone_for_coordinates(resolved_lat, resolved_lng)
        if auto_tz is None:
            raise ValueError(
                "No tz_str/tz_offset_minutes given, and timezonefinder "
                "could not resolve a zone for these coordinates - pass "
                "a timezone explicitly."
            )
        tz_str = auto_tz
        tz_note = "auto_modern_only"  # see docstring - not safe for historical dates

    subject, tz_used, tz_source = build_subject(
        name, year, month, day, hour, minute, second,
        resolved_lat, resolved_lng, tz_str, tz_offset_minutes,
        house_system, zodiac_type,
    )
    raw = subject.model_dump(mode="json")

    planets = {p: raw[p] for p in DEFAULT_POINTS if raw.get(p) is not None}

    houses: Dict[str, Any] = {}
    for angle_key, short in ANGLE_SHORT_NAMES.items():
        if raw.get(angle_key) is not None:
            houses[short] = raw[angle_key]
    for house_key, short in HOUSE_SHORT_NAMES.items():
        if raw.get(house_key) is not None:
            houses[short] = raw[house_key]

    result: Dict[str, Any] = {
        "planets": planets,
        "houses": houses,
    }

    lot_points: Dict[str, Any] = {}
    if include_arabic_parts and lots:
        # One extra ephemeris computation, shared across every requested
        # Lot (not one per Lot) - see engine/lots.py for why a numeric
        # speed estimate needs a second, slightly time-shifted chart at
        # all.
        dt_hours = 1.0 / 6.0  # 10 minutes
        shifted = datetime(year, month, day, hour, minute, second) + timedelta(hours=dt_hours)
        future_subject, _, _ = build_subject(
            name, shifted.year, shifted.month, shifted.day,
            shifted.hour, shifted.minute, shifted.second,
            resolved_lat, resolved_lng, tz_str, tz_offset_minutes,
            house_system, zodiac_type,
        )
        raw_future = future_subject.model_dump(mode="json")
        lot_points = compute_all_lots(lots, raw, raw_future, dt_hours)
        result["lots"] = lot_points
        result["is_day_birth"] = is_day_birth(raw)

    if include_aspects:
        aspect_points = dict(planets)
        aspect_points.update(lot_points)
        for angle_key in ANGLE_KEYS:
            if raw.get(angle_key) is not None:
                aspect_points[ANGLE_SHORT_NAMES[angle_key]] = raw[angle_key]
        if include_house_cusp_aspects:
            for house_key in HOUSE_KEYS:
                if raw.get(house_key) is not None:
                    aspect_points[HOUSE_SHORT_NAMES[house_key]] = raw[house_key]
        luminary_bonus = config.LUMINARY_ORB_BONUS_TRANSIT
        result["aspects"] = _natal_self_aspects(
            aspect_points, aspect_set, orb_table, luminary_bonus,
        )

    if include_fixed_stars:
        jd = raw.get("julian_day") or getattr(subject, "julian_day", None)
        if jd is not None:
            stars = compute_fixed_stars(jd)
            result["fixed_stars"] = stars
            star_target_points = {**planets, **lot_points, **{
                ANGLE_SHORT_NAMES[k]: raw[k] for k in ANGLE_KEYS if raw.get(k) is not None
            }}
            result["fixed_star_conjunctions"] = stars_conjunct_points(
                stars, star_target_points, orb_deg=1.5,
            )
        else:
            result["fixed_stars"] = {"error": "julian_day not available on subject"}

    result["meta"] = {
        "location_source": location_source,
        "resolved_city_name": resolved_city_name,
        "lat": resolved_lat,
        "lng": resolved_lng,
        "tz_used": tz_used,
        "tz_source": tz_source,
        "tz_note": tz_note,
        "house_system": house_system,
        "zodiac_type": zodiac_type,
        "input_datetime": f"{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:{second:02d}",
        "schema_version": 2,  # bumped: "arabic_parts" -> "lots" (richer
                              # per-Lot shape: house+speed, not a bare
                              # float), new top-level "is_day_birth"
    }
    return result
