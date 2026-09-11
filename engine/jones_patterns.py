"""
Marc Edmund Jones' planetary patterns ("chart shaping") - classifies the
overall distribution of the 10 classical+modern planets around the
zodiac into one of Jones' named shapes (Bundle, Locomotive, Bowl,
Bucket, Splash, Splay, See-Saw) plus one additional shape found only in
later Russian-language sources (Sling) that has no independent
English-language sourcing - see module docstring sections below and
BIBLIOGRAPHY.md for exactly what each shape's numeric definition is
based on and how confident that sourcing is.

Deliberately excluded from this module:
  - "Stool" (two planets in opposition inside an otherwise-empty Bundle
    gap, splitting it into two symmetric sub-gaps): the only source
    describing it is internally unclear about its own numeric
    definition, and no second source corroborates it as a distinct
    shape at all. Rather than guess at an uncorroborated definition, a
    handle of 2-3 planets is recognized as Sling ONLY when those handle
    planets are themselves a tight cluster (see HANDLE_CLUSTER_ORB) -
    i.e. one "fat" point, not two separate poles. A genuine two-pole
    split inside the gap (which is what Stool would require) simply
    isn't classified as anything by this module and falls through to
    the general classification below it.
  - "Werewolf" (every one of the 10 gaps under 30 deg, per Russian
    sources only): mathematically unreachable with exactly 10 points -
    10 gaps each under 30 deg can sum to at most just under 300 deg, but
    all gaps around a circle must sum to exactly 360 deg. Not merely
    under-sourced like Stool - provably impossible as described.

Design note on WHY a priority-ordered decision tree, not independent
per-shape checks: several of these shapes are strict numeric SUBSETS of
each other (a Bowl is a narrow-span case of the broader Locomotive
range) - a chart can satisfy more than one shape's raw numeric condition
at once. The tree below always checks the more specific/narrower shape
before falling back to the more general one that would also technically
match, so ties resolve toward the more descriptive label rather than an
arbitrary one.
"""

from itertools import combinations
from typing import Any, Dict, List, Optional, Tuple

from .aspects import angular_separation

JONES_PLANET_NAMES = [
    "sun", "moon", "mercury", "venus", "mars",
    "jupiter", "saturn", "uranus", "neptune", "pluto",
]

# Orb used wherever a specific angular relationship needs to be checked
# (e.g. "the two rim planets of a Bowl are opposite each other").
#
# WIDENED TWICE from an initial 9 deg, both times after checking against
# real production data - Jones' shapes are a coarse VISUAL
# characterization of the whole wheel, not a precision aspect:
#   1) Irina Allegrova (20.01.1952) had rim planets 18 deg off exact
#      opposition, which a 9 deg orb rejected outright, kicking a
#      clearly Bucket-shaped chart into "Mixed". Widened to 20.
#   2) Ksenia Sobchak (5.11.1981): occupied span 159.73 deg (rim
#      planets 20.27 deg off exact opposition) - a visually unambiguous
#      Bowl per independent cross-check against Astrodienst - missed
#      BOTH the span threshold (needed >=160) and this orb (was 20.0)
#      by the same 0.27 deg, and fell through into a Splay
#      misclassification instead (see the fix to _check_splay below for
#      the other half of that specific bug). Widened to 23 - generous
#      enough to cover a further 3 deg of real-world slack beyond the
#      already-widened case above, while still meaning something
#      ("roughly opposite", not "anywhere in the same half of the
#      wheel").
OPPOSITION_ORB = 23.0
# Orb used for "a lone planet/handle sits roughly in the middle of the
# empty gap" (Sling/Bucket) - wider than OPPOSITION_ORB since "roughly
# bisecting a wide gap" is an even looser condition than "roughly
# opposite a specific point". Also widened after the same production-
# data check.
MIDPOINT_ORB = 30.0
# Max span allowed WITHIN a multi-planet handle for it to still count as
# "one clustered mass" rather than two separate poles (the rejected
# Stool configuration) - a conjunction-width tolerance, not sourced to
# any specific number since no source gives one; chosen generously
# enough to cover a real conjunction but nowhere near half of the
# 120 deg+ gap a handle sits inside, so it can't accidentally admit a
# genuine two-pole split.
HANDLE_CLUSTER_ORB = 20.0


