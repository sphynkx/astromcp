# Socionics typing methodology (Model A)

Reworked from the user's own working prompt (25 years of practical
socionics experience, refined through real use with another model before
this project existed) into this service's `help_texts/` conventions. This
is a new methodology document, not yet battle-tested through many real
typing sessions the way `help("rectification")` has been - treat it as
binding procedure regardless, but expect it to grow real-incident
annotations over time the same way that document did (see "How this
document should evolve" at the end).

## How to use this document - read this section first, every time

**Binding operating procedure, not background reading to half-remember.**
Read it in full at the start of every typing task - including one that
continues a typing already in progress - and follow it as a literal
procedure, not a vibe. A prior session's habits are not a substitute for
actually re-reading this.

**What this document does NOT cover: who the person is, or what material
you're analyzing.** Those are supplied by the user in their own message
for each specific typing request (the person's identity, any useful
visual/vocal/contextual description, the material itself - a transcript,
an autobiography excerpt, an interview, correspondence, whatever's
available) - never invented, assumed, or carried over from a different
person's typing. This file is the fixed method applied to whatever
per-request material and framing the user provides. If the material is a
video this service has no way to watch directly, see
`help("video_description")` for how it gets turned into text first.

## Core principle: TIM is fixed, behavior is not

Socionics describes a person's information metabolism type (ТИМ) - a
congenital, structural property, not a mood, a role, or a personality
trait in the everyday sense. All 8 functions of Model A are fixed for
life; they don't change with the person's mood, their social role in the
moment, or the specific circumstances of whatever material is being
analyzed. A useful working image: TIM is the skeleton - a fixed number
of joints, each bending in a fixed direction, always. Temperament,
mannerisms, mood, the specifics of an individual personality - that's
the muscle and skin layered on top, genuinely variable, and NOT what
this methodology is trying to determine.

**Never fix on the first behavioral pattern noticed and work backward to
make the type fit it.** A conclusion is only valid once it rests on a
genuinely complete analysis of all 8 functions - not on whichever one or
two functions happened to produce the most vivid, easy-to-spot evidence
first.

## Mandatory procedure

1. **Study the entire source material first, in full, before concluding
   anything about any function.** Don't start drafting a verdict on
   function 1 while still partway through the material - a pattern that
   looks decisive early on is exactly the kind of premature anchor the
   rule above is against.

2. **Identify the actual target person before analyzing anything.**
   Confirm who you're typing versus anyone else present in the material
   (interviewers, co-hosts, other speakers, characters someone is
   describing) - a wrong-person mix-up invalidates everything downstream
   of it, so get this right before functions are even considered.

3. **Analyze via all 8 functions of Model A**, using the flow/position
   each one occupies rather than treating them as a flat checklist. A
   technical framing that maps cleanly onto this project's own domain,
   useful for keeping each function's actual ROLE straight (not a
   different theory, just a mnemonic - the socionics content is the
   classical Model A itself):

   - **1st (Базовая/Base) — `stdin`.** The primary scan of the world, the
     input channel the person leads with unreflectively.
   - **2nd (Творческая/Creative) — `stdout`.** The main tool for actively
     producing output and acting on the world.
   - **3rd (Ролевая/Role) — a `try/catch`-handled exception.** The social
     mask: adaptation via rigid, learned norms and templates - handled,
     but not natively fluent.
   - **4th (Болевая/Vulnerable) — an unhandled exception.** The point of
     least resistance, where the system genuinely crashes rather than
     gracefully degrading.
   - **5th (Суггестивная/Suggestive) — a passive log.** Uncritical
     reception; quiet, largely unfiltered intake from the environment,
     read for suggestion rather than judged.
   - **6th (Активационная/Mobilizing) — an external call / incoming
     webhook (sometimes a service reload).** Activation and
     self-evaluation, recharged by an outside impulse rather than
     self-generated.
   - **7th (Ограничительная/Restrictive) — `/dev/null`.** Filters and
     instantly discards excess or imposed activity along this axis.
   - **8th (Фоновая/Background) — a daemon process.** Silent background
     control, with no output to the visible console stream - present and
     load-bearing, but never the thing being narrated.

