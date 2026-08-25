"""
Fixed star positions - NEW capability, not used anywhere else in this
project. kerykeion (and therefore this whole service) is built on top of
pyswisseph, but nothing so far has called its fixed-star functions
directly - the rectification tools never needed them. This module does,
for the public /astro report (see public_api.py).

Uses swe.fixstar2_ut, the modern (post-2020-catalog) Swiss Ephemeris fixed
star call. Requires the same ephemeris files kerykeion already relies on to
be on swisseph's search path - kerykeion sets this at import time, so as
long as this module is imported AFTER kerykeion (which chart.py already
guarantees at package-import order), swe.set_ephe_path should already be
configured. If fixstar lookups fail with a file-not-found style error in
practice, call swe.set_ephe_path(...) explicitly here first - check what
path kerykeion itself uses (see its own settings/config) and reuse it.

NOT independently verified against a running install in this session -
this is a first-pass implementation to test against your actual server
and ephemeris files, not a drop-in guaranteed-working module. Sanity-check
a few star positions against a known reference (e.g. Astrodienst's chart
for a known date) before trusting it in production.
"""

from typing import Dict, Any, List
import swisseph as swe

from .constants import SIGN_ORDER

# A traditionally significant subset - the four Persian "Royal Stars" plus
# a handful of other stars with well-documented interpretive traditions.
# Extend this list as needed; it is NOT exhaustive (Swiss Ephemeris ships
# positions for several hundred named stars).
DEFAULT_STAR_LIST: List[str] = [
    "Aldebaran",   # Royal star - Watcher of the East
    "Regulus",     # Royal star - Watcher of the North
    "Antares",     # Royal star - Watcher of the West
    "Fomalhaut",   # Royal star - Watcher of the South
    "Spica",
    "Algol",
    "Sirius",
    "Vega",
    "Pollux",
    "Castor",
    "Betelgeuse",
    "Rigel",
]


def _sign_and_position(abs_pos: float) -> Dict[str, Any]:
    abs_pos = abs_pos % 360
    idx = int(abs_pos // 30)
    return {
        "abs_pos": abs_pos,
        "sign": SIGN_ORDER[idx],
        "sign_num": idx,
        "position": abs_pos - idx * 30,
    }


def compute_fixed_stars(
    julian_day_ut: float,
    star_list: List[str] = None,
) -> Dict[str, Dict[str, Any]]:
    """
    Returns {star_name: {abs_pos, sign, sign_num, position, declination,
    distance_au, magnitude}} for every star in star_list (default
    DEFAULT_STAR_LIST), at the given Julian Day (UT).

    julian_day_ut - use the same JD the rest of this service already
    computes for the subject (kerykeion exposes it on the AstrologicalSubject
    as `julian_day` - reuse that value rather than recomputing, to avoid any
    UT/TT or rounding mismatch against the planetary positions in the same
    report).
    """
    stars = star_list if star_list is not None else DEFAULT_STAR_LIST
    flags = swe.FLG_SWIEPH | swe.FLG_SPEED
    out: Dict[str, Dict[str, Any]] = {}
    for star_name in stars:
        try:
            # fixstar2_ut returns ((lon, lat, dist, lon_speed, lat_speed,
            # dist_speed), resolved_star_name)
            (lon, lat, dist, *_), resolved_name = swe.fixstar2_ut(star_name, julian_day_ut, flags)
            mag = swe.fixstar2_mag(star_name)[0]
            entry = _sign_and_position(lon)
            entry["ecliptic_latitude"] = lat
            entry["distance_au"] = dist
            entry["magnitude"] = mag
            entry["resolved_name"] = resolved_name.strip()
            out[star_name] = entry
        except Exception as e:
            out[star_name] = {"error": str(e)}
    return out


def stars_conjunct_points(
    stars: Dict[str, Dict[str, Any]],
    natal_points: Dict[str, Dict[str, Any]],
    orb_deg: float = 1.5,
) -> List[Dict[str, Any]]:
    """
    Cross-references computed star longitudes against the chart's own
    points/angles/house-cusps and reports conjunctions within orb_deg - the
    one aspect fixed stars are traditionally read by (no other Ptolemaic
    aspects, by the usual convention). Returns a flat list, not nested per
    star, so it merges naturally into the same "aspects"-shaped output the
    rest of the report already uses.
    """
    hits = []
    for star_name, star_data in stars.items():
        star_pos = star_data.get("abs_pos")
        if star_pos is None:
            continue
        for point_name, point_data in natal_points.items():
            point_pos = point_data.get("abs_pos")
            if point_pos is None:
                continue
            diff = abs(star_pos - point_pos) % 360
            sep = diff if diff <= 180 else 360 - diff
            if sep <= orb_deg:
                hits.append({
                    "star": star_name,
                    "point": point_name,
                    "orb": round(sep, 4),
                })
    return hits
