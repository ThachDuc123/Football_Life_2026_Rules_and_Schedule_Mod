import struct, sys
sys.path.insert(0, r'D:\FL26\SiderAddons\content\ucl_calendar_guard')
from audit_native_knockout import Reader, BASE, COMP, ROUND
from inspect_live import pid_of_game
r = Reader(pid_of_game())
model = r.pointer(r.pointer(BASE + 0x3705E10) + 0x48)
comps = r.read(model + COMP, 300 * 0x314)
for i in range(300):
    rec = comps[i * 0x314:(i + 1) * 0x314]
    if struct.unpack_from('<H', rec)[0] == 0x403:
        rids = [x for x in struct.unpack_from('<58i', rec, 0x88) if x != -1]
        print('comp 0x403 rids', rids, '+0x300', rec[0x300:0x314].hex(' '))
        for rid in rids[:2] + rids[-1:]:
            rd = r.read(model + ROUND + rid * 0x208, 0x208)
            print('round', rid, 'id', struct.unpack_from('<H', rd)[0], 'hdr', rd[0:4].hex(' '), 'packed', hex(struct.unpack_from('<I', rd, 0x204)[0]))
            for s in range(6):
                print('   slot', s, rd[4 + s * 32:4 + (s + 1) * 32].hex(' '))
