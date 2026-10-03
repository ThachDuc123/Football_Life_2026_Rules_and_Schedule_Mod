"""New competitions on top of the FL26 database (test 1).

The game has a fixed set of runtime competition ids (1..175, see the schedule
dispatcher 0x14157F810). FL26 leaves some of them without data:
  * 76/77/78 run the same engine code as the Copa Libertadores 8/9/10
    (qualifier / group stage / knockout) - the PES 2021 Copa Sudamericana.
    They become the UEFA Conference League: 77 = league phase (9 groups of 4,
    home and away = 6 matches, redrawn later to the real 6-pot format),
    78 = knockout (24 clubs: play-offs 9-24, round of 16 with 1-8).
  * 139/144/146 are knockout cups with a European season; they become the
    league cups that exist in reality: EFL Cup (England), Taca da Liga
    (Portugal), Scottish League Cup.
Each needs a Competition.bin record (database id, country, name), its
regulation records and, for the first season, CompetitionEntry rows.
"""
import struct
from pathlib import Path

RECORD = 2352
COEF = Path(__file__).resolve().parent / 'data' / 'club_coefficients.tsv'

# database id, country byte (Competition.bin byte 3), kind (byte 6), internal name
UECL_DB, EFL_DB, TACA_DB, SCOT_DB = 0x06, 0x92, 0x93, 0x94
NEW_DB = [
    (UECL_DB, 0x08, 0x02, 'UEFA_CONFERENCE_LEAGUE'),
    (EFL_DB, 0x10, 0x22, 'ENGLAND_LEAGUE_CUP'),
    (TACA_DB, 0x30, 0x22, 'PORTUGAL_LEAGUE_CUP'),
    (SCOT_DB, 0x78, 0x22, 'SCOTLAND_LEAGUE_CUP'),
]

# The 22 clubs of the real 2025/26 Conference League league phase that exist
# in FL26 (team ids); the other 14 (Shamrock Rovers, Celje, Zrinjski, Lincoln,
# KuPS, Drita, Breidablik, Sigma Olomouc, AEK Larnaca, Shkendija, Craiova,
# Hamrun, Noah, Shelbourne) are not in the game.
UECL_2025 = [124, 242, 1232, 4344, 1819, 1756, 175, 134, 382, 2127, 370, 2185,
             436, 4213, 5269, 2526, 270, 1219, 5361, 5288, 5322, 4964]

# 2025/26 title holders: the game enters them itself (Super Cup PSG - Tottenham).
HOLDERS = {114, 179}

# Real 2025/26 Taca da Liga quarter-finalists: Sporting CP, FC Alverca,
# SL Benfica, CD Tondela, FC Porto, Vitoria SC, SC Braga, CD Santa Clara.
TACA_2025 = [193, 5845, 191, 2614, 192, 1804, 1974, 2391]

NAME_SLOTS = [0x14 + k * 0x73 for k in range(9)] + [0x43F + k * 0x73 for k in range(11)]
INTERNAL_SLOT, INTERNAL_LEN, NAME_LEN = 0x41F, 0x20, 0x73


def _name(rec, display, internal):
    for off in NAME_SLOTS:
        if any(rec[off:off + NAME_LEN]):
            raw = display.encode('utf-8')[:NAME_LEN - 1]
            rec[off:off + NAME_LEN] = raw + bytes(NAME_LEN - len(raw))
    raw = internal.encode()[:INTERNAL_LEN - 1]
    rec[INTERNAL_SLOT:INTERNAL_SLOT + INTERNAL_LEN] = raw + bytes(INTERNAL_LEN - len(raw))