def _sorted_gaps(longitudes: Dict[str, float]) -> List[Tuple[float, str, str]]:
    """Returns (gap_size, name_of_point_starting_the_gap, name_of_point_ending_the_gap)
    for all N consecutive gaps around the circle, sorted by longitude."""
    items = sorted(longitudes.items(), key=lambda kv: kv[1] % 360)
    n = len(items)
    gaps = []
    for i in range(n):
        name_a, pos_a = items[i]
        name_b, pos_b = items[(i + 1) % n]
        gap = (pos_b - pos_a) % 360
        if gap == 0 and n > 1:
            gap = 360.0  # all points coincide - degenerate, treated as one big gap
        gaps.append((gap, name_a, name_b))
    return gaps


def _is_opposition(pos_a: float, pos_b: float, orb: float = OPPOSITION_ORB) -> bool:
    return abs(angular_separation(pos_a, pos_b) - 180.0) <= orb


def _points_in_arc(longitudes: Dict[str, float], start: float, end: float) -> List[str]:
    """Names of points strictly inside the open arc (start, end), going
    forward (counter-clockwise, increasing longitude) from start to end."""
    span = (end - start) % 360
    found = []
    for name, pos in longitudes.items():
        offset = (pos - start) % 360
        if 0 < offset < span:
            found.append(name)
    return found


def _enclosing_arc(longitudes: Dict[str, float]) -> Tuple[float, str, str]:
    """(occupied_span, gap_start_planet, gap_end_planet) for the smallest
    arc that contains every point in `longitudes` - i.e. 360 minus the
    single largest gap between consecutive points. gap_start/gap_end are
    the two planets bounding that largest (empty) gap - gap_start is
    where the empty gap begins (the "trailing" edge of the occupied
    arc), gap_end is where it ends (the "leading" edge)."""
    gaps = _sorted_gaps(longitudes)
    g_max, edge_a, edge_b = max(gaps, key=lambda g: g[0])
    return 360.0 - g_max, edge_a, edge_b


