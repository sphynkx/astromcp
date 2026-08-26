-- Модуль:Astrodata
-- Обёртка над astromcp REST API (/astro, см. astromcp.sphynkx.org.ua) для
-- получения натальных данных рождения и генерации:
--   p.chart(frame)          - табличка планет + углов (Asc/Dsc/MC/IC)
--   p.categories(frame)     - категории по знакам/ретроградности/домам/
--                             аспектам/соединениям со звёздами (рождение)
--   p.wheel(frame)          - SVG-колесо натальной карты (внешняя ссылка,
--                             см. комментарий у самой функции)
--   p.deathCategories(frame) - категории по дате смерти (не требует
--                             обращения к сервису вообще)
--
-- НАСТРОЙКА АДРЕСА СЕРВИСА: у расширения ExternalData нет механизма
-- "именованных источников" для Lua-вызовов getExternalData - URL всегда
-- передаётся напрямую в коде/шаблоне. Единственное, что реально нужно
-- прописать в конфиге - это разрешить сам домен/адрес в LocalSettings.php:
--   $edgAllowExternalDataFrom = array( 'http://192.168.7.3:8765/' );
-- Используем внутренний адрес сервиса, а не
-- публичный домен astromcp.sphynkx.org.ua - быстрее (без выхода наружу и
-- обратно) и не зависит от того, останется ли сервис открыт в интернет.
-- Но можно и публичный домен - просто меняем строку ниже.
--
-- Для p.wheel() дополнительно нужно разрешить сам SVG как внешнее
-- изображение:
--   $wgAllowExternalImages = false;
--   $wgAllowExternalImagesFrom = array( 'http://192.168.7.3:8765/' );
-- Подробности - в README сервиса, раздел "Интеграция с MediaWiki".
local BASE_URL = "http://192.168.7.3:8765/astro"

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
	sun         = { nom = "Солнце",   gen = "Солнца",   retro = "Ретроградное Солнце" },
	moon        = { nom = "Луна",     gen = "Луны",     retro = "Ретроградная Луна" },
	mercury     = { nom = "Меркурий", gen = "Меркурия", retro = "Ретроградный Меркурий" },
	venus       = { nom = "Венера",   gen = "Венеры",   retro = "Ретроградная Венера" },
	mars        = { nom = "Марс",     gen = "Марса",    retro = "Ретроградный Марс" },
	jupiter     = { nom = "Юпитер",   gen = "Юпитера",  retro = "Ретроградный Юпитер" },
	saturn      = { nom = "Сатурн",   gen = "Сатурна",  retro = "Ретроградный Сатурн" },
	uranus      = { nom = "Уран",     gen = "Урана",    retro = "Ретроградный Уран" },
	neptune     = { nom = "Нептун",   gen = "Нептуна",  retro = "Ретроградный Нептун" },
	pluto       = { nom = "Плутон",   gen = "Плутона",  retro = "Ретроградный Плутон" },
	chiron      = { nom = "Хирон",    gen = "Хирона",   retro = "Ретроградный Хирон" },
	mean_lilith = { nom = "Лилит",    gen = "Лилит",    retro = "Ретроградная Лилит" }, -- несклоняемое
}

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

-- "Fifth_House" -> 5
local function houseNumber(houseField)
	if not houseField then return nil end
	local ordinal = houseField:match("^(%a+)_House$")
	return ordinal and ORDINAL_TO_NUM[ordinal] or nil
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

-- Табличка планет + углов в формате "22Sag14". Только <table>...</table> -
-- обёртку (коллапсируемый div и т.п.) делает вызывающий шаблон.
-- Возвращает "" без данных - без ошибки.
function p.chart(frame)
	local args = resolveArgs(frame)
	local json = p._getData(args)
	if not json or not json.planets or not json.houses then
		return ""
	end

	local rows = {}

	for _, id in ipairs(PLANET_IDS) do
		local pl = json.planets[id]
		local info = PLANET[id]
		if pl and info then
			table.insert(rows, "<tr><td>" .. info.nom .. ":</td><td>" ..
				formatDegree(pl.position, pl.sign) .. "</td></tr>")
		end
	end

	for _, angle in ipairs(ANGLES) do
		local h = json.houses[angle.key]
		if h then
			table.insert(rows, "<tr><td>" .. angle.table_label .. ":</td><td>" ..
				formatDegree(h.position, h.sign) .. "</td></tr>")
		end
	end

	if #rows == 0 then
		return ""
	end

	return "<table>\n" .. table.concat(rows, "\n") .. "\n</table>"
end

-- Категории: знак планеты, ретроградность, дом планеты, знак угловых
-- домов, аспекты между классическими точками (10 планет + Хирон + Лилит -
-- без углов/куспидов, иначе категорий будет на порядок больше, чем нужно -
-- пока не реализованы аспекты к углам),
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

	if json.aspects then
		for _, asp in ipairs(json.aspects) do
			local a, b = PLANET[asp.point_a], PLANET[asp.point_b]
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
-- Возвращает вики-разметку внешней ссылки вида "[URL]" - MediaWiki сама
-- отрисовывает такую ссылку как <img>, если домен разрешён через
-- $wgAllowExternalImagesFrom в LocalSettings.php (см. README сервиса,
-- раздел "Интеграция с MediaWiki"). Санитайзер MediaWiki не пропускает
-- сырой <svg>-код в вывод модуля напрямую в вики-разметку - путь через
-- внешнее изображение единственный рабочий здесь без JS.
--
-- Имя файла для "сохранить как" генерируется из заголовка страницы в виде
-- "Натал_<Заголовок с _ вместо пробелов>.svg" и передаётся серверу
-- параметром filename, который выставляет Content-Disposition - сам файл
-- при этом не сохраняется на сервере или в вики, это только подсказка
-- браузеру при ручном сохранении картинки.
--
-- args.name/args.place - необязательные подписи для заголовка карты
-- (имя персоны/место); если name не передан явно, используется заголовок
-- страницы.
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

	local filename = "Натал_" .. pageTitle:gsub(" ", "_") .. ".svg"
	table.insert(extra, "filename=" .. mw.uri.encode(filename))

	return "[" .. svgUrl .. "&" .. table.concat(extra, "&") .. "]"
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
