"""Aspect geometry and applying/separating/exact status."""

from typing import Dict, List, Any, Iterable


def angular_separation(pos_a: float, pos_b: float) -> float:
    """Shortest angular distance between two ecliptic longitudes, 0..180."""
    diff = abs(pos_a - pos_b) % 360
    return diff if diff <= 180 else 360 - diff


def aspect_status(moving_pos: float, moving_speed: float, target_pos: float,
                   aspect_deg: float, current_orb: float) -> str:
    """
    Determines applying / separating / exact by numerically projecting the
    moving point forward by a small time step and checking whether the orb
    shrinks or grows. Works uniformly for direct/retrograde motion and for
    solar arc (nominal forward speed).
    """
    if abs(current_orb) < 0.0167:  # under 1 arcminute counts as exact
        return "exact"
    dt = 1.0
    future_pos = (moving_pos + moving_speed * dt) % 360
    future_sep = angular_separation(future_pos, target_pos)
    future_orb = abs(future_sep - aspect_deg)
    if future_orb < current_orb:
        return "applying"
    elif future_orb > current_orb:
        return "separating"
    return "static"


def compute_aspects(
    computed_points: Dict[str, Dict[str, Any]],
    natal_points: Dict[str, Dict[str, Any]],
    aspect_set: Iterable[float],
    orb_table: Dict[float, float],
    luminary_bonus: float,
    luminary_names: Iterable[str],
) -> List[Dict[str, Any]]:
    results = []
    for name_a, pa in computed_points.items():
        pos_a = pa.get("abs_pos")
        speed_a = pa.get("speed", 0.0) or 0.0
        if pos_a is None:
            continue
        for name_b, pb in natal_points.items():
            pos_b = pb.get("abs_pos")
            if pos_b is None:
                continue
            sep = angular_separation(pos_a, pos_b)
            for asp_deg in aspect_set:
                allowed_orb = orb_table.get(asp_deg, 4.0)
                if name_a in luminary_names or name_b in luminary_names:
                    allowed_orb += luminary_bonus
                orb = abs(sep - asp_deg)
                if orb <= allowed_orb:
                    status = aspect_status(pos_a, speed_a, pos_b, asp_deg, orb)
                    results.append({
                        "point_a": name_a,
                        "point_b": name_b,
                        "aspect_deg": asp_deg,
                        "exact_orb": round(orb, 4),
                        "status": status,
                    })
    return results
