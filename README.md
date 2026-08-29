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

Separately, `/astro` and `/astro/chart.svg` (the same `app.py`, same
port) are also reachable as a plain REST endpoint for the MediaWiki
integration (see below) - via a **second, independent** nginx proxy
block, this one on the wiki's own server, forwarding `/astro` on the
wiki's own domain straight to this backend. Two different reverse
proxies, two different domains, same backend port - don't confuse the
nginx config for astromcp's own public MCP domain (above) with the
wiki-side proxy block documented in the MediaWiki section below.

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
    │   ├── .env.example        # documents all tunable settings
    │   └── Module_Astrodata.lua  # MediaWiki Lua module - see "Integration
    │                              # with MediaWiki" below. Kept in Russian
    │                              # (the one exception to this project's
    │                              # English-comments convention)
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
        ├── jobs.py             # in-memory async job registry for long scans
        ├── help.py             # reads help_texts/*.md on demand
        ├── tools.py            # MCP tool implementations (no MCP dependency itself)
        ├── display.py          # human-readable console summaries
        ├── geocode.py          # offline city->coords (geonamescache) and coords->tz
        │                       # (timezonefinder) lookups - used only by public_api.py
        ├── fixed_stars.py      # fixed-star positions via pyswisseph, used only by
        │                       # public_api.py - not used by any rectification tool
        ├── public_api.py       # builds the flat JSON for the /astro REST endpoint
        ├── svg_chart.py        # builds the SVG for /astro/chart.svg - see that
        │                        # endpoint's README section for design notes
        └── photo_fetch.py      # fetches+inlines the optional chart-header photo as
                                 # a data: URI - see the README's "Photo embedding" note

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
separating for it same as any planet. That numeric-rather-than-analytic
speed is deliberate: it works identically for any formula added to the
registry later, with no per-formula derivative to hand-derive.

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
instead of an error - useful for a quick `curl` sanity check. Any request
that has params but is invalid or incomplete (missing `date`, unparsable
`time`, unknown city, ...) returns `{"error": ..., "help": {...}}` with
that same reference attached, so the parameter list is always one field
away rather than only living in this README - readable directly in a
terminal (`curl ... | jq`) and just as easy for a MediaWiki-side script to
parse and surface to an editor who fat-fingered a query.

City-name lookup (`&city=...`) and timezone auto-resolution (when neither
`&tz=` nor `&tz_offset=` is given) are both **offline** - `geonamescache`
for the former, `timezonefinder` for the latter - no live external
geocoding call happens. `&city=` accepts English or Russian input: a
curated exonym table (`RU_CITY_EXONYMS` in `engine/geocode.py`) covers
cases like Москва/Moscow where the Russian name is a genuinely different
word, geonamescache's own bundled alternate-name data covers a fair
number of Cyrillic spellings for free, and a transliteration fallback
catches the rest where transliterating happens to land close to a known
spelling. `&country_code=` (used to disambiguate a common city name)
likewise accepts ISO2, or a country name in English or Russian, resolved
via Babel's CLDR data - no hand-maintained table needed for countries,
unlike cities. Both come with real caveats spelled out in
`engine/geocode.py`'s docstring: city-name matching is a population-based
heuristic that can pick the wrong same-named town, the Russian-language
support hasn't been independently verified against the live dataset (test
it against your running server and grow `RU_CITY_EXONYMS` from what
actually fails), and the auto-resolved timezone is the *modern* zone
boundary only - **not safe for historical dates** without independently
verifying the actual historical offset (see the Soviet decree-time
example already documented in `help_texts/rectification.md`). For
anything precise, pass `lat`/`lon` and `tz`/`tz_offset` explicitly.

Fixed-star positions (`engine/fixed_stars.py`) are a new capability added
for this endpoint - no rectification tool in this project used them
before. First-pass implementation, not independently verified against a
running install in the session that wrote it; sanity-check a few star
positions against a known reference (e.g. Astrodienst) after deploying.

### SVG chart wheel: `GET /astro/chart.svg`

Same date/time/location/timezone/house_system parameters as `/astro`
above, rendered as a standalone SVG natal chart wheel instead of JSON -
see `engine/svg_chart.py` for the drawing code and the design notes in
its module docstring (rotation convention, why the sign-wedge colors are
a computed hue-stepped palette rather than hand-picked hex values, aspect
line color/style rules, what "exact" means for the bold highlighting).

    GET /astro/chart.svg?date=23.11.1993&time=14:30&city=Kyiv
      &name=Displayed+person+name
      &place=Displayed+place+name
      &filename=Some_name.svg

