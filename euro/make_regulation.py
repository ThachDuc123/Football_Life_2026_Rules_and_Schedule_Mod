"""Build livecpk/UEFA36/common/etc/pesdb/CompetitionRegulation.bin.

Source: livecpk/UML_Database (WESYS: ff 10 81 'WESYS', u32 compressed size,
u32 size, zlib). Records are 2352 bytes; the stage parameters are bytes 8..19:
db competition, stage type, group index (ff = parent), teams (low 6 bits),
then packed fields where byte 16 (low 5 bits) is the number of groups and
byte 17 bits 4-5 the number of meetings (1 = single round robin, 2 = home and
away). Verified against the runtime Competition records (+0x307 = groups).

UCL league phase (comp 3) and UEL league phase (comp 5) become 36 clubs in
4 groups of 9 playing once: 8 matches per club, 144 matches, as in the
2024+ format; euro_rules/ucl32_format redraw the opponents from it. The
group records past the fourth are removed.

extra_comps.py adds the UEFA Conference League (77/78) and the league cups
(139/144/146) to the regulation, Competition.bin and CompetitionEntry.bin.
"""
import struct
import sys
import zlib
from pathlib import Path

import extra_comps as extra

ROOT = Path(r'D:\FL26\SiderAddons\livecpk')
SOURCE = ROOT / 'UML_Database/common/etc/pesdb/CompetitionRegulation.bin'
TARGET = ROOT / 'UEFA36/common/etc/pesdb/CompetitionRegulation.bin'
RECORD = 2352
MAGIC = b'\xff\x10\x81WESYS'


def unpack(raw):
    assert raw[:8] == MAGIC, 'not a WESYS file'
    csize, usize = struct.unpack_from('<II', raw, 8)
    data = zlib.decompress(raw[16:16 + csize])
    assert len(data) == usize
    return data


def pack(data):
    comp = zlib.compress(data, 9)
    return MAGIC + struct.pack('<II', len(comp), len(data)) + comp


def convert(data):
    assert len(data) % RECORD == 0
    out, changed, dropped = [], [], []
    for i in range(len(data) // RECORD):
        rec = bytearray(data[i * RECORD:(i + 1) * RECORD])
        comp = struct.unpack_from('<H', rec, 2)[0]
        base, group = comp & 0x3FF, comp >> 10
        if base in (3, 5) and rec[9] == 2:              # UCL / UEL group stage
            if group > 4:
                dropped.append(comp)
                continue
            rec[11] = (rec[11] & 0xC0) | 36
            rec[16] = (rec[16] & 0xE0) | 4
            rec[17] = (rec[17] & 0xCF) | 0x10
            changed.append(comp)
        rec, patched = extra.patch_existing(bytes(rec))
        if patched:
            changed.append(comp)
        out.append(bytes(rec))
    return b''.join(out), changed, dropped


def main():
    data = unpack(SOURCE.read_bytes())
    new, changed, dropped = convert(data)
    assert len(changed) == 10 + len(extra.SINGLE_MODE) and len(dropped) == 12, (changed, dropped)
    added = extra.regulation_records(data)
    new += b''.join(added)
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_bytes(pack(new))
    assert unpack(TARGET.read_bytes()) == new
    print(f'{TARGET}: {len(new) // RECORD} records (was {len(data) // RECORD}); '
          f'changed {[hex(c) for c in changed]}; dropped {[hex(c) for c in dropped]}; '
          f'added {[hex(struct.unpack_from("<H", r, 2)[0]) for r in added]}')
    comps = extra.competition_bin(unpack((SOURCE.parent / 'Competition.bin').read_bytes()))
    (TARGET.parent / 'Competition.bin').write_bytes(pack(comps))
    entries_src = unpack((SOURCE.parent / 'CompetitionEntry.bin').read_bytes())
    lists = extra.first_season(entries_src)
    (TARGET.parent / 'CompetitionEntry.bin').write_bytes(pack(extra.entry_bin(entries_src, lists)))
    print(f'Competition.bin: {len(comps) // 36} records; CompetitionEntry.bin first season '
          + ', '.join(f'{db:#x}: {len(t)} clubs' for db, t in lists.items()))


if __name__ == '__main__':
    sys.exit(main())
