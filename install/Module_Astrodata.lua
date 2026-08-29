-- Модуль:Astrodata
-- Обёртка над astromcp REST API (/astro, см. astromcp.sphynkx.org.ua) для
-- получения натальных данных рождения и генерации:
--   p.planetslist(frame)    - табличка планет + углов + Парсов, с
--                             эмодзи-символами и буквами достоинства
--                             (обитель/экзальтация/изгнание/падение)
--   p.aspectslist(frame)    - табличка аспектов (включая Парсы), точные
--                             аспекты жирным
--   p.categories(frame)     - категории по знакам/ретроградности/домам/
--                             аспектам/соединениям со звёздами/Парсам
--                             (рождение)
--   p.wheel(frame)          - SVG-колесо натальной карты (см. комментарий
--                             у самой функции)
--   p.deathCategories(frame) - категории по дате смерти (не требует
--                             обращения к сервису вообще)
--
-- НАСТРОЙКА АДРЕСА СЕРВИСА: у расширения ExternalData нет механизма
-- "именованных источников" для Lua-вызовов getExternalData - URL всегда
-- передаётся напрямую в коде/шаблоне.
--
-- BASE_URL берётся из mw.site.server, а не хардкодится - работает
-- автоматически на любом домене/протоколе, которым открыта сама вики
-- (staging-копия, смена домена и т.п. не требуют правки этого файла).
-- Это стало возможным благодаря обратному прокси в nginx самой вики,
-- который отдаёт /astro напрямую с бэкенда astromcp, так что для вики
-- (и для запросов getExternalData, выполняемых самим сервером MediaWiki,
-- а не браузером) это выглядит как обычный путь на собственном домене:
--   location /astro {
--       proxy_pass http://192.168.7.3:8765;
--   }
-- (добавляется в конфиг nginx вики - НЕ в конфиг самого astromcp).
--
-- Раньше здесь был захардкожен внутренний IP сервиса напрямую
-- (192.168.7.3:8765) в обход nginx вики - при таком варианте
-- getExternalData не проходит через собственный обратный прокси вики
-- лишний раз. Если это когда-то станет узким местом (сервер вики не
-- резолвит свой публичный домен во внутренний адрес, и трафик реально
-- уходит наружу и обратно) - можно откатиться к прямому IP, просто
-- заменив строку ниже обратно на литерал.
--
-- Из-за смены адреса не забудьте обновить и allowlist в
-- LocalSettings.php - теперь запросы идут на домен вики, а не на
-- внутренний IP сервиса:
--   $edgAllowExternalDataFrom = array( 'https://sociowiki.sphynkx.org.ua/' );
--
-- Для p.wheel() дополнительно нужно разрешить сам тег <img>:
--   $wgAllowImageTag = true;
-- Подробности - в README сервиса, раздел "Интеграция с MediaWiki".
local BASE_URL = mw.site.server .. "/astro"

local p = {}

-- ==================== Справочные таблицы ====================

local PLANET_IDS = {
	"sun", "moon", "mercury", "venus", "mars",
	"jupiter", "saturn", "uranus", "neptune", "pluto",
	"chiron", "mean_lilith",
}

-- именительный / родительный падеж / полная фраза ретроградности.
-- Род у планет в русском разный (Солнце - ср.р., Луна/Венера/Лилит - ж.р.,
-- остальные - м.р.), поэтому "Ретроградный/ая/ое ..." хранится уже готовой
-- фразой, а не собирается по правилу на лету.
local PLANET = {
	sun         = { nom = "Солнце",   gen = "Солнца",   retro = "Ретроградное Солнце",  glyph = "\226\152\137" },
	moon        = { nom = "Луна",     gen = "Луны",     retro = "Ретроградная Луна",    glyph = "\226\152\189" },
	mercury     = { nom = "Меркурий", gen = "Меркурия", retro = "Ретроградный Меркурий", glyph = "\226\152\191" },
	venus       = { nom = "Венера",   gen = "Венеры",   retro = "Ретроградная Венера",   glyph = "\226\153\128" },
	mars        = { nom = "Марс",     gen = "Марса",    retro = "Ретроградный Марс",     glyph = "\226\153\130" },
	jupiter     = { nom = "Юпитер",   gen = "Юпитера",  retro = "Ретроградный Юпитер",   glyph = "\226\153\131" },
	saturn      = { nom = "Сатурн",   gen = "Сатурна",  retro = "Ретроградный Сатурн",   glyph = "\226\153\132" },
	uranus      = { nom = "Уран",     gen = "Урана",    retro = "Ретроградный Уран",     glyph = "\226\153\133" },
	neptune     = { nom = "Нептун",   gen = "Нептуна",  retro = "Ретроградный Нептун",   glyph = "\226\153\134" },
	pluto       = { nom = "Плутон",   gen = "Плутона",  retro = "Ретроградный Плутон",   glyph = "\226\153\135" },
	chiron      = { nom = "Хирон",    gen = "Хирона",   retro = "Ретроградный Хирон",    glyph = "\226\154\183" },
	mean_lilith = { nom = "Лилит",    gen = "Лилит",    retro = "Ретроградная Лилит",    glyph = "\226\154\184" }, -- несклоняемое
}

