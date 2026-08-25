"""
Degree clustering rectification - two closely related documented methods
that share the same underlying mechanism (see BIBLIOGRAPHY.md):

- B. Israitel's "condensation method" (метод сгущений): for a large
  number of life events, write down the coordinates of TRANSITING
  planets on each event's date; find which zodiacal degrees recur most
  often across all of them. If a recurring degree has no natal planet
  sitting there, hypothesize an angular house cusp at that degree. The
  source states this only works once uncertainty is already down to
  20-30 minutes or less, and needs a large volume of events.

- B. Brady's "graphic rectification": ~15 ANGULAR life events
  (relationship/birth/death of close people specifically), positions of
  the slower planets (Mars through Pluto, plus the nodes - fast personal
  planets Sun/Moon/Mercury/Venus explicitly excluded as too imprecise/
  noisy for this purpose) rounded to the nearest degree, histogrammed;
  peaks with no natal planet there suggest an angular cusp.

Unlike the candidate-scanning tools elsewhere in this engine, this method
does NOT need a birth TIME at all to run - transiting planet positions
depend only on the event's own date, and natal slow-planet positions are
stable enough across a single day that only the birth DATE is needed to
compute them (this is also why Moon is excluded from the clustered set -
it moves too fast for a same-day approximation to be safe). The output is
a histogram of raw ecliptic degrees, not a time - converting a suggested
degree into an actual candidate birth time is a separate step (see
houses.py-style Ascendant-time search, exposed via find_time_for_ascendant
below).
"""

from typing import List, Dict, Any, Optional
from collections import Counter
from datetime import datetime

from .chart import build_subject
from .aspects import angular_separation

CLUSTERING_POINTS = ["mars", "jupiter", "saturn", "uranus", "neptune", "pluto", "mean_node", "true_node"]


def collect_transiting_degrees(
    events: List[Dict[str, Any]],
    round_to_deg: float = 1.0,
) -> List[Dict[str, Any]]:
    """
    events: list of {year, month, day, hour?, minute?, second?, lat?, lng?,
    tz_str?, tz_offset_minutes?} - one per life event. hour defaults to 12
    (noon) if not given, since these are slow planets and a single day's
    motion is well within round_to_deg for all but the fastest of them
    (Mars, at worst ~0.5 deg/day).

    Returns a flat list of {event_index, point, abs_pos_rounded} - the raw
    material; use build_degree_histogram to tally it.
    """
    records = []
    for i, ev in enumerate(events):
        tz_str = ev.get("tz_str")
        tz_offset = ev.get("tz_offset_minutes")
        if tz_str is None and tz_offset is None:
            tz_offset = 0
        subject, _, _ = build_subject(
            f"clustering_event_{i}", ev["year"], ev["month"], ev["day"],
            ev.get("hour", 12), ev.get("minute", 0), ev.get("second", 0),
            ev.get("lat", 0.0), ev.get("lng", 0.0), tz_str, tz_offset,
            "P", "Tropic",  # house system/zodiac irrelevant - only point longitudes used
        )
        raw = subject.model_dump(mode="json")
        for point in CLUSTERING_POINTS:
            if point in raw:
                deg = raw[point]["abs_pos"]
                rounded = round(deg / round_to_deg) * round_to_deg
                records.append({"event_index": i, "point": point, "abs_pos_rounded": rounded % 360})
    return records


