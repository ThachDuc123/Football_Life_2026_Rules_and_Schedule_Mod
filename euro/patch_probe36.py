"""Patch modules/ucl_schedule_probe.lua for the 36-club UCL/UEL single table.

Applied once to the phase-1 file (original/ucl_schedule_probe.lua.phase1);
every replacement must match exactly once (or the stated count).
"""
from pathlib import Path

P = Path(r'D:\FL26\SiderAddons\modules\ucl_schedule_probe.lua')
s = P.read_text(encoding='utf-8')


def rep(a, b, count=1):
    global s
    assert s.count(a) == count, (s.count(a), a[:90])
    s = s.replace(a, b)


rep("""local league_records = {}
local window_start = 0""", """local league_records = {}
-- Clubs in the merged table: 32 (8 groups of 4) or 36 (UEFA 2024+ league
-- phase: the regulation in livecpk/UEFA36 makes 4 groups of 9). league_comp is
-- the competition whose results fill it: 3 = Champions League, 5 = Europa League.
local league_total = 32
local league_comp = 3
local max_league_pages = 36
local window_start = 0""")

rep('local league_title = "UEFA Champions League \\xe2\\x80\\x94 Fase Liga"\n',
    'local league_title = "UEFA Champions League \\xe2\\x80\\x94 Fase Liga"\n'
    'local league_titles = {\n'
    '    [3] = league_title,\n'
    '    [5] = "UEFA Europa League \\xe2\\x80\\x94 Fase Liga",\n'
    '}\n')

start = s.index('local function standings_from_results()')
end = s.index('local function pack_record_fields(fields, position)')
NEW_STANDINGS = r'''-- Every played league-phase match of the Champions League (comp 3) and the
-- Europa League (comp 5), straight from the native Event table: 96 matches in
-- the 32-club format, 144 in the 36-club one, in whatever order they sit.
-- Returns standings[comp][team] and extras[comp][team] (the Article 18.01
-- criteria the native record has no field for), plus played[comp].
local function league_phase_standings()
    local root_slot = 0x143705E10
    if not readable_span(root_slot, 8) then return nil end
    local root = read_u64(root_slot)
    if not root or root < 0x10000 or not readable_span(root + 0x48, 8) then return nil end
    local model = read_u64(root + 0x48)
    if not model or model < 0x10000 then return nil end
    local events = model + 0xE9FF08
    local size = 13000 * match_record_stride
    if not readable_span(events, size) then return nil end
    local data = memory.read(events, size)
    if not data or #data ~= size then return nil end

    local function u32_at(offset)
        local a, b, c, d = string.byte(data, offset + 1, offset + 4)
        return a + b * 0x100 + c * 0x10000 + d * 0x1000000
    end
    -- UEFA disciplinary points of one side: yellow 1, direct red 3, two
    -- yellows 3. Appearances are 16 bytes, home from +0x24 (17), away from
    -- +0x134 (18); the packed word at +12 holds the card bits.
    local function side_cards(base, first, slots)
        local total = 0
        for slot = 0, slots - 1 do
            local at = base + first + slot * 16
            if u32_at(at + 4) ~= 0 then
                local packed = u32_at(at + 12)
                if bit.band(packed, 0x40000) ~= 0 then
                    total = total + 3
                else
                    if bit.band(packed, 0x80000) ~= 0 then total = total + 1 end
                    if bit.band(packed, 0x100000) ~= 0 then total = total + 3 end
                end
            end
        end
        return total
    end

    local standings, played = { [3] = {}, [5] = {} }, { [3] = 0, [5] = 0 }
    local function entry(comp, team)
        local row = standings[comp][team]
        if not row then
            row = { pj = 0, pts = 0, g = 0, e = 0, p = 0, gf = 0, gc = 0,
                    away_gf = 0, away_w = 0, disc = 0, opponents = {} }
            standings[comp][team] = row
        end
        return row
    end
    for index = 0, 12999 do
        local base = index * match_record_stride
        local lo, hi = string.byte(data, base + 1, base + 2)
        if lo + hi * 256 == index then
            local tlo, thi = string.byte(data, base + 5, base + 6)
            local comp = (tlo + thi * 256) % 0x400
            if comp == 3 or comp == 5 then
                local home_team = decode_team(u32_at(base + 0x14))
                local away_team = decode_team(u32_at(base + 0x18))
                local home = entry(comp, home_team)
                local away = entry(comp, away_team)
                if bit.band(string.byte(data, base + 8), 0x40) ~= 0 then
                    played[comp] = played[comp] + 1
                    local home_goals = string.byte(data, base + 0x1C + 1)
                    local away_goals = string.byte(data, base + 0x1F + 1)
                    home.pj = home.pj + 1
                    away.pj = away.pj + 1
                    home.gf = home.gf + home_goals
                    home.gc = home.gc + away_goals
                    away.gf = away.gf + away_goals
                    away.gc = away.gc + home_goals
                    away.away_gf = away.away_gf + away_goals
                    home.disc = home.disc + side_cards(base, 0x24, 17)
                    away.disc = away.disc + side_cards(base, 0x134, 18)
                    home.opponents[#home.opponents + 1] = away_team
                    away.opponents[#away.opponents + 1] = home_team
                    if home_goals > away_goals then
                        home.g = home.g + 1
                        home.pts = home.pts + 3
                        away.p = away.p + 1
                    elseif away_goals > home_goals then
                        away.g = away.g + 1
                        away.away_w = away.away_w + 1
                        away.pts = away.pts + 3
                        home.p = home.p + 1
                    else
                        home.e = home.e + 1
                        away.e = away.e + 1
                        home.pts = home.pts + 1
                        away.pts = away.pts + 1
                    end
                end
            end
        end
    end
    local extras = { [3] = {}, [5] = {} }
    for comp, rows in pairs(standings) do
        for team, row in pairs(rows) do
            local extra = { away_gf = row.away_gf, away_w = row.away_w, disc = row.disc,
                            opp_pts = 0, opp_gd = 0, opp_gf = 0 }
            for _, opponent in ipairs(row.opponents) do
                local o = rows[opponent]
                extra.opp_pts = extra.opp_pts + o.pts
                extra.opp_gd = extra.opp_gd + o.gf - o.gc
                extra.opp_gf = extra.opp_gf + o.gf
            end
            extras[comp][team] = extra
        end
    end
    return standings, extras, played
end

'''
s = s[:start] + NEW_STANDINGS + s[end:]

