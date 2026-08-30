"""
Tool implementations (business logic). app.py wraps these as MCP tools via
@mcp.tool() decorators. This module has no dependency on the mcp/FastMCP
package itself, so it can in principle be tested or reused without a running
MCP server.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from . import config
from . import horary
from . import lots
from . import houses as houses_module
from .chart import build_subject, serialize_subject, natal_points_dict, subject_raw, resolve_fixed_offset_minutes
from .aspects import compute_aspects
from .techniques import (
    technique_transit, technique_secondary_progression, technique_solar_arc,
    technique_solar_return, technique_profection,
    technique_primary_direction_zodiacal, technique_relocated_transit,
)
from .scan import run_scan
from .trutina import run_trutina_hermetis
from .criteria import run_three_movements_scan, run_timoshenko_scan, run_bonatti_scan, run_herich_scan
from .clustering import collect_transiting_degrees, build_degree_histogram, find_time_for_angle
from .help import get_help
from .constants import DEFAULT_POINTS, LUMINARY_NAMES, HOUSE_KEYS
from .display import print_chart_result, print_technique_result, print_scan_result
from .jobs import submit_job, get_job

logger = logging.getLogger("astromcp")

HORARY_PLANET_NAMES = ["sun", "moon", "mercury", "venus", "mars", "jupiter",
                        "saturn", "uranus", "neptune", "pluto"]
# Max look-ahead when building the "future" snapshot used for refranation
# detection (engine/horary.py:check_interruption). A key aspect that
# wouldn't perfect for months is already well past the "next aspect"
# scope horary judgment concerns itself with (see Frawley, quoted in
# horary.py's module docstring) - past this cap, the future snapshot is
# simply skipped rather than built for an ever-growing offset.
HORARY_FUTURE_SNAPSHOT_MAX_DAYS = 40.0


def horary_chart(
    year: int, month: int, day: int,
    hour: int, minute: int, second: int = 0,
    lat: float = 0.0, lng: float = 0.0,
    tz_str: Optional[str] = None,
    tz_offset_minutes: Optional[int] = None,
    house_system: Optional[str] = None,
    zodiac_type: Optional[str] = None,
    question: str = "",
    quesited_house: Optional[int] = None,
    derived_house_chain: Optional[List[int]] = None,
    derived_house_labels: Optional[List[str]] = None,
    is_self_query: bool = False,
) -> Dict[str, Any]:
    """
    Builds and judges a horary chart. See help_texts/horary.md for the
    full methodology this implements - this docstring covers only the
    calling contract.

    house_system defaults to Placidus ("P") - horary's own conventional
    default (see horar_wri_gl01.txt), independent of
    config.DEFAULT_HOUSE_SYSTEM which is tuned for rectification work.
    Regiomontanus ("R") is the classical Lilly-era alternative, also
    supported.

    quesited_house - the house (1-12) representing the matter asked
    about, when the question is about the querent directly or about
    something with an immediate, undisputed house (money=2, siblings=3,
    health=6, marriage=7, ...). See help_texts/horary.md's house-meaning
    table for the standard assignments.

    derived_house_chain - instead of quesited_house, for a question about
    a THIRD PARTY (the querent's brother's dog, a friend's job, etc):
    the sequence of house numbers for each hop from the querent outward,
    per the derived-house method (e.g. a full brother's dog is [6, 3] -
    the dog(6th) of the brother(3rd)). derived_house_labels is an
    optional same-length list of human-readable labels for each hop
    (e.g. ["brother", "dog"]) purely echoed back in the output for
    traceability - it plays no role in the arithmetic. The resolved
    house and the chain that produced it are both returned explicitly,
    per the methodology's own requirement that the model use this
    number as given rather than recompute the chain itself.

    is_self_query - True if the astrologer is judging their own
    question (changes which house the secondary radicality checks and
    "quesited house" default examine - see help_texts/horary.md section 1).
    """
    house_system = house_system or "P"
    zodiac_type = zodiac_type or config.DEFAULT_ZODIAC_TYPE
    try:
        if derived_house_chain:
            derivation = horary.derived_house(derived_house_chain)
            if derived_house_labels:
                derivation["labels"] = derived_house_labels
            q_house = derivation["resolved_house"]
        elif quesited_house is not None:
            derivation = None
            q_house = quesited_house
        else:
            return {"error": "either quesited_house or derived_house_chain must be given"}
        if not (1 <= q_house <= 12):
            return {"error": f"resolved quesited house {q_house} is out of range 1-12"}

        subject, resolved_tz, tz_source = build_subject(
            "horary", year, month, day, hour, minute, second,
            lat, lng, tz_str, tz_offset_minutes, house_system, zodiac_type,
        )
        raw = subject_raw(subject)

        planets = {p: raw[p] for p in HORARY_PLANET_NAMES if raw.get(p) is not None}
        pof = lots.compute_lot("part_of_fortune", raw)
        cof = lots.compute_lot("cross_of_fate", raw)
        all_points = dict(planets)
        all_points["part_of_fortune"] = pof
        all_points["cross_of_fate"] = cof

        cusps = {i: raw[HOUSE_KEYS[i - 1]]["abs_pos"] for i in range(1, 13)}

        def house_rulers_for(house_num: int):
            if house_num in horary.ANGULAR_HOUSES:
                return horary.house_rulers(horary.sign_idx(cusps[house_num]))
            next_house = house_num + 1 if house_num < 12 else 1
            return horary.house_ruler_by_majority(cusps[house_num], cusps[next_house])

        querent_primary, querent_secondary = house_rulers_for(1)
        quesited_primary, quesited_secondary = house_rulers_for(q_house)
        fourth_primary, fourth_secondary = house_rulers_for(4)

        # Full aspect grid (planets + Part of Fortune + Cross of Fate) using
        # horary's own aspect set/orb convention - general supplementary
        # info, and what assess_significator cites aspects from.
        full_aspects = compute_aspects(
            all_points, all_points, horary.HORARY_ASPECTS, horary.HORARY_ORB_TABLE,
            horary.HORARY_LUMINARY_BONUS, horary.LUMINARIES,
        )
        # de-duplicate the symmetric (a,b)/(b,a) pairs compute_aspects
        # produces when computed_points and natal_points are the same dict
        seen = set()
        deduped_aspects = []
        for asp in full_aspects:
            if asp["point_a"] == asp["point_b"]:
                continue
            fkey = (frozenset((asp["point_a"], asp["point_b"])), asp["aspect_deg"])
            if fkey in seen:
                continue
            seen.add(fkey)
            deduped_aspects.append(asp)
        full_aspects = deduped_aspects

        def aspects_for(name):
            return [a for a in full_aspects if a["point_a"] == name or a["point_b"] == name]

        def house_of(name):
            return horary.house_number_from_field(all_points[name].get("house"))

        querent_assessment = horary.assess_significator(
            querent_primary, all_points[querent_primary], house_of(querent_primary),
            all_points, aspects_for(querent_primary),
        )
        quesited_assessment = horary.assess_significator(
            quesited_primary, all_points[quesited_primary], house_of(quesited_primary),
            all_points, aspects_for(quesited_primary),
        )
        moon_assessment = horary.assess_significator(
            "moon", all_points["moon"], house_of("moon"), all_points, aspects_for("moon"),
        )
        fourth_assessment = horary.assess_significator(
            fourth_primary, all_points[fourth_primary], house_of(fourth_primary),
            all_points, aspects_for(fourth_primary),
        )
        querent_secondary_assessment = None
        if querent_secondary:
            querent_secondary_assessment = horary.assess_significator(
                querent_secondary, all_points[querent_secondary], house_of(querent_secondary),
                all_points, aspects_for(querent_secondary),
            )
        quesited_secondary_assessment = None
        if quesited_secondary:
            quesited_secondary_assessment = horary.assess_significator(
                quesited_secondary, all_points[quesited_secondary], house_of(quesited_secondary),
                all_points, aspects_for(quesited_secondary),
            )

        reception = horary.mutual_reception(
            all_points[querent_primary], all_points[quesited_primary], querent_primary, quesited_primary,
        )

        voc = horary.moon_forward_aspects(all_points["moon"], all_points)

        # Refranation needs a real future ephemeris snapshot - see
        # horary.check_interruption's docstring for why a linear guess
        # from current speed alone isn't reliable near a station.
        key_asp = horary.key_aspect_between(
            querent_primary, all_points[querent_primary], quesited_primary, all_points[quesited_primary],
        )
        future_points = None
        if key_asp and key_asp["status"] == "applying":
            rel_speed = (all_points[querent_primary].get("speed", 0.0) or 0.0) - \
                        (all_points[quesited_primary].get("speed", 0.0) or 0.0)
            if rel_speed != 0:
                days = abs(key_asp["exact_orb"]) / abs(rel_speed)
                if 0 < days <= HORARY_FUTURE_SNAPSHOT_MAX_DAYS:
                    future_dt = datetime(year, month, day, hour, minute, second) + timedelta(days=days)
                    future_subject, _, _ = build_subject(
                        "horary_future", future_dt.year, future_dt.month, future_dt.day,
                        future_dt.hour, future_dt.minute, future_dt.second,
                        lat, lng, tz_str, tz_offset_minutes, house_system, zodiac_type,
                    )
                    future_raw = subject_raw(future_subject)
                    future_points = {
                        name: future_raw[name] for name in (querent_primary, quesited_primary)
                        if future_raw.get(name) is not None
                    }

        verdict = horary.compute_verdict(
            querent_primary, all_points[querent_primary],
            quesited_primary, all_points[quesited_primary],
            {k: v for k, v in all_points.items() if k not in ("part_of_fortune", "cross_of_fate")},
            querent_assessment, quesited_assessment, reception, voc, future_points,
        )

        # Radicality
        asc_abs = raw["ascendant"]["abs_pos"]
        target_house = 1 if is_self_query else 7
        relevant_angle_sign_idx = horary.sign_idx(cusps[target_house])
        saturn_house = house_of("saturn")
        saturn_aspects_to_target = []
        for name, pt in all_points.items():
            if name in ("saturn", "part_of_fortune", "cross_of_fate"):
                continue
            if house_of(name) != target_house:
                continue
            asp = horary.key_aspect_between("saturn", all_points["saturn"], name, pt)
            if asp:
                saturn_aspects_to_target.append(asp)
        radicality = horary.check_radicality(
            asc_abs, all_points["moon"]["abs_pos"], relevant_angle_sign_idx,
            saturn_house, saturn_aspects_to_target, is_self_query,
        )

        result = {
            "question": question,
            "is_self_query": is_self_query,
            "quesited_house": q_house,
            "derived_house": derivation,
            "radicality": radicality,
            "significators": {
                "querent": {
                    "house": 1,
                    "primary_ruler": querent_assessment,
                    "secondary_ruler": querent_secondary_assessment,
                    "co_significator_moon": moon_assessment,
                },
                "quesited": {
                    "house": q_house,
                    "primary_ruler": quesited_assessment,
                    "secondary_ruler": quesited_secondary_assessment,
                },
                "fourth_house_ruler": fourth_assessment,
            },
            "mutual_reception": reception,
            "void_of_course_moon": voc,
            "verdict": verdict,
            "final_answer": "yes" if verdict["verdict"] else "no",
            "aspects": full_aspects,
            "points": {k: v for k, v in all_points.items()},
            "houses": {i: {"abs_pos": cusps[i]} for i in range(1, 13)},
            "meta": {
                "tz_used": resolved_tz,
                "tz_source": tz_source,
                "house_system": house_system,
                "zodiac_type": zodiac_type,
                "input_datetime": f"{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:{second:02d}",
            },
        }
        if config.CONSOLE_RESULT_PREVIEW:
            logger.info(
                "  horary: verdict=%s radical=%s querent=%s(%s) quesited=%s(%s house %d)",
                result["final_answer"], radicality["radical"],
                querent_primary, querent_assessment["strength"],
                quesited_primary, quesited_assessment["strength"], q_house,
            )
        return result
    except Exception as e:
        logger.exception("horary_chart failed")
        return {"error": str(e)}


def rectif_chart(
    year: int, month: int, day: int,
    hour: int, minute: int, second: int = 0,
    lat: float = 0.0, lng: float = 0.0,
    tz_str: Optional[str] = None,
    tz_offset_minutes: Optional[int] = None,
    house_system: Optional[str] = None,
    zodiac_type: Optional[str] = None,
    points: Optional[List[str]] = None,
    include_raw: bool = False,
    name: str = "subject",
) -> Dict[str, Any]:
    house_system = house_system or config.DEFAULT_HOUSE_SYSTEM
    zodiac_type = zodiac_type or config.DEFAULT_ZODIAC_TYPE
    try:
        subject, resolved_tz, tz_source = build_subject(
            name, year, month, day, hour, minute, second,
            lat, lng, tz_str, tz_offset_minutes, house_system, zodiac_type,
        )
        pts = points if points else DEFAULT_POINTS
        data = serialize_subject(subject, pts, include_raw)
        data["meta"] = {
            "tz_used": resolved_tz,
            "tz_source": tz_source,
            "house_system": house_system,
            "zodiac_type": zodiac_type,
            "input_datetime": f"{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:{second:02d}",
        }
        if config.CONSOLE_RESULT_PREVIEW:
            print_chart_result(data)
        return data
    except Exception as e:
        logger.exception("rectif_chart failed")
        return {"error": str(e)}


def rectif_chart_batch(requests: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    results = []
    for i, req in enumerate(requests):
        try:
            results.append(rectif_chart(**req))
        except Exception as e:
            logger.exception(f"rectif_chart_batch item {i} failed")
            results.append({"error": str(e), "index": i})
    return results


def rectif_technique(
    natal_year: int, natal_month: int, natal_day: int,
    natal_hour: int, natal_minute: int, natal_second: int,
    natal_lat: float, natal_lng: float,
    natal_tz_str: Optional[str] = None,
    natal_tz_offset_minutes: Optional[int] = None,
    house_system: Optional[str] = None,
    zodiac_type: Optional[str] = None,
    technique: str = "transit",
    target_year: int = 2000, target_month: int = 1, target_day: int = 1,
    target_hour: int = 12, target_minute: int = 0, target_second: int = 0,
    angle_method: str = "solar_arc_naibod",
    event_lat: Optional[float] = None, event_lng: Optional[float] = None,
    event_tz_str: Optional[str] = None, event_tz_offset_minutes: Optional[int] = None,
    compute_aspects_flag: bool = True,
    aspect_set: Optional[List[float]] = None,
    orb_table: Optional[Dict[str, float]] = None,
    luminary_orb_bonus: Optional[float] = None,
    relocate_lat: Optional[float] = None, relocate_lng: Optional[float] = None,
) -> Dict[str, Any]:
    house_system = house_system or config.DEFAULT_HOUSE_SYSTEM
    zodiac_type = zodiac_type or config.DEFAULT_ZODIAC_TYPE
    try:
        natal_subject, resolved_tz, tz_source = build_subject(
            "natal", natal_year, natal_month, natal_day, natal_hour, natal_minute, natal_second,
            natal_lat, natal_lng, natal_tz_str, natal_tz_offset_minutes, house_system, zodiac_type,
        )
        n_raw = subject_raw(natal_subject)
        n_points = natal_points_dict(natal_subject)

        if technique == "secondary_progression":
            fixed_offset = resolve_fixed_offset_minutes(
                natal_tz_str, natal_tz_offset_minutes,
                natal_year, natal_month, natal_day, natal_hour, natal_minute, natal_second,
            )
            computed, natal_pts, meta = technique_secondary_progression(
                natal_year, natal_month, natal_day, natal_hour, natal_minute, natal_second,
                natal_lat, natal_lng, fixed_offset, house_system, zodiac_type,
                n_raw, n_points, target_year, target_month, target_day, angle_method,
            )
        elif technique == "solar_arc":
            fixed_offset = resolve_fixed_offset_minutes(
                natal_tz_str, natal_tz_offset_minutes,
                natal_year, natal_month, natal_day, natal_hour, natal_minute, natal_second,
            )
            computed, natal_pts, meta = technique_solar_arc(
                natal_year, natal_month, natal_day, natal_hour, natal_minute, natal_second,
                natal_lat, natal_lng, fixed_offset, house_system, zodiac_type,
                n_raw, n_points, target_year, target_month, target_day,
            )
        elif technique == "solar_return":
            computed, natal_pts, meta = technique_solar_return(
                natal_month, natal_day,
                n_raw, n_points,
                house_system, zodiac_type,
                target_year,
                event_lat if event_lat is not None else natal_lat,
                event_lng if event_lng is not None else natal_lng,
            )
        elif technique == "profection":
            ev_tz_str = event_tz_str
            ev_tz_off = event_tz_offset_minutes
            if ev_tz_str is None and ev_tz_off is None:
                ev_tz_str, ev_tz_off = natal_tz_str, natal_tz_offset_minutes
            computed, natal_pts, meta = technique_profection(
                natal_year, natal_month, natal_day,
                n_raw, n_points, house_system, zodiac_type,
                target_year, target_month, target_day, target_hour, target_minute, target_second,
                event_lat if event_lat is not None else natal_lat,
                event_lng if event_lng is not None else natal_lng,
                ev_tz_str, ev_tz_off,
            )
        elif technique == "primary_direction_zodiacal":
            computed, natal_pts, meta = technique_primary_direction_zodiacal(
                natal_year, natal_month, natal_day,
                n_raw, n_points, target_year, target_month, target_day,
            )
        elif technique == "relocated_transit":
            fixed_offset = resolve_fixed_offset_minutes(
                natal_tz_str, natal_tz_offset_minutes,
                natal_year, natal_month, natal_day, natal_hour, natal_minute, natal_second,
            )
            computed, natal_pts, meta = technique_relocated_transit(
                natal_year, natal_month, natal_day, natal_hour, natal_minute, natal_second,
                fixed_offset,
                relocate_lat if relocate_lat is not None else (event_lat if event_lat is not None else natal_lat),
                relocate_lng if relocate_lng is not None else (event_lng if event_lng is not None else natal_lng),
                house_system, zodiac_type,
                target_year, target_month, target_day, target_hour, target_minute, target_second,
                event_lat if event_lat is not None else natal_lat,
                event_lng if event_lng is not None else natal_lng,
                event_tz_str, event_tz_offset_minutes,
            )
        elif technique == "transit":
            ev_tz_str = event_tz_str
            ev_tz_off = event_tz_offset_minutes
            if ev_tz_str is None and ev_tz_off is None:
                ev_tz_str, ev_tz_off = natal_tz_str, natal_tz_offset_minutes
            computed, natal_pts, meta = technique_transit(
                n_raw, n_points,
                target_year, target_month, target_day, target_hour, target_minute, target_second,
                event_lat if event_lat is not None else natal_lat,
                event_lng if event_lng is not None else natal_lng,
                ev_tz_str, ev_tz_off, house_system, zodiac_type,
            )
        else:
            return {"error": f"Unknown technique: {technique}"}

        result = {
            "technique": technique,
            "computed_points": computed,
            "natal_points_echo": natal_pts,
            "meta": meta,
        }

        if compute_aspects_flag:
            asp_set = aspect_set if aspect_set else config.DEFAULT_ASPECT_SET

            if orb_table:
                orb_tbl = {float(k): v for k, v in orb_table.items()}
            elif technique in ("transit", "solar_return", "profection", "relocated_transit"):
                orb_tbl = config.DEFAULT_ORB_TABLE_TRANSIT
            else:
                orb_tbl = config.DEFAULT_ORB_TABLE_DIRECTION

            if luminary_orb_bonus is not None:
                bonus = luminary_orb_bonus
            elif technique in ("transit", "solar_return", "profection", "relocated_transit"):
                bonus = config.LUMINARY_ORB_BONUS_TRANSIT
            else:
                bonus = config.LUMINARY_ORB_BONUS_DIRECTION

            result["aspects"] = compute_aspects(computed, natal_pts, asp_set, orb_tbl, bonus, LUMINARY_NAMES)

        if config.CONSOLE_RESULT_PREVIEW:
            print_technique_result(result)
        return result
    except Exception as e:
        logger.exception("rectif_technique failed")
        return {"error": str(e)}


def rectif_technique_batch(requests: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    results = []
    for i, req in enumerate(requests):
        try:
            results.append(rectif_technique(**req))
        except Exception as e:
            logger.exception(f"rectif_technique_batch item {i} failed")
            results.append({"error": str(e), "index": i})
    return results


def rectif_scan(
    natal_year: int, natal_month: int, natal_day: int,
    natal_lat: float, natal_lng: float,
    natal_tz_str: Optional[str] = None,
    natal_tz_offset_minutes: Optional[int] = None,
    house_system: Optional[str] = None,
    zodiac_type: Optional[str] = None,
    scan_start_hour: int = 0, scan_start_minute: int = 0,
    scan_end_hour: int = 23, scan_end_minute: int = 59,
    step_minutes: int = 2,
    events: Optional[List[Dict[str, Any]]] = None,
    target_points: Optional[List[str]] = None,
    aspect_set: Optional[List[float]] = None,
    orb_threshold: Optional[float] = None,
    top_n: int = 20,
    include_full_table: bool = False,
    scan_start_second: int = 0,
    scan_end_second: int = 59,
    step_seconds: Optional[int] = None,
) -> Dict[str, Any]:
    house_system = house_system or config.DEFAULT_HOUSE_SYSTEM
    zodiac_type = zodiac_type or config.DEFAULT_ZODIAC_TYPE
    try:
        if not events:
            return {"error": "events list is required and must be non-empty"}
        result = run_scan(
            natal_year, natal_month, natal_day, natal_lat, natal_lng,
            natal_tz_str, natal_tz_offset_minutes, house_system, zodiac_type,
            scan_start_hour, scan_start_minute, scan_end_hour, scan_end_minute,
            step_minutes, events,
            target_points=target_points,
            aspect_set=aspect_set,
            orb_threshold=orb_threshold,
            top_n=top_n,
            include_full_table=include_full_table,
            scan_start_second=scan_start_second,
            scan_end_second=scan_end_second,
            step_seconds=step_seconds,
        )
        if config.CONSOLE_RESULT_PREVIEW:
            print_scan_result(result)
        return result
    except Exception as e:
        logger.exception("rectif_scan failed")
        return {"error": str(e)}


def rectif_scan_start(
    natal_year: int, natal_month: int, natal_day: int,
    natal_lat: float, natal_lng: float,
    natal_tz_str: Optional[str] = None,
    natal_tz_offset_minutes: Optional[int] = None,
    house_system: Optional[str] = None,
    zodiac_type: Optional[str] = None,
    scan_start_hour: int = 0, scan_start_minute: int = 0,
    scan_end_hour: int = 23, scan_end_minute: int = 59,
    step_minutes: int = 2,
    events: Optional[List[Dict[str, Any]]] = None,
    target_points: Optional[List[str]] = None,
    aspect_set: Optional[List[float]] = None,
    orb_threshold: Optional[float] = None,
    top_n: int = 20,
    include_full_table: bool = False,
    scan_start_second: int = 0,
    scan_end_second: int = 59,
    step_seconds: Optional[int] = None,
) -> Dict[str, Any]:
    house_system = house_system or config.DEFAULT_HOUSE_SYSTEM
    zodiac_type = zodiac_type or config.DEFAULT_ZODIAC_TYPE
    if not events:
        return {"error": "events list is required and must be non-empty"}
    job_id = submit_job(
        run_scan,
        natal_year, natal_month, natal_day, natal_lat, natal_lng,
        natal_tz_str, natal_tz_offset_minutes, house_system, zodiac_type,
        scan_start_hour, scan_start_minute, scan_end_hour, scan_end_minute,
        step_minutes, events,
        target_points=target_points,
        aspect_set=aspect_set,
        orb_threshold=orb_threshold,
        top_n=top_n,
        include_full_table=include_full_table,
        scan_start_second=scan_start_second,
        scan_end_second=scan_end_second,
        step_seconds=step_seconds,
    )
    logger.info(f"astromcp: scan job {job_id} submitted ({len(events)} events)")
    return {"job_id": job_id, "status": "running"}


def rectif_scan_result(job_id: str) -> Dict[str, Any]:
    result = get_job(job_id)
    if config.CONSOLE_RESULT_PREVIEW and result.get("status") == "done":
        print_scan_result(result["result"])
    return result


def rectif_trutina(
    natal_year: int, natal_month: int, natal_day: int,
    natal_lat: float, natal_lng: float,
    natal_tz_str: Optional[str] = None,
    natal_tz_offset_minutes: Optional[int] = None,
    house_system: Optional[str] = None,
    zodiac_type: Optional[str] = None,
    initial_guess_hour: int = 12, initial_guess_minute: int = 0, initial_guess_second: int = 0,
    max_iterations: int = 30,
    mother_year: Optional[int] = None, mother_month: Optional[int] = None, mother_day: Optional[int] = None,
    mother_hour: Optional[int] = None, mother_minute: Optional[int] = None, mother_second: Optional[int] = None,
    mother_lat: Optional[float] = None, mother_lng: Optional[float] = None,
    mother_tz_str: Optional[str] = None, mother_tz_offset_minutes: Optional[int] = None,
) -> Dict[str, Any]:
    house_system = house_system or config.DEFAULT_HOUSE_SYSTEM
    zodiac_type = zodiac_type or config.DEFAULT_ZODIAC_TYPE
    try:
        result = run_trutina_hermetis(
            natal_year, natal_month, natal_day, natal_lat, natal_lng,
            natal_tz_str, natal_tz_offset_minutes, house_system, zodiac_type,
            initial_guess_hour, initial_guess_minute, initial_guess_second,
            max_iterations,
            mother_year, mother_month, mother_day,
            mother_hour, mother_minute, mother_second,
            mother_lat, mother_lng, mother_tz_str, mother_tz_offset_minutes,
        )
        if config.CONSOLE_RESULT_PREVIEW:
            for key, branch in result.items():
                if isinstance(branch, dict) and "rectified_hour" in branch:
                    logger.info(
                        "  trutina %s: %02d:%02d:%02d (converged=%s, cycle=%s)",
                        key, branch["rectified_hour"], branch["rectified_minute"],
                        branch["rectified_second"], branch["converged"], branch["cycle_detected"],
                    )
        return result
    except Exception as e:
        logger.exception("rectif_trutina failed")
        return {"error": str(e)}


def rectif_movements_scan(
    natal_year: int, natal_month: int, natal_day: int,
    natal_lat: float, natal_lng: float,
    natal_tz_str: Optional[str] = None,
    natal_tz_offset_minutes: Optional[int] = None,
    house_system: Optional[str] = None,
    zodiac_type: Optional[str] = None,
    scan_start_hour: int = 0, scan_start_minute: int = 0,
    scan_end_hour: int = 23, scan_end_minute: int = 59,
    step_minutes: int = 2,
    target_year: int = 2000, target_month: int = 1, target_day: int = 1,
    target_houses: Optional[List[int]] = None,
    target_points: Optional[List[str]] = None,
    direction_orb_deg: float = 1.0,
    transit_orb_deg: float = 3.0,
    scan_start_second: int = 0, scan_end_second: int = 59,
    step_seconds: Optional[int] = None,
) -> Dict[str, Any]:
    house_system = house_system or config.DEFAULT_HOUSE_SYSTEM
    zodiac_type = zodiac_type or config.DEFAULT_ZODIAC_TYPE
    try:
        result = run_three_movements_scan(
            natal_year, natal_month, natal_day, natal_lat, natal_lng,
            natal_tz_str, natal_tz_offset_minutes, house_system, zodiac_type,
            scan_start_hour, scan_start_minute, scan_end_hour, scan_end_minute,
            step_minutes, target_year, target_month, target_day,
            target_houses, target_points, direction_orb_deg, transit_orb_deg,
            scan_start_second, scan_end_second, step_seconds,
        )
        if config.CONSOLE_RESULT_PREVIEW:
            logger.info(
                "  three_movements: %d/%d candidates qualify (>=2 of 3), %d windows",
                result["candidates_qualifying_raw_count"], result["candidates_tested"],
                len(result["qualifying_windows"]),
            )
        return result
    except Exception as e:
        logger.exception("rectif_movements_scan failed")
        return {"error": str(e)}


def rectif_timoshenko_scan(
    natal_year: int, natal_month: int, natal_day: int,
    natal_lat: float, natal_lng: float,
    natal_tz_str: Optional[str] = None,
    natal_tz_offset_minutes: Optional[int] = None,
    house_system: Optional[str] = None,
    zodiac_type: Optional[str] = None,
    scan_start_hour: int = 0, scan_start_minute: int = 0,
    scan_end_hour: int = 23, scan_end_minute: int = 59,
    step_minutes: int = 2,
    target_year: int = 2000, target_month: int = 1, target_day: int = 1,
    house_num: int = 1,
    orb_deg: float = 1.0,
    scan_start_second: int = 0, scan_end_second: int = 59,
    step_seconds: Optional[int] = None,
) -> Dict[str, Any]:
    house_system = house_system or config.DEFAULT_HOUSE_SYSTEM
    zodiac_type = zodiac_type or config.DEFAULT_ZODIAC_TYPE
    try:
        result = run_timoshenko_scan(
            natal_year, natal_month, natal_day, natal_lat, natal_lng,
            natal_tz_str, natal_tz_offset_minutes, house_system, zodiac_type,
            scan_start_hour, scan_start_minute, scan_end_hour, scan_end_minute,
            step_minutes, target_year, target_month, target_day, house_num, orb_deg,
            scan_start_second, scan_end_second, step_seconds,
        )
        if config.CONSOLE_RESULT_PREVIEW:
            logger.info(
                "  timoshenko: %d/%d candidates qualify (all 4 conditions), %d windows",
                result["candidates_qualifying_raw_count"], result["candidates_tested"],
                len(result["qualifying_windows"]),
            )
        return result
    except Exception as e:
        logger.exception("rectif_timoshenko_scan failed")
        return {"error": str(e)}


def rectif_bonatti_scan(
    natal_year: int, natal_month: int, natal_day: int,
    natal_lat: float, natal_lng: float,
    natal_tz_str: Optional[str] = None,
    natal_tz_offset_minutes: Optional[int] = None,
    house_system: Optional[str] = None,
    zodiac_type: Optional[str] = None,
    scan_start_hour: int = 0, scan_start_minute: int = 0,
    scan_end_hour: int = 23, scan_end_minute: int = 59,
    step_minutes: int = 2,
    orb_deg: float = 1.0,
    affliction_orb_deg: float = 8.0,
    scan_start_second: int = 0, scan_end_second: int = 59,
    step_seconds: Optional[int] = None,
) -> Dict[str, Any]:
    house_system = house_system or config.DEFAULT_HOUSE_SYSTEM
    zodiac_type = zodiac_type or config.DEFAULT_ZODIAC_TYPE
    try:
        result = run_bonatti_scan(
            natal_year, natal_month, natal_day, natal_lat, natal_lng,
            natal_tz_str, natal_tz_offset_minutes, house_system, zodiac_type,
            scan_start_hour, scan_start_minute, scan_end_hour, scan_end_minute,
            step_minutes, orb_deg, affliction_orb_deg,
            scan_start_second, scan_end_second, step_seconds,
        )
        if config.CONSOLE_RESULT_PREVIEW:
            logger.info(
                "  bonatti: %d/%d candidates qualify, %d windows",
                result["candidates_qualifying_raw_count"], result["candidates_tested"],
                len(result["qualifying_windows"]),
            )
        return result
    except Exception as e:
        logger.exception("rectif_bonatti_scan failed")
        return {"error": str(e)}


def rectif_degree_clustering(
    events: List[Dict[str, Any]],
    natal_year: int, natal_month: int, natal_day: int,
    natal_lat: float, natal_lng: float,
    natal_tz_str: Optional[str] = None,
    natal_tz_offset_minutes: Optional[int] = None,
    house_system: Optional[str] = None,
    zodiac_type: Optional[str] = None,
    round_to_deg: float = 1.0,
    exclude_natal_occupied_deg_tolerance: float = 2.0,
    top_n: int = 10,
    convert_top_peaks_to_times: bool = True,
) -> Dict[str, Any]:
    house_system = house_system or config.DEFAULT_HOUSE_SYSTEM
    zodiac_type = zodiac_type or config.DEFAULT_ZODIAC_TYPE
    try:
        records = collect_transiting_degrees(events, round_to_deg)
        histogram = build_degree_histogram(
            records, natal_year, natal_month, natal_day, natal_lat, natal_lng,
            round_to_deg, exclude_natal_occupied_deg_tolerance,
        )
        top_peaks = histogram["peaks_excluding_natal_planet_degrees"][:top_n]

        if convert_top_peaks_to_times and top_peaks:
            fixed_offset = resolve_fixed_offset_minutes(
                natal_tz_str, natal_tz_offset_minutes,
                natal_year, natal_month, natal_day, 12, 0, 0,
            )
            for peak in top_peaks:
                peak["as_ascendant_time"] = find_time_for_angle(
                    peak["degree"], natal_year, natal_month, natal_day,
                    natal_lat, natal_lng, fixed_offset, house_system, zodiac_type, "ascendant",
                )["candidate_time"]
                peak["as_medium_coeli_time"] = find_time_for_angle(
                    peak["degree"], natal_year, natal_month, natal_day,
                    natal_lat, natal_lng, fixed_offset, house_system, zodiac_type, "medium_coeli",
                )["candidate_time"]

        histogram["peaks_excluding_natal_planet_degrees"] = top_peaks
        if config.CONSOLE_RESULT_PREVIEW:
            logger.info(
                "  degree_clustering: %d events, %d peaks (top %d shown)",
                histogram["total_events"], len(records), len(top_peaks),
            )
        return histogram
    except Exception as e:
        logger.exception("rectif_degree_clustering failed")
        return {"error": str(e)}


def rectif_herich_scan(
    natal_year: int, natal_month: int, natal_day: int,
    natal_lat: float, natal_lng: float,
    natal_tz_str: Optional[str] = None,
    natal_tz_offset_minutes: Optional[int] = None,
    house_system: Optional[str] = None,
    zodiac_type: Optional[str] = None,
    scan_start_hour: int = 0, scan_start_minute: int = 0,
    scan_end_hour: int = 23, scan_end_minute: int = 59,
    step_minutes: int = 2,
    orb_deg: float = 8.0,
    check_all_house_cusps: bool = False,
    scan_start_second: int = 0, scan_end_second: int = 59,
    step_seconds: Optional[int] = None,
) -> Dict[str, Any]:
    house_system = house_system or config.DEFAULT_HOUSE_SYSTEM
    zodiac_type = zodiac_type or config.DEFAULT_ZODIAC_TYPE
    try:
        result = run_herich_scan(
            natal_year, natal_month, natal_day, natal_lat, natal_lng,
            natal_tz_str, natal_tz_offset_minutes, house_system, zodiac_type,
            scan_start_hour, scan_start_minute, scan_end_hour, scan_end_minute,
            step_minutes, orb_deg, check_all_house_cusps,
            scan_start_second, scan_end_second, step_seconds,
        )
        if config.CONSOLE_RESULT_PREVIEW:
            logger.info(
                "  herich: %d/%d candidates qualify, %d windows",
                result["candidates_qualifying_raw_count"], result["candidates_tested"],
                len(result["qualifying_windows"]),
            )
        return result
    except Exception as e:
        logger.exception("rectif_herich_scan failed")
        return {"error": str(e)}


def ping(message: str = "world") -> str:
    return f"pong: {message} (from astromcp, kerykeion engine loaded)"


def help(topic: str = "overview") -> str:
    return get_help(topic)
