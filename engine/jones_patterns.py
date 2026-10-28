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
#
# WIDENED from an initial 9 deg (mirroring OPPOSITION_ORB's own history
# above) after the Hensel twins (7.03.1990, conjoined - Abigail and
# Brittany, a single natal chart by necessity): Jupiter (91.0 deg) and
# Moon (122.8 deg) sit 31.8 deg apart, opposite an 8-planet main mass
# (Pluto through Sun, occupied span 119.2 deg) - the two OUTER sub-gaps
# either side of this Jupiter/Moon pair are 104.1 and 104.9 deg,
# essentially equal, which is the actual signature of one widened
# handle roughly bisecting the main gap (matching this module's own
# _handle_is_opposite check, which already passed for this pair before
# this change - only the clustering check was failing it). A true Stool
# would instead need the two handle planets themselves roughly opposite
# each other (~180 deg apart, per the module docstring's own Stool
# definition), splitting the gap at its EDGES rather than sitting
# together near its middle - 31.8 deg is nowhere close to that, so this
# widening doesn't blur the Sling/Stool distinction, it just recognizes
# that "one clustered mass" doesn't have to be as tight as a classical
# conjunction. Confirmed via direct classify_jones_figure() run on this
# chart's real computed longitudes: was "splash" (fell through the old
# 20 deg check entirely), correctly "sling" once widened. 35 deg gives
# ~3 deg of real-world slack beyond this case, same margin-adding style
# as OPPOSITION_ORB's own second widening above - not sourced to a
# specific number (no source gives one for handle width either), but
# checked against this real chart rather than picked arbitrarily.
HANDLE_CLUSTER_ORB = 35.0

# For a MULTI-planet handle only (trivially irrelevant for a single
# planet - see _handle_bisection_ratio): how close to equal the two
# "outer" sub-gaps either side of the handle (within the remaining
# group's own empty arc) must be, expressed as smaller/larger (1.0 =
# exactly equal). This is the check that was actually verified BY HAND
# when HANDLE_CLUSTER_ORB was widened above for the Hensel twins - "the
# two OUTER sub-gaps either side of this Jupiter/Moon pair are 104.1 and
# 104.9 deg, essentially equal, which is the actual signature of one
# widened handle roughly bisecting the main gap" - but that reasoning
# was never actually encoded as a check, only used once to justify the
# widening itself. It stayed unenforced until Gauquelin, Marie-Francoise
# (19.06.1929, 4:00, Neuchatel) exposed the gap: Moon+Saturn, 33.2 deg
# apart (comfortably inside HANDLE_CLUSTER_ORB, and each individually
# within MIDPOINT_ORB of the remaining mass's own gap midpoint - both
# existing checks already passed), standing apart from an otherwise-
# clean 8-planet, 138.0 deg bundle. But the two outer sub-gaps here are
# 85.0 and 103.9 deg - a visibly lopsided split (ratio 0.818), nothing
# like Hensel's near-perfect bisection (ratio 0.992) or Ryazanov, Eldar
# Alexandrovich's own 2-planet handle (Jupiter+Uranus, ratio 0.981,
# verified separately below). Classified "sling"; the user's own direct
# read of the real chart is uncertain between Locomotive, See-Saw, and
# "a very non-standard Sling" - i.e. NOT a confident Sling at all, which
# is exactly what an unenforced bisection check would miss (every OTHER
# condition this module checks for a handle still passes). Restricted to
# handle_size>=2 because a lone single-planet handle can't be "two poles
# lopsided to one side" in the first place - there's nothing to split
# unevenly. 0.90 is chosen to keep Hensel (0.992) and Ryazanov (0.981)
# comfortably clear with margin to spare, while still rejecting
# Gauquelin's 0.818 by a similar margin on the other side - not sourced
# to a specific number (same as HANDLE_CLUSTER_ORB itself), checked
# against these three real charts rather than picked arbitrarily.
HANDLE_BISECTION_RATIO_MIN = 0.90


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


