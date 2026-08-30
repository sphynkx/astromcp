# Technique implementation checklist

Every technique named in BIBLIOGRAPHY.md, tracked here so nothing is
silently skipped again. Update this file whenever a technique's status
changes. "Implemented" means there is a working tool/function for it in
`engine/`, not just that it's mentioned in docs.

**Testing caveat:** this development sandbox has no `kerykeion`/Swiss
Ephemeris installed, so nothing here has been run against a real chart
before reaching the production server. What WAS verified in-sandbox: pure
Python logic with no kerykeion dependency (house-element/ruler selection,
Timoshenko's 4-condition boolean logic, Aizin's derived-house algebra,
the Arabic Parts day/night formula, and the ecliptic<->equatorial
conversion used by the zodiacal primary direction) - each against
constructed test cases or known reference points, not just syntax-checked.
What was NOT verified here: end-to-end behavior through kerykeion itself.
First real use of each new technique on the production server should be
treated as its first real test, not assumed correct because the sandbox
checks passed.

## Implemented (as of the previous session)

- [x] Transit (all sources)
- [x] Secondary progression (all sources)
- [x] Solar arc direction, Sun-based (classical "key of Ptolemy" approximation)
- [x] Symbolic direction, flat rate (`technique_symbolic_direction`) - covers
      classical 1deg/year AND Zaprjagaev/Shestopalov-school "perfection"
      (30deg/year) as the same mechanism at different rates
- [x] Solar return
- [x] Hellenistic annual/monthly profection (traditional rulers)
- [x] Trutine of Hermes, Kefer's 4-branch formulation + optional Jonas Rule
- [x] "Elements of house" (Shestopalov/Aizin) via `target_houses`
- [x] Grishchenyuk's "three movements" criterion (`rectif_movements_scan`)
- [x] Profective-MC-to-marriage-significator check (manual `rectif_technique`
      calls - not yet a dedicated one-call tool)

## Implemented this session

- [x] Direction of ALL house cusps (2,3,5,6,8,9,11,12), not just the 4 angles -
      `technique_solar_arc`, `technique_symbolic_direction`, and
      `technique_secondary_progression`'s `direct_progressed_angles` mode
      now all shift the full HOUSE_KEYS set, not just ANGLE_KEYS
- [x] Aizin's formal "houses from houses" derived-house algebra for relatives
      (`engine/relations.py` - `derive_relation_house`); verified by running
      8 worked examples through the actual code, not by hand-checking
- [x] General Arabic Parts/Lots calculator (D. Kutalev's day/night formula)
      (`engine/arabic_parts.py`); day/night Part of Fortune formula verified
      against hand-computed expected values
- [x] Timoshenko's 4-condition bidirectional aspect test (ruler+cusp each
      send AND receive) - `rectif_timoshenko_scan`; the boolean logic
      verified against two constructed pass/fail scenarios, not just
      syntax-checked