def _find(data, comp, group=0):
    for i in range(len(data) // RECORD):
        rec = data[i * RECORD:(i + 1) * RECORD]
        if struct.unpack_from('<H', rec, 2)[0] == comp | group << 10:
            return bytearray(rec)
    raise KeyError((comp, group))


def _set_teams(rec, n):
    rec[11] = (rec[11] & 0xC0) | n


def regulation_records(source):
    """Regulation records for the new competitions, cloned from FL26 ones."""
    out = []
    # UEFA Conference League league phase: parent + 9 groups of 4, two meetings.
    for g in range(10):
        rec = _find(source, 5, min(g, 1))           # UEL parent / group record
        struct.pack_into('<H', rec, 2, 77 | g << 10)
        struct.pack_into('<H', rec, 6, 77 if g else 0)
        rec[8] = UECL_DB
        rec[10] = 0xFF if g == 0 else g - 1
        _set_teams(rec, 36)
        rec[16] = (rec[16] & 0xE0) | 9
        rec[17] = (rec[17] & 0xCF) | 0x20
        _name(rec, 'UEFA Conference League', 'UEFA_CONF_LEAGUE_GROUPSTAGE')
        out.append(bytes(rec))
    # Knockout: 24 clubs (8 byes = places 1-8, play-offs for 9-24).
    rec = _find(source, 6)
    struct.pack_into('<H', rec, 2, 78)
    rec[8] = UECL_DB
    _set_teams(rec, 24)
    _name(rec, 'UEFA Conference League', 'UEFA_CONF_LEAGUE_KNOCKOUT')
    out.append(bytes(rec))
    # League cups, cloned from the FA Cup / Scottish Cup knockout records.
    for comp, db, teams, base, legs, display, internal in (
            (139, EFL_DB, 44, 23, 0x00, 'Carabao Cup', 'ENGLAND_LEAGUE_CUP_KNOCKOUT'),
            (144, TACA_DB, 8, 28, 0x00, 'Taça da Liga', 'PORTUGAL_LEAGUE_CUP_KNOCKOUT'),
            (146, SCOT_DB, 12, 137, 0x00, 'Premier Sports Cup', 'SCOTLAND_LEAGUE_CUP_KNOCKOUT')):
        rec = _find(source, base)
        struct.pack_into('<H', rec, 2, comp)
        struct.pack_into('<H', rec, 0, 0)
        rec[8] = db
        _set_teams(rec, teams)
        rec[17] = legs
        if comp == 139:
            rec[19] = 0x28            # level after 90 minutes: penalties, no extra time
        _name(rec, display, internal)
        out.append(bytes(rec))
    return out


# euro_extra.dll decides single/two-legged per round (real formats); the
# regulation of these existing records is set to "single" so the game's
# other readers of the leg mode agree: Belgian Cup (two-legged rounds in
# FL26), Supercopa de Espana (two legs in FL26), Danish European play-off.
SINGLE_MODE = (122, 87, 151)


def patch_existing(rec):
    comp = struct.unpack_from('<H', rec, 2)[0]
    if comp in SINGLE_MODE:
        rec = bytearray(rec)
        rec[17] = 0x00
        return bytes(rec), True
    return rec, False


def competition_bin(data):
    """Competition.bin (36-byte records sorted by database id) plus the new ids."""
    recs = [data[i:i + 36] for i in range(0, len(data), 36)]
    have = {r[5] for r in recs}
    for db, country, kind, name in NEW_DB:
        assert db not in have, hex(db)
        raw = name.encode()[:27]
        recs.append(bytes([0x64, 0xC8, 0x00, country, 0x00, db, kind, 0x00]) + raw + bytes(28 - len(raw)))
    recs.sort(key=lambda r: r[5])
    return b''.join(recs)


def _entries(data):
    return [struct.unpack_from('<III', data, i) for i in range(0, len(data), 12)]


def _coefficients():
    ranked = []
    for line in COEF.read_text(encoding='utf-8').splitlines():
        parts = line.split('\t')
        if len(parts) >= 2 and parts[0].isdigit():
            ranked.append((-float(parts[1]), int(parts[0])))
    return [t for _, t in sorted(ranked)]


def first_season(data):
    """{database id: [team ids]} for the first season of a new Master League."""
    entries = _entries(data)
    by_db = {}
    for team, _eid, packed in entries:
        by_db.setdefault(packed & 0xFF, []).append(((packed >> 8) & 0xFF, team))
    listed = lambda db: [t for _, t in sorted(by_db.get(db, []))]
    europe = set(listed(0x02)) | set(listed(0x03)) | HOLDERS
    uecl = [t for t in UECL_2025 if t not in europe]
    european_league_clubs = set()
    for db in (0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x27, 0x6F, 0x72, 0x75, 0x77, 0x80, 0x89, 0x42, 0x43, 0x44, 0x45):
        european_league_clubs.update(listed(db))
    for team in _coefficients():
        if len(uecl) >= 36:
            break
        if team not in europe and team not in uecl and team in european_league_clubs:
            uecl.append(team)
    portugal = listed(0x0E)
    taca = [t for t in TACA_2025 if t in portugal]
    for team in portugal:                      # clubs missing from FL26 replaced
        if len(taca) >= 8:
            break
        if team not in taca:
            taca.append(team)
    return {
        UECL_DB: uecl[:36],
        EFL_DB: listed(0x0F),                  # the 44 English clubs of the FA Cup
        TACA_DB: taca[:8],
        SCOT_DB: listed(0x89),                 # the 12 Scottish Premiership clubs
    }


def entry_bin(data, lists):
    entries = _entries(data)
    next_id = 900000
    used = {e for _, e, _ in entries}
    out = bytearray(data)
    for db, teams in lists.items():
        assert db not in {p & 0xFF for _, _, p in entries}, hex(db)
        for slot, team in enumerate(teams, 1):
            while next_id in used:
                next_id += 1
            out += struct.pack('<III', team, next_id, db | slot << 8)
            used.add(next_id)
    return bytes(out)
