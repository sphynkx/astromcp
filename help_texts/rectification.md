# Rectification methodology

This is accumulated, hard-won practice from real rectification sessions
with this service, cross-checked against a substantial survey of
published Russian-language rectification literature (see "Sources
surveyed" at the end). It is not a single author's doctrine - where
sources disagree, that's noted explicitly rather than papered over.
Deliberately excluded from this survey: anything by Pavel Globa, and
Vedic/Indian astrology - per this project's explicit direction, not
because of any technical flaw.

## How to use this document - read this section first, every single time

**This file is binding operating instructions, not background reading
to half-remember from earlier conversations.** Read it in full at the
start of every rectification session - including a session that
continues one already in progress - and follow it as a literal
procedure. Do not rely on having "generally done this before": a prior
session's habits, shortcuts, or which tools happened to get used are
not a substitute for actually reading this document again. A real,
documented failure mode: sessions drifted toward relying on two or three
familiar tools while several implemented, source-documented techniques
sat unused for long stretches, and an invented-scoring tool kept
reappearing in final conclusions despite an explicit standing rule
against it - not because either was ever decided to be the right call,
but because the fuller method wasn't re-read and re-applied each time.
That is a methodology failure, not a reasonable adaptation, and this
document exists specifically to prevent it from happening by default.

**Each rectification is an independent task, evaluated fresh.** Assume
this may be a brand-new conversation with no memory of any other person
ever rectified with this service, because it may genuinely be one - the
person may open a new chat per person specifically to avoid carrying
history across cases. Nothing about a DIFFERENT person's chart, an
earlier session's numeric findings, or an earlier session's shortcuts
should influence how thoroughly THIS person's case is worked. Every
session gets the full method below, regardless of how many times it's
been run before.

**Time and tool-call budget are not a constraint on how much of this
method gets applied.** A thorough rectification legitimately takes many
dozens of tool calls across multiple techniques per event. That cost is
accepted and expected - never shorten, skip, or reorder the sequence
below to save time or effort. If a session's scope or the person's own
stated preference genuinely calls for doing less than the full method,
that is a decision to discuss explicitly and agree on with the person
BEFORE proceeding - never a default to fall into silently.

**This is analytical work, not a mechanical checklist.** At every step,
actually reason about the event: what it concretely meant in this
person's life, which houses/significators that meaning implies (see
"Reasoning about which houses apply to an event" below), whether the
source recording the event or the time is trustworthy. Running
techniques without engaging with what they mean produces numbers, not a
rectification.

## Absolute rule: never invent a scoring or weighting scheme

**It is forbidden to invent point systems, significance weights, or any
other numeric scoring/ranking scheme not itself part of a named,
documented rectification method, and forbidden to use one for counting,
ranking, or deciding between candidates - under any framing, including
"rough", "exploratory", or "just for orientation".** This rule has been
stated before and was not followed reliably; it is restated here in the
strongest terms because of that, not as a hypothetical.

Concretely:

- **`rectif_scan`'s `total_score`/per-event `score` fields must never be
  read, cited, mentioned, or reasoned from - full stop.** Summing a
  hit-count across unrelated events into one number and ranking
  candidates by it is not a method any surveyed source uses; it was
  invented for this service. An earlier, weaker version of this rule
  allowed citing the score "if clearly labeled as exploratory" - that
  carve-out was used repeatedly, across many real sessions, to justify
  putting numbers like "балл 103" directly into final conclusions shown
  to the person. The carve-out is withdrawn. `rectif_scan`'s sweep
  mechanism (stepping through many candidate clock times in one call)
  may still be used purely as a convenience, but only by reading
  `include_full_table=true`'s real per-candidate aspect/orb values -
  exactly as if each candidate had been checked with an individual
  `rectif_technique` call - never its score. If that distinction makes
  `rectif_scan` feel pointless to reach for, that is correct: prefer the
  criterion-based tools in the inventory below, or direct
  `rectif_technique` calls, in the first place.
