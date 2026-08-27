"""
SVG natal chart wheel renderer for the /astro/chart.svg REST endpoint (see
app.py). Pure stdlib (math + datetime/zoneinfo for the GMT-offset header
line) - no new dependency for this file.

Design brief, fourth iteration - a ZET9 screenshot as a loose visual
reference initially, then exact sign colors/house ring/Asc-MC markers/
dignity letters, then a bug-fix + polish round, and now:
  - per-house sector coloring (a table like SIGN_COLORS, all 12 entries
    currently the same hex - the hook for a future cardinal/succedent/
    cadent color scheme without touching the drawing code)
  - the external tick mark for house cusps came back for the 4 angle
    houses too (it was dropped for those in the previous round while
    disambiguating it from the planet ticks - the disambiguation was the
    point, dropping the tick entirely for angles was an overcorrection)
  - the side planet/angle list now column-aligns the degree number, sign
    glyph, and minutes as three separately-positioned pieces instead of
    one concatenated string (SVG has no monospace-grid text layout, so
    fixed x-per-column is how this has to work)
  - the aspect table is now a proper shrinking staircase (row i only has
    i cells) with column headers along the bottom instead of a half-empty
    square with headers on top - smaller footprint, moved up the canvas
  - aspect glyphs drawn at each wheel chord's own midpoint, matching the
    small aspect-type glyphs visible along the aspect lines in the ZET9
    reference
  - chords are now also drawn from planets to the 4 angles (not just
    planet-planet) - the underlying aspect list includes house-cusp
    aspects now (include_house_cusp_aspects=True from app.py), but only
    angle-endpoint aspects get a drawn chord; all 12 cusps' aspects
    (if any) are still listed in their own tooltip
  - every cusp/angle tooltip now includes any aspects to that point, and
    every tooltip (planet/cusp/aspect chord) includes the applying/
    separating mark
  - GMT offset, essential-dignity letters, and the applying/separating
    aspect-table coloring from the previous round are unchanged

Chart rotation convention (standard Western tropical wheel): Ascendant at
screen-left (180 degrees), ecliptic longitude increasing counterclockwise
- house numbers increase counterclockwise from the Ascendant, Descendant
is always exactly opposite the Ascendant by construction. The four angle
houses (I/IV/VII/X) get an Asc/IC/Dsc/MC marker instead of a Roman
numeral - matching the ZET9 reference, which doesn't print those either.
"""

import math
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - shouldn't happen given this
    ZoneInfo = None  # project's actual Python requirement

from .constants import SIGN_ORDER

# ==================== Reference tables ====================

# Exact hex values from the project owner - kept separate from the
# drawing code so it's easy to retune. Index matches SIGN_ORDER
# (0=Aries..11=Pisces).
SIGN_COLORS = {
    "Ari": "#fabdba", "Tau": "#fddcbd", "Gem": "#fdfdbd", "Can": "#ddfdbc",
    "Leo": "#bdfebe", "Vir": "#addac5", "Lib": "#b5fdfd", "Sco": "#bcddfc",
    "Sag": "#bdbdfd", "Cap": "#ddbdfe", "Aqu": "#fbbafa", "Pis": "#fdbedd",
}

# Per-house sector coloring - all 12 currently the same flat color (what
# the house ring looked like before this table existed). Keyed by house
# NUMBER (1-12), so a future cardinal/succedent/cadent scheme is just
# "houses 1/4/7/10 get color X, 2/5/8/11 get Y, 3/6/9/12 get Z" without
# touching build_natal_chart_svg at all.
HOUSE_COLORS = {n: "#e2edfa" for n in range(1, 13)}

SIGN_GLYPHS = {
    "Ari": "\u2648", "Tau": "\u2649", "Gem": "\u264A", "Can": "\u264B",
    "Leo": "\u264C", "Vir": "\u264D", "Lib": "\u264E", "Sco": "\u264F",
    "Sag": "\u2650", "Cap": "\u2651", "Aqu": "\u2652", "Pis": "\u2653",
}

PLANET_GLYPHS = {
    "sun": "\u2609", "moon": "\u263D", "mercury": "\u263F", "venus": "\u2640",
    "mars": "\u2642", "jupiter": "\u2643", "saturn": "\u2644",
    "uranus": "\u2645", "neptune": "\u2646", "pluto": "\u2647",
    "chiron": "\u26B7", "mean_lilith": "\u26B8",
}

# For tooltips/legends - plain Russian names, kept in sync BY HAND with
# install/Module_Astrodata.lua's PLANET.nom table.
PLANET_NAMES_RU = {
    "sun": "Солнце", "moon": "Луна", "mercury": "Меркурий", "venus": "Венера",
    "mars": "Марс", "jupiter": "Юпитер", "saturn": "Сатурн", "uranus": "Уран",
    "neptune": "Нептун", "pluto": "Плутон", "chiron": "Хирон", "mean_lilith": "Лилит",
}

ASPECT_NAMES_RU = {
    0: "Соединение", 30: "Полусекстиль", 45: "Полуквадрат", 60: "Секстиль",
    90: "Квадрат", 120: "Тригон", 135: "Полуторный квадрат", 150: "Квинконс",
    180: "Оппозиция",
}

HOUSE_SYSTEM_NAMES = {
    "P": "Placidus", "K": "Koch", "W": "Whole Sign", "E": "Equal",
    "R": "Regiomontanus", "C": "Campanus", "O": "Porphyry", "M": "Morinus",
}