def classify_jones_figure(longitudes: Dict[str, float]) -> Dict[str, Any]:
    """
    longitudes: {planet_name: absolute_longitude_degrees, ...} - exactly
    the 10 names in JONES_PLANET_NAMES (nodes/Chiron/Lilith/asteroids are
    never part of this technique in any source consulted - see
    BIBLIOGRAPHY.md).

    Returns {"figure": <english slug>, "detail": <str>, "gaps": [...]}
    - "figure" is one of: bundle, sling, locomotive, bowl, bucket,
    splash, splay, seesaw, mixed. "mixed" is a genuine, correctly-
    computed result (no clean pattern fit), not an error - a caller
    should never treat it the way it treats an {"error": ...} response
    from this or any other tool in this project.
    """
    missing = [p for p in JONES_PLANET_NAMES if p not in longitudes]
    if missing:
        raise ValueError(f"classify_jones_figure requires all 10 points; missing: {missing}")

    gaps = _sorted_gaps(longitudes)
    gaps_report = [{"gap_deg": round(g, 3), "from": a, "to": b} for g, a, b in gaps]

    occupied_span, edge_a, edge_b = _enclosing_arc(longitudes)
    g_max = 360.0 - occupied_span

    # --- Clean Bundle (<=140 deg, nothing in the gap at all) ---
    if occupied_span <= 140.0:
        return {"figure": "bundle", "detail": f"all planets within {occupied_span:.1f} deg; empty gap {g_max:.1f} deg ({edge_a}->{edge_b})", "gaps": gaps_report}

    # --- Clean Bowl (155-205 deg span, rim planets in opposition, gap empty) ---
    # WIDENED from 160-200 after Ksenia Sobchak (5.11.1981) - occupied
    # span 159.73 deg, a visually unambiguous Bowl cross-checked directly
    # against Astrodienst, missed the old 160 lower bound by 0.27 deg and
    # fell through into a Splay misclassification (see the _check_splay
    # fix below for the other half of that bug). 155-205 gives 5 deg of
    # real-world slack on a threshold that's a rough visual guideline to
    # begin with, not a physical law.
    if 155.0 <= occupied_span <= 205.0 and _is_opposition(longitudes[edge_a], longitudes[edge_b]):
        return {"figure": "bowl", "detail": f"all planets within {occupied_span:.1f} deg; rim planets {edge_a}/{edge_b} in opposition, empty gap {g_max:.1f} deg", "gaps": gaps_report}

    # --- Splay / See-Saw: checked from the RAW gap structure (no
    # hypothetical point removal) BEFORE the Sling/Bucket handle search
    # below. This ordering matters: a genuine three-cluster Splay (Jones'
    # own "tripod", clusters roughly 120 deg apart) will very often ALSO
    # satisfy "two of the three clusters combined span <=140 deg, treat
    # the third as a handle" - i.e. it would misread as Sling if the
    # handle-search ran first. Splay/See-Saw are directly recognizable
    # from the gap list alone (three, or two, genuinely separate
    # clusters), so that direct reading takes priority over the more
    # speculative "what if we set a few points aside" interpretation
    # Sling/Bucket require. Jones' own literature is explicit that
    # Splay/See-Saw are the two hardest of his shapes to tell apart in
    # practice - this ordering doesn't eliminate that inherent ambiguity,
    # only resolves it consistently in one direction.
    seesaw = _check_seesaw(longitudes, gaps)
    if seesaw:
        return seesaw

    splay = _check_splay(longitudes, gaps)
    if splay:
        return splay

    # --- Sling / Bucket: 1-3 points ("handle"/"bail") set apart from an
    # otherwise-clean Bundle or Bowl formed by the remaining points.
    # Brute-forced over which 1-3 points are the handle, since removing
    # them changes which gap is largest for the remaining points -
    # trying every small subset (at most 175 combinations for 10 points)
    # is simpler and more robust than trying to infer the split from the
    # already-merged gap list. Handle size checked smallest-first so a
    # single lone planet is preferred over a same-fitting 2-3 point
    # reading of the same chart.
    names = list(longitudes.keys())
    for handle_size in (1, 2, 3):
        for handle in combinations(names, handle_size):
            remaining = {n: p for n, p in longitudes.items() if n not in handle}
            rem_span, rem_edge_a, rem_edge_b = _enclosing_arc(remaining)
            if rem_span <= 140.0:
                # A multi-planet handle is still a Sling, not a distinct
                # shape, as long as the handle planets are themselves a
                # tight cluster (conjunction) rather than two separate
                # poles splitting the gap - the latter is the rejected
                # "Stool" configuration (see module docstring), which
                # this deliberately does NOT recognize as anything but
                # a fallthrough to the general classification below.
                if _handle_is_opposite(longitudes, handle, remaining) and _handle_is_clustered(longitudes, handle):
                    return {"figure": "sling",
                            "detail": f"bundle ({rem_span:.1f} deg) with a {handle_size}-planet handle ({', '.join(handle)}, in conjunction) standing apart in the gap",
                            "gaps": gaps_report}
            elif 155.0 <= rem_span <= 205.0 and _is_opposition(remaining[rem_edge_a], remaining[rem_edge_b]):
                if _handle_is_opposite(longitudes, handle, remaining):
                    return {"figure": "bucket",
                            "detail": f"bowl ({rem_span:.1f} deg span) plus a {handle_size}-planet handle ({', '.join(handle)}) opposite the main group",
                            "gaps": gaps_report}

    # --- Locomotive (occupied span up to 240 deg / empty arc >=120 deg) ---
    if occupied_span <= 240.0:
        return {"figure": "locomotive", "detail": f"all planets within {occupied_span:.1f} deg (empty arc {g_max:.1f} deg >= 120 deg) - a full sign-and-a-half or more left empty", "gaps": gaps_report}

    # NOTE: a "Werewolf" shape (Russian-sources-only: every one of the 10
    # gaps under 30 deg) was considered and deliberately NOT implemented -
    # it is mathematically unreachable with exactly 10 points, since 10
    # gaps each under 30 deg can sum to at most just under 300 deg, but
    # all gaps around a circle must sum to exactly 360 deg. This is a
    # stronger objection than the sourcing concern already noted for
    # Sling above (this one isn't just under-sourced, it's provably
    # impossible to satisfy as literally described) - see BIBLIOGRAPHY.md.
    #
    # Splash's threshold was originally a hardcoded g_max<=60 deg, sourced
    # from a Russian-language paraphrase. Checked against real production
    # data (42 charts), that left a completely uncovered band - any chart
    # with a largest gap of roughly 60-120 deg matched NEITHER Splash
    # (needed <=60) NOR Locomotive (needed >=120) NOR any of the more
    # specific shapes above, and fell into "Mixed" by construction, not
    # because the chart was genuinely ambiguous (e.g. Alla Pugacheva,
    # 15.04.1949: largest gap 78.6 deg - comfortably "spread out" by any
    # ordinary reading, misclassified as Mixed under the old threshold).
    # Since every chart already fails Locomotive's own occupied_span<=240
    # check by the time execution reaches here (g_max<120), Splash is now
    # simply "not Locomotive, and no more specific shape fit" - the two
    # exhaust the whole range between them with nothing left uncovered,
    # matching Splash's traditional role as the default "no dominant
    # single-gap shape" reading rather than a narrow named pattern of its
    # own. "Mixed" remains in the code as a defensive fallback (kept
    # genuinely reachable, not dead code, in case a future change to the
    # checks above ever leaves a real gap again) but should no longer
    # fire in practice for any chart with 10 well-defined points - if it
    # does, that's worth investigating as a real gap, not dismissed as an
    # expected outcome.
    if g_max < 120.0:
        return {"figure": "splash", "detail": f"planets spread around most/all of the wheel, largest single gap {g_max:.1f} deg (<120 deg, i.e. not Locomotive-worthy)", "gaps": gaps_report}

    return {"figure": "mixed", "detail": f"no clean fit - largest gap {g_max:.1f} deg, occupied span {occupied_span:.1f} deg does not match any single pattern's range cleanly; this is a genuine, correctly-computed result (Jones' own sources acknowledge transitional/mixed charts exist), not a computation error", "gaps": gaps_report}


