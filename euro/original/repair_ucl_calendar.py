"""Repair native UCL Event dates and Calendar membership; never edit game saves.

Default is a read-only plan. --apply pauses the process briefly, rechecks the
entire input, writes only changed fields and verifies them before resuming.
Existing matches, results, Round links and the current date are preserved.
"""
from __future__ import annotations

import argparse
import ctypes as ct
import datetime as dt
import json
import struct
from pathlib import Path

from audit_native_knockout import BASE, COMP, ROUND, EVENT, CALENDAR, Reader, decode_tables, team, u16, u32
from repair_ucl_group_menu import make_group_menu_plan
from repair_ucl_fixture import make_fixture_plan, country_map, league_matches

SIZES = ((COMP, 300 * 0x314), (ROUND, 2000 * 0x208),
         (EVENT, 13000 * 0x254), (CALENDAR, 0x6CD00))
STAGES = ((47, 0), (47, 1), (51, 0), (51, 1), (52, 0), (52, 1), (53, 2))


def make_personal_schedule_plan(events, calendar):
    """Repair only future UCL group references in the native club day cache.

    Calendar+3F180 contains 32 agendas: header[8], 365 records[16], count[4].
    Each record is {u16 event, u16 competition, u32 round, u32 leg, u32 club}.
    Event/Calendar remain authoritative; never rewrite fixtures or results.
    """
    current, year, count = struct.unpack_from('<HHH', calendar, 0x3F174)
    if count != 365 or current >= 365 or len(calendar) != 0x6CD00:
        raise ValueError('Personal schedule: invalid Calendar')
    patches, details = [], []
    empty = struct.pack('<HHIII', 0xFFFF, 0xFFFF, 55, 3, 0xFFFFFFFF)
    for slot in range(32):
        base = 0x3F180 + slot * 0x16DC
        encoded = u32(calendar, base + 4)
        club = team(encoded)
        if club is None:
            continue
        if u16(calendar, base + 0x16D8) != 365:
            raise ValueError('Personal schedule: invalid agenda length')
        for day in range(current, 365):
            pos = base + 8 + day * 16
            old = calendar[pos:pos + 16]
            old_id, old_comp = struct.unpack_from('<HH', old)
            candidates = []
            for eid in struct.unpack_from('<280H', calendar, day * 0x2C4):
                if eid == 0xFFFF:
                    continue
                evpos = eid * 0x254
                if eid >= 13000 or u16(events, evpos) != eid:
                    raise ValueError('Personal schedule: invalid Event reference')
                packed = u32(events, evpos + 4)
                if packed & 0x3FF != 3 or packed & 0x40000000:
                    continue
                sides = (u32(events, evpos + 20), u32(events, evpos + 24))
                if encoded not in sides:
                    continue
                if events[evpos + 8:evpos + 12] != date_bytes(year, day):
                    raise ValueError('Personal schedule: Event date differs from Calendar')
                candidates.append((eid, packed))
            if len(candidates) > 1:
                raise ValueError('Personal schedule: ambiguous club fixture')
            if not candidates:
                continue
            eid, packed = candidates[0]
            wanted = struct.pack('<HHIII', eid, packed & 0xFFFF,
                                 (packed >> 16) & 0xFFF, (packed >> 28) & 3, encoded)
            if old == wanted:
                continue
            if old != empty and old_comp & 0x3FF != 3:
                raise ValueError('Personal schedule: another activity occupies the day')
            patches.append((CALENDAR + pos, old, wanted))
            details.append({'club': club, 'day': day, 'before_event': old_id,
                            'after_event': eid})
    return patches, details


