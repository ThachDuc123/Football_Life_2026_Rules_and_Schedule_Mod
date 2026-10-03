"""Offline test of the knockout steps added to repair_ucl_calendar.py.

Builds a native-shaped state (Competition, Round, Event, Calendar) from a real
save's league phase plus a 24-club UCL knockout laid out the way ucl32_c41 and
the native bracket do it (play-off tie k = slots 3k+1 v 3k+2, round-of-16 tie
k = slot 3k v winner of play-off k), then checks:
  * bracket_report finds the bracket euro_rules.dll would have written;
  * make_leg_order_plan swaps exactly the ties whose better club hosted leg 1,
    and a second pass finds nothing left to do;
  * after the patches every second leg is hosted by the better-placed club.
Usage: python test_guard.py <ML save with a finished league phase> <season year>
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, r'D:\FL26\SiderAddons\content\ucl_calendar_guard')
import euro_rules as er  # noqa: E402
import repair_ucl_calendar as guard  # noqa: E402
from audit_native_knockout import COMP, ROUND, EVENT, CALENDAR, decode_tables  # noqa: E402
from export_events import events_from_save  # noqa: E402

STRIDE = 0x254


def build_state(events, year):
    rows, unplayed = er.league_table(events, 3)
    assert len(rows) == 32 and not unplayed
    order = er.ranked(rows)
    enc = {r['id']: r['encoded'] for r in rows}
    ids = [r['id'] for r in order]
    ties = er.build_bracket(er.draw_seed(year, ids[:24]))
    events = bytearray(events)
    comps = bytearray(300 * 0x314)
    rounds = bytearray(b'\xff' * (2000 * 0x208))
    calendar = bytearray(0x6CD00)
    for day in range(365):
        struct.pack_into('<280H', calendar, day * 0x2C4, *([0xFFFF] * 280))
    struct.pack_into('<HHH', calendar, 0x3F174, 40, year + 1, 365)
    free = [i for i in range(13000) if struct.unpack_from('<H', events, i * STRIDE)[0] != i]
    days = {}

    def new_event(code, leg, home, away, day, played=False, hg=0, ag=0):
        eid = free.pop(0)
        rec = bytearray(STRIDE)
        packed = 4 | (code << 16) | (leg << 28) | (0x40000000 if played else 0)
        struct.pack_into('<HHI', rec, 0, eid, 0, packed)
        rec[8:12] = guard.date_bytes(year + 1, day)
        struct.pack_into('<II', rec, 0x14, home, away)
        rec[0x1C], rec[0x1F] = hg, ag
        events[eid * STRIDE:(eid + 1) * STRIDE] = rec
        days.setdefault(day, []).append(eid)
        return eid

    def new_round(rid, code, pairs):
        rec = bytearray(b'\xff' * 0x208)
        struct.pack_into('<H', rec, 0, 4)
        struct.pack_into('<I', rec, 0x204, (code << 26) | len(pairs))
        for slot, (a, b, evs) in enumerate(pairs):
            struct.pack_into('<II', rec, 4 + slot * 0x20, a, b)
            struct.pack_into('<HH', rec, 4 + slot * 0x20 + 8, *(evs + [0xFFFF] * (2 - len(evs))))
        rounds[rid * 0x208:(rid + 1) * 0x208] = rec

    undecided = 0x3FFFF << 14
    po, r16 = [], []
    for k, (s, h, a) in enumerate(ties):
        home, away = enc[ids[h]], enc[ids[a]]
        e0 = new_event(46, 0, home, away, 46, True, 1, 0)       # unseeded wins leg 1 1-0
        e1 = new_event(46, 1, away, home, 53, True, 2, 0)       # seeded wins leg 2 2-0
        po.append((home, away, [e0, e1]))
        seed = enc[ids[s]]
        f0 = new_event(47, 0, seed, away, 67)                   # native: first team hosts leg 1
        f1 = new_event(47, 1, away, seed, 74)
        r16.append((seed, away, [f0, f1]))
    new_round(10, 46, po)
    new_round(11, 47, r16)
    qf = [(undecided, undecided, [new_event(51, 0, undecided, undecided, 95),
                                  new_event(51, 1, undecided, undecided, 102)]) for _ in range(4)]
    new_round(12, 51, qf)
    sf = [(undecided, undecided, [new_event(52, 0, undecided, undecided, 116),
                                  new_event(52, 1, undecided, undecided, 123)]) for _ in range(2)]
    new_round(13, 52, sf)
    new_round(14, 53, [(undecided, undecided, [new_event(53, 2, undecided, undecided, 149)])])
    for day, eids in days.items():
        lst = eids + [0xFFFF] * (280 - len(eids))
        struct.pack_into('<280H', calendar, day * 0x2C4, *lst)
        struct.pack_into('<H', calendar, day * 0x2C4 + 0x230, len(eids))
    struct.pack_into('<H', comps, 0, 4)
    struct.pack_into('<I', comps, 0x308, 24 << 16)
    struct.pack_into('<I', comps, 0x300, 5 << 19)
    slots = [10, 11, 12, 13, 14] + [-1] * 53
    struct.pack_into('<58i', comps, 0x88, *slots)
    for i, (s, h, a) in enumerate(ties):
        struct.pack_into('<III', comps, 0x170 + i * 12, enc[ids[s]], enc[ids[h]], enc[ids[a]])
    return [bytes(comps), bytes(rounds), bytes(events), bytes(calendar)], ids, ties


def apply(state, patches):
    bases = {COMP: 0, ROUND: 1, EVENT: 2, CALENDAR: 3}
    out = [bytearray(x) for x in state]
    for offset, before, after in patches:
        base = max(b for b in bases if b <= offset)
        buf, at = out[bases[base]], offset - base
        assert buf[at:at + len(before)] == before, hex(offset)
        buf[at:at + len(after)] = after
    return [bytes(x) for x in out]


def main():
    events, clubs = events_from_save(Path(sys.argv[1]))
    year = int(sys.argv[2])
    state, ids, ties = build_state(events, year)
    pos = {t: i + 1 for i, t in enumerate(ids)}
    rep = guard.bracket_report(*state)
    assert rep and rep['status'] == 'as-expected', rep
    print('bracket_report:', rep['status'])
    patches, changes = guard.make_leg_order_plan(*state)
    print('leg-order changes:', len(changes), [(c['code'], c['slot'], c['position'], c['opponent_position']) for c in changes])
    assert len(changes) == 8 and all(c['code'] == 47 for c in changes), changes
    state2 = apply(state, patches)
    again, _ = guard.make_leg_order_plan(*state2)
    assert not again, again
    audit = decode_tables(*state2, wanted=(4,))
    for r in audit['competitions'][0]['rounds'][:2]:
        for tie in r['ties']:
            legs = {e['leg']: e for e in tie['events']}
            host2 = legs[1]['home']
            other = legs[1]['away']
            assert pos[host2] < pos[other], (r['code'], tie['slot'], pos[host2], pos[other])
            assert tie['teams'] == [legs[0]['home'], legs[0]['away']]
    print('every play-off and round-of-16 second leg is hosted by the better club')
    rep2 = guard.bracket_report(*state2)
    assert rep2['status'] == 'as-expected', rep2
    nm = lambda t: clubs[t].name if t in clubs else t
    for k, (s, h, a) in enumerate(ties):
        print(f"  R16-{k + 1}: {pos[ids[s]]}. {nm(ids[s])} v winner of {h + 1}. {nm(ids[h])} / {a + 1}. {nm(ids[a])}")
    print('OK')


if __name__ == '__main__':
    main()