def _handle_is_clustered(all_longitudes: Dict[str, float], handle: Tuple[str, ...]) -> bool:
    """True if every planet in `handle` is within HANDLE_CLUSTER_ORB of
    every other one - i.e. the handle is one tight conjunction, not two
    (or more) separate poles. Trivially true for a single-planet handle.
    This is exactly the distinction between an accepted "fat" Sling and
    the rejected Stool (two planets in opposition inside the gap) - see
    module docstring."""
    if len(handle) <= 1:
        return True
    positions = [all_longitudes[h] for h in handle]
    return all(
        angular_separation(positions[i], positions[j]) <= HANDLE_CLUSTER_ORB
        for i in range(len(positions))
        for j in range(i + 1, len(positions))
    )


def _handle_is_opposite(all_longitudes: Dict[str, float], handle: Tuple[str, ...], remaining: Dict[str, float]) -> bool:
    """True if the handle point(s) sit roughly in the middle of the
    remaining group's own empty gap - i.e. genuinely opposite the main
    mass, not just incidentally excluded. Uses the wide MIDPOINT_ORB
    since Jones' own sources never gave this a tight number ("in the
    opposite arc" is qualitative)."""
    rem_span, edge_a, edge_b = _enclosing_arc(remaining)
    gap_start = remaining[edge_a]
    gap_end = remaining[edge_b]
    gap_size = (gap_end - gap_start) % 360
    gap_mid = (gap_start + gap_size / 2.0) % 360
    return all(
        abs(angular_separation(all_longitudes[h], gap_mid)) <= MIDPOINT_ORB
        for h in handle
    )


