"""
City-name -> coordinates -> timezone resolution for the public REST
endpoint (see public_api.py), with Russian-language input support.

Three offline, no-network-call data sources, each doing the job it's
actually good at rather than one library stretched to cover everything:

- geonamescache: bundled ~25k-city dataset (name, lat/lng, country,
  population, and an `alternatenames` list per city sourced from GeoNames'
  own alternate-name data - which, per GeoNames' own 2006 changelog,
  already includes Cyrillic variants for ~60k populated places, Russian
  ones among them). This project indexes BOTH `name` and every entry in
  `alternatenames`, so a fair number of Russian spellings resolve for
  free with no extra data to maintain (e.g. "Одесса" -> Odesa, if GeoNames
  shipped that variant for this particular city - not guaranteed for
  every city, see caveats below).
- A small hand-curated RU_CITY_EXONYMS table for the cases geonamescache's
  alternate names can't be expected to cover: Russian exonyms that are a
  genuinely different word, not a spelling variant of the English name
  (Москва -> Moscow, Вена -> Vienna) - no transliteration or fuzzy match
  will ever bridge that gap, it has to be a lookup table. Each entry maps
  to a LIST of English spellings tried in order (handles cases like
  GeoNames' 2021 Odessa -> Odesa rename, where we can't be sure which
  spelling a given install's bundled dataset actually uses). Extend as
  your wiki's actual usage shows what's needed, same policy as the
  original curated table this replaced.
- Babel's CLDR data (Locale('ru').territories) for COUNTRY names - this
  one doesn't need curating at all, CLDR already ships an exact Russian
  name for every ISO 3166-1 territory, professionally maintained by the
  Unicode Consortium. Use this instead of hand-writing a Russian country
  table.

Cyrillic input that matches neither the geonamescache index nor
RU_CITY_EXONYMS falls back to a simple letter-by-letter transliteration
(GOST-ish, not linguistically perfect) and retries the same lookup - this
catches cases where the transliterated spelling happens to match an
existing English/alternate name (e.g. "Краков" -> "Krakov", close enough
to "Krakow"/"Kraków" depending on what GeoNames actually stored) but will
NOT catch genuine exonyms (transliterating "Москва" gives "Moskva", which
is not "Moscow" - that's exactly what RU_CITY_EXONYMS is for).

IMPORTANT CAVEATS, both already flagged in this project and worth
repeating here specifically because this module makes them easy to
forget:

1. geonamescache's population-based city disambiguation is a heuristic,
   not a guarantee - "Springfield" or "San Jose" resolve to whichever
   entry has the largest population unless the caller disambiguates with
   a country code. For anything where the exact town matters, pass
   lat/lng directly instead of a city name (same advice
   help_texts/rectification.md already gives for the "small village not
   in the database" problem - a bundled dataset doesn't solve that, it
   just raises the bar of what counts as "not in the database").
2. timezonefinder (see timezone_for_coordinates below) resolves the
   CURRENT/modern IANA zone boundary for a coordinate. It says nothing
   about what offset was actually in effect on a historical date at that
   location (Soviet decree time, wartime shifts, colonial-era zones, etc.
   - see this project's own documented real case: a Western-Siberian
   village that was UTC+7 in 1934 despite legacy software assuming UTC+8
   for that zone today). Treat the auto-resolved tz as a MODERN-DATE
   convenience default only. For historical dates, pass tz_str or
   tz_offset_minutes explicitly after verifying the actual historical
   offset independently - do not trust this module for that.
3. This module's Russian-language support has NOT been independently
   verified against the actual bundled geonamescache dataset in this
   session (no network access to install and inspect it) - the claim
   that GeoNames ships ~60k Cyrillic city variants is sourced from
   GeoNames' own public changelog, not from inspecting this specific
   package's cities.json. Test a handful of real Russian city names
   against your running server before trusting this in production, and
   grow RU_CITY_EXONYMS from what actually fails.
"""

from typing import Optional, Tuple, List
import logging
import re

import geonamescache
from timezonefinder import TimezoneFinder
from babel import Locale

logger = logging.getLogger("astromcp")

_gc = geonamescache.GeonamesCache()
_tf = TimezoneFinder()

# --- city index: name + every alternate name -> list of city dicts ---
_CITY_INDEX = {}
for _geonameid, _city in _gc.get_cities().items():
    _names = {_city["name"]}
    _names.update(_city.get("alternatenames") or [])
    for _n in _names:
        _key = _n.strip().lower()
        if _key:
            _CITY_INDEX.setdefault(_key, []).append(_city)

# --- country index: English name (from geonamescache) -> ISO2 ---
_EN_COUNTRY_INDEX = {
    _country["name"].strip().lower(): _iso2
    for _iso2, _country in _gc.get_countries().items()
}

# --- country index: Russian name (from Babel/CLDR) -> ISO2 ---
# CLDR names things like "Россия" / "Украина" / "Соединённые Штаты Америки" -
# authoritative and requires no hand-maintenance, unlike cities.
_RU_COUNTRY_INDEX = {
    _name.strip().lower(): _code
    for _code, _name in Locale("ru").territories.items()
    if len(_code) == 2  # skip aggregate region codes like '001' (World)
}

