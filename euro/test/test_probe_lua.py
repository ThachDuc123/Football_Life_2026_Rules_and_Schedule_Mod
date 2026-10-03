"""Run the standings code of modules/ucl_schedule_probe.lua (extracted verbatim)
on a real save's league phase and compare its order with euro_rules.py."""
import re
import sys
from pathlib import Path

from lupa import luajit21 as lj

sys.path.insert(0, r'D:\FL26\SiderAddons\content\ucl_calendar_guard')
import euro_rules as er  # noqa: E402
from export_events import events_from_save  # noqa: E402

src = Path(r'D:\FL26\SiderAddons\modules\ucl_schedule_probe.lua').read_text(encoding='utf-8')


def chunk(start, end):
    i = src.index(start)
    j = src.index(end, i)
    return src[i:j]


code = '\n'.join([
    chunk('local function decode_team(encoded)', 'local function parse_hex'),
    chunk('local function signed_u32(number)', 'local function standings_equal'),
    chunk('-- Article 18.01 criteria', 'local function validate_match_block'),
    chunk('local function standings_from_results()', 'local function pack_record_fields'),
])
events, _ = events_from_save(Path(sys.argv[1]))
first = [i for i in range(13000)
         if int.from_bytes(events[i * 0x254:i * 0x254 + 2], 'little') == i
         and int.from_bytes(events[i * 0x254 + 4:i * 0x254 + 8], 'little') & 0x3FF == 3]
assert len(first) == 96 and first == list(range(first[0], first[0] + 96)), 'league block not contiguous'
block = events[first[0] * 0x254:(first[0] + 96) * 0x254]
lua = lj.LuaRuntime()
g = lua.globals()
g.BLOCK = block
harness = '''
local bit = require("bit")
local BLOCK = BLOCK
memory = { read = function(addr, n) return string.sub(BLOCK, addr + 1, addr + n) end }
local match_record_stride = 0x254
local match_record_count = 96
local match_state_played = 0x60
local function locate_match_block() return 0 end
''' + code + '''
local standings, played = standings_from_results()
local records = {}
for team, row in pairs(standings) do
    local gd = row.gf - row.gc
    if gd < 0 then gd = gd + 0x100000000 end
    records[#records + 1] = { fields = { team * 0x4000, 0, row.pj, row.pts, row.g, row.e, row.p, row.gf, row.gc, gd } }
end
table.sort(records, standings_before)
local out = {}
for i, r in ipairs(records) do out[i] = decode_team(r.fields[1]) end
return out, played
'''
out, played = lua.execute(harness)
lua_order = [out[i] for i in range(1, len(out) + 1)]
rows, unplayed = er.league_table(events, 3)
py_order = [r['id'] for r in er.ranked(rows)]
print('played', played, 'clubs', len(lua_order), 'Lua == Python:', lua_order == py_order)
assert lua_order == py_order, (lua_order, py_order)
