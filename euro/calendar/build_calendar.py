"""Real 2025/26 calendar for every European competition of the FL26 Master League.

The game dates a competition by rows {day of year, round code, leg} (handlers
behind the dispatcher 0x14157F810) and repeats them every season. FL26's rows
copy the COVID 2020/21 calendar (midweek league rounds on 14/1, 21/1, 4/2), so
the UEFA league phase and the cups cannot get their real dates without clubs
playing two matches in two days. This script builds a new calendar:

  * every round gets the days it really had in 2025/26 (sources/: fixture
    lists of fixturedownload.com and openfootball, cup round dates from the
    competitions' Wikipedia pages), the day with most matches first;
  * the game plays a whole round on ONE day, so for every kind of club
    (country x division x European competition) all its possible matches must
    be at least MIN_GAP days apart; a min-conflicts search picks, per round,
    one of its real days, widening to nearby days only where nothing fits;
  * no European league round before CLAMP (the new season's leagues are
    created some time between 1 and 24 July; the earliest FL26 fixture is 2/8).

Output: calendar.json (rows per competition, the choices and their cost) and
../euro_calendar.h for euro_extra.dll. Usage: python build_calendar.py
"""
import collections
import csv
import datetime as dt
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / 'sources'
D = dt.date
CLAMP = D(2025, 8, 2)
MIN_GAP = 3
STAGES = ['F', 'SF', 'QF', 'R16', 'R32', 'R64', 'R128']      # from the end


def doy(d):
    return (d - D(d.year, 1, 1)).days


def parse_dmy(s):
    return dt.datetime.strptime(s[:10], '%d/%m/%Y').date()


# ------------------------------------------------------------------ sources
def fd_rounds(slug):
    rows = list(csv.DictReader(open(SRC / f'{slug}.csv', encoding='utf-8-sig')))
    by = collections.OrderedDict()
    for r in rows:
        by.setdefault(r['Round Number'], collections.Counter())[parse_dmy(r['Date'])] += 1
    return by


def of_rounds(name):
    data = json.loads((SRC / f'of_{name}.json').read_text(encoding='utf-8'))
    by = collections.OrderedDict()
    for m in data['matches']:
        by.setdefault(m['round'], collections.Counter())[D.fromisoformat(m['date'])] += 1
    return by


def league_rounds(src, n):
    kind, name = src
    by = fd_rounds(name) if kind == 'fd' else of_rounds(name)
    rounds = [c for k, c in by.items() if k != 'Playoffs']
    assert len(rounds) == n, (name, len(rounds), n)
    return rounds


def weekends(start, end, skip=(), midweeks=()):
    """Generated calendar: every Saturday in [start, end] except `skip`, plus midweeks."""
    out, d = [], start
    while d <= end:
        if d.weekday() == 5 and d not in skip:
            out.append(d)
        d += dt.timedelta(days=1)
    return sorted(out + list(midweeks))


INTL = [D(2025, 9, 6), D(2025, 10, 11), D(2025, 11, 15), D(2026, 3, 28)]


