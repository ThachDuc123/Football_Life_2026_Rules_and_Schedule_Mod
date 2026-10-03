import struct, sys
sys.path.insert(0, r'D:\FL26\SiderAddons\content\ucl_calendar_guard')
from audit_native_knockout import Reader, BASE, CALENDAR
from inspect_live import pid_of_game
r = Reader(pid_of_game())
model = r.pointer(r.pointer(BASE + 0x3705E10) + 0x48)
raw = r.read(model + CALENDAR + 0x3F170, 0x40)
print(raw.hex(' '))
for slot in range(4):
    base = 0x3F180 + slot * 0x16DC
    hdr = r.read(model + CALENDAR + base, 8)
    print('agenda', slot, hdr.hex(' '), 'team', (struct.unpack_from('<I', hdr, 4)[0] >> 14) & 0x1FFFF)