CHART_POINTS = [
    "sun", "moon", "mercury", "venus", "mars", "jupiter", "saturn",
    "uranus", "neptune", "pluto", "chiron", "mean_lilith",
]

# Essential dignities - see previous rounds' notes; a popular modern
# convention, not the strict 7-planet classical system, exactly as given.
PLANET_DIGNITY = {
    "sun":     {"O": ["Leo"], "E": ["Ari"], "D": ["Aqu"], "F": ["Lib"]},
    "moon":    {"O": ["Can"], "E": ["Tau"], "D": ["Cap"], "F": ["Sco"]},
    "mercury": {"O": ["Gem", "Vir"], "E": ["Vir"], "D": ["Sag", "Pis"], "F": ["Pis"]},
    "venus":   {"O": ["Tau", "Lib"], "E": ["Pis"], "D": ["Sco", "Ari"], "F": ["Vir"]},
    "mars":    {"O": ["Ari", "Sco"], "E": ["Cap"], "D": ["Lib", "Tau"], "F": ["Can"]},
    "jupiter": {"O": ["Sag", "Pis"], "E": ["Can"], "D": ["Gem", "Vir"], "F": ["Cap"]},
    "saturn":  {"O": ["Cap", "Aqu"], "E": ["Lib"], "D": ["Can", "Leo"], "F": ["Ari"]},
    "uranus":  {"O": ["Aqu", "Cap"], "E": ["Sco"], "D": ["Leo", "Can"], "F": ["Tau"]},
    "neptune": {"O": ["Pis", "Sag"], "E": ["Aqu"], "D": ["Vir", "Gem"], "F": ["Leo"]},
    "pluto":   {"O": ["Sco", "Ari"], "E": ["Leo"], "D": ["Tau", "Lib"], "F": ["Aqu"]},
}
DIGNITY_PRIORITY = ["O", "E", "D", "F"]
DIGNITY_DISPLAY = {"O": "О", "E": "Э", "D": "И", "F": "П"}

ANGLE_KEYS = ["asc", "mc", "dsc", "ic"]
ANGLE_LABELS = {"asc": "Asc", "mc": "MC", "dsc": "Dsc", "ic": "IC"}
ANGLE_HOUSE_INDEX = {0: "asc", 3: "ic", 6: "dsc", 9: "mc"}  # house_N index (0-based) -> angle key

HOUSE_ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"]
ORDINAL_WORDS = ["First", "Second", "Third", "Fourth", "Fifth", "Sixth",
                 "Seventh", "Eighth", "Ninth", "Tenth", "Eleventh", "Twelfth"]

# aspect_deg -> (css_color, dash_array_or_None, base_stroke_width) - the
# WHEEL's own aspect chords (hard=red/soft=green). The aspect TABLE uses
# a different rule - see APPLYING_COLOR/SEPARATING_COLOR below.
ASPECT_STYLE = {
    0:   ("#555555", None,  1.4),
    30:  ("#4a9c4a", "2,3", 0.9),
    45:  ("#c23b3b", "1,3", 0.9),
    60:  ("#4a9c4a", "6,3", 1.1),
    90:  ("#c23b3b", "6,3", 1.3),
    120: ("#4a9c4a", None,  1.3),
    135: ("#c23b3b", "1,3", 0.9),
    150: ("#b08a1e", "2,3", 0.9),
    180: ("#c23b3b", None,  1.5),
}
ASPECT_GLYPH = {
    0: "\u260C", 30: "\u26BA", 45: "\u2220", 60: "\u26B9", 90: "\u25A1",
    120: "\u25B3", 135: "\u29C3", 150: "\u26BB", 180: "\u260D",
}
CONVERGENCE_MARK = {"applying": "\u203a\u2022\u2039", "separating": "\u2039\u2022\u203a"}
# ">•<" / "<•>" - using the angle-quote variants (U+203A/2039) rather than
# literal </> so they never look like stray HTML inside a tooltip string.

# Aspects drawn as CHORDS on the wheel are restricted to the majors - the
# minors (semisextile/semisquare/sesquiquadrate/quincunx) still show up in
# the aspect table and in tooltips, just not as an extra line crossing the
# circle - with ten-plus points in play the minors were adding clutter
# without much payoff at wheel scale.
MAJOR_ASPECTS = {0, 60, 90, 120, 180}

APPLYING_COLOR = "#c2508a"    # pink - aspect table only, see module docstring
SEPARATING_COLOR = "#4a90c2"  # light blue
UNKNOWN_STATUS_COLOR = "#888888"

EXACT_ORB_DEG = 1.0

# ==================== Geometry helpers ====================


def _screen_point(cx: float, cy: float, radius: float, abs_pos: float, asc_abs_pos: float) -> Tuple[float, float]:
    theta_deg = 180 + (abs_pos - asc_abs_pos)
    theta = math.radians(theta_deg)
    x = cx + radius * math.cos(theta)
    y = cy - radius * math.sin(theta)
    return x, y


def _fmt_dm_parts(position: float, sign: str) -> Tuple[str, str, str]:
    """Returns (deg_str, sign_glyph_with_vs16, minute_str) as three
    separate pieces so the caller can right-align the degree number, fix
    the glyph position, and left-align the minutes - a single
    concatenated string left-aligns the whole thing, which is what made
    one- and two-digit degrees look ragged."""
    deg = int(math.floor(position))
    minute = int(math.floor((position - deg) * 60 + 0.5))
    if minute == 60:
        minute = 0
        deg += 1
    glyph = SIGN_GLYPHS.get(sign, sign) + "\ufe0f"
    return str(deg), glyph, f"{minute:02d}"