- **Do not assign a numeric `weight` to an event** based on a read of
  the person's personality or which events seem more important. A chart
  either shows a correspondence to an event or it doesn't; deciding in
  advance how much an event "should" count is interpretation dressed up
  as data. The `weight` field defaults to 1.0 and stays there unless the
  person explicitly asks to experiment with it themselves.
- **What this rule does NOT forbid**: a documented method's own literal,
  published output is not "invented scoring", even when it involves a
  count. `rectif_degree_clustering`'s frequency count (how many events'
  transiting slow planets land on the same degree) is Israitel's and
  Brady's own stated method - that count IS the technique, not a summed
  heuristic layered on top of it. `rectif_movements_scan`'s "N of 3
  movements concordant" is Grishchenyuk's own literal published
  threshold. Reproducing a named author's rule and reporting exactly
  what they say to report is the opposite of inventing one.

## Complete inventory of implemented techniques - read this before choosing which to run

Every technique below is real, callable, and expected to be used where
it applies - per "Full mandatory sequence" further down, not
cherry-picked. This list exists so a technique is never skipped simply
because it wasn't remembered to exist; check against this list, not
memory, at the start of a session.

**`rectif_trutina`** - Jan Kefer's Trutina Hermetis (1939). No life
events needed at all; run it first, always, even with a completely
unknown birth time. Returns four independent branches (Moon above/below
horizon, crossed with waxing/waning - two separate conditions, not
synonyms). Pass the mother's own birth data when available (`mother_*`
parameters) for the Jonas Rule refinement, which fixes the conception
date via the mother's natal Sun-Moon angle instead of leaving ~10
candidate conception dates per gestation window undecided.