def _second_largest_gap(longitudes: Dict[str, float]) -> float:
    """Returns the second-largest of the consecutive gaps around this
    point set (ties broken arbitrarily - only the magnitude matters
    here). Kept as a small utility (used by nothing in this module as
    of the rewrite below, but cheap and potentially useful for callers
    inspecting a chart's gap structure) - see _internal_big_gap_count
    for the actual "is this one clean mass" test now used internally."""
    gaps = sorted((g for g, _a, _b in _sorted_gaps(longitudes)), reverse=True)
    return gaps[1] if len(gaps) > 1 else 0.0


def _internal_big_gap_count(longitudes: Dict[str, float], threshold: float) -> int:
    """How many of this point set's OWN internal gaps (i.e. every
    consecutive gap except the single largest one, which is taken to
    be the empty arc defining the set's occupied span, not part of its
    internal structure) exceed `threshold`. Used to tell a single mass
    with one uneven/sparse stretch apart from a mass that is really two
    or more separate clusters - see CLEAN_MASS_BIG_GAP_THRESHOLD below
    for why this has to be a GAP COUNT, not a single magnitude ceiling
    on "the second-largest gap" (the earlier approach, kept only as
    _second_largest_gap above for compatibility)."""
    gaps = sorted((g for g, _a, _b in _sorted_gaps(longitudes)), reverse=True)
    return sum(1 for g in gaps[1:] if g > threshold)


# Threshold for what counts as a "real" internal break for
# _internal_big_gap_count, and the rule built on it (used everywhere
# this module checks that a Bundle/Bowl - or a Sling/Bucket's
# "remaining" group - is one clean mass, not two+ clusters squeezed
# into the same span): AT MOST ONE internal gap may exceed this value.
#
# This replaces an earlier approach (a flat ceiling on just the
# second-largest internal gap, widened once from 40 to 43 - see git
# history) that is mathematically unable to handle two real cases this
# project has now hit at once, because their defining numbers run the
# WRONG way for a single ceiling to separate them:
#
#   - Kovalenko, Roman Konstantinovich (10.07.1990, Novosibirsk, noon):
#     removing Pluto alone merges the two gaps either side of it
#     (mercury->pluto 108.7 deg + pluto->uranus 52.1 deg) into one
#     199.2 deg "occupied" span that passes the Bowl range and
#     opposition check - but that span contains not one but TWO large
#     internal gaps of its own, 76.3 deg (moon->mars) AND 49.7 deg
#     (mars->venus) - i.e. it is really three separate clusters spaced
#     unevenly around that span (and, together with Pluto, four
#     clusters around the whole wheel), not one mass with a handle.
#     MUST be rejected (correct reading: "splash", true largest gap
#     among all 10 points is 108.7 deg).
#   - Beletskaya, Irina Evgenyevna (20.11.1965, noon - no birth time on
#     record): removing Jupiter alone leaves a 172.3 deg remaining span
#     (pluto through saturn) that passes the Bowl range and opposition
#     check (edges 7.7 deg off exact opposition) - with exactly ONE
#     notably uneven internal gap, 55.6 deg (venus->saturn), and
#     nothing else in that span over 34.4 deg. Visually and
#     structurally a clean Bucket (confirmed directly by the user) with
#     Saturn simply sitting at the sparser end of an otherwise ordinary
#     bowl, not a second hidden cluster. MUST be accepted.
#
#   Kovalenko's rejected gap (49.7) is SMALLER than Beletskaya's
#   accepted one (55.6) - no single "second-largest gap <= N" ceiling
#   can put 49.7 on one side of N and 55.6 on the other. What actually
#   distinguishes them isn't the size of any one gap, it's the COUNT:
#   Kovalenko's remaining span has two comparably large internal breaks
#   (76.3 AND 49.7, both well clear of 40), Beletskaya's has only one
#   (55.6 - the next-biggest, 34.4, isn't close). Two real breaks means
#   (at least) three real clusters; one real break is just one mass
#   with an unevenly-filled stretch, which is well within how loosely
#   Jones' own Bowl/Bundle were ever defined to begin with.
#
#   40 deg is kept from the original ceiling's own reasoning (still
#   comfortably above HANDLE_CLUSTER_ORB's 35 deg handle-width
#   tolerance) and sits cleanly between Beletskaya's single qualifying
#   gap (55.6, counted) and her next one (34.4, not counted), while
#   still catching BOTH of Kovalenko's two qualifying gaps (76.3 and
#   49.7 are both > 40, so his count is 2, correctly rejected). The
#   Ryazanov, Eldar Alexandrovich case that motivated the earlier 40->43
#   widening (remaining mass's own largest internal gap 42.2 deg,
#   pluto->neptune) is also unaffected by reverting to 40 here: 42.2 is
#   its ONLY internal gap anywhere near large (next is 31.2), so its
#   count is 1 either way - the count-based rule admits it without
#   needing that widening at all.
CLEAN_MASS_BIG_GAP_THRESHOLD = 40.0


