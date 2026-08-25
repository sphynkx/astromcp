# Bibliography

Sources surveyed while developing the rectification methodology for this
service (see `help_texts/rectification.md` for the operational summary).
Mostly Russian-language rectification literature from astrological
bulletins, courses and books of the 1990s-2000s, plus one 1939 classical
text and one contemporary English-language book. Compiled here in more
detail than the help text for future reference - citations, what each
source actually contributed, and what wasn't used.

Deliberately excluded from the survey per project direction: anything by
Pavel Globa, and Vedic/Indian astrology - not evaluated on technical
merit, simply out of scope.

## Primary sources used

**Aizin, S.** "Формальные методы прогнозирования событий и ректификации
натальной карты" (Formal methods of event forecasting and natal chart
rectification). Approved/endorsed by M.B. Levin, Rector of the Academy of
Astrology. — Formal house-derivation logic ("houses from houses" for
relatives - a grandmother is 3rd-house kin directly, or 4th-from-4th /
10th-from-10th depending on lineage and the native's sex), an
interval-intersection rectification algorithm (compute continuous time
windows where a condition holds, intersect across events, rather than
scoring a discrete grid), the "Point of Life" (0 Aries progressing
symbolically), and an explicit statement that rectification from zero
starting information is, as of writing, an unsolved problem. Worked
example: Moscow, 4 Feb 1938, rectified to 16:03:42, cross-validated
against a second event 26 years later.

**Grishchenyuk, A.** (1996). Text file "REKTIF.TXT", transcribing the
Zaprjagaev -> Vronsky -> Shestopalov lineage (St. Petersburg Academy of
Astrology). — "Elements of house" (ruler + co-ruler + occupying planets),
Koch house system requirement, the three-movement confirmation rule
(secondary progression + fast/30-degree-per-year progression/profection +
transit; 3 concordant aspects across movements = ~100% event probability,
2 = ~66%), and the profective-MC-to-marriage-significator rule (30
arcminute orb; Venus/Moon for men day/night birth, Sun/Mars for women).
Worked example included (marriage + childbirth dates).

**Budarovsky, A.** (Crimean Astrological Academy, branch of the St.
Petersburg Academy - same Shestopalov lineage as Grishchenyuk).
"Ректификация карты при неточном времени рождения" (Rectifying a chart
with an imprecise birth time). — Real worked example with dated events
(award, surgeries, a trip), the "sufficient" (slow/background, readiness)
vs "necessary" (fast/event, trigger) aspect distinction, and a practical
iterative narrowing procedure (coarse 7-candidate grid, progressively
eliminated by successive events).

**Israitel, B.Z.** "Полное руководство по ректификации" (Complete Guide
to Rectification). — The formal directions-vs-progressions distinction
(directions = objectively verifiable events; progressions = subjective,
internally-experienced reactions to them - with a documented example of a
direction showing a father's death before the client subjectively knew
about it). Classification of methods (exact: primary/secondary/minor
directions, primary/secondary/tertiary progressions, solar returns,
transits; approximate: prenatal epoch/Trutina, symbolic degrees,
physiognomy, biolocation, the "condensation method"). Four direction
speeds (1deg/year classic; 1deg/12days = 30deg/year profection, 12-year
cycle; 1deg/day, ~1-year cycle; 1deg/month, ~30-year Saturn-linked cycle).
Detailed event-to-significator tables (marriage, children, surgery/
injury, moves, divorce, deaths distinguishing sudden/Pluto-VIII vs
prolonged/VI-XII). Orb guidance (Sun-related 2deg, Moon-related 1.5deg,
others 1deg; Saturn asymmetric 0.5deg applying / 1.5deg separating). The
"condensation method": for a large event set, plot transiting-planet
degrees and look for clusters with no natal planet already there,
hypothesizing an angular cusp - usable only below ~20-30 minutes of
initial uncertainty, needs a large data volume.

**Kefer, Jan.** *Prakticka Astrologie* (1939; Russian edition "Практическая
астрология", Moscow, 1991, ISBN 5-86452-004-7). — The original Trutina
Hermetis formulation used in this service: Moon above/below horizon and
waxing/waning phase treated as two INDEPENDENT conditions (four total
cases), not one condition with two states as some later secondary
sources present it. Also documents, more briefly: Bonatti's method (an
angle = midpoint of Sun and a planet, or conjunct a planet, depending on
whether the Sun is afflicted), Glahn's "harmony law" (one main axis
passes between Sun and Moon - the extracted copy of this text has a gap
right at the operative instruction for selecting which axis; not
recoverable from what was available for this project), "Herich's number"
(a formula from Sun + Moon + Saturn longitudes; the source itself
acknowledges an ~8 degree margin of error - the extracted copy of this
text also has a gap exactly where the formula belongs, see von Gerich's
own article below for how it was actually recovered), the progressive-
meridian method (sidereal-time based; 1 day = 1 year, 2 hours = 1 month,
4 minutes = 1 day - confirmed mechanically identical to this service's
existing secondary-progression technique applied to the MC, so not
separately implemented), and true primary directions via the Ptolemaic
key (1 year = 1 degree of arc; 1 month = 5 arcminutes; 6 days = 1
arcminute; computed via right ascension, requiring conversion from
ecliptic longitude) - which Kefer himself calls the most precise of the
methods he surveys, and which this service implements as
`technique_primary_direction_zodiacal` (MC/IC only - see the note there).

