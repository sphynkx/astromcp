"""
"Elements of house" - the classical rectification primitive used by the
Shestopalov/St.Petersburg Academy of Astrology school (documented by
A. Grishchenyuk and A. Budarovsky) and formally grounded by S. Aizin's
house-derivation logic.

For a given house, its "elements" are:
  (a) the ruler of the sign on the house cusp,
  (b) the co-ruler - the ruler of the NEXT sign, if the house cusp is less
      than ~17 degrees from the end of its sign (i.e. the house extends
      more than ~13 degrees into the next sign, so a meaningful portion of
      the house falls under that sign's rulership too),
  (c) any natal planet actually located inside the house.

This module returns element sets as plain lists of point names (e.g.
["venus", "mercury"]) - the same names already used as `DEFAULT_POINTS`
elsewhere in this engine - so they can be dropped directly into any
technique's `target_points` field without further plumbing.

Modern rulerships are used here (not the traditional set used by
profections) - see constants.MODERN_RULERS and the note there.
"""

from typing import Dict, Any, List, Iterable

from .constants import DEFAULT_POINTS, MODERN_RULERS, HOUSE_KEYS

# House cusp keys in order, First_House=index 0 ... Twelfth_House=index 11,
# matching kerykeion's "house" field values on points (e.g. "First_House").
HOUSE_NAME_BY_NUM = {
    1: "First_House", 2: "Second_House", 3: "Third_House", 4: "Fourth_House",
    5: "Fifth_House", 6: "Sixth_House", 7: "Seventh_House", 8: "Eighth_House",
    9: "Ninth_House", 10: "Tenth_House", 11: "Eleventh_House", 12: "Twelfth_House",
}

# Below this many degrees remaining in the cusp's own sign, the house is
# considered to extend meaningfully into the next sign, activating a
# co-ruler. 30 - 13 = 17: if the cusp sign-position is already past 13
# degrees, less than 17 degrees of that sign remain in the house.
CO_RULER_THRESHOLD_SIGN_POSITION = 13.0


def get_house_ruler_and_coruler(natal_raw: Dict[str, Any], house_num: int) -> List[str]:
    """Returns [ruler] or [ruler, co_ruler] for the given house number (1-12)."""
    house_key = HOUSE_KEYS[house_num - 1]
    cusp = natal_raw[house_key]
    sign_num = cusp["sign_num"]
    sign_position = cusp["position"]  # degrees into the sign, 0-30

    ruler = MODERN_RULERS[sign_num]
    result = [ruler]

    if sign_position > CO_RULER_THRESHOLD_SIGN_POSITION:
        next_sign_num = (sign_num + 1) % 12
        co_ruler = MODERN_RULERS[next_sign_num]
        if co_ruler != ruler:
            result.append(co_ruler)

    return result


def get_planets_in_house(natal_raw: Dict[str, Any], house_num: int,
                          points: Iterable[str] = DEFAULT_POINTS) -> List[str]:
    """Returns the names of all natal points physically located in the given house."""
    house_name = HOUSE_NAME_BY_NUM[house_num]
    return [p for p in points if natal_raw.get(p, {}).get("house") == house_name]


def get_house_element_names(
    natal_raw: Dict[str, Any],
    house_numbers: Iterable[int],
    points: Iterable[str] = DEFAULT_POINTS,
) -> List[str]:
    """
    Returns the deduplicated union of "elements" (ruler, co-ruler if
    applicable, occupying planets) across all given house numbers. This is
    the list to pass as `target_points` for an event whose significance is
    tied to those houses - see help_texts/rectification.md for guidance on
    choosing which houses apply to a given life event (this module does
    not classify events itself - that's a reasoning task, not a lookup
    table, per Aizin's chain-of-consequence method).
    """
    elements: List[str] = []
    for house_num in house_numbers:
        for name in get_house_ruler_and_coruler(natal_raw, house_num):
            if name not in elements:
                elements.append(name)
        for name in get_planets_in_house(natal_raw, house_num, points):
            if name not in elements:
                elements.append(name)
    return elements


def house_number_for_longitude(natal_raw: Dict[str, Any], abs_pos: float) -> int:
    """
    Which house (1-12) a given ecliptic longitude falls in, from this
    chart's own 12 cusps. For points kerykeion doesn't already know about
    itself (kerykeion only sets a `.house` field on its own computed
    objects) - a computed Lot/Arabic Part is exactly this case, see
    engine/lots.py.

    Handles house-size wraparound generically (a house's angular span is
    just the gap to the next cusp, going forward around the circle - works
    the same way regardless of house system, and regardless of whether
    that particular house happens to be wider than 180 degrees under some
    system/latitude combination).
    """
    cusps = [natal_raw[HOUSE_KEYS[i]]["abs_pos"] for i in range(12)]
    abs_pos = abs_pos % 360
    for i in range(12):
        start = cusps[i]
        end = cusps[(i + 1) % 12]
        span = (end - start) % 360
        if span == 0:
            span = 360
        offset = (abs_pos - start) % 360
        if offset < span:
            return i + 1
    return 12  # defensive fallback - shouldn't be reachable given the loop above covers the full circle
