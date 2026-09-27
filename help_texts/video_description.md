# Video-to-text description methodology

Not an astrology or rectification topic - a companion to `help("socionics")`
(and potentially useful anywhere else video material needs to become plain
text). This service's own MCP tools have no video/audio input capability at
all (Claude's vision is image-only - see the project's own chat history for
why), so getting anything useful out of a video means routing it through an
external video-capable model first (Gemini or similar) and feeding THAT
model's text output back in as ordinary material - the same way a book
excerpt or interview transcript would be supplied for typing work.

## What this prompt is for, and what it deliberately does NOT do

Purely descriptive/observational elicitation - speech, timing, appearance,
setting, tone, gesture - nothing more. It deliberately does NOT ask the
video-analysis model to identify socionics-relevant signals itself (e.g.
"flag moments that look like mirroring", "note which function this
suggests"). That interpretation is `help("socionics")`'s job, done once,
carefully, by whichever model does the actual typing - mixing in a second,
less rigorous interpretive pass from a different model at the description
stage would contaminate the raw material rather than just recording it.
Keep this step strictly factual.

## The prompt

Use this close to verbatim with a video-capable external model. Framed
honestly around its real purpose (feeding a downstream text-only analysis
step) rather than a fabricated reason - see the project's own chat history
for why an earlier draft framed around a false disability claim was
rejected: the manipulation itself was the problem, independent of whether
it would have worked.

```
Мне нужно исчерпывающее, максимально подробное текстовое описание этого
видео — оно послужит единственным источником информации о видео для
другой системы анализа текста, у которой нет доступа ни к изображению,
ни к звуку. Поэтому ничего из происходящего в видео не должно остаться
неописанным — если ты этого не опишешь, эта информация будет для
дальнейшего анализа безвозвратно потеряна.

Сделай расшифровку в виде ОДНОГО markdown-блока, со следующей
обязательной структурой:

1. Текст речи с таймкодами. Каждая реплика — с отметкой времени начала
   ([MM:SS], или [ЧЧ:ММ:СС] для видео длиннее часа) и явным указанием,
   кто говорит (имя, если оно известно или называется в видео; иначе —
   последовательное условное обозначение вроде "Ведущий" / "Собеседник 1",
   одно и то же для одного и того же человека на всём протяжении видео,
   а не только в первый раз).

2. Визуальные пояснения — в угловых скобках <...>, по ходу расшифровки,
   в момент появления или изменения:
   - внешность и одежда каждого человека в кадре (максимально подробно:
     цвет и стиль одежды, причёска, характерные детали облика);
   - расположение людей в кадре (кто где сидит/стоит, относительно друг
     друга и относительно камеры);
   - мимика и эмоциональные проявления — отслеживай по ходу всего
     разговора, а не только в начале;
   - жесты и характерные движения;
   - смена планов камеры, если она есть.

3. Голосовые/звуковые характеристики — по ходу расшифровки:
   - интонации, изменения тона, темп речи, паузы;
   - смех, вздохи и другие невербальные звуки;
   - наложения реплик/перебивания, если несколько человек говорят
     одновременно.

4. Обстановка и окружение:
   - помещение/локация в целом — в начале, и повторно, если меняется по
     ходу видео;
   - значимые детали интерьера или фона.

Требования:
- Ничего не суммаризируй и не сокращай — расшифровка должна покрывать
  ВСЮ продолжительность видео, а не только "основные моменты".
- Не пропускай визуальные и звуковые детали, даже если они кажутся
  малозначительными — решать, что из этого важно, будет другая система,
  не ты.
- Если что-то не удаётся разобрать однозначно (неразборчивая речь,
  неясно, кто говорит, кадр не даёт понять деталь одежды и т.п.) — прямо
  отметь это как неопределённость в тексте, а не пропускай и не
  додумывай недостающее.
```

## Using the result

The output is plain material for `help("socionics")`'s procedure - supply
it as the analyzed content exactly like a transcript or autobiography
excerpt would be, including whatever per-request framing that document
calls for (who the target person is, any professional/domain context worth
flagging up front). Nothing about the description step above substitutes
for `help("socionics")`'s own confound-control and ambiguity-escalation
rules - if anything, a good description makes those rules easier to apply,
since gestures/tone/setting are now actually present in the material
instead of missing entirely.

## Open question, not yet resolved

The user's own sketch: an external service that calls Gemini (or similar)
with this prompt for a given video and returns the result over MCP -
not yet built, not yet designed in detail (how results get delivered,
whether as a new tool here or some other mechanism). Revisit this section
once that shape is actually decided, rather than speculating further here.