**von Gerich, Paul.** Article on "Herich's number" (this project's
transliteration follows Kefer's Russian edition; the original German-
language sources spell it "Gerich"), first published 1929, reprinted in
A.Frank Glahn's *Erklarung und systematische Deutung des
Geburtshoroskopes* (1930), pp.94-97, "Die Gerich'schen Harmoniegesetze".
Full formula and a worked numeric example (Kurt Eisner's chart) recovered
from a primary-source excerpt at misyats.wordpress.com/2009/12/11/gerich,
cross-checked against an independent glossary entry at
astrokot.kiev.ua/slovar/g/geriha.htm (same formula, same 8-degree orb).
This project's implementation (`rectif_herich_scan`) was verified against
Gerich's own worked example before being shipped - see BIBLIOGRAPHY.md's
sibling document TECHNIQUE_STATUS.md for the specific check performed.

**AstroZeus encyclopedia** (astro-zeus.ru/encyclopedia) - a large,
useful index of named rectification methods, consulted for cross-
reference and to locate additional named techniques not yet covered
elsewhere in this bibliography. Located one technique not found in any
other surveyed source: a claimed correspondence between house system and
a specific planet coinciding with the Ascendant/MC in the 360th harmonic
chart (Placidus-Moon, Koch-Mars, Regiomontanus-Jupiter, topocentric-
Saturn). Not implemented - every source found repeats the same short
glossary-entry-level description with no worked example and no stated
comparison orb; see TECHNIQUE_STATUS.md for what would be needed to
implement this responsibly.

**Kudyanov, S.**; discussing articles by **Kolesnikov, A.** and
**Tkachenko, V.** — Two real family cases (mother/daughter, mother/son,
with one generation's birth time independently documented) used to
cross-validate Trutina variants. Clarifies (his own reading, not
independently re-verified against Kefer here) that some authors'
"waxing/waning" language actually means "rising/setting" (horizon
position) rather than lunar phase - noted in this service's
documentation as a real point of disagreement with Kefer's original text,
resolved in favor of Kefer's four-independent-conditions formulation.
Documents the **Jonas Rule** (Dr. Eugen Jonas, medically documented):
conception occurs when the transiting Sun-Moon angular separation equals
that of the mother's own natal chart - used in this service to fix the
Trutina conception date directly rather than leaving it ambiguous.
References an additional technique from **Llewellyn George**, *Astrology
from A to Z*: bringing planetary right-ascension aspects to the MC's
right ascension on the event date (a primary-direction variant) - not
yet implemented here.

**Uranov, V.** "Хитрости ректификации" (Rectification tricks/tips). —
Practical multi-stage narrowing workflow (hourly grid via fast-progressed-
Moon sign ingresses, narrowed to tens of minutes via house tables, then
final confirmation across all aspects at once). Explicitly uses
**Placidus** houses (disagreeing with the Shestopalov school's Koch
requirement) and reports good results. Warns against over-relying on
minor aspects/asteroids ("attracting by the ears"). Practical event
checklist for client intake, and guidance that 10-20 precisely dated
events are needed for good results.

**Brady, Bernadette.** (Published Western astrologer; article on
graphic rectification theory, concept and practice, translated). —
Histogram/clustering method ("graphic rectification"): collect ~15
significant ANGULAR life events (relationship/birth/death of close
people specifically, not arbitrary events), record positions of Mars
through Pluto plus nodes (fast personal planets Sun/Moon/Mercury/Venus
explicitly excluded as too imprecise/noisy for this purpose) rounded to
the nearest degree, build a frequency histogram across 0-29 degrees;
peaks with no natal planet already present hypothesize an angular house
cusp there. Needs 80-100 data points (~15 dates) for good results.
Explicitly excludes the birth dates of older siblings/parents (chart
didn't exist yet) and the native's own death. Associated with a software
tool named "Jigsaw". Not yet implemented in this service.

**Hammerslaf, Bruce F.** *Современная техника ректификации карты*
("Modern chart rectification technique"; Russian translation of an
English-language book). — Extensive practical data-collection guidance
(a mailed worksheet, 10-20 events, emphasis on Uranus-linked events -
deaths, breakups - as giving the most precise timing; photograph
requests for physiognomy cross-check). **Relocated charts**: for events
occurring more than roughly 300 miles from the birth location, check
transits against the chart's angles recomputed for the event's location
(same birth moment) - documents a real case where a transiting Jupiter
event missed the natal MC by several degrees but landed exactly on the
relocated-chart MC. Uranian-school tools: 45-degree graphic ephemerides
(transiting planets across many event dates, watching for a recurring
degree pattern - functionally similar to Brady's histogram approach but
via a dial rather than tabulation) and the 90-degree dial applied to
directed (solar arc / lunar arc) planets, with orb-difference averaging
across many events to refine an estimate. Neither the relocated-chart
technique nor the dial tools are implemented in this service yet.

**Timoshenko, I.** "Ректификация. Нет больше страха…" (Rectification. No
more fear...) plus an associated multi-lecture practical course
(VALIRAN astrological center, 2001) confirmed to be a duplicate/
elaboration of the same method under two different archive filenames. —
A four-rule bidirectional aspect requirement: for an event, the DIRECTED
ruler of the relevant house must send at least one aspect to a natal
element of that house; the DIRECTED cusp must likewise send one; the
NATAL ruler must receive at least one aspect from a directed element; the
NATAL cusp must likewise receive one - all four simultaneously, not just
"an aspect exists somewhere". Extended point list (Lilith, lunar apogee,
Part of Fortune, Cross of Destiny, Vertex, a "Point of Life" progressing
1 sign per 7 years - a different rate than Aizin's version of the same
name - and event-specific significators such as Vesta for marriage/
family/property). A precise interval-intersection algorithm for
same-day rectification (natal inter-planetary angular distances mod 30
degrees, matched against the "event arc", intersected across ~10 points)
claiming typical precision of 10-30 seconds. Also describes rectifying
WITHOUT any dated event at all, for a very small (~1 hour) starting
window, using the statistically near-universal eventual-marriage
assumption. Not yet implemented in this service.

**Shatskaya, Valentina.** *Методы ректификации гороскопа: уточнение
времени рождения* (Methods of chart rectification: refining the birth
time). Zodiac publishing, Tomsk, 1993. — Profective-MC calculation
combined with sidereal-time/MC-longitude formulas, worked through by hand
(not computer-dependent). Includes a real client case where the
predicted birth time (16:45) was later independently confirmed by the
client's mother to the minute. Also includes a speculative rectification
of Seraphim of Sarov's nativity from several of his religious-life dates.

**Levin, M.B.** Lecture transcript, "Ректификация" (Rectification;
Rector of the Academy of Astrology, who endorsed Aizin's work above). —
Live worked example using transiting slow planets (Neptune, Pluto,
Uranus, Saturn, Mars) crossing hypothesized angles across several dated
events (marriages, baptism, operation, illness), cross-checked against
physical appearance (a Jupiter-square-Ascendant native's Jupiterian
build). Notes the "planetary hour" method (Chaldean order; hour ruler =
Ascendant ruler) as a weak auxiliary indicator. States the heuristic that
a parent's Sun or Moon position often falls on a child's ASC, DSC, or MC.
Explicitly distrusts psychics and pendulums for birth-time determination.

**Zhuravleva, Irina.** "Ректификация по дате первого брака…! или ?"
(Rectification by the date of the first marriage - or not?). — Traces
the historical provenance of the profective-MC marriage rule: Alfred
Witte (founder of the Hamburg School) discovered it while searching for
the hypothetical body "Cupido" (comparing many charts with known marriage
dates to find where a "missing" significator planet would have to sit);
the technique was carried into Russian/Soviet astrology via S. Vronsky,
formalized in practice by his student Avgusta Semenko (rarely credited by
name), and later popularized by S. Shestopalov. Surveys classical
marriage significators across earlier authorities: Ptolemy (Tetrabiblos
IV.5 - Venus/Mars mutual reception or aspect between the two charts),
Ibn Ezra (*Book of Judgments of the Stars*), Mashallah (Sun=husband
significator in a woman's chart, Moon=wife in a man's), Al-Kindi (Arabic
Parts/Lots of marriage/husband/wife), and William Lilly (*Christian
Astrology*, horary rules for "will X marry?"). Documents **D. Kutalev's**
general Arabic Parts formula, applicable to any house, not just
Fortune/marriage: cusp + ruler - significator (day birth), or
Ascendant + significator - ruler (night birth). Confirms explicitly that
the profective-MC rule is specific to Koch houses. Not yet implemented
as a general-purpose Arabic Parts calculator in this service.

## Consulted but not used

**Boguzky.** "Гермес Трисмегист" (Hermes Trismegistus). — Turned out to
be a history-of-religion/Hermeticism/gnosticism text (translations of
scholarly material on Thoth/Hermes, alchemy, and gnostic cosmology), not
a technical rectification method. "Trutina Hermetis" appears there only
as mythological/philosophical context, not as the astrological technique.
Not relevant to this project.

**Daragan, K.** "Ректификационный анализ гороскопа А.Р.Чикатило"
(Rectification analysis of A.R. Chikatilo's chart). — A real worked
case study, but relies extensively on sidereal-zodiac fixed-star
interpretation per Pavel Globa's framework ("Wheel of Zoroaster",
Globa's ephemerides and fixed-star meanings) - excluded per this
project's explicit direction to skip Globa-derived material. One
generically useful, non-Globa-specific technique was extracted anyway:
narrowing a birth-time window by intersecting the time ranges implied by
several qualitative house-placement constraints (e.g. "Lilith in the 8th
house", "Pluto in the 5th house") known independently of exact degrees.

**Timoshenko lecture course "Морфология" folder** (sign-by-sign
character/appearance descriptions bundled with the same course as
above). — Qualitative/physiognomic rectification material, not a
distinct quantitative technique; not surveyed in depth.
