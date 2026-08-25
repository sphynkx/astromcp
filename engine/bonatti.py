"""
Guido Bonatti's method (via Jan Kefer, Prakticka Astrologie, 1939, section
2 - see BIBLIOGRAPHY.md): a minor, auxiliary rectification check the
source itself says to "use cautiously, always combined with another
correction" - not a primary technique.

Rule (quoted precisely, not paraphrased into something looser): look at
the Sun's condition.
1. If the Sun is NOT afflicted by Saturn, Uranus, or Mars (best case: not
   afflicted at all), then one of the four angles (Asc/Desc/MC/IC) is the
   MIDPOINT between the Sun and some planet.
2. If the Sun IS afflicted, then one of the four angles is in CONJUNCTION
   with some planet.

"Afflicted" is operationalized here as: the Sun forms a hard aspect
(conjunction/square/opposition) with Saturn, Uranus, or Mars, within the
given orb - a defensible, standard reading of "damaged", though the
source does not spell out an exact orb for this determination itself.
"""

from typing import Dict, Any, List

from .aspects import angular_separation
from .constants import DEFAULT_POINTS, ANGLE_KEYS

MALEFICS_FOR_AFFLICTION = ("saturn", "uranus", "mars")
HARD_ASPECTS = (0, 90, 180)


def is_sun_afflicted(natal_raw: Dict[str, Any], orb_deg: float = 8.0) -> bool:
    sun_pos = natal_raw["sun"]["abs_pos"]
    for malefic in MALEFICS_FOR_AFFLICTION:
        if malefic not in natal_raw:
            continue
        sep = angular_separation(sun_pos, natal_raw[malefic]["abs_pos"])
        for aspect_deg in HARD_ASPECTS:
            if abs(sep - aspect_deg) <= orb_deg:
                return True
    return False


def check_bonatti(
    natal_raw: Dict[str, Any],
    orb_deg: float = 1.0,
    affliction_orb_deg: float = 8.0,
    points: List[str] = DEFAULT_POINTS,
) -> Dict[str, Any]:
    """
    Checks Bonatti's rule against a single natal chart (one candidate birth
    time). Returns which case applies (afflicted vs not), and any angle/
    point pair(s) satisfying the corresponding condition within orb_deg.
    An empty matches list means the rule does not hold for this candidate.
    """
    afflicted = is_sun_afflicted(natal_raw, affliction_orb_deg)
    sun_pos = natal_raw["sun"]["abs_pos"]
    matches = []

    for angle_key in ANGLE_KEYS:
        if angle_key not in natal_raw:
            continue
        angle_pos = natal_raw[angle_key]["abs_pos"]

        if afflicted:
            for point in points:
                if point == "sun" or point not in natal_raw:
                    continue
                sep = angular_separation(angle_pos, natal_raw[point]["abs_pos"])
                if sep <= orb_deg:
                    matches.append({"angle": angle_key, "planet": point, "case": "conjunction", "orb": round(sep, 4)})
        else:
            for point in points:
                if point == "sun" or point not in natal_raw:
                    continue
                planet_pos = natal_raw[point]["abs_pos"]
                # Midpoint of Sun and planet - check both possible midpoints
                # (the shorter and longer arc between them both have a
                # midpoint 180 degrees apart; test both).
                diff = (planet_pos - sun_pos) % 360
                midpoint_a = (sun_pos + diff / 2) % 360
                midpoint_b = (midpoint_a + 180) % 360
                for midpoint in (midpoint_a, midpoint_b):
                    sep = angular_separation(angle_pos, midpoint)
                    if sep <= orb_deg:
                        matches.append({
                            "angle": angle_key, "planet": point, "case": "midpoint",
                            "midpoint_deg": round(midpoint, 4), "orb": round(sep, 4),
                        })

    return {
        "sun_afflicted": afflicted,
        "case_applied": "conjunction (Sun afflicted)" if afflicted else "midpoint (Sun unafflicted)",
        "matches": matches,
        "rule_holds": len(matches) > 0,
    }
