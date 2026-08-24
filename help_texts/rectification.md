# Rectification methodology

This is accumulated, hard-won practice from real rectification sessions
with this service, cross-checked against a substantial survey of
published Russian-language rectification literature (see "Sources"
below). It is not a single author's doctrine - where sources disagree,
that's noted explicitly rather than papered over. Deliberately excluded
from this survey: anything by Pavel Globa, and Vedic/Indian astrology -
per this project's explicit direction, not because of any technical flaw.

## Technique priority order

1. **`rectif_trutina`** first, always - it's free (a handful of direct
   calculations, not a scan) and needs zero life events. Run it before
   anything else, even with completely unknown birth time. It follows Jan
   Kefer's original 1939 formulation and returns FOUR branches (Moon
   above/below horizon, independently combined with waxing/waning phase -
   these are two separate conditions, not synonyms, despite some later
   secondary sources conflating them). One or more branches may report
   `cycle_detected: true` with a `cycle_candidates` list instead of a
   single converged time - a genuine, documented property of the
   classical method on some charts, not a bug. **If the mother's own
   birth data is available, ask for it and pass it** - the Jonas Rule
   refinement (mother_year etc. parameters) fixes the conception date
   directly via the mother's natal Sun-Moon angle, removing the classical
   method's single biggest weakness (roughly ten candidate conception
   dates per gestation window that the classical rule alone can't tell
   apart).

2. **"Elements of house" scoring** (Shestopalov/St.Petersburg Academy of
   Astrology school, formalized by S. Aizin) is the structural backbone
   for most of what follows. For a house, its elements are: the ruler of
   the sign on the cusp, the co-ruler (ruler of the next sign, if the
   house extends more than ~13 degrees into it), and any natal planet
   actually sitting in that house. `rectif_scan` computes this
   automatically per candidate when an event specifies `target_houses`
   (a list of house numbers) instead of a fixed `target_points` list -
   see engine/houses.py. **Classify which houses apply to an event by
   reasoning through the chain of real-world consequences (Aizin's
   method), not a rigid lookup table**: marriage isn't "just house 7" -
   trace what actually changes (partnership=7, shared home=4, new social
   circle=3, status=10, and so on depending on the specifics you're
   told), and only include houses whose connection to the event is real
   for that specific case. A worked derivation you can reuse directly:
   relatives map onto "houses from houses" (a grandmother is 3rd-house
   kin, but also the 4th-from-4th or 10th-from-10th depending on the
   parent's side and the native's sex - i.e. 1st, 3rd or 7th house
   depending on the case; work this out the same way for any relative,
   not just grandparents). Modern rulerships are used here (not the
   traditional set used by profections below) - this is the doctrine the
   surveyed 20th-century Russian schools use for this specific technique.

3. **Profections** (`technique="profection"`). Traditional (Hellenistic)
   sign rulerships are used deliberately - Scorpio=Mars, Aquarius=Saturn,
   Pisces=Jupiter, not the modern outer-planet rulers - because that is
   the doctrine profections are historically computed with; this is not
   an arbitrary choice and should not be changed to "modern" rulerships.

