"""Subject construction, serialization, and timezone helpers."""

from typing import Optional, List, Dict, Any
from datetime import datetime
from zoneinfo import ZoneInfo

from kerykeion import AstrologicalSubjectFactory

from .constants import DEFAULT_POINTS, HOUSE_KEYS, ANGLE_KEYS, SIGN_ORDER


def offset_minutes_to_tz_str(offset_minutes: int) -> str:
    """
    Converts a whole-hour UTC offset into a fixed IANA zone of the form Etc/GMT+-N.
    IMPORTANT: Etc/GMT sign convention is INVERTED relative to common usage:
    Etc/GMT-8 means UTC+8, and Etc/GMT+5 means UTC-5.
    Only works for whole-hour offsets. For half-hour/quarter-hour offsets,
    pass tz_str as an explicit IANA zone instead.
    """
    if offset_minutes % 60 != 0:
        raise ValueError(
            f"offset_minutes={offset_minutes} is not a multiple of 60 - "
            "Etc/GMT does not support half-hour offsets, pass tz_str directly"
        )
    hours = offset_minutes // 60
    sign = "-" if hours >= 0 else "+"
    return f"Etc/GMT{sign}{abs(hours)}"


def resolve_fixed_offset_minutes(tz_str: Optional[str], tz_offset_minutes: Optional[int],
                                  year: int, month: int, day: int,
                                  hour: int, minute: int, second: int) -> int:
    """Resolves a fixed UTC offset (in minutes) for a given civil datetime."""
    if tz_offset_minutes is not None:
        return tz_offset_minutes
    dt = datetime(year, month, day, hour, minute, second, tzinfo=ZoneInfo(tz_str))
    return int(dt.utcoffset().total_seconds() // 60)


def build_subject(
    name: str,
    year: int, month: int, day: int,
    hour: int, minute: int, second: int,
    lat: float, lng: float,
    tz_str: Optional[str] = None,
    tz_offset_minutes: Optional[int] = None,
    house_system: str = "P",
    zodiac_type: str = "Tropic",
):
    if tz_str is None and tz_offset_minutes is None:
        raise ValueError("Either tz_str or tz_offset_minutes must be provided")

    resolved_tz = tz_str if tz_str else offset_minutes_to_tz_str(tz_offset_minutes)
    tz_source = f"explicit:{tz_str}" if tz_str else f"offset_override:{tz_offset_minutes}min"

    subject = AstrologicalSubjectFactory.from_birth_data(
        name=name,
        year=year, month=month, day=day,
        hour=hour, minute=minute,
        lat=lat, lng=lng,
        tz_str=resolved_tz,
        houses_system_identifier=house_system,
        zodiac_type=zodiac_type,
        online=False,
    )
    return subject, resolved_tz, tz_source


def serialize_subject(subject, points: List[str], include_raw: bool = False) -> Dict[str, Any]:
    try:
        raw = subject.model_dump(mode="json")
    except AttributeError:
        raw = {k: v for k, v in vars(subject).items()}

    def dump_point(key: str):
        val = raw.get(key)
        if val is None:
            return None
        if isinstance(val, dict):
            return val
        try:
            return val.model_dump(mode="json")
        except AttributeError:
            return str(val)

    result = {
        "points": {p: dump_point(p) for p in points if dump_point(p) is not None},
        "houses": {h: dump_point(h) for h in HOUSE_KEYS if dump_point(h) is not None},
        "angles": {a: dump_point(a) for a in ANGLE_KEYS if dump_point(a) is not None},
    }
    if include_raw:
        result["raw"] = raw
    return result


def natal_points_dict(subject) -> Dict[str, Dict[str, Any]]:
    raw = subject.model_dump(mode="json")
    out = {}
    for key in DEFAULT_POINTS + ANGLE_KEYS:
        val = raw.get(key)
        if val is not None:
            out[key] = val
    return out


def subject_raw(subject) -> Dict[str, Any]:
    """Full pydantic dump of a subject - source of truth for any point lookup."""
    return subject.model_dump(mode="json")


def recompute_sign_fields(point_dict: Dict[str, Any], new_abs_pos: float) -> Dict[str, Any]:
    """
    After manually shifting a point's abs_pos (e.g. solar arc direction),
    the sign/sign_num/position fields do NOT update themselves - they must
    be recomputed from the new absolute longitude. Mutates and returns the
    same dict for convenience.
    """
    new_abs_pos = new_abs_pos % 360
    idx = int(new_abs_pos // 30)
    point_dict["abs_pos"] = new_abs_pos
    point_dict["position"] = new_abs_pos - idx * 30
    point_dict["sign"] = SIGN_ORDER[idx]
    point_dict["sign_num"] = idx
    return point_dict
