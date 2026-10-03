"""Patch content/ucl_calendar_guard/repair_ucl_calendar.py for the 36-club format.

* leg order and bracket report for the UCL (comp 4 from comp 3) and the UEL
  (comp 6 from comp 5);
* with a 36-club league phase (4 groups in the regulation) the 32x6 fixture and
  group-menu repairs are skipped (ucl32_format writes fixtures and MatchSlots).
Applied once to original/repair_ucl_calendar.py.phase1.
"""
from pathlib import Path

P = Path(r'D:\FL26\SiderAddons\content\ucl_calendar_guard\repair_ucl_calendar.py')
s = P.read_text(encoding='utf-8')


def rep(a, b, count=1):
    global s
    assert s.count(a) == count, (s.count(a), a[:90])
    s = s.replace(a, b)


rep('''def make_leg_order_plan(comps, rounds, events, calendar):
    """The club with the better league-phase position hosts the second leg.

    Applies to every two-legged UCL knockout tie whose two clubs are known and
    whose legs are both unplayed. The tie's team order and both Events'
    home/away are swapped together, so Round and Event stay consistent.
    """
    audit = decode_tables(comps, rounds, events, calendar, wanted=(4,))
    if audit['calendar_errors'] or len(audit['competitions']) != 1:
        return [], []
    positions = euro_rules.league_positions(events, 3)''',
    '''def league_groups(comps, comp_id):
    """Groups of a league phase in the runtime Competition record (8, 12 or 4)."""
    for cp in range(0, len(comps), 0x314):
        if u16(comps, cp) == comp_id:
            return comps[cp + 0x307] & 0x3F
    return 0


def make_leg_order_plan(comps, rounds, events, calendar, ko=4, league=3):
    """The club with the better league-phase position hosts the second leg.

    Applies to every two-legged knockout tie of `ko` (4 = UCL, 6 = UEL) whose
    two clubs are known and whose legs are both unplayed; positions come from
    the `league` phase table (3 = UCL, 5 = UEL). The tie's team order and both
    Events' home/away are swapped together, so Round and Event stay consistent.
    """
    audit = decode_tables(comps, rounds, events, calendar, wanted=(ko,))
    if audit['calendar_errors'] or len(audit['competitions']) != 1:
        return [], []
    positions = euro_rules.league_positions(events, league)''')

rep("""            changes.append({'code': r['code'], 'slot': tie['slot'], 'second_leg_home': a,""",
    """            changes.append({'comp': ko, 'code': r['code'], 'slot': tie['slot'], 'second_leg_home': a,""")

rep('''def bracket_report(comps, rounds, events, calendar):
    """Compare the native UCL bracket with the 2025/26 bracket euro_rules.dll built."""
    audit = decode_tables(comps, rounds, events, calendar, wanted=(4,))''',
    '''def bracket_report(comps, rounds, events, calendar, ko=4, league=3):
    """Compare the native knockout bracket with the 2025/26 bracket euro_rules.dll built."""
    audit = decode_tables(comps, rounds, events, calendar, wanted=(ko,))''')
rep("""    rows, unplayed = euro_rules.league_table(events, 3)
    if len(rows) != 32 or unplayed:
        return None""",
    """    rows, unplayed = euro_rules.league_table(events, league)
    if len(rows) not in (32, 36) or unplayed:
        return None""")

rep("""        fixture, fixture_details = ([], {})
        planned = list(state)
        if a.ensure:""",
    """        fixture, fixture_details = ([], {})
        planned = list(state)
        # 36-club league phase: ucl32_format already wrote fixtures and
        # MatchSlots; the 32x6 repairs below must not run.
        league36 = league_groups(state[0], 3) == 4
        if league36:
            report['league36'] = True
        if a.ensure and not league36:""")

rep("""        if a.group_menu_only or (a.ensure and group_pending):""",
    """        if a.ensure and league36 and group_pending:
            patches, details = personal, {'status': 'league36-group', 'agenda_changes': changes}
        elif a.group_menu_only or (a.ensure and group_pending):""")

rep("""            legs, leg_changes = make_leg_order_plan(*state) if a.ensure else ([], [])
            report['euro'] = {'bracket': bracket_report(*state), 'leg_order': leg_changes}""",
    """            legs, leg_changes = make_leg_order_plan(*state) if a.ensure else ([], [])
            uel_legs, uel_changes = make_leg_order_plan(*state, ko=6, league=5) if a.ensure else ([], [])
            legs, leg_changes = legs + uel_legs, leg_changes + uel_changes
            report['euro'] = {'bracket': bracket_report(*state),
                              'uel_bracket': bracket_report(*state, ko=6, league=5),
                              'leg_order': leg_changes}""")

P.write_text(s, encoding='utf-8')
print('patched', P)
