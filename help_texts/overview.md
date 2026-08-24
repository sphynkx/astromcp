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
  (transit, secondary_progression, solar_arc, solar_return, profection) for
  a natal chart against one target date, with aspects to the natal chart.
- `rectif_scan` - sweeps many candidate birth times against a list of life
  events, scores aspect hits per candidate, returns ranked results. This is
  the core rectification search tool. Blocking/synchronous - fine for small
  scans.
- `rectif_scan_start` / `rectif_scan_result` - same as rectif_scan, but
  asynchronous (submit + poll). Use for anything large: wide time ranges,
  many events, or technique="solar_return" (several times more expensive
  per event than the others).
- `rectif_trutina` - Trutine of Hermes: a fast, direct (non-brute-force)
  classical rectification method that needs no life events at all. Good
  first move even with zero information about birth time.
- `ping` - connectivity check.

## Before doing rectification work

Call `help("rectification")` for the accumulated methodology - technique
priority order, an explicit rule about NOT assigning subjective
"significance" weights to events, how to interpret Trutina's dual branches
and possible cycle_detected output, timezone/coordinate handling advice,
and realistic expectations about what rectification can and can't resolve
without at least a rough starting time window. This reflects hard-won
lessons from real rectification sessions (documented mismatches between
technique families, a fixed timezone bug, etc.) - reading it first will
save you from re-deriving the same conclusions or repeating past mistakes.

## Other topics

Only rectification is covered in depth right now. If you're doing
something else with this service (synastry, horary, a plain natal reading,
transit forecasting) and a dedicated help topic doesn't exist yet, use
`rectif_chart` / `rectif_technique` directly - they're general-purpose -
and treat the rectification methodology notes as background context where
relevant (e.g. the timezone/coordinate advice applies universally).

Call `help()` with no arguments (or an unrecognized topic) to get this
overview again, including a live-updated list of whatever topics exist at
that moment.
