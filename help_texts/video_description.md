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

## Getting Gemini's output into this service

`describe_videos_start(youtube_urls, prompt=None, model=..., combine=True)`
/ `describe_videos_result(job_id, video_index=None)` (app.py) - submit_job-
backed, same async pattern as `rectif_pipeline_start`, since a real call
(especially several videos combined) can run for minutes. `prompt` can be
omitted to use this file's own prompt above automatically
(`engine/gemini_client.default_prompt()` reads it straight from this
file's fenced block - so editing the prompt here is the only place it
ever needs to change).

**Multiple videos of the same person** (the common real case - a batch of
shorter videos across different settings/moods/times, for one composite
picture) go in one `youtube_urls` list. `combine=True` (default) sends
them all in a SINGLE Gemini request - the tool automatically appends an
instruction telling Gemini to keep each video in its own clearly
separated, explicitly numbered section rather than blending the material
together. This also matters for Gemini's own daily call-count quota, not
just convenience - fewer, larger requests spend that budget more slowly
than one request per video.

`combine=False` instead sends one request per video and keeps each
result separate (`describe_videos_result`'s `video_index` param reads one
at a time, without pulling a whole large batch into one response) - the
fallback if a large combined batch turns out to degrade in practice.
Whether it actually does is genuinely untested as of this writing: Gemini
supports multiple videos in one request in general, but nobody here has
yet pushed a few dozen long videos through combine=True and checked
whether quality holds up as well as it does on one video at a time. If
you notice degradation (sections getting thinner, videos blending despite
the instruction, anything that reads like it's running out of room) -
that's the signal to switch to combine=False for that batch, and worth a
`rectif_note_append` note either way once you have a real answer.

## Known SDK quirk, deliberately not worked around

Every direct `generate_content()` call prints an informational "automatic
function calling... not recommended, use Chat instead" notice. Harmless
here - nothing in this integration ever passes `tools=`, so there is
nothing for AFC to act on regardless of the notice, and `google-genai`'s
own issue tracker documents sharp edges from explicitly disabling AFC
(a second warning if `maximum_remote_calls` isn't also set; state that
bleeds across calls in mixed tool/no-tool sessions) for a integration
that was never going to use tools in the first place. Silence it locally
in your own environment if the console noise bothers you; not worth
carrying the complexity in the shared code for zero behavioral benefit.