def _is_one_clean_mass(longitudes: Dict[str, float]) -> bool:
    """True if this point set reads as one mass (at most one internal
    gap over CLEAN_MASS_BIG_GAP_THRESHOLD) rather than two or more
    separate clusters - see CLEAN_MASS_BIG_GAP_THRESHOLD for the full
    reasoning and the real-chart cases that shaped it."""
    return _internal_big_gap_count(longitudes, CLEAN_MASS_BIG_GAP_THRESHOLD) <= 1


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
    if occupied_span <= 140.0 and _is_one_clean_mass(longitudes):
        return {"figure": "bundle", "detail": f"all planets within {occupied_span:.1f} deg; empty gap {g_max:.1f} deg ({edge_a}->{edge_b})", "gaps": gaps_report}

    # --- Clean Bowl (155-205 deg span, rim planets in opposition, gap empty) ---
    # WIDENED from 160-200 after Ksenia Sobchak (5.11.1981) - occupied
    # span 159.73 deg, a visually unambiguous Bowl cross-checked directly
    # against Astrodienst, missed the old 160 lower bound by 0.27 deg and
    # fell through into a Splay misclassification (see the _check_splay
    # fix below for the other half of that bug). 155-205 gives 5 deg of
    # real-world slack on a threshold that's a rough visual guideline to
    # begin with, not a physical law.
    if 155.0 <= occupied_span <= 205.0 and _is_opposition(longitudes[edge_a], longitudes[edge_b]) and _is_one_clean_mass(longitudes):
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
            # Upper bound WIDENED from 140 to 145 after Ryazanov, Eldar
            # Alexandrovich (18.11.1927, noon): removing a clustered,
            # roughly-opposite 2-planet handle (Jupiter+Uranus, 6.1 deg
            # apart) leaves an 8-planet remaining mass spanning 141.4
            # deg - a genuine Sling (handle-plus-bundle) structure by
            # every other check (opposition, clustering, internal-gap
            # cleanliness - see CLEAN_MASS_BIG_GAP_THRESHOLD above),
            # but 1.4 deg past the old 140 cutoff, so
            # it fell into the dead zone between this branch's old 140
            # ceiling and the Bucket branch's 155 floor below and was
            # never evaluated as a handle candidate at all - it fell
            # through past Locomotive to Splash (raw single largest gap
            # 107.3 deg, under the 120 deg Locomotive threshold), not
            # because the chart lacks handle structure but because the
            # structure it has was outside both windows this code
            # checked. 145 is chosen to admit this real case with a
            # small margin while staying a full 10 deg clear of the
            # Bucket branch's 155 floor just below, so the two windows
            # still don't overlap and a genuine half-circle Bowl is
            # never read as a Sling's "bundle" instead.
            if rem_span <= 145.0 and _is_one_clean_mass(remaining):
                # A multi-planet handle is still a Sling, not a distinct
                # shape, as long as the handle planets are themselves a
                # tight cluster (conjunction) rather than two separate
                # poles splitting the gap - the latter is the rejected
                # "Stool" configuration (see module docstring), which
                # this deliberately does NOT recognize as anything but
                # a fallthrough to the general classification below.
                # The remaining group must also itself be one clean mass,
                # not two+ clusters merely left under the span threshold
                # by removing the handle - see CLEAN_MASS_BIG_GAP_THRESHOLD.
                # A multi-planet handle must also roughly BISECT the gap
                # rather than sit lopsided to one side of it - see
                # HANDLE_BISECTION_RATIO_MIN (Gauquelin, Marie-Francoise).
                if (
                    _handle_is_opposite(longitudes, handle, remaining)
                    and _handle_is_clustered(longitudes, handle)
                    and _handle_bisection_ratio(longitudes, handle, remaining, rem_edge_a, rem_edge_b) >= HANDLE_BISECTION_RATIO_MIN
                ):
                    return {"figure": "sling",
                            "detail": f"bundle ({rem_span:.1f} deg) with a {handle_size}-planet handle ({', '.join(handle)}, in conjunction) standing apart in the gap",
                            "gaps": gaps_report}
            elif 155.0 <= rem_span <= 205.0 and _is_opposition(remaining[rem_edge_a], remaining[rem_edge_b]) and _is_one_clean_mass(remaining):
                # Same clustering requirement as the Sling branch above,
                # and for the same reason - this check was missing here
                # until Kashnitsky, Saveliy Efremovich (21.03.1952,
                # 12:00, Kyiv) exposed it: with Mars/Saturn/Neptune
                # removed as the "handle", the remaining 7 planets do
                # form a clean 198.8 deg bowl with Pluto/Moon in
                # opposition (18.8 deg off, within OPPOSITION_ORB) - but
                # Mars/Saturn/Neptune themselves span 35.9 deg
                # (mars-saturn alone, just over HANDLE_CLUSTER_ORB), i.e.
                # three separate points scattered across more than a
                # sign, not one handle. _handle_is_opposite alone can't
                # catch this - each of the three sits within MIDPOINT_ORB
                # of the bowl's gap-midpoint individually, which is all
                # that check verifies. Without this, the chart classified
                # as "bucket"; the correct real-chart reading (verified
                # via direct classify_jones_figure() run on these exact
                # longitudes) is "splash" - no handle in any 1-3 planet
                # subset is both opposite the remaining bowl/bundle AND
                # itself a tight cluster, so it falls through past
                # Locomotive to Splash (g_max=79.1 deg), matching how the
                # chart actually looks. A single- or double-planet handle
                # (the ordinary case) is unaffected: _handle_is_clustered
                # returns True trivially for len(handle)<=1, and a real
                # conjunction-handle still passes for 2-3 planets.
                # Same bisection requirement as the Sling branch above -
                # see HANDLE_BISECTION_RATIO_MIN (Gauquelin, Marie-Francoise).
                if (
                    _handle_is_opposite(longitudes, handle, remaining)
                    and _handle_is_clustered(longitudes, handle)
                    and _handle_bisection_ratio(longitudes, handle, remaining, rem_edge_a, rem_edge_b) >= HANDLE_BISECTION_RATIO_MIN
                ):
                    return {"figure": "bucket",
                            "detail": f"bowl ({rem_span:.1f} deg span) plus a {handle_size}-planet handle ({', '.join(handle)}, in conjunction) opposite the main group",
                            "gaps": gaps_report}

    # --- Locomotive (occupied span up to 260 deg / empty arc >=100 deg) ---
    # LOWERED from the traditional 240/120 split after a direct
    # biography cross-check against the "Фигура Джонса: Брызги" wiki
    # category turned up real people the 120 deg empty-arc requirement
    # was misreading as Splash despite having no handle structure at
    # all (so none of the Sling/Bucket widening above applies to them -
    # this is a plain threshold miss, not a dead zone): most notably
    # Antonov, Yuri Mikhailovich (birth time per Pavel Globa's own
    # rectification, 22:57) - g_max=118.1 deg, a single dominant empty
    # arc with no second gap anywhere near it (next-largest internal gap
    # only 48.7 deg), i.e. structurally a clean Locomotive missing the
    # old cutoff by under 2 deg - matching the user's own direct
    # biographical judgement ("он формирователь эпохи", not a candidate
    # for the mediocrity/drift Splash is read as in this project's own
    # socionics-based framework) and their own first-suggested fix for
    # this whole class of case ("Наверное стоит изменить диапазон до
    # 100 гр"). 100 deg was chosen, rather than the also-suggested 90,
    # specifically to keep a wide safety margin above Karpenko (88.4
    # deg) and Marchenko (86.3 deg) - the two charts in the same
    # category the user directly confirmed DO look like genuine
    # Splash/Splay by eye and should NOT flip. This does admit a number
    # of other charts in the 100-120 deg band that haven't been
    # individually biography-checked the way Antonov was - that's a
    # known, accepted tradeoff of a single global threshold rather than
    # a per-chart judgement call, flagged for the user to review against
    # the wiki category rather than silently assumed correct.
    if occupied_span <= 260.0:
        return {"figure": "locomotive", "detail": f"all planets within {occupied_span:.1f} deg (empty arc {g_max:.1f} deg >= 100 deg) - a full sign-and-a-half or more left empty", "gaps": gaps_report}

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
    # (needed <=60) NOR Locomotive (needed >=120 at the time) NOR any of
    # the more specific shapes above, and fell into "Mixed" by
    # construction, not because the chart was genuinely ambiguous (e.g.
    # Alla Pugacheva, 15.04.1949: largest gap 78.6 deg - comfortably
    # "spread out" by any ordinary reading, misclassified as Mixed under
    # the old threshold).
    # Since every chart already fails Locomotive's own occupied_span<=260
    # check by the time execution reaches here (g_max<100, following the
    # Locomotive threshold's own lowering to 100 deg above), Splash is
    # now simply "not Locomotive, and no more specific shape fit" - the
    # two exhaust the whole range between them with nothing left
    # uncovered, matching Splash's traditional role as the default "no
    # dominant single-gap shape" reading rather than a narrow named
    # pattern of its own. "Mixed" remains in the code as a defensive
    # fallback (kept genuinely reachable, not dead code, in case a future
    # change to the checks above ever leaves a real gap again) but should
    # no longer fire in practice for any chart with 10 well-defined
    # points - if it does, that's worth investigating as a real gap, not
    # dismissed as an expected outcome.
    if g_max < 100.0:
        return {"figure": "splash", "detail": f"planets spread around most/all of the wheel, largest single gap {g_max:.1f} deg (<100 deg, i.e. not Locomotive-worthy)", "gaps": gaps_report}

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