# --------------------------------------------------------------- variables
class Var:
    __slots__ = ('comp', 'key', 'domain', 'real', 'realset', 'choice', 'flex', 'idx')

    def __init__(self, comp, key, counter=None, dates=None, flex=4, fixed=False):
        self.comp, self.key = comp, key
        if counter is not None:
            top = max(counter.values())
            pairs = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))
            dom = []
            main = pairs[0][0]
            for d, c in pairs:
                if abs((d - main).days) > 4:
                    continue                      # a fixture moved to another week
                cost = 0 if c == top else (1 if c >= 2 else 2)
                dom.append((d, cost))
        else:
            dom = [(d, i) for i, d in enumerate(dates)]
        self.real = dom[0][0]
        self.realset = {d for d, _ in dom}
        dom = [(d, c) for d, c in dom if d >= CLAMP or comp in PRESEASON]
        if not dom:                                     # July round of a league
            dom = [(CLAMP, 3)]
        dom = [(d, c) for d, c in dom if (d.month, d.day) not in NO_MATCH] or dom
        self.domain = dom
        self.flex = 0 if fixed else flex
        self.choice = 0
        if not fixed:
            self.widen(7 if comp in UEFA_COMPS else (14 if comp in CUP_COMPS else 4))

    @property
    def day(self):
        return self.domain[self.choice][0]

    def widen(self, extra):
        have = {d for d, _ in self.domain}
        base = self.domain[0][0]
        for delta in range(1, extra + 1):
            for d in (base - dt.timedelta(days=delta), base + dt.timedelta(days=delta)):
                if d not in have and (d >= CLAMP or self.comp in PRESEASON) and (d.month, d.day) not in NO_MATCH:
                    self.domain.append((d, 3 + delta if delta <= 4 else 7 + delta // 2))
                    have.add(d)

    def __repr__(self):
        return f'{self.comp}:{self.key}@{self.day}'


PRESEASON = {105, 106, 107}
NO_MATCH = {(12, 24), (12, 25)}
UEFA_COMPS = {1, 2, 3, 4, 5, 6, 7, 77, 78}
CUP_COMPS = {23, 24, 25, 26, 27, 28, 53, 122, 123, 124, 125, 137, 142, 139, 144, 146,
             86, 87, 88, 89, 90, 91, 95, 128, 129, 130}
VARS = []
BY_COMP = collections.defaultdict(list)       # comp -> ordered vars


def weight(comp, key):
    """How much moving this round away from its real day costs."""
    final = (key[0] == 'S' and key[1] == 'F') or (key[0] in ('K', 'C') and key[1] == 53)
    if comp in UEFA_COMPS:
        return 6 if final else 3
    if comp in CUP_COMPS:
        return 4 if final else 2
    if comp in (79, 80, 81, 82, 83, 84, 85):
        return 1                            # second divisions give way first
    return 3                                # top-division rounds keep their weekend


def add(comp, key, **kw):
    v = Var(comp, key, **kw)
    w = weight(comp, key)
    v.domain = [(d, c * w) for d, c in v.domain]
    v.idx = len(VARS)
    VARS.append(v)
    BY_COMP[comp].append(v)
    return v


# ------------------------------------------------------------------ leagues
LEAGUES = {        # comp: (source, rounds)
    17: (('fd', 'epl'), 38), 79: (('fd', 'championship'), 46),
    18: (('fd', 'serie-a'), 38), 82: (('of', 'it.2'), 38),
    19: (('fd', 'la-liga'), 38), 80: (('of', 'es.2'), 42),
    20: (('fd', 'bundesliga'), 34),
    # FL26's 2. Bundesliga has 22 clubs (42 rounds): the 42-round Segunda calendar
    81: (('of', 'es.2'), 42),
    21: (('fd', 'eredivisie'), 34), 22: (('fd', 'primeira-liga'), 34),
    116: (('fd', 'ligue-1'), 34), 118: (('fd', 'super-lig'), 34),
    117: (('of', 'gr.1'), 26), 155: (('of', 'be.1'), 30), 134: (('of', 'sco.1'), 33),
}
for comp, (src, n) in LEAGUES.items():
    for i, counter in enumerate(league_rounds(src, n)):
        add(comp, ('R', i), counter=counter)

# Leagues without a fixture list here: Saturdays of the real season windows.
POL = weekends(D(2025, 8, 2), D(2025, 12, 13), INTL, [D(2025, 8, 6)]) + \
    weekends(D(2026, 1, 31), D(2026, 5, 23), INTL)
assert len(POL) == 34, len(POL)
for i, d in enumerate(POL):
    add(50, ('R', i), dates=[d, d + dt.timedelta(days=1), d - dt.timedelta(days=1)])
DEN = weekends(D(2025, 8, 2), D(2025, 12, 6), INTL, [D(2025, 8, 6), D(2025, 8, 13)]) + \
    weekends(D(2026, 2, 14), D(2026, 3, 7))
assert len(DEN) == 22, len(DEN)
for i, d in enumerate(DEN):
    add(147, ('R', i), dates=[d, d + dt.timedelta(days=1), d - dt.timedelta(days=1)])
# Split stages (the second group of each pair gets the same days).
DEN_SPLIT = [D(2026, 3, 14), D(2026, 3, 21), D(2026, 4, 4), D(2026, 4, 11), D(2026, 4, 18),
             D(2026, 4, 22), D(2026, 4, 25), D(2026, 5, 2), D(2026, 5, 9), D(2026, 5, 17)]
for i, d in enumerate(DEN_SPLIT):
    add(148, ('R', i), dates=[d, d + dt.timedelta(days=1), d - dt.timedelta(days=1)])
BEL_PO = [D(2026, 4, 4), D(2026, 4, 11), D(2026, 4, 18), D(2026, 4, 25), D(2026, 5, 2), D(2026, 5, 9)]
for i, d in enumerate(BEL_PO):
    add(156, ('R', i), dates=[d, d + dt.timedelta(days=1)])
SCO_SPLIT = [D(2026, 4, 25), D(2026, 5, 2), D(2026, 5, 9), D(2026, 5, 13), D(2026, 5, 16)]
for i, d in enumerate(SCO_SPLIT):
    add(135, ('R', i), dates=[d, d + dt.timedelta(days=1)])
ALIAS = {172: 156, 136: 135, 175: 148, 106: 105, 107: 105}           # same days as their pair
add(159, ('C', 53, 2), dates=[D(2026, 5, 24), D(2026, 5, 23)])      # BEL European play-off final
add(151, ('C', 53, 2), dates=[D(2026, 5, 21), D(2026, 5, 23)])      # DEN European play-off final

# Promotion play-offs (two-legged where real): code 46 = semi-finals, 53 = final.
for comp, sf1, sf2, f1, f2 in (
        (83, [D(2026, 5, 9), D(2026, 5, 8)], [D(2026, 5, 12), D(2026, 5, 11)], [D(2026, 5, 23)], None),
        (85, [D(2026, 5, 17)], [D(2026, 5, 20)], [D(2026, 5, 24)], [D(2026, 5, 29)]),
        (84, [D(2026, 6, 6), D(2026, 6, 7)], [D(2026, 6, 10)], [D(2026, 6, 14)], [D(2026, 6, 20)])):
    add(comp, ('C', 46, 0), dates=sf1)
    add(comp, ('C', 46, 1), dates=sf2)
    if f2 is None:
        add(comp, ('C', 53, 2), dates=f1)
    else:
        add(comp, ('C', 53, 0), dates=f1)
        add(comp, ('C', 53, 1), dates=f2)

# --------------------------------------------------------------------- cups
# Stage dates of 2025/26 (first date = main day). Two-legged stages list both legs.
CUPS = {   # comp: (rounds expected in FL26, {stage: [leg dates...]}, two-legged stages)
    23: (6, {'R64': [[D(2026, 1, 10), D(2026, 1, 11)]], 'R32': [[D(2026, 2, 14), D(2026, 2, 15)]],
             'R16': [[D(2026, 3, 7), D(2026, 3, 8)]], 'QF': [[D(2026, 4, 4), D(2026, 4, 5)]],
             'SF': [[D(2026, 4, 25), D(2026, 4, 26)]], 'F': [[D(2026, 5, 16)]]}, ()),
    139: (6, {'R64': [[D(2025, 8, 12), D(2025, 8, 13)]],
              'R32': [[D(2025, 9, 23), D(2025, 9, 24), D(2025, 9, 16), D(2025, 9, 17)]],
              'R16': [[D(2025, 10, 28), D(2025, 10, 29)]], 'QF': [[D(2025, 12, 16), D(2025, 12, 17)]],
              'SF': [[D(2026, 1, 13), D(2026, 1, 14)], [D(2026, 2, 3), D(2026, 2, 4)]],
              'F': [[D(2026, 3, 22)]]}, ('SF',)),
    24: (6, {'R64': [[D(2025, 8, 16), D(2025, 8, 15), D(2025, 8, 17), D(2025, 8, 18)]],
             'R32': [[D(2025, 9, 24), D(2025, 9, 23), D(2025, 9, 25)]],
             'R16': [[D(2025, 12, 3), D(2025, 12, 2), D(2025, 12, 4)]],
             'QF': [[D(2026, 2, 4), D(2026, 2, 5), D(2026, 2, 10), D(2026, 2, 11)]],
             'SF': [[D(2026, 3, 3), D(2026, 3, 4)], [D(2026, 4, 21), D(2026, 4, 22)]],
             'F': [[D(2026, 5, 13)]]}, ('SF',)),
    25: (6, {'R64': [[D(2025, 12, 3)]], 'R32': [[D(2025, 12, 17)]], 'R16': [[D(2026, 1, 14)]],
             'QF': [[D(2026, 2, 4)]], 'SF': [[D(2026, 2, 11)], [D(2026, 3, 4)]],
             'F': [[D(2026, 4, 18)]]}, ('SF',)),
    26: (6, {'R64': [[D(2025, 8, 16), D(2025, 8, 15), D(2025, 8, 17), D(2025, 8, 18)]],
             'R32': [[D(2025, 10, 28), D(2025, 10, 29)]], 'R16': [[D(2025, 12, 2), D(2025, 12, 3)]],
             'QF': [[D(2026, 2, 3), D(2026, 2, 4), D(2026, 2, 10), D(2026, 2, 11)]],
             'SF': [[D(2026, 4, 22), D(2026, 4, 21)]], 'F': [[D(2026, 5, 23)]]}, ()),
    27: (5, {'R32': [[D(2025, 12, 17), D(2025, 12, 16), D(2025, 12, 18)]],
             'R16': [[D(2026, 1, 14), D(2026, 1, 13), D(2026, 1, 15)]],
             'QF': [[D(2026, 2, 4), D(2026, 2, 3), D(2026, 2, 5)]],
             'SF': [[D(2026, 3, 4), D(2026, 3, 3), D(2026, 3, 5)]], 'F': [[D(2026, 4, 19)]]}, ()),
    28: (5, {'R32': [[D(2025, 11, 22), D(2025, 11, 21), D(2025, 11, 23)]],
             'R16': [[D(2025, 12, 17), D(2025, 12, 18), D(2025, 12, 23)]],
             'QF': [[D(2026, 1, 14), D(2026, 1, 11)]],
             'SF': [[D(2026, 3, 3), D(2026, 2, 4)], [D(2026, 4, 22), D(2026, 4, 23)]],
             'F': [[D(2026, 5, 24)]]}, ('SF',)),
    53: (5, {'R32': [[D(2025, 10, 29), D(2025, 10, 28), D(2025, 10, 30)]],
             'R16': [[D(2025, 12, 3), D(2025, 12, 2), D(2025, 12, 4)]],
             'QF': [[D(2026, 3, 4), D(2026, 3, 3), D(2026, 3, 5)]],
             'SF': [[D(2026, 4, 8), D(2026, 4, 9)]], 'F': [[D(2026, 5, 2)]]}, ()),
    123: (5, {'R32': [[D(2026, 1, 10), D(2026, 1, 11)]], 'R16': [[D(2026, 2, 4), D(2026, 2, 5)]],
              'QF': [[D(2026, 3, 4), D(2026, 3, 5)]], 'SF': [[D(2026, 4, 22), D(2026, 4, 21)]],
              'F': [[D(2026, 5, 22)]]}, ()),
    125: (5, {'R32': [[D(2025, 10, 29), D(2025, 10, 28), D(2025, 10, 30)]],
              'R16': [[D(2025, 12, 3), D(2025, 12, 2), D(2025, 12, 4)]],
              'QF': [[D(2026, 4, 22), D(2026, 4, 21), D(2026, 4, 23)]],
              'SF': [[D(2026, 5, 6), D(2026, 5, 5), D(2026, 5, 13), D(2026, 5, 14)]],
              'F': [[D(2026, 5, 22)]]}, ()),
    122: (4, {'R16': [[D(2025, 12, 3), D(2025, 12, 2), D(2025, 12, 4)]],
              'QF': [[D(2026, 1, 14), D(2026, 1, 13), D(2026, 1, 15)]],
              'SF': [[D(2026, 2, 4), D(2026, 2, 3), D(2026, 2, 5)], [D(2026, 2, 11), D(2026, 2, 10), D(2026, 2, 12)]],
              'F': [[D(2026, 5, 14)]]}, ('SF',)),
    124: (4, {'R16': [[D(2026, 1, 7), D(2026, 1, 6), D(2026, 1, 8)]],
              'QF': [[D(2026, 1, 14), D(2026, 1, 13), D(2026, 1, 15)]],
              'SF': [[D(2026, 2, 2), D(2026, 2, 3)], [D(2026, 2, 12), D(2026, 2, 11)]],
              'F': [[D(2026, 4, 25)]]}, ('SF',)),
    137: (4, {'R16': [[D(2026, 2, 7), D(2026, 2, 8)]], 'QF': [[D(2026, 3, 7), D(2026, 3, 8)]],
              'SF': [[D(2026, 4, 18), D(2026, 4, 19)]], 'F': [[D(2026, 5, 23)]]}, ()),
    142: (4, {'R16': [[D(2025, 10, 29), D(2025, 10, 28), D(2025, 10, 30)]],
              'QF': [[D(2025, 12, 3), D(2025, 12, 2), D(2025, 12, 4)], [D(2025, 12, 13), D(2025, 12, 14)]],
              'SF': [[D(2026, 2, 11), D(2026, 2, 12)], [D(2026, 3, 7), D(2026, 3, 8)]],
              'F': [[D(2026, 5, 14)]]}, ('QF', 'SF')),
    144: (3, {'QF': [[D(2025, 10, 29), D(2025, 10, 28), D(2025, 10, 30)]],
              'SF': [[D(2026, 1, 6), D(2026, 1, 7)]], 'F': [[D(2026, 1, 10)]]}, ()),
    146: (4, {'R16': [[D(2025, 8, 16), D(2025, 8, 15), D(2025, 8, 17)]],
              'QF': [[D(2025, 9, 20), D(2025, 9, 19), D(2025, 9, 21)]],
              'SF': [[D(2025, 11, 1), D(2025, 11, 2)]], 'F': [[D(2025, 12, 14)]]}, ()),
}
for comp, (rounds, stages, two) in CUPS.items():
    for si in range(rounds - 1, -1, -1):
        stage = STAGES[si]
        legs = stages[stage]
        if stage in two:
            assert len(legs) == 2, (comp, stage)
            add(comp, ('S', stage, 0), dates=legs[0])
            add(comp, ('S', stage, 1), dates=legs[1])
        else:
            add(comp, ('S', stage, 2), dates=legs[0])

# Super cups (single final in FL26's two-club format) and pre-season tournaments.
SUPER = {86: [D(2025, 8, 10)], 88: [D(2025, 8, 16)], 90: [D(2025, 8, 3)], 91: [D(2025, 8, 2)],
         95: [D(2025, 8, 2)], 128: [D(2025, 8, 9), D(2025, 8, 12), D(2025, 8, 13)],
         87: [D(2026, 1, 11)], 89: [D(2025, 12, 22)], 129: [D(2026, 1, 8)], 130: [D(2026, 1, 10)]}
for comp, dates in SUPER.items():
    add(comp, ('S', 'F', 2), dates=dates)
for i, d in enumerate((D(2025, 7, 25), D(2025, 7, 28), D(2025, 7, 31))):   # pre-season tournaments
    add(105, ('R', i), dates=[d], fixed=True)

# -------------------------------------------------------------------- UEFA
def uefa(slug, comp, group_rounds):
    by = fd_rounds(slug)
    for i in range(group_rounds):
        add(comp, ('MD', i), counter=by[str(i + 1)])
    return by


ucl = uefa('champions-league', 3, 8)
uel = uefa('europa-league', 5, 8)
uecl = uefa('conference-league', 77, 6)
for comp, by, final in ((4, ucl, 'Final'), (6, uel, 'Final'), (78, uecl, 'Final')):
    for name, code in (('Play-off', 46), ('R16', 47), ('QF', 51), ('SF', 52)):
        add(comp, ('K', code, 0), counter=by[f'{name} Game 1'])
        add(comp, ('K', code, 1), counter=by[f'{name} Game 2'])
    add(comp, ('K', 53, 2), counter=by[final], fixed=True)      # finals keep their real day
add(2, ('K', 53, 0), dates=[D(2025, 8, 19)], fixed=True)        # UCL play-off (native rows)
add(2, ('K', 53, 1), dates=[D(2025, 8, 26)], fixed=True)
add(7, ('S', 'F', 2), dates=[D(2025, 8, 13)], fixed=True)       # UEFA Super Cup
# Club World Cup: in the summer gap after the club season and before the national
# team tournaments of July (World Cup / EURO), so no club round is ever touched.
add(1, ('K', 46, 2), dates=[D(2026, 6, 10)], fixed=True)
add(1, ('K', 53, 2), dates=[D(2026, 6, 13)], fixed=True)

# ---------------------------------------------------------------- categories
COUNTRY = {   # top division (+ split stages), D2 league (+ play-offs), cups, super cup
    'ENG': ([17], [79, 83], [23, 139], [86]), 'ITA': ([18], [82, 85], [24], [89]),
    'ESP': ([19], [80, 84], [25], [87]), 'GER': ([20], [81], [26], [88]),
    'NED': ([21], [], [27], [90]), 'POR': ([22], [], [28, 144], [91]),
    'POL': ([50], [], [53], [95]), 'FRA': ([116], [], [123], [129]),
    'GRE': ([117], [], [124], []), 'TUR': ([118], [], [125], [130]),
    'BEL': ([155, 156, 159], [], [122], [128]), 'SCO': ([134, 135], [], [137, 146], []),
    'DEN': ([147, 148, 151], [], [142], []),
}
FIRST_ROUND_LOWER = {23, 139, 24, 25, 26}      # code 46 only for the lower division (byes)
EURO = {'UCL': [3, 4, 7, 1], 'UEL': [5, 6, 7], 'UECL': [77, 78], 'none': [],
        # play-off clubs (never the title holders): UCL play-off then UCL or UEL
        'UCLPO': [2, 3, 4], 'UCLPO-UEL': [2, 5, 6]}


def vars_of(comps, top=True):
    out = []
    for c in comps:
        for v in BY_COMP[c]:
            if top and c in FIRST_ROUND_LOWER and v.key[0] == 'S' and v.key[1] == STAGES[CUPS[c][0] - 1]:
                continue
            out.append(v)
    return out


CATS = {}
HOLDER_COUNTRIES = {'ENG', 'ITA', 'ESP', 'GER', 'FRA', 'NED', 'POR'}   # realistic UCL/UEL winners
for cc, (top, d2, cups, sup) in COUNTRY.items():
    for euro, ecomps in EURO.items():
        if cc not in HOLDER_COUNTRIES:
            ecomps = [c for c in ecomps if c != 7]
        CATS[(cc, euro)] = vars_of(top + cups + sup + ecomps)
    if d2:
        CATS[(cc, 'D2')] = vars_of(d2 + cups, top=False)

DAY = [0] * len(VARS)
NEIGH = [set() for _ in VARS]
for members in CATS.values():
    ids = [v.idx for v in members]
    for a in ids:
        NEIGH[a].update(ids)
for i in range(len(VARS)):
    NEIGH[i].discard(i)
NEIGH_L = [sorted(n) for n in NEIGH]
ORDER = []                    # (earlier var, later var) inside a competition
for comp, vs in BY_COMP.items():
    for a, b in zip(vs, vs[1:]):
        ORDER.append((a.idx, b.idx))
BEFORE = collections.defaultdict(list)
AFTER = collections.defaultdict(list)
for a, b in ORDER:
    AFTER[a].append(b)
    BEFORE[b].append(a)


def pair_bad(i, di, j, dj):
    return abs(di - dj) < MIN_GAP


def conflicts(i, d):
    """Violations of variable i if it took ordinal day d (others unchanged)."""
    n = 0
    for j in NEIGH_L[i]:
        if abs(DAY[j] - d) < MIN_GAP:
            n += 1
    for j in BEFORE[i]:
        if DAY[j] >= d:
            n += 1
    for j in AFTER[i]:
        if DAY[j] <= d:
            n += 1
    return n


def set_day(i, k, conf, bad):
    old, new = DAY[i], VARS[i].domain[k][0].toordinal()
    if old == new:
        VARS[i].choice = k
        return
    for j in NEIGH_L[i]:
        delta = (abs(DAY[j] - new) < MIN_GAP) - (abs(DAY[j] - old) < MIN_GAP)
        if delta:
            conf[j] += delta
            conf[i] += delta
            (bad.add if conf[j] else bad.discard)(j)
    for j in BEFORE[i]:
        delta = (DAY[j] >= new) - (DAY[j] >= old)
        if delta:
            conf[j] += delta
            conf[i] += delta
            (bad.add if conf[j] else bad.discard)(j)
    for j in AFTER[i]:
        delta = (DAY[j] <= new) - (DAY[j] <= old)
        if delta:
            conf[j] += delta
            conf[i] += delta
            (bad.add if conf[j] else bad.discard)(j)
    (bad.add if conf[i] else bad.discard)(i)
    DAY[i] = new
    VARS[i].choice = k


def total():
    bad = sum(conflicts(v.idx, DAY[v.idx]) for v in VARS) // 2
    cost = sum(v.domain[v.choice][1] for v in VARS)
    return bad, cost


def solve(steps=400000, seed=1):
    rnd = random.Random(seed)
    for v in VARS:
        DAY[v.idx] = v.day.toordinal()
    conf = [conflicts(v.idx, DAY[v.idx]) for v in VARS]
    bad = {i for i, c in enumerate(conf) if c}
    tabu = collections.deque(maxlen=20)
    for step in range(steps):
        if not bad:
            break
        i = rnd.choice(tuple(bad)) if step % 50 == 0 or len(bad) < 64 else next(iter(bad))
        v = VARS[i]
        if len(v.domain) == 1:
            if rnd.random() < 0.9:
                # move a neighbour instead
                cand = [j for j in NEIGH_L[i] if abs(DAY[j] - DAY[i]) < MIN_GAP and len(VARS[j].domain) > 1]
                if not cand:
                    continue
                i = rnd.choice(cand)
                v = VARS[i]
            else:
                continue
        options = []
        for k, (d, cost) in enumerate(v.domain):
            if (i, k) in tabu and k != v.choice:
                continue
            options.append((conflicts(i, d.toordinal()) * 100 + cost + rnd.random() * 0.9, k))
        if not options:
            continue
        options.sort()
        pick = options[0][1] if rnd.random() > 0.08 else rnd.choice(options)[1]
        set_day(i, pick, conf, bad)
        tabu.append((i, pick))
    # cost polish: cheaper days that keep zero conflicts
    for _ in range(3):
        for v in VARS:
            for k, (d, cost) in sorted(enumerate(v.domain), key=lambda kv: kv[1][1]):
                if cost >= v.domain[v.choice][1]:
                    break
                if conflicts(v.idx, d.toordinal()) == 0 and conf[v.idx] == 0:
                    set_day(v.idx, k, conf, bad)
                    break
    return bad


def improve(rounds=6):
    """Ejection chains: move a round to a cheaper day and re-place the (at most two)
    rounds it would clash with, if the total cost drops and nothing clashes."""
    conf = [conflicts(v.idx, DAY[v.idx]) for v in VARS]
    bad = {i for i, c in enumerate(conf) if c}
    assert not bad
    cost = lambda v: v.domain[v.choice][1]
    for _ in range(rounds):
        gained = 0
        for v in VARS:
            here = cost(v)
            for k, (d, c) in sorted(enumerate(v.domain), key=lambda kv: kv[1][1]):
                if c >= here:
                    break
                dn = d.toordinal()
                clash = [j for j in NEIGH_L[v.idx] if abs(DAY[j] - dn) < MIN_GAP]
                clash += [j for j in BEFORE[v.idx] if DAY[j] >= dn] + [j for j in AFTER[v.idx] if DAY[j] <= dn]
                if len(clash) > 2:
                    continue
                old_v = v.choice
                set_day(v.idx, k, conf, bad)
                saved = [(j, VARS[j].choice) for j in clash]
                extra, ok = 0, True
                for j in clash:
                    u = VARS[j]
                    best = None
                    for ku, (du, cu) in enumerate(u.domain):
                        if conflicts(j, du.toordinal()) == 0 and (best is None or cu < best[0]):
                            best = (cu, ku)
                    if best is None:
                        ok = False
                        break
                    extra += best[0] - cost(u)
                    set_day(j, best[1], conf, bad)
                if ok and not bad and c - here + extra < 0:
                    gained += here - c - extra
                    break
                for j, ku in reversed(saved):       # undo
                    set_day(j, ku, conf, bad)
                set_day(v.idx, old_v, conf, bad)
        if not gained:
            break
    return sum(cost(v) for v in VARS)


def anneal(steps=1500000, seed=1, t0=60.0, t1=0.3, w=50):
    """Lower the total cost while keeping zero conflicts at the end (best kept)."""
    import math
    rnd = random.Random(seed)
    conf = [conflicts(v.idx, DAY[v.idx]) for v in VARS]
    bad = {i for i, c in enumerate(conf) if c}
    cur = sum(conf) // 2 * w + sum(v.domain[v.choice][1] for v in VARS)
    best = (cur, [v.choice for v in VARS]) if not bad else None
    movable = [v for v in VARS if len(v.domain) > 1]
    for step in range(steps):
        t = t0 * (t1 / t0) ** (step / steps)
        v = rnd.choice(movable)
        k = rnd.randrange(len(v.domain))
        if k == v.choice:
            continue
        i = v.idx
        d_new = v.domain[k][0].toordinal()
        delta = (conflicts(i, d_new) - conf[i]) * w + v.domain[k][1] - v.domain[v.choice][1]
        if delta <= 0 or rnd.random() < math.exp(-delta / t):
            set_day(i, k, conf, bad)
            cur += delta
            if not bad and (best is None or cur < best[0]):
                best = (cur, [w.choice for w in VARS])
    if best:
        for v, k in zip(VARS, best[1]):
            v.choice = k
            DAY[v.idx] = v.day.toordinal()
    return best



# ------------------------------------------------------------ C header
LEAGUE_TEAMS = {17: 20, 79: 24, 18: 20, 82: 20, 19: 20, 80: 22, 20: 18, 81: 22, 21: 18, 22: 18,
                116: 18, 118: 18, 117: 14, 155: 16, 134: 12, 50: 18, 147: 12,
                148: 6, 175: 6, 156: 4, 172: 4, 135: 6, 136: 6, 105: 4, 106: 4, 107: 4}
TEAMS_IN = {'F': 2, 'SF': 4, 'QF': 8, 'R16': 16, 'R32': 32, 'R64': 64, 'R128': 128}


def write_header(rows):
    def day_of(comp, key):
        for r in rows[comp]:
            if tuple(r['key']) == key:
                return r['doy']
        raise KeyError((comp, key))
    out = ['// Generated by calendar/build_calendar.py from calendar.json - do not edit.',
           '// Days are day-of-year (0 = 1 January) of the 2025/26 real calendar, adjusted so',
           '// that every club has at least %d days between two matches.' % MIN_GAP, '',
           'struct CalLeague { uint16_t comp; uint8_t teams; uint8_t rounds; uint16_t day[46]; };',
           'struct CalRow { uint16_t comp; uint16_t day; uint8_t code; uint8_t leg; };',
           'struct CalStage { uint16_t comp; uint8_t teams; uint8_t two_legged; uint16_t day[2]; };', '']
    out.append('static const CalLeague kCalLeagues[] = {')
    for comp, teams in LEAGUE_TEAMS.items():
        base = ALIAS.get(comp, comp)
        days = [r['doy'] for r in rows[base] if r['key'][0] == 'R']
        out.append(f'    {{{comp}, {teams}, {len(days)}, {{{", ".join(map(str, days))}}}}},')
    out.append('};')
    out.append('static const CalRow kCalRows[] = {')
    for comp in (3, 5, 77):                                  # league phases: code = matchday
        for r in rows[comp]:
            out.append(f'    {{{comp}, {r["doy"]}, {r["key"][1]}, 2}},')
    for comp in (4, 6, 78, 83, 84, 85, 2, 1):
        for r in rows[comp]:
            out.append(f'    {{{comp}, {r["doy"]}, {r["key"][1]}, {r["key"][2]}}},')
    out.append(f'    {{1, {day_of(1, ("K", 53, 2))}, 54, 2}},           // third place, final day')
    for comp in (151, 159):
        out.append(f'    {{{comp}, {day_of(comp, ("C", 53, 2))}, 53, 2}},')
    for comp in list(SUPER) + [7]:
        out.append(f'    {{{comp}, {day_of(comp, ("S", "F", 2))}, 53, 2}},')
    out.append('};')
    out.append('static const CalStage kCalStages[] = {')
    for comp, (rounds, stages, two) in CUPS.items():
        for stage in STAGES[:rounds]:
            if stage in two:
                d0, d1 = day_of(comp, ('S', stage, 0)), day_of(comp, ('S', stage, 1))
                out.append(f'    {{{comp}, {TEAMS_IN[stage]}, 1, {{{d0}, {d1}}}}},')
            else:
                d = day_of(comp, ('S', stage, 2))
                out.append(f'    {{{comp}, {TEAMS_IN[stage]}, 0, {{{d}, {d}}}}},')
    out.append('};')
    out.append('// Competitions whose matches are single (super cups, European play-off finals).')
    out.append('static const uint16_t kCalSingle[] = {%s};' % ', '.join(map(str, list(SUPER) + [7, 151, 159, 1])))
    (HERE.parent / 'euro_calendar.h').write_text(chr(10).join(out) + chr(10), encoding='utf-8')


def main():
    best = None
    for attempt in range(6):
        bad = [VARS[i] for i in solve(seed=attempt + 1)]
        print(f'attempt {attempt}: {len(bad)} rounds in conflict, cost {total()[1]}')
        score = (len(bad), total()[1])
        if best is None or score < best[0]:
            best = (score, [v.choice for v in VARS])
        if not bad:
            got = improve()
            print(f'  ejection chains: cost {got}')
            best = ((0, got), [v.choice for v in VARS])
            break
        for v in bad:                       # widen what does not fit, then retry
            if v.flex:
                v.widen(min(v.flex, attempt + 1))
            for j in NEIGH_L[v.idx]:
                if VARS[j].flex and abs((VARS[j].day - v.day).days) < MIN_GAP:
                    VARS[j].widen(min(VARS[j].flex, attempt + 1))
    for v, k in zip(VARS, best[1]):
        v.choice = k
        DAY[v.idx] = v.day.toordinal()
    bad = [v for v in VARS if conflicts(v.idx, DAY[v.idx])]
    moved = [v for v in VARS if v.day not in v.realset]
    report = {'conflicts': [repr(v) for v in bad],
              'moved_from_real': [f'{v.comp}:{v.key} {v.real} -> {v.day}' for v in moved]}
    rows = collections.defaultdict(list)
    for v in VARS:
        rows[v.comp].append({'key': list(v.key), 'date': v.day.isoformat(), 'real': v.real.isoformat(),
                             'doy': doy(v.day)})
    for alias, base in ALIAS.items():
        rows[alias] = rows[base]
    out = {'season': '2025/26', 'min_gap': MIN_GAP, 'report': report,
           'cups': {c: {'rounds': r, 'two_legged': list(t)} for c, (r, _, t) in CUPS.items()},
           'rows': rows}
    (HERE / 'calendar.json').write_text(json.dumps(out, indent=1), encoding='utf-8')
    if not bad:
        write_header(rows)
    print(f'{len(VARS)} rounds; conflicts {len(bad)}; moved from their real days {len(moved)}')
    for line in report['conflicts'][:40]:
        print('  CONFLICT', line)
    for line in report['moved_from_real'][:60]:
        print('  moved', line)
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