def schedule_compliant(state):
    """Read-only automatic gate: never shift a valid schedule as days advance."""
    comps, rounds, events, calendar = state
    audit = decode_tables(comps, rounds, events, calendar, wanted=(4,))
    if audit['calendar_errors'] or len(audit['competitions']) != 1:
        return False
    competition = audit['competitions'][0]
    rs = competition['rounds']
    if [r.get('code') for r in rs] != [46, 47, 51, 52, 53]:
        return False
    stage_days = {}
    entries = [e for r in rs[1:] for t in r['ties'] for e in t['events']]
    if len(entries) != 29 or any('error' in e for e in entries):
        return False
    clubs = {club for t in rs[1]['ties'] for club in t['teams'] if club is not None}
    if len(clubs) != 16:
        return False
    ids = {e['id'] for e in entries}
    for e in entries:
        if len(e['days']) != 1:
            return False
        day = e['days'][0]
        if e['date_raw'] != date_bytes(audit['calendar']['year'], day).hex():
            return False
        key = (e['code'], e['leg'])
        if key in stage_days and stage_days[key] != day:
            return False
        stage_days[key] = day
    if set(stage_days) != set(STAGES):
        return False
    ordered = [stage_days[key] for key in STAGES]
    if ordered[-1] != 149 or any(b - a < 7 for a, b in zip(ordered, ordered[1:])):
        return False
    playoff_days = [day for tie in rs[0]['ties'] for e in tie['events'] for day in e['days']]
    if not playoff_days or ordered[0] - max(playoff_days) < 7:
        return False
    for day in ordered:
        for near in range(max(0, day - 2), min(365, day + 3)):
            for eid in struct.unpack_from('<280H', calendar, near * 0x2C4):
                if eid == 0xFFFF or eid in ids:
                    continue
                if eid >= 13000 or u16(events, eid * 0x254) != eid:
                    return False
                pos = eid * 0x254
                if clubs & {team(u32(events, pos + 0x14)), team(u32(events, pos + 0x18))}:
                    return False
    return True


def date_bytes(year, day):
    # PES always uses a 365-day calendar, including leap years.
    date = dt.date(2025, 1, 1) + dt.timedelta(days=day)
    return struct.pack('<HBB', year, date.month, date.day)


def choose_days(current, blocked, capacity, counts, last=150, final_day=None):
    """Require a week between UCL dates and optionally pin the native final.

    Never compress the knockout schedule to make a late recovery fit.
    """
    def visit(chosen):
        if len(chosen) == len(counts):
            return chosen
        start = chosen[-1] + 7 if chosen else current + 1
        finish = final_day if final_day is not None else last
        finish -= 7 * (len(counts) - len(chosen) - 1)
        candidates = (range(start, finish + 1) if final_day is None or
                      len(chosen) != len(counts) - 1 else [final_day])
        for day in candidates:
            if day < start or day > last:
                continue
            if day in blocked or capacity[day] < counts[len(chosen)]:
                continue
            result = visit(chosen + [day])
            if result:
                return result
        return None
    result = visit([])
    if result is None:
        raise ValueError('No caben las fechas con siete días de separación antes de junio; se requiere un punto anterior de la carrera')
    return result


