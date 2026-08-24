# Rectification methodology

This is accumulated, hard-won practice from real rectification sessions
with this service, not astrological doctrine handed down from elsewhere.
Follow it unless the person you're working with directs otherwise.

## Technique priority order

1. **`rectif_trutina`** first, always - it's free (a handful of direct
   calculations, not a scan) and needs zero life events. Run it before
   anything else, even with completely unknown birth time. It returns two
   branches (Moon above/below horizon at birth); one or both branches may
   report `cycle_detected: true` with a `cycle_candidates` list instead of
   a single converged time - that is a genuine, documented property of the
   classical method on some charts (the whole-day gestation table can put
   the true fixed point on an integer-day boundary), not a bug. Treat the
   cycle_candidates spread as the plausible range for that branch, not
   noise to average away.

2. **Profections** (`technique="profection"`) second. Suspected (not yet
   proven across enough cases) to give the clearest signal of the
   event-based techniques, because they make a narrow, falsifiable claim
   (does the Lord of the Year/Month or profected Ascendant get activated
   by transit on the event date?) rather than a diffuse one. Traditional
   (Hellenistic) sign rulerships are used deliberately - Scorpio=Mars,
   Aquarius=Saturn, Pisces=Jupiter, not the modern outer-planet rulers -
   because that is the doctrine profections are historically computed
   with; this is not an arbitrary choice and should not be changed to
   "modern" rulerships.

3. **Solar arc direction** (`technique="solar_arc"`, the classical "key of
   Ptolemy") next - a real direction technique, degree-for-a-year, applied
   to the whole chart.

4. **Other/primary directions** (different "keys" - Regiomontanus,
   Placidus-under-pole, etc., computed via true diurnal motion rather than
   simple arc addition) are NOT YET IMPLEMENTED in this service. Don't
   claim to perform them; if asked, say so plainly rather than
   approximating with solar_arc under a different name.

5. **Secondary progressions, transits, and solar returns are secondary /
   optional / cross-check tools, not primary rectification drivers.**
   Progressions in particular describe internally-experienced development
   more than externally-verifiable events, which makes them a weaker
   rectification signal than directions or profections - use them for
   corroboration, not as the main search technique. Transits are good for
   confirming a candidate against events with an exactly known date/time
   (they don't depend on birth hour except through the natal points they
   aspect). Solar returns are the most expensive technique computationally
   (see "Performance" below) and are best used sparingly, as a tiebreaker
   or cross-check on a small number of already-narrowed candidates.

## Never assign subjective event weights

The `weight` field on scan events defaults to 1.0 and should stay that way.
Do not invent "significance" weights based on your read of the person's
personality or which events seem more important - this was tried and
reversed. A natal chart either shows a correspondence to an event or it
doesn't; deciding in advance how much an event "should" count is
interpretation dressed up as data, and it visibly changes which candidate
wins. If the person explicitly wants to experiment with weighting, that's
their call to make explicitly per-event - not a default you apply.

## Realistic expectations

Rectification from a completely unknown birth time, using only life
events, does not reliably converge to one answer. Across real sessions:
different technique families (transits vs. progressions vs. solar returns)
have produced meaningfully different leading candidates for the same
person on the same event set. Say this plainly rather than presenting one
number with false confidence. If the person has ANY independent
information - even a rough "morning" vs "evening", or a ±1 hour window
from family/records - that constrains the search enormously and should be
used as a hard filter before searching, not discovered by search alone.

## Timezones

- Prefer `tz_str` (IANA zone name) for modern dates - Python's `zoneinfo`
  correctly and automatically resolves DST, including for future dates,
  more reliably than older astrology software with static transition
  tables.
- For historical dates, especially Soviet-era locations, do NOT trust
  old software's timezone tables uncritically - cross-check with an
  independent source (e.g. reasoning about the natural longitude-based
  zone plus the 1930 Soviet decree-time rule) when the location is near a
  zone boundary. A real case: a Western-Siberian village was found to be
  UTC+7, not the UTC+8 initially assumed from a legacy astrology program.
- `tz_offset_minutes` (explicit, whole-hour) overrides `tz_str` when both
  are given - use it for verified historical offsets, or whenever you've
  independently confirmed the correct value.
- For ambiguous/nonexistent local times at a DST transition (the skipped
  hour in spring-forward, the repeated hour in fall-back), don't rely on
  local-time resolution at all - compute the moment in UTC yourself and
  pass it with `tz_offset_minutes=0`.

## Coordinates

This service never geocodes place names - only explicit decimal `lat`/
`lng`. For real locations, get coordinates from Wikipedia's infobox or
Wikidata (property P625: coordinate location) rather than guessing or
relying on a possibly-outdated gazetteer. This also sidesteps the "small
village not in the database" problem entirely.

## Performance / async

`rectif_scan` is synchronous and fine for a few hundred candidates times a
handful of transit/progression/solar_arc/profection events. For anything
bigger - wide time ranges, many events, or ANY use of
`technique="solar_return"` (its iterative per-candidate search is several
times more expensive than the other techniques and can push a full-day
scan well past MCP/proxy timeouts even though the server keeps working) -
use `rectif_scan_start` + poll `rectif_scan_result` instead of blocking on
`rectif_scan`.

## Practical scan workflow

1. `rectif_trutina` for a free first estimate (or two, given the two
   branches).
2. A coarse `rectif_scan` (or `_start` if solar_return is involved) across
   the full day, step a few minutes, using profections and solar_arc
   directions as the primary events.
3. Narrow to the leading window(s) with a finer step (`step_seconds` is
   supported for sub-minute precision once a region is found).
4. Cross-check the leading candidate(s) with `rectif_technique` calls
   using transits on events with an exactly known date/time, and
   optionally solar returns, before presenting a final answer.
5. If different technique families disagree on the leading candidate,
   say so explicitly rather than picking one silently - see "Realistic
   expectations" above.