4. **Cross-check against the 4 base dichotomies** independently of the
   function-by-function read above, as a consistency check rather than
   the primary method: Этик-Логик (Ethical/Logical), Сенсорик-Интуит
   (Sensory/Intuitive), Экстратим-Интротим (Extratim/Introtim),
   Рационал-Иррационал (Rational/Irrational). A function-level read and a
   dichotomy-level read that disagree is itself a signal worth surfacing
   explicitly, not silently resolving in favor of whichever came first.

5. **Control for subject-matter confounds - generalized, not limited to
   the examples below.** Whatever specific domain the material happens to
   involve (professional/technical jargon the person is more or less
   forced to use, historical facts and processes they explain, any other
   specialized subject) creates surface features that can look like
   function evidence but aren't:
   - Domain-specific terminology forced by the subject matter is not
     evidence of any particular function - it's an unavoidable nuance of
     the topic, not a personal expressive choice.
   - Explaining historical facts or processes must NOT be auto-read as
     strong intuition (Ni/Ne) - explaining known facts and generating
     novel possibilities are different things that can look superficially
     similar in text.
   - This generalizes to any comparable domain-forced pattern the
     material happens to contain - the two examples above are
     illustrations of the failure mode, not the exhaustive list of it.
   The actual target: how the person builds their OWN formulations
   within and around the domain constraint - which personal values
   organize their speech, which verbs and adjectives they reach for by
   preference - not the domain content itself.

6. **Control for interlocutor mirroring/adaptation.** In any
   conversational material, a person can partially adapt to or mirror
   whoever they're talking to, temporarily surfacing traits that belong
   to the OTHER person's type rather than their own. Weight stable,
   persistent proportions across the whole material over isolated,
   localized moments - an isolated pocket of atypical expression is more
   likely induced than genuine. As a soft, non-decisive check: if the
   target person's apparent type and their interlocutor's apparent type
   come out the same, treat that as a reason for extra suspicion of
   mirroring interference, not as confirmation.

7. **On genuine ambiguity: stop and escalate - see the next section.**

## When to ask rather than guess - and why that's the correct move here, not a fallback

**If the analysis reaches a genuine ambiguity, stop, say so explicitly,
and ask the user for clarification or more material before concluding
anything for the function(s) in question.** Do not produce a forced,
falsely-confident verdict to avoid an extra round-trip. This is the
single most important procedural instruction in this document, stated
because a known failure mode of an unguided LLM on this exact task is
manufacturing a confident-sounding conclusion out of thin evidence rather
than admitting the material didn't settle the question.

This isn't a fallback for when the method fails - it's a designed part
of it, for two concrete reasons:

- **The user has 25 years of hands-on socionics practice and a
  genuinely trained eye for this specific task.** Their judgment on a
  contested read is not a rubber stamp to route around - it's the more
  reliable signal on exactly the calls this document can't fully
  reduce to explicit rules.
- **Some real typing judgments happen at an intuitive, gestalt level
  that doesn't cleanly decompose into the discrete textual evidence a
  language model reasons over.** A rule-based read from text alone can
  genuinely be insufficient for a specific call, through no failure of
  applying this document correctly - that's a real limitation of the
  method here, not a mistake to paper over with confidence.

Ask about a genuine fork in the analysis (which of two functions a
passage actually evidences, whether a moment reads as mirroring or as
genuine, whether the material even settles a specific dichotomy) - not
about routine steps this document already specifies. The point is
surfacing real analytical uncertainty, not offloading ordinary work back
onto the user one small question at a time.

## Output format

1. A complete breakdown across all 8 Model A functions, plus a separate,
   clearly marked final verdict.
2. Every claim tied to a specific piece of the material - a described
   passage/moment, or a short quote. Keep any quote itself short and
   sparing (a phrase, not a reproduced passage) - this project's usual
   copyright-quoting limits apply here the same as anywhere else, and a
   paraphrased description of what happened at a given point in the
   material is preferable to a quote in most cases anyway.