-- Знаки зодиака как эмодзи-символы (с VS16 \239\184\143 после базового
-- символа - тот же приём, что в примере из ТЗ "♉️": делает символ цветным
-- эмодзи, а не текстовым глифом, там где шрифт/платформа это поддерживает).
local SIGN_GLYPH = {
	Ari = "\226\153\136\239\184\143", Tau = "\226\153\137\239\184\143",
	Gem = "\226\153\138\239\184\143", Can = "\226\153\139\239\184\143",
	Leo = "\226\153\140\239\184\143", Vir = "\226\153\141\239\184\143",
	Lib = "\226\153\142\239\184\143", Sco = "\226\153\143\239\184\143",
	Sag = "\226\153\144\239\184\143", Cap = "\226\153\145\239\184\143",
	Aqu = "\226\153\146\239\184\143", Pis = "\226\153\147\239\184\143",
}

-- Аспекты как юникод-символы, для p.aspectslist. Тот же набор градусов и
-- цветовой смысл (жёсткие/мягкие), что и в SVG-колесе (engine/svg_chart.py)
-- - держим оба места в согласии вручную, поскольку Lua и Python тут не
-- делят общий источник данных.
local ASPECT_GLYPH = {
	[0]   = "\226\152\140", [30]  = "\226\154\186", [45]  = "\226\136\160",
	[60]  = "\226\154\185", [90]  = "\226\150\161", [120] = "\226\150\179",
	[135] = "\226\167\131", [150] = "\226\154\187", [180] = "\226\152\141",
}

-- Порог точного аспекта (орбис в градусах) - точные показываем жирным,
-- как в SVG-колесе (EXACT_ORB_DEG там же).
local EXACT_ORB_DEG = 1.0

-- Достоинства планет (обитель/экзальтация/изгнание/падение) - таблица от
-- владельца проекта, современный популярный вариант, который по аналогии
-- расширяет классическую 7-планетную систему на Уран/Нептун/Плутон (не
-- строгая традиционная астрология). Только эти 10 планет - для Хирона и
-- Лилит достоинства не задавались.
local PLANET_DIGNITY = {
	sun     = { O = { "Leo" },        E = { "Ari" }, D = { "Aqu" },        F = { "Lib" } },
	moon    = { O = { "Can" },        E = { "Tau" }, D = { "Cap" },        F = { "Sco" } },
	mercury = { O = { "Gem", "Vir" }, E = { "Vir" }, D = { "Sag", "Pis" }, F = { "Pis" } },
	venus   = { O = { "Tau", "Lib" }, E = { "Pis" }, D = { "Sco", "Ari" }, F = { "Vir" } },
	mars    = { O = { "Ari", "Sco" }, E = { "Cap" }, D = { "Lib", "Tau" }, F = { "Can" } },
	jupiter = { O = { "Sag", "Pis" }, E = { "Can" }, D = { "Gem", "Vir" }, F = { "Cap" } },
	saturn  = { O = { "Cap", "Aqu" }, E = { "Lib" }, D = { "Can", "Leo" }, F = { "Ari" } },
	uranus  = { O = { "Aqu", "Cap" }, E = { "Sco" }, D = { "Leo", "Can" }, F = { "Tau" } },
	neptune = { O = { "Pis", "Sag" }, E = { "Aqu" }, D = { "Vir", "Gem" }, F = { "Leo" } },
	pluto   = { O = { "Sco", "Ari" }, E = { "Leo" }, D = { "Tau", "Lib" }, F = { "Aqu" } },
}
local DIGNITY_ORDER = { "O", "E", "D", "F" }