# Genuine Russian exonyms for cities - words that don't transliterate or
# fuzzy-match to their English name (unlike "Одесса"/"Odessa", which are
# close enough that geonamescache's own alternatenames likely already
# bridges them). Keys lowercase. Extend as needed; seeded with the
# post-Soviet cities and major world capitals most likely to come up in
# rectification work off a Russian-language wiki.
# Genuine Russian exonyms for cities - words that don't transliterate or
# fuzzy-match to their English name (unlike "Одесса"/"Odessa", which are
# close enough that geonamescache's own alternatenames likely already
# bridges them). Keys lowercase, values are the English name(s) to try
# against the geonamescache index, in order - a list handles cases where
# the "official" English spelling has changed over time (e.g. GeoNames'
# 2021 Odessa -> Odesa rename) and we can't be sure which one this
# install's bundled dataset actually uses. Extend as needed; seeded with
# the post-Soviet cities and major world capitals most likely to come up
# in rectification work off a Russian-language wiki.
RU_CITY_EXONYMS = {
    "москва": ["Moscow"],
    "санкт-петербург": ["Saint Petersburg"],
    "петербург": ["Saint Petersburg"],
    "ленинград": ["Saint Petersburg"],
    "киев": ["Kyiv", "Kiev"],
    "одесса": ["Odesa", "Odessa"],
    "минск": ["Minsk"],
    "вена": ["Vienna"],
    "прага": ["Prague"],
    "варшава": ["Warsaw"],
    "белград": ["Belgrade"],
    "бухарест": ["Bucharest"],
    "рим": ["Rome"],
    "флоренция": ["Florence"],
    "неаполь": ["Naples"],
    "венеция": ["Venice"],
    "мюнхен": ["Munich"],
    "кельн": ["Cologne"],
    "женева": ["Geneva"],
    "цюрих": ["Zurich"],
    "гаага": ["The Hague"],
    "лондон": ["London"],
    "эдинбург": ["Edinburgh"],
    "париж": ["Paris"],
    "марсель": ["Marseille"],
    "афины": ["Athens"],
    "тбилиси": ["Tbilisi"],
    "ереван": ["Yerevan"],
    "баку": ["Baku"],
    "кишинёв": ["Chisinau"],
    "кишинев": ["Chisinau"],
    "рига": ["Riga"],
    "вильнюс": ["Vilnius"],
    "таллин": ["Tallinn"],
    "хельсинки": ["Helsinki"],
    "стокгольм": ["Stockholm"],
    "копенгаген": ["Copenhagen"],
    "пекин": ["Beijing"],
    "токио": ["Tokyo"],
    "нью-йорк": ["New York"],
    "лос-анджелес": ["Los Angeles"],
    "иерусалим": ["Jerusalem"],
    "каир": ["Cairo"],
    "дели": ["Delhi"],
    "стамбул": ["Istanbul"],
}

_CYRILLIC_RE = re.compile("[\u0400-\u04FF]")

# Simplified letter-by-letter Cyrillic -> Latin table (not a linguistic
# transliteration standard, just enough to retry a lookup against
# geonamescache's Latin-alphabet index).
_TRANSLIT_MAP = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "i", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


class GeocodeError(Exception):
    pass


def _is_cyrillic(text: str) -> bool:
    return bool(_CYRILLIC_RE.search(text))


def _transliterate_ru(text: str) -> str:
    return "".join(_TRANSLIT_MAP.get(ch, ch) for ch in text.lower())


def resolve_country_code(value: Optional[str]) -> Optional[str]:
    """
    Accepts an ISO 3166-1 alpha-2 code, an English country name, or a
    Russian country name (via Babel/CLDR - see this module's docstring),
    and returns the ISO2 code. Returns None for a falsy input. Raises
    GeocodeError for anything it can't resolve.
    """
    if not value:
        return None
    v = value.strip()
    if len(v) == 2 and v.isalpha():
        return v.upper()
    key = v.lower()
    if key in _EN_COUNTRY_INDEX:
        return _EN_COUNTRY_INDEX[key]
    if key in _RU_COUNTRY_INDEX:
        return _RU_COUNTRY_INDEX[key]
    raise GeocodeError(
        f"Country '{value}' was not recognized as an ISO 3166-1 alpha-2 "
        "code, an English country name, or a Russian country name."
    )


def _find_city_candidates(name: str) -> Optional[List[dict]]:
    key = name.strip().lower()

    if key in RU_CITY_EXONYMS:
        for english_name in RU_CITY_EXONYMS[key]:
            candidates = _CITY_INDEX.get(english_name.lower())
            if candidates:
                return candidates
        # exonym known, but none of its listed English spellings are in
        # this install's dataset - fall through to the generic paths
        # below rather than giving up immediately.

    candidates = _CITY_INDEX.get(key)
    if candidates:
        return candidates

    if _is_cyrillic(name):
        translit_key = _transliterate_ru(name)
        candidates = _CITY_INDEX.get(translit_key)
        if candidates:
            return candidates

    return None


def lookup_city(name: str, country_code: Optional[str] = None) -> Tuple[float, float, str]:
    """
    Returns (lat, lng, resolved_display_name) for a city name - English,
    Russian exonym, or a Cyrillic spelling geonamescache already carries
    as an alternate name. Raises GeocodeError (safe to surface to the
    HTTP caller) if nothing matches.

    country_code - ISO2, or an English/Russian country name (resolved via
    resolve_country_code) - disambiguates a common city name. Without it,
    ties are broken by picking the highest-population match, which is a
    heuristic, not a guarantee - see this module's docstring.
    """
    candidates = _find_city_candidates(name)
    if not candidates:
        raise GeocodeError(
            f"City '{name}' was not found (checked the offline "
            "geonamescache dataset - including its alternate/Cyrillic "
            "names - the curated RU_CITY_EXONYMS table, and a "
            "transliteration fallback). Pass lat/lon directly instead, "
            "or add this city to engine/geocode.py:RU_CITY_EXONYMS if "
            "it's a genuine Russian exonym."
        )
    if country_code:
        resolved_cc = resolve_country_code(country_code)
        filtered = [c for c in candidates if c.get("countrycode", "").upper() == resolved_cc]
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
