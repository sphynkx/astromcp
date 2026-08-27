"""
Generic Lot (Arabic Part) computation framework.

The design goal here, per the project owner: store a Lot's FORMULA
separately from the generic machinery that turns "a formula" into "a full
point with house placement, motion, and aspects" - because the project
owner expects to invent and study their own custom Lots, which means
wildly different formulas operating on wildly different pieces of the
chart, and the machinery needs to stay indifferent to what a given
formula actually does.

THE REGISTRY (LOT_REGISTRY below) is exactly that separation: a dict of
name -> LotDefinition, where a LotDefinition bundles the formula
together with its DISPLAY metadata (full name, genitive form for Russian
aspect-category text, a short abbreviation, an optional dedicated glyph,
and a one-line description of the methodology). Part of Fortune is
special - it's the one widely-known Lot with its own traditional symbol
(⊗) - but most Lots the project owner invents won't have that, which is
why `abbr` exists as the normal case and `glyph` is optional. This
metadata travels all the way into the JSON response (see compute_lot
below) specifically so downstream consumers - the SVG renderer in this
same process, and the separate MediaWiki Lua module reading the JSON
over HTTP - do NOT need their own hardcoded per-Lot display table. Add a
Lot here once, with its display info, and both the wheel/side-list/
tables in the SVG and the wiki's planetslist/aspectslist/categories pick
it up with no changes on their end.

A formula is any Python callable of shape `(raw: dict) -> float` (an
ecliptic longitude in degrees). `raw` is the same full kerykeion dump
already used throughout this project - so a formula has access to EVERY
point, house cusp, everything, and can reason about any of it (sign,
house, day/night, any arithmetic) however the theory being tested calls
for. Adding a new Lot is: write one function matching that shape, one
LotDefinition, one line in LOT_REGISTRY (or call register_lot at
runtime). Nothing else in this file, or in public_api.py, needs to know
what the formula does.

THE ENGINE (compute_lot/compute_all_lots) is the part that's the same
for every Lot regardless of formula: evaluate it, decompose the result
into sign/position (constants.decompose_longitude), work out which house
it falls in (houses.house_number_for_longitude - a Lot isn't one of
kerykeion's own objects, so it has no `.house` field the way a planet
does), and estimate its instantaneous motion. That last part matters for
aspects: aspects.aspect_status() needs A speed to tell applying from
separating, and a Lot's real motion is exactly as real as a planet's -
Part of Fortune moves at a highly non-uniform rate (dominated by the
Ascendant, which itself moves anywhere from very slowly to very fast
depending on latitude and time of day) but a genuine rate all the same.
Rather than hand-deriving that rate analytically per formula (which
would have to be redone for every new Lot the project owner invents),
this estimates it NUMERICALLY: evaluate the same formula against the
chart recomputed a short time later, and take the difference. This works
identically for literally any formula, which is the whole point of a
framework meant to stay agnostic about what's inside one. A negative
speed means the Lot is moving backward through the zodiac at that
moment - the same sense as planetary retrograde, even though nothing
about a Lot is "in retrograde" in the orbital-mechanics sense that word
originally means.

The result of compute_lot() is shaped exactly like any other point in
this project (abs_pos/sign/sign_num/position/house/speed), PLUS the
LotDefinition's display fields (name_ru/gen_ru/abbr/glyph/description) -
so it drops straight into the same dict that gets fed to
aspects.compute_aspects() alongside planets and angles, and picks up
aspects "for free" through that already-generic machinery, while still
carrying everything a renderer needs to label it.
"""

from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, Optional

from .arabic_parts import compute_part_of_fortune
from .constants import decompose_longitude
from .houses import house_number_for_longitude

LotFormula = Callable[[Dict[str, Any]], float]


@dataclass
class LotDefinition:
    formula: LotFormula
    name_ru: str          # nominative - "Парс Фортуны"
    gen_ru: str            # genitive - "Парса Фортуны" (for Russian aspect-category
                            # text like "Секстиль Луны и Парса Фортуны" - Russian
                            # noun-case declension isn't something to guess
                            # heuristically, so this is stated explicitly per Lot
                            # rather than derived from name_ru)
    abbr: str              # short text label - the normal case for a Lot without
                            # a widely-recognized dedicated symbol
    description: str       # one line on the formula/methodology, for anyone
                            # reading LOT_REGISTRY to understand what a Lot is
                            # without cross-referencing arabic_parts.py
    glyph: Optional[str] = None  # a dedicated Unicode symbol, ONLY for the rare
                                  # Lot that has one in real use (Part of Fortune);
                                  # None means "render abbr instead" everywhere


