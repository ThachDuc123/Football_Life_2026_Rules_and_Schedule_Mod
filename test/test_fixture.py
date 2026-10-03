"""Offline test for repair_ucl_fixture.py on the real native fixture from ucl32_probe.log."""
import re
import struct
import sys
from collections import Counter, defaultdict
from pathlib import Path

GUARD = Path(r'D:\FL26\SiderAddons\content\ucl_calendar_guard')
sys.path.insert(0, str(GUARD))
from audit_native_knockout import EVENT, team  # noqa: E402
from repair_ucl_fixture import country_map, league_matches, make_fixture_plan, valid_draw  # noqa: E402

probe = []
for line in Path(r'D:\FL26\ucl32_probe.log').read_text(encoding='utf-8', errors='replace').splitlines():
    m = re.search(r'\| EV eid=(\d+) sub=0x([0-9A-F]+) grupo=(\d+) code=(\d+) leg=(\d+) '
                  r'home=0x([0-9A-F]+)/t\d+ away=0x([0-9A-F]+)/t\d+', line)
    if m:
        eid, sub, group, code, leg, home, away = m.groups()
        probe.append((int(eid), int(sub, 16), int(group), int(code), int(leg), int(home, 16), int(away, 16)))
assert len(probe) == 96

failures = 0


def check(cond, msg):
    global failures
    if not cond:
        failures += 1
        print('  FAIL:', msg)


def build(replace=None, played_first=False):
    events = bytearray(b'\xff' * (13000 * 0x254))
    calendar = bytearray(0x6CD00)
    for day in range(365):
        struct.pack_into('<280H', calendar, day * 0x2C4, *([0xFFFF] * 280))
    struct.pack_into('<HHH', calendar, 0x3F174, 200, 2026, 365)
    slots = defaultdict(int)
    for i, (eid, sub, _, code, leg, home, away) in enumerate(probe):
        if replace:
            home = replace[1] if home == replace[0] else home
            away = replace[1] if away == replace[0] else away
        pos = eid * 0x254
        events[pos:pos + 0x254] = bytes(0x254)
        packed = sub | code << 16 | leg << 28 | (0x40000000 if played_first and i == 0 else 0)
        struct.pack_into('<HHI', events, pos, eid, 0, packed)
        struct.pack_into('<II', events, pos + 20, home, away)
        day = 250 + 14 * code
        struct.pack_into('<H', calendar, day * 0x2C4 + 2 * slots[day], eid)
        slots[day] += 1
    return events, calendar


def verify(events):
    matches = league_matches(events)
    check(valid_draw(matches), 'valid_draw rechaza el resultado')
    opp, rounds = defaultdict(set), defaultdict(Counter)
    for _, code, h, a, _ in matches:
        h, a = team(h), team(a)
        opp[h].add(a); opp[a].add(h)
        rounds[h][code] += 1; rounds[a][code] += 1
    check(len(opp) == 32 and all(len(v) == 6 for v in opp.values()), '6 rivales distintos')
    check(all(set(c.values()) == {1} and len(c) == 6 for c in rounds.values()), '1 partido por jornada')
    return matches


def apply(events, patches):
    out = bytearray(events)
    for offset, before, after in patches:
        at = offset - EVENT
        check(out[at:at + len(before)] == before, 'before no coincide')
        out[at:at + len(after)] = after
    return out


print('P1 fixture nativo real con Pafos t9504 (ahora en countries.json)')
events, calendar = build()
countries = country_map(events, GUARD)
patches, details = make_fixture_plan(events, calendar, countries)
print('  ', {k: details[k] for k in ('status', 'same_country', 'synthetic_country')}, len(patches), 'parches')
check(details['same_country'] == 0 and details['synthetic_country'] == [], 'P1 detalles')
matches = verify(apply(events, patches))
print('   Pafos:', sorted(team(a) if team(h) == 9504 else team(h)
                          for _, _, h, a, _ in matches if 9504 in (team(h), team(a))))

print('P2 club desconocido t9876 (sin pais en ninguna fuente)')
events, calendar = build(replace=(0x09480202, (9876 << 14) | 0x202))
patches, details = make_fixture_plan(events, calendar, country_map(events, GUARD))
print('  ', {k: details[k] for k in ('status', 'same_country', 'synthetic_country')})
check(details['synthetic_country'] == [9876], 'P2 pais sintetico')
verify(apply(events, patches))

print('P3 un partido jugado: se conserva')
events, calendar = build(played_first=True)
patches, details = make_fixture_plan(events, calendar, country_map(events, GUARD))
print('  ', details['status'])
check(details['status'] == 'blocked-played' and not patches, 'P3')

print('P4 ya aplicado: no se reescribe')
events, calendar = build()
patches, _ = make_fixture_plan(events, calendar, country_map(events, GUARD))
fixed = apply(events, patches)
patches2, details2 = make_fixture_plan(fixed, calendar, country_map(fixed, GUARD))
print('  ', details2['status'])
check(details2['status'] == 'six-distinct-opponents' and not patches2, 'P4')

print('\nRESULTADO:', 'todo OK' if not failures else f'{failures} fallos')
sys.exit(1 if failures else 0)
