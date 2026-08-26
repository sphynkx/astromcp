"""
SVG natal chart wheel renderer for the /astro/chart.svg REST endpoint (see
app.py). Pure stdlib (math + colorsys) - no new dependency for this file.

Design brief (from the project owner, working from a ZET9 screenshot as a
loose visual reference - colors and general layout, explicitly NOT a
pixel-exact reproduction):
  - 12 colored zodiac-sign wedges around the rim
  - house cusp lines + Roman numerals
  - planets placed by ecliptic longitude, with position labels
  - aspect lines between planets, colored by aspect family (hard=red,
    soft=green), dashed/dotted by aspect "weight", and EXACT aspects
    (tight orb) drawn bold
  - header block (name/date/time/tz/place), side planet list, and a
    triangular aspect table at the bottom

Sign wedge colors: a hue-stepped pastel palette (hue = sign_index * 30
degrees, fixed saturation/lightness) computed with colorsys rather than
hand-picked hex values. This was chosen after visually comparing it
against the ZET9 reference image, where the 12 wedge colors turned out to
already be very close to a smooth hue rotation around the color wheel -
so a formula reproduces the *spirit* of that palette without claiming
pixel-matched hex values lifted from a screenshot (which would not have
been reliable to extract by eye anyway).

Chart rotation convention (standard Western tropical wheel, confirmed
against the reference image): Ascendant is drawn at the LEFT (180
degrees in standard screen-angle terms), and ecliptic longitude increases
COUNTERCLOCKWISE - so house numbers increase counterclockwise from the
Ascendant (I at left, II below it, IV/IC at the bottom, VII/Descendant at
the right, X/MC wherever it actually falls near the top, XII just above
the Ascendant). Descendant is therefore always exactly opposite the
Ascendant on screen (180 degrees apart) by construction, regardless of
house system - only the MC/IC axis position varies with house system and
latitude.
"""

import colorsys
import math
from typing import Any, Dict, List, Optional, Tuple

from .constants import SIGN_ORDER

# ==================== Reference tables ====================

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

# Display order for the side list and aspect table - the 10 classical
# points + Chiron + Lilith. Angles (Asc/Dsc/MC/IC) are drawn on the wheel
# itself but kept out of the aspect table to keep it to a manageable 12x12
# rather than 16x16.
CHART_POINTS = [
    "sun", "moon", "mercury", "venus", "mars", "jupiter", "saturn",
    "uranus", "neptune", "pluto", "chiron", "mean_lilith",
]

ANGLE_KEYS = ["asc", "mc", "dsc", "ic"]
ANGLE_LABELS = {"asc": "Asc", "mc": "MC", "dsc": "Dsc", "ic": "IC"}

HOUSE_ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"]

# aspect_deg -> (css_color, dash_array_or_None, base_stroke_width, family)
# "family" only used for the aspect-table cell background tint.
ASPECT_STYLE = {
    0:   ("#555555", None,        1.4, "neutral"),
    30:  ("#4a9c4a", "2,3",       0.9, "soft"),
    45:  ("#c23b3b", "1,3",       0.9, "hard"),
    60:  ("#4a9c4a", "6,3",       1.1, "soft"),
    90:  ("#c23b3b", "6,3",       1.3, "hard"),
    120: ("#4a9c4a", None,        1.3, "soft"),
    135: ("#c23b3b", "1,3",       0.9, "hard"),
    150: ("#b08a1e", "2,3",       0.9, "soft"),
    180: ("#c23b3b", None,        1.5, "hard"),
}
ASPECT_GLYPH = {
    0: "\u260C", 30: "\u26BA", 45: "\u2220", 60: "\u26B9", 90: "\u25A1",
    120: "\u25B3", 135: "\u29C3", 150: "\u26BB", 180: "\u260D",
}

EXACT_ORB_DEG = 1.0  # aspects tighter than this are drawn/highlighted bold

# ==================== Geometry / color helpers ====================


