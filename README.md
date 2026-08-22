# astromcp

MCP (Model Context Protocol) server exposing precise astrological chart
calculations (natal charts, transits, secondary progressions, solar arc
directions) for use as tools by an LLM assistant. Built on
kerykeion (https://github.com/g-battaglia/kerykeion), which wraps the
Swiss Ephemeris for astronomical accuracy.

Originally built to support natal chart rectification work (determining
an unknown/uncertain birth time by matching astrological techniques against
a list of known life events), but the tools are general-purpose and usable
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
                                              --> app.py (FastMCP + kerykeion)

The service exposes tools, not a REST API - it must be added to Claude as
an MCP connector (streamable-http transport), not fetched as a plain URL.

## Tools exposed

| Tool | Purpose |
|---|---|
| rectif_chart | Full chart (planets, houses, angles) for one date/time/place |
| rectif_chart_batch | Batch version of the above |
| rectif_technique | Transit / secondary progression / solar arc direction, with aspects |
| rectif_technique_batch | Batch version of the above |
| ping | Connectivity test |

Full parameter reference is in the docstrings in app.py (visible to the
MCP client, including the LLM, at call time).

### Key design choices

- No geocoding. The service never looks up place names - you always
  pass explicit lat/lng as decimal degrees. This avoids the "small
  village not in the database" problem entirely; get coordinates from
  Wikipedia/Wikidata (property P625) or any gazetteer, and pass them
  directly.
- Timezones: tz_str (IANA name) or explicit tz_offset_minutes.
  IANA names correctly auto-resolve DST for modern dates. For historical
  dates where the modern IANA zone boundary/rule doesn't apply (e.g.
  Soviet-era administrative timezone changes), pass tz_offset_minutes
  explicitly to override.
- For ambiguous/nonexistent local times (the hour that's skipped in a
  spring-forward, or repeated in a fall-back), kerykeion raises an error
  rather than silently guessing. The reliable workaround is to compute
  the UTC time yourself and pass it with tz_offset_minutes=0 - this
  sidesteps local-time DST resolution entirely.
- Orbs are technique-aware. Transits default to wide classical orbs;
  progressions/directions default to tight ~1 degree orbs, since for
  directions 1 degree of arc is roughly 1 year of life, so a wide orb
  there directly becomes years of dating error.

## Requirements

- Linux server (developed on Fedora 39) with a public HTTPS-capable domain
  (or, for local-only testing via Claude Desktop, just LAN access)
- Python 3.12+
- nginx + a valid TLS certificate (Let's Encrypt via certbot) - Claude's
  web client connects from Anthropic's infrastructure and will not accept
  a self-signed certificate
- mcp[cli]>=1.10.1,<2.0.0 - pin below 2.0.0. The v2 SDK (released
  2026-07-28) renamed FastMCP to MCPServer and switched to a stateless
  protocol; this codebase targets the 1.x API and stateful transport.

## Installation

    mkdir -p /opt/astromcp
    cd /opt/astromcp
    python3 -m venv .venv
    source .venv/bin/activate
    pip install --upgrade pip
    pip install -r install/requirements.txt

Place app.py in /opt/astromcp/app.py (see repo root).

Optional .env in /opt/astromcp/.env:

    ASTROMCP_HOST=0.0.0.0
    ASTROMCP_PORT=8765

### Run manually (for testing)

    source .venv/bin/activate
    python app.py

Default MCP endpoint: http://0.0.0.0:8765/mcp

### Run as a systemd service (production)

    cp install/astromcp.service /etc/systemd/system/astromcp.service
    systemctl daemon-reload
    systemctl enable astromcp
    systemctl start astromcp
    systemctl status astromcp

## Hosting / reverse proxy setup

1. Point a subdomain (e.g. astromcp.example.com) at your server's public IP.
2. Get a certificate:

       certbot --nginx -d astromcp.example.com

3. nginx reverse proxy (/etc/nginx/conf.d/astromcp.conf or similar):

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
               proxy_read_timeout 300s;
           }
       }

4. Reload nginx: nginx -t && systemctl reload nginx

No authentication is configured by default (no OAuth). Consider adding
fail2ban on nginx and/or an IP allowlist if the endpoint is publicly
reachable, since it will otherwise be found by scanners.

## Connecting to Claude

In claude.ai: Settings -> Connectors -> Add custom connector
- URL: https://astromcp.example.com/mcp
- No OAuth

After adding, the tools become available in any conversation with the
connector enabled. If you add new tools to app.py and restart the
service, you generally need to reconnect the connector in Settings for
Claude to see the updated tool list.

## Testing

Quick sanity check with the official MCP Python client (more reliable
than hand-rolled curl, which is finicky against the streamable-http
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

- Progressed/directed angle method (direct_progressed_angles) matches
  the correct sign but has a residual ~10-23 arcminute offset against
  Zet9 that grows with elapsed time - likely a slightly different
  year-length constant or time-of-day handling. Not yet root-caused.
- Intermediate progressed/directed house cusps (2,3,5,6,8,9,11,12) are
  not currently computed - only the four angles (ASC/MC/DSC/IC).
- Historical timezone data relies on IANA tzdata via Python's zoneinfo,
  which is well-maintained but may not capture every obscure historical
  administrative change (e.g. small USSR settlements reassigned between
  time zones). Use tz_offset_minutes to override when you've verified
  the correct historical offset independently.
- Runs as root in the current systemd unit; consider a dedicated
  unprivileged user for production hardening.
- No authentication on the MCP endpoint. Fine for a single-user personal
  tool behind a non-guessable subdomain; add an allowlist/secret header
  if this becomes a concern.

## License

Personal project. No license specified.