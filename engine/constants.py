"""
Structural constants: which points/houses/angles kerykeion exposes, and the
zodiac sign ordering used to recompute sign fields after manually shifting
a point's absolute position (e.g. solar arc direction).

These are NOT meant to be tuned via .env - they reflect the shape of the
data model (what kerykeion returns), not astrological preferences. For
tunable settings (default house system, orb tables, luminary bonuses,
scan defaults, etc.) see config.py.
"""

DEFAULT_POINTS = [
    "sun", "moon", "mercury", "venus", "mars", "jupiter", "saturn",
    "uranus", "neptune", "pluto", "mean_node", "true_node", "chiron",
    "mean_lilith",
]

HOUSE_KEYS = [
    "first_house", "second_house", "third_house", "fourth_house",
    "fifth_house", "sixth_house", "seventh_house", "eighth_house",
    "ninth_house", "tenth_house", "eleventh_house", "twelfth_house",
]

ANGLE_KEYS = ["ascendant", "descendant", "medium_coeli", "imum_coeli"]

SIGN_ORDER = ["Ari", "Tau", "Gem", "Can", "Leo", "Vir", "Lib", "Sco", "Sag", "Cap", "Aqu", "Pis"]

LUMINARY_NAMES = {"sun", "moon"}