def make_plan(comps, rounds, events, calendar):
    audit = decode_tables(comps, rounds, events, calendar, wanted=(4,))
    if audit['calendar_errors'] or len(audit['competitions']) != 1:
        raise ValueError('Calendario inconsistente o competición UCL ambigua')
    c = audit['competitions'][0]
    if c['actual'] != 24 or c['round_count'] != 5:
        raise ValueError('Se requiere el cuadro nativo de 24 clubes y cinco rondas')
    rs = c['rounds']
    if [r['code'] for r in rs] != [46, 47, 51, 52, 53]:
        raise ValueError('Cadena de rondas inesperada')
    if [r['tie_count'] for r in rs] != [8, 8, 4, 2, 1]:
        raise ValueError('Número de cruces inesperado')
    if c['unreferenced_events']:
        raise ValueError('Hay eventos UCL ajenos al cuadro')
    for r in rs:
        # Round+0 is its competition ID, not its index in Round[].
        if r['record_id'] != c['id']:
            raise ValueError('La ronda no pertenece a UCL')
        for tie in r['ties']:
            expected = [2] if r['code'] == 53 else [0, 1]
            if sorted(e.get('leg', -1) for e in tie['events']) != expected:
                raise ValueError('Ida/vuelta incompleta')
            for e in tie['events']:
                if e.get('competition') != 4 or e.get('code') != r['code']:
                    raise ValueError('Evento no pertenece a su ronda')
    if not all(e['played'] for t in rs[0]['ties'] for e in t['events']):
        raise ValueError('El playoff aún no está terminado')
    remaining = [e for r in rs[1:] for t in r['ties'] for e in t['events']]
    if any(e['played'] for e in remaining):
        raise ValueError('No se reprograman rondas que ya tienen resultados')
    clubs = [club for tie in rs[1]['ties'] for club in tie['teams']]
    if None in clubs or len(set(clubs)) != 16:
        raise ValueError('Octavos no tiene sus dieciséis clasificados únicos')
    for tie in rs[1]['ties']:
        for e in tie['events']:
            expected = tie['teams'] if e['leg'] == 0 else tie['teams'][::-1]
            if [e['home'], e['away']] != expected:
                raise ValueError('Los rivales del evento no coinciden con el cruce')
    ids = {e['id'] for e in remaining}
    if len(ids) != 29:
        raise ValueError('Eventos duplicados o incompletos')
    blocked, reasons, capacity = set(), {}, {}
    for day in range(365):
        day_ids = struct.unpack_from('<280H', calendar, day * 0x2C4)
        retained = [eid for eid in day_ids if eid != 0xFFFF and eid not in ids]
        capacity[day] = 280 - len(retained)
        if len(set(retained)) != len(retained):
            raise ValueError('Eventos duplicados en el calendario')
        for eid in retained:
            if eid >= 13000 or u16(events, eid * 0x254) != eid:
                raise ValueError('Referencia inválida en el calendario')
            pos = eid * 0x254
            overlap = set(clubs) & {team(u32(events, pos + 0x14)), team(u32(events, pos + 0x18))}
            if overlap:
                # Two complete rest days: a Sunday domestic game excludes
                # Friday through Tuesday for a UCL match (date gap >= 3).
                for excluded in range(max(0, day - 2), min(365, day + 3)):
                    blocked.add(excluded)
                    reasons.setdefault(excluded, []).append({
                        'event': eid, 'event_day': day, 'clubs': sorted(overlap)})
    current, year = audit['calendar']['day'], audit['calendar']['year']
    counts = [sum((e['code'], e['leg']) == stage for e in remaining) for stage in STAGES]
    # C3's native UCL final is day 149 (30 May). The old recovery moved it
    # ahead of UEL completion; native Super Cup qualification assumes both
    # competition winners exist. Never bring this final forward again.
    playoff_days = [day for tie in rs[0]['ties'] for e in tie['events'] for day in e['days']]
    if not playoff_days:
        raise ValueError('No se puede verificar el descanso desde el playoff')
    days = choose_days(max(current, max(playoff_days) + 6), blocked,
                       capacity, counts, final_day=149)
    desired = dict(zip(STAGES, days))
    ev_new, cal_new = bytearray(events), bytearray(calendar)
    for e in remaining:
        ev_new[e['id'] * 0x254 + 8:e['id'] * 0x254 + 12] = date_bytes(year, desired[e['code'], e['leg']])
    for day in range(365):
        pos = day * 0x2C4
        old = list(struct.unpack_from('<280H', calendar, pos))
        new = [0xFFFF if eid in ids else eid for eid in old]
        for e in remaining:
            if desired[e['code'], e['leg']] == day:
                new[new.index(0xFFFF)] = e['id']
        struct.pack_into('<280H', cal_new, pos, *new)
        struct.pack_into('<H', cal_new, pos + 0x230, sum(eid != 0xFFFF for eid in new))
    patches = []
    # Store the minimum complete field, not whole structures.
    for e in remaining:
        pos = e['id'] * 0x254 + 8
        if events[pos:pos + 4] != ev_new[pos:pos + 4]:
            patches.append((EVENT + pos, events[pos:pos + 4], bytes(ev_new[pos:pos + 4])))
    for day in range(365):
        for off in list(range(0, 560, 2)) + [0x230]:
            pos = day * 0x2C4 + off
            if calendar[pos:pos + 2] != cal_new[pos:pos + 2]:
                patches.append((CALENDAR + pos, calendar[pos:pos + 2], bytes(cal_new[pos:pos + 2])))
    after = decode_tables(comps, rounds, ev_new, cal_new, wanted=(4,))
    if after['calendar_errors']:
        raise ValueError('El calendario calculado no valida')
    for r in after['competitions'][0]['rounds'][1:]:
        for t in r['ties']:
            for e in t['events']:
                if e['days'] != [desired[e['code'], e['leg']]]:
                    raise ValueError('El evento calculado no quedó en su día único')
    return patches, {'calendar': audit['calendar'], 'clubs': clubs,
                     'dates': [{'code': s[0], 'leg': s[1], 'day': d,
                                'date': f'{year}-{date_bytes(year, d)[2]:02}-{date_bytes(year, d)[3]:02}'}
                               for s, d in desired.items()],
                     'blocked_future_days': {d: v for d, v in reasons.items() if current < d <= 150},
                     'before': audit, 'calculated_after': after}