def _fmt_dms_plain(position: float, sign: str) -> str:
    """WITH seconds, plain 3-letter sign code - for tooltip text."""
    deg = int(math.floor(position))
    rem = (position - deg) * 60
    minute = int(math.floor(rem))
    second = int(round((rem - minute) * 60))
    if second == 60:
        second = 0
        minute += 1
    if minute == 60:
        minute = 0
        deg += 1
    return f"{deg}\u00b0{minute:02d}'{second:02d}\"{sign}"


def _dignity_letter(planet_id: str, sign: str) -> str:
    table = PLANET_DIGNITY.get(planet_id)
    if not table:
        return ""
    for letter in DIGNITY_PRIORITY:
        if sign in table.get(letter, ()):
            return DIGNITY_DISPLAY[letter]
    return ""


def _house_number(house_field: Optional[str]) -> Optional[int]:
    if not house_field:
        return None
    word = house_field.replace("_House", "")
    try:
        return ORDINAL_WORDS.index(word) + 1
    except ValueError:
        return None


def _format_gmt_offset(tz_name: Optional[str], input_datetime: str) -> str:
    if not tz_name or not ZoneInfo:
        return tz_name or ""
    try:
        naive = datetime.strptime(input_datetime, "%Y-%m-%d %H:%M:%S")
        aware = naive.replace(tzinfo=ZoneInfo(tz_name))
        offset = aware.utcoffset()
        if offset is None:
            return tz_name
        total_minutes = int(offset.total_seconds() // 60)
        sign = "+" if total_minutes >= 0 else "-"
        h, m = divmod(abs(total_minutes), 60)
        return f"GMT{sign}{h}" if m == 0 else f"GMT{sign}{h}:{m:02d}"
    except Exception:
        return tz_name


def _esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace('"', "&quot;"))


def _title(text: str) -> str:
    return f"<title>{_esc(text)}</title>"


def _aspect_lines_for_point(point_key: str, aspects: List[Dict[str, Any]],
                             names_ru: Dict[str, str]) -> List[str]:
    """
    Formats every aspect involving point_key (a CHART_POINTS id, a Lot id,
    an angle key, or a 'house_N' key) as tooltip lines: "<AspectName>
    <orb> <OtherName> <convergence mark>". Used by planet, cusp, angle,
    and Lot tooltips alike. names_ru resolves point ids to display names -
    built once in build_natal_chart_svg (planets + registered Lots), so
    this function itself needs no per-point-type special-casing.
    """
    lines = []
    for asp in aspects:
        other = None
        if asp.get("point_a") == point_key:
            other = asp.get("point_b")
        elif asp.get("point_b") == point_key:
            other = asp.get("point_a")
        if not other:
            continue
        asp_name = ASPECT_NAMES_RU.get(asp.get("aspect_deg"))
        if not asp_name:
            continue
        other_name = names_ru.get(other, other)
        orb = asp.get("exact_orb", 0)
        orb_deg = int(orb)
        orb_min = int(round((orb - orb_deg) * 60))
        mark = CONVERGENCE_MARK.get(asp.get("status"), "")
        lines.append(f"{asp_name} {orb_deg}\u00b0{orb_min:02d}' {other_name} {mark}".strip())
    return lines


# ==================== Main builder ====================