- [x] Zodiacal primary direction of the MC (Kefer's "zodiacal primary
      directions", Ptolemy's key, via right ascension) - MC/IC only;
      `technique_primary_direction_zodiacal`. The ecliptic<->equatorial
      conversion formulas were round-trip tested numerically at 10 points
      including the equinoxes/solstices (where RA=longitude exactly,
      giving an independent correctness check), not just algebra-checked.
      Full primary directions of other points (oblique ascension under
      the pole, semi-arc proportional to geographic latitude) remain NOT
      implemented - the docstring in engine/techniques.py explains why
      this is a deliberate scope limit, not an oversight
- [x] Relocated chart transits (B. Hammerslaf) - `technique_relocated_transit`

## Implemented this session (round 2)

- [x] Bonatti's method (`rectif_bonatti_scan`) - Sun-affliction-based angle
      check; logic verified against 3 constructed scenarios (unafflicted/
      midpoint case, afflicted/conjunction case, neither-holds case)
- [x] Degree clustering (`rectif_degree_clustering`) - Israitel's
      condensation method / Brady's graphic rectification, implemented as
      one shared tool since they're the same mechanism; fundamentally
      different paradigm from every other tool here (collects transiting
      slow-planet degrees across many events, finds recurrence peaks, does
      NOT scan candidate birth times). Reuses aspects.py's
      angular_separation rather than re-deriving wraparound math.
- [x] Progressive meridian method (Kefer sec.7) - confirmed to be
      mechanically identical to the existing secondary_progression
      technique applied to the MC (both rest on the same sidereal-time-
      drift principle); no new code needed, just this note

## Explicitly could NOT be implemented (source material insufficient)

- [ ] Glahn's harmony law - the extracted source text has a gap right at
      the operative instruction ("Определение меридиана: ... Если в
      полдень дня рождения большинство планет в положительных знаках,
      направляем Солнце к Луне...") - the actual mechanism of "pointing"
      one luminary at the other is not recoverable from what was
      extracted, and a second, independent source (traditional-astrology.ru)
      only repeats the same short summary ("one main axis passes between
      Sun and Moon") without the missing selection mechanism either.
      Implementing this would require guessing the missing mechanism,
      which is exactly the kind of invention this project avoids. Would
      need to consult Kefer's original text directly (a physical/scanned
      copy, not the OCR extraction used for this project) or another
      primary source not yet located.

## Implemented this session (round 3)

- [x] Herich's number (`rectif_herich_scan`) - formula recovered from a
      primary-source excerpt (misyats.wordpress.com, reproducing Paul von
      Gerich's 1929 article) after Kefer's own text turned out to have an
      OCR gap exactly where the formula belonged; cross-checked against
      astrokot.kiev.ua's independent glossary entry (same formula, same
      8-degree orb). Verified against Gerich's own worked numeric example
      (Kurt Eisner's chart: inputs MO/SO=302, SA/SO=321, MO/SA=211 ->
      this implementation gives b=261.25, matching the source's b=261 and
      an independently-computed Ascendant of 262 from a third source)

## Found but insufficiently sourced to implement - a genuinely new item

- [ ] Harmonic-360 angle/planet coincidence rule (astro-zeus.ru
      encyclopedia: Placidus houses -> pairs with Moon, Koch -> Mars,
      Regiomontanus -> Jupiter, topocentric -> Saturn; claims the
      Ascendant or MC coincides with that house-system-specific planet in
      the H360 harmonic chart). The harmonic-360 MATH itself is standard
      and unambiguous (harmonic position = (360 x longitude) mod 360),
      but no source found gives the comparison orb or confirms exactly
      which two H360 positions are compared - implementing without that
      would mean guessing the missing procedural detail, which this
      project avoids. Multiple search results all trace back to the same
      short encyclopedia glossary entry with no worked example; would
      need a fuller primary source (the encyclopedia's own detailed
      pages, not yet located, or the forum threads at astrozet.net which
      disallow automated fetching) before this can be implemented
      responsibly.

## Horary (implemented this session)

New tool `horary_chart` + `engine/horary.py`, following
`horar_wri_gl00-04.txt` (Masenkov's textbook, the primary structural
source) with Frawley's precise prohibition/frustration/refranation
definitions and Lavoie's "judge even non-radical charts" position - see
BIBLIOGRAPHY.md and help_texts/horary.md.

- [x] Radicality check (main: Asc in first/last 3 degrees; 5 secondary
      warning factors, accumulated not decisive individually)
- [x] Significators via the ten-planet sign-rulership system, incl. the
      two-ruler signs (Scorpio/Aquarius/Pisces: classical + modern
      co-ruler); angular-house cusp rule and majority-of-house-span rule
      for succedent/cadent houses (`house_ruler_by_majority`), including
      intercepted-sign handling - verified against gl03's own worked
      example (Venus as VIII-house ruler, Virgo intercepted and excluded)
- [x] Derived-house method for third-party questions (`derived_house`) -
      verified against both of gl03's own worked examples (brother's dog
      -> house VIII, cousin's dog -> house III)
- [x] Essential dignity (rulership/exaltation/detriment/fall, 7 classical
      planets; Uranus/Neptune/Pluto only as co-rulers of their one sign)
      + accidental dignity (angularity, combustion/under-the-beams,
      besieged/captive, Via Combusta with the Spica exception, aspects
      from luminaries/malefics) combined into a strong/weak/mixed
      classification with every contributing factor listed individually
- [x] Mutual reception (sign-based only - reception by exaltation/term/
      face is an explicitly-optional extension per the source, not
      implemented, see help_texts/horary.md section 3)
- [x] Void-of-course Moon (checked against the 9 real planets only, not
      Part of Fortune/Cross of Fate - see engine/horary.py's module
      docstring for why) + "last aspect before leaving sign"
- [x] Translation and collection of light (favorable aspects only, per
      the source's own aspect-type taxonomy)
- [x] Perfection-interruption: prohibition/frustration/refranation per
      Frawley's precise definitions - refranation specifically uses a
      real second ephemeris snapshot at the projected perfection time
      (not a linear speed guess, which can't distinguish "slowing down"
      from "about to station") to detect a genuine direction reversal
- [x] Part of Fortune + Cross of Fate (Asc+Mars-Saturn) via the existing
      Lots framework (`engine/lots.py`) - no new machinery needed
- [x] Full Yes/No verdict decision tree (help_texts/horary.md section 5)

**Testing caveat applies here too** (see the note at the top of this
file) - the pure-Python logic (derived-house arithmetic, essential
dignity, house-ruler-by-majority with interception, the verdict decision
tree) was verified against the source's own worked examples in-sandbox;
end-to-end behavior through kerykeion on the production server is this
tool's first real test.

## Documented but intentionally not implemented (with reason)

- [x] ~~Bonatti's method~~ - now implemented (`rectif_bonatti_scan`)- [ ] Progressive meridian method - confirmed redundant, see above; no
      separate tool needed
- [x] ~~Brady's graphic/histogram clustering method~~ - now implemented
      (`rectif_degree_clustering`)
- [x] ~~Israitel's "condensation method"~~ - same tool as Brady's above
- [ ] Hammerslaf's Uranian 45deg/90deg dial techniques - conceptually
      overlaps with `rectif_degree_clustering`; a dedicated dial-specific
      implementation (as opposed to the tabular histogram approach taken
      here) has not been attempted
- [x] ~~Llewellyn George's RA-based MC-direction method~~ - subsumed by
      `technique_primary_direction_zodiacal`
- [ ] Full (non-zodiacal) primary directions with oblique ascension - real
      spherical-trigonometry undertaking (each point needs its own
      pole-dependent semi-arc calculation), deferred until specifically
      needed