def _handle_bisection_ratio(
    all_longitudes: Dict[str, float],
    handle: Tuple[str, ...],
    remaining: Dict[str, float],
    edge_a: str,
    edge_b: str,
) -> float:
    """For a multi-planet handle, how evenly it splits the remaining
    group's own empty arc into two "outer" sub-gaps - the stretch from
    one edge of the empty arc to the nearest handle point, and the
    stretch from the farthest handle point to the other edge. Returns
    smaller/larger (1.0 = a perfect, dead-center bisection).

    Trivially 1.0 for a single-planet handle: with one point there is
    nothing to split unevenly, and the "lopsided handle" failure mode
    this function exists to catch has no meaning for a lone planet
    (see HANDLE_BISECTION_RATIO_MIN for the real-chart history behind
    this: Hensel twins 0.992, Ryazanov, Eldar Alexandrovich 0.981,
    both genuine, vs. Gauquelin, Marie-Francoise 0.818, not).
    """
    if len(handle) <= 1:
        return 1.0
    gap_start = remaining[edge_a]
    gap_end = remaining[edge_b]
    gap_total = (gap_end - gap_start) % 360
    offsets = sorted((all_longitudes[h] - gap_start) % 360 for h in handle)
    outer1 = offsets[0]
    outer2 = gap_total - offsets[-1]
    if outer1 <= 0 or outer2 <= 0:
        # Degenerate (a handle point sitting exactly on an edge) - don't
        # let a boundary artifact reject an otherwise fine handle.
        return 1.0
    return min(outer1, outer2) / max(outer1, outer2)