def make_staged_r47_plan(comps, rounds, events, calendar):
    """Schedule a pre-existing R47 before playoff winners have been filled in.

    This is only for the exact 17 March state: R46 second legs are pending and
    R47 already has its eight seeded sides plus eight empty winner positions.
    It deliberately does not touch later rounds or create any teams/events.
    """
    audit = decode_tables(comps, rounds, events, calendar, wanted=(4,))
    if audit['calendar_errors'] or len(audit['competitions']) != 1:
        raise ValueError('Calendario inconsistente o competición UCL ambigua')
    c = audit['competitions'][0]
    rs = c['rounds']
    if (c['actual'], c['round_count'], [r['code'] for r in rs],
            [r['tie_count'] for r in rs]) != (24, 5, [46, 47, 51, 52, 53], [8, 8, 4, 2, 1]):
        raise ValueError('No es el cuadro UCL de 24 clubes esperado')
    current, year = audit['calendar']['day'], audit['calendar']['year']
    if current > 75 or not any(not e['played'] for t in rs[0]['ties'] for e in t['events']):
        raise ValueError('Este modo exige la vuelta del playoff pendiente el 17 de marzo')
    r47 = rs[1]
    entries = [e for tie in r47['ties'] for e in tie['events']]
    if len(entries) != 16 or any(e['played'] or e['days'] or e['date_raw'] != 'ffff0000' for e in entries):
        raise ValueError('Los octavos no están en el estado vacío reparable')
    seeded = [club for tie in r47['ties'] for club in tie['teams'] if club is not None]
    if len(seeded) != 8 or len(set(seeded)) != 8:
        raise ValueError('Los ocho cabezas de serie de octavos no son válidos')
    ids = {e['id'] for e in entries}
    for day, wanted in ((82, 8), (89, 8)):
        values = [eid for eid in struct.unpack_from('<280H', calendar, day * 0x2C4) if eid != 0xFFFF]
        if len(values) + wanted > 280 or ids & set(values):
            raise ValueError(f'El día {day} no admite los octavos')
        for eid in values:
            if eid >= 13000 or u16(events, eid * 0x254) != eid:
                raise ValueError('Referencia inválida en el calendario')
            pos = eid * 0x254
            if set(seeded) & {team(u32(events, pos + 0x14)), team(u32(events, pos + 0x18))}:
                raise ValueError(f'Un cabeza de serie UCL ya juega el día {day}')
    ev_new, cal_new = bytearray(events), bytearray(calendar)
    for e in entries:
        day = 82 if e['leg'] == 0 else 89
        ev_new[e['id'] * 0x254 + 8:e['id'] * 0x254 + 12] = date_bytes(year, day)
        pos = day * 0x2C4
        values = list(struct.unpack_from('<280H', cal_new, pos))
        values[values.index(0xFFFF)] = e['id']
        struct.pack_into('<280H', cal_new, pos, *values)
        struct.pack_into('<H', cal_new, pos + 0x230, sum(v != 0xFFFF for v in values))
    after = decode_tables(comps, rounds, ev_new, cal_new, wanted=(4,))
    if after['calendar_errors']:
        raise ValueError('El calendario calculado no valida')
    after_entries = [e for t in after['competitions'][0]['rounds'][1]['ties'] for e in t['events']]
    if any(e['days'] != [82 if e['leg'] == 0 else 89] for e in after_entries):
        raise ValueError('Los octavos calculados no quedaron en sus fechas')
    patches = []
    for e in entries:
        pos = e['id'] * 0x254 + 8
        patches.append((EVENT + pos, events[pos:pos + 4], bytes(ev_new[pos:pos + 4])))
    for day in (82, 89):
        for off in list(range(0, 560, 2)) + [0x230]:
            pos = day * 0x2C4 + off
            if calendar[pos:pos + 2] != cal_new[pos:pos + 2]:
                patches.append((CALENDAR + pos, calendar[pos:pos + 2], bytes(cal_new[pos:pos + 2])))
    return patches, {'calendar': audit['calendar'], 'mode': 'staged-r47',
                     'dates': [{'code': 47, 'leg': 0, 'day': 82, 'date': f'{year}-03-24'},
                               {'code': 47, 'leg': 1, 'day': 89, 'date': f'{year}-03-31'}],
                     'before': audit, 'calculated_after': after}