-- "<Планета> <SIGN_LOCATIVE[sign]>" -> "Солнце во Льве"
local SIGN_LOCATIVE = {
	Ari = "в Овне",      Tau = "в Тельце",    Gem = "в Близнецах",
	Can = "в Раке",      Leo = "во Льве",     Vir = "в Деве",
	Lib = "в Весах",     Sco = "в Скорпионе", Sag = "в Стрельце",
	Cap = "в Козероге",  Aqu = "в Водолее",   Pis = "в Рыбах",
}

local ORDINAL_TO_NUM = {
	First = 1, Second = 2, Third = 3, Fourth = 4, Fifth = 5, Sixth = 6,
	Seventh = 7, Eighth = 8, Ninth = 9, Tenth = 10, Eleventh = 11, Twelfth = 12,
}

-- Только те градусы аспектов, которые отдаёт сервис по умолчанию (major +
-- минорные). Если сервер настроен на другой набор - аспекты, которых нет
-- в этой таблице, просто не дадут категорию (безопасный fallback), не
-- ошибку.
local ASPECT_NAMES = {
	[0]   = "Соединение",
	[30]  = "Полусекстиль",
	[45]  = "Полуквадрат",
	[60]  = "Секстиль",
	[90]  = "Квадрат",
	[120] = "Тригон",
	[135] = "Полуторный квадрат",
	[150] = "Квинконс",
	[180] = "Оппозиция",
}

-- см. engine/fixed_stars.py:DEFAULT_STAR_LIST на стороне сервиса
local STAR_NAMES_RU = {
	Aldebaran  = "Альдебаран",
	Regulus    = "Регул",
	Antares    = "Антарес",
	Fomalhaut  = "Фомальгаут",
	Spica      = "Спика",
	Algol      = "Алголь",
	Sirius     = "Сириус",
	Vega       = "Вега",
	Pollux     = "Поллукс",
	Castor     = "Кастор",
	Betelgeuse = "Бетельгейзе",
	Rigel      = "Ригель",
}

local MONTH_GENITIVE = {
	"января", "февраля", "марта", "апреля", "мая", "июня",
	"июля", "августа", "сентября", "октября", "ноября", "декабря",
}

-- Углы: ключ JSON -> подпись в табличке -> подпись в категориях.
-- Специально НЕ унифицирую стиль между ASC/DSC и MC/IC - следую заданному
-- в ТЗ образцу буквально ("Асц в Козероге", "Dsc в Раке"); для MC/IC
-- примера категорий не было, оставил как в табличке (латиницей) - скажи,
-- если нужен другой вид ("Мц в Тельце" и т.п.).
local ANGLES = {
	{ key = "asc", table_label = "ASC", cat_label = "Асц" },
	{ key = "dsc", table_label = "DSC", cat_label = "Dsc" },
	{ key = "mc",  table_label = "MC",  cat_label = "MC" },
	{ key = "ic",  table_label = "IC",  cat_label = "IC" },
}

-- Парсы (Арабские точки) - см. engine/lots.py:LOT_REGISTRY на стороне
-- сервиса. Сервис отдаёт их в json.lots{имя: {abs_pos,sign,position,
-- house,speed, name_ru,gen_ru,abbr,glyph,description}} - позиционные
-- поля той же формы, что у планет, ПЛЮС уже готовые подписи для вывода.
-- Специально НЕТ своей локальной таблицы с именами/значками для Парсов
-- (в отличие от PLANET выше) - вся эта информация теперь приходит с
-- сервера вместе с данными, поэтому добавление нового зарегистрированного
-- там Парса не требует правки этого модуля вообще. По умолчанию сервис
-- отдаёт только "part_of_fortune" - если понадобятся другие, передайте
-- |lots=part_of_fortune,другое_имя в вызов (см. buildQuery).
--
-- glyph заполнен только у Парсов с широко известным символом (Фортуна -
-- ⊗); для большинства будущих Парсов сервер пришлёт glyph=nil и здесь
-- используется abbr (короткая текстовая аббревиатура) вместо него - см.
-- lotGlyph() ниже.
local function lotGlyph(lot)
	if lot.glyph and lot.glyph ~= "" then
		return lot.glyph
	end
	return lot.abbr or "?"
end

-- ==================== Вспомогательные функции ====================

-- [[Target]] или [[Target|Display]] -> Target (без разметки)
local function cleanWikiLink(s)
	if not s then return nil end
	s = mw.text.trim(s)
	s = s:gsub("^%[%[", ""):gsub("%]%]$", "")
	local target = s:match("^([^|]+)")
	return mw.text.trim(target or s)
end

local function isBlank(s)
	return s == nil or mw.text.trim(tostring(s)) == ""
