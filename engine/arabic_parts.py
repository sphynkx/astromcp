"""
Arabic Parts / Lots. Two things live here:

1. compute_part_of_fortune: the one universally standard, unambiguous Lot
   (Fortune) - Asc + Moon - Sun (day birth), or Asc + Sun - Moon (night
   birth).

2. compute_arabic_part: D. Kutalev's GENERAL formula (via I. Zhuravleva -
   see BIBLIOGRAPHY.md), usable to construct a Lot for any house/theme,
   not just Fortune: cusp + ruler - significator (day birth), or
   Ascendant + significator - ruler (night birth). This module does NOT
   hardcode which planet is the "significator" for a given theme (e.g.
   Venus for marriage, Sun for father) - that choice is exactly the kind
   of judgment call this project's methodology insists be reasoned
   through per case (see help_texts/rectification.md's guidance on house
   classification), not looked up from a table presented as authoritative
   when the sources themselves don't agree on one universal table.
"""

from typing import Dict, Any


def is_day_birth(natal_raw: Dict[str, Any]) -> bool:
    """Sun above the horizon (houses 7-12) = day birth, per classical convention."""
    house_name = natal_raw["sun"]["house"]
    day_houses = {
        "Seventh_House", "Eighth_House", "Ninth_House",
        "Tenth_House", "Eleventh_House", "Twelfth_House",
    }
    return house_name in day_houses


def compute_part_of_fortune(natal_raw: Dict[str, Any]) -> float:
    asc = natal_raw["ascendant"]["abs_pos"]
    sun = natal_raw["sun"]["abs_pos"]
    moon = natal_raw["moon"]["abs_pos"]
    if is_day_birth(natal_raw):
        return (asc + moon - sun) % 360
    return (asc + sun - moon) % 360


def compute_arabic_part(
    natal_raw: Dict[str, Any],
    cusp_abs_pos: float,
    ruler_abs_pos: float,
    significator_abs_pos: float,
) -> float:
    """
    D. Kutalev's general Lot formula. Day birth: cusp + ruler -
    significator. Night birth: Ascendant + significator - ruler. Caller
    supplies cusp/ruler/significator as explicit absolute positions
    (degrees) - e.g. cusp_abs_pos=natal_raw["seventh_house"]["abs_pos"],
    ruler_abs_pos=<abs_pos of that cusp's sign ruler>,
    significator_abs_pos=<abs_pos of the planet reasoned to signify the
    theme>, following the same per-case reasoning as house classification
    elsewhere in this project - not a hardcoded significator table.
    """
    asc = natal_raw["ascendant"]["abs_pos"]
    if is_day_birth(natal_raw):
        return (cusp_abs_pos + ruler_abs_pos - significator_abs_pos) % 360
    return (asc + significator_abs_pos - ruler_abs_pos) % 360
