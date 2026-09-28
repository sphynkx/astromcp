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

Three tools (app.py), all backed by `engine/gemini_client.py`:
`describe_videos_start(youtube_urls, prompt=None, model=..., group_size=1,
probe=True, refresh=False)` -> `job_id`; `describe_videos_result(job_id,
unit_index=None, offset=0, limit=None)`; `describe_videos_budget()`.
`prompt` defaults to this file's fenced prompt above (read from the file at
run time, so editing it here is the only place it ever changes).

### One request per video, by default

Measured, not guessed: one 53-minute video came back as ~48 KB of text, so
roughly 1 KB per minute of video. Several long videos cannot share one
response, and Gemini's own docs cap a request at 10 videos and put a
1M-token context at about 3 hours of video in the default mode. So
`group_size=1` is the default; `group_size` 2..10 exists for short clips.
(The docs page states no output-length cap, so whether ten combined
descriptions would actually be cut off is inferred from the 1 KB/min figure,
not tested.) A grouped unit's text is one blob with "## Видео N" headers
Gemini was asked to add - it can't be split per video afterwards; if you
need per-video pieces, don't group.

### Reading a batch: index, then pages

`describe_videos_result` on a finished multi-video batch returns an index
first - per unit `{unit_index, youtube_urls, status, text_length | reason}`
- so you can see what exists and what didn't. A one-video batch skips it.
Then read a unit's full text by pages: pass `unit_index`, follow
`next_offset` until it is null. Pages are 100,000 characters by default
(max 150,000, at line breaks) because one MCP tool result can't carry a
multi-hour batch; nothing is summarized or dropped. Compression (zlib) is
used only for storage - a reader always gets plain text, and compressing
can't reduce what has to fit in a model's context.

Reading 15-20 hours of descriptions in one pass is not realistic even with
paging - it is around a megabyte. Work through them one video (or a few) at
a time, keep structured notes per function with timestamp anchors, then
synthesize from the notes; the full text stays available to re-read.

### Resumable, and it stops itself

Every finished unit is stored (30 days, `ASTROMCP_VIDEO_CACHE_TTL_DAYS`),
keyed by video ids + prompt. Re-submitting the same URLs returns finished
ones as `cached` without calling Gemini: that is how an interrupted or
quota-limited batch continues, and how you recover the index after the job
record itself expires (3 days). A different prompt is a different cache
entry; `refresh=True` forces regeneration.

A batch ends early instead of burning quota - anything not attempted is
reported `deferred`, re-submit later:
- **probe** (default on, only with 2+ videos left): one tiny real request
  first; if the model is refusing right now, no video is sent.
- **circuit breaker**: 3 consecutive units failing even after retries
  (`ASTROMCP_GEMINI_BREAKER_THRESHOLD`).
- **fatal errors** (401/403/404 - bad key, retired model): stop at once,
  every unit would fail identically.
- **daily quota** (a 429 that looks per-day - a text heuristic, Google
  doesn't expose which quota tripped): stop at once. Per-minute 429s are
  waited out (`retry in Ns` from the message when present).
- **local daily budget** (`describe_videos_budget`): 8 h of video per day
  (`ASTROMCP_GEMINI_DAILY_VIDEO_HOURS`; the free tier's documented YouTube
  cap) and an optional request cap. Video hours are an ESTIMATE from
  prompt-token usage (~100 tokens/second, the docs' default-mode figure).
  The day is the Pacific day (when Gemini's daily quotas reset); the video
  cap's own day boundary isn't documented, so that's an assumption.

Retries: 3 attempts per request, 30 s then 60 s (plus jitter). Every
attempt counts as one request in the local budget, because users report
that Gemini counts 503s against RPM/RPD (a community report, not
official documentation).

### Why there's no free "is Gemini busy?" check

No capacity/health endpoint turned up in the docs; the AI Studio status
page (linked from the docs) is a human-facing incident page, and I haven't
checked whether it's machine-readable or whether it reflects per-model
demand spikes. Metadata calls (`models.get`, `countTokens`) don't exercise
generation, so they can't tell you a 503 is coming. The only real test is a
generation request, which costs one request - hence one probe per batch
rather than one per video, and none for a single video (its real request is
its own probe).

### Things that are still unverified

- The whole path to Gemini from this service after the first successful
  test (55 KB, 53-min video, worked). The tests in `tests/` exercise
  everything around the two functions that call google-genai, against a
  fake, not the SDK itself.
- How the real SDK's exceptions look mid-stream; `_classify` is written
  against the shapes seen in real failures ("ServerError: 503 UNAVAILABLE",
  "ClientError: 404 NOT_FOUND").
- Whether a 503 also consumes token quota (only request quota is reported).
- Agentic video mode (Gemini's docs: up to 88% fewer tokens on long videos,
  newer models) - not used; static is the default. Worth a look if quota
  becomes the bottleneck.
- Google's 404 for `gemini-2.5-flash` recommends the Interactions API;
  `generate_content_stream` still works as of this writing. Migrate if it's
  deprecated.

## Known SDK quirk, deliberately not worked around

Every direct `generate_content()` call prints an informational "automatic
function calling... not recommended, use Chat instead" notice. Harmless
here - nothing in this integration passes `tools=`, so AFC has nothing to
act on, and `google-genai`'s issue tracker documents sharp edges from
explicitly disabling it (a second warning if `maximum_remote_calls` isn't
also set; state bleeding across calls in mixed tool/no-tool sessions) for an
integration that never used tools. Silence it in your own environment if
the noise bothers you.