def _check_seesaw(longitudes: Dict[str, float], gaps: List[Tuple[float, str, str]]) -> Optional[Dict[str, Any]]:
    """
    See-Saw: planets fall into two groups on roughly opposite sides of
    the wheel, separated by two vacant arcs of very roughly 60-90 deg
    each (Jones' own figure, per claytentylor.com's transcription:
    'polarized around opposite ends of a diameter, leaving two vacant
    arcs of from 60 deg to 90 deg at opposite sides'). Implemented as:
    exactly two gaps in the 50-100 deg range (a bit wider than Jones'
    own 60-90 to allow for real charts not landing exactly on his
    illustrative range), together accounting for most of the circle's
    remaining space once the two planet-groups are removed, and roughly
    opposite each other (within ~40 deg of true opposition, generous
    since "opposite sides" was never given a tight orb in any source).
    """
    big_gaps = [(g, a, b) for g, a, b in gaps if 50.0 <= g <= 100.0]
    if len(big_gaps) != 2:
        return None
    (g1, a1, b1), (g2, a2, b2) = big_gaps
    # midpoints of the two gaps should be roughly opposite each other
    mid1 = (longitudes[a1] + g1 / 2.0) % 360
    mid2 = (longitudes[a2] + g2 / 2.0) % 360
    if not _is_opposition(mid1, mid2, 40.0):
        return None
    return {
        "figure": "seesaw",
        "detail": f"two planet groups separated by two gaps of {g1:.1f} deg and {g2:.1f} deg on roughly opposite sides of the wheel",
        "gaps": [{"gap_deg": round(g, 3), "from": a, "to": b} for g, a, b in gaps],
    }


def _check_splay(longitudes: Dict[str, float], gaps: List[Tuple[float, str, str]]) -> Optional[Dict[str, Any]]:
    """
    Splay ("Сгущение" in the Russian sources, though their own numeric
    description differs - see module docstring): Jones' own definition
    per astro.com/esotericmeanings.com is a "tripod" of exactly THREE
    separate planet clusters, with at least one empty sign (30 deg)
    between each pair of clusters - not a single sub-cluster inside an
    otherwise-Splash-like spread, which is how the Russian sources
    describe it. This implementation follows Jones' own English-sourced
    definition as the more authoritative/specific one.

    A "cluster boundary" is any gap >= 30 deg. Finding exactly three
    such boundaries is necessary but NOT sufficient - each of the three
    resulting clusters must also contain at least 2 planets. Without
    this check, a lopsided chart (a large main mass with one or two
    lone planets sitting just outside it, each more than 30 deg away)
    was being misread as a genuine three-way tripod instead of falling
    through to Bowl/Locomotive/Bucket, where a lone planet belongs (see
    _handle_is_clustered and the Sling/Bucket logic above - that's
    exactly the mechanism meant for "one stray planet near an otherwise
    unified mass"). Confirmed as a real bug via a direct cross-check
    against Astrodienst: Ksenia Sobchak (5.11.1981) has 8 planets in one
    arc and Mars/the Moon sitting alone 37.6/48.6 deg to either side -
    three gaps >=30 deg, satisfying the old check, but visually and
    structurally a Bowl (occupied span 159.7 deg), not a tripod.
    """
    big_gap_count = sum(1 for g, a, b in gaps if g >= 30.0)
    if big_gap_count != 3:
        return None

    # Rotate the gap list to start right after a big gap, so a genuine
    # cluster spanning the 0/360 wrap-around point isn't artificially
    # split into two pieces by where the list happens to start.
    start = next(i for i, (g, a, b) in enumerate(gaps) if g >= 30.0)
    ordered = gaps[start + 1:] + gaps[:start + 1]

    cluster_sizes: List[int] = []
    big_gap_values: List[float] = []
    current = 0
    for g, a, b in ordered:
        current += 1
        if g >= 30.0:
            cluster_sizes.append(current)
            big_gap_values.append(g)
            current = 0

    if len(cluster_sizes) == 3 and all(size >= 2 for size in cluster_sizes):
        return {
            "figure": "splay",
            "detail": f"three separate planet clusters (tripod, sizes {cluster_sizes}), separated by gaps of {', '.join(f'{g:.1f}' for g in sorted(big_gap_values, reverse=True))} deg",
            "gaps": [{"gap_deg": round(g, 3), "from": a, "to": b} for g, a, b in gaps],
        }
    return None