`name`/`place` are free-text header labels (the JSON report's `meta` has
no "person's name" field, since a date/time/place alone doesn't carry
one). `filename` only sets the `Content-Disposition` header so a
browser's "save as" proposes that name - it does not change the response
body, and nothing is written to disk on the server.

Colors and layout were built from a ZET9 screenshot the project owner
supplied as a loose visual reference, **not** a pixel-exact
reproduction (their own framing of the brief) - sign-wedge hues (an
exact hand-picked hex table, `SIGN_COLORS` in `engine/svg_chart.py`, kept
separate from the drawing code specifically so it's easy to retune), a
thin house ring (matching the sign ring's own width, rather than
reaching toward center - planets sit right at its inner edge) with
planets placed inside it, Ascendant/MC markers, the hard/soft aspect
color split on the wheel's own aspect chords, essential-dignity letters
next to each planet in the side list (`PLANET_DIGNITY` - a popular modern
convention that also assigns dignities to Uranus/Neptune/Pluto, not the
strict 7-planet classical system, exactly as specified), and the general
header/wheel/list/table layout follow that reference; exact ZET9 pixel
colors (beyond the explicitly-specified sign hexes), per-planet
aspect-count balance bars, and ZET9's own (much larger) fixed-star
catalog were deliberately not chased.

Every planet, house cusp/angle, and aspect chord carries a native SVG
`<title>` element (position/house, and any aspects to that point,
including the applying/separating mark), so hovering it in a browser
shows a tooltip - modeled on a ZET9 screenshot of exactly this hover
behavior. The aspect TABLE (as opposed to the wheel's own chords) colors
each aspect by applying vs. separating ("сходящиеся"/"расходящиеся" -
pink vs. light blue) rather than hard/soft, since the harmonious/tense
split is already visible in the glyph itself; it's laid out as a
shrinking staircase (row *i* has *i* cells, column headers along the
bottom) rather than a half-empty square, which needs one fewer row/
column of header space. Chords are drawn for planet-planet aspects and
for planet-to-**angle** aspects (Asc/MC/Dsc/IC); aspects to the other 8
house cusps aren't drawn as chords (that would clutter the wheel fast)
but do show up in that cusp's own tooltip. House sectors are colored
per `HOUSE_COLORS` in `engine/svg_chart.py` - a table like `SIGN_COLORS`,
currently all 12 entries the same flat hex, kept separate from the
drawing code specifically so a future cardinal/succedent/cadent scheme
is a table edit, not a code change.

**Photo embedding is more involved than it looks**, because of a real
browser restriction worth understanding before debugging it further: an
SVG loaded as the source of an HTML `<img>` (exactly how the Lua module
embeds this chart) runs in a restricted context that is **not allowed to
load its own external resources** - so a plain `<image href="https://
external-host/photo.jpg">` inside the SVG silently never loads, even
though navigating to the same SVG URL directly in a browser tab loads it
fine (this is exactly the "opens in a new tab but not from inside the
picture" symptom). There's no fix on the SVG-authoring side for this -
it's deliberate. The fix is `engine/photo_fetch.py`: the server fetches
the photo itself and inlines it as a `data:` URI (not an external
resource, so the restriction doesn't apply) before the SVG is ever sent
to the browser. This is why `/astro/chart.svg`'s `photo_url` param now
only accepts URLs matching `ASTROMCP_PHOTO_ALLOWED_PREFIXES` (empty by
default - fails closed) - a publicly reachable endpoint that fetches any
URL a caller hands it is a textbook SSRF surface, so set this to your own
wiki's file-serving host before photos will render (see `.env.example`).

On the MediaWiki side, `resolveFileUrl` (in the Lua module) tries three
things in order: (1) `computeHashedFileUrl` - computes the direct file
path from MediaWiki's own default hashed-upload-directory scheme
(`mw.hash.hashValue('md5', filename)`, first/first-two hex chars as the
subdirectory) - deterministic, no live-wiki dependency, and confirmed
against a real working URL by the project owner (`md5sum` in a shell
matched the actual path); (2) the Scribunto File object's direct URL
(`title.file:getUrl()`/`canonicalUrl`, wrapped in `pcall` since the exact
method available varies by Scribunto version); (3) the `Special:FilePath`
redirect. `WIKI_UPLOAD_PATH` (top of the module) holds the upload
directory name - `/images_sociowiki` for sociowiki.sphynkx.org.ua,
adjust if you copy this module to a wiki with a different
`$wgUploadPath`. Whichever of the three resolves is still only the
*source* URL handed to `photo_url` - it still goes through the
server-side fetch-and-inline step above, computing the "real" direct path
doesn't bypass that requirement (see the note above on why).

Untested against a real browser/MediaWiki render in the session that
wrote it (no network access to rasterize locally, and no live wiki to
confirm the exact Scribunto File-object method names or the photo fetch
against) - the SVG was checked for structural validity (finite
coordinates within the canvas, correct arc sweep directions including
the now-variable-width house sectors, compiles/runs without exceptions
against synthetic data shaped like a real `/astro` response) but not
eyeballed rendered - render one real chart after deploying and compare
against expectations before relying on it.
expectations before relying on it.

Errors return a small SVG containing the error text (with the correct
HTTP status code) rather than JSON - an `<img>`/external-image consumer
like MediaWiki has nowhere to display JSON error text, so a visibly
broken image with a readable message beats a broken image with none.

## Integration with MediaWiki

A ready-to-use Lua module lives at `install/Module_Astrodata.lua` -
consumes `/astro` via the
[External Data](https://www.mediawiki.org/wiki/Extension:External_Data)
extension's `mw.ext.externalData.getExternalData` and `/astro/chart.svg`
as an external-image link, and generates the Russian-language category
tags described below. **This is the one file in the project kept in
Russian rather than English** - it's Lua for a Russian-language wiki's
editors to read and maintain directly, not Python for this project's own
contributors, so the usual English-comments convention doesn't apply to
it.

### LocalSettings.php requirements

External Data has no "named data source" indirection for Lua calls - the
URL is always given directly in code, so the only real configuration
needed is to allow-list wherever `BASE_URL` in the module actually
resolves to.

**As of this round, `BASE_URL` is `mw.site.server .. "/astro"` - the
wiki's own domain, not the astromcp backend's address directly.** This
depends on the wiki's own nginx reverse-proxying `/astro` straight
through to the astromcp backend, e.g.:

    location /astro {
        proxy_pass http://192.168.7.3:8765;
    }

(this block goes in the **wiki's** nginx config, not astromcp's own -
see the "Deployment" section below for astromcp's own nginx config,
which is a separate, unrelated reverse proxy for astromcp's public
domain). With this in place, `getExternalData` calls made by the wiki's
own PHP (External Data fetches happen server-side, not in the visitor's
browser) go out to the wiki's public domain and come back in via this
proxy block - so the allow-list entry needs to match that domain, not
the backend's internal address:

    $edgAllowExternalDataFrom = array( 'https://sociowiki.sphynkx.org.ua/' );

The previous round hardcoded the backend's internal IP directly
(`192.168.7.3:8765`), bypassing the wiki's own nginx entirely - this
was slightly more direct (one less proxy hop) but meant `BASE_URL`
had to be edited by hand for every wiki/environment this module gets
copied to, and the allow-list above had to reference the internal
address specifically, which reads confusingly next to a
publicly-facing wiki config. Deriving it from `mw.site.server` instead
removes that hardcoding - the module now works unmodified on a
staging copy of the wiki, a domain rename, etc. If the wiki server
can't resolve its own public domain back to something local (so this
round-trips out to the internet and back rather than staying
internal), reverting `BASE_URL` to a literal internal IP is a one-line
change back - see the comment directly above `BASE_URL` in the module.

For `p.wheel()` (the SVG chart), MediaWiki also needs permission to render
an `<img>` tag - its Sanitizer strips raw `<img>` from wikitext/module
output by default:

    $wgAllowImageTag = true;

This is a narrow, purpose-built flag (unlike `$wgRawHtml`, it permits only
the `<img>` tag, nothing else) and - importantly - side-steps a real
MediaWiki core limitation: the alternative approach (a bare, unbracketed
external-image URL, auto-embedded via `$wgAllowExternalImages`/
`$wgAllowExternalImagesFrom`) depends on MediaWiki's own
`EXT_IMAGE_REGEX` recognizing `.svg` as an image extension, which
historically it did **not** by default (only `gif|png|jpg|jpeg` - see
[phabricator T65806](https://phabricator.wikimedia.org/T65806); some
installs needed a core patch to add `svg`). Whether your specific version
has that fixed is not something to gamble on, so `p.wheel()` returns a
literal `<img src="...">` tag and relies on `$wgAllowImageTag` instead,
which has no such extension dependency.

(If `$wgAllowImageTag` isn't an option on your install for some reason,
the bare-URL external-image path is still worth trying as a fallback -
`$wgAllowExternalImages = false; $wgAllowExternalImagesFrom = array('https://sociowiki.sphynkx.org.ua/');`
plus a template call with **no** manual `[...]` brackets around the
`{{#invoke:...}}` - but test it, since the `.svg`-recognition caveat
above applies.)

### Installing the module

Create the wiki page `Module:Astrodata` and paste in the contents of
`install/Module_Astrodata.lua`.

### Calling it from a template

The module reads `date`/`time`/`lat`/`lon`/`city`/`country`/`houses`/
`name`/`place`/`photo`/`lots` from its own direct args and/or its parent
frame's args (so both `{{#invoke:Astrodata|planetslist|date=...}}` and a
template calling `{{#invoke:...}}` with already-named parameters work).
Missing `date`, or missing both coordinates and a city, makes every
function silently return `""` - no error text on the page, per the
original design brief - so a template can call all five functions
unconditionally without an `{{#if:}}` guard.

    {{#invoke:Astrodata|planetslist
      |date={{{Дата рождения}}} |time={{{Время рождения}}}
      |lat={{{Широта рождения}}} |lon={{{Долгота рождения}}}
      |city={{{Город рождения}}} |country={{{Страна рождения}}}
    }}

    {{#invoke:Astrodata|aspectslist | ... same params ... }}

    {{#invoke:Astrodata|categories | ... same params ... }}

    {{#invoke:Astrodata|wheel | ... same params ...,
      optionally |name=... |place=... |photo={{{Изображение}}} }}

    {{#invoke:Astrodata|deathCategories|date={{{Дата смерти}}}}}

`city`/`country` are cleaned of `[[wikilink]]` markup internally, so
passing them straight from wikitext fields is fine. `lat`/`lon` must be
**decimal degrees with lat first, lon second** - a template that swaps
them (this has happened once already) will silently geocode the wrong
point whenever a page has explicit coordinates and no `city` fallback.

`planetslist`/`aspectslist` render each point/aspect with its Unicode
glyph rather than a spelled-out name - `planetslist` also shows an
essential-dignity letter (domicile/exaltation/detriment/fall - see
`PLANET_DIGNITY` in the module) between the glyph and the position, and
`aspectslist` bolds aspects tighter than 1 degree.

**Lots/Arabic Parts** (see the `/astro` README section above for the
server-side framework) show up in `planetslist`, `aspectslist`, and
`categories` automatically once the server returns a `json.lots` section
- the module's `LOT` table (parallel to `PLANET`) maps a registered
Lot's name to its display glyph/nominative/genitive, and `pointInfo()`
looks up either table so aspect rendering doesn't care whether a point
is a planet or a Lot. Only `part_of_fortune` is registered on the server
by default; pass `|lots=part_of_fortune,other_name` to request others
once they exist (see `engine/lots.py`). Adding a NEWLY-registered
server-side Lot to the module's own display (glyph, name) is a one-line
addition to the `LOT` table - the rest (table rows, aspect rows,
categories) picks it up automatically since it all iterates `LOT_IDS`/
`json.lots` generically rather than hardcoding `part_of_fortune`.

`p.wheel()` names the downloadable file from the current page title
(`Натал_<Заголовок,_с_подчёркиваниями>.svg`) - MediaWiki's standard
"Фамилия, Имя Отчество" biography title convention maps onto this
directly, no extra template parameter needed. `photo` should be a
filename already uploaded to the wiki, without the leading `Файл:`/`File:`
(exactly what a `{{{Изображение}}}` template parameter typically holds) -
resolved via `Special:FilePath`, with `Unknown-person.png` as a fallback
if that specific file doesn't exist and isn't itself missing. It returns
a clickable image (wrapped in a link to the same SVG, so a reader can
open it full-size out of a cramped infobox) - call it bare, with **no**
manual `[...]` or `[[...]]` wrapping around the `{{#invoke:...}}`
(wrapping it produces broken nested-bracket wikitext, since the module's
own output already has its own bracket structure).

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
