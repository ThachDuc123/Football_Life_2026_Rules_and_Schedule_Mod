"""Pure, transactional plans for the validated FL26 32-club/six-match format."""
import json
import random
import struct
from collections import Counter, defaultdict
from pathlib import Path

from audit_native_knockout import EVENT, team, u16, u32


def league_matches(events):
    matches = []
    for eid in range(len(events) // 0x254):
        pos = eid * 0x254
        packed = u32(events, pos + 4)
        if u16(events, pos) == eid and packed & 0x3FF == 3:
            home, away = struct.unpack_from('<II', events, pos + 20)
            matches.append((eid, (packed >> 16) & 0xFFF, home, away,
                            bool(packed & 0x40000000)))
    return sorted(matches, key=lambda m: (m[1], m[0]))


def valid_draw(matches):
    opponents, rounds = defaultdict(set), defaultdict(list)
    homes, aways = Counter(), Counter()
    for _, code, h, a, _ in matches:
        h, a = team(h), team(a)
        if h is None or a is None or h == a or a in opponents[h]:
            return False
        opponents[h].add(a)
        opponents[a].add(h)
        rounds[code].extend((h, a))
        homes[h] += 1
        aways[a] += 1
    clubs = set(opponents)
    return (len(matches) == 96 and len(clubs) == 32 and set(rounds) == set(range(6))
            and all(len(r) == 32 and set(r) == clubs for r in rounds.values())
            and all(len(opponents[c]) == 6 and homes[c] == aways[c] == 3 for c in clubs))


def country_map(events, directory):
    directory = Path(directory)
    mapped = {int(k): int(v) for k, v in json.loads(
        (directory / 'countries.json').read_text(encoding='utf-8')).items()}
    domestic = {17,18,19,20,21,22,50,79,80,81,82,115,116,117,118,133,141,162}
    canonical = {79:17,80:19,81:20,82:18}
    observed = defaultdict(set)
    for eid in range(len(events) // 0x254):
        pos = eid * 0x254
        stage = u32(events, pos + 4) & 0x3FF
        if u16(events, pos) != eid or stage not in domestic:
            continue
        for side in (20,24):
            club = team(u32(events, pos + side))
            if club is not None:
                observed[club].add(canonical.get(stage, stage))
    for club, countries in observed.items():
        if len(countries) == 1:
            mapped[club] = next(iter(countries))
    exported = directory / 'countries-runtime.tsv'
    if exported.exists():
        for line in exported.read_text(encoding='ascii').splitlines():
            club, country = map(int, line.split())
            if club <= 0 or country <= 0:
                raise ValueError('Mapa de paises invalido')
            mapped[club] = country
    return mapped


def draw(clubs, countries, year):
    seed = year
    for club in clubs:
        seed = (seed * 16777619 ^ club) & 0xFFFFFFFF
    rng = random.Random(seed)
    for _ in range(4096):
        rotation = list(clubs)
        rng.shuffle(rotation)
        edges = []
        for _ in range(31):
            pairs = [(rotation[i], rotation[31-i]) for i in range(16)]
            if all(countries[a] != countries[b] for a,b in pairs):
                edges.extend(pairs)
                if len(edges) == 96:
                    break
            rotation = [rotation[0], rotation[-1], *rotation[1:-1]]
        if len(edges) != 96:
            continue
        # Orient each Euler circuit: every vertex has three incoming/outgoing edges.
        used, oriented = set(), [None] * 96
        for start in clubs:
            stack = [start]
            while stack:
                v = stack[-1]
                index = next((i for i,(a,b) in enumerate(edges)
                              if i not in used and v in (a,b)), None)
                if index is None:
                    stack.pop()
                    continue
                a,b = edges[index]
                other = b if a == v else a
                used.add(index)
                oriented[index] = (v, other)
                stack.append(other)
        return oriented
    raise ValueError('No se encontro un sorteo sin cruces del mismo pais')


def make_fixture_plan(events, calendar, countries):
    matches = league_matches(events)
    if not matches:
        return [], {'status': 'no-league'}
    if valid_draw(matches):
        return [], {'status': 'six-distinct-opponents', 'matches': 96}
    if any(m[4] for m in matches):
        return [], {'status': 'blocked-played', 'message':
                    'Calendario antiguo con partidos jugados: se conserva. Prueba desde antes de J1 o en una nueva temporada.'}
    if len(matches) != 96 or Counter(m[1] for m in matches) != {i:16 for i in range(6)}:
        raise ValueError('Fase liga incompleta: se esperan 96 eventos y seis jornadas')
    encodings = defaultdict(set)
    for _,_,h,a,_ in matches:
        for raw in (h,a):
            encodings[team(raw)].add(raw)
    if None in encodings or len(encodings) != 32 or any(len(v) != 1 for v in encodings.values()):
        raise ValueError('Los 32 participantes no tienen codificacion unica')
    clubs = sorted(encodings)
    missing = [c for c in clubs if not countries.get(c)]
    if missing:
        raise ValueError('Pais desconocido para clubes: ' + str(missing))
    current, year, days = struct.unpack_from('<HHH', calendar, 0x3F174)
    if days != 365 or current >= days:
        raise ValueError('Calendario nativo invalido')
    # Every round must already exist on one future day, with unique membership.
    membership = defaultdict(list)
    for day in range(365):
        for eid in struct.unpack_from('<280H', calendar, day * 0x2C4):
            if eid != 0xFFFF:
                membership[eid].append(day)
    round_days = defaultdict(set)
    for eid,code,_,_,_ in matches:
        dates = membership[eid]
        if len(dates) != 1 or dates[0] < current:
            raise ValueError('UCL sin fecha futura unica; se espera a completar el calendario')
        round_days[code].add(dates[0])
    if any(len(v) != 1 for v in round_days.values()):
        raise ValueError('Una jornada UCL ocupa varios dias')
    oriented = draw(clubs, countries, year)
    changed = bytearray(events)
    patches = []
    for (eid,_,_,_,_), (h,a) in zip(matches, oriented):
        pos = eid * 0x254 + 20
        value = struct.pack('<II', next(iter(encodings[h])), next(iter(encodings[a])))
        if events[pos:pos+8] != value:
            patches.append((EVENT+pos, bytes(events[pos:pos+8]), value))
            changed[pos:pos+8] = value
    if not valid_draw(league_matches(changed)):
        raise ValueError('El sorteo calculado no supera sus invariantes')
    return patches, {'status': 'repaired-six-distinct-opponents', 'matches':96,
                     'clubs':32, 'home':3, 'away':3, 'same_country':0}