def build_natal_chart_svg(
    report: Dict[str, Any],
    person_name: Optional[str] = None,
    place_label: Optional[str] = None,
    photo_url: Optional[str] = None,
) -> str:
    """
    report - the dict from public_api.build_full_report(), called with
    include_house_cusp_aspects=True so house/angle tooltips can list their
    own aspects. person_name/place_label are free text for the header.
    photo_url - a data: URI (see engine/photo_fetch.py - NOT a plain
    external URL, that doesn't work once this SVG is embedded via <img>,
    see that module's docstring) or None.

    Returns a complete standalone SVG document as a string.
    """
    planets = report.get("planets", {})
    houses = report.get("houses", {})
    lots = report.get("lots", {})
    lot_ids = list(lots.keys())
    aspects_raw = report.get("aspects", [])
    # House-to-house (and angle-to-angle/angle-to-house) aspects are a
    # meaningless byproduct of computing aspects across the full point set
    # (planets + Lots + angles + all 12 cusps) - a cusp is "opposite" its
    # counterpart by construction, that's not an astrological finding.
    # Keep only aspects where at least one side is an actual planet or a
    # Lot; planet/Lot-to-house and planet/Lot-to-angle aspects are still
    # meaningful and stay in.
    meaningful_points = set(CHART_POINTS) | set(lot_ids)
    aspects = [
        a for a in aspects_raw
        if a.get("point_a") in meaningful_points or a.get("point_b") in meaningful_points
    ]
    conjunctions = report.get("fixed_star_conjunctions", [])
    meta = report.get("meta", {})

    # Combined glyph/name lookups (planets + whatever Lots this report
    # actually carries) - built once here so every place below that draws
    # or labels a point (side list, wheel glyphs, aspect table, tooltips)
    # treats a Lot exactly like a planet without its own special-casing.
    # A Lot's symbol is its dedicated glyph if it has one (Part of
    # Fortune's ⊗), otherwise its abbreviation (engine/lots.py - most
    # future Lots won't have a traditional dedicated symbol).
    all_glyphs: Dict[str, str] = dict(PLANET_GLYPHS)
    all_names_ru: Dict[str, str] = dict(PLANET_NAMES_RU)
    for lid, ldata in lots.items():
        all_glyphs[lid] = ldata.get("glyph") or ldata.get("abbr") or "?"
        all_names_ru[lid] = ldata.get("name_ru", lid)

    asc = houses.get("asc")
    if not asc:
        raise ValueError("report has no 'asc' angle - cannot orient the wheel")
    asc_abs_pos = asc["abs_pos"]

    # ---- canvas layout ----
    width, height = 1200, 1400
    cx, cy = 480, 500
    r_outer = 340
    r_sign_inner = 300
    r_house_ring_inner = 250
    r_planet = 250
    r_planet_alt = 220  # widened from 232 - 18px wasn't reliably clearing
                        # a near-exact conjunction's glyph bounding boxes
    # House cusp lines used to run all the way from near-center out to the
    # ring, which visually tangled with aspect chords crossing near the
    # center (especially oppositions). Fixed as a short stub hanging INWARD
    # off the house ring's own inner edge - mirrors the short OUTER stub
    # near the numeral (which hangs outward off the ring's outer edge) -
    # rather than a separate stub floating near the center circle.
    r_house_line_inner_start = r_house_ring_inner - 28
    r_house_line_inner_end = r_house_ring_inner
    r_tick_outer = r_outer + 16
    r_numeral = r_outer + 34
    r_angle_label = r_outer + 58

    svg: List[str] = []
    svg.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="\'DejaVu Sans\', \'Segoe UI Symbol\', '
        f'\'Noto Sans Symbols\', Arial, sans-serif">'
    )
    svg.append(f'<rect x="0" y="0" width="{width}" height="{height}" fill="#ffffff"/>')

    # ---- header (photo, if given, then text) ----
    text_x = 24
    if photo_url:
        svg.append(
            f'<image href="{_esc(photo_url)}" x="24" y="16" width="90" height="112" '
            f'preserveAspectRatio="xMidYMid slice"/>'
        )
        svg.append('<rect x="24" y="16" width="90" height="112" fill="none" stroke="#bbb"/>')
        text_x = 128

    header_lines = []
    if person_name:
        header_lines.append(_esc(person_name))
    dt = meta.get("input_datetime", "")
    gmt = _format_gmt_offset(meta.get("tz_used"), dt)
    header_lines.append(_esc(f"{dt}  ({gmt})".strip()))
    if place_label:
        header_lines.append(_esc(place_label))
    elif meta.get("resolved_city_name"):
        header_lines.append(_esc(str(meta["resolved_city_name"])))
    lat, lng = meta.get("lat"), meta.get("lng")
    house_system_name = HOUSE_SYSTEM_NAMES.get(meta.get("house_system"), meta.get("house_system", ""))
    if lat is not None and lng is not None:
        header_lines.append(f"{lat:.4f}, {lng:.4f}  \u2022  {_esc(house_system_name)}")

    y = 34
    weights = ["bold", "normal", "normal", "normal"]
    sizes = [20, 15, 15, 13]
    for i, line in enumerate(header_lines[:4]):
        svg.append(
            f'<text x="{text_x}" y="{y}" font-size="{sizes[min(i, 3)]}" '
            f'font-weight="{weights[min(i, 3)]}" fill="#111">{line}</text>'
        )
        y += sizes[min(i, 3)] + 8

    # ---- sign ring (12 wedges, exact hex per SIGN_COLORS) ----
    for i, sign in enumerate(SIGN_ORDER):
        sign_start_abs = i * 30
        x1o, y1o = _screen_point(cx, cy, r_outer, sign_start_abs, asc_abs_pos)
        x2o, y2o = _screen_point(cx, cy, r_outer, sign_start_abs + 30, asc_abs_pos)
        x1i, y1i = _screen_point(cx, cy, r_sign_inner, sign_start_abs, asc_abs_pos)
        x2i, y2i = _screen_point(cx, cy, r_sign_inner, sign_start_abs + 30, asc_abs_pos)
        color = SIGN_COLORS[sign]
        path = (
            f'M {x1o:.1f},{y1o:.1f} A {r_outer},{r_outer} 0 0 0 {x2o:.1f},{y2o:.1f} '
            f'L {x2i:.1f},{y2i:.1f} A {r_sign_inner},{r_sign_inner} 0 0 1 {x1i:.1f},{y1i:.1f} Z'
        )
        svg.append(f'<path d="{path}" fill="{color}" stroke="#888" stroke-width="0.6"/>')
        mid_abs = sign_start_abs + 15
        gx, gy = _screen_point(cx, cy, (r_outer + r_sign_inner) / 2, mid_abs, asc_abs_pos)
        svg.append(
            f'<text x="{gx:.1f}" y="{gy:.1f}" font-size="22" text-anchor="middle" '
            f'dominant-baseline="central" fill="#222">{SIGN_GLYPHS[sign]}</text>'
        )

    svg.append(f'<circle cx="{cx}" cy="{cy}" r="{r_outer}" fill="none" stroke="#4a7fa8" stroke-width="1.5"/>')
    svg.append(f'<circle cx="{cx}" cy="{cy}" r="{r_sign_inner}" fill="none" stroke="#4a7fa8" stroke-width="1.2"/>')

    # ---- house ring: per-house sectors (HOUSE_COLORS), not one flat fill -
    # unequal angular widths (house cusps, unlike the fixed 30deg sign
    # wedges), so large-arc-flag has to be computed per sector instead of
    # always 0.
    for i in range(12):
        start_h = houses.get(f"house_{i + 1}")
        end_h = houses.get(f"house_{(i + 1) % 12 + 1}")
        if not start_h or not end_h:
            continue
        start_abs = start_h["abs_pos"]
        span = (end_h["abs_pos"] - start_abs) % 360
        if span <= 0:
            span = 360
        large_arc = 1 if span > 180 else 0
        x1o, y1o = _screen_point(cx, cy, r_sign_inner, start_abs, asc_abs_pos)
        x2o, y2o = _screen_point(cx, cy, r_sign_inner, start_abs + span, asc_abs_pos)
        x1i, y1i = _screen_point(cx, cy, r_house_ring_inner, start_abs, asc_abs_pos)
        x2i, y2i = _screen_point(cx, cy, r_house_ring_inner, start_abs + span, asc_abs_pos)
        color = HOUSE_COLORS.get(i + 1, "#e2edfa")
        path = (
            f'M {x1o:.1f},{y1o:.1f} A {r_sign_inner},{r_sign_inner} 0 {large_arc} 0 {x2o:.1f},{y2o:.1f} '
            f'L {x2i:.1f},{y2i:.1f} A {r_house_ring_inner},{r_house_ring_inner} 0 {large_arc} 1 {x1i:.1f},{y1i:.1f} Z'
        )
        svg.append(f'<path d="{path}" fill="{color}" stroke="#8aa" stroke-width="0.4"/>')
    svg.append(f'<circle cx="{cx}" cy="{cy}" r="{r_house_ring_inner}" fill="none" stroke="#4a7fa8" stroke-width="1"/>')

    # ---- house cusp lines, tooltips, external tick, numeral ----
    # Every cusp gets a tooltip (position + any aspects to that cusp, per
    # the brief - previously only the thin inner line carried one, which
    # was hard to actually hover; now the whole cusp group - line, tick,
    # numeral/marker - shares one). All 12 get the external stub tick
    # (dropped for the 4 angle houses in the previous round while fixing
    # the tick-ambiguity issue - that was an overcorrection, the ambiguity
    # was about the RADIUS the ticks ended at, not about angle houses
    # specifically). Only the 8 non-angle houses get a Roman numeral - the
    # 4 angle houses get their own Asc/IC/Dsc/MC marker instead, drawn
    # further below.
    angle_screen: Dict[str, Tuple[float, float]] = {}
    for i in range(12):
        house_key = f"house_{i + 1}"
        h = houses.get(house_key)
        if not h:
            continue
        abs_pos = h["abs_pos"]
        is_angle_axis = i in ANGLE_HOUSE_INDEX
        x1, y1 = _screen_point(cx, cy, r_house_line_inner_start, abs_pos, asc_abs_pos)
        x2, y2 = _screen_point(cx, cy, r_house_line_inner_end, abs_pos, asc_abs_pos)
        tx1, ty1 = _screen_point(cx, cy, r_outer, abs_pos, asc_abs_pos)
        tx2, ty2 = _screen_point(cx, cy, r_tick_outer, abs_pos, asc_abs_pos)

        aspect_lines = _aspect_lines_for_point(house_key, aspects, all_names_ru)
        tooltip_text = "\n".join(
            [f"{HOUSE_ROMAN[i]} дом: {_fmt_dms_plain(h['position'], h['sign'])}"] + aspect_lines
        )

        # Same principle as the planet glyphs below: the tooltip sits on
        # the small marker (external tick + numeral), not the inner stub
        # line - keeps the hoverable target small and precise instead of
        # a thin radial corridor that could compete with a neighboring
        # cusp's line at some house systems/latitudes.
        svg.append(
            f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="{"#3a5a8a" if is_angle_axis else "#c9a0c9"}" '
            f'stroke-width="{1.6 if is_angle_axis else 0.8}"/>'
        )
        marker_group = [
            _title(tooltip_text),
            f'<line x1="{tx1:.1f}" y1="{ty1:.1f}" x2="{tx2:.1f}" y2="{ty2:.1f}" '
            f'stroke="#3a5a8a" stroke-width="1.2"/>',
        ]
        if not is_angle_axis:
            nx, ny = _screen_point(cx, cy, r_numeral, abs_pos, asc_abs_pos)
            marker_group.append(
                f'<text x="{nx:.1f}" y="{ny:.1f}" font-size="14" text-anchor="middle" '
                f'dominant-baseline="central" fill="#333">{HOUSE_ROMAN[i]}</text>'
            )
        svg.append(f'<g>{"".join(marker_group)}</g>')

    # explicit angle labels (Asc/Dsc/MC/IC), each with its own tooltip
    # (position + aspects); angle_screen recorded here for drawing chords
    # to planets further below.
    for key in ANGLE_KEYS:
        a = houses.get(key)
        if not a:
            continue
        lx, ly = _screen_point(cx, cy, r_angle_label, a["abs_pos"], asc_abs_pos)
        angle_screen[key] = _screen_point(cx, cy, r_house_ring_inner, a["abs_pos"], asc_abs_pos)
        aspect_lines = _aspect_lines_for_point(key, aspects, all_names_ru)
        tooltip_text = "\n".join(
            [f"{ANGLE_LABELS[key]}: {_fmt_dms_plain(a['position'], a['sign'])}"] + aspect_lines
        )
        svg.append(
            f'<g>{_title(tooltip_text)}<text x="{lx:.1f}" y="{ly:.1f}" font-size="13" font-weight="bold" '
            f'text-anchor="middle" dominant-baseline="central" fill="#1a3a6a">'
            f'{ANGLE_LABELS[key]}</text></g>'
        )

    # Ascendant arrowhead (always points due left by construction) and an
    # open circle at the MC.
    asc_tip_x, asc_tip_y = cx - (r_outer + 42), cy
    asc_base1_x, asc_base1_y = cx - (r_outer + 24), cy - 7
    asc_base2_x, asc_base2_y = cx - (r_outer + 24), cy + 7
    svg.append(
        f'<polygon points="{asc_tip_x:.1f},{asc_tip_y:.1f} {asc_base1_x:.1f},{asc_base1_y:.1f} '
        f'{asc_base2_x:.1f},{asc_base2_y:.1f}" fill="#c23b3b"/>'
    )
    mc = houses.get("mc")
    if mc:
        mx, my = _screen_point(cx, cy, r_outer + 30, mc["abs_pos"], asc_abs_pos)
        svg.append(f'<circle cx="{mx:.1f}" cy="{my:.1f}" r="6" fill="#ffffff" stroke="#1a3a6a" stroke-width="2"/>')

    svg.append(f'<circle cx="{cx}" cy="{cy}" r="18" fill="none" stroke="#3a3a8a" stroke-width="1.5"/>')

    # ---- planet + Lot placement ----
    planet_screen: Dict[str, Tuple[float, float]] = {}
    combined_points = (
        [(pid, planets[pid], "planet") for pid in CHART_POINTS if pid in planets]
        + [(lid, lots[lid], "lot") for lid in lot_ids]
    )
    ordered = sorted(combined_points, key=lambda kv: kv[1]["abs_pos"])
    prev_abs = None
    alt_band = False
    for pid, pdata, kind in ordered:
        abs_pos = pdata["abs_pos"]
        if prev_abs is not None:
            gap = min((abs_pos - prev_abs) % 360, (prev_abs - abs_pos) % 360)
            alt_band = gap < 6
        radius = r_planet_alt if alt_band else r_planet
        prev_abs = abs_pos

        tick_x1, tick_y1 = _screen_point(cx, cy, radius + 14, abs_pos, asc_abs_pos)
        tick_x2, tick_y2 = _screen_point(cx, cy, r_sign_inner, abs_pos, asc_abs_pos)
        px, py = _screen_point(cx, cy, radius, abs_pos, asc_abs_pos)
        planet_screen[pid] = (px, py)
        glyph = all_glyphs.get(pid, "?")
        # A Lot's abbreviation can be 2+ characters (Part of Fortune's own
        # glyph is one character, but most future Lots won't have a
        # dedicated glyph - see engine/lots.py) - shrink the font so it
        # still fits inside the same visual footprint as a single-glyph
        # planet symbol, rather than overflowing into its neighbors.
        glyph_font_size = 20 if len(glyph) <= 1 else 12

        # House placement: kerykeion gives planets a string like
        # "Fifth_House" (parsed by _house_number); a Lot's house is
        # already a plain int (engine.houses.house_number_for_longitude,
        # since a Lot isn't one of kerykeion's own objects).
        if kind == "planet":
            house_num = _house_number(pdata.get("house"))
        else:
            house_num = pdata.get("house")
        house_roman = HOUSE_ROMAN[house_num - 1] if house_num else "?"
        tooltip_lines = [
            f"{all_names_ru.get(pid, pid)} {_fmt_dms_plain(pdata['position'], pdata['sign'])}, {house_roman}"
        ]
        tooltip_lines.extend(_aspect_lines_for_point(pid, aspects, all_names_ru))
        tooltip = _title("\n".join(tooltip_lines))

        # Tick line is purely decorative and drawn WITHOUT a tooltip - two
        # near-conjunct points' ticks run almost on top of each other
        # (same angle, only the radius differs), so a tooltip attached to
        # the tick was effectively unreachable for whichever point got
        # drawn first (the later one's tick visually/hit-area covers it).
        # The tooltip now sits on the glyph text alone - "exactly on the
        # symbol", per the brief - which stays a small, precise,
        # non-overlapping target even for a near-exact conjunction.
        svg.append(
            f'<line x1="{tick_x1:.1f}" y1="{tick_y1:.1f}" x2="{tick_x2:.1f}" y2="{tick_y2:.1f}" '
            f'stroke="#999" stroke-width="0.6"/>'
        )
        glyph_group = [
            tooltip,
            f'<text x="{px:.1f}" y="{py:.1f}" font-size="{glyph_font_size}" text-anchor="middle" '
            f'dominant-baseline="central" fill="#000">{glyph}</text>',
        ]
        # Planets: kerykeion's own retrograde flag. Lots: no such field
        # exists (a Lot isn't an orbiting body) - but a negative computed
        # speed means the SAME thing visually (moving backward through
        # the zodiac at that moment), see engine/lots.py's docstring.
        is_retro = pdata.get("retrograde") if kind == "planet" else (
            pdata.get("speed") is not None and pdata["speed"] < 0
        )
        if is_retro:
            glyph_group.append(f'<text x="{px + 11:.1f}" y="{py - 9:.1f}" font-size="9" fill="#a03030">R</text>')
        svg.append(f'<g>{"".join(glyph_group)}</g>')

    # ---- aspect chords: planet/Lot-planet/Lot, and planet/Lot-angle -
    # MAJOR aspects only (see MAJOR_ASPECTS) to keep the wheel itself
    # readable; minors still show in the aspect table and in tooltips.
    # (plain house-cusp aspects, i.e. to houses 2/3/5/6/8/9/11/12, are
    # listed in that cusp's tooltip but NOT drawn as a chord - only the 4
    # angles get a drawn line, per the brief.)
    all_endpoints = {**planet_screen, **angle_screen}
    for asp in aspects:
        if asp.get("aspect_deg") not in MAJOR_ASPECTS:
            continue
        pa, pb = asp.get("point_a"), asp.get("point_b")
        if pa not in all_endpoints or pb not in all_endpoints:
            continue
        if pa not in planet_screen and pb not in planet_screen:
            continue  # skip angle-angle (shouldn't occur, but be defensive)
        style = ASPECT_STYLE.get(asp.get("aspect_deg"))
        if not style:
            continue
        color, dash, width = style
        is_exact = asp.get("exact_orb", 99) < EXACT_ORB_DEG
        x1, y1 = all_endpoints[pa]
        x2, y2 = all_endpoints[pb]
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        asp_name = ASPECT_NAMES_RU.get(asp.get("aspect_deg"), "")
        mark = CONVERGENCE_MARK.get(asp.get("status"), "")
        name_a = all_names_ru.get(pa, ANGLE_LABELS.get(pa, pa))
        name_b = all_names_ru.get(pb, ANGLE_LABELS.get(pb, pb))
        tooltip = _title(
            f"{name_a} {asp_name} {name_b} (орбис {asp.get('exact_orb', 0):.2f}\u00b0) {mark}".strip()
        )
        # Aspect glyph sits at 1/3 along the chord (from point A), not the
        # midpoint - several oppositions on one chart otherwise stack
        # their glyphs on top of each other right at the shared center.
        third_x, third_y = x1 + (x2 - x1) / 3, y1 + (y2 - y1) / 3
        asp_glyph = ASPECT_GLYPH.get(asp.get("aspect_deg"))
        chord_group = [
            tooltip,
            f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="{color}" stroke-width="{width * (1.8 if is_exact else 1)}"'
            f'{dash_attr} opacity="{1.0 if is_exact else 0.75}"/>',
        ]
        if asp_glyph:
            chord_group.append(
                f'<text x="{third_x:.1f}" y="{third_y:.1f}" font-size="11" text-anchor="middle" '
                f'dominant-baseline="central" fill="{color}" '
                f'style="paint-order:stroke;stroke:#fff;stroke-width:2px;">{asp_glyph}</text>'
            )
        svg.append(f'<g>{"".join(chord_group)}</g>')

    # ==================== side planet list (column-aligned) ====================
    col_glyph_x = 905     # shifted right from 860 - was overlapping the
                          # angle labels (Asc/MC/Dsc/IC sit as far out as
                          # r_outer+58, whose right edge lands right around
                          # x=878 at this canvas's cx=480)
    col_deg_x = 953       # right-aligned degree number
    col_glyph2_x = 957    # sign glyph, fixed start
    col_min_x = 981       # minutes, fixed start
    col_extra_x = 1055
    ly = 60
    svg.append(f'<text x="{col_glyph_x}" y="{ly}" font-size="14" font-weight="bold" fill="#111">Планеты</text>')
    ly += 22

    def _draw_position_row(label_x: float, label_text: str, position: float, sign: str,
                            retro: bool, dignity: str, star_note: str, y_pos: float) -> None:
        cell = f'<text x="{label_x}" y="{y_pos}" font-size="16" fill="#000">{label_text}'
        if dignity:
            cell += f'<tspan font-size="10" font-weight="bold" dy="-5">{dignity}</tspan>'
        cell += '</text>'
        svg.append(cell)
        deg_str, glyph, min_str = _fmt_dm_parts(position, sign)
        svg.append(f'<text x="{col_deg_x}" y="{y_pos}" font-size="13" text-anchor="end" fill="#000">{deg_str}</text>')
        pos_cell = f'<text x="{col_glyph2_x}" y="{y_pos}" font-size="13" fill="#000">{glyph}</text>'
        svg.append(pos_cell)
        min_cell = f'<text x="{col_min_x}" y="{y_pos}" font-size="13" fill="#000">{min_str}'
        if retro:
            min_cell += '<tspan font-size="9" font-weight="bold" dy="5" fill="#a03030">R</tspan>'
        min_cell += '</text>'
        svg.append(min_cell)
        if star_note:
            svg.append(f'<text x="{col_extra_x}" y="{y_pos}" font-size="12" fill="#555">{star_note}</text>')

    for pid in CHART_POINTS:
        pdata = planets.get(pid)
        if not pdata:
            continue
        glyph = all_glyphs.get(pid, "?")
        dignity = _dignity_letter(pid, pdata["sign"])
        star_note = ""
        for conj in conjunctions:
            if conj.get("point") == pid:
                star_note = f"\u2605{_esc(str(conj.get('star', '')))}"
                break
        _draw_position_row(col_glyph_x, glyph, pdata["position"], pdata["sign"],
                            bool(pdata.get("retrograde")), dignity, star_note, ly)
        ly += 22

    ly += 8
    svg.append(f'<text x="{col_glyph_x}" y="{ly}" font-size="14" font-weight="bold" fill="#111">Углы</text>')
    ly += 22
    for key in ANGLE_KEYS:
        a = houses.get(key)
        if not a:
            continue
        _draw_position_row(col_glyph_x, ANGLE_LABELS[key], a["position"], a["sign"],
                            False, "", "", ly)
        ly += 22

    if lots:
        ly += 8
        svg.append(f'<text x="{col_glyph_x}" y="{ly}" font-size="14" font-weight="bold" fill="#111">Парсы</text>')
        ly += 22
        for lid in lot_ids:
            ldata = lots[lid]
            glyph = all_glyphs.get(lid, "?")
            is_retro = ldata.get("speed") is not None and ldata["speed"] < 0
            _draw_position_row(col_glyph_x, glyph, ldata["position"], ldata["sign"],
                                is_retro, "", "", ly)
            ly += 22

    # ==================== aspect table: full staircase (both axes show
    # the SAME complete point list, not one axis missing its first entry
    # and the other missing its last - a strict "row 1..n-1 / column
    # 0..n-2" staircase is mathematically complete (every pair shown
    # exactly once) but reads as if the first/last point were dropped
    # from one axis; row 0 and column n-1 are simply empty here (nothing
    # to compare them against within their own edge) rather than omitted
    # from the labels entirely. ====================
    table_top = 860
    cell = 34
    label_col_w = 38  # widened slightly - a Lot's 2-letter abbreviation
                      # needs more room than a single-glyph planet symbol
    present = [pid for pid in CHART_POINTS if pid in planets] + lot_ids
    n = len(present)
    aspect_lookup: Dict[frozenset, Dict[str, Any]] = {}
    for asp in aspects:
        pa, pb = asp.get("point_a"), asp.get("point_b")
        if pa in present and pb in present:
            aspect_lookup[frozenset((pa, pb))] = asp

    svg.append(
        f'<text x="24" y="{table_top - 20}" font-size="14" font-weight="bold" fill="#111">'
        f'Таблица аспектов</text>'
    )
    grid_x0 = 24 + label_col_w
    grid_y0 = table_top

    for i in range(0, n):
        row_y = grid_y0 + i * cell
        row_glyph = all_glyphs.get(present[i], "?")
        row_font = 15 if len(row_glyph) <= 1 else 10
        svg.append(
            f'<text x="{grid_x0 - 8}" y="{row_y + cell / 2:.1f}" font-size="{row_font}" text-anchor="end" '
            f'dominant-baseline="central" fill="#000">{row_glyph}</text>'
        )
        for j in range(0, i):
            cx0 = grid_x0 + j * cell
            cy0 = row_y
            svg.append(
                f'<rect x="{cx0}" y="{cy0}" width="{cell}" height="{cell}" '
                f'fill="none" stroke="#ddd" stroke-width="0.5"/>'
            )
            asp = aspect_lookup.get(frozenset((present[i], present[j])))
            if not asp or asp.get("aspect_deg") not in ASPECT_GLYPH:
                continue
            status = asp.get("status")
            if status == "applying":
                color = APPLYING_COLOR
            elif status == "separating":
                color = SEPARATING_COLOR
            else:
                color = UNKNOWN_STATUS_COLOR
            is_exact = asp.get("exact_orb", 99) < EXACT_ORB_DEG
            glyph = ASPECT_GLYPH[asp.get("aspect_deg")]
            if is_exact:
                svg.append(
                    f'<rect x="{cx0 + 1}" y="{cy0 + 1}" width="{cell - 2}" height="{cell - 2}" '
                    f'fill="{color}" opacity="0.18"/>'
                )
            weight = "bold" if is_exact else "normal"
            svg.append(
                f'<text x="{cx0 + cell / 2:.1f}" y="{cy0 + cell / 2 - 4:.1f}" font-size="14" '
                f'text-anchor="middle" fill="{color}" font-weight="{weight}">{glyph}</text>'
            )
            # orb number now bolds along with the glyph when exact - it
            # wasn't before, which made "exact" easy to miss at a glance
            svg.append(
                f'<text x="{cx0 + cell / 2:.1f}" y="{cy0 + cell - 6:.1f}" font-size="8" '
                f'text-anchor="middle" fill="#555" font-weight="{weight}">{asp.get("exact_orb", 0):.1f}\u00b0</text>'
            )

    bottom_y = grid_y0 + n * cell + 16
    for j in range(0, n):
        gx = grid_x0 + j * cell + cell / 2
        col_glyph = all_glyphs.get(present[j], "?")
        col_font = 15 if len(col_glyph) <= 1 else 10
        svg.append(
            f'<text x="{gx:.1f}" y="{bottom_y}" font-size="{col_font}" text-anchor="middle" '
            f'fill="#000">{col_glyph}</text>'
        )

    legend_y = bottom_y + 24
    svg.append(
        f'<text x="24" y="{legend_y}" font-size="11" fill="#555">'
        f'<tspan fill="{APPLYING_COLOR}" font-weight="bold">Розовый</tspan> - сходящиеся аспекты '
        f'(усиливаются), <tspan fill="{SEPARATING_COLOR}" font-weight="bold">голубой</tspan> - '
        f'расходящиеся (ослабевают).</text>'
    )
    svg.append(
        f'<text x="24" y="{legend_y + 15}" font-size="11" fill="#555">'
        f'Точные аспекты (орбис &lt; {EXACT_ORB_DEG:g}\u00b0) выделены жирным. '
        f'У планет: О-обитель, Э-экзальтация, И-изгнание, П-падение.</text>'
    )

    svg.append("</svg>")
    return "\n".join(svg)
