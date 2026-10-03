"""Rebuild the in-memory Event table (13000 x 0x254) from an ML save.

Save row i is Event i: the save keeps the 592 bytes after the 4-byte header
and appends id + 1, so the record is u16 id, u16 0, row[0:592].
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, r'D:\FL26\SiderAddons\Dugout')
from dugout.pes import crypto, world  # noqa: E402

STRIDE, CAPACITY = 0x254, 13000


def events_from_save(path):
    data = crypto.read(str(path)).data
    start = world.locate_fixture_table(data)
    out = bytearray(b'\xff' * (STRIDE * CAPACITY))
    for f in world.fixtures(data, with_entries=False):
        i = (f.offset - start) // STRIDE
        out[i * STRIDE:(i + 1) * STRIDE] = struct.pack('<HH', i, 0) + data[f.offset:f.offset + 592]
    return bytes(out), world.clubs(data)


if __name__ == '__main__':
    events, _ = events_from_save(Path(sys.argv[1]))
    Path(sys.argv[2]).write_bytes(events)
