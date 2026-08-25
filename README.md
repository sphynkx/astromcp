# astromcp

MCP (Model Context Protocol) server exposing precise astrological chart
calculations (natal charts, transits, secondary progressions, solar arc
directions, and full birth-time rectification scans) for use as tools by an
LLM assistant. Built on kerykeion (https://github.com/g-battaglia/kerykeion),
which wraps the Swiss Ephemeris for astronomical accuracy.

Originally built to support natal chart rectification work (determining an
unknown/uncertain birth time by matching astrological techniques against a
list of known life events), but the tools are general-purpose and usable
for any natal/transit/progression/direction calculation.

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

The service exposes tools, not a REST API - it must be added to Claude as
an MCP connector (streamable-http transport), not fetched as a plain URL.

## Project structure

    astromcp/
    ├── app.py                  # MCP entry point: tool registration only
    ├── README.md
    ├── help_texts/             # LLM-facing methodology guides, read via the help() tool
    │   ├── overview.md
    │   └── rectification.md
    ├── install/
    │   ├── requirements.txt
    │   ├── astromcp.service    # systemd unit
    │   └── .env.example        # documents all tunable settings
    └── engine/
        ├── __init__.py
        ├── config.py           # .env-driven settings, with built-in defaults
        ├── constants.py        # structural constants + traditional sign rulerships
        ├── chart.py            # subject construction, serialization, tz helpers
        ├── aspects.py          # aspect geometry, applying/separating/exact
        ├── techniques.py       # transit / progression / solar arc / solar return / profection
        ├── trutina.py          # Trutine of Hermes (classical rectification, no events needed)
        ├── scan.py             # rectif_scan: sweeps candidate birth times
        ├── criteria.py         # Grishchenyuk / Timoshenko / Bonatti / Herich criterion tests
        ├── clustering.py       # Israitel/Brady degree-clustering rectification
        ├── arabic_parts.py     # Part of Fortune + Kutalev's general Lot formula
        ├── relations.py        # "elements of house" - see houses.py
        ├── houses.py           # house ruler/co-ruler/occupant lookups
        ├── jobs.py             # in-memory async job registry for long scans
        ├── help.py             # reads help_texts/*.md on demand
        ├── tools.py            # MCP tool implementations (no MCP dependency itself)
        ├── display.py          # human-readable console summaries
        ├── geocode.py          # offline city->coords (geonamescache) and coords->tz
        │                       # (timezonefinder) lookups - used only by public_api.py
        ├── fixed_stars.py      # fixed-star positions via pyswisseph, used only by
        │                       # public_api.py - not used by any rectification tool
        └── public_api.py       # builds the flat JSON for the /astro REST endpoint

`app.py` deliberately contains no astrological logic - it only registers
MCP tools and delegates to `engine/tools.py`. This keeps the transport layer
(MCP/FastMCP specifics) separate from the domain logic, which can be read,
modified, or reused independently.

## Tools exposed

| Tool | Purpose |
|---|---|
| `rectif_chart` | Full chart (planets, houses, angles) for one date/time/place |
| `rectif_chart_batch` | Batch version of the above |
| `rectif_technique` | One technique - transit / secondary progression / solar arc direction / solar return / profection - with aspects to the natal chart |
| `rectif_technique_batch` | Batch version of the above |
| `rectif_scan` | EXPLORATORY ONLY (see help_texts/rectification.md "No invented scoring") - sums an arbitrary hit-count into a ranking not documented by any surveyed source; useful for a rough sense of where to look, not for conclusions |
| `rectif_scan_start` / `rectif_scan_result` | Async version of rectif_scan (submit + poll) - use for large scans or `technique="solar_return"`, which can otherwise exceed MCP/proxy timeouts |
| `rectif_trutina` | Trutine of Hermes: fast, direct classical rectification via the conception (epoch) chart - needs no life events at all |
| `rectif_movements_scan` | Grishchenyuk's literal "3 movements" criterion (>=2 of 3 concordant) - returns qualifying times, not scores |
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
      "arabic_parts": {"part_of_fortune": ..., "is_day_birth": ...},
      "fixed_stars": {"Regulus": {...}, ...},
      "fixed_star_conjunctions": [{"star": "...", "point": "...", "orb": ...}],
      "meta": {"schema_version": 1, ...}
    }

