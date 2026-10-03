"""Read-only view of the new competitions in the running game (test 1).

Usage: python inspect_extra.py [pid]
For comps 76/77/78 (Conference League), 139/144/146 (league cups) and, for
comparison, 23 (FA Cup): competition records (participants, groups, round
ids) and their events (round code, leg, date, teams) grouped by round.
"""
import collections
import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, r'D:\FL26\SiderAddons\content\ucl_calendar_guard')
from audit_native_knockout import Reader, BASE, COMP, EVENT, CALENDAR, team  # noqa: E402
from inspect_live import pid_of_game  # noqa: E402

WATCH = (76, 77, 78, 139, 144, 146, 23)
NAMES = Path(__file__).with_name('club_names.json')


def main():
    pid = int(sys.argv[1]) if len(sys.argv) > 1 else pid_of_game()
    if not pid:
        print('game not running')
        return 1
    names = {int(k): v for k, v in json.loads(NAMES.read_text(encoding='utf-8')).items()} if NAMES.exists() else {}
    nm = lambda t: names.get(t, str(t))[:18]
    r = Reader(pid)
    root = r.pointer(BASE + 0x3705E10)
    model = r.pointer(root + 0x48) if root else 0
    if not model:
        print('no Master League loaded')
        return 1
    count = struct.unpack('<I', r.read(model + 0xD0BCF4, 4))[0]
    comps = r.read(model + COMP, 300 * 0x314)
    events = r.read(model + EVENT, 13000 * 0x254)
    day, year = struct.unpack('<HH', r.read(model + CALENDAR + 0x3F174, 4))
    print(f'calendar day {day} year {year}; competitions {count}')
    for i in range(count):
        rec = comps[i * 0x314:(i + 1) * 0x314]
        cid = struct.unpack_from('<H', rec)[0]
        if cid & 0x3FF not in WATCH:
            continue
        actual = (struct.unpack_from('<I', rec, 0x308)[0] >> 16) & 0x7F
        groups = rec[0x307] & 0x3F
        legmode = struct.unpack_from('<I', rec, 0x300)[0] >> 29
        rids = [x for x in struct.unpack_from('<58i', rec, 0x88) if x != -1]
        parts = [team(struct.unpack_from('<I', rec, 0x170 + k * 4)[0]) for k in range(actual)]
        print(f'comp {cid & 0x3FF} group {cid >> 10}: participants {actual} groups {groups} '
              f'legmode {legmode} next {struct.unpack_from("<H", rec, 0x78)[0]} rounds {len(rids)}')
        if actual and cid >> 10 == 0:
            print('    ' + ', '.join(nm(t) for t in parts))
    by = collections.defaultdict(list)
    for eid in range(13000):
        pos = eid * 0x254
        if struct.unpack_from('<H', events, pos)[0] != eid:
            continue
        packed = struct.unpack_from('<I', events, pos + 4)[0]
        if packed & 0x3FF not in WATCH:
            continue
        code, leg = (packed >> 16) & 0xFFF, (packed >> 28) & 3
        y, m, d = struct.unpack_from('<HBB', events, pos + 8)
        h, a = team(struct.unpack_from('<I', events, pos + 0x14)[0]), team(struct.unpack_from('<I', events, pos + 0x18)[0])
        by[(packed & 0x3FF, code, leg)].append((f'{y}-{m:02}-{d:02}', nm(h), nm(a), (packed >> 10) & 0x3F,
                                                bool(packed & 0x40000000)))
    for key in sorted(by):
        rows = by[key]
        dates = sorted({x[0] for x in rows})
        played = sum(1 for x in rows if x[4])
        print(f'comp {key[0]} round {key[1]} leg {key[2]}: {len(rows)} events, {played} played, dates {dates}')
        for x in rows[:3]:
            print(f'      g{x[3]} {x[1]} - {x[2]}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
