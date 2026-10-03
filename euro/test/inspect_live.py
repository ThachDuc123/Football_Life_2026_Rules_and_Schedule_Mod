"""Read-only snapshot of the UCL/UEL league phases in the running game.

Usage: python inspect_live.py [pid]   (no writes: PROCESS_VM_READ only)
Prints, for comps 2/3/4/5/6 and their groups: participants, Round records,
and the league events per round with their dates.
"""
import collections
import struct
import subprocess
import sys

sys.path.insert(0, r'D:\FL26\SiderAddons\content\ucl_calendar_guard')
from audit_native_knockout import Reader, BASE, COMP, ROUND, EVENT, CALENDAR, team  # noqa: E402


def pid_of_game():
    out = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq FL_2026.exe', '/FO', 'CSV', '/NH'],
                         capture_output=True, text=True).stdout.strip()
    return int(out.split(',')[1].strip('"')) if 'FL_2026' in out else None


def main():
    pid = int(sys.argv[1]) if len(sys.argv) > 1 else pid_of_game()
    r = Reader(pid)
    root = r.pointer(BASE + 0x3705E10)
    model = r.pointer(root + 0x48) if root else 0
    if not model:
        print('no Master League loaded')
        return 1
    count = struct.unpack('<I', r.read(model + 0xD0BCF4, 4))[0]
    comps = r.read(model + COMP, 300 * 0x314)
    rounds = r.read(model + ROUND, 2000 * 0x208)
    events = r.read(model + EVENT, 13000 * 0x254)
    cal = r.read(model + CALENDAR + 0x3F174, 6)
    day, year, _ = struct.unpack('<HHH', cal)
    print(f'model {model:#x}  calendar day {day} year {year}  competitions {count}')
    for i in range(count):
        rec = comps[i * 0x314:(i + 1) * 0x314]
        cid = struct.unpack_from('<H', rec)[0]
        if cid & 0x3FF not in (2, 3, 4, 5, 6):
            continue
        actual = (struct.unpack_from('<I', rec, 0x308)[0] >> 16) & 0x7F
        groups = rec[0x307] & 0x3F
        rcount = (struct.unpack_from('<I', rec, 0x300)[0] >> 19) & 0x3F
        rids = [x for x in struct.unpack_from('<58i', rec, 0x88) if x != -1]
        parts = [team(struct.unpack_from('<I', rec, 0x170 + k * 4)[0]) for k in range(actual)]
        line = f'comp {cid:#06x} groups={groups} participants={actual} rounds={rcount} round_ids={rids[:12]}'
        if cid & 0x3FF in (3, 5) and cid >> 10:
            ties = []
            for rid in rids:
                rd = rounds[rid * 0x208:(rid + 1) * 0x208]
                packed = struct.unpack_from('<I', rd, 0x204)[0]
                ties.append((packed >> 26, packed & 0x3FFFFFF))
            line += f' round(code,ties)={ties}'
        print(line)
        if actual and cid >> 10 == 0:
            print('   ', parts)
    for base in (3, 5):
        per = collections.Counter()
        dates = collections.defaultdict(set)
        teams = collections.Counter()
        for eid in range(13000):
            pos = eid * 0x254
            if struct.unpack_from('<H', events, pos)[0] != eid:
                continue
            packed = struct.unpack_from('<I', events, pos + 4)[0]
            if packed & 0x3FF != base:
                continue
            code = (packed >> 16) & 0xFFF
            per[code] += 1
            y, m, d = struct.unpack_from('<HBB', events, pos + 8)
            dates[code].add(f'{y}-{m:02}-{d:02}')
            for off in (0x14, 0x18):
                teams[team(struct.unpack_from('<I', events, pos + off)[0])] += 1
        print(f'comp {base}: {sum(per.values())} league events, {len(teams)} clubs, '
              f'matches per club {sorted(set(teams.values()))}')
        for code in sorted(per):
            print(f'   round {code}: {per[code]} events, dates {sorted(dates[code])}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
