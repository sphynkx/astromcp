"""
Formal "houses from houses" (derived house) algebra, per S. Aizin's
rectification methodology - see BIBLIOGRAPHY.md. A relative's house is
found by counting from the house of the person through whom the relation
is traced, not by a flat lookup table: a paternal grandfather is "the
father's father" = the 4th house counted from the (natal) 4th house.

This module makes that counting mechanical and explicit, rather than
eyeballing it per event (which is what earlier sessions did, and which
directly caused a wrong house assignment for a grandparent - see
TECHNIQUE_STATUS.md history).

Convention used here (stated explicitly because sources differ): 4th
house = father, 10th house = mother. This is the classical/Ptolemaic
association (4th/IC = root, family line, typically read as the father in
most traditional and the surveyed Russian-school sources); some modern
authors reverse it. If a person you're working with uses the reversed
convention, swap BASE_RELATION_HOUSES["father"] and ["mother"] for that
chart rather than silently assuming.
"""

from typing import List

# Base (1st-house-relative) house for common relations, counted directly
# from the native's own chart.
BASE_RELATION_HOUSES = {
    "self": 1,
    "sibling": 3,
    "father": 4,
    "mother": 10,
    "spouse": 7,
    "child": 5,
    "friend": 11,
    "enemy_open": 7,
    "enemy_hidden": 12,
}


def house_from_house(base_house: int, offset_house: int) -> int:
    """
    "The Nth house from the Mth house": counts offset_house houses forward
    from base_house, wrapping at 12. E.g. house_from_house(4, 4) = 7 (the
    4th house from the 4th house - father's father, paternal grandfather).
    Both arguments are 1-12; the result is always 1-12.
    """
    return ((base_house - 1) + (offset_house - 1)) % 12 + 1


def derive_relation_house(relation_path: List[str]) -> int:
    """
    Composes a chain of relations into a single house number by repeated
    house-from-house counting. relation_path is a list of relation names
    from BASE_RELATION_HOUSES, read as "the X's Y's Z ... " from the
    native outward. Examples:
      ["father"]                    -> 4  (father)
      ["mother"]                    -> 10 (mother)
      ["father", "father"]          -> 7  (paternal grandfather:
                                            4th-from-4th)
      ["mother", "father"]          -> 1  (maternal grandfather:
                                            4th-from-10th, wraps to 1)
      ["father", "mother"]          -> 1  (paternal grandmother:
                                            10th-from-4th, wraps to 1)
      ["mother", "mother"]          -> 7  (maternal grandmother:
                                            10th-from-10th, wraps to 7)
      ["sibling", "child"]          -> 7  (nephew/niece: 5th-from-3rd)
      ["spouse", "father"]          -> 10 (father-in-law: 4th-from-7th)
    Unknown relation names raise ValueError rather than guessing.
    """
    if not relation_path:
        raise ValueError("relation_path must be non-empty")
    house = 1
    for relation in relation_path:
        if relation not in BASE_RELATION_HOUSES:
            raise ValueError(
                f"Unknown relation '{relation}'. Known: {sorted(BASE_RELATION_HOUSES)}"
            )
        house = house_from_house(house, BASE_RELATION_HOUSES[relation])
    return house
