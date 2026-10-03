"""Choose the days of the UEFA and league-cup rounds inside the game calendar.

The game dates every competition by fixed day-of-year rows (day 0 = 1 January)
that repeat each season; the domestic leagues and cups keep the FL26 rows
(data/game_days.json, read from Master League saves plus the split-stage rows
of the executable). For every round of the competitions we date ourselves
this picks the day closest to the real 2025/26 date such that every club that
can play it is at least MIN_GAP days away from any other match it can have
(league, domestic cups, super cups, the other new rounds).

Usage: python plan_calendar.py            -> prints the plan and the checks
"""
import datetime as dt
import json
import sys
from pathlib import Path

MIN_GAP = 3
HERE = Path(__file__).resolve().parent
GAME = {int(k): set(v) for k, v in json.loads((HERE / 'data' / 'game_days.json').read_text()).items()}

# Split stages that only appear late in a season (rows read from the exe).
GAME.setdefault(135, set()).update({107, 114, 121, 128, 142})   # Scotland top six
GAME.setdefault(136, set()).update({107, 114, 121, 128, 142})   # Scotland bottom six
for c in (156, 157, 158, 172):                                   # Belgium play-offs
    GAME.setdefault(c, set()).update({79, 86, 107, 114, 128, 142})
GAME.setdefault(159, set()).update({170, 171})
for c in (148, 149, 150, 175):                                   # Denmark championship/relegation
    GAME.setdefault(c, set()).update({58, 65, 72, 79, 86, 100, 107, 114, 121, 128})
GAME.setdefault(151, set()).update({167, 174})
GAME.setdefault(83, set()).update({165, 168, 171, 174})           # EFL play-offs
CWC = {349, 352}                                                  # Club World Cup (UCL holder)

COUNTRIES = {   # top-division competitions + cups + super cups per country
    'ENG': [17, 23, 86], 'ITA': [18, 24, 89], 'ESP': [19, 25, 87], 'GER': [20, 26, 88],
    'NED': [21, 27, 90], 'POR': [22, 28, 91], 'POL': [50, 53, 95], 'FRA': [116, 123, 129],
    'GRE': [117, 124], 'TUR': [118, 125, 130], 'BEL': [155, 156, 157, 158, 172, 159, 122, 128],
    'SCO': [134, 135, 136, 137], 'DEN': [147, 148, 149, 150, 175, 151, 142],
}


def days_of(comps):
    out = set()
    for c in comps:
        out |= GAME.get(c, set())
    return out


EUROPE = set()
for comps in COUNTRIES.values():
    EUROPE |= days_of(comps)


def date(day):
    d = dt.date(2025, 1, 1) + dt.timedelta(days=day)
    return d.strftime('%d/%m')


def real(month, day):
    return (dt.date(2025, month, day) - dt.date(2025, 1, 1)).days


def gap(a, b):
    d = abs(a - b) % 365
    return min(d, 365 - d)


def choose(target, busy, taken=(), window=12):
    """Closest day to target with gap >= MIN_GAP to busy and to taken."""
    best = None
    for delta in range(window + 1):
        for day in sorted({(target - delta) % 365, (target + delta) % 365}):
            if all(gap(day, b) >= MIN_GAP for b in busy) and all(gap(day, t) >= MIN_GAP for t in taken):
                return day
            score = min([gap(day, b) for b in busy] + [gap(day, t) for t in taken] + [99])
            if best is None or score > best[0]:
                best = (score, day)
    return best[1]


def plan():
    p = {}
    # UEFA league phases. Native game days (UCL 257.., UEL 258..) already fit the
    # league calendar; the January matchdays and the Conference League are new.
    p['UCL league'] = [choose(real(m, d), EUROPE) for m, d in
                       ((9, 16), (9, 30), (10, 21), (11, 4), (11, 25), (12, 9), (1, 20), (1, 28))]
    p['UEL league'] = [choose(real(m, d), EUROPE) for m, d in
                       ((9, 24), (10, 2), (10, 23), (11, 6), (11, 27), (12, 11), (1, 22), (1, 29))]
    p['UECL league'] = [choose(real(m, d), EUROPE) for m, d in
                        ((10, 2), (10, 23), (11, 6), (11, 27), (12, 11), (12, 18))]
    ko = ((2, 17), (2, 24), (3, 10), (3, 17), (4, 7), (4, 14), (4, 28), (5, 5))
    p['UCL knockout'] = [choose(real(m, d), EUROPE) for m, d in ko] + [choose(real(5, 30), EUROPE)]
    ko2 = ((2, 19), (2, 26), (3, 12), (3, 19), (4, 9), (4, 16), (4, 30), (5, 7))
    p['UEL knockout'] = [choose(real(m, d), EUROPE) for m, d in ko2] + [choose(real(5, 20), EUROPE)]
    p['UECL knockout'] = [choose(real(m, d), EUROPE) for m, d in ko2] + [choose(real(5, 27), EUROPE)]
    uefa_eng = set(p['UCL league'] + p['UEL league'] + p['UECL league'] + p['UCL knockout']
                   + p['UEL knockout'] + p['UECL knockout']) | {230, 237, 222} | CWC
    # EFL Cup: 44 clubs, 6 rounds (R1 = Championship clubs in the real draw,
    # R2 = round of 32, R3 = round of 16, QF, SF two legs, final).
    eng = days_of([17, 79, 23, 86, 83]) | uefa_eng
    efl = []
    for m, d in ((8, 12), (9, 17), (10, 29), (12, 17), (1, 14), (2, 4)):
        efl.append(choose(real(m, d), eng, efl))
    efl.append(choose(real(3, 22), eng, efl))
    p['EFL Cup'] = efl
    # Taca da Liga: quarter-finals, final four (semi-finals, final).
    por = days_of([22, 28, 91]) | uefa_eng
    taca = []
    for m, d in ((10, 29), (1, 6), (1, 10)):
        taca.append(choose(real(m, d), por, taca))
    p['Taca da Liga'] = taca
    # Scottish League Cup: second round (last 16), QF, SF, final.
    sco = days_of([134, 135, 136, 137]) | uefa_eng
    scot = []
    for m, d in ((8, 16), (9, 20), (11, 1), (12, 14)):
        scot.append(choose(real(m, d), sco, scot))
    p['Scottish League Cup'] = scot
    return p


def check(p):
    """Min gap of every planned day against what its clubs can also play."""
    bad = []
    uefa = {k: v for k, v in p.items() if k.startswith(('UCL', 'UEL', 'UECL'))}
    for name, days in uefa.items():
        for d in days:
            g = min(gap(d, e) for e in EUROPE)
            if g < MIN_GAP:
                bad.append(f'{name} {date(d)}: {g} day(s) from a domestic match')
    for name, comps in (('EFL Cup', [17, 79, 23, 86, 83]), ('Taca da Liga', [22, 28, 91]),
                        ('Scottish League Cup', [134, 135, 136, 137])):
        others = days_of(comps)
        for k, v in uefa.items():
            others |= set(v)
        for d in p[name]:
            g = min(gap(d, e) for e in others | CWC | {230, 237, 222})
            if g < MIN_GAP:
                bad.append(f'{name} {date(d)}: {g} day(s) from another match')
    return bad


if __name__ == '__main__':
    p = plan()
    for k, v in p.items():
        print(f'{k:20}', ' '.join(f'{date(d)}({d})' for d in v))
    problems = check(p)
    print('\n'.join(problems) if problems else f'all rounds at least {MIN_GAP} days from any other match')
    sys.exit(1 if problems else 0)