# name -> LotDefinition. Start with the one universally unambiguous Lot;
# add more here (or via register_lot) as they get tried out. See this
# module's docstring, and arabic_parts.compute_arabic_part's docstring,
# for how to register a formula that itself needs extra fixed arguments
# (a ruler/significator) - wrap it in a closure/lambda that captures
# those, since LotDefinition.formula's shape is always just (raw) -> float.
LOT_REGISTRY: Dict[str, LotDefinition] = {
    "part_of_fortune": LotDefinition(
        formula=compute_part_of_fortune,
        name_ru="Парс Фортуны",
        gen_ru="Парса Фортуны",
        abbr="ПФ",  # fallback only; this Lot has a real glyph below
        description=(
            "Asc + Луна - Солнце (дневное рождение), "
            "Asc + Солнце - Луна (ночное) - классический, однозначный Парс"
        ),
        glyph="\u2297",
    ),
}


def register_lot(name: str, definition: LotDefinition) -> None:
    """Adds or overwrites a Lot in LOT_REGISTRY. Equivalent to editing the
    dict directly - exists as a function mainly so a closure-wrapped
    formula (see module docstring) reads a bit more intentionally at the
    call site than a bare dict assignment."""
    LOT_REGISTRY[name] = definition


def compute_lot(
    name: str,
    raw: Dict[str, Any],
    raw_future: Optional[Dict[str, Any]] = None,
    dt_hours: float = 1.0 / 6.0,
) -> Dict[str, Any]:
    """
    Evaluates the named Lot's formula against raw and returns a
    point-shaped dict: {abs_pos, sign, sign_num, position, house, speed},
    plus that Lot's display metadata (name_ru, gen_ru, abbr, glyph,
    description) so a renderer never needs its own hardcoded lookup.

    raw_future - this SAME chart recomputed dt_hours later (see
    public_api.py, which builds this ONCE per request and shares it
    across every requested Lot, rather than one extra ephemeris call
    per Lot). When given, `speed` is a numeric derivative - (formula(
    raw_future) - formula(raw)) / dt_hours, converted to degrees/day to
    match the unit convention kerykeion's own points report speed in -
    computed the same way regardless of what the formula does inside,
    which is the reason this is numeric rather than analytic (an
    analytic speed would have to be re-derived by hand for every new
    formula added to the registry; this doesn't). If raw_future is
    omitted, `speed` is None - aspects.aspect_status() then can't tell
    applying from separating for this point's aspects, but the aspects
    themselves are still computed correctly either way.

    Raises ValueError if `name` isn't in LOT_REGISTRY.
    """
    definition = LOT_REGISTRY.get(name)
    if definition is None:
        raise ValueError(f"unknown lot '{name}' - registered: {sorted(LOT_REGISTRY)}")

    abs_pos = definition.formula(raw)
    result = decompose_longitude(abs_pos)
    result["house"] = house_number_for_longitude(raw, abs_pos)

    if raw_future is not None:
        future_abs_pos = definition.formula(raw_future)
        # Signed shortest angular delta - handles the 359->1 wraparound
        # the same way angular_separation does for the unsigned case.
        delta = ((future_abs_pos - abs_pos + 180) % 360) - 180
        result["speed"] = delta / dt_hours * 24.0  # -> degrees/day
    else:
        result["speed"] = None

    result["name_ru"] = definition.name_ru
    result["gen_ru"] = definition.gen_ru
    result["abbr"] = definition.abbr
    result["glyph"] = definition.glyph
    result["description"] = definition.description
    return result


def compute_all_lots(
    names: Iterable[str],
    raw: Dict[str, Any],
    raw_future: Optional[Dict[str, Any]] = None,
    dt_hours: float = 1.0 / 6.0,
) -> Dict[str, Dict[str, Any]]:
    """compute_lot() for each name in names, collected as {name: result}."""
    return {name: compute_lot(name, raw, raw_future, dt_hours) for name in names}
