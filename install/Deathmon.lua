local p = {}

--[[
Checks whether a person has a death date (P570) recorded on Wikidata,
looked up via the wikidata_api ExternalData source (see LocalSettings.php)
by Russian Wikipedia sitelink title.

Called directly (no wrapping template in the examples this was written
for):
  {{#invoke:Deathmon|checkDeath}}                              (uses the current page's own title)
  {{#invoke:Deathmon|checkDeath|Дали, Сальвадор}}               (explicit name)

FIXED (two independent bugs):

1) The explicit name argument was never actually read. The original code
   used frame:getParent().args, which is for reading a WRAPPING
   TEMPLATE's own parameters from inside a module it calls - it has
   nothing to do with the args passed directly after the function name
   in a bare #invoke like the ones above. For a direct #invoke (no
   template in between), the passed argument lives in frame.args, not
   frame:getParent().args - the latter was always nil/empty here, so
   args[1] was always nil, and the code always fell through to
   mw.title.getCurrentTitle().text - i.e. the CURRENT PAGE'S OWN TITLE,
   silently ignoring whichever name was actually passed. This is why
   both example calls, sitting on the same monitoring page, produced
   the identical (wrong) result: both were actually querying Wikidata
   for the monitoring page's own title, not either person's name.
   Fixed by reading frame.args first (the direct-invoke case these
   calls actually use), falling back to frame:getParent().args only if
   that's ever nil (keeps this working if the module is later wrapped
   in a template that passes its own parameter through instead).

2) The JSON path ("entities.*.claims.P570.0.mainsnak.datavalue.value.time")
   used "*" as a wildcard for the (unpredictable) Wikidata Q-id key under
   "entities" - but ExternalData only understands "*" as a wildcard in
   its JSONPath mode, which needs to be turned on explicitly (either via
   `format = 'JSON with JSONpath'` on the data source, or `use jsonpath`
   on the #get_web_data call itself). With the source's format left as
   plain 'json', "*" was being read as a literal (nonexistent) key name,
   so the path never resolved - #external_value returned ExternalData's
   own "no such variable" error, rendered as a <span class="error">...
   </span> - and string.sub(rawTime, 2, 11) sliced "span class" out of
   THAT html, which is the exact text reported. This half of the fix
   requires updating $wgExternalDataSources['wikidata_api'] in
   LocalSettings.php to use format 'JSON with JSONpath' (see the comment
   above the data= line below) - nothing on the Lua side can work around
   a source that isn't in JSONPath mode.

3) The "{QUERY}" placeholder in the source URL was never actually a
   recognized ExternalData syntax at all. Per the extension's own
   configuration documentation, dynamic URL substitution uses
   $paramname$ (dollar-sign-wrapped), declared explicitly via
   'params' => [...] on the data source - "{QUERY}" (curly braces) is
   not a thing ExternalData understands, so it was being sent to
   Wikidata as a literal string the entire time. Confirmed directly by
   dumping the raw fetched data via mw.ext.externalData.getExternalData()
   (bypassing the #get_web_data/#external_value string interface
   entirely): Wikidata's response showed
   {"entities":[{"missing":"","site":"ruwiki","title":"{QUERY}"}]} -
   i.e. it was asked for a page literally named "{QUERY}", which of
   course doesn't exist ("missing":""). This was the actual root cause
   behind every earlier symptom in this investigation (the "variable
   not set" errors persisted through the JSONPath fix and the
   URL-encoding fix because neither of those mattered yet - the
   substitution parameter itself was never reaching the URL). Fixed by
   renaming the Lua-side parameter from query= to title= (matching
   $title$ in the URL and 'params' => ['title'] in LocalSettings.php -
   see the README/commit notes for the required LocalSettings.php
   change, which nothing on the Lua side can substitute for).
--]]
function p.checkDeath(frame)
    -- Сбрасываем временные переменные ExternalData от возможного
    -- предыдущего #invoke на этой же страничке (если на одной странице
    -- несколько вызовов checkDeath подряд, для разных людей) - без
    -- этого сброса второй и последующие вызовы иногда не получают
    -- собственных данных, используя пусто/чужое состояние с прошлого
    -- вызова. Дешёвая, безопасная защита, даже если в вашем конкретном
    -- случае это не было причиной проблемы.
    frame:callParserFunction('#clear_external_data', {''})

    -- 1. Определяем имя человека: из параметра прямого вызова (обычный
    -- случай для этого модуля), с запасным вариантом на случай обёртки
    -- шаблоном, и с последним запасным вариантом - имя текущей страницы.
    local args = frame.args
    if args[1] == nil and frame:getParent() then
        args = frame:getParent().args
    end
    local pageTitle = args[1] or mw.title.getCurrentTitle().text

    -- Очищаем имя от лишних пробелов
    pageTitle = mw.text.trim(pageTitle)

    -- 2. Вызываем ExternalData через парсерную функцию #get_web_data.
    -- Источник wikidata_api должен быть настроен в LocalSettings.php с
    -- format = 'JSON with JSONpath' и params = ['title'] - иначе ни "*"
    -- ниже не будет понят как wildcard, ни $title$ в URL не подставится
    -- (см. комментарий выше про то, почему было "{QUERY}" буквально).
    -- Путь начинается с "$." (корень JSONPath) и использует [0] для
    -- индекса массива вместо ".0" - это стандартный JSONPath-синтаксис.
    -- pageTitle кодируется через mw.uri.encode() ПЕРЕД подстановкой -
    -- ExternalData сам это не делает, а сырая кириллица с запятой и
    -- пробелом даёт невалидный URL (подтверждено напрямую через curl).
    frame:callParserFunction('#get_web_data', {
        'source=wikidata_api',
        'title=' .. mw.uri.encode(pageTitle),
        'data=death_time=$.entities.*.claims.P570[0].mainsnak.datavalue.value.time'
    })

    -- 3. Получаем извлеченное значение из ExternalData
    local rawTime = frame:callParserFunction('#external_value', 'death_time')

    -- 4. Анализируем результат
    -- ВАЖНО: для человека БЕЗ даты смерти (P570 отсутствует) JSONPath-
    -- путь не резолвится вообще, и #external_value возвращает НЕ пустую
    -- строку, а текст служебной ошибки ExternalData ("Ошибка: локальная
    -- переменная «death_time» не установлена.") - то есть непустую
    -- строку, которую старая проверка "rawTime ~= ''" ошибочно
    -- принимала за настоящее значение. Проверяем вместо этого, что
    -- rawTime действительно похож на значение времени Wikidata - оно
    -- всегда начинается с "+" или "-" (знак эры в их формате времени,
    -- например "+1989-01-23T00:00:00Z") - а не просто "не пусто".
    local looksLikeWikidataTime = rawTime and (rawTime:sub(1, 1) == "+" or rawTime:sub(1, 1) == "-")
    if looksLikeWikidataTime then
        -- rawTime вернет что-то вроде "+1968-03-27T00:00:00Z"
        -- Вырезаем чистую дату (ГГГГ-ММ-ДД), убирая первый плюс
        local cleanDate = string.sub(rawTime, 2, 11)
        return "Умер (Дата: " .. cleanDate .. ")"
    else
        -- Либо переменная действительно пустая (человек жив), либо
        -- путь не резолвился вовсе (P570 отсутствует) - оба случая
        -- означают одно и то же для наших целей.
        return "Жив (или нет данных о смерти)"
    end
end

return p