end

-- json.lots - обычная Lua-таблица без гарантированного порядка обхода
-- (pairs()) - собираем и сортируем ключи по имени один раз, чтобы вывод
-- (planetslist/categories) был стабильным между вызовами, а не прыгал в
-- случайном порядке от запроса к запросу.
local function sortedLotIds(json)
	local ids = {}
	if json.lots then
		for id in pairs(json.lots) do
			table.insert(ids, id)
		end
		table.sort(ids)
	end
	return ids
end

-- Десятичный градус внутри знака (0-30) + 3-буквенный код знака из JSON
-- ("Sag" и т.п., как есть, без перевода - это техническая табличка)
-- -> "22Sag14"
local function formatDegree(position, signCode)
	position = tonumber(position)
	if not position then return "?" end
	local deg = math.floor(position)
	local min = math.floor((position - deg) * 60 + 0.5)
	if min == 60 then
		min = 0
		deg = deg + 1
	end
	return string.format("%d%s%02d", deg, signCode or "", min)
end

-- То же самое, но со знаком-эмодзи вместо 3-буквенного кода -> "11♉️22"
-- (пример из ТЗ) - используется в planetslist. Оставлена как есть для
-- мест, где нужна одна строка целиком.
local function formatDegreeEmoji(position, signCode)
	position = tonumber(position)
	if not position then return "?" end
	local deg = math.floor(position)
	local min = math.floor((position - deg) * 60 + 0.5)
	if min == 60 then
		min = 0
		deg = deg + 1
	end
	return string.format("%d%s%02d", deg, SIGN_GLYPH[signCode] or (signCode or ""), min)
end

-- Три отдельных куска (градус, знак-эмодзи, минуты) вместо одной строки -
-- для табличных ячеек с фиксированной шириной и выравниванием градуса по
-- правому краю (planetslist/aspectslist). Одна строка целиком всегда
-- выравнивается по левому краю ячейки, из-за чего однозначные градусы
-- визуально "гуляли" относительно двузначных.
local function formatDegreeEmojiParts(position, signCode)
	position = tonumber(position)
	if not position then return "?", "", "" end
	local deg = math.floor(position)
	local min = math.floor((position - deg) * 60 + 0.5)
	if min == 60 then
		min = 0
		deg = deg + 1
	end
	return tostring(deg), (SIGN_GLYPH[signCode] or (signCode or "")), string.format("%02d", min)
end

-- Буква достоинства планеты в знаке (О/Э/И/П) или "" если ни одно из
-- четырёх не подходит (в т.ч. для Хирона/Лилит, для которых достоинства
-- не заданы вовсе). Внутренние ключи таблицы PLANET_DIGNITY латинские
-- (O/E/D/F), а на экран выводим кириллические буквы через DIGNITY_DISPLAY.
local DIGNITY_DISPLAY = { O = "О", E = "Э", D = "И", F = "П" }
local function dignityLetter(planetId, signCode)
	local table_ = PLANET_DIGNITY[planetId]
	if not table_ then return "" end
	for _, letter in ipairs(DIGNITY_ORDER) do
		local signs = table_[letter]
		if signs then
			for _, s in ipairs(signs) do
				if s == signCode then
					return DIGNITY_DISPLAY[letter]
				end
			end
		end
	end
	return ""
end

-- "Fifth_House" -> 5
local function houseNumber(houseField)
	if not houseField then return nil end
	local ordinal = houseField:match("^(%a+)_House$")
	return ordinal and ORDINAL_TO_NUM[ordinal] or nil
end

-- НАСТРОЙКА ДЛЯ ФОТО: путь загрузок конкретно этой вики ($wgUploadPath +
-- имя каталога, у sociowiki это "images_sociowiki" - судя по реальному
-- рабочему URL .../images_sociowiki/7/7c/Koroleva_natasha.jpg). Поменяйте,
-- если у вас иначе.
local WIKI_UPLOAD_PATH = "/images_sociowiki"

