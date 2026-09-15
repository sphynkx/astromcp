# astromcp

MCP (Model Context Protocol) server exposing precise astrological chart
calculations - natal charts, transits, secondary progressions, solar arc
directions, solar/lunar returns, profections, primary directions,
relocated transits, and a suite of documented birth-time rectification
methods - for use as tools by an LLM assistant. Built on kerykeion
(https://github.com/g-battaglia/kerykeion), which wraps the Swiss
Ephemeris for astronomical accuracy.

## Why this exists

Off-the-shelf AI astrology workflows tend to hallucinate planetary
positions, use unstated/inconsistent orbs, and mishandle timezones
(especially historical ones). This service gives an LLM assistant a real
ephemeris to call instead of guessing - every number returned traces back
to a Swiss Ephemeris calculation, not to the model's training data.

## Architecture

    Claude (claude.ai / API) --MCP over HTTPS--> nginx reverse proxy
                                              --> uvicorn (127.0.0.1:8765)
                                                  --> app.py (tool registration)
                                                      --> engine/ (all logic)

Two interfaces share this one process and port:

- **MCP tools** (streamable-http transport) - added to Claude as a
  connector, not fetched as a plain URL.
- **`GET /astro` and `GET /astro/chart.svg`** - plain REST endpoints,
  registered via `@mcp.custom_route` in `app.py`, for non-MCP callers
  such as MediaWiki (see "REST endpoint" and "Integration with
  MediaWiki" below). Reachable through a **second, independent** nginx
  proxy block - typically on a different domain (e.g. a wiki's own
  server), forwarding straight to this same backend port. Don't confuse
  that wiki-side proxy block with the one documented under "Hosting"
  below, which is for this project's own MCP domain.

## Project structure

    astromcp/
    ├── app.py                  # MCP entry point: tool registration only
    ├── README.md
    ├── BIBLIOGRAPHY.md          # full source list backing help_texts/ and TECHNIQUE_STATUS.md
    ├── TECHNIQUE_STATUS.md      # per-technique implementation status
    ├── help_texts/             # LLM-facing methodology guides, read via the help() tool
    │   ├── overview.md
    │   ├── rectification.md
    │   └── horary.md
    ├── install/
    │   ├── requirements.txt
    │   ├── astromcp.service    # systemd unit
    │   ├── .env.example        # documents all tunable settings
    │   └── Mediawiki/          # everything MediaWiki-side - see
    │                           # install/Mediawiki/README.md for all of it
    │       ├── README.md
    │       ├── Module_Astrodata.lua  # calls astromcp's own /astro REST endpoint
    │       ├── Module_ParseType.lua  # standalone, no astromcp calls
    │       ├── Deathmon.lua          # standalone, no astromcp calls
    │       └── purge_deathmon.sh
    └── engine/
        ├── __init__.py
        ├── config.py           # .env-driven settings, with built-in defaults
        ├── constants.py        # structural constants + traditional sign rulerships
        ├── chart.py            # subject construction, serialization, tz helpers
        ├── aspects.py          # aspect geometry, applying/separating/exact
        ├── techniques.py       # transit / secondary progression / solar arc /
        │                       # solar return / lunar return / profection /
        │                       # primary direction (zodiacal) / relocated transit
        ├── trutina.py          # Trutine of Hermes (classical rectification, no events needed)
        ├── scan.py             # rectif_scan: sweeps candidate birth times
        ├── criteria.py         # scan wrappers for the criterion-based methods:
        │                       # Grishchenyuk (three movements) / Timoshenko /
        │                       # Bonatti / Herich - imports bonatti.py/herich.py
        │                       # for the latter two's actual check logic
        ├── bonatti.py          # Bonatti's method - check logic used by criteria.py
        ├── herich.py           # Herich's number - check logic used by criteria.py
        ├── clustering.py       # Israitel/Brady degree-clustering rectification
        ├── jones_patterns.py   # Jones planetary-pattern classification (bundle/
        │                       # bowl/bucket/locomotive/splash/splay/seesaw/mixed)
        ├── arabic_parts.py     # Lot FORMULAS: Part of Fortune + Kutalev's general
        │                       # Lot formula - see lots.py for the generic engine
        │                       # that turns a formula into a full point
        ├── lots.py             # generic Lot/Arabic Part framework: LOT_REGISTRY
        │                       # (name -> formula) + compute_lot (formula -> full
        │                       # point with house placement, numeric speed, ready
        │                       # to feed into the same aspect engine as a planet)
        ├── relations.py        # "elements of house" - see houses.py
        ├── houses.py           # house ruler/co-ruler/occupant lookups, and
        │                       # house_number_for_longitude (used by lots.py for
        │                       # points that aren't one of kerykeion's own objects)
        ├── horary.py           # horary chart judgment: radicality, significators,
        │                       # dignity, reception, void-of-course Moon, translation/
        │                       # collection of light, prohibition/frustration/
        │                       # refranation, verdict - see help_texts/horary.md
        ├── jobs.py             # async job registry (Redis or in-memory) with
        │                       # sectioned retrieval for large pipeline results
        ├── help.py             # reads help_texts/*.md on demand
        ├── tools.py            # MCP tool implementations (no MCP dependency itself)
        ├── display.py          # human-readable console summaries
        ├── geocode.py          # offline city->coords (geonamescache) and coords->tz
        │                       # (timezonefinder) lookups - used only by public_api.py
        ├── fixed_stars.py      # fixed-star positions via pyswisseph, used only by
        │                       # public_api.py - not used by any rectification tool
        ├── public_api.py       # builds the flat JSON for the /astro REST endpoint
        ├── svg_chart.py        # builds the SVG for /astro/chart.svg
        └── photo_fetch.py      # fetches+inlines the optional chart-header photo as a data: URI

`app.py` deliberately contains no astrological logic - it only registers
MCP tools and delegates to `engine/tools.py`. This keeps the transport layer
(MCP/FastMCP specifics) separate from the domain logic, which can be read,
modified, or reused independently.

## Tools exposed

| Tool | Purpose |
|---|---|
| `rectif_chart` | Full chart (planets, houses, angles) for one date/time/place |
| `rectif_chart_batch` | Batch version of the above |
| `rectif_technique` | One technique - transit / secondary progression / solar arc direction / solar return / lunar return / profection / primary direction (zodiacal) / relocated transit - with aspects to the natal chart |
| `rectif_technique_batch` | Batch version of the above |
| `rectif_scan` | Sweeps candidate birth times against a list of events. Its score/ranking fields are not a valid rectification result on their own - see `help_texts/rectification.md`'s "Absolute rule: never invent a scoring or weighting scheme" before using this tool's output for anything beyond a convenience sweep mechanism |
| `rectif_scan_start` / `rectif_scan_result` | Async version of rectif_scan (submit + poll) - use for large scans or `technique="solar_return"`, which can otherwise exceed MCP/proxy timeouts |
| `rectif_trutina` | Trutine of Hermes: fast, direct classical rectification via the conception (epoch) chart - needs no life events at all |
| `rectif_movements_scan` | Grishchenyuk's literal "3 movements" criterion (>=2 of 3 concordant) - returns qualifying time windows, not a ranking |
| `rectif_timoshenko_scan` | Timoshenko's 4-condition bidirectional aspect test (ruler+cusp each send AND receive) - returns qualifying time windows |
| `rectif_bonatti_scan` | Bonatti's method, reproduced literally - a weak auxiliary check per the source's own framing, not a primary technique |
| `rectif_herich_scan` | Herich's number (Paul von Gerich) - a weak auxiliary check, the source's own author acknowledges up to 8deg uncertainty |
| `rectif_degree_clustering` | Brady's graphic/Israitel's condensation method - histograms transiting-degree hits across many events, converts top peaks to candidate times |
| `rectif_pipeline` / `rectif_pipeline_start` + `rectif_pipeline_result` | **Full rectification pipeline** - runs Trutina + movements_scan for every event + intersection + auxiliary checks + direct candidate verification, all server-side in one call. `rectif_pipeline_result` supports sectioned retrieval (`section=` parameter) to stay under MCP's 1 MB limit |
| `horary_chart` | Builds and judges a horary chart (a question asked at a specific moment/place) - radicality, significators, dignity, reception, void-of-course Moon, translation/collection of light, prohibition/frustration/refranation, Yes/No verdict. See `help("horary")` |
| `help` | Reads a methodology/usage guide from `help_texts/*.md` - see below |
| `ping` | Connectivity test |

Full parameter reference is in the docstrings in `app.py` (visible to the
MCP client, including the LLM, at call time).

## REST endpoint for non-MCP callers (MediaWiki, etc.)

`GET /astro` is a plain HTTP endpoint alongside the MCP tools above,
registered via `@mcp.custom_route` in `app.py` - it runs in the same
process, on the same host/port, so no separate service or reverse-proxy
change is needed. It answers a different question than the MCP tools do:
"give me everything the ephemeris knows about this date/time/place" in one
call, in a flat JSON shape meant for consumers like MediaWiki's
[External Data](https://www.mediawiki.org/wiki/Extension:External_Data)
extension, which needs simple dotted/array paths into the response rather
than kerykeion's native field names.

    GET /astro?date=23.11.1993&time=14:30&lat=50.45&lon=30.52
    GET /astro?date=23.11.1993&time=14:30&city=Kyiv

Response shape (see `engine/public_api.py` for the full docstring):

    {
      "planets": {"sun": {...}, "moon": {...}, ...},
      "houses":  {"asc": {...}, "mc": {...}, "house_1": {...}, ..., "house_12": {...}},
      "aspects": [{"point_a": "...", "point_b": "...", "aspect_deg": ..., "exact_orb": ..., "status": "..."}],
      "lots": {"part_of_fortune": {"abs_pos": ..., "sign": ..., "house": ..., "speed": ...}, ...},
      "is_day_birth": true,
      "fixed_stars": {"Regulus": {...}, ...},
      "fixed_star_conjunctions": [{"star": "...", "point": "...", "orb": ...}],
      "meta": {"schema_version": 2, ...}
    }

### Lots / Arabic Parts

`engine/lots.py` is a generic framework, not a hardcoded Part of Fortune
special-case: a Lot is a name registered in `LOT_REGISTRY` pointing at a
FORMULA (`(raw: dict) -> float`, an ecliptic longitude - `raw` being the
full kerykeion dump, so a formula can reference any point/house/cusp and
do whatever arithmetic or conditional logic the theory calls for). The
engine (`compute_lot`) turns whatever a formula returns into a full point
- sign, house placement (`houses.house_number_for_longitude`, since a
Lot isn't one of kerykeion's own objects and has no `.house` field the
way a planet does), and a NUMERIC speed estimate (the same formula
evaluated against the chart recomputed 10 minutes later, one shared
extra ephemeris call per request regardless of how many Lots are
requested) - so aspects.compute_aspects() can tell applying from
separating for it same as any planet.

Only `part_of_fortune` is registered today. Request others via
`&lots=name1,name2` (default is just `part_of_fortune` if omitted); an
unregistered name returns a 400 naming what IS registered rather than
silently doing nothing. Adding a new Lot is a code change (write a
formula function, add one line to `LOT_REGISTRY` or call
`register_lot()`) - there's no way to submit an arbitrary formula via the
HTTP API itself, on purpose: `arabic_parts.compute_arabic_part` (Kutalev's
general formula) needs a ruler/significator choice that this project's
own methodology treats as a reasoned judgment call per case (see
`help_texts/rectification.md`), not something to accept unreviewed from
a query string.

Only ONE house system is computed per call (default from
`ASTROMCP_HOUSE_SYSTEM`, override with `&house_system=K` etc.) - mixing
several systems' cusps into one flat response would make it ambiguous
which system a given cusp or aspect belongs to. Call the endpoint twice
with different `house_system` values if a page genuinely needs both.

**Discovering the parameters**: `GET /astro` with no query string at all
returns the parameter reference (`ASTROMCP_HELP_DOC` in `app.py`) as JSON
instead of an error. Any request that has params but is invalid or
incomplete (missing `date`, unparsable `time`, unknown city, ...) returns
`{"error": ..., "help": {...}}` with that same reference attached.

City-name lookup (`&city=...`) and timezone auto-resolution (when neither
`&tz=` nor `&tz_offset=` is given) are both **offline** - `geonamescache`
for the former, `timezonefinder` for the latter - no live external
geocoding call happens. `&city=` accepts English or Russian input via a
curated exonym table (`RU_CITY_EXONYMS` in `engine/geocode.py`),
geonamescache's own bundled alternate names, and a transliteration
fallback. `&country_code=` likewise accepts ISO2, or a country name in
English or Russian (resolved via Babel's CLDR data, plus a curated
`RU_COUNTRY_EXONYMS` table for common Russian abbreviations CLDR doesn't
carry, like США/РФ). Real caveats, spelled out in full in
`engine/geocode.py`'s own docstring: city-name matching is a
population-based heuristic that can pick the wrong same-named town, and
the auto-resolved timezone is the *modern* zone boundary only - **not
safe for historical dates** (see `help_texts/rectification.md`'s
timezone section). For anything precise, pass `lat`/`lon` and
`tz`/`tz_offset` explicitly.

### SVG chart wheel: `GET /astro/chart.svg`

Same date/time/location/timezone/house_system parameters as `/astro`
above, rendered as a standalone SVG natal chart wheel instead of JSON.

    GET /astro/chart.svg?date=23.11.1993&time=14:30&city=Kyiv
      &name=Displayed+person+name
      &place=Displayed+place+name
      &filename=Some_name.svg

`name`/`place` are free-text header labels. `filename` only sets the
`Content-Disposition` header so a browser's "save as" proposes that name
- it does not change the response body, and nothing is written to disk
on the server.

Layout and colors follow the style and spirit of ZET9 (not a pixel-exact
reproduction): a sign-wedge color wheel, a house ring with planets placed
inside it, Ascendant/MC markers, a hard/soft aspect color split on the
wheel's chords, essential-dignity letters next to each planet, and an
aspect table colored by applying/separating. Every planet, cusp, and
aspect chord carries a native SVG `<title>` for hover tooltips. Visual
parameters (`SIGN_COLORS`, `HOUSE_COLORS`, and related tables in
`engine/svg_chart.py`) are plain Python dicts, edited directly in that
file; house system, orb tables, and other behavioral defaults are tuned
via `.env` (see `install/.env.example`) without touching code.

Embedding a photo (`&photo_url=...`) requires the image to be fetched and
inlined server-side as a `data:` URI (`engine/photo_fetch.py`) rather than
referenced by its original URL - an SVG loaded as an HTML `<img>` source
cannot load its own external resources, a real browser restriction, not
a bug in this service. When integrating with MediaWiki specifically, see
`install/Mediawiki/README.md` for how the Lua module resolves an
uploaded file's fetchable URL before passing it here.

Errors return a small SVG containing the error text (with the correct
HTTP status code) rather than JSON, since an `<img>`/external-image
consumer has nowhere to display JSON error text.

## Integration with MediaWiki

Everything MediaWiki-side (Lua modules, ExternalData/LocalSettings.php
configuration, template-calling conventions, the Wikidata death-date
monitoring setup with its bot/cron pieces) has moved to
[`install/Mediawiki/README.md`](install/Mediawiki/README.md) - it's a
big enough topic, spanning three independent Lua modules and one shell
script, to warrant its own document rather than a section of this one.

### How the LLM client learns the methodology

Two mechanisms work together:

1. **`instructions`** on the `FastMCP(...)` constructor in `app.py` - sent
   automatically to the client during the MCP `initialize` handshake,
   before any tool is called. It's kept short: essentially "call `help()`
   before doing rectification work."
2. **`help_texts/*.md`**, read on demand via the `help` tool. This is
   where the actual accumulated methodology lives. Add a new topic by
   adding a new `help_texts/<topic>.md` file; `help()` with no arguments
   (or an unrecognized topic) lists whatever topics currently exist, so
   nothing needs to be hardcoded elsewhere when a topic is added.

This exists so that methodology learned the hard way in one chat session
isn't lost when the service is used from a different chat or account -
the service itself carries its own operating instructions, rather than
relying on them being re-explained every time.

### Key design choices

- **No geocoding for MCP rectification tools.** You always pass explicit
  `lat`/`lng` as decimal degrees. This avoids the "small village not in
  the database" problem entirely; get coordinates from Wikipedia/Wikidata
  (property P625) or any gazetteer, and pass them directly. (The `/astro`
  REST endpoint separately offers optional offline `&city=` lookup - see
  above - for callers like MediaWiki that need it; the MCP rectification
  tools themselves don't use it.)
- **Timezones: `tz_str` (IANA name) or explicit `tz_offset_minutes`.**
  IANA names correctly auto-resolve DST for modern dates. For historical
  dates where the modern IANA zone boundary/rule doesn't apply, pass
  `tz_offset_minutes` explicitly to override.
- **For ambiguous/nonexistent local times** (the hour that's skipped in a
  spring-forward, or repeated in a fall-back), kerykeion raises an error
  rather than silently guessing. The reliable workaround is to compute the
  UTC time yourself and pass it with `tz_offset_minutes=0`.
- **Orbs are technique-aware.** Transits default to wide classical orbs;
  progressions/directions default to tight ~1° orbs, since for directions
  1° of arc ≈ 1 year of life. All defaults are tunable via `.env`.
- **`rectif_scan` builds the natal chart once per candidate**, not once
  per event, so cost scales as `candidates × events`, not `candidates ×
  events × (natal + technique)`.

## Horary astrology: `horary_chart`

A horary chart answers one Yes/No question, judged from the chart cast
for the moment/place the question was asked (or received - see
`help("horary")` for phone/online/written-question conventions) - a
different discipline from natal work, with its own significator/
dignity/aspect rules. See `help_texts/horary.md` for the full
methodology (adapted from a synthesis of Masenkov's textbook, Frawley's
precise prohibition/frustration/refranation definitions, and Lavoie's
position on judging non-radical charts - see `BIBLIOGRAPHY.md`) and
`TECHNIQUE_STATUS.md` for exactly what's implemented.

The tool computes everything deterministically - radicality, both
significators (with essential + accidental dignity broken into
individually-listed factors, not just a strong/weak label), mutual
reception, void-of-course Moon, translation/collection of light,
perfection-interruption, and a final Yes/No - the same "explain the
already-computed verdict, don't re-derive it" contract `rectif_*`
already uses for rectification. Call `help("horary")` before using this
tool's output.

Two ways to specify what the question is about:

    # direct: the question is about the querent (or has an obvious house)
    horary_chart(..., quesited_house=7)  # "will I get married?"

    # derived: the question is about a THIRD PARTY
    horary_chart(..., derived_house_chain=[6, 3],
                 derived_house_labels=["brother", "dog"])
    # "will my brother's dog be found?" - 6th (a pet) from the 3rd
    # (a sibling) = house VIII; the tool resolves and returns this
    # itself, per the methodology's own requirement not to hand-derive it

House system defaults to Placidus (`"P"`) here specifically -
independent of `ASTROMCP_HOUSE_SYSTEM`, which is tuned for
rectification - since Placidus (not Koch) is horary's own conventional
default; Regiomontanus (`"R"`) is the classical Lilly-era alternative.

Part of Fortune and the Cross of Fate (`Asc + Mars - Saturn`, a second
horary-specific point) are computed via the existing Lots framework
(`engine/lots.py`) rather than new machinery.

## Requirements

- A Fedora-based Linux server (or any modern systemd Linux distribution -
  nothing here is Fedora-specific beyond how the examples are phrased)
- Python 3.12+
- nginx + a valid TLS certificate (Let's Encrypt via certbot) - Claude's
  web client connects from Anthropic's infrastructure and will not accept
  a self-signed certificate
- `mcp[cli]>=1.10.1,<2.0.0` - **pin below 2.0.0**. The v2 SDK
  (released 2026-07-28) renamed `FastMCP` to `MCPServer` and switched to a
  stateless protocol; this codebase targets the 1.x API and stateful
  transport.

## Installation

    mkdir -p /opt/astromcp
    cd /opt/astromcp
    python3 -m venv .venv
    source .venv/bin/activate
    pip install --upgrade pip
    pip install -r install/requirements.txt

Place `app.py` and the `engine/` directory under `/opt/astromcp/`.

Optionally copy `install/.env.example` to `.env` **in the project root**
(`/opt/astromcp/.env` - not `install/.env`) and adjust any settings you
want to override (house system, orb tables, scan defaults, console
output, etc.):

    cp install/.env.example .env

Every value has a working built-in default, so this step can be skipped
entirely for a first run. `.env` must live in the root because that's
where `load_dotenv()` looks by default, and where the systemd unit's
`EnvironmentFile` points.

### Run manually (for testing)

    source .venv/bin/activate
    python app.py

Default MCP endpoint: `http://0.0.0.0:8765/mcp`

### Run as a systemd service (production)

    cp install/astromcp.service /etc/systemd/system/astromcp.service
    systemctl daemon-reload
    systemctl enable astromcp
    systemctl start astromcp
    systemctl status astromcp

## Hosting / reverse proxy setup

1. Point a subdomain (e.g. `astromcp.example.com`) at your server's public IP.
2. Get a certificate:

       certbot --nginx -d astromcp.example.com

3. nginx reverse proxy (`/etc/nginx/conf.d/astromcp.conf` or similar):

       server {
           listen 443 ssl;
           server_name astromcp.example.com;

           ssl_certificate     /etc/letsencrypt/live/astromcp.example.com/fullchain.pem;
           ssl_certificate_key /etc/letsencrypt/live/astromcp.example.com/privkey.pem;

           location / {
               proxy_pass http://127.0.0.1:8765;
               proxy_http_version 1.1;
               proxy_set_header Host $host;
               proxy_set_header X-Real-IP $remote_addr;
               proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
               proxy_set_header X-Forwarded-Proto $scheme;
               # streamable-http keeps a connection open per session, and
               # rectif_scan requests can legitimately take tens of seconds
               proxy_read_timeout 300s;
           }
       }

4. Reload nginx: `nginx -t && systemctl reload nginx`

No authentication is configured by default (no OAuth). Consider adding
`fail2ban` on nginx and/or an IP allowlist if the endpoint is publicly
reachable, since it will otherwise be found by scanners.

## Connecting to Claude

In claude.ai: **Settings → Connectors → Add custom connector**
- URL: `https://astromcp.example.com/mcp`
- No OAuth

After adding, the tools become available in any conversation with the
connector enabled. If you add new tools to `app.py` and restart the
service, you generally need to reconnect the connector in Settings for
Claude to see the updated tool list.

## Console output

With `ASTROMCP_CONSOLE_RESULT_PREVIEW=true` (the default), every tool call
also prints a compact, human-readable summary of its result to the server
console/journal - so `journalctl -u astromcp -f` shows actual chart
positions, aspects, and scan rankings, not just "request received /
response sent". This is purely a logging convenience; the MCP response
itself is unaffected. See `engine/display.py` to customize the format, or
set the variable to `false` to disable it.

## Pipeline jobs — running and retrieving rectification results

The rectification pipeline (`rectif_pipeline_start`) processes dozens of
life events against dozens of candidate birth times. A full run (e.g. 71
events × 91 candidates) takes **~30 minutes** and produces a result that
can be **tens of megabytes** — too large for MCP's 1 MB tool-result limit
to return in one piece, and too expensive to repeat if the service
restarts.

### Job storage (Redis recommended)

Set `ASTROMCP_REDIS_URL=redis://localhost:6379/0` in `.env` to store jobs
in Redis. Results survive service restarts and are kept for 3 days.
Without Redis, jobs live in memory only — a restart loses everything.

    # Install Redis if needed
    dnf install redis        # Fedora
    systemctl enable --now redis

    # Add to .env
    echo 'ASTROMCP_REDIS_URL=redis://localhost:6379/0' >> .env

### REST endpoints for manual job access

Jobs are accessible via plain HTTP, independently of MCP. All examples
assume the service runs on `localhost:8765` (the default port).

**List all jobs:**

    curl http://localhost:8765/astro/jobs

**Check job status** (lightweight, no result payload):

    curl http://localhost:8765/astro/jobs/<job_id>/status

Example response:

    {
      "status": "done",
      "elapsed_seconds": 1842.3,
      "available_sections": ["trutina", "movements_scan", "movements_intersection",
                             "auxiliary", "candidate_verification", "summary", ...],
      "events_count": 71,
      "summary": {"events_processed": 71, "candidates_verified": 8, ...}
    }

**Fetch one section** (each fits comfortably in memory and in MCP):

    curl http://localhost:8765/astro/jobs/<job_id>/trutina
    curl http://localhost:8765/astro/jobs/<job_id>/movements_scan
    curl http://localhost:8765/astro/jobs/<job_id>/candidate_verification
    curl http://localhost:8765/astro/jobs/<job_id>/auxiliary
    curl http://localhost:8765/astro/jobs/<job_id>/movements_intersection
    curl http://localhost:8765/astro/jobs/<job_id>/summary

**Pretty-print with jq:**

    curl -s http://localhost:8765/astro/jobs/<job_id>/summary | jq .

**Save full result to file** (WARNING: can be 10-50 MB):

    curl http://localhost:8765/astro/jobs/<job_id> > result.json

**Pipe a section into a file for offline analysis:**

    curl -s http://localhost:8765/astro/jobs/<job_id>/candidate_verification > candidates.json
    cat candidates.json | python3 -m json.tool | less

### How the LLM retrieves results

The MCP tool `rectif_pipeline_result(job_id, section=...)` uses the same
sectioned retrieval:

    rectif_pipeline_result(job_id)                              → status + available_sections
    rectif_pipeline_result(job_id, section="trutina")           → Trutina data
    rectif_pipeline_result(job_id, section="movements_scan")    → per-event windows
    rectif_pipeline_result(job_id, section="candidate_verification") → technique matrix

## Testing

Quick sanity check with the official MCP Python client (more reliable
than hand-rolled `curl`, which is finicky against the streamable-http
protocol's session/SSE handshake):

    import asyncio
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    async def main():
        async with streamablehttp_client("https://astromcp.example.com/mcp") as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                print([t.name for t in tools.tools])
                result = await session.call_tool("ping", {"message": "hello"})
                print(result)

    asyncio.run(main())

## Known limitations / open items

- Progressed/directed angle method (`direct_progressed_angles`) matches
  the correct sign but has a residual ~10-23' offset against reference
  software that grows with elapsed time - likely a slightly different
  year-length constant or time-of-day handling. Not yet root-caused.
- Intermediate progressed/directed house cusps (2,3,5,6,8,9,11,12) are
  not currently computed - only the four angles (ASC/MC/DSC/IC).
- Historical timezone data relies on IANA tzdata via Python's `zoneinfo`,
  which is well-maintained but may not capture every obscure historical
  administrative change. Use `tz_offset_minutes` to override when you've
  verified the correct historical offset independently.
- `rectif_scan` cost scales linearly with `candidates × events`; very
  wide ranges at fine step sizes with many events can take minutes -
  tune `proxy_read_timeout` accordingly, or narrow the range first with
  a coarse pass.
- Runs as `root` in the current systemd unit; consider a dedicated
  unprivileged user for production hardening.
- No authentication on the MCP endpoint. Fine for a single-user personal
  tool behind a non-guessable subdomain; add an allowlist/secret header
  if this becomes a concern.