def _max_internal_gap_in_arc(longitudes: Dict[str, float], start_name: str, end_name: str) -> float:
    """Largest consecutive gap among every point lying in the CLOSED
    forward arc from `start_name` to `end_name` (inclusive of both
    endpoints), measuring only within that bounded arc - no wraparound
    past `end_name`. 0.0 if the arc contains one point or fewer. Used
    to check that a candidate "group" bounded by two gaps isn't itself
    hiding an even bigger internal split - see _check_seesaw."""
    start_pos = longitudes[start_name]
    end_pos = longitudes[end_name]
    span = (end_pos - start_pos) % 360
    offsets = sorted((pos - start_pos) % 360 for pos in longitudes.values() if (pos - start_pos) % 360 <= span + 1e-9)
    if len(offsets) <= 1:
        return 0.0
    return max(b - a for a, b in zip(offsets, offsets[1:]))


# How coherent each of Seesaw's two candidate groups must be, relative to
# the (smaller of the) two gaps dividing them: a group's own largest
# internal gap must be under this fraction of that defining gap. See the
# long comment inside _check_seesaw where this is used (Kovalenko/
# Kashnitsky false positives vs. the genuine Filimonov case) for the
# real-chart numbers that picked 0.6 specifically.
SEESAW_GROUP_COHERENCE_RATIO = 0.6


