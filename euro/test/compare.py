"""Check euro_core.h (test_core.exe) against euro_rules.py on real saves.

Usage: python compare.py test_core.exe save [save ...]
Also checks the bracket invariants of the 2025/26 regulations.
"""
import os
import random
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, r'D:\FL26\SiderAddons\content\ucl_calendar_guard')
import euro_rules as er  # noqa: E402
from export_events import events_from_save  # noqa: E402


def python_dump(events, year, qualified, ranks=None):
    lines = []
    rows, unplayed = er.league_table(events, 3, ranks=ranks)
    lines.append(f'UCL {len(rows)} {unplayed}')
    order = er.ranked(rows)
    for p, r in enumerate(order):
        lines.append('RANK %d %d %d %d %d %d %d %d %d %d %d %d %d' % (
            p + 1, r['id'], r['played'], r['points'], r['gf'] - r['ga'], r['gf'], r['away_gf'],
            r['wins'], r['away_wins'], r['opp_points'], r['opp_gd'], r['opp_gf'], r['discipline']))
    if len(order) >= 24:
        seed = er.draw_seed(year, [r['id'] for r in order[:24]])
        lines.append(f'SEED {seed}')
        ties = er.build_bracket(seed)
        lines += [f'TIE {k} {s} {h} {a}' for k, (s, h, a) in enumerate(ties)]
        if len(order) == 32:
            perm = [0] * 32
            for k, (s, h, a) in enumerate(ties):
                perm[k], perm[23 - k], perm[8 + k] = s, h, a
            for i in range(24, 32):
                perm[i] = i
            lines.append('PERM ' + ' '.join(map(str, perm)))
    if qualified:
        for i, t in enumerate(er.group_thirds(events, 5, qualified)):
            lines.append('THIRD %d %d %d %d %d %d' % (i, t['id'], t['points'], t['gd'], t['gf'], t['wins']))
    return lines


def check_bracket(ties):
    seeds = [t[0] for t in ties]
    assert sorted(seeds) == list(range(8)), seeds
    sections = {0: 3, 1: 3, 2: 2, 3: 2, 4: 1, 5: 1, 6: 0, 7: 0}   # seed -> play-off section
    for s, home, away in ties:
        sec = sections[s]
        assert away in (8 + 2 * sec, 9 + 2 * sec), (s, away)
        assert home in (22 - 2 * sec, 23 - 2 * sec), (s, home)
    for half in (ties[:4], ties[4:]):
        names = [t[0] // 2 for t in half]            # 0=A 1=B 2=C 3=D
        assert names == [0, 3, 1, 2], names
    pos = sorted(p for t in ties for p in t)
    assert pos == list(range(24)), pos


def main():
    exe = sys.argv[1]
    runs = []
    for save in sys.argv[2:]:
        events, clubs = events_from_save(Path(save))
        runs.append((save, events, clubs, ''))
        # Every played league match 0-0: the table is then decided by the last
        # criteria only (opponents, discipline, club ranking).
        draws = bytearray(events)
        for eid in range(er.CAPACITY):
            pos = eid * er.STRIDE
            if int.from_bytes(draws[pos:pos + 2], 'little') == eid and \
                    int.from_bytes(draws[pos + 4:pos + 8], 'little') & 0x3FF == 3:
                draws[pos + 0x1C] = draws[pos + 0x1F] = 0
        runs.append((save, bytes(draws), clubs, ' (all league matches 0-0)'))
    for save, events, clubs, variant in runs:
        fx_year = 0
        with tempfile.TemporaryDirectory() as tmp:
            binp = os.path.join(tmp, 'events.bin')
            Path(binp).write_bytes(events)
            # Europa League knockout clubs that did not come from the UCL league phase.
            ucl = {r['id'] for r in er.league_table(events, 3)[0]}
            r32 = set()
            for eid in range(er.CAPACITY):
                pos = eid * er.STRIDE
                if int.from_bytes(events[pos:pos + 2], 'little') != eid:
                    continue
                packed = int.from_bytes(events[pos + 4:pos + 8], 'little')
                if packed & 0x3FF == 6 and (packed >> 16) & 0xFFF == 46:
                    r32.add(er.team(int.from_bytes(events[pos + 0x14:pos + 0x18], 'little')))
                    r32.add(er.team(int.from_bytes(events[pos + 0x18:pos + 0x1C], 'little')))
                if packed & 0x3FF == 3 and not fx_year:
                    fx_year = int.from_bytes(events[pos + 8:pos + 10], 'little')
            qualified = sorted(r32 - ucl)
            qpath = os.path.join(tmp, 'q.txt')
            Path(qpath).write_text(' '.join(map(str, qualified)))
            # Random world-club-ranking places, so the last tie-breaker is exercised too.
            rnd = random.Random(fx_year)
            ids = sorted(ucl)
            ranks = dict(zip(ids, rnd.sample(range(1, 600), len(ids))))
            rpath = os.path.join(tmp, 'ranks.txt')
            Path(rpath).write_text('\n'.join(f'{t} {p}' for t, p in ranks.items()))
            out = subprocess.run([exe, binp, str(fx_year), qpath, rpath], capture_output=True, text=True,
                                 check=True).stdout.split('\n')
            cpp = [l for l in out if l]
            py = python_dump(events, fx_year, qualified, ranks)
            same = cpp == py
            print(f'{Path(save).parent.parent.name}/{Path(save).name}{variant}: year {fx_year}, '
                  f'{cpp[0]}, lines {len(cpp)}, C++ == Python: {same}')
            if not same:
                for a, b in zip(cpp, py):
                    if a != b:
                        print('  C++', a, '\n  PY ', b)
                        break
                raise SystemExit(1)
            ties = [tuple(map(int, l.split()[2:])) for l in cpp if l.startswith('TIE')]
            if ties:
                check_bracket(ties)
                print('  bracket invariants ok')
            thirds = [l for l in cpp if l.startswith('THIRD')]
            if thirds:
                print(f'  {len(thirds)} Europa League thirds, best 8:',
                      [clubs[int(l.split()[2])].name for l in thirds[:8]])


if __name__ == '__main__':
    main()
