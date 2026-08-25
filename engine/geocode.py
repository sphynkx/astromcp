"""
City-name -> coordinates -> timezone resolution for the public REST
endpoint (see public_api.py).

Uses two offline, no-network-call libraries (per the user's own prior
experience with this exact problem in another project):

- geonamescache: a bundled static dataset of ~25k cities (name, lat/lng,
  country, population). No API calls, no rate limits, no external service
  dependency at request time - just a package data file.
- timezonefinder: bundled timezone-boundary shapefiles, resolves lat/lng ->
  IANA zone name (e.g. "Europe/Kyiv") entirely offline.

This keeps the project's original principle intact in spirit (see
help_texts/rectification.md's "Coordinates" section: no live-geocoding
external calls, no network dependency at request time) while adding real
worldwide coverage instead of a small hand-maintained table - "never
geocode" was about not depending on an external service with its own
uptime/rate-limits/terms, not a ban on any coordinate lookup at all.

IMPORTANT CAVEATS - both already flagged elsewhere in this project and
worth repeating here specifically because this module makes them easy to
forget:

1. geonamescache's population-based city disambiguation is a heuristic,
   not a guarantee - "Springfield" or "San Jose" will resolve to whichever
   entry has the largest population unless the caller disambiguates with a
   country code. For anything where the exact town matters, pass lat/lng
   directly instead of a city name (same advice help_texts/
   rectification.md already gives for the "small village not in the
   database" problem - a bundled dataset doesn't solve that, it just
   raises the bar of what counts as "not in the database").
2. timezonefinder resolves the CURRENT/modern IANA zone boundary for a
   coordinate. It says nothing about what offset was actually in effect on
   a historical date at that location (Soviet decree time, wartime
   shifts, colonial-era zones, etc. - see this project's own documented
   real case: a Western-Siberian village that was UTC+7 in 1934 despite
   legacy software assuming UTC+8 for that zone today). Treat the
   auto-resolved tz as a MODERN-DATE convenience default only. For
   historical dates, pass tz_str or tz_offset_minutes explicitly after
   verifying the actual historical offset independently - do not trust
   this module for that.
"""

from typing import Optional, Tuple
import logging

import geonamescache
from timezonefinder import TimezoneFinder

logger = logging.getLogger("astromcp")

_gc = geonamescache.GeonamesCache()
_tf = TimezoneFinder()

# Build a lowercase-name -> list-of-city-dicts index once at import time.
# geonamescache keys its city dict by geonameid, so we index by name
# ourselves. Several cities can share a name - resolve by taking the
# highest population unless the caller supplies a country code.
_CITY_INDEX = {}
for _geonameid, _city in _gc.get_cities().items():
    _key = _city["name"].strip().lower()
    _CITY_INDEX.setdefault(_key, []).append(_city)


class GeocodeError(Exception):
    pass


def lookup_city(name: str, country_code: Optional[str] = None) -> Tuple[float, float, str]:
    """
    Returns (lat, lng, resolved_display_name) for a city name via
    geonamescache. Raises GeocodeError (safe to surface to the HTTP
    caller) if nothing matches.

    country_code - optional ISO 3166-1 alpha-2 (e.g. "UA", "RU") to
    disambiguate a common city name. Without it, ties are broken by
    picking the highest-population match, which is a heuristic, not a
    guarantee - see this module's docstring.
    """
    key = name.strip().lower()
    candidates = _CITY_INDEX.get(key)
    if not candidates:
        raise GeocodeError(
            f"City '{name}' was not found in the offline geonamescache "
            "dataset. Pass lat/lon directly instead, or check spelling "
            "(geonamescache matches on its own canonical city names, "
            "which may differ from local/transliterated spellings)."
        )
    if country_code:
        filtered = [c for c in candidates if c.get("countrycode", "").upper() == country_code.upper()]
        if filtered:
            candidates = filtered
    best = max(candidates, key=lambda c: c.get("population", 0))
    return float(best["latitude"]), float(best["longitude"]), best["name"]


def timezone_for_coordinates(lat: float, lng: float) -> Optional[str]:
    """
    Returns the MODERN IANA timezone name for a coordinate, or None if
    timezonefinder can't resolve one (open ocean, etc). See this module's
    docstring - NOT safe to trust for historical dates without independent
    verification.
    """
    tz = _tf.timezone_at(lat=lat, lng=lng)
    if tz is None:
        logger.warning(f"timezonefinder found no zone for ({lat}, {lng})")
    return tz
