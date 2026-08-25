"""
Herich's number (Paul von Gerich, 1929 article, published in A.Frank
Glahn's "Erklarung und systematische Deutung des Geburtshoroskopes",
1930, pp.94-97, "Die Gerich'schen Harmoniegesetze" - see
BIBLIOGRAPHY.md). Formula and worked example recovered from a primary-
source excerpt (misyats.wordpress.com/2009/12/11/gerich/) after Kefer's
own text (extracted for this project) turned out to have an OCR gap
exactly where the formula should be - cross-checked against
astrokot.kiev.ua's glossary entry, which independently gives the same
formula and an 8-degree orb.

Rule: taking the midpoints of each pair among {Sun, Moon, Saturn}
(Gerich's own midpoint notation, e.g. "MO/SO" = midpoint of Moon and
Sun):
    a = midpoint(midpoint(Moon, Sun), midpoint(Saturn, Sun))
    b = midpoint(a, midpoint(Moon, Saturn))
b is then hypothesized to coincide with the Ascendant or Midheaven
(astrokot.kiev.ua: within an 8 degree orb; may also coincide with any
other house cusp). Gerich's own worked example (Kurt Eisner's chart:
MO/SO=302, SA/SO=321, MO/SA=211) gives b=261, matching an independently
computed Ascendant of 262 from another source (Brandler-Pracht) - this
project's implementation reproduces that same result (b=261.25) when fed
those inputs, which is the closest confirmation available without the
chart's full original data.

The source itself states an explicit uncertainty: "Gerich himself
acknowledges a possible discrepancy of up to 8 degrees" (per Kefer via
astrokot.kiev.ua) - use cautiously, as a weak auxiliary signal, same as
Bonatti's method.
"""

from typing import Dict, Any, List

from .aspects import angular_separation
from .constants import ANGLE_KEYS, HOUSE_KEYS


def _midpoint(x: float, y: float) -> float:
    diff = ((y - x + 180) % 360) - 180
    return (x + diff / 2) % 360


def compute_herich_number(natal_raw: Dict[str, Any]) -> float:
    sun = natal_raw["sun"]["abs_pos"]
    moon = natal_raw["moon"]["abs_pos"]
    saturn = natal_raw["saturn"]["abs_pos"]

    mo_so = _midpoint(moon, sun)
    sa_so = _midpoint(saturn, sun)
    mo_sa = _midpoint(moon, saturn)

    a = _midpoint(mo_so, sa_so)
    b = _midpoint(a, mo_sa)
    return b


def check_herich(
    natal_raw: Dict[str, Any],
    orb_deg: float = 8.0,
    check_all_house_cusps: bool = False,
) -> Dict[str, Any]:
    """
    Checks whether Herich's number (b) falls within orb_deg of the
    Ascendant or Midheaven (the source's primary claim), and optionally
    of any other house cusp (the source's secondary, weaker claim - "may
    also coincide with the cusp of any other house").
    """
    b = compute_herich_number(natal_raw)

    check_points = list(ANGLE_KEYS)
    if check_all_house_cusps:
        check_points += HOUSE_KEYS

    matches = []
    for key in check_points:
        if key not in natal_raw:
            continue
        sep = angular_separation(b, natal_raw[key]["abs_pos"])
        if sep <= orb_deg:
            matches.append({"point": key, "orb": round(sep, 4)})

    return {
        "herich_number_deg": round(b, 4),
        "matches": matches,
        "rule_holds": len(matches) > 0,
    }