def build_degree_histogram(
    records: List[Dict[str, Any]],
    natal_year: int, natal_month: int, natal_day: int,
    natal_lat: float, natal_lng: float,
    round_to_deg: float = 1.0,
    exclude_natal_occupied_deg_tolerance: float = 2.0,
) -> Dict[str, Any]:
    """
    Tallies how often each rounded degree recurs across records (from
    collect_transiting_degrees), then filters OUT any degree within
    exclude_natal_occupied_deg_tolerance of a natal slow-planet position
    (computed at noon on the birth date - Moon and personal planets are
    not checked here since this whole method already excludes them from
    the clustered set). Remaining peaks, sorted by raw frequency count
    (the count IS the method's own output per both sources - not an
    invented score - since "which degree recurs most often" is literally
    what condensation/graphic rectification looks for), are the
    candidates for an angular house cusp degree.
    """
    counts = Counter(r["abs_pos_rounded"] for r in records)

    natal_subject, _, _ = build_subject(
        "natal_reference", natal_year, natal_month, natal_day, 12, 0, 0,
        natal_lat, natal_lng, None, 0, "P", "Tropic",
    )
    natal_raw = natal_subject.model_dump(mode="json")
    natal_occupied_degrees = [natal_raw[p]["abs_pos"] for p in CLUSTERING_POINTS if p in natal_raw]

    def near_natal_planet(deg: float) -> bool:
        for occ in natal_occupied_degrees:
            if angular_separation(deg, occ) <= exclude_natal_occupied_deg_tolerance:
                return True
        return False

    peaks = []
    for deg, count in counts.most_common():
        if near_natal_planet(deg):
            continue
        peaks.append({"degree": deg, "count": count})

    return {
        "method": "degree_clustering",
        "source": "B. Israitel's condensation method / B. Brady's graphic rectification (see BIBLIOGRAPHY.md)",
        "total_events": len({r["event_index"] for r in records}),
        "total_data_points": len(records),
        "peaks_excluding_natal_planet_degrees": peaks,
        "note": (
            "peaks_excluding_natal_planet_degrees lists raw ecliptic degrees "
            "(0-360) where transiting slow planets recurred most often across "
            "the supplied events, with degrees already occupied by a natal slow "
            "planet filtered out. The count is the method's own frequency tally, "
            "not an invented score. Both sources caution this needs a LARGE "
            "number of events (Brady: ~15 events, 80-100 data points; Israitel: "
            "similarly large) and, per Israitel, is only reliable once birth-time "
            "uncertainty is already under 20-30 minutes - not a wide-open search "
            "tool. A resulting degree is a hypothesis for an ANGULAR house cusp; "
            "convert it to a candidate birth time with find_time_for_angle."
        ),
    }


def find_time_for_angle(
    target_deg: float,
    natal_year: int, natal_month: int, natal_day: int,
    natal_lat: float, natal_lng: float,
    fixed_offset_minutes: int,
    house_system: str = "P", zodiac_type: str = "Tropic",
    angle: str = "ascendant",
    start_hour: int = 12, start_minute: int = 0, start_second: int = 0,
    max_iterations: int = 20,
    tolerance_deg: float = 1e-4,
) -> Dict[str, Any]:
    """
    Direct solve (Newton-style, not a scan): finds the civil time on the
    given birth date at which the given angle (ascendant or medium_coeli)
    equals target_deg - i.e. converts a degree hypothesis from
    build_degree_histogram into an actual candidate birth time.
    """
    from datetime import timedelta

    guess_dt = datetime(natal_year, natal_month, natal_day, start_hour, start_minute, start_second)
    for _ in range(max_iterations):
        subj, _, _ = build_subject(
            "angle_search", guess_dt.year, guess_dt.month, guess_dt.day,
            guess_dt.hour, guess_dt.minute, guess_dt.second,
            natal_lat, natal_lng, None, fixed_offset_minutes, house_system, zodiac_type,
        )
        raw = subj.model_dump(mode="json")
        cur = raw[angle]["abs_pos"]
        speed = raw[angle]["speed"] or 360.0
        diff = (target_deg - cur + 180) % 360 - 180
        if abs(diff) < tolerance_deg:
            break
        delta_days = diff / speed
        guess_dt = guess_dt + timedelta(days=delta_days)

    return {
        "target_deg": target_deg,
        "angle": angle,
        "candidate_time": f"{guess_dt.hour:02d}:{guess_dt.minute:02d}:{guess_dt.second:02d}",
    }
