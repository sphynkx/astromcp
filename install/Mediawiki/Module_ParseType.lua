-- Module:ParseType
-- Generates modality/dichotomy categories (logic/ethics, sensing/intuition,
-- extraversion/introversion, rational/irrational) from a 3-letter socionics
-- type code (ILE, LSI, etc.) - deliberately WITHOUT any "coloring"
-- (function-order/quadra) information, just the four raw dichotomies.
--
-- Membership lists below (the simpler of two equivalent approaches - the
-- other being parsing letter positions directly) were cross-checked by
-- hand against the standard letter-position rule for all 16 types before
-- being used here:
--   - among the first two letters: L -> Logic, E -> Ethics
--   - among the first two letters: S -> Sensing, I -> Intuition
--   - third letter: E -> Extratim, I -> Introtim
--   - first letter: E or L -> Rational; I or S -> Irrational
-- Both derivations agree exactly for all 16 types - no discrepancy found.
--
-- Called directly (no parent-template indirection expected, per the
-- actual invocation in use):
--   {{#invoke:ParseType|modal|tim={{{Социотип|}}} }}

local p = {}

local LOGIC      = { ILE=true, LII=true, LSI=true, SLE=true, LIE=true, ILI=true, LSE=true, SLI=true }
local ETHIC      = { SEI=true, ESE=true, EIE=true, IEI=true, ESI=true, SEE=true, EII=true, IEE=true }
local SENSOR     = { SEI=true, ESE=true, LSI=true, SLE=true, ESI=true, SEE=true, LSE=true, SLI=true }
local INTUIT     = { ILE=true, LII=true, EIE=true, IEI=true, LIE=true, ILI=true, EII=true, IEE=true }
local EXTRATIM   = { ILE=true, ESE=true, EIE=true, SLE=true, LIE=true, SEE=true, LSE=true, IEE=true }
local INTROTIM   = { SEI=true, LII=true, LSI=true, IEI=true, ESI=true, ILI=true, EII=true, SLI=true }
local RATIONAL   = { LII=true, ESE=true, LSI=true, EIE=true, LIE=true, ESI=true, LSE=true, EII=true }
local IRRATIONAL = { ILE=true, SEI=true, SLE=true, IEI=true, SEE=true, ILI=true, SLI=true, IEE=true }

-- Order controls the order categories are emitted in - matches the
-- order the dichotomies were listed in the request.
local DICHOTOMIES = {
	{ set = LOGIC,      label = "Логик" },
	{ set = ETHIC,      label = "Этик" },
	{ set = SENSOR,     label = "Сенсорик" },
	{ set = INTUIT,     label = "Интуит" },
	{ set = EXTRATIM,   label = "Экстратим" },
	{ set = INTROTIM,   label = "Интротим" },
	{ set = RATIONAL,   label = "Рационал" },
	{ set = IRRATIONAL, label = "Иррационал" },
}

-- Every valid 3-letter code, for validating input before generating any
-- category at all - an unrecognized string (typo, empty, wrong case
-- after normalization, or just not a real sociotype) produces nothing
-- rather than a partial/guessed result. LOGIC and ETHIC alone already
-- cover all 16 codes exactly once each (first dichotomy is exhaustive
-- and mutually exclusive), so their union is the complete valid set -
-- no need for a sixteenth separate list.
local VALID_TYPES = {}
for code in pairs(LOGIC) do VALID_TYPES[code] = true end
for code in pairs(ETHIC) do VALID_TYPES[code] = true end

--[[
Returns the concatenation of all four modality categories for the given
socionics type code, or "" if the field was empty/missing or the value
isn't one of the 16 recognized codes (typo, wrong case after
normalization, stray whitespace that didn't resolve to a real code,
etc.) - silently, matching the existing Astrodata module's convention
of not showing raw error text on the page for a missing/bad field.
--]]
function p.modal(frame)
	local raw = frame.args["tim"]
	if raw == nil then
		return ""
	end

	local socType = mw.text.trim(raw):upper()
	if socType == "" or not VALID_TYPES[socType] then
		return ""
	end

	local cats = {}
	for _, d in ipairs(DICHOTOMIES) do
		if d.set[socType] then
			table.insert(cats, "[[Category:Модал: " .. d.label .. "]]")
		end
	end

	return table.concat(cats)
end

return p
