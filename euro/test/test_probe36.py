"""The 36-club single table of modules/ucl_schedule_probe.lua against euro_rules.py.

Takes the events written by test_format36.exe (league phase after the
generator), plays every UCL/UEL league match (random scores, then a second run
with every match 0-0 so the last criteria decide), gives the clubs random places
in a fake world club ranking, then runs the probe's league_phase_standings +
standings_before (extracted verbatim, with memory/readable_span stubs) and
compares the order of both tables with the Python port.
Usage: python test_probe36.py events_after.bin
"""
import random
import struct
import sys
from pathlib import Path

from lupa import luajit21 as lj

sys.path.insert(0, r'D:\FL26\SiderAddons\content\ucl_calendar_guard')
import euro_rules as er  # noqa: E402

STRIDE = 0x254
src = Path(r'D:\FL26\SiderAddons\modules\ucl_schedule_probe.lua').read_text(encoding='utf-8')


def chunk(start, end):
    i = src.index(start)
    return src[i:src.index(end, i)]


CODE = '\n'.join([
    chunk('local function decode_team(encoded)', 'local function parse_hex'),
    chunk('local function signed_u32(number)', 'local function standings_equal'),
    chunk('-- Article 18.01 criteria', 'local function validate_match_block'),
    chunk('-- Every played league-phase match', 'local function pack_record_fields'),
])
HARNESS = '''
local bit = require("bit")
local EVENTS, RANKING = EVENTS, RANKING
local MODEL = 0x10000000
memory = { read = function(addr, n)
    if addr == MODEL + 0xE9FF08 then return EVENTS end
    if addr == MODEL + 0x16705A8 then return RANKING end
    return string.rep("\\0", n)
end }
local function readable_span() return true end
local function read_u64(addr)
    if addr == 0x143705E10 then return 0x50000 end
    if addr == 0x50000 + 0x48 then return MODEL end
    return 0
end
local match_record_stride = 0x254
''' + CODE + '''
local standings, extras, played = league_phase_standings()
local result = {}
for _, comp in ipairs({ 3, 5 }) do
    league_extra = extras[comp]
    local records = {}
    for team, row in pairs(standings[comp]) do
        local gd = row.gf - row.gc
        if gd < 0 then gd = gd + 0x100000000 end
        records[#records + 1] = { fields = { team * 0x4000, 0, row.pj, row.pts, row.g, row.e, row.p, row.gf, row.gc, gd } }
    end
    table.sort(records, standings_before)
    local order = {}
    for i, r in ipairs(records) do order[i] = decode_team(r.fields[1]) end
    result[comp] = order
end
return result[3], result[5], played[3], played[5]
'''


def play(events, draws, rnd):
    out = bytearray(events)
    for eid in range(13000):
        pos = eid * STRIDE
        if struct.unpack_from('<H', out, pos)[0] != eid:
            continue
        packed = struct.unpack_from('<I', out, pos + 4)[0]
        if packed & 0x3FF in (3, 5):
            struct.pack_into('<I', out, pos + 4, packed | 0x40000000)
            out[pos + 0x1C] = 0 if draws else rnd.choice([0, 0, 1, 1, 1, 2, 2, 3, 4])
            out[pos + 0x1F] = 0 if draws else rnd.choice([0, 0, 1, 1, 1, 2, 2, 3])
    return bytes(out)


def main():
    base = Path(sys.argv[1]).read_bytes()
    rnd = random.Random(7)
    ok = True
    for draws in (False, True):
        events = play(base, draws, rnd)
        teams = {r['id']: r['encoded'] for comp in (3, 5) for r in er.league_table(events, comp)[0]}
        places = dict(zip(sorted(teams), rnd.sample(range(1, 600), len(teams))))
        ranking = bytearray(b'\xff' * (16 * 1024))
        for i, (t, place) in enumerate(sorted(places.items(), key=lambda kv: kv[1])):
            struct.pack_into('<4I', ranking, i * 16, teams[t], place, 0, 0)
        lua = lj.LuaRuntime()
        lua.globals().EVENTS = events
        lua.globals().RANKING = bytes(ranking)
        ucl, uel, p3, p5 = lua.execute(HARNESS)
        for comp, lua_order, played in ((3, ucl, p3), (5, uel, p5)):
            lua_list = [lua_order[i] for i in range(1, len(lua_order) + 1)]
            rows, _ = er.league_table(events, comp, ranks=er.club_ranks(bytes(ranking)))
            py_list = [r['id'] for r in er.ranked(rows)]
            same = lua_list == py_list
            ok &= same and len(lua_list) == 36 and played == 144
            print(f'comp {comp}{" (all 0-0)" if draws else ""}: {played} played, {len(lua_list)} clubs, '
                  f'Lua == Python: {same}')
    sys.exit(0 if ok else 1)


main()
