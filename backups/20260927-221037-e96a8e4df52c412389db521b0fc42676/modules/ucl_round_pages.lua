-- Native UCL knockout pages, verified in game on 2026-09-07.
-- ResultFinalTournament builds its page list from a competition-specific
-- list of round codes. UCL omitted 47 even when Round 47 already existed.
-- Route ONLY its family-id=2 branch through the existing five-code loop.
-- The loop still looks up UCL's own Round/MatchSlot/Event and skips absent
-- rounds. No fixtures, participants, save data or graphics are fabricated.
-- Removal: remove this module from sider.ini and restart the game.
local m = { version = "1.0.0-native-round47" }

local base = 0x140000000
local site = base + 0x00CAAEA0
local original = "\xe9\x02\x0f\x84\x6e\x03\x00\x00"
local patched  = "\xe9\x02\x0f\x84\x0f\x02\x00\x00"
local table4 = "\x2e\x00\x00\x00\x33\x00\x00\x00"
    .. "\x34\x00\x00\x00\x35\x00\x00\x00"
local table5 = "\x2e\x00\x00\x00\x2f\x00\x00\x00"
    .. "\x33\x00\x00\x00\x34\x00\x00\x00\x35\x00\x00\x00"

function m.init(ctx)
    if memory.read(base + 0x02724738, #table4) ~= table4
        or memory.read(base + 0x02724748, #table5) ~= table5 then
        log("[ucl_round_pages] BLOCKED: round-table signatures differ")
        return
    end
    local current = memory.read(site, #original)
    if current == patched then
        log("[ucl_round_pages] already installed " .. m.version)
        return
    end
    if current ~= original then
        log("[ucl_round_pages] BLOCKED: native UCL branch signature differs")
        return
    end
    -- m.init runs during Sider startup, before this menu is constructed.
    memory.write(site, patched)
    if memory.read(site, #patched) ~= patched then
        memory.write(site, original)
        log("[ucl_round_pages] BLOCKED: readback failed; rollback attempted")
        return
    end
    log("[ucl_round_pages] INSTALLED " .. m.version
        .. " UCL branch 0x140CAAEA2 -> 0x140CAB0B7; native codes 46,47,51,52,53")
end

return m