-- Прямой путь к файлу по стандартной хеш-схеме MediaWiki ($wgHashedUpload
-- Directory, включена по умолчанию): подкаталоги - первый hex-символ
-- md5(имя_файла_с_подчёркиваниями), затем первые два символа того же
-- хеша. Формула проверена вручную (md5sum в консоли) и совпала с реально
-- работающим URL - поэтому это ОСНОВНОЙ способ получить путь к файлу,
-- надёжнее, чем гадать метод File-объекта Scribunto (см. resolveFileUrl
-- ниже, где это используется как первый вариант, а File-объект и
-- Special:FilePath - как запасные).
local function computeHashedFileUrl(filename)
	if isBlank(filename) then return nil end
	local underscored = filename:gsub(" ", "_")
	local ok, hash = pcall(mw.hash.hashValue, "md5", underscored)
	if not ok or not hash or #hash < 2 then
		return nil
	end
	local h1 = hash:sub(1, 1)
	local h2 = hash:sub(1, 2)
	return mw.site.server .. WIKI_UPLOAD_PATH .. "/" .. h1 .. "/" .. h2 .. "/" .. mw.uri.encode(underscored)
end

-- Абсолютный URL загруженного в вики файла (без ведущего "Файл:") или nil,
-- если такого файла нет.
--
-- ВАЖНО: этот URL всё равно должен пройти через серверный fetch+base64
-- сервиса (см. photo_url в /astro/chart.svg и engine/photo_fetch.py) -
-- сам по себе прямой путь к файлу НЕ решает проблему показа фото внутри
-- встроенного через <img> SVG (это ограничение браузера на загрузку
-- SVG'ом любых внешних ресурсов, включая уже корректные прямые ссылки -
-- работает только data:URI). Здесь этот URL нужен ТОЛЬКО как исходная
-- ссылка, которую скачает сам astromcp.
--
-- Порядок попыток: 1) хешированный путь по стандартной схеме MediaWiki
-- (см. computeHashedFileUrl - детерминированно и уже сверено вручную);
-- 2) File-объект Scribunto (метод отличается между версиями, поэтому
-- через pcall); 3) Special:FilePath - редирект, но давно документирован.
local function resolveFileUrl(filename)
	if isBlank(filename) then return nil end
	local title = mw.title.new(filename, "File")
	if not title or not title.fileExists then
		return nil
	end

	local hashedUrl = computeHashedFileUrl(filename)
	if hashedUrl then
		return hashedUrl
	end

	local ok, url = pcall(function()
		if title.file then
			if type(title.file.getUrl) == "function" then
				return title.file:getUrl()
			end
			if title.file.canonicalUrl then
				return title.file.canonicalUrl
			end
		end
		return nil
	end)
	if ok and url and url ~= "" then
		return tostring(url)
	end

	return tostring(mw.uri.fullUrl("Special:FilePath/" .. filename))
end

-- ==================== Получение данных ====================

-- Собирает URL запроса из args. base по умолчанию - JSON-эндпоинт
-- (BASE_URL); p.wheel() передаёт BASE_URL .. "/chart.svg" вместо него,
-- чтобы не дублировать разбор одних и тех же параметров под SVG-версию.
-- Возвращает nil (без ошибки), если не хватает обязательных данных -
-- по ТЗ: молча ничего не генерируем, а не вываливаемся с ошибкой на
-- странице.
local function buildQuery(args, base)
	base = base or BASE_URL

	local date = args.date
	if isBlank(date) then
		return nil
	end

	local time = args.time
	if isBlank(time) then
		time = "12:00"
	end

	local lat = args.lat
	local lon = args.lon
	local city = cleanWikiLink(args.city)
	local country = cleanWikiLink(args.country)

	local hasCoords = not isBlank(lat) and not isBlank(lon)
	local hasCity = not isBlank(city)
	if not hasCoords and not hasCity then
		return nil
	end

	local houseSystem = args.houses
	if isBlank(houseSystem) then
		houseSystem = "P"
	end

	local parts = {
		"date=" .. mw.uri.encode(date),
		"time=" .. mw.uri.encode(time),
		"house_system=" .. mw.uri.encode(houseSystem),
	}
	if hasCoords then
		table.insert(parts, "lat=" .. mw.uri.encode(tostring(lat)))
		table.insert(parts, "lon=" .. mw.uri.encode(tostring(lon)))
	else
		table.insert(parts, "city=" .. mw.uri.encode(city))
		if not isBlank(country) then
			table.insert(parts, "country_code=" .. mw.uri.encode(country))
		end
	end
	-- |lots=part_of_fortune,другое_имя - какие зарегистрированные на
	-- сервисе Парсы считать (см. engine/lots.py:LOT_REGISTRY). Не задано -
	-- сервис сам подставит дефолт (сейчас это "part_of_fortune").
	if not isBlank(args.lots) then
		table.insert(parts, "lots=" .. mw.uri.encode(args.lots))
	end

	return base .. "?" .. table.concat(parts, "&")