4. **Solar arc direction** (`technique="solar_arc"`, the classical "key of
   Ptolemy") - degree-for-a-year, applied to the whole chart. A specific,
   historically important special case worth running on its own even
   outside a full scan: on the date of a first marriage, the DIRECTED
   Midheaven (not progressed - true solar-arc-style direction) forming a
   tight (30 arcminute or less) aspect to the marriage significator -
   Venus/Moon for a man (day/night birth respectively), Sun/Mars for a
   woman - is one of the most consistently documented single
   rectification markers in the surveyed literature (traced through A.
   Witte's Hamburg School founding work on the hypothetical body
   "Cupido", via S. Vronsky and his student A. Semenko, to S.
   Shestopalov's later popularization). This specific rule requires
   **Koch houses**, not Placidus - the Shestopalov-school sources are
   explicit that it does not transfer cleanly to other house systems.

5. **True primary directions** (not yet implemented in this service under
   that name - the Ptolemaic key is documented: 1 year = 1 degree of
   arc, 1 month = 5 arcminutes, 6 days = 1 arcminute, measured via RIGHT
   ASCENSION, not ecliptic longitude directly - ecliptic positions must
   be converted to the equator first). Several other named auxiliary
   methods exist in the classical literature with much weaker evidence
   behind them and are not implemented: Bonatti's method (an angle is
   the midpoint of Sun and a planet, or in conjunction with a planet if
   the Sun is afflicted), Glahn's "harmony law", and "Herich's number" (a
   formula from Sun+Moon+Saturn longitudes; even its own author
   acknowledged an ~8 degree margin of error). Don't claim to perform
   primary directions or these minor methods; if asked, say they're
   documented but not yet implemented, rather than approximating them
   under a different name.

6. **Secondary progressions, transits, and solar returns are secondary /
   optional / cross-check tools, not primary rectification drivers.**
   This is a formal distinction, not a stylistic preference: **directions
   describe objectively verifiable events; progressions describe
   subjective, internally-experienced reactions to them** (documented
   explicitly by B. Israitel, with a striking example: a direction
   correctly showed a client's father had died before the client
   subjectively knew it - the progression only activated later, when the
   news actually reached him). Use progressions for corroboration, not as
   the main search technique. Transits are good for confirming a
   candidate against events with an exactly known date/time. Solar
   returns are the most expensive technique computationally (see
   "Performance" below) and are best used sparingly, as a tiebreaker on a
   small number of already-narrowed candidates.

## Never assign subjective event weights

The `weight` field on scan events defaults to 1.0 and should stay that
way. Do not invent "significance" weights based on your read of the
person's personality or which events seem more important - this was
tried and reversed. A natal chart either shows a correspondence to an
event or it doesn't; deciding in advance how much an event "should" count
is interpretation dressed up as data. If the person explicitly wants to
experiment with weighting, that's their call to make explicitly
per-event - not a default you apply.

If you do want a principled, non-subjective reason to weight events
differently, weight by **how precisely the event's date/time is known**
(a dated-to-the-second event is a sharper astrological test than "some
time in 1988"), not by presumed psychological importance - this reflects
real signal quality rather than your read of the person's character.

## Realistic expectations

Rectification from a completely unknown birth time, using only life
events, does not reliably converge to one answer - and this is not just
an implementation limitation of this service. S. Aizin's own formal
treatment states plainly that rectifying a chart from literally zero
starting information (place, date, and events only - no time window at
all) is, as of his writing, an unsolved problem. Real sessions with this
service have shown the same thing empirically: different technique
families (transits vs. progressions vs. solar returns) can produce
meaningfully different leading candidates for the same person on the
same event set. Say this plainly rather than presenting one number with
false confidence. If the person has ANY independent information - even a
rough "morning" vs "evening", or a +/-1 hour window from family/records -
that constrains the search enormously and should be used as a hard
filter before searching, not discovered by search alone.

## House system choice matters and isn't neutral

Different sources in the surveyed literature explicitly disagree on this
and say so:
- The Shestopalov school insists on **Koch houses** specifically for its
  "elements of house" technique and the profective-MC marriage rule,
  citing that Koch houses work strictly cusp-to-cusp (per Gauquelin's
  research), unlike some other systems whose sphere of influence is
  argued to start partway into the previous house.
- V. Uranov, working independently, uses **Placidus** and reports it
  working just as well for character and event correspondence in his
  practice.
- S. Aizin explicitly notes that rectifying in one house system does not
  carry over to another - each system corresponds to a different actual
  moment, and switching systems means rectifying again from scratch
  (though a chart already rectified in one system narrows the search a
  lot for the next).

Don't treat house system as an incidental setting. If a technique's
source specifies one, use that one for that technique; don't mix a
Koch-specified rule with a Placidus chart and expect the historical
success rate to transfer.

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

For events that happened far from the birth location (more than a few
hundred kilometers/miles - B. Hammerslaf's rectification book uses 300
miles as a rule of thumb), consider checking transits against the
RELOCATED chart's angles (natal angles recomputed for the event's
location, same birth moment) rather than only the natal-location angles -
a person can respond to a transit hitting their relocated angle even
when it misses the birth-location angle by a wide margin. Hammerslaf
documents a real case where a transiting Jupiter offer-of-employment
event missed the natal MC by several degrees but landed exactly on the
MC of the chart relocated to where the person was actually living at the
time. Not yet implemented as a dedicated technique in this service.

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

