import struct, sys, os
sys.path.insert(0, r'D:\FL26\SiderAddons\content\ucl_calendar_guard')
sys.path.insert(0, r'D:\FL26\SiderAddons\Dugout')
from audit_native_knockout import Reader, BASE, COMP, team
from inspect_live import pid_of_game
from dugout.pes import crypto, world
data = crypto.read(os.path.expanduser('~/Documents/KONAMI/eFootball PES 2021 SEASON UPDATE/2026/save/ML00000002')).data
clubs = world.clubs(data)
nm = lambda t: clubs[t].name[:20] if t in clubs else f'#{t}'
r = Reader(pid_of_game())
model = r.pointer(r.pointer(BASE + 0x3705E10) + 0x48)
comps = r.read(model + COMP, 300 * 0x314)
recs = {struct.unpack_from('<H', comps, i * 0x314)[0]: comps[i * 0x314:(i + 1) * 0x314] for i in range(300)}
for base in (3, 5):
    print('== comp', base)
    for g in range(1, 5):
        rec = recs[(g << 10) | base]
        n = (struct.unpack_from('<I', rec, 0x308)[0] >> 16) & 0x7F
        print(f'  group {g}:', ' | '.join(nm(team(struct.unpack_from('<I', rec, 0x170 + k * 4)[0])) for k in range(n)))