def _sign_pastel_color(sign_index: int) -> str:
    """Hue-stepped pastel palette - see module docstring."""
    hue = (sign_index * 30) / 360.0
    r, g, b = colorsys.hls_to_rgb(hue, 0.82, 0.55)
    return "#%02x%02x%02x" % (int(r * 255), int(g * 255), int(b * 255))


def _screen_point(cx: float, cy: float, radius: float, abs_pos: float, asc_abs_pos: float) -> Tuple[float, float]:
    """
    Maps an ecliptic longitude (abs_pos, 0-360) to an (x, y) screen point,
    with the Ascendant fixed at the left and longitude increasing
    counterclockwise - see module docstring for why.
    """
    theta_deg = 180 + (abs_pos - asc_abs_pos)
    theta = math.radians(theta_deg)
    x = cx + radius * math.cos(theta)
    y = cy - radius * math.sin(theta)
    return x, y


def _fmt_dm(position: float, sign: str) -> str:
    """Decimal degrees-within-sign -> '9\u264a34' style label."""
    deg = int(math.floor(position))
    minute = int(math.floor((position - deg) * 60 + 0.5))
    if minute == 60:
        minute = 0
        deg += 1
    glyph = SIGN_GLYPHS.get(sign, sign)
    return f"{deg}{glyph}{minute:02d}"


def _esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace('"', "&quot;"))


# ==================== Main builder ====================