def _check_seesaw(longitudes: Dict[str, float], gaps: List[Tuple[float, str, str]]) -> Optional[Dict[str, Any]]:
    """
    See-Saw: planets fall into two groups on roughly opposite sides of
    the wheel, separated by two vacant arcs of very roughly 60-90 deg
    each (Jones' own figure, per claytentylor.com's transcription:
    'polarized around opposite ends of a diameter, leaving two vacant
    arcs of from 60 deg to 90 deg at opposite sides'). Implemented as:
    the two LARGEST gaps in the whole chart, each at least 50 deg (a
    bit wider a floor than Jones' own 60-90 to allow for real charts
    not landing exactly on his illustrative range), roughly opposite
    each other (within ~40 deg of true opposition, generous since
    "opposite sides" was never given a tight orb in any source).

    REWORKED from "exactly two gaps fall inside a fixed window" (originally
    50-100, once widened to 50-115) after Filimonov, Sergey (28.04.1969,
    noon - no birth time on record) exposed that a fixed window can't
    work AT ALL here, in either direction: the chart's two real dividing
    gaps are mercury->moon (111.9 deg) and mars->venus (113.8 deg) - close
    to each other in size and, per the opposition check below, genuinely
    close to opposite (20.1 deg off) - splitting the wheel into two
    compact, visually confirmed poles (4 planets spanning 46.2 deg; 6
    planets spanning 88.1 deg, with one merely uneven internal gap of
    57.3 deg between uranus and neptune - see _max_internal_gap_in_arc's
    coherence check below, which this case passes comfortably: 57.3 is
    well under the smaller defining gap, 111.9). Widening the window's
    ceiling to let in 111.9/113.8 ALSO let back in that same 57.3 deg
    internal gap (it was always inside 50-100 too), giving three matches
    instead of two and failing the "exactly two" count outright - no
    single window, however wide, can admit the real pair while excluding
    that unrelated third gap, because 57.3 sits numerically between parts
    of the pair rather than outside it. Taking the two LARGEST gaps
    directly (then checking everything else about them, as before) sidesteps
    this: the 57.3 deg gap is never a candidate divider at all once 111.9
    and 113.8 outrank it, and it is only ever seen afterwards by the
    per-group coherence check as what it actually is - ordinary internal
    unevenness inside the 6-planet pole, not a third division. Before
    this rework, the chart fell through to _check_splay instead, which
    DOES see a gap of that size (treats any gap >=30 deg as a cluster
    boundary, with no upper limit at all) and misread that same 57.3 deg
    unevenness as a THIRD genuine cluster boundary - three clusters of
    sizes [4, 2, 4], satisfying Splay's own "exactly three clusters, each
    >=2 planets" check even though two of those three "clusters" are
    really one pole with an uneven middle. Chart classified "splay";
    correct reading (confirmed directly by the user) is "seesaw". The
    50 deg floor is kept from the original window (still a meaningful
    "real vacant arc", not noise) - no ceiling is needed any more: a
    single dominant (Locomotive-sized) gap just won't have a genuine
    second, comparably-large, roughly-opposite gap to pair it with, so
    the opposition and per-group coherence checks below reject those
    cases on their own merits rather than needing a hardcoded cutoff to
    pre-filter them out.
    """
    sorted_desc = sorted(gaps, key=lambda g: -g[0])
    if len(sorted_desc) < 2 or sorted_desc[1][0] < 50.0:
        return None
    (g1, a1, b1), (g2, a2, b2) = sorted_desc[0], sorted_desc[1]
    # midpoints of the two gaps should be roughly opposite each other
    mid1 = (longitudes[a1] + g1 / 2.0) % 360
    mid2 = (longitudes[a2] + g2 / 2.0) % 360
    if not _is_opposition(mid1, mid2, 40.0):
        return None

    # Each of the two "groups" these gaps bound must itself be a real,
    # reasonably coherent group, not hiding an even-bigger split that
    # these two gaps alone don't capture. Added after Beletskaya, Irina
    # Evgenyevna (20.11.1965, noon - no birth time on record): Jupiter
    # sits alone, 78.5 deg from the main 8-planet mass on one side and
    # 109.2 deg from Saturn (the mass's far rim planet) on the other -
    # that 109.2 deg gap is the single LARGEST in the whole chart, but
    # it fell outside the old 50-100 deg filter window, so the old code
    # never saw it and happily matched "two gaps, 78.5 and 55.6, roughly
    # opposite" - reading {Saturn, Jupiter} as one of the two "groups",
    # when those two planets are actually just the bare endpoints of an
    # entirely empty 109 deg arc, not a group at all. Correct reading
    # (confirmed directly by the user, visually and structurally): a
    # single 9-planet Bucket with Jupiter as the sole handle (see the
    # matching CLEAN_MASS_BIG_GAP_THRESHOLD fix, needed for the Bucket
    # branch below to actually accept that remaining 9-planet mass once
    # Seesaw stops preempting it here).
    #
    # This started as an ABSOLUTE check (reject if a group's own largest
    # internal gap is >= the smaller defining gap, i.e. ratio >= 1.0) -
    # comfortably rejects Beletskaya (ratio 1.96: her bad "group" has an
    # internal gap of 109.2 against a smaller defining gap of 55.6), but
    # TOO LAX for two other real cases that the top-2-gaps rework above
    # (see its own comment) exposed by newly reaching this far at all:
    #   - Kovalenko, Roman Konstantinovich (10.07.1990, Novosibirsk,
    #     noon): 108.7/76.3 deg gaps, roughly opposite (0.5 deg off) -
    #     but EACH group is nearly half again as uneven as its own
    #     defining gap (internal-gap/defining-gap ratios 0.68 and 0.65).
    #     Established reading for this chart (see CLEAN_MASS_BIG_GAP_
    #     THRESHOLD above) is "locomotive" (raw g_max 108.7 deg, over
    #     this module's own 100 deg Locomotive floor) - a single
    #     dominant gap, not a real two-pole Seesaw.
    #   - Kashnitsky, Saveliy Efremovich (21.03.1952, 12:00, Kyiv):
    #     79.1/72.3 deg gaps, roughly opposite - one group's ratio is
    #     0.73. Established reading (see the Bucket-branch handle-
    #     clustering fix above) is "splash" (g_max 79.1 deg).
    # Replaced with a RATIO check instead: reject if a group's own
    # largest internal gap is 60% or more of the smaller defining gap.
    # Filimonov's worse group clears this comfortably (ratio 0.51,
    # clean margin below 0.6); Kovalenko's better group (0.65) and
    # Kashnitsky's worse group (0.73) both still correctly fail it. A
    # genuine two-pole Seesaw's own poles should look clearly MORE
    # coherent than the arcs separating them, not just technically
    # smaller - a ratio close to or above 1.0 was never a meaningful
    # bar for that, which is why it missed both regressions above.
    smaller_defining_gap = min(g1, g2)
    coherence_limit = SEESAW_GROUP_COHERENCE_RATIO * smaller_defining_gap
    if _max_internal_gap_in_arc(longitudes, b1, a2) >= coherence_limit:
        return None
    if _max_internal_gap_in_arc(longitudes, b2, a1) >= coherence_limit:
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