rep("""    if ranking.declared ~= 8 or ranking.outer_count ~= 8 then
        ranking_log(string.format(
            "merge_skip|expected declared=8 outer=8, found declared=%d outer=%d",
            ranking.declared, ranking.outer_count
        ))
        return false
    end

    local records = {}
    for _, group in ipairs(ranking.groups) do
        if #group ~= 4 then
            ranking_log("merge_skip|expected four records in every group")
            return false
        end
        for _, record in ipairs(group) do
            records[#records + 1] = record
        end
    end
    if #records ~= 32 then
        ranking_log("merge_skip|expected exactly 32 records")
        return false
    end

    -- Replace the per-group stats with the ones the results actually produce.
    -- The team field is kept untouched; only played/points/W/D/L/GF/GA/GD are
    -- rewritten. If the match block cannot be found or validated we leave the
    -- native numbers alone, so a failure here degrades to the old behaviour
    -- instead of showing something invented.
    local standings, matches_played = standings_from_results()
    if standings then
        local covered = 0
        for _, record in ipairs(records) do
            local row = standings[decode_team(record.fields[1])]
            if row then
                covered = covered + 1
            else
                row = { pj = 0, pts = 0, g = 0, e = 0, p = 0, gf = 0, gc = 0 }
            end""",
    """    -- 8 groups of 4 (32-club format) or 4 groups of 9 (36-club format).
    local per_group = ranking.groups[1] and #ranking.groups[1] or 0
    if ranking.declared ~= ranking.outer_count
        or not ((ranking.outer_count == 8 and per_group == 4)
            or (ranking.outer_count == 4 and per_group == 9)) then
        ranking_log(string.format(
            "merge_skip|expected 8x4 or 4x9 groups, found declared=%d outer=%d first=%d",
            ranking.declared, ranking.outer_count, per_group
        ))
        return false
    end

    local records = {}
    for _, group in ipairs(ranking.groups) do
        if #group ~= per_group then
            ranking_log("merge_skip|groups of different sizes")
            return false
        end
        for _, record in ipairs(group) do
            records[#records + 1] = record
        end
    end
    local total = #records
    if total - ranking_group_layout_rows + 1 > max_league_pages then
        ranking_log("merge_skip|too many pages for the window buffer")
        return false
    end

    -- Whose league phase is this? Only a table whose clubs all play the UCL
    -- or the UEL league phase is merged (the Conference League, World Cup
    -- and other group stages keep their native tables).
    local standings, extras, matches_played = league_phase_standings()
    if not standings then
        ranking_log("merge_skip|Event table not readable")
        log("[ucl_probe] WARNING: match records not found; native group tables kept")
        return false
    end
    local comp
    for _, candidate in ipairs({ 3, 5 }) do
        local found = 0
        for _, record in ipairs(records) do
            if standings[candidate][decode_team(record.fields[1])] then found = found + 1 end
        end
        if found == total then comp = candidate end
    end
    if not comp then
        ranking_log("merge_skip|clubs are not a UCL/UEL league phase")
        return false
    end
    league_extra = extras[comp]

    -- Replace the per-group stats with the ones the results actually produce.
    -- The team field is kept untouched; only played/points/W/D/L/GF/GA/GD are
    -- rewritten.
    do
        local covered = 0
        for _, record in ipairs(records) do
            local row = standings[comp][decode_team(record.fields[1])]
            if row then
                covered = covered + 1
            else
                row = { pj = 0, pts = 0, g = 0, e = 0, p = 0, gf = 0, gc = 0 }
            end""")

