# astromcp - overview

MCP service for astrological chart calculations (Swiss Ephemeris via
kerykeion). Originally built for birth-time rectification; the primitives
are general enough for other astrological work too (synastry, horary,
transit forecasting, etc. - see "Other topics" below for what's covered so
far).

## Tool groups

- `rectif_chart` / `rectif_chart_batch` - a chart (planets, houses, angles)
  for an arbitrary date/time/place. The base primitive everything else is
  built on.
- `rectif_technique` / `rectif_technique_batch` - one predictive technique
  for a natal chart against one target date, with aspects to the natal
  chart. Valid `technique` values: `transit`, `secondary_progression`,
  `solar_arc`, `solar_return`, `lunar_return`, `profection`,
  `primary_direction_zodiacal`, `relocated_transit` - see
  `help("rectification")` for what each one actually computes and when to
  use it; don't guess from the name alone.
- `rectif_scan` - sweeps many candidate birth times against a list of life
  events. Blocking/synchronous - fine for small scans. **Its score fields
  are not a valid rectification result on their own - see
  `help("rectification")`'s "Absolute rule: never invent a scoring or
  weighting scheme" before using this tool's output for anything beyond a
  convenience sweep mechanism.**
- `rectif_scan_start` / `rectif_scan_result` - same as rectif_scan, but
  asynchronous (submit + poll). Use for anything large: wide time ranges,
  many events, or technique="solar_return" (several times more expensive
  per event than the others).
- `rectif_trutina` - Trutine of Hermes: a fast, direct (non-brute-force)
  classical rectification method that needs no life events at all. Good
  first move even with zero information about birth time.
- `rectif_movements_scan` - A. Grishchenyuk's three-movements rectification
  rule (progression + perfection + transit, >=2 of 3 concordant), reproduced
  literally - returns qualifying time windows, not a score.
- `rectif_timoshenko_scan` - I. Timoshenko's four-condition bidirectional
  aspect test for one house at one event date, reproduced literally.
- `rectif_bonatti_scan` / `rectif_herich_scan` - Guido Bonatti's and Paul
  von Gerich's classical auxiliary rectification rules, reproduced
  literally - both sources explicitly say to use these only combined with
  a stronger technique, never alone.
- `rectif_degree_clustering` - B. Israitel's condensation method / B.
  Brady's graphic rectification: tallies where transiting slow planets
  land across many event dates to suggest a candidate angular degree -
  the one rectification tool here that needs no birth-time scan at all,
  only event dates.
- **`rectif_pipeline`** / `rectif_pipeline_start` + `rectif_pipeline_result`
  - **the recommended entry point for rectification.** Runs the entire
  mandatory sequence (Trutina, movements_scan for every event, intersection,
  auxiliary checks, direct verification of candidates) server-side in one
  call. Accepts birth data + annotated event list, returns the full data
  matrix. See `help("rectification")` section "Pipeline tool". Also
  available as REST: `POST /astro/rectify`.
- `horary_chart` - builds and judges a horary chart (a question asked at
  a specific moment/place - "will I get this job?", "where is my lost
  cat?") per classical horary technique: radicality, significators with
  full essential/accidental dignity, mutual reception, void-of-course
  Moon, translation/collection of light, perfection-interruption
  (prohibition/frustration/refranation), and a Yes/No verdict. Call
  `help("horary")` before using this one too - same "explain the
  computed verdict, don't re-derive it" contract as rectification.
- `ping` - connectivity check.

This service is also reachable outside the MCP tool interface, via two
plain HTTP GET endpoints on the same server - `/astro` (JSON report) and
`/astro/chart.svg` (rendered SVG chart wheel, with optional `photo_url`/
`name`/`place` for a wiki-infobox-style rendering). These are meant for
non-MCP callers (a MediaWiki template, a browser) and are not tools this
Claude instance calls itself - see the main README.md's "REST endpoint
for non-MCP callers" section for the full parameter list if a request
needs one of these URLs constructed or explained.

## Before doing rectification work

**Call `help("rectification")` and read it in full before starting -
every session, not just the first time.** It is binding operating
procedure, not optional background: source-quality assessment, the
complete inventory of every implemented technique (several of which -
`rectif_movements_scan`, `rectif_timoshenko_scan`, `rectif_bonatti_scan`,
`rectif_herich_scan`, `rectif_degree_clustering`, `lunar_return` - have
gone unused in real past sessions simply because this document wasn't
re-read each time), the mandatory full sequence for applying them, an
absolute rule against inventing scores or significance weights, the
required final report format, timezone/coordinate handling, and
realistic expectations about what rectification can and can't resolve.
Treat each rectification as an independent task - do not rely on memory
of a different session's shortcuts or findings influencing how
thoroughly this one gets worked.

## Other topics

Rectification and horary are covered in depth - see `help("rectification")`
and `help("horary")`. If you're doing something else with this service
(synastry, a plain natal reading, transit forecasting) and a dedicated
help topic doesn't exist yet, use `rectif_chart` / `rectif_technique`
directly - they're general-purpose - and treat the rectification
methodology notes as background context where relevant (e.g. the
timezone/coordinate advice applies universally).

Call `help()` with no arguments (or an unrecognized topic) to get this
overview again, including a live-updated list of whatever topics exist at
that moment.
