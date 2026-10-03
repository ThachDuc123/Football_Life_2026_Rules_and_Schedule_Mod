"""Check euro_calendar.h the way euro_extra.dll uses it.

Re-implements the DLL's row logic (round codes 0x141557B90, bracket size from the
club count, single/two-legged stages) on the generated tables with FL26's club
counts, then verifies:
  * every round/leg the game will create for a competition has a row;
  * rounds of a competition come in order;
  * every kind of club (country x division x European competition, as in
    calendar/build_calendar.py) has at least MIN_GAP days between two matches.
Usage: python test_calendar.py
"""
import collections
import importlib.util
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
HEADER = (HERE.parent / 'euro_calendar.h').read_text(encoding='utf-8')
spec = importlib.util.spec_from_file_location('bc', HERE.parent / 'calendar' / 'build_calendar.py')
bc = importlib.util.module_from_spec(spec)
sys.argv = ['x']
spec.loader.exec_module(bc)          # definitions only (main() is not run)

LEAGUES = {}
block = HEADER[HEADER.index('kCalLeagues[]'):HEADER.index('kCalRows[]')]
for m in re.finditer(r'^    \{(\d+), (\d+), (\d+), \{([\d, ]+)\}\},$', block, re.M):
    LEAGUES[int(m[1])] = (int(m[2]), int(m[3]), [int(x) for x in m[4].split(',')])
block = HEADER[HEADER.index('kCalRows[]'):HEADER.index('kCalStages[]')]
ROWS = collections.defaultdict(list)
for m in re.finditer(r'\{(\d+), (\d+), (\d+), (\d+)\}', block):
    ROWS[int(m[1])].append((int(m[2]), int(m[3]), int(m[4])))
block = HEADER[HEADER.index('kCalStages[]'):HEADER.index('kCalSingle[]')]
STAGES = {}
for m in re.finditer(r'\{(\d+), (\d+), ([01]), \{(\d+), (\d+)\}\}', block):
    STAGES[(int(m[1]), int(m[2]))] = (bool(int(m[3])), int(m[4]), int(m[5]))
SINGLE = {int(x) for x in re.search(r'kCalSingle\[\] = \{([\d, ]+)\}', HEADER)[1].split(',')}

CUP_CLUBS = {23: 44, 139: 44, 24: 40, 25: 41, 26: 40, 27: 18, 28: 18, 53: 18, 122: 16, 123: 18,
             124: 14, 125: 18, 137: 12, 142: 12, 144: 8, 146: 12}


def round_code(total, teams):
    if teams == 2:
        return 53
    if teams == 4:
        return 52 if total > 4 else 46
    if teams == 8:
        return 51 if total > 8 else 46
    return {1: 46, 2: 47, 4: 48, 8: 49, 16: 50}.get(total // teams, 55)


def bracket(n):
    t = 2
    while t < n:
        t <<= 1
    return t


def season_order(doy):
    """Day of year -> position in a July-June season."""
    return doy - 181 if doy >= 181 else doy + 184


def rows_of(comp):
    """[(day, code, leg, stage label)] as euro_extra.dll would answer."""
    if comp in LEAGUES:
        teams, rounds, days = LEAGUES[comp]
        return [(days[r], r, 2, ('R', r)) for r in range(rounds)]
    if comp in (3, 5):
        out = [(d, c, l, ('MD', c)) for d, c, l in ROWS[comp] if c <= 7]
        return out                      # (the empty ninth round has no match)
    if comp == 77:
        return [(d, c, l, ('MD', c)) for d, c, l in ROWS[comp] if c <= 5]
    if comp in CUP_CLUBS:
        total, out = bracket(CUP_CLUBS[comp]), []
        t = total
        while t >= 2:
            two, d0, d1 = STAGES[(comp, t)]
            code = round_code(total, t)
            out += [(d0, code, 0, (t, 0)), (d1, code, 1, (t, 1))] if two else [(d0, code, 2, (t, 2))]
            t >>= 1
        return out
    return [(d, c, l, (c, l)) for d, c, l in ROWS[comp]]


def main():
    problems = []
    # 1. coverage / legs for the cups
    for comp, n in CUP_CLUBS.items():
        total = bracket(n)
        t = total
        while t >= 2:
            if (comp, t) not in STAGES:
                problems.append(f'cup {comp}: no stage for {t} clubs')
            t >>= 1
    # 2. order inside every competition
    for comp in set(LEAGUES) | set(ROWS) | set(CUP_CLUBS):
        if comp in (2,):
            continue
        rows = rows_of(comp)
        seq = [season_order(d) for d, code, _, _ in rows if not (comp == 1 and code == 54)]
        if seq != sorted(seq) or len(set(seq)) != len(seq):
            problems.append(f'comp {comp}: rounds out of order {seq}')
    # 3. gaps per kind of club
    def days(comps, top=True):
        out = []
        for c in comps:
            base = bc.ALIAS.get(c, c)
            for d, code, leg, label in rows_of(base):
                if top and c in bc.FIRST_ROUND_LOWER and code == 46:
                    continue
                if c == 1 and code == 54:
                    continue
                out.append((season_order(d), f'{c}:{label}'))
        return out
    worst = 99
    for cc, (top, d2, cups, sup) in bc.COUNTRY.items():
        kinds = {}
        for euro, ecomps in bc.EURO.items():
            if cc not in bc.HOLDER_COUNTRIES:
                ecomps = [c for c in ecomps if c != 7]
            kinds[euro] = days(top + cups + sup + ecomps)
        if d2:
            kinds['D2'] = days(d2 + cups, top=False)
        for kind, ds in kinds.items():
            ds.sort()
            for (a, la), (b, lb) in zip(ds, ds[1:]):
                worst = min(worst, b - a)
                if b - a < bc.MIN_GAP:
                    problems.append(f'{cc}/{kind}: {la} and {lb} only {b - a} day(s) apart')
    print(f'{len(LEAGUES)} league tables, {sum(len(v) for v in ROWS.values())} fixed rows, '
          f'{len(STAGES)} cup stages; smallest gap {worst} days')
    print('\n'.join(problems[:40]) if problems else 'OK: every round covered, in order, >= %d days apart' % bc.MIN_GAP)
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