**`rectif_technique`** (single candidate, single event) and
**`rectif_scan`**/**`rectif_scan_start`+`rectif_scan_result`** (many
candidates swept at once, score fields ignored per the rule above) both
dispatch on a `technique` string. All of the following are valid values
- **all are available in `rectif_technique`; `rectif_scan` currently
  supports `transit`, `secondary_progression`, `solar_arc`,
  `solar_return`, `lunar_return`, and `profection` - use `rectif_technique`
  directly for `primary_direction_zodiacal` and `relocated_transit`
  across a sweep of candidates, one call per candidate**:

- `"transit"` - real transiting planets at a real event date/time,
  compared to the natal chart. **When the event's own clock time is
  known, always pass it via `target_hour`/`target_minute`/`target_second`
  - this is categorical, not optional** (see "Always pass known event
  times" below). Good for cross-checking a candidate against a precisely
  dated/timed event.
- `"secondary_progression"` - "a day for a year": the chart cast for
  the natal-day-plus-elapsed-years. Per B. Israitel, progressions
  describe SUBJECTIVE, internally-experienced reactions to events, as
  opposed to directions' objective description of the event itself
  (documented example: a direction showed a client's father's death
  before the client knew of it; the progression only activated once the
  news actually reached him) - run alongside directions, not instead of
  them, and don't expect it to peak exactly ON an event's own date for
  that reason.
- `"solar_arc"` - the classical Ptolemaic "key": the real transiting
  Sun's actual motion since birth applied as a uniform arc to the whole
  natal chart. **Mandatory for every event, including imprecisely-dated
  ones** (see "Directions are mandatory for imprecise dates" below).
  Special documented case: on a first marriage's date, the DIRECTED
  Midheaven forming a tight (<=30 arcminute) aspect to the marriage
  significator (Venus/Moon for a man, Sun/Mars for a woman, by day/night
  birth respectively) is one of the most consistently attested single
  rectification markers in the surveyed literature (Witte to Vronsky/
  Semenko to Shestopalov) - **requires Koch houses**, not Placidus.
- `"solar_return"` - the chart for the moment the transiting Sun exactly
  returns to its natal degree in a given year. Computationally the most
  expensive technique (see "Performance" below) - batch/scope
  accordingly, but that is a performance note, not a reason to skip it.
- `"lunar_return"` - the same mechanism as solar_return but for the
  Moon, which recurs roughly every 27.3 days rather than once a year.
  Pass a full target date (year+month+day), not just a year - the tool
  resolves to whichever actual lunar return falls nearest that date and
  reports the real instant used in `lunar_return_utc`; check that field
  rather than assuming the return lands exactly on the target date.
- `"profection"` - the Hellenistic annual/monthly profection technique.
  Uses TRADITIONAL sign rulerships deliberately (Scorpio=Mars,
  Aquarius=Saturn, Pisces=Jupiter - not modern outer-planet rulers),
  because that is the doctrine this technique is historically computed
  with.
- `"primary_direction_zodiacal"` - Jan Kefer's zodiacal primary
  direction, MC/IC only (the classical Ptolemaic key - 1 year=1 degree,
  1 month=5 arcminutes, 6 days=1 arcminute - applied via right ascension
  rather than ecliptic longitude directly). Scope is deliberately
  MC/IC-only; Kefer's fuller method directs other points too via
  spherical-trigonometry oblique ascension under the local pole, which
  is not implemented.
- `"relocated_transit"` - B. Hammerslaf's technique: for an event that
  happened far from the birth location (300+ miles/a few hundred
  kilometers is Hammerslaf's own rule of thumb), the person may respond
  to a transit hitting the ANGLES of the chart relocated to where they
  actually were, even when the birth-location angles miss it by a wide
  margin. Rebuilds the natal chart's angles/houses at the relocated
  coordinates (same birth instant), then compares real transiting
  planets against those relocated angles.

**Criterion-based tools** - each reproduces one named author's literal,
published decision rule and reports which candidate time(s) satisfy it,
not a ranking:

- **`rectif_movements_scan`** - A. Grishchenyuk's three-movements rule
  (secondary progression + "perfection"/30-degree-per-year symbolic
  direction + transit; >=2 of 3 concordant is the source's own stated
  threshold for ~100% confidence). Returns `qualifying_windows`
  (contiguous time ranges), not a leaderboard. If a very high fraction of
  the scanned range qualifies, the default orb is too loose to be
  informative for that specific event alone - tighten the orb for that
  call, or intersect with another event's qualifying windows, rather
  than treating a near-total-qualification result as confirmation of
  anything.
- **`rectif_timoshenko_scan`** - I. Timoshenko's four-condition test for
  one house at one event: the DIRECTED ruler must send a hard aspect
  (0/90/180) to a natal house element, the DIRECTED cusp must likewise
  send one, the NATAL ruler must receive one from a directed element,
  the NATAL cusp must likewise receive one - all four required (an AND,
  not a threshold). The source claims 10-30 second precision from this
  combination; that specific claim has not been independently
  re-verified by this implementation, only the mechanical test itself.
- **`rectif_bonatti_scan`** - Guido Bonatti's method (via Kefer, 1939):
  purely a Sun-affliction/angle rule, no life events needed at all. The
  source's own explicit instruction is to use this only combined with
  another correction, never alone - treat a qualifying window here as a
  weak auxiliary signal to intersect with something stronger, not
  standalone evidence.
- **`rectif_herich_scan`** - Paul von Gerich's "Herich's number" (1929/
  1930): a Sun/Moon/Saturn midpoint-chain formula against the angles (or
  any house cusp). The source's own stated orb is 8 degrees, and even
  its author acknowledged a possible discrepancy of that same size -
  same caution as Bonatti's method: weak auxiliary only, never alone.
- **`rectif_degree_clustering`** - B. Israitel's "condensation method"
  and B. Brady's "graphic rectification" (closely related, sharing a
  mechanism): tallies where TRANSITING slow planets (Mars through Pluto
  plus the nodes - fast personal planets and the Moon are excluded as
  too imprecise for this method) land, in absolute zodiacal degrees, on
  the dates of many life events, and finds which degrees recur most
  often. A recurring degree with no natal planet there is a candidate
  ANGULAR house cusp. Unusually, **this method needs no birth time
  scan at all** - only event dates - since it works from real transiting
  positions on real dates; it produces a candidate DEGREE, which then
  still needs a separate step to find what birth time would put that
  degree on an angle. Israitel's version wants uncertainty already down
  to 20-30 minutes or less before it's useful; Brady's wants ~15 angular
  events (relationship/birth/death of close people specifically). The
  frequency count this returns is the method's own literal output, not
  invented scoring (see the rule above).

**Documented but genuinely not implemented** - say so plainly if asked,
rather than approximating under a different name: true primary
directions for points other than MC/IC (the oblique-ascension machinery
for the Ascendant and other points), Glahn's "harmony law".

## Full mandatory sequence

Apply this to every rectification, start to finish. Steps are ordered;
do not reorder or skip without explicit prior discussion with the
person (see "How to use this document" above).

1. **Assess the source(s) for the stated birth time** (see "Assess
   source quality" below) before running anything else - this shapes
   how much weight a documented-but-unconfirmed time deserves relative
   to what the search finds, not whether to search at all.
2. **`rectif_trutina`**, always, with the mother's birth data if it can
   be obtained (ask for it explicitly if not already given).
3. **Gather personal events**: every marriage, divorce, child's birth,
   and death of a close family member, asking explicitly for
   approximate dates if not volunteered - including imprecisely-dated
   ones. Do this before leaning on any public/career event (see
   "Personal events take priority" below).
4. **For every personal event with a known clock time**: sweep
   `transit` across the full plausible natal-time window (the source's
   own stated range if one exists, otherwise a sensibly wide default) at
   roughly 5-minute steps, reading real aspects/orbs directly (never a
   `rectif_scan` score). Then cross-check the same event with
   `secondary_progression`.
5. **For every personal event without a known clock time**: run the
   full direction stack in order - `solar_arc`, `secondary_progression`,
   `profection`, `lunar_return` - all four, not whichever comes to mind
   first.
6. **Run `rectif_movements_scan` for every event from steps 4-5**
   alongside the individual technique checks, using `target_houses`
   reasoned per-event (see "Reasoning about which houses apply" below)
   and Koch houses. Where relevant, also run `rectif_timoshenko_scan`.
7. **Public/career/minor events (awards, releases, appearances) still
   get the full technique stack from steps 4-6** - not skipped, not
   reserved for "important" events only. They are weighted lower in
   confidence when reasoning about the outcome (see "Personal events
   take priority" below), which is a difference in how much a result
   moves the conclusion, never a reason to skip running the technique.
8. **Intersect, never sum.** Take each event's qualifying windows/
   direct-verified hits and intersect them across events - only keep
   candidates that qualify for EVERY event checked (or report plainly
   that nothing survives the intersection, and why). If personal and
   public events' surviving sets disagree, prefer whichever is confirmed
   more thoroughly and more tightly, and say so explicitly.
9. **`rectif_bonatti_scan`, `rectif_herich_scan`, and, if enough events
   exist, `rectif_degree_clustering`** as auxiliary cross-checks,
   intersected with (never substituted for) the above.
10. **Narrow with `step_seconds`** once a surviving window is small
    enough (see "Attempt second-level precision" below).
11. **Final direct re-verification**: individually re-check the
    surviving candidate(s) against the strongest events using every
    applicable technique from the full stack, not just transits, before
    presenting an answer.
12. **Report** using the format below.

## Mandatory final report format

The person must always be able to see the full process, not just a
final number - report format is not optional cosmetic detail.

Present, in this order:

1. **Source assessment** - what was stated, how strong the source is,
   and any alternative times under consideration.
2. **Technique-by-technique results table**: for every technique
   actually run (per the inventory above), list which one, which
   event(s) it was run against, and its real result (qualifying
   window(s), or the specific aspect/orb found by direct verification) -
   not a score. Group by event if that reads more clearly for a
   particular case (a list of events, each with its result under every
   method applied to it) - either grouping is fine as long as every
   technique's actual application and actual output is visible, not
   summarized away.
3. **Intersection/narrowing steps** - how the surviving candidate set
   was reached from the individual results above, stated explicitly
   enough that the narrowing itself could be checked by someone else.
4. **Final verdict** - the resulting time range, and the single most
   probable time within it if one is warranted (see "Attempt
   second-level precision" and "Realistic expectations" below for when
   a single point isn't warranted and a range should be reported
   instead). State the location the time is given in (see "Timezones"
   below - always true LMT with the location named, never an internal
   working-zone shift left unconverted).

## Assess source quality before starting, and re-verify it as carefully as any winning candidate

Not every stated birth time carries the same weight:

- A birth certificate in hand, corroborated independently by a
  published autobiography AND a separate biography (Salvador Dalí's
  8:45, astro-databank rating from a primary document) is about as
  strong as birth-time evidence gets.
- A time relayed secondhand through an interview, a family member's
  recollection, or an unsourced online post is real evidence, but
  weaker and more prone to rounding/misremembering.
- No stated time at all means a genuinely blind search across the full
  day, which behaves differently (see the next section) from searching
  near an already-plausible anchor.

This matters operationally, not just rhetorically: a documented time
must be checked with the SAME direct rigor - real `rectif_technique`
calls against the strongest events, not just its rank in an exploratory
`rectif_scan` - as whatever candidate a search turns up as the top
scorer, before concluding the two disagree. A real session (Salvador
Dalí, 11.05.1904) initially dismissed a birth-certificate-sourced 8:45
as unsupported, based only on its middling position in a wide exploratory
scan - and, when directly re-checked with the same rigor given to the
scan's top candidate, 8:45 turned out to show an aspect (0.003 degrees,
exact) tighter than the one that had been presented as the winner. The
error wasn't the scan - it was skipping the direct-verification step for
the well-documented candidate specifically because the scan's coarse
score made it look unnecessary. Never skip that step for a
well-documented candidate, regardless of where it ranks in an
exploratory pass.

## Wide blind searches produce tight-looking coincidences more often - don't let that alone override a good source

When no birth time is stated at all, a full-day search (as many as
several hundred candidates, each compared against every event) is
sometimes the only option - but it changes the odds. Testing hundreds
of candidates against many events means SOME candidate will show a
tight, thematically-plausible-sounding aspect somewhere in the day
purely by chance - this is the same statistical phenomenon as multiple
comparisons in any other field, not a flaw specific to this method.
A tight orb found this way is real (the math is correct), but it carries
less evidential weight per hit than the same tight orb found while
checking a specific, independently-motivated candidate (a stated time,
a prior technique's convergence point). When a wide blind search's top
candidate conflicts with a well-documented stated time by several hours,
the right response is not to trust the search's top hit by default - it
is to give the documented time the same direct, event-by-event
verification the search's winner already got (see previous section)
before deciding there's a real conflict at all.

## Reasoning about which houses apply to an event

"Elements of house" (Shestopalov/St.Petersburg Academy of Astrology
school, formalized by S. Aizin) is the structural backbone for
`target_houses` across most techniques above. For a house, its elements
are: the ruler of the sign on the cusp, the co-ruler (ruler of the next
sign, if the house extends more than ~13 degrees into it), and any natal
planet actually sitting in that house.

**Classify which houses apply to an event by reasoning through the chain
of real-world consequences (Aizin's method), not a rigid lookup table**:
marriage isn't "just house 7" - trace what actually changes
(partnership=7, shared home=4, new social circle=3, status=10, and so on
depending on the specifics you're told), and only include houses whose
connection to the event is real for that specific case. A worked
derivation to reuse directly: relatives map onto "houses from houses" (a
grandmother is 3rd-house kin, but also the 4th-from-4th or 10th-from-10th
depending on the parent's side and the native's sex - i.e. 1st, 3rd or
7th house depending on the case; work this out the same way for any
relative, not just grandparents). Modern rulerships are used here (not
the traditional set used by profections) - this is the doctrine the
surveyed 20th-century Russian schools use for this specific technique.

## Always pass known event times to `target_hour`/`target_minute`/`target_second`

**Categorical, not a style preference.** When running `technique="transit"`
(or any technique accepting a target time) against an event whose own
clock time is known (a death certificate, a launch time, any documented
hour/minute), pass that exact time explicitly - never call the tool with
only the date and let it silently fall back to a default. Confirmed
directly in a real session: the parameters ARE accepted and DO change
the result meaningfully - not just slow-moving transiting planets, but
the angles (Ascendant/MC) and house cusps, which move fast enough that a
same-day-wrong-hour transit chart can show materially different,
sometimes misleading, aspects. If the exact time is genuinely unknown,
running the technique on the date alone is still worthwhile - but never
let genuinely-available precision go unused.

## Personal events take priority over public/career events

**Check births of children, marriages, and divorces first, and trust
them more than career/public/political events when the two disagree.**
This is a real, repeatedly-confirmed pattern, not a stylistic
preference: a real session (Dmitry Gordon, 21.10.1967) initially
converged on a candidate driven almost entirely by media/career
milestones (YouTube channel launches, a criminal case abroad) - a
broad but, on reflection, public-facing cluster. A dedicated pass
checking all six of his children with exactly-known birth dates (out
of seven total) against the SAME candidate window found the
public-event candidate showed almost nothing for the family events,
while a different candidate roughly two hours away showed six-for-six
near-exact direction hits (several under 0.1 degree) across 27 years
of family history. The family-driven candidate was adopted as the
final answer over the public-event one specifically because it was
more thoroughly and more tightly confirmed - not because personal
events are dogmatically "more correct" in principle, but because in
this case they demonstrably gave the sharper, more numerous
correspondences. The general lesson: public/career events are numerous
and easy to reach for (frequently exact-dated, well-documented,
convenient) precisely because they're public - that convenience is not
evidential strength. A person's own marriages, divorces, and children's
births sit closer to the chart's own core significations (VII, V, and
their rulers) than a film premiere or a channel launch does, and should
be gathered and checked BEFORE leaning on a public-event-only
convergence as a final answer. If the person hasn't volunteered this
information, ask for it explicitly.

This does not license assigning children/marriages a higher numeric
`weight` - see "Absolute rule: never invent a scoring or weighting
scheme" above, which still applies. The priority here is about
investigative order and which evidence to trust when two categories of
events point to different candidates, not about feeding a different
number into anything.

## Directions are mandatory for imprecise dates, not optional

Every event with only a year, or a year+month, known - not just the
precisely-dated ones - must still be run through the full direction
stack (see "Full mandatory sequence" step 5), using a reasonable
specific day within the known range (documented as an assumption)
rather than skipped for lack of precision. An imprecise date is exactly
the situation directions are suited for: solar arc moves about 1 degree
per year, so a day-level uncertainty within a known month, or a
month-level uncertainty within a known year, changes the resulting arc
by a small fraction of a degree - well inside normal orb tolerances -
while still contributing real evidence. Skipping imprecise events
because they "aren't exact enough" throws away information directions
can use perfectly well; it's transits, mainly, that need exact dates,
not directions.

## Attempt second-level precision, and say plainly when it isn't reached

Once a candidate window has narrowed to a few minutes, always run a
final `step_seconds` pass before presenting the answer, rather than
stopping at minute-level by default. Report the outcome honestly either
way: sometimes a real, narrow plateau or peak emerges (worth stating to
the second); often, because the underlying events are dated without a
time-of-day, the fine pass shows a flat plateau spanning a minute or
more with no internal peak - that's a genuine property of the method's
resolution given day-only event dates, not a failure to look hard
enough, and should be reported as "minute-level precision" (with the
plateau's actual width stated) rather than picking an arbitrary second
within it to sound more precise than the evidence supports.

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
- **Pre-standardization births (before local/national timezone adoption -
  Russia before 1919, Germany before 1893, France before 1911, the US
  before 1883, etc.) use Local Mean Time (LMT) based on the birth
  location's own longitude.** `tz_offset_minutes` only accepts whole-hour
  offsets, so LMT (which is essentially never a whole hour) has to be
  handled via an equivalent-shift workaround: pick a real whole-hour zone
  (commonly the location's modern zone), compute the difference between
  it and true LMT, and add that difference to every clock time before
  running any calculation in that zone. This workaround is fine
  computationally - the SAME calendar moment is being represented either
  way - but it is real-world confusing, not just a formatting nicety: a
  session that reports results in the shifted zone ("14:07") without
  converting back makes the person tracking the case verify or record
  the wrong number. **Always convert every reported candidate - the
  running short-list, the final verdict, everything a person is meant to
  read or copy down - back into true LMT before presenting it, and always
  name the location it's LMT for** ("14:07 in the PST-equivalent working
  zone" is an internal computation detail, not a result; "13:57 LMT,
  San Francisco" is the result). Do this at each step along the way, not
  only in a final summary - a person comparing two candidates mid-session
  needs both already in the same, real units to compare them at all.

## Coordinates

This service never geocodes place names - only explicit decimal `lat`/
`lng`. For real locations, get coordinates from Wikipedia's infobox or
Wikidata (property P625: coordinate location) rather than guessing or
relying on a possibly-outdated gazetteer. This also sidesteps the "small
village not in the database" problem entirely.

For events that happened far from the birth location, use
`technique="relocated_transit"` (see the technique inventory above) -
B. Hammerslaf's rectification book uses 300 miles as a rule of thumb for
when this matters - rather than only checking the natal-location angles.

## Performance / async

`rectif_scan` is synchronous and fine for a few hundred candidates times a
handful of transit/progression/solar_arc/profection events. For anything
bigger - wide time ranges, many events, or ANY use of
`technique="solar_return"` (its iterative per-candidate search is several
times more expensive than the other techniques and can push a full-day
scan well past MCP/proxy timeouts even though the server keeps working) -
use `rectif_scan_start` + poll `rectif_scan_result` instead of blocking on
`rectif_scan`. The same applies to `rectif_timoshenko_scan`/
`rectif_bonatti_scan`/`rectif_herich_scan` over wide ranges.

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
  events) - implemented as `rectif_degree_clustering`
- S. Kudyanov, A. Kolesnikov, V. Tkachenko - Trutina refinements
  including the Jonas Rule
- Jan Kefer, Prakticka Astrologie (1939) - the original four-branch
  Trutina formulation, the zodiacal primary direction (MC/IC), plus
  transcriptions of Bonatti's and Glahn's methods
- V. Uranov - practical workflow, Placidus-based practice, event
  checklist
- B. Brady - graphic/histogram rectification (clustering slow-planet
  transit degrees across ~15 angular life events) - implemented as
  `rectif_degree_clustering`, sharing a mechanism with Israitel's method
- B. Hammerslaf - data collection practice, relocated charts
  (implemented as `technique="relocated_transit"`), Uranian
  45-degree/90-degree dial techniques (not implemented)
- I. Timoshenko - a four-rule bidirectional aspect requirement (house
  ruler AND cusp must both send and receive at least one directed
  aspect each) combined with an interval-intersection search, claiming
  second-level precision - implemented as `rectif_timoshenko_scan`; the
  specific precision claim has not been independently re-verified, only
  the mechanical test itself
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
