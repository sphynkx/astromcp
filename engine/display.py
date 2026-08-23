"""
Human-readable console output for tool results.

Controlled by ASTROMCP_CONSOLE_RESULT_PREVIEW in .env (see config.py). When
enabled, every tool call also prints a compact summary of its result to the
server console/journal - useful for an operator watching `journalctl -u
astromcp -f` to see what's actually happening, not just that a request came
in and a response went out.
"""

import logging

logger = logging.getLogger("astromcp")


def print_chart_result(data: dict) -> None:
    if "error" in data:
        logger.info("  -> ERROR: %s", data["error"])
        return
    meta = data.get("meta", {})
    logger.info(
        "  chart @ %s  tz=%s(%s)  house_sys=%s",
        meta.get("input_datetime"), meta.get("tz_used"), meta.get("tz_source"), meta.get("house_system"),
    )
    for name, p in data.get("points", {}).items():
        logger.info(
            "    %-12s %6.2f deg %-4s house=%s%s",
            name, p.get("abs_pos", 0.0), p.get("sign", "?"), p.get("house", "?"),
            " (R)" if p.get("retrograde") else "",
        )
    angles = data.get("angles", {})
    if angles:
        asc = angles.get("ascendant", {})
        mc = angles.get("medium_coeli", {})
        logger.info(
            "    ASC=%.2f(%s)  MC=%.2f(%s)",
            asc.get("abs_pos", 0.0), asc.get("sign", "?"), mc.get("abs_pos", 0.0), mc.get("sign", "?"),
        )


def print_technique_result(data: dict) -> None:
    if "error" in data:
        logger.info("  -> ERROR: %s", data["error"])
        return
    logger.info("  technique=%s  meta=%s", data.get("technique"), data.get("meta"))
    aspects = data.get("aspects", [])
    if aspects:
        logger.info("  aspects (%d):", len(aspects))
        for a in sorted(aspects, key=lambda x: x["exact_orb"])[:15]:
            logger.info(
                "    %-10s %3d deg %-12s orb=%.3f %s",
                a["point_a"], a["aspect_deg"], a["point_b"], a["exact_orb"], a["status"],
            )
        if len(aspects) > 15:
            logger.info("    ... and %d more", len(aspects) - 15)


def print_scan_result(data: dict) -> None:
    if "error" in data:
        logger.info("  -> ERROR: %s", data["error"])
        return
    logger.info(
        "  scan: %d candidates, step=%d min",
        data.get("candidates_tested"), data.get("step_minutes"),
    )
    for r in data.get("top_results", [])[:15]:
        per_ev = " ".join(f"{k}={v.get('score', '?')}" for k, v in r.get("per_event", {}).items())
        logger.info("    %02d:%02d  score=%8.2f  %s", r["hour"], r["minute"], r["total_score"], per_ev)
