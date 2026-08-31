"""
Horary chart computation: radicality, significators (including derived
houses for third-party questions), essential/accidental dignity, mutual
reception, void-of-course Moon, translation/collection of light,
perfection-interruption (prohibition/frustration/refranation), and the
final Yes/No verdict.

This module computes every fact deterministically. The companion
help_texts/horary.md tells the model to EXPLAIN a verdict this module
already reached, not to re-derive or second-guess it - the same
"полномочие уже вычисленного вердикта" pattern used for rectification
(see help_texts/rectification.md) and directions.

Sources (see BIBLIOGRAPHY.md for full citations): Masenkov's
"Построение хорарной карты" for the base horary_wri_gl0X textbook this
follows chapter-by-chapter (house meanings, the derived-house formula,
sign rulers, radicality/void-of-course rules, aspect orbs); Frawley,
"The Horary Textbook", for the precise classical definitions of
prohibition/frustration/refranation used here; Lavoie, "Lose This Book"
for the "judge the chart anyway" position on non-radical charts that
this implementation follows (a deliberate, documented choice - the
stricter classical position, per Lilly, is to refuse judgment entirely;
see help_texts/horary.md section 1 and section 9 for how this is
surfaced to the reader).

Design choices worth flagging up front, because the source prose leaves
them under-specified for a deterministic engine (each is called out
again at its point of use below):
  - Combustion orb: the source states "10-15 degrees" as the combustion
    zone itself (unlike the classical Lilly value of ~8.5 degrees) and
    describes "under the beams" only as "a greater distance" with no
    upper bound given. Implemented literally as combust <= 15 deg, with
    "under the beams" as 15-17 deg (the 17 deg upper bound is this
    module's own reasonable extension of classical convention, not
    something the source specifies numerically).
  - "Strong"/"weak" significator is a combination of several
    independently-named factors (own sign, exaltation, angular house,
    detriment, fall, cadent, combustion, besiegement, via combusta,
    aspects from luminaries/malefics) that the source lists but does not
    algebraically combine. A small point score (see ESSENTIAL_DIGNITY_*
    and _classify_strength below) resolves this into one classification;
    every contributing factor is still reported individually so nothing
    is hidden behind the number.
  - Void-of-course and "Moon's last aspect in sign" are checked against
    the 9 other real planets (Sun through Pluto) only - not Part of
    Fortune or the Cross of Fate. Classical VOC has always been a
    real-planet concept, and both of those points move at close to the
    Ascendant's own (fast, non-linear) rate, which the short-window
    linear projection used here cannot represent accurately - including
    them would produce numbers that look precise but aren't.
"""

import math
from typing import Any, Dict, List, Optional, Tuple

from .constants import SIGN_ORDER, TRADITIONAL_RULERS, MODERN_RULERS, decompose_longitude
from .aspects import angular_separation, aspect_status

# ==================== Horary-specific aspect/orb rules ====================
# Deliberately NOT engine.config.DEFAULT_ASPECT_SET/DEFAULT_ORB_TABLE_TRANSIT
# - horary uses its own smaller aspect set (no semisextile/semisquare/
# sesquiquadrate) and its own orb convention (a flat per-aspect base orb
# widened for the luminaries, rather than a per-planet-pair table).
HORARY_ASPECTS = [0, 60, 90, 120, 150, 180]
HORARY_FAVORABLE_ASPECTS = {60, 120}
HORARY_HARD_ASPECTS = {90, 150, 180}
# Base orb 7 deg for all aspects except quincunx (5 deg, stated with no
# range in the source); luminary bonus +3 deg brings Sun/Moon aspects to
# 10 deg, matching the source's stated "8-10 deg for Sun/Moon" - the
# bonus is flat rather than reproducing the exact 8-10 range, which is
# the same simplification engine.config's transit orb table already
# makes for the rest of this project.
HORARY_ORB_TABLE = {0: 7.0, 60: 7.0, 90: 7.0, 120: 7.0, 150: 5.0, 180: 7.0}
HORARY_LUMINARY_BONUS = 3.0
LUMINARIES = {"sun", "moon"}

CLASSICAL_SEVEN = ["sun", "moon", "mercury", "venus", "mars", "jupiter", "saturn"]
MODERN_THREE = {"uranus": "Aqu", "neptune": "Pis", "pluto": "Sco"}  # co-ruled sign only