end

-- Запрос через ExternalData -> распарсенный JSON (Lua-таблица) или nil.
-- Любая проблема (не хватает параметров, сеть, сервис вернул ошибку)
-- приводит к тихому nil - страница просто не получает табличку/категории,
-- без текста ошибки на видном месте сайта.
function p._getData(args)
	local url = buildQuery(args)
	if not url then
		return nil
	end

	local data, errors = mw.ext.externalData.getExternalData{
		url = url,
		format = "JSON",
		data = { json = "__json" },
	}

	if errors or not data or not data.json then
		return nil
	end

	return data.json
end

-- Берёт args из прямого вызова {{#invoke:Astrodata|chart|date=...}} и/или
-- из родительского фрейма - так шаблон, вызывающий модуль через
-- {{#invoke:...}}, может передавать {{{Дата рождения}}} и т.п. под именами,
-- которые уже нормализованы в самом шаблоне (date/time/lat/lon/city/
-- country/houses).
local function resolveArgs(frame)
	local args = {}
	local parent = frame:getParent()
	if parent then
		for k, v in pairs(parent.args) do
			args[k] = v
		end
	end
	for k, v in pairs(frame.args) do
		args[k] = v
	end
	return args
end

-- ==================== Публичные функции ====================

-- Табличка планет + углов с эмодзи-символами знаков, буквой достоинства
-- надстрочно у значка планеты и ретроградностью подстрочно у координаты
-- (сила планеты визуально сливалась со значком при обычном начертании -
-- над/подстрочный формат разводит их). Градус, знак и минуты - в трёх
-- отдельных ячейках фиксированной ширины (градус по правому краю), иначе
-- однозначные градусы "гуляют" относительно двузначных в одной ячейке.
-- Только <table>...</table> - обёртку (коллапсируемый div и т.п.) делает
-- вызывающий шаблон. Возвращает "" без данных - без ошибки.
function p.planetslist(frame)
	local args = resolveArgs(frame)
	local json = p._getData(args)
	if not json or not json.planets or not json.houses then
		return ""
	end

	local rows = {}

	local function positionRow(labelCell, position, signCode, retrograde)
		local deg, glyph, min = formatDegreeEmojiParts(position, signCode)
		local minCell = min
		if retrograde then
			minCell = minCell .. "<sub><b>R</b></sub>"
		end
		return '<tr><td style="width:2.5em;">' .. labelCell .. ':</td>' ..
			'<td style="width:2em;text-align:right;">' .. deg .. '</td>' ..
			'<td style="width:1.5em;">' .. glyph .. '</td>' ..
			'<td style="width:3em;">' .. minCell .. '</td></tr>'
	end

	for _, id in ipairs(PLANET_IDS) do
		local pl = json.planets[id]
		local info = PLANET[id]
		if pl and info then
			local dignitySup = ""
			local dignity = dignityLetter(id, pl.sign)
			if dignity ~= "" then
				dignitySup = "<sup><b>" .. dignity .. "</b></sup>"
			end
			table.insert(rows, positionRow(info.glyph .. dignitySup, pl.position, pl.sign, pl.retrograde))
		end
	end

	for _, angle in ipairs(ANGLES) do
		local h = json.houses[angle.key]
		if h then
			table.insert(rows, positionRow(angle.table_label, h.position, h.sign, false))
		end
	end

	if json.lots then
		for _, id in ipairs(sortedLotIds(json)) do
			local lot = json.lots[id]
			if lot then
				local isRetro = lot.speed ~= nil and lot.speed < 0
				table.insert(rows, positionRow(lotGlyph(lot), lot.position, lot.sign, isRetro))
			end
		end
	end

	if #rows == 0 then
		return ""
	end

	return '<table style="table-layout:fixed;">\n' .. table.concat(rows, "\n") .. "\n</table>"
end

-- Табличка аспектов, тем же принципом что planetslist, но по аспектам:
-- значок первой планеты, значок аспекта, значок второй планеты, орбис,
-- и отметка схождения/расхождения (">•<" - аспект усиливается / сходится,
-- "<•>" - ослабевает / расходится). Точные аспекты (орбис меньше
-- EXACT_ORB_DEG) выделены жирным. Возвращает "" без данных - без ошибки.
local CONVERGENCE_MARK = {
	applying   = ">\226\128\162<",  -- ">•<"
	separating = "<\226\128\162>",  -- "<•>"
}

-- Общий поиск по имени точки среди планет (таблица PLANET) и
-- зарегистрированных Парсов (json.lots, приходит с сервера целиком -
-- никакой локальной таблицы под Парсы больше нет). Обе ветки возвращают
-- одну и ту же форму {nom, gen, glyph}, так что дальше по коду неважно,
-- откуда взялась точка.
local function pointInfo(id, json)
	local planet = PLANET[id]
	if planet then
		return planet
	end
	local lot = json and json.lots and json.lots[id]
	if lot then
		return { nom = lot.name_ru or id, gen = lot.gen_ru or lot.name_ru or id, glyph = lotGlyph(lot) }
	end
	return nil
end

function p.aspectslist(frame)
	local args = resolveArgs(frame)
	local json = p._getData(args)
	if not json or not json.aspects then
		return ""
	end

	local rows = {}
	for _, asp in ipairs(json.aspects) do
		local a, b = pointInfo(asp.point_a, json), pointInfo(asp.point_b, json)
		local aspGlyph = ASPECT_GLYPH[asp.aspect_deg]
		if a and b and aspGlyph then
			local orb = tonumber(asp.exact_orb) or 0
			local mark = CONVERGENCE_MARK[asp.status] or ""
			local aspText = a.glyph .. " " .. aspGlyph .. " " .. b.glyph
			local orbText = string.format("%.1f", orb) .. "\194\176"
			if orb < EXACT_ORB_DEG then
				aspText = "<b>" .. aspText .. "</b>"
				orbText = "<b>" .. orbText .. "</b>"
			end
			table.insert(rows, '<tr><td style="width:5em;">' .. aspText .. '</td>' ..
				'<td style="width:3.5em;text-align:right;">' .. orbText .. '</td>' ..
				'<td style="width:2em;">' .. mark .. "</td></tr>")
		end
	end

	if #rows == 0 then
		return ""
	end

	return '<table style="table-layout:fixed;">\n' .. table.concat(rows, "\n") .. "\n</table>"
end

-- Категории: знак планеты, ретроградность, дом планеты, знак угловых
-- домов, знак и дом Парсов (см. json.lots), аспекты между классическими
-- точками + Парсами (10 планет + Хирон + Лилит + зарегистрированные
-- Парсы - без углов/куспидов, иначе категорий будет на порядок больше,
-- чем нужно - пока не реализованы аспекты к углам),
-- соединения неподвижных звёзд с планетами.
function p.categories(frame)
	local args = resolveArgs(frame)
	local json = p._getData(args)
	if not json or not json.planets then
		return ""
	end

	local cats = {}
	local function addCat(name)
		table.insert(cats, "[[Category:" .. name .. "]]")
	end

	for _, id in ipairs(PLANET_IDS) do
		local pl = json.planets[id]
		local info = PLANET[id]
		if pl and info then
			local loc = SIGN_LOCATIVE[pl.sign]
			if loc then
				addCat(info.nom .. " " .. loc)
			end
			if pl.retrograde then
				addCat(info.retro)
			end
			local hn = houseNumber(pl.house)
			if hn then
				addCat(info.nom .. " в " .. hn .. " доме")
			end
		end
	end

	if json.houses then
		for _, angle in ipairs(ANGLES) do
			local h = json.houses[angle.key]
			if h then
				local loc = SIGN_LOCATIVE[h.sign]
				if loc then
					addCat(angle.cat_label .. " " .. loc)
				end
			end
		end
	end

	if json.lots then
		for _, id in ipairs(sortedLotIds(json)) do
			local lot = json.lots[id]
			if lot then
				local nom = lot.name_ru or id
				local loc = SIGN_LOCATIVE[lot.sign]
				if loc then
					addCat(nom .. " " .. loc)
				end
				-- lot.house уже число (1-12) - в отличие от планет, парсам
				-- дом не проставляет Kerykeion, сервис считает его сам и
				-- отдаёт готовым числом, а не строкой "Fifth_House".
				if lot.house then
					addCat(nom .. " в " .. lot.house .. " доме")
				end
			end
		end
	end

	if json.aspects then
		for _, asp in ipairs(json.aspects) do
			local a, b = pointInfo(asp.point_a, json), pointInfo(asp.point_b, json)
			local aspName = ASPECT_NAMES[asp.aspect_deg]
			if a and b and aspName then
				addCat(aspName .. " " .. a.gen .. " и " .. b.gen)
			end
		end
	end

	if json.fixed_star_conjunctions then
		for _, conj in ipairs(json.fixed_star_conjunctions) do
			local starRu = STAR_NAMES_RU[conj.star]
			local planetInfo = PLANET[conj.point]
			if starRu and planetInfo then
				addCat("Звезда " .. starRu .. " в соединении с " .. planetInfo.gen)
			end
		end
	end

	return table.concat(cats, "\n")
end

-- SVG-колесо натальной карты (astromcp GET /astro/chart.svg).
--
-- Возвращает готовый <img>, обёрнутый в ссылку на сам SVG "как есть" -
-- клик по картинке открывает полноразмерный SVG отдельно (в маленьком
-- инфобоксе детали иначе не разглядеть). MediaWiki по умолчанию режет
-- <img> из вывода модуля (Sanitizer) - нужно явно разрешить это в
-- LocalSettings.php:
--   $wgAllowImageTag = true;
-- (это отдельный узкий флаг именно для тега <img>, не открывает
-- произвольный HTML как $wgRawHtml, и не зависит от того, распознаёт ли
-- конкретная версия MediaWiki .svg как "картиночное" расширение в своей
-- логике автоэмбеддинга голых URL - та логика у части версий вообще не
-- поддерживает svg, см. README сервиса, раздел "Интеграция с MediaWiki".)
--
-- Имя файла для "сохранить как" генерируется из заголовка страницы в виде
-- "Натал_<Заголовок с _ вместо пробелов>.svg" и передаётся серверу
-- параметром filename, который выставляет Content-Disposition - сам файл
-- при этом не сохраняется на сервере или в вики, это только подсказка
-- браузеру при ручном сохранении картинки.
--
-- args.name/args.place - необязательные подписи для заголовка карты
-- (имя персоны/место); если name не передан явно, используется заголовок
-- страницы. args.photo - имя файла из {{{Изображение}}} (без "Файл:"),
-- уже загруженного в вики; если не задан или не найден, пробуем
-- заглушку "Unknown-person.png" (если она тоже не загружена - просто не
-- рисуем фото на карте, без ошибки).
function p.wheel(frame)
	local args = resolveArgs(frame)
	local svgUrl = buildQuery(args, BASE_URL .. "/chart.svg")
	if not svgUrl then
		return ""
	end

	local pageTitle = mw.title.getCurrentTitle().text

	local personName = args.name
	if isBlank(personName) then
		personName = pageTitle
	end

	local extra = { "name=" .. mw.uri.encode(personName) }
	if not isBlank(args.place) then
		table.insert(extra, "place=" .. mw.uri.encode(args.place))
	end

	local photoUrl = resolveFileUrl(args.photo)
	if not photoUrl then
		photoUrl = resolveFileUrl("Unknown-person.png")
	end
	if photoUrl then
		table.insert(extra, "photo_url=" .. mw.uri.encode(photoUrl))
	end

	local filename = "Натал_" .. pageTitle:gsub(" ", "_") .. ".svg"
	table.insert(extra, "filename=" .. mw.uri.encode(filename))

	local fullUrl = svgUrl .. "&" .. table.concat(extra, "&")
	-- "&" внутри URL нужно экранировать под HTML-атрибут (src="...") -
	-- иначе он не строго валиден как HTML/XML, даже если браузеры обычно
	-- прощают это в src/href.
	local htmlSafeUrl = fullUrl:gsub("&", "&amp;")

	return '[' .. htmlSafeUrl .. ' ' .. '<img src="' .. htmlSafeUrl .. '" alt="Натальная карта: ' ..
		personName .. '" style="max-width:100%;">]'
end

-- Категории по дате смерти. Не требует обращения к сервису вообще -
-- args.date здесь это дата смерти (шаблон передаёт её из
-- {{{Дата смерти}}} под тем же именем "date", что и для рождения, вызывая
-- эту функцию отдельно от p.chart/p.categories).
function p.deathCategories(frame)
	local args = resolveArgs(frame)
	if isBlank(args.date) then
		return ""
	end

	local day, month, year = args.date:match("^(%d%d?)%.(%d%d?)%.(%d%d%d%d)$")
	if not day then
		return ""
	end
	day, month, year = tonumber(day), tonumber(month), tonumber(year)
	if not (month and month >= 1 and month <= 12) then
		return ""
	end

	local monthGen = MONTH_GENITIVE[month]
	local cats = {
		"[[Category:Умер в " .. year .. " г.]]",
		"[[Category:Умер в " .. monthGen .. "]]",
		"[[Category:Умер " .. day .. " " .. monthGen .. "]]",
	}
	return table.concat(cats, "\n")
end

return p