Only ONE house system is computed per call (default from
`ASTROMCP_HOUSE_SYSTEM`, override with `&house_system=K` etc.) - mixing
several systems' cusps into one flat response would make it ambiguous
which system a given cusp or aspect belongs to. Call the endpoint twice
with different `house_system` values if a page genuinely needs both.

City-name lookup (`&city=...`) and timezone auto-resolution (when neither
`&tz=` nor `&tz_offset=` is given) are both **offline** - `geonamescache`
for the former, `timezonefinder` for the latter - no live external
geocoding call happens. Both come with real caveats spelled out in
`engine/geocode.py`'s docstring: city-name matching is a population-based
heuristic that can pick the wrong same-named town, and the auto-resolved
timezone is the *modern* zone boundary only - **not safe for historical
dates** without independently verifying the actual historical offset (see
the Soviet decree-time example already documented in
`help_texts/rectification.md`). For anything precise, pass `lat`/`lon` and
`tz`/`tz_offset` explicitly.

Fixed-star positions (`engine/fixed_stars.py`) are a new capability added
for this endpoint - no rectification tool in this project used them
before. First-pass implementation, not independently verified against a
running install in the session that wrote it; sanity-check a few star
positions against a known reference (e.g. Astrodienst) after deploying.

### How the LLM client learns the methodology

Two mechanisms work together:

1. **`instructions`** on the `FastMCP(...)` constructor in `app.py` - sent
   automatically to the client during the MCP `initialize` handshake,
   before any tool is called. It's kept short: essentially "call `help()`
   before doing rectification work."
2. **`help_texts/*.md`**, read on demand via the `help` tool. This is
   where the actual accumulated methodology lives - technique priority
   order, the rule against inventing subjective event-significance
   weights, timezone/coordinate handling advice, and so on. Add a new
   topic by adding a new `help_texts/<topic>.md` file; `help()` with no
   arguments (or an unrecognized topic) lists whatever topics currently
   exist, so nothing needs to be hardcoded elsewhere when a topic is
   added.

This exists so that methodology learned the hard way in one chat session
isn't lost when the service is used from a different chat or account -
the service itself carries its own operating instructions, rather than
relying on them being re-explained every time.

### Key design choices

- **No geocoding.** The service never looks up place names - you always
  pass explicit `lat`/`lng` as decimal degrees. This avoids the "small
  village not in the database" problem entirely; get coordinates from
  Wikipedia/Wikidata (property P625) or any gazetteer, and pass them
  directly.
- **Timezones: `tz_str` (IANA name) or explicit `tz_offset_minutes`.**
  IANA names correctly auto-resolve DST for modern dates. For historical
  dates where the modern IANA zone boundary/rule doesn't apply (e.g.
  Soviet-era administrative timezone changes), pass `tz_offset_minutes`
  explicitly to override.
- **For ambiguous/nonexistent local times** (the hour that's skipped in a
  spring-forward, or repeated in a fall-back), kerykeion raises an error
  rather than silently guessing. The reliable workaround is to compute the
  UTC time yourself and pass it with `tz_offset_minutes=0` - this
  sidesteps local-time DST resolution entirely.
- **Orbs are technique-aware.** Transits default to wide classical orbs;
  progressions/directions default to tight ~1° orbs, since for directions
  1° of arc ≈ 1 year of life, so a wide orb there directly becomes years
  of dating error. All defaults are tunable via `.env` - see
  `.env.example`.
- **`rectif_scan` builds the natal chart once per candidate**, not once
  per event, so cost scales as `candidates × events`, not `candidates ×
  events × (natal + technique)`. A 2-hour range at 1-minute resolution
  with 20 events is on the order of 2,400 chart builds - typically tens
  of seconds, well within the timeout configured in the reverse proxy.

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
  administrative change (e.g. small USSR settlements reassigned between
  time zones). Use `tz_offset_minutes` to override when you've verified
  the correct historical offset independently.
- `rectif_scan` cost scales linearly with `candidates × events`; very
  wide ranges at fine step sizes with many events can take minutes -
  tune `proxy_read_timeout` accordingly, or narrow the range first with
  a coarse pass.
- Runs as `root` in the current systemd unit; consider a dedicated
  unprivileged user for production hardening.
- No authentication on the MCP endpoint. Fine for a single-user personal
  tool behind a non-guessable subdomain; add an allowlist/secret header
  if this becomes a concern.

## License

Personal project. No license specified.
