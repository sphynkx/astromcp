# MediaWiki integration

Everything in this folder is **MediaWiki-side** - three independent Lua
modules plus one shell script, none of them part of the astromcp Python
service's own MCP/REST interface. Two of them (`Module_ParseType.lua`,
`Deathmon.lua`) don't call astromcp at all; only `Module_Astrodata.lua`
does. They're grouped here because they all live on the same wiki, not
because they share code or a deployment story.

    install/Mediawiki/
    ├── README.md              # this file
    ├── Module_Astrodata.lua   # calls astromcp's /astro REST endpoint - see main README's
    │                          # "Tools exposed" / "REST endpoint" sections for what it returns
    ├── Module_ParseType.lua   # socionics dichotomy categories from a 3-letter type code - pure Lua
    ├── Deathmon.lua           # Wikidata (P570) death-date monitoring - pure Lua + Extension:ExternalData
    └── purge_deathmon.sh      # cron script: forces a wiki-wide recheck via a bot-authenticated purge

---

## Module:Astrodata

A ready-to-use Lua module - consumes astromcp's `/astro` via the
[External Data](https://www.mediawiki.org/wiki/Extension:External_Data)
extension's `mw.ext.externalData.getExternalData` and `/astro/chart.svg`
as an external-image link, and generates the Russian-language category
tags described below. **This is the one file in the whole project kept
in Russian rather than English** - it's Lua for a Russian-language
wiki's editors to read and maintain directly, not Python for the
astromcp project's own contributors, so that project's usual
English-comments convention doesn't apply to it.

### LocalSettings.php requirements

External Data has no "named data source" indirection for Lua calls - the
URL is always given directly in code, so the only real configuration
needed is to allow-list wherever `BASE_URL` in the module actually
resolves to.

**As of this round, `BASE_URL` is `mw.site.server .. "/astro"` - the
wiki's own domain, not the astromcp backend's address directly.** This
depends on the wiki's own nginx reverse-proxying `/astro` straight
through to the astromcp backend, e.g.:

    location /astro {
        proxy_pass http://192.168.7.3:8765;
    }

(this block goes in the **wiki's** nginx config, not astromcp's own -
see the main `README.md`'s "Hosting / reverse proxy setup" section for
astromcp's own nginx config, which is a separate, unrelated reverse
proxy for astromcp's public domain). With this in place, `getExternalData`
calls made by the wiki's own PHP (External Data fetches happen
server-side, not in the visitor's browser) go out to the wiki's public
domain and come back in via this proxy block - so the allow-list entry
needs to match that domain, not the backend's internal address:

    $edgAllowExternalDataFrom = array( 'https://sociowiki.sphynkx.org.ua/' );

The previous round hardcoded the backend's internal IP directly
(`192.168.7.3:8765`), bypassing the wiki's own nginx entirely - this
was slightly more direct (one less proxy hop) but meant `BASE_URL`
had to be edited by hand for every wiki/environment this module gets
copied to, and the allow-list above had to reference the internal
address specifically, which reads confusingly next to a
publicly-facing wiki config. Deriving it from `mw.site.server` instead
removes that hardcoding - the module now works unmodified on a
staging copy of the wiki, a domain rename, etc. If the wiki server
can't resolve its own public domain back to something local (so this
round-trips out to the internet and back rather than staying
internal), reverting `BASE_URL` to a literal internal IP is a one-line
change back - see the comment directly above `BASE_URL` in the module.

For `p.wheel()` (the SVG chart), MediaWiki also needs permission to render
an `<img>` tag - its Sanitizer strips raw `<img>` from wikitext/module
output by default:

    $wgAllowImageTag = true;

This is a narrow, purpose-built flag (unlike `$wgRawHtml`, it permits only
the `<img>` tag, nothing else) and - importantly - side-steps a real
MediaWiki core limitation: the alternative approach (a bare, unbracketed
external-image URL, auto-embedded via `$wgAllowExternalImages`/
`$wgAllowExternalImagesFrom`) depends on MediaWiki's own
`EXT_IMAGE_REGEX` recognizing `.svg` as an image extension, which
historically it did **not** by default (only `gif|png|jpg|jpeg` - see
[phabricator T65806](https://phabricator.wikimedia.org/T65806); some
installs needed a core patch to add `svg`). Whether your specific version
has that fixed is not something to gamble on, so `p.wheel()` returns a
literal `<img src="...">` tag and relies on `$wgAllowImageTag` instead,
which has no such extension dependency.

(If `$wgAllowImageTag` isn't an option on your install for some reason,
the bare-URL external-image path is still worth trying as a fallback -
`$wgAllowExternalImages = false; $wgAllowExternalImagesFrom = array('https://sociowiki.sphynkx.org.ua/');`
plus a template call with **no** manual `[...]` brackets around the
`{{#invoke:...}}` - but test it, since the `.svg`-recognition caveat
above applies.)

### Installing the module

Create the wiki page `Модуль:Astrodata` and paste in the contents of
`Module_Astrodata.lua`.

### Calling it from a template

The module reads `date`/`time`/`lat`/`lon`/`city`/`country`/`houses`/
`name`/`place`/`photo`/`lots` from its own direct args and/or its parent
frame's args (so both `{{#invoke:Astrodata|planetslist|date=...}}` and a
template calling `{{#invoke:...}}` with already-named parameters work).
Missing `date`, or missing both coordinates and a city, makes every
function silently return `""` - no error text on the page, per the
original design brief - so a template can call all functions
unconditionally without an `{{#if:}}` guard.

    {{#invoke:Astrodata|planetslist
      |date={{{Дата рождения}}} |time={{{Время рождения}}}
      |lat={{{Широта рождения}}} |lon={{{Долгота рождения}}}
      |city={{{Город рождения}}} |country={{{Страна рождения}}}
    }}

    {{#invoke:Astrodata|aspectslist | ... same params ... }}

    {{#invoke:Astrodata|categories | ... same params ... }}

    {{#invoke:Astrodata|wheel | ... same params ...,
      optionally |name=... |place=... |photo={{{Изображение}}} }}

    {{#invoke:Astrodata|deathCategories|date={{{Дата смерти}}}}}

    {{#invoke:Astrodata|jonesFigure
      |date={{{Дата рождения}}} |time={{{Время рождения}}}
      |lat={{{Широта рождения}}} |lon={{{Долгота рождения}}}
      |city={{{Город рождения}}} |country={{{Страна рождения}}}
    }}

`city`/`country` are cleaned of `[[wikilink]]` markup internally, so
passing them straight from wikitext fields is fine. `lat`/`lon` must be
**decimal degrees with lat first, lon second** - a template that swaps
them (this has happened once already) will silently geocode the wrong
point whenever a page has explicit coordinates and no `city` fallback.

`planetslist`/`aspectslist` render each point/aspect with its Unicode
glyph rather than a spelled-out name - `planetslist` also shows an
essential-dignity letter (domicile/exaltation/detriment/fall - see
`PLANET_DIGNITY` in the module) between the glyph and the position, and
`aspectslist` bolds aspects tighter than 1 degree.

**Lots/Arabic Parts** (see the main `README.md`'s `/astro` section for
the server-side framework) show up in `planetslist`, `aspectslist`, and
`categories` automatically once the server returns a `json.lots` section
- the module's `LOT` table (parallel to `PLANET`) maps a registered
Lot's name to its display glyph/nominative/genitive, and `pointInfo()`
looks up either table so aspect rendering doesn't care whether a point
is a planet or a Lot. Only `part_of_fortune` is registered on the server
by default; pass `|lots=part_of_fortune,other_name` to request others
once they exist (see `engine/lots.py`). Adding a NEWLY-registered
server-side Lot to the module's own display (glyph, name) is a one-line
addition to the `LOT` table - the rest (table rows, aspect rows,
categories) picks it up automatically since it all iterates `LOT_IDS`/
`json.lots` generically rather than hardcoding `part_of_fortune`.

**Jones planetary-pattern figure** (see the main `README.md`'s
`Jones_figure` field docs) - `jonesFigure` translates the English slug
the server returns into a Russian category tag via `JONES_FIGURE_NAMES_RU`.
Three distinct "nothing to show" outcomes are handled differently on
purpose: no data at all (network/params) is silent `""`; a value that
starts with `"Error:"` (the classification itself failed server-side,
not the whole request) is also silent `""`, not shown as raw English
error text; an unrecognized-but-real value (the server added a new
figure this table doesn't know about yet) is shown **as-is in English**
rather than hidden, so a new figure's arrival is visible on the page
instead of silently disappearing.

`p.wheel()` names the downloadable file from the current page title
(`Натал_<Заголовок,_с_подчёркиваниями>.svg`) - MediaWiki's standard
"Фамилия, Имя Отчество" biography title convention maps onto this
directly, no extra template parameter needed. `photo` should be a
filename already uploaded to the wiki, without the leading `Файл:`/`File:`
(exactly what a `{{{Изображение}}}` template parameter typically holds) -
resolved via `Special:FilePath`, with `Unknown-person.png` as a fallback
if that specific file doesn't exist and isn't itself missing. It returns
a clickable image (wrapped in a link to the same SVG, so a reader can
open it full-size out of a cramped infobox) - call it bare, with **no**
manual `[...]` or `[[...]]` wrapping around the `{{#invoke:...}}`
(wrapping it produces broken nested-bracket wikitext, since the module's
own output already has its own bracket structure).

---

## Module:ParseType

Standalone - no calls to astromcp, no ExternalData source needed. One
function, `p.modal(frame)`: takes a 3-letter socionics type code (`ILE`,
`LSI`, etc.) and returns the concatenation of all four raw modality/
dichotomy categories (Логик/Этик, Сенсорик/Интуит, Экстратим/Интротим,
Рационал/Иррационал) - deliberately **without** any function-order/quadra
"coloring", just the four dichotomies.

### Installing

Create the wiki page `Модуль:ParseType` and paste in the contents of
`Module_ParseType.lua`.

### Calling it

    {{#invoke:ParseType|modal|tim={{{Социотип|}}} }}

The parameter is named `tim` (ТИМ - Тип Информационного Метаболизма,
the standard socionics term for what it holds). Input is validated
against the real 16 codes (case-insensitive, whitespace-trimmed) before
generating anything - an empty field or an unrecognized string returns
`""` silently, same convention as Module:Astrodata.

The eight membership lists inside the module were cross-checked by hand
against the letter-position rule (first two letters: `L`/`E` ->
Logic/Ethics, `S`/`I` -> Sensing/Intuition; third letter: `E`/`I` ->
Extra-/Introversion; first letter: `E` or `L` -> Rational, `I` or `S`
-> Irrational) for all 16 types before use - both approaches agree
exactly, no discrepancy found in any of the eight lists.

---

## Deathmon: Wikidata death-date (P570) monitoring

A small, self-contained pair of Lua functions (`Deathmon.lua`) plus one
cron script (`purge_deathmon.sh`) - together they answer "did someone
on my wiki die and I haven't updated their page yet?" without having to
manually check every person's Wikidata entry by hand.

### The two functions

**`p.checkDeath(frame)`** - manual/ad-hoc lookup. Called directly (no
template wrapper), either bare (uses the current page's own title) or
with an explicit name:

    {{#invoke:Deathmon|checkDeath}}
    {{#invoke:Deathmon|checkDeath|Дали, Сальвадор}}

Returns `Умер (Дата: YYYY-MM-DD)` or `Жив (или нет данных о смерти)` -
meant for checking one person at a time by hand, e.g. on a scratch page
while investigating, not for wiring into every biography page (see
`p.deathmon` below for that).

**`p.deathmon(frame)`** - the automated one, wired into the "Персона"
template's existing `{{{Дата смерти}}}` handling:

```
{{#if:{{{Дата смерти|}}}
|
............(existing markup for when the field IS filled)
|{{#invoke:Deathmon|deathmon}}
}}
```

Runs *only* when `Дата смерти` is empty (guaranteed by the `#if` itself;
the function re-checks this internally too, as cheap extra insurance -
harmless duplication, not a bug). When it's empty, it looks up the
*current page's own title* on Wikidata and checks **only whether P570
exists at all** - no date needed for this use, unlike `checkDeath`. If
P570 is set, it emits `[[Category:Недавно умершие]]` so these cases can
be found and the wiki's own `Дата смерти` field filled in by hand; if
P570 isn't set, or the page isn't found on Wikidata at all (e.g. the
wiki's title doesn't match Wikipedia's), it silently returns `""` -
both of those cases look identical to the JSONPath resolution (neither
resolves to anything), and both mean the same thing here: nothing to
report.

Note the two functions read their inputs from **different frames** on
purpose, not by accident: `checkDeath` is called directly (no wrapping
template), so its argument lives in `frame.args`; `deathmon` is called
from *inside* the "Персона" template's own `#if`, so `frame:getParent().args`
correctly reaches that template's own `Дата смерти` parameter. Mixing
these two up (using the wrong frame for either function) was, in fact,
the very first bug found in this module - see the numbered list further
below for the whole debugging history.

### Required `LocalSettings.php` source

```php
$wgExternalDataSources['wikidata_api'] = [
    'url' => 'https://www.wikidata.org/w/api.php?action=wbgetentities&sites=ruwiki&props=claims&format=json&titles=$title$',
    'format' => 'JSON with JSONpath',
    'params' => ['title'],
];
```

All three pieces matter - see the numbered bug list below for what
breaks if any one of them is missing.

### Why "someone died" doesn't just show up on its own

This is the part worth understanding **before** relying on this module,
not after. MediaWiki does not proactively rescan pages in the
background looking for external changes. What actually happens (per
[Manual:Job queue](https://www.mediawiki.org/wiki/Manual:Job_queue) and
[Manual:Parser cache](https://www.mediawiki.org/wiki/Manual:Parser_cache)):
category/link data for a page gets recomputed when (a) the page itself
is edited, (b) a template/module it transcludes is *edited* (not just
viewed - MediaWiki enqueues a `refreshLinks` job for every page
transcluding a template when that template's content changes), or (c)
the page's parser-cache entry naturally expires and someone happens to
view it again afterward.

None of these are triggered by Wikidata changing on its own - nothing
on the wiki itself changes when someone dies, so there's no edit event
for the job queue to react to. A biography page nobody happens to visit
could sit with a stale (or simply never-yet-computed) `Дата смерти`
almost indefinitely. Relying on organic traffic defeats the entire
purpose of a monitoring tool meant to catch things you don't already
know to look for.

**The fix: force a recheck of every page on a schedule, via the API's
`forcerecursivelinkupdate` purge parameter**, not by visiting every
person page individually:

    action=purge&forcerecursivelinkupdate=1&titles=Модуль:Deathmon

Per the [API:Purge](https://www.mediawiki.org/wiki/API:Purge) docs,
this parameter does "the same as `forcelinkupdate`, **and** update the
links tables for any page that uses this page as a template" - i.e.
purging `Модуль:Deathmon` *itself* this way cascades the recheck (and
therefore the fresh Wikidata fetch) to every page that calls it via
`#invoke`, without visiting any of them directly. This is a genuine,
officially-documented API parameter (distinct from a plain purge, which
only affects the purged page's own cache, and distinct from
`$wgWhitelistRead`, which only affects anonymous *read* access and has
nothing to do with triggering a recheck at all - read is not edit).

### Setting up a purge bot (Special:BotPasswords)

A closed/login-required wiki needs *some* authenticated identity for the
cron job to purge with. The clean, MediaWiki-native way is
`Special:BotPasswords` - a separate, revocable username+password pair
scoped to just the rights it needs, rather than the admin's own login.

**You do not need to check any permission checkbox at all** for
purge-only use. `purge` (along with `read` and `writeapi`) is part of
the `basic` grant, which MediaWiki marks as `hidden` in
`$wgGrantPermissionGroups` - meaning it's **automatically included with
every bot password**, not a togglable option in the grant list at all.
(This was confirmed against three independent live wikis'
`Special:ListGrants` pages, all consistently listing "Purge the cache
for a page (purge)" under "Basic rights (basic)".) If the bot-creation
form insists on at least one box being checked to let you save, tick
something harmless and unrelated to editing (e.g. "Просмотр вашего
списка наблюдения") purely to satisfy the form - it has no bearing on
whether purge actually works, since that comes from the always-present
`basic` grant regardless.

An IP-range restriction (e.g. `192.168.7.0/24`, matching the server the
cron job runs from) is a good, orthogonal extra layer of safety, fully
compatible with the above.

### The cron script: `purge_deathmon.sh`

```
15 3 * * * /var/www/wiki/purge_deathmon.sh
```

Logs in via the bot password and issues the purge, using a single
temporary cookie jar (created and cleaned up automatically - nothing to
manage by hand):

1. **Fetch a login token** (`action=query&meta=tokens&type=login`) -
   required by MediaWiki's anti-CSRF protection even for bot-password
   logins; there's no way to skip this step.
2. **Log in** (`action=login`) using that token, the same cookie jar.
3. **Purge**, authenticated, with `forcerecursivelinkupdate=1`.

Edit `WIKI_API`, `BOT_USER` (format: `ИмяБота@ИмяПароля`, exactly what
`Special:BotPasswords` displays when the bot is created), `BOT_PASS`,
and `TARGET_TITLE` at the top of the script before using it. Each step
checks for failure explicitly and exits with a clear message rather
than silently continuing with an empty token/session.

### Debugging history: five independent bugs, in the order they were found

Getting this module working end-to-end surfaced five separate bugs.
None of them were guessed at - all five were confirmed by directly
dumping the raw fetched data via `mw.ext.externalData.getExternalData()`
(bypassing the `#get_web_data`/`#external_value` string interface
entirely, which otherwise just shows a generic "variable not set" for
every one of them, making them look identical from the symptom alone).
Worth keeping this list for whoever touches this module next, since
none of these failure modes look like what they actually are just from
the visible error text:

1. **`frame:getParent().args` vs `frame.args`** - a direct `#invoke`
   (no wrapping template) has its arguments in `frame.args`, not
   `frame:getParent().args`, which reads a *wrapping template's* own
   parameters instead. Using the wrong one for `checkDeath` meant an
   explicitly-passed name was always silently ignored in favor of the
   current page's own title.
2. **`*` as a JSON wildcard needs JSONPath mode explicitly turned on**
   (`format => 'JSON with JSONpath'` on the source) - without it, `*`
   is read as a literal, nonexistent key name and the path never
   resolves, regardless of how the rest of the path is written.
3. **`{QUERY}`-style curly-brace placeholders are not real
   ExternalData syntax** - dynamic URL substitution uses
   `$paramname$` (dollar-sign-wrapped), explicitly declared via
   `'params' => [...]` on the source, with a matching parameter name
   passed to `#get_web_data` (here, `title=`). `{QUERY}` was silently
   sent to Wikidata as a literal string the entire time - confirmed by
   dumping the raw fetch and seeing Wikidata's response
   `{"entities":[{"missing":"","title":"{QUERY}"}]}`, i.e. it was
   asked for a page literally named "{QUERY}". This was the actual
   root cause behind every other symptom in the investigation up to
   this point - bugs 1, 2, and 4 were all independently real and
   needed fixing regardless, but none of them mattered until this one
   was found.
4. **Cyrillic/comma/space in the title need `mw.uri.encode()`** before
   being used as a URL parameter value - ExternalData doesn't encode
   substituted values itself. Easy to miss testing in a browser (which
   silently auto-encodes whatever's pasted into the address bar) -
   confirmed instead by running the exact same raw URL through plain
   `curl`, which refused it outright as malformed input.
5. **A missing P570 isn't a plain empty value** - the unresolved
   JSONPath makes `#external_value` return ExternalData's own "local
   variable not set" error text, a *non-empty* string. Checking only
   `rawTime ~= ""` (in `checkDeath`) treated that error text as a real
   date. Fixed by checking that the value actually starts with `+` or
   `-` (the era sign every real Wikidata time value has) before trying
   to parse it as one.

`p.deathmon`'s existence check (does P570 exist at all, no date needed)
sidesteps bug 5 entirely by design - it only ever compares the fetched
value against the literal string `"P570"` (echoed back by Wikidata's
own `mainsnak.property` field when the claim genuinely exists), so
there's no date-parsing step that could misinterpret an error string in
the first place.