ANGULAR_HOUSES = {1, 4, 7, 10}
SUCCEDENT_HOUSES = {2, 5, 8, 11}
CADENT_HOUSES = {3, 6, 9, 12}

# Exaltation sign index (0=Aries..11=Pisces) per classical planet - no
# exaltation is assigned to Uranus/Neptune/Pluto in this system.
EXALTATION_SIGN = {"sun": 0, "moon": 1, "mercury": 5, "venus": 11, "mars": 9, "jupiter": 3, "saturn": 6}
FALL_SIGN = {p: (s + 6) % 12 for p, s in EXALTATION_SIGN.items()}

# Via Combusta: 15 Libra - 15 Scorpio (195-225 abs degrees), except a
# roughly 2-degree window around 23 Libra (203 deg) where Spica's
# benefic influence is traditionally held to cancel the effect.
VIA_COMBUSTA_START = 195.0
VIA_COMBUSTA_END = 225.0
SPICA_EXCEPTION_CENTER = 203.0
SPICA_EXCEPTION_HALF_WIDTH = 1.0


def sign_idx(abs_pos: float) -> int:
    return int((abs_pos % 360) // 30)


_ORDINAL_WORDS = ["First", "Second", "Third", "Fourth", "Fifth", "Sixth",
                   "Seventh", "Eighth", "Ninth", "Tenth", "Eleventh", "Twelfth"]


def house_number_from_field(house_field: Optional[str]) -> Optional[int]:
    """kerykeion gives each point's house as a string like 'Seventh_House' -
    this turns that into the plain integer 7. Returns None if house_field
    is falsy or doesn't match the expected pattern."""
    if not house_field:
        return None
    word = house_field.replace("_House", "")
    try:
        return _ORDINAL_WORDS.index(word) + 1
    except ValueError:
        return None


def house_rulers(sign_idx: int) -> Tuple[str, Optional[str]]:
    """(primary_ruler, secondary_ruler_or_None) for a sign, by index.
    Secondary ruler is only set for Scorpio/Aquarius/Pisces (the three
    signs with a "modern" co-ruler in this system) - see
    house_meanings_and_rulers in horary_methodology / gl03 chapter 3."""
    primary = TRADITIONAL_RULERS[sign_idx]
    modern = MODERN_RULERS[sign_idx]
    secondary = modern if modern != primary else None
    return primary, secondary


def is_via_combusta(abs_pos: float) -> bool:
    pos = abs_pos % 360
    if SPICA_EXCEPTION_CENTER - SPICA_EXCEPTION_HALF_WIDTH <= pos <= SPICA_EXCEPTION_CENTER + SPICA_EXCEPTION_HALF_WIDTH:
        return False
    return VIA_COMBUSTA_START <= pos < VIA_COMBUSTA_END


def house_ruler_by_majority(cusp_start_abs: float, cusp_end_abs: float) -> Tuple[str, Optional[str]]:
    """
    Ruler of a succedent/cadent house: whichever sign occupies the larger
    share of the house's span, per horar_wri_gl03.txt chapter 3 part 1.
    A sign that is fully swallowed by the house (touches neither cusp -
    the classical "intercepted sign") is excluded from consideration
    even if it happens to hold the largest share; only the two boundary
    signs (the one at the start cusp, the one at the end cusp) compete,
    with the cusp's own sign winning any near-tie (<0.5 deg difference).
    Angular houses (I/IV/VII/X) don't use this - their ruler is simply
    whatever sign is on the cusp itself, no majority computation needed.

    Verified against gl03's own worked example (VIII cusp 26 Leo, IX
    cusp 8 Libra -> Virgo fully intercepted and excluded, Libra's 8 deg
    share beats Leo's 4 deg share -> Venus).
    """
    cusp_start_abs = cusp_start_abs % 360
    cusp_end_abs = cusp_end_abs % 360
    span = (cusp_end_abs - cusp_start_abs) % 360
    if span <= 0:
        span = 360.0
    start_sign = sign_idx(cusp_start_abs)
    end_sign = sign_idx(cusp_end_abs)
    if start_sign == end_sign and span < 30:
        return house_rulers(start_sign)

    shares: Dict[int, float] = {}
    pos = cusp_start_abs
    remaining = span
    current_sign = start_sign
    while remaining > 1e-9:
        sign_end_abs = (current_sign + 1) * 30
        dist_to_sign_end = (sign_end_abs - pos) % 360
        if dist_to_sign_end == 0:
            dist_to_sign_end = 30.0
        take = min(dist_to_sign_end, remaining)
        shares[current_sign] = shares.get(current_sign, 0.0) + take
        pos = (pos + take) % 360
        remaining -= take
        current_sign = (current_sign + 1) % 12

    boundary_signs = {start_sign, end_sign}
    candidates = {s: deg for s, deg in shares.items() if s in boundary_signs}
    if not candidates:
        candidates = shares
    best_sign = max(candidates, key=lambda s: candidates[s])
    if len(candidates) == 2:
        vals = list(candidates.values())
        if abs(vals[0] - vals[1]) < 0.5:
            best_sign = start_sign
    return house_rulers(best_sign)


def derived_house(chain: List[int]) -> Dict[str, Any]:
    """
    D' = sum(chain) - N + 1, reduced into 1-12. `chain` is the sequence of
    house numbers for each hop from the querent outward (see
    help_texts/horary.md section 2 for worked examples - e.g. a cousin's
    dog is [3,5,3,6] via "mother(4)->her brother(3rd-from-4th)->his
    son(5th-from-that)->dog(6th-from-that)", collapsed to house numbers).
    Returns the resolved house plus the raw chain for transparency, since
    the model is instructed to use this number verbatim rather than
    recomputing the chain itself.
    """
    if not chain:
        raise ValueError("derived_house chain must have at least one house number")
    n = len(chain)
    d = sum(chain) - n + 1
    while d > 12:
        d -= 12
    while d < 1:
        d += 12
    return {"chain": chain, "resolved_house": d}


def essential_dignity(planet: str, sign_idx: int) -> Dict[str, Any]:
    """
    Returns {status, detail} where status is one of:
    "rulership" (own sign, incl. modern co-rulership of Sco/Aqu/Pis for
    Uranus/Neptune/Pluto specifically), "exaltation", "detriment", "fall",
    "peregrine" (none of the above - no essential dignity or debility).
    Uranus/Neptune/Pluto only ever get "rulership" (in their one
    co-ruled sign) or "peregrine" - no exaltation/detriment/fall is
    assigned to them in this system (they simply weren't part of the
    classical scheme those are drawn from).
    """
    primary, secondary = house_rulers(sign_idx)
    if planet == primary or planet == secondary:
        return {"status": "rulership", "detail": f"{'primary' if planet == primary else 'secondary'} ruler of {SIGN_ORDER[sign_idx]}"}
    if planet in EXALTATION_SIGN:
        if EXALTATION_SIGN[planet] == sign_idx:
            return {"status": "exaltation", "detail": f"exalted in {SIGN_ORDER[sign_idx]}"}
        if FALL_SIGN[planet] == sign_idx:
            return {"status": "fall", "detail": f"in fall in {SIGN_ORDER[sign_idx]}"}
        # detriment = the sign opposite whichever sign(s) this planet rules
        ruled_signs = [i for i in range(12) if TRADITIONAL_RULERS[i] == planet]
        if any((s + 6) % 12 == sign_idx for s in ruled_signs):
            return {"status": "detriment", "detail": f"in detriment in {SIGN_ORDER[sign_idx]}"}
    return {"status": "peregrine", "detail": "no essential dignity or debility here"}


def _combustion_status(planet_pos: float, sun_pos: float, planet_name: str) -> Optional[Dict[str, Any]]:
    if planet_name == "sun":
        return None
    orb = angular_separation(planet_pos, sun_pos)
    if orb <= 15.0:
        return {"status": "combust", "orb_to_sun": round(orb, 3),
                "detail": f"{round(orb, 2)} deg from the Sun (combust; severity increases the closer it is)"}
    if orb <= 17.0:
        return {"status": "under_the_beams", "orb_to_sun": round(orb, 3),
                "detail": f"{round(orb, 2)} deg from the Sun (under the beams - milder than combustion)"}
    return None


def _besieged_status(planet_pos: float, mars_pos: float, saturn_pos: float) -> Optional[Dict[str, Any]]:
    lo, hi = sorted([mars_pos % 360, saturn_pos % 360])
    short_arc = (hi - lo) <= 180
    if short_arc:
        between = lo < (planet_pos % 360) < hi
    else:
        # the short arc wraps through 0 deg
        between = (planet_pos % 360) > hi or (planet_pos % 360) < lo
    if not between:
        return None
    orb_mars = angular_separation(planet_pos, mars_pos)
    orb_saturn = angular_separation(planet_pos, saturn_pos)
    if orb_mars <= 15.0 and orb_saturn <= 15.0:
        return {"status": "captive", "detail": "between Mars and Saturn, both within 15 deg - besieged and captive"}
    return {"status": "besieged", "detail": "between Mars and Saturn by longitude (besieged)"}


def assess_significator(
    planet_name: str,
    planet_data: Dict[str, Any],
    house_num: int,
    all_points: Dict[str, Dict[str, Any]],
    aspects_involving: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Full dignity assessment for one significator: essential dignity,
    accidental dignity (house angularity, combustion, besiegement, via
    combusta, aspects received from luminaries/malefics), a resolved
    strong/weak/mixed classification, and the list of factors that
    produced it (so the explanation can cite them individually rather
    than just the label).
    """
    sidx = sign_idx(planet_data["abs_pos"])
    factors: List[str] = []
    score = 0.0

    ess = essential_dignity(planet_name, sidx)
    factors.append(f"essential dignity: {ess['detail']}")
    score += {"rulership": 2.0, "exaltation": 2.0, "detriment": -2.0, "fall": -2.0, "peregrine": 0.0}[ess["status"]]

    if house_num in ANGULAR_HOUSES:
        factors.append(f"in angular house {house_num}")
        score += 1.0
    elif house_num in CADENT_HOUSES:
        factors.append(f"in cadent house {house_num}")
        score -= 1.0

    combustion = None
    if "sun" in all_points and planet_name != "sun":
        combustion = _combustion_status(planet_data["abs_pos"], all_points["sun"]["abs_pos"], planet_name)
        if combustion:
            factors.append(combustion["detail"])
            score += -2.0 if combustion["status"] == "combust" else -0.5

    besiege = None
    if "mars" in all_points and "saturn" in all_points and planet_name not in ("mars", "saturn"):
        besiege = _besieged_status(planet_data["abs_pos"], all_points["mars"]["abs_pos"], all_points["saturn"]["abs_pos"])
        if besiege:
            factors.append(besiege["detail"])
            score += -2.0 if besiege["status"] == "captive" else -1.0

    via_combusta = is_via_combusta(planet_data["abs_pos"])
    if via_combusta:
        factors.append("on the Via Combusta")
        score -= 1.0

    malefic_hard_applying = []
    luminary_favorable_applying = []
    for asp in aspects_involving:
        other = asp["point_b"] if asp["point_a"] == planet_name else asp["point_a"]
        if asp["status"] != "applying":
            continue
        if other in LUMINARIES and other != planet_name and asp["aspect_deg"] in HORARY_FAVORABLE_ASPECTS:
            luminary_favorable_applying.append((other, asp["aspect_deg"]))
        if other in (LUMINARIES | {"mars", "saturn", "uranus", "neptune", "pluto"}) and other != planet_name \
                and asp["aspect_deg"] in HORARY_HARD_ASPECTS:
            malefic_hard_applying.append((other, asp["aspect_deg"]))

    if luminary_favorable_applying:
        factors.append(f"applying favorable aspect from a luminary ({luminary_favorable_applying[0][0]})")
        score += 1.0
    if malefic_hard_applying:
        factors.append(f"applying hard aspect from {malefic_hard_applying[0][0]}")
        score -= 1.0

    retrograde = bool(planet_data.get("retrograde"))
    if retrograde:
        factors.append("retrograde (a change of mind/circumstance signal, not a weakness by itself)")

    if score >= 1.0:
        strength = "strong"
    elif score <= -1.0:
        strength = "weak"
    else:
        strength = "mixed"

    return {
        "planet": planet_name,
        "sign": SIGN_ORDER[sidx],
        "house": house_num,
        "essential_dignity": ess,
        "combustion": combustion,
        "besieged": besiege,
        "via_combusta": via_combusta,
        "retrograde": retrograde,
        "score": score,
        "strength": strength,
        "factors": factors,
    }


def mutual_reception(sig_a: Dict[str, Any], sig_b: Dict[str, Any], name_a: str, name_b: str) -> bool:
    """Sign-based mutual reception: A sits in a sign B rules AND B sits in
    a sign A rules. Reception by exaltation/term/face is a documented,
    explicitly-optional extension in the source material (an astrologer's
    personal choice, not a settled technique) and is deliberately not
    implemented here - see help_texts/horary.md."""
    sign_a = sign_idx(sig_a["abs_pos"])
    sign_b = sign_idx(sig_b["abs_pos"])
    a_rules_b_sign = name_a in house_rulers(sign_b)
    b_rules_a_sign = name_b in house_rulers(sign_a)
    return a_rules_b_sign and b_rules_a_sign


def key_aspect_between(name_a: str, pt_a: Dict[str, Any], name_b: str, pt_b: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    sep = angular_separation(pt_a["abs_pos"], pt_b["abs_pos"])
    speed_a = pt_a.get("speed", 0.0) or 0.0
    best = None
    for deg in HORARY_ASPECTS:
        allowed = HORARY_ORB_TABLE[deg] + (HORARY_LUMINARY_BONUS if (name_a in LUMINARIES or name_b in LUMINARIES) else 0.0)
        orb = abs(sep - deg)
        if orb <= allowed and (best is None or orb < best["exact_orb"]):
            status = aspect_status(pt_a["abs_pos"], speed_a, pt_b["abs_pos"], deg, orb)
            best = {"point_a": name_a, "point_b": name_b, "aspect_deg": deg, "exact_orb": round(orb, 4), "status": status}
    return best


def _degrees_to_sign_end(abs_pos: float) -> float:
    return 30.0 - (abs_pos % 30)


def check_interruption(
    name_a: str, pt_a: Dict[str, Any],
    name_b: str, pt_b: Dict[str, Any],
    key_aspect: Dict[str, Any],
    all_points: Dict[str, Dict[str, Any]],
    future_points: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Checks whether the applying aspect between A and B perfects cleanly,
    or is interrupted first. Classical terms (Frawley, "The Horary
    Textbook"): REFRANATION - the moving planet turns retrograde before
    completing; PROHIBITION - the moving planet completes an aspect with
    some third planet C first; FRUSTRATION - the planet being moved
    TOWARD instead completes an aspect with a third planet first, or
    changes sign before being reached. Returns None if nothing disrupts
    it (or if the aspect isn't applying at all - nothing to interrupt).

    The prohibition/frustration/sign-change checks are simulated forward
    from the horary moment using each point's current (instantaneous)
    speed - a linear approximation valid over the short windows involved
    (at most a few days, bounded by whichever significator would reach
    the end of its current sign first), the same approximation already
    used throughout this project for short-range aspect timing.

    Refranation is different: a station is exactly where a planet's
    speed passes through zero, so linear extrapolation from the CURRENT
    speed cannot tell whether a flip happens before perfection (a speed
    that's just slowing down and one that's about to reverse look
    identical from a single snapshot). `future_points` - a second chart
    built for the moment the aspect would perfect, supplied by the
    caller (engine/tools.py builds it via a real ephemeris call, not an
    approximation) - resolves this properly: if either point's speed
    sign there differs from its speed sign now, a station happened in
    between. If future_points isn't supplied, refranation is simply not
    checked (skipped, not guessed at) rather than silently assuming an
    answer either way.
    """
    if key_aspect["status"] != "applying":
        return None

    sep = angular_separation(pt_a["abs_pos"], pt_b["abs_pos"])
    aspect_deg = key_aspect["aspect_deg"]
    rel_speed = (pt_a.get("speed", 0.0) or 0.0) - (pt_b.get("speed", 0.0) or 0.0)
    if rel_speed == 0:
        return None  # static - won't perfect either way, not a disruption per se
    time_to_perfect = abs(key_aspect["exact_orb"]) / abs(rel_speed)

    if future_points:
        for name, pt in ((name_a, pt_a), (name_b, pt_b)):
            speed_now = pt.get("speed", 0.0) or 0.0
            future_pt = future_points.get(name)
            if future_pt is None or speed_now == 0:
                continue
            speed_future = future_pt.get("speed", 0.0) or 0.0
            if speed_now * speed_future < 0:  # sign flipped
                return {"type": "refranation", "planet": name,
                        "detail": f"{name} turns stationary and reverses direction before the aspect perfects"}

    # prohibition/frustration: does either A or B perfect a DIFFERENT
    # aspect with some third planet C first, or change sign first?
    events = []
    for mover_name, mover, other_name in ((name_a, pt_a, name_b), (name_b, pt_b, name_a)):
        # sign change
        deg_to_edge = _degrees_to_sign_end(mover["abs_pos"]) if (mover.get("speed", 0.0) or 0.0) >= 0 \
            else (mover["abs_pos"] % 30)
        speed_abs = abs(mover.get("speed", 0.0) or 0.0)
        if speed_abs > 0:
            t_sign_change = deg_to_edge / speed_abs
            if t_sign_change < time_to_perfect:
                events.append((t_sign_change, "sign_change", mover_name, None))
        # aspect with a third planet
        for c_name, c_pt in all_points.items():
            if c_name in (name_a, name_b):
                continue
            c_sep = angular_separation(mover["abs_pos"], c_pt["abs_pos"])
            c_rel_speed = (mover.get("speed", 0.0) or 0.0) - (c_pt.get("speed", 0.0) or 0.0)
            if c_rel_speed == 0:
                continue
            for deg in HORARY_ASPECTS:
                allowed = HORARY_ORB_TABLE[deg] + (HORARY_LUMINARY_BONUS if (mover_name in LUMINARIES or c_name in LUMINARIES) else 0.0)
                c_orb = abs(c_sep - deg)
                status = aspect_status(mover["abs_pos"], mover.get("speed", 0.0) or 0.0, c_pt["abs_pos"], deg, c_orb)
                if status != "applying":
                    continue
                t_c = c_orb / abs(c_rel_speed)
                if t_c < time_to_perfect and c_orb <= allowed:
                    events.append((t_c, "third_planet_aspect", mover_name, c_name))
    if not events:
        return None
    events.sort(key=lambda e: e[0])
    t_event, kind, mover_name, other_planet = events[0]
    if mover_name == name_a:
        label = "prohibition"
        detail = (f"before completing the aspect, {name_a} " +
                  (f"changes sign" if kind == "sign_change" else f"aspects {other_planet} first"))
    else:
        label = "frustration"
        detail = (f"before {name_a} reaches it, {name_b} " +
                  (f"changes sign" if kind == "sign_change" else f"aspects {other_planet} first"))
    return {"type": label, "planet": mover_name, "detail": detail}


def find_translation_collection(
    name_a: str, pt_a: Dict[str, Any],
    name_b: str, pt_b: Dict[str, Any],
    all_points: Dict[str, Dict[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Translation of light: a third planet C, faster than BOTH A and B,
    has just separated from a favorable aspect with one of them and is
    now applying a favorable aspect to the other. Collection of light: a
    third planet C, slower than both, has favorable APPLYING aspects to
    both at once. Only trine/sextile count as "favorable" here, per the
    source's own aspect-type taxonomy (conjunction is neutral-by-planet,
    not "favorable" in this specific sense).
    """
    speed_a = abs(pt_a.get("speed", 0.0) or 0.0)
    speed_b = abs(pt_b.get("speed", 0.0) or 0.0)
    translations, collections = [], []

    for c_name, c_pt in all_points.items():
        if c_name in (name_a, name_b):
            continue
        speed_c = abs(c_pt.get("speed", 0.0) or 0.0)

        asp_to_a = key_aspect_between(c_name, c_pt, name_a, pt_a)
        asp_to_b = key_aspect_between(c_name, c_pt, name_b, pt_b)
        fav_to_a = asp_to_a and asp_to_a["aspect_deg"] in HORARY_FAVORABLE_ASPECTS
        fav_to_b = asp_to_b and asp_to_b["aspect_deg"] in HORARY_FAVORABLE_ASPECTS

        if speed_c > speed_a and speed_c > speed_b:
            case1 = fav_to_a and asp_to_a["status"] == "separating" and fav_to_b and asp_to_b["status"] == "applying"
            case2 = fav_to_b and asp_to_b["status"] == "separating" and fav_to_a and asp_to_a["status"] == "applying"
            if case1 or case2:
                translations.append({
                    "planet": c_name,
                    "from": name_a if case1 else name_b,
                    "to": name_b if case1 else name_a,
                    "aspect_from": asp_to_a if case1 else asp_to_b,
                    "aspect_to": asp_to_b if case1 else asp_to_a,
                })
        if speed_c < speed_a and speed_c < speed_b:
            if fav_to_a and asp_to_a["status"] == "applying" and fav_to_b and asp_to_b["status"] == "applying":
                collections.append({
                    "planet": c_name,
                    "aspect_to_a": asp_to_a,
                    "aspect_to_b": asp_to_b,
                })
    return {"translations": translations, "collections": collections}


def moon_forward_aspects(moon: Dict[str, Any], all_points: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """
    Every aspect the Moon will complete between her current position and
    the end of her current sign, checked against the 9 other real planets
    only (see module docstring for why Part of Fortune/Cross of Fate are
    excluded). Returns void_of_course=True if none are found. "last
    aspect" is whichever completes latest (closest to the sign boundary)
    - the classical significator of how the matter finally resolves.
    """
    moon_speed = moon.get("speed", 0.0) or 0.0
    sign_end_distance = _degrees_to_sign_end(moon["abs_pos"])
    time_to_sign_exit = sign_end_distance / moon_speed if moon_speed > 0 else float("inf")

    # The 9 other real planets only - see module docstring for why Part of
    # Fortune/Cross of Fate are excluded from VOC specifically.
    voc_candidate_names = {"sun", "mercury", "venus", "mars", "jupiter", "saturn", "uranus", "neptune", "pluto"}

    found = []
    for name, pt in all_points.items():
        if name not in voc_candidate_names:
            continue
        sep = angular_separation(moon["abs_pos"], pt["abs_pos"])
        rel_speed = moon_speed - (pt.get("speed", 0.0) or 0.0)
        if rel_speed <= 0:
            continue
        # Moon is always a luminary, so every Moon aspect already gets the
        # bonus; add it again only if the OTHER point is also a luminary
        # (i.e. the Sun) would double it incorrectly - one bonus is the
        # correct amount regardless of which side is the luminary, so it
        # is added exactly once here, unconditionally.
        for deg in HORARY_ASPECTS:
            allowed = HORARY_ORB_TABLE[deg] + HORARY_LUMINARY_BONUS
            orb = abs(sep - deg)
            status = aspect_status(moon["abs_pos"], moon_speed, pt["abs_pos"], deg, orb)
            if status != "applying" or orb > allowed:
                continue
            t_exact = orb / rel_speed
            if t_exact <= time_to_sign_exit:
                found.append({"point": name, "aspect_deg": deg, "exact_orb": round(orb, 4),
                               "time_to_exact_days": round(t_exact, 4),
                               "favorable": deg in HORARY_FAVORABLE_ASPECTS})
    found.sort(key=lambda e: e["time_to_exact_days"])
    return {
        "void_of_course": len(found) == 0,
        "aspects_before_sign_exit": found,
        "last_aspect": found[-1] if found else None,
    }


def check_radicality(
    asc_abs_pos: float,
    moon_abs_pos: float,
    relevant_angle_sign_idx: int,
    saturn_house: int,
    saturn_aspects_to_relevant_house: List[Dict[str, Any]],
    is_self_query: bool,
) -> Dict[str, Any]:
    """
    Radicality (whether the chart is fit to judge). The main check (Asc in
    the first/last 3 degrees of its sign) is the only one this
    implementation treats as decisive by itself; the rest accumulate as
    secondary warning flags, per help_texts/horary.md section 1.

    The secondary checks look at house VII (and its cusp sign) normally,
    or house I (and the Ascendant's own sign) when the astrologer is
    judging their own question - `relevant_angle_sign_idx` and
    `saturn_house`/`saturn_aspects_to_relevant_house` should already be
    whichever of the two applies; this function doesn't re-derive that
    choice itself - the caller (tools.horary_chart) does.
    """
    target_house = 1 if is_self_query else 7
    asc_deg_in_sign = asc_abs_pos % 30
    main_failed = asc_deg_in_sign <= 2.0 or asc_deg_in_sign >= 27.0

    secondary = []
    if is_via_combusta(moon_abs_pos):
        secondary.append("Moon on the Via Combusta")
    if is_via_combusta(asc_abs_pos):
        secondary.append("Ascendant on the Via Combusta")
    if saturn_house == target_house:
        secondary.append(f"Saturn in house {target_house}")
    if relevant_angle_sign_idx in (9, 10):  # Cap=9, Aqu=10
        cusp_label = "the Ascendant" if is_self_query else "the VII cusp"
        secondary.append(f"Capricorn or Aquarius on {cusp_label}")
    for asp in saturn_aspects_to_relevant_house:
        if asp.get("status") == "applying" and asp.get("aspect_deg") in HORARY_HARD_ASPECTS:
            secondary.append(f"applying hard aspect from Saturn to a planet in house {target_house}")
            break

    return {
        "main_check_failed": main_failed,
        "asc_degree_in_sign": round(asc_deg_in_sign, 3),
        "secondary_warnings": secondary,
        "radical": not main_failed,
    }


def compute_verdict(
    querent_name: str, querent_pt: Dict[str, Any],
    quesited_name: str, quesited_pt: Dict[str, Any],
    all_points: Dict[str, Dict[str, Any]],
    querent_assessment: Dict[str, Any],
    quesited_assessment: Dict[str, Any],
    reception: bool,
    voc: Dict[str, Any],
    future_points: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    The decision tree from help_texts/horary.md section 5, applied
    mechanically. Returns the verdict plus every intermediate fact that
    led to it, so the explanation can cite them - never just the label.
    """
    key_aspect = key_aspect_between(querent_name, querent_pt, quesited_name, quesited_pt)
    interruption = None
    tc = find_translation_collection(querent_name, querent_pt, quesited_name, quesited_pt, all_points)

    verdict = None
    outcome_quality = None
    path = []

    if key_aspect and key_aspect["status"] == "exact":
        verdict = True
        outcome_quality = "clean"
        path.append("significators are the same planet, or already in an exact aspect - union already in effect")
    elif key_aspect and key_aspect["status"] == "applying":
        interruption = check_interruption(querent_name, querent_pt, quesited_name, quesited_pt,
                                           key_aspect, all_points, future_points)
        if interruption:
            verdict = False
            outcome_quality = "no"
            path.append(f"applying {key_aspect['aspect_deg']} deg aspect exists but is interrupted ({interruption['type']})")
        elif key_aspect["aspect_deg"] in ({0} | HORARY_FAVORABLE_ASPECTS):
            verdict = True
            outcome_quality = "clean"
            path.append(f"clean applying {key_aspect['aspect_deg']} deg aspect between the significators")
        else:  # hard aspect: 90, 150, 180
            strong_a = querent_assessment["strength"] != "weak" or reception
            strong_b = quesited_assessment["strength"] != "weak" or reception
            if strong_a and strong_b:
                verdict = True
                outcome_quality = "under_tension"
                path.append(f"applying hard aspect ({key_aspect['aspect_deg']} deg), but both significators strong"
                             + (" (reception compensates)" if reception and (querent_assessment['strength'] == 'weak' or quesited_assessment['strength'] == 'weak') else "")
                             + " - achieved under tension")
            elif not strong_a:
                verdict = False
                outcome_quality = "no"
                path.append("applying hard aspect and the querent's significator is weak")
            else:
                # The quesited significator being weak under an applying
                # hard aspect is the classical "pyrrhic victory" reading -
                # achieved, but only barely and at real cost, not a clean
                # failure. An earlier version of this function labeled the
                # reasoning "pyrrhic" while still returning verdict=False,
                # which contradicts the label (a pyrrhic victory is still a
                # victory) - fixed to return True with the qualification
                # made explicit via outcome_quality, after a real case
                # (see BIBLIOGRAPHY.md / commit history) played out exactly
                # this way: achieved, but by the narrowest possible margin,
                # only after real difficulty.
                verdict = True
                outcome_quality = "pyrrhic"
                path.append("applying hard aspect and the quesited significator is weak - "
                             "a pyrrhic outcome: achieved, but narrowly and at real cost, not a clean win")
    elif key_aspect and key_aspect["status"] == "separating":
        verdict = False
        outcome_quality = "no"
        path.append(f"only a separating {key_aspect['aspect_deg']} deg aspect (already past)")
    else:
        verdict = False
        outcome_quality = "no"
        path.append("no aspect in orb between the significators")

    if verdict is False and (tc["translations"] or tc["collections"]):
        verdict = True
        outcome_quality = "indirect"
        if tc["translations"]:
            t = tc["translations"][0]
            path.append(f"translation of light via {t['planet']} ({t['from']} -> {t['to']})")
        else:
            c = tc["collections"][0]
            path.append(f"collection of light via {c['planet']}")

    if verdict is False and reception and not (key_aspect and key_aspect["status"] == "applying"):
        verdict = True
        outcome_quality = "indirect"
        path.append("mutual reception between the significators, with no other applying aspect")

    voc_override = False
    if voc.get("void_of_course"):
        if verdict is not False:
            voc_override = True
        verdict = False
        outcome_quality = "no"
        path.append("Moon is void of course - overrides to a negative verdict regardless of the above")

    return {
        "key_aspect": key_aspect,
        "interruption": interruption,
        "translation_collection": tc,
        "mutual_reception": reception,
        "verdict": verdict,
        "outcome_quality": outcome_quality,
        "voc_override": voc_override,
        "reasoning_path": path,
    }