3. Simplified markdown.
4. Render each of the 8 aspects with this exact markup wherever one is
   named in running text (not just in the reference table below):

   | Aspect | Markup |
   |---|---|
   | ЧЛ (Деловая логика) | `<span title="P, ЧЛ" class="socio-font">P</span>` |
   | БЛ (Структурная логика) | `<span title="L, БЛ" class="socio-font">L</span>` |
   | ЧЭ (Этика эмоций) | `<span title="E, ЧЭ" class="socio-font">E</span>` |
   | БЭ (Этика отношений) | `<span title="R, БЭ" class="socio-font">R</span>` |
   | ЧС (Силовая сенсорика) | `<span title="F, ЧС" class="socio-font">F</span>` |
   | БС (Сенсорика ощущений) | `<span title="S, БС" class="socio-font">S</span>` |
   | ЧИ (Интуиция возможностей) | `<span title="I, ЧИ" class="socio-font">I</span>` |
   | БИ (Интуиция времени) | `<span title="T, БИ" class="socio-font">T</span>` |

## Reference: the 16 types across all 8 Model A functions

Columns: 1 base, 2 creative, 3 role, 4 vulnerable, 5 suggestive,
6 mobilizing, 7 restrictive, 8 background.

| Тип | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---|---|---|---|---|---|---|---|
| **ILE** (Дон Кихот) | ЧИ | БЛ | ЧС | БЭ | БС | ЧЭ | БИ | ЧЛ |
| **SEI** (Дюма) | БС | ЧЭ | БИ | ЧЛ | ЧИ | БЛ | ЧС | БЭ |
| **ESE** (Гюго) | ЧЭ | БС | ЧЛ | БИ | БЛ | ЧИ | БЭ | ЧС |
| **LII** (Робеспьер) | БЛ | ЧИ | БЭ | ЧС | ЧЭ | БС | ЧЛ | БИ |
| **EIE** (Гамлет) | ЧЭ | БИ | ЧЛ | БС | БЛ | ЧС | БЭ | ЧИ |
| **LSI** (Максим Горький) | БЛ | ЧС | БЭ | ЧИ | ЧЭ | БИ | ЧЛ | БС |
| **SLE** (Жуков) | ЧС | БЛ | ЧИ | БЭ | БИ | ЧЭ | БС | ЧЛ |
| **IEI** (Есенин) | БИ | ЧЭ | БС | ЧЛ | ЧС | БЛ | ЧИ | БЭ |
| **SEE** (Наполеон) | ЧС | БЭ | ЧИ | БЛ | БИ | ЧЛ | БС | ЧЭ |
| **ILI** (Бальзак) | БИ | ЧЛ | БС | ЧЭ | ЧС | БЭ | ЧИ | БЛ |
| **LIE** (Джек Лондон) | ЧЛ | БИ | ЧЭ | БС | БЭ | ЧС | БЛ | ЧИ |
| **ESI** (Драйзер) | БЭ | ЧС | БЛ | ЧИ | ЧЛ | БИ | ЧЭ | БС |
| **LSE** (Штирлиц) | ЧЛ | БС | ЧЭ | БИ | БЭ | ЧИ | БЛ | ЧС |
| **EII** (Достоевский) | БЭ | ЧИ | БЛ | ЧС | ЧЛ | БС | ЧЭ | БИ |
| **IEE** (Гексли) | ЧИ | БЭ | ЧС | БЛ | БС | ЧЛ | БИ | ЧЭ |
| **SLI** (Габен) | БС | ЧЛ | БИ | ЧЭ | ЧИ | БЭ | ЧС | БЛ |

## Aspect glossary

- **ЧИ** - Чёрная интуиция (интуиция возможностей)
- **БИ** - Белая интуиция (интуиция времени)
- **ЧЛ** - Чёрная логика (деловая логика)
- **БЛ** - Белая логика (структурная логика)
- **ЧС** - Чёрная сенсорика (силовая сенсорика)
- **БС** - Белая сенсорика (сенсорика ощущений)
- **ЧЭ** - Чёрная этика (этика эмоций)
- **БЭ** - Белая этика (этика отношений)

## How this document should evolve

Same convention as this project's other methodology files: a real
finding from an actual typing session (a confound this document didn't
anticipate, a case where the escalate-on-ambiguity rule should have
fired and didn't, a refinement the user and the model agreed on in
practice) gets promoted into this file as a deliberate, explicitly-
discussed edit - not folded in silently, and not left to accumulate only
in session-local memory where a future session can't benefit from it.
`rectif_note_append`/`help("session_notes")` is the right place to log
something mid-session for later review before it's ready to become a
standing rule here.
