#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Regenerates engine/ussr_city_table.py from a plain-text city list in the
format described below. Source of truth for that file: NEVER hand-edit
ussr_city_table.py directly - fix the source list and rerun this script,
so every correction stays traceable back to an actual read of the book.

INPUT FORMAT (one or more text files, default: all *.txt in this
directory's citylist_source/ subfolder, see SRC_GLOB below): any line
starting with "#" or "=" is ignored (comments/page markers); every other
non-blank line holds exactly two entries, space-separated:
    NAME... CODE LATnMM LONeMM TABLE_NUM   NAME... CODE LATnMM LONeMM TABLE_NUM
  - NAME: one or more Cyrillic words (hyphens allowed)
  - CODE: 2-4 uppercase Latin letters (the book's own region code)
  - LAT: DDnMM (degrees north, 00-90, then literal "n", then minutes 00-59)
  - LON: DD(D)eMM (degrees east, 00-180, then literal "e", then minutes)
  - TABLE_NUM: 1-2 digits, a key into ussr_time_tables.TABLES (after the
    TABLE_REDIRECTS fixup below)
This is exactly the format produced by this project's OCR+repair pass
(see the chat history of the astromcp project for the full extraction
story: djvu -> tesseract OCR -l rus+eng --psm 6 -> deterministic n/e
digit-run repair -> full manual read-through against the book's page
images) - this script does not re-derive that format, only parses it.

A city name maps to a LIST of candidates, not a single value, because a
meaningful fraction of names in this book are genuinely ambiguous - more
than one real place shares the name (e.g. "Актас"/"Акташ"/"Актогай" each
appear more than once with different coordinates and table numbers).
engine/ussr_time_tables.py's resolver disambiguates by nearest
coordinates at lookup time; this generator never guesses among them.

EXCLUDED_ENTRIES below lists specific (name, code) pairs that stayed
genuinely unresolved after OCR + manual review (an "l" vs "1" ambiguity,
a malformed region code, or leftover corruption) - these are dropped
from the generated table entirely rather than shipped with a guess.
Extend this list (and rerun) if a future review pass finds more.
"""
import glob
import os
import re

_HERE = os.path.dirname(os.path.abspath(__file__))
SRC_GLOB = os.path.join(_HERE, "citylist_source", "*.txt")
OUT = os.path.join(_HERE, "..", "engine", "ussr_city_table.py")

# The source book prints tables "40" and "45" as forward-reference-only
# rows ("40 RUAL - см.70", "45 RUKE - см.75", etc. - see
# ussr_time_tables.py's TABLES comments) rather than inline data: the
# city list's own table-number column still says "40"/"45", but the
# actual chronological data lives under a different number depending on
# region code. Resolved here so CITY_TABLE never points at a table
# number that doesn't exist.
TABLE_REDIRECTS = {
    ("40", "RUAL"): "70",
    ("40", "RUNS"): "71",
    ("40", "RUTO"): "72",
    ("45", "RUAL"): "74",
    ("45", "RUKE"): "75",
    ("45", "RUNS"): "76",
    ("45", "RUTO"): "77",
    ("45", "RUTU"): "78",
}
# One observed typo in the corrected source: a single table-40 entry has
# region code "RYTO" where context (it's the only aberrant code among
# ~38 table-40 entries, and every other one is RUAL/RUNS/RUTO) makes
# "RUTO" the obvious intended value - a U/Y OCR swap.
CODE_TYPO_FIXES = {
    "RYTO": "RUTO",
}

# (name, region_code) of the SPECIFIC entries the validator could not
# confirm - excluded individually so a clean entry sharing a line with a
# bad one isn't thrown away too. See chat message for why each one
# couldn't be auto-fixed (l/1 ambiguity, malformed code, or leftover
# corruption).
EXCLUDED_ENTRIES = {
    ("Акмолинск", "KZCE"),
    ("Бахмач", "UVACG"),
    ("Бекабад", "UZTA"),
    ("Вертневка", "UACG"),
    ("Воловец", "UAZK"),
    ("Возрождение", "RUSA"),
    ("Вуктыл", "RUKO"),
    ("Голобы", "UVAVO"),
    ("Знаменск", "RUKL"),
    ("Кокошкино", "RUMO"),
    ("Короча", "RUBE"),
    ("Красное-на-Волге", "RUKS"),
    ("Макаров", "RUSH"),
    ("Орджоникидзе", "GE"),
    ("Павловская", "КГЛВ"),
}


def dms_to_decimal(token: str, kind: str) -> float:
    sep = "n" if kind == "lat" else "e"
    m = re.match(rf"^(\d{{2,3}}){sep}(\d{{2}})$", token)
    if not m:
        raise ValueError(f"bad {kind} token: {token!r}")
    deg, mins = int(m.group(1)), int(m.group(2))
    return round(deg + mins / 60.0, 4)


def main():
    entries = []  # (name, region_code, lat, lon, table_id)
    excluded = []

    src_files = sorted(glob.glob(SRC_GLOB))
    if not src_files:
        raise SystemExit(
            f"No source files matched {SRC_GLOB!r} - put the corrected "
            "city-list text file(s) there first (see this script's "
            "docstring for the expected format)."
        )

    for src_path in src_files:
      with open(src_path, encoding="utf-8") as f:
        for lineno, raw in enumerate(f, 1):
            line = raw.rstrip("\n")
            if not line.strip() or line.startswith("#") or line.startswith("==="):
                continue
            tokens = line.split()
            pending = []
            i, n = 0, len(tokens)
            row_entries = []
            ok = True
            while i < n:
                tok = tokens[i]
                if re.search(r"\d", tok):
                    j = i
                    run = []
                    while j < n and re.search(r"\d", tokens[j]):
                        run.append(tokens[j])
                        j += 1
                    if len(run) != 3 or not pending:
                        ok = False
                        break
                    *name_words, code = pending
                    row_entries.append((" ".join(name_words), code, run[0], run[1], run[2]))
                    pending = []
                    i = j
                    continue
                pending.append(tok)
                i += 1
            if not ok or pending:
                excluded.append((lineno, line))
                continue
            for (name, code, lat_tok, lon_tok, table_tok) in row_entries:
                if (name, code) in EXCLUDED_ENTRIES:
                    excluded.append((lineno, f"{name} {code} {lat_tok} {lon_tok} {table_tok}"))
                    continue
                try:
                    lat = dms_to_decimal(lat_tok, "lat")
                    lon = dms_to_decimal(lon_tok, "lon")
                except ValueError:
                    excluded.append((lineno, line))
                    continue
                table_id = str(int(table_tok)).zfill(2)
                code = CODE_TYPO_FIXES.get(code, code)
                redirect = TABLE_REDIRECTS.get((table_id, code))
                if redirect is not None:
                    table_id = redirect
                entries.append((name, code, lat, lon, table_id))

    print(f"Parsed entries: {len(entries)}")
    print(f"Excluded lines: {len(excluded)}")
    for lineno, line in excluded:
        print(f"  L{lineno}: {line}")

    # group by lowercased name
    by_name = {}
    for (name, code, lat, lon, table_id) in entries:
        key = name.lower()
        by_name.setdefault(key, []).append((code, lat, lon, table_id))

    dupes = {k: v for k, v in by_name.items() if len(v) > 1}
    print(f"Distinct names: {len(by_name)}, ambiguous (>1 candidate): {len(dupes)}")

    with open(OUT, "w", encoding="utf-8") as out:
        out.write(
            '"""\n'
            "Auto-generated from the Zaytsev & Kutalev reference book's own\n"
            "city-coordinate list (book pages 12-44), via OCR + deterministic\n"
            "repair + a full manual read-through against the book's page\n"
            "images (see engine/ussr_time_tables.py's module docstring for\n"
            "the full extraction story). DO NOT hand-edit this file - fix\n"
            "tools/citylist_source/*.txt and rerun\n"
            "tools/generate_ussr_city_table.py instead, so corrections stay\n"
            "traceable to an actual read of the book.\n"
            "\n"
            f"{len(entries)} entries covering {len(by_name)} distinct city names\n"
            f"({len(dupes)} names are ambiguous - more than one real place in\n"
            "the book shares that name, e.g. \"Актас\"/\"Акташ\"/\"Актогай\" each\n"
            "appear more than once with different coordinates and different\n"
            "table numbers). CITY_TABLE therefore maps each name to a LIST of\n"
            "candidates; engine/ussr_time_tables.py's resolver picks among\n"
            "them by nearest coordinates to whatever lat/lng the caller gave,\n"
            "and refuses to guess if it can't confidently narrow it to one.\n"
            "\n"
            f"{len(excluded)} entries from the source list were excluded\n"
            "rather than shipped with a guess - each had an unresolved l/1\n"
            "OCR ambiguity, a malformed region code, or leftover corruption\n"
            "that neither OCR nor the project owner's own read-through could\n"
            "pin down with confidence. See this generator script's\n"
            "EXCLUDED_ENTRIES list for the itemized reasons.\n"
            '"""\n\n'
            "from typing import Dict, List, NamedTuple\n\n\n"
            "class CityEntry(NamedTuple):\n"
            "    region_code: str\n"
            "    lat: float   # decimal degrees, +north\n"
            "    lon: float   # decimal degrees, +east\n"
            "    table_id: str  # key into ussr_time_tables.TABLES\n\n\n"
            "CITY_TABLE: Dict[str, List[CityEntry]] = {\n"
        )
        for key in sorted(by_name.keys()):
            candidates = by_name[key]
            cand_str = ", ".join(
                f'CityEntry({code!r}, {lat}, {lon}, {table_id!r})'
                for (code, lat, lon, table_id) in candidates
            )
            out.write(f"    {key!r}: [{cand_str}],\n")
        out.write("}\n")

    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