rep("""        ranking_log(string.format(
            "global_standings|matches_played=%d|teams_with_results=%d/32",
            matches_played, covered
        ))
        log(string.format(
            "[ucl_probe] league-phase standings rebuilt from %d played matches",
            matches_played
        ))
    else
        ranking_log("global_standings|unavailable, keeping native group numbers")
        log("[ucl_probe] WARNING: match records not found; table still shows per-group numbers")
    end""",
    """        ranking_log(string.format(
            "global_standings|comp=%d|matches_played=%d|teams_with_results=%d/%d",
            comp, matches_played[comp], covered, total
        ))
        log(string.format(
            "[ucl_probe] comp %d league-phase standings rebuilt from %d played matches",
            comp, matches_played[comp]
        ))
    end""")

rep("""    league_records = merged
    window_start = 0
    visible_rows = ranking_group_layout_rows
    if not write_visible_window() then""",
    """    league_records = merged
    league_total = total
    league_comp = comp
    window_start = 0
    visible_rows = ranking_group_layout_rows
    league_page_count = league_total - visible_rows + 1
    if title_buffer_addr then
        memory.write(title_buffer_addr, (league_titles[comp] or league_title) .. "\\x00")
    end
    if not write_visible_window() then""")

rep("""        "merge_applied|object=%s|records=32|visible_rows=%d|window=1-%d|pages=%d",
        memory.hex(object), visible_rows, visible_rows, league_page_count
    ))
    log(string.format(
        "[ucl_probe] native UCL league window applied: 32 teams, rows 1-%d",
        visible_rows
    ))""",
    """        "merge_applied|object=%s|comp=%d|records=%d|visible_rows=%d|window=1-%d|pages=%d",
        memory.hex(object), league_comp, league_total, visible_rows, visible_rows, league_page_count
    ))
    log(string.format(
        "[ucl_probe] native league window applied: comp %d, %d teams, rows 1-%d",
        league_comp, league_total, visible_rows
    ))""")

rep("    if #league_records ~= 32 or not merged_records_addr then",
    "    if #league_records ~= league_total or not merged_records_addr then")
rep("    if not active_object or object ~= active_object or #league_records ~= 32 then",
    "    if not active_object or object ~= active_object or #league_records ~= league_total then", count=3)
rep("    local limit = 32 - visible_rows", "    local limit = league_total - visible_rows", count=2)
rep("        window_start = math.min(window_start + step, 32 - visible_rows)",
    "        window_start = math.min(window_start + step, league_total - visible_rows)")
rep("""        "[ucl_probe] UCL league window: %d-%d of 32",
        window_start + 1, window_start + visible_rows""",
    """        "[ucl_probe] league window: %d-%d of %d",
        window_start + 1, window_start + visible_rows, league_total""")
rep("""    if active_object and #league_records == 32 then
        return string.format(
            "UCL Fase Liga: R1 baja, L1 sube | equipos %d-%d de 32",
            window_start + 1, window_start + visible_rows
        )
    end""",
    """    if active_object and #league_records == league_total then
        return string.format(
            "%s Fase Liga: R1 baja, L1 sube | equipos %d-%d de %d",
            league_comp == 5 and "UEL" or "UCL",
            window_start + 1, window_start + visible_rows, league_total
        )
    end""")
rep("    merged_outer_addr = memory.allocate_codecave(league_page_count * 24)",
    "    merged_outer_addr = memory.allocate_codecave(max_league_pages * 24)")
rep('            "[ucl_probe] %d-row/32-team league window armed: capture=%s->%s pages=%d refresh=%s->%s",',
    '            "[ucl_probe] %d-row league window (32 or 36 teams, UCL/UEL) armed: capture=%s->%s pages=%d refresh=%s->%s",')
rep("""    active_object = nil
    saved_object_state = nil
    league_records = {}
    window_start = 0""", """    active_object = nil
    saved_object_state = nil
    league_records = {}
    window_start = 0
    if title_buffer_addr then
        memory.write(title_buffer_addr, league_title .. "\\x00")
    end""")

P.write_text(s, encoding='utf-8')
print('patched', P)