def build_natal_chart_svg(
    report: Dict[str, Any],
    person_name: Optional[str] = None,
    place_label: Optional[str] = None,
) -> str:
    """
    report - the dict from public_api.build_full_report() (planets/houses/
    aspects/fixed_star_conjunctions/meta - same shape as the /astro JSON
    endpoint). person_name/place_label are free text for the header (the
    report's own meta doesn't carry a person's name, and only carries
    whichever of city/lat-lng was actually used, not necessarily a nice
    display string).

    Returns a complete standalone SVG document as a string.
    """
    planets = report.get("planets", {})
    houses = report.get("houses", {})
    aspects = report.get("aspects", [])
    conjunctions = report.get("fixed_star_conjunctions", [])
    meta = report.get("meta", {})

    asc = houses.get("asc")
    if not asc:
        raise ValueError("report has no 'asc' angle - cannot orient the wheel")
    asc_abs_pos = asc["abs_pos"]

    # ---- canvas layout ----
    width, height = 1000, 1300
    cx, cy = 480, 470
    r_outer = 340
    r_sign_inner = 300
    r_house_numeral = 365
    r_planet = 230
    r_planet_alt = 205  # alternate band for crowded planets
    r_tick_inner = 300  # ticks reach from r_planet up to the sign ring

    svg: List[str] = []
    svg.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="\'DejaVu Sans\', \'Segoe UI Symbol\', '
        f'\'Noto Sans Symbols\', Arial, sans-serif">'
    )
    svg.append(f'<rect x="0" y="0" width="{width}" height="{height}" fill="#ffffff"/>')

    # ---- header ----
    header_lines = []
    if person_name:
        header_lines.append(_esc(person_name))
    dt = meta.get("input_datetime", "")
    tz = meta.get("tz_used", "")
    header_lines.append(_esc(f"{dt}  ({tz})".strip()))
    if place_label:
        header_lines.append(_esc(place_label))
    elif meta.get("resolved_city_name"):
        header_lines.append(_esc(str(meta["resolved_city_name"])))
    lat, lng = meta.get("lat"), meta.get("lng")
    if lat is not None and lng is not None:
        header_lines.append(f"{lat:.4f}, {lng:.4f}  \u2022  {_esc(str(meta.get('house_system', '')))}")

    y = 34
    weights = ["bold", "normal", "normal", "normal"]
    sizes = [20, 15, 15, 13]
    for i, line in enumerate(header_lines[:4]):
        svg.append(
            f'<text x="24" y="{y}" font-size="{sizes[min(i, 3)]}" '
            f'font-weight="{weights[min(i, 3)]}" fill="#111">{line}</text>'
        )
        y += sizes[min(i, 3)] + 8

    # ---- sign ring (12 pastel wedges) ----
    for i, sign in enumerate(SIGN_ORDER):
        sign_start_abs = i * 30
        theta1 = 180 + (sign_start_abs - asc_abs_pos)
        theta2 = 180 + (sign_start_abs + 30 - asc_abs_pos)
        x1o, y1o = _screen_point(cx, cy, r_outer, sign_start_abs, asc_abs_pos)
        x2o, y2o = _screen_point(cx, cy, r_outer, sign_start_abs + 30, asc_abs_pos)
        x1i, y1i = _screen_point(cx, cy, r_sign_inner, sign_start_abs, asc_abs_pos)
        x2i, y2i = _screen_point(cx, cy, r_sign_inner, sign_start_abs + 30, asc_abs_pos)
        color = _sign_pastel_color(i)
        # wedge sweeps 30deg counterclockwise on screen, i.e. large-arc=0,
        # sweep-flag=0 for our y-flipped (CCW-positive) convention
        path = (
            f'M {x1o:.1f},{y1o:.1f} A {r_outer},{r_outer} 0 0 0 {x2o:.1f},{y2o:.1f} '
            f'L {x2i:.1f},{y2i:.1f} A {r_sign_inner},{r_sign_inner} 0 0 1 {x1i:.1f},{y1i:.1f} Z'
        )
        svg.append(f'<path d="{path}" fill="{color}" stroke="#888" stroke-width="0.6"/>')
        # sign glyph centered in the wedge
        mid_abs = sign_start_abs + 15
        gx, gy = _screen_point(cx, cy, (r_outer + r_sign_inner) / 2, mid_abs, asc_abs_pos)
        svg.append(
            f'<text x="{gx:.1f}" y="{gy:.1f}" font-size="22" text-anchor="middle" '
            f'dominant-baseline="central" fill="#222">{SIGN_GLYPHS[sign]}</text>'
        )

    svg.append(f'<circle cx="{cx}" cy="{cy}" r="{r_outer}" fill="none" stroke="#4a7fa8" stroke-width="1.5"/>')
    svg.append(f'<circle cx="{cx}" cy="{cy}" r="{r_sign_inner}" fill="none" stroke="#4a7fa8" stroke-width="1.5"/>')

    # ---- house cusp lines + Roman numerals ----
    for i in range(12):
        house_key = f"house_{i + 1}"
        h = houses.get(house_key)
        if not h:
            continue
        abs_pos = h["abs_pos"]
        x1, y1 = _screen_point(cx, cy, r_planet_alt - 40, abs_pos, asc_abs_pos)
        x2, y2 = _screen_point(cx, cy, r_sign_inner, abs_pos, asc_abs_pos)
        is_angle_axis = i in (0, 3, 6, 9)  # I/IV/VII/X = Asc/IC/Dsc/MC
        svg.append(
            f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="{"#3a5a8a" if is_angle_axis else "#c9a0c9"}" '
            f'stroke-width="{1.6 if is_angle_axis else 0.8}"/>'
        )
        nx, ny = _screen_point(cx, cy, r_house_numeral, abs_pos, asc_abs_pos)
        svg.append(
            f'<text x="{nx:.1f}" y="{ny:.1f}" font-size="14" text-anchor="middle" '
            f'dominant-baseline="central" fill="#333">{HOUSE_ROMAN[i]}</text>'
        )

    # explicit angle labels (Asc/Dsc/MC/IC) just outside the numeral ring
    for key in ANGLE_KEYS:
        a = houses.get(key)
        if not a:
            continue
        lx, ly = _screen_point(cx, cy, r_house_numeral + 26, a["abs_pos"], asc_abs_pos)
        svg.append(
            f'<text x="{lx:.1f}" y="{ly:.1f}" font-size="13" font-weight="bold" '
            f'text-anchor="middle" dominant-baseline="central" fill="#1a3a6a">'
            f'{ANGLE_LABELS[key]}</text>'
        )

    # decorative center circle
    svg.append(f'<circle cx="{cx}" cy="{cy}" r="18" fill="none" stroke="#3a3a8a" stroke-width="1.5"/>')

    # ---- planet placement (with light crowding avoidance) ----
    planet_screen: Dict[str, Tuple[float, float]] = {}
    ordered = sorted(
        ((pid, planets[pid]) for pid in CHART_POINTS if pid in planets),
        key=lambda kv: kv[1]["abs_pos"],
    )
    prev_abs = None
    alt_band = False
    for pid, pdata in ordered:
        abs_pos = pdata["abs_pos"]
        if prev_abs is not None:
            gap = min((abs_pos - prev_abs) % 360, (prev_abs - abs_pos) % 360)
            alt_band = gap < 6
        radius = r_planet_alt if alt_band else r_planet
        prev_abs = abs_pos

        tick_x1, tick_y1 = _screen_point(cx, cy, radius + 14, abs_pos, asc_abs_pos)
        tick_x2, tick_y2 = _screen_point(cx, cy, r_tick_inner, abs_pos, asc_abs_pos)
        svg.append(
            f'<line x1="{tick_x1:.1f}" y1="{tick_y1:.1f}" x2="{tick_x2:.1f}" y2="{tick_y2:.1f}" '
            f'stroke="#999" stroke-width="0.6"/>'
        )
        px, py = _screen_point(cx, cy, radius, abs_pos, asc_abs_pos)
        planet_screen[pid] = (px, py)
        glyph = PLANET_GLYPHS.get(pid, "?")
        svg.append(
            f'<text x="{px:.1f}" y="{py:.1f}" font-size="20" text-anchor="middle" '
            f'dominant-baseline="central" fill="#000">{glyph}</text>'
        )
        if pdata.get("retrograde"):
            svg.append(
                f'<text x="{px + 11:.1f}" y="{py - 9:.1f}" font-size="9" fill="#a03030">R</text>'
            )

    # ---- aspect lines (chords between planet points) ----
    for asp in aspects:
        pa, pb = asp.get("point_a"), asp.get("point_b")
        if pa not in planet_screen or pb not in planet_screen:
            continue  # only draw planet-planet aspects on the wheel itself
        style = ASPECT_STYLE.get(asp.get("aspect_deg"))
        if not style:
            continue
        color, dash, width, _family = style
        is_exact = asp.get("exact_orb", 99) < EXACT_ORB_DEG
        x1, y1 = planet_screen[pa]
        x2, y2 = planet_screen[pb]
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        svg.append(
            f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="{color}" stroke-width="{width * (1.8 if is_exact else 1)}"'
            f'{dash_attr} opacity="{1.0 if is_exact else 0.75}"/>'
        )

    # ==================== side planet list ====================
    list_x = 860
    ly = 60
    svg.append(f'<text x="{list_x}" y="{ly}" font-size="14" font-weight="bold" fill="#111">Планеты</text>')
    ly += 22
    for pid in CHART_POINTS:
        pdata = planets.get(pid)
        if not pdata:
            continue
        glyph = PLANET_GLYPHS.get(pid, "?")
        label = _fmt_dm(pdata["position"], pdata["sign"])
        retro = " R" if pdata.get("retrograde") else ""
        star_note = ""
        for conj in conjunctions:
            if conj.get("point") == pid:
                star_note = f"  \u2605{_esc(str(conj.get('star', '')))}"
                break
        svg.append(
            f'<text x="{list_x}" y="{ly}" font-size="13" fill="#000">'
            f'{glyph} {label}{retro}{star_note}</text>'
        )
        ly += 19

    ly += 10
    svg.append(f'<text x="{list_x}" y="{ly}" font-size="14" font-weight="bold" fill="#111">Углы</text>')
    ly += 22
    for key in ANGLE_KEYS:
        a = houses.get(key)
        if not a:
            continue
        label = _fmt_dm(a["position"], a["sign"])
        svg.append(f'<text x="{list_x}" y="{ly}" font-size="13" fill="#000">{ANGLE_LABELS[key]} {label}</text>')
        ly += 19

    # ==================== aspect table (triangular grid) ====================
    table_top = 860
    cell = 34
    label_col_w = 30
    present = [pid for pid in CHART_POINTS if pid in planets]
    n = len(present)
    aspect_lookup: Dict[frozenset, Dict[str, Any]] = {}
    for asp in aspects:
        pa, pb = asp.get("point_a"), asp.get("point_b")
        if pa in present and pb in present:
            aspect_lookup[frozenset((pa, pb))] = asp

    svg.append(
        f'<text x="24" y="{table_top - 16}" font-size="14" font-weight="bold" fill="#111">'
        f'Таблица аспектов</text>'
    )
    # column headers (glyphs) along the top, row headers along the left -
    # only the upper triangle is filled in, matching a standard aspectarian
    grid_x0 = 24 + label_col_w
    grid_y0 = table_top
    for j, pid in enumerate(present):
        gx = grid_x0 + j * cell + cell / 2
        svg.append(
            f'<text x="{gx:.1f}" y="{grid_y0 - 8}" font-size="15" text-anchor="middle" '
            f'fill="#000">{PLANET_GLYPHS.get(pid, "?")}</text>'
        )
    for i, pid in enumerate(present):
        ry = grid_y0 + i * cell + cell / 2
        svg.append(
            f'<text x="{24 + label_col_w - 8}" y="{ry:.1f}" font-size="15" text-anchor="end" '
            f'dominant-baseline="central" fill="#000">{PLANET_GLYPHS.get(pid, "?")}</text>'
        )
        for j, pid2 in enumerate(present):
            cx0 = grid_x0 + j * cell
            cy0 = grid_y0 + i * cell
            svg.append(
                f'<rect x="{cx0}" y="{cy0}" width="{cell}" height="{cell}" '
                f'fill="none" stroke="#ddd" stroke-width="0.5"/>'
            )
            if j <= i:
                continue  # upper triangle only
            asp = aspect_lookup.get(frozenset((pid, pid2)))
            if not asp:
                continue
            style = ASPECT_STYLE.get(asp.get("aspect_deg"))
            if not style:
                continue
            color, _dash, _w, _family = style
            is_exact = asp.get("exact_orb", 99) < EXACT_ORB_DEG
            glyph = ASPECT_GLYPH.get(asp.get("aspect_deg"), "?")
            if is_exact:
                svg.append(
                    f'<rect x="{cx0 + 1}" y="{cy0 + 1}" width="{cell - 2}" height="{cell - 2}" '
                    f'fill="{color}" opacity="0.15"/>'
                )
            svg.append(
                f'<text x="{cx0 + cell / 2:.1f}" y="{cy0 + cell / 2 - 4:.1f}" font-size="14" '
                f'text-anchor="middle" fill="{color}" '
                f'font-weight="{"bold" if is_exact else "normal"}">{glyph}</text>'
            )
            svg.append(
                f'<text x="{cx0 + cell / 2:.1f}" y="{cy0 + cell - 6:.1f}" font-size="8" '
                f'text-anchor="middle" fill="#555">{asp.get("exact_orb", 0):.1f}\u00b0</text>'
            )

    # legend
    legend_y = grid_y0 + n * cell + 26
    svg.append(
        f'<text x="24" y="{legend_y}" font-size="11" fill="#555">'
        f'Красный - жёсткие аспекты, зелёный - мягкие, чёрный - соединение. '
        f'Точные аспекты (орбис &lt; {EXACT_ORB_DEG:g}\u00b0) выделены жирным и подложкой.</text>'
    )

    svg.append("</svg>")
    return "\n".join(svg)