def read_state(reader):
    root = reader.pointer(BASE + 0x3705E10)
    model = reader.pointer(root + 0x48) if root else 0
    if not model:
        raise ValueError('No hay Liga Máster cargada')
    # Both installed C3 patches must be active before repairing data.
    if reader.read(BASE + 0x1348A91, 3) != bytes.fromhex('83fe2f'):
        raise ValueError('Falta el parche de progresión C3')
    if reader.read(BASE + 0x158147A, 1) != b'\xe9':
        raise ValueError('Falta el parche de calendario C3')
    return model, tuple(reader.read(model + off, size) for off, size in SIZES)


def apply(reader, model, state, patches):
    api = reader.api
    api.WriteProcessMemory.argtypes = [ct.c_void_p, ct.c_void_p, ct.c_void_p, ct.c_size_t, ct.POINTER(ct.c_size_t)]
    handle = api.OpenProcess(0xC38, False, args_pid := reader.pid)
    if not handle:
        raise ct.WinError(ct.get_last_error())
    nt = ct.WinDLL('ntdll')
    for name in ('NtSuspendProcess', 'NtResumeProcess'):
        getattr(nt, name).argtypes = [ct.c_void_p]
        getattr(nt, name).restype = ct.c_long
    suspended = False
    written = []
    def write(offset, data):
        count = ct.c_size_t()
        if not api.WriteProcessMemory(handle, model + offset, data, len(data), ct.byref(count)) or count.value != len(data):
            raise ct.WinError(ct.get_last_error())
    try:
        status = nt.NtSuspendProcess(handle)
        if status < 0:
            raise RuntimeError(f'No se pudo pausar el proceso: {status}')
        suspended = True
        if read_state(reader) != (model, state):
            raise ValueError('La partida cambió durante el diagnóstico; no se escribe')
        try:
            for offset, before, after in patches:
                written.append((offset, before))
                write(offset, after)
            for offset, before, after in patches:
                if reader.read(model + offset, len(after)) != after:
                    raise RuntimeError('Falló la relectura; revirtiendo')
        except BaseException:
            for offset, before in reversed(written):
                write(offset, before)
            raise
    finally:
        if suspended:
            status = nt.NtResumeProcess(handle)
            if status < 0:
                raise RuntimeError(f'No se pudo reanudar el proceso {args_pid}: {status}')
        api.CloseHandle(handle)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pid', type=int, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--apply', action='store_true')
    p.add_argument('--ensure', action='store_true',
                   help='automatic mode: leave an already compliant calendar untouched')
    p.add_argument('--stage-r47', action='store_true',
                   help='schedule only the pre-existing R47 on days 82/89')
    p.add_argument('--personal-only', action='store_true',
                   help='synchronize only the club agenda used by the main menu')
    p.add_argument('--group-menu-only', action='store_true',
                   help='synchronize league MatchSlot teams from existing Events only')
    a = p.parse_args()
    report = {'pid': a.pid, 'time': dt.datetime.now().astimezone().isoformat(), 'applied': False}
    reader = None
    a.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        reader = Reader(a.pid)
        reader.pid = a.pid
        model, state = read_state(reader)
        # Loading an existing ML does not necessarily invoke the native draw hook.
        # Plan Events, Round MatchSlots and the personal agenda from the SAME
        # corrected snapshot, then commit all three atomically.
        fixture, fixture_details = ([], {})
        planned = list(state)
        if a.ensure:
            fixture, fixture_details = make_fixture_plan(state[2], state[3],
                country_map(state[2], Path(__file__).parent))
            report['fixture'] = fixture_details
            if (fixture_details.get('status') == 'blocked-played' and
                    any(not m[4] for m in league_matches(state[2]))):
                report.update(status='blocked-played', error=fixture_details['message'])
                return 1
            if fixture:
                planned[2] = bytearray(state[2])
                for offset, before, after in fixture:
                    at = offset - EVENT
                    planned[2][at:at + len(after)] = after
        personal, changes = make_personal_schedule_plan(planned[2], planned[3]) if (a.ensure or a.personal_only) else ([], [])
        # During the group phase the knockout recovery is not applicable.
        # A repaired agenda is independent of the later knockout planner.
        group_pending = any(
            u16(state[2], i * 0x254) == i and
            u32(state[2], i * 0x254 + 4) & 0x3FF == 3 and
            not u32(state[2], i * 0x254 + 4) & 0x40000000
            for i in range(13000))
        if a.group_menu_only or (a.ensure and group_pending):
            menu, menu_changes = make_group_menu_plan(*planned[:3])
            patches, details = fixture + menu + ([] if a.group_menu_only else personal), {
                'status': 'group-menu', 'menu_changes': menu_changes,
                'agenda_changes': [] if a.group_menu_only else changes}
        elif a.personal_only:
            patches, details = personal, {'status': 'personal-schedule', 'agenda_changes': changes}
        elif a.ensure and schedule_compliant(state):
            report.update(status='compliant', fields_verified=0)
            return 0
        else:
            if a.stage_r47:
                patches, details = make_staged_r47_plan(*state)
            elif a.ensure:
                try:
                    patches, details = make_staged_r47_plan(*state)
                except ValueError:
                    patches, details = make_plan(*state)
            else:
                patches, details = make_plan(*state)
        report.update(details, model=hex(model), patches=[{'offset': hex(o), 'before': b.hex(), 'after': n.hex()} for o, b, n in patches])
        # Persist the complete rollback journal BEFORE any mutation.
        a.output.write_text(json.dumps(report, indent=2), encoding='utf-8')
        if a.apply:
            if patches:
                journal = a.output.with_name('rollback-' + str(a.pid) + '-' +
                    dt.datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.json')
                journal.write_text(json.dumps(report, indent=2), encoding='utf-8')
            if patches:
                apply(reader, model, state, patches)
            report.update(applied=True, fields_verified=len(patches))
    except Exception as exc:
        report['error'] = repr(exc)
    finally:
        if reader:
            reader.close()
        a.output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    return int('error' in report)


if __name__ == '__main__':
    raise SystemExit(main())