1. `rectif_trutina` for a free first estimate (ask for the mother's birth
   data if at all possible, to enable the Jonas Rule refinement).
2. A coarse `rectif_scan` (or `_start` if solar_return is involved) across
   the full day, step a few minutes, using profections and solar_arc
   directions as the primary events - prefer `target_houses` (reasoned
   per-event, see above) over the generic angle/luminary default
   `target_points` wherever you can identify which houses genuinely apply.
3. Narrow to the leading window(s) with a finer step (`step_seconds` is
   supported for sub-minute precision once a region is found).
4. Cross-check the leading candidate(s) with `rectif_technique` calls
   using transits on events with an exactly known date/time, and
   optionally solar returns, before presenting a final answer.
5. If different technique families disagree on the leading candidate,
   say so explicitly rather than picking one silently - see "Realistic
   expectations" above.

## Sources surveyed

Real, attributed, published sources this methodology draws on (Russian
rectification literature, mostly 1990s-2000s bulletins and books, plus
one 1939 classical text and one contemporary English-language book):

- A. Grishchenyuk (1996) transcribing the Zaprjagaev/Vronsky/Shestopalov
  lineage - "elements of house", Koch houses, three-movement confirmation
- A. Budarovsky (Crimean Astrological Academy, same lineage) - real
  worked example, necessary/sufficient aspect distinction
- S. Aizin - formal house-derivation logic ("houses from houses" for
  relatives), interval-intersection rectification algorithm, explicit
  statement that zero-information rectification is unsolved
- B. Israitel - directions-vs-progressions (objective/subjective)
  distinction, four direction speeds, event-to-significator tables,
  the "condensation method" (clustering transit degrees across many
  events)
- S. Kudyanov, A. Kolesnikov, V. Tkachenko - Trutina refinements
  including the Jonas Rule
- Jan Kefer, Prakticka Astrologie (1939) - the original four-branch
  Trutina formulation, plus Bonatti/Glahn/Herich/primary-direction
  summaries
- V. Uranov - practical workflow, Placidus-based practice, event
  checklist
- B. Brady - graphic/histogram rectification (clustering slow-planet
  transit degrees across ~15 angular life events)
- B. Hammerslaf - data collection practice, relocated charts, Uranian
  45-degree/90-degree dial techniques
- I. Timoshenko - a four-rule bidirectional aspect requirement (house
  ruler AND cusp must both send and receive at least one directed
  aspect each) combined with an interval-intersection search, claiming
  second-level precision; not yet implemented in this service
- V. Shatskaya - profective-MC + sidereal-time calculation, a real
  case confirmed independently by the client's mother
- M. Levin - live transit-to-angle rectification practice; the heuristic
  that a parent's Sun or Moon often falls on a child's ASC/DSC/MC
- I. Zhuravleva - historical provenance of the profective-MC marriage
  rule (Witte to Vronsky to Semenko to Shestopalov), classical marriage
  significators from Ptolemy, Ibn Ezra, Al-Kindi, and Lilly, and D.
  Kutalev's general Arabic Parts formula (cusp + ruler - significator by
  day, Asc + significator - ruler by night) for any house, not just
  marriage/Fortune
