import struct, sys, os
sys.path.insert(0, r'D:\FL26\SiderAddons\content\ucl_calendar_guard')
sys.path.insert(0, r'D:\FL26\SiderAddons\Dugout')
from audit_native_knockout import Reader, BASE, COMP, team
from inspect_live import pid_of_game
from dugout.pes import crypto, world
clubs = world.clubs(crypto.read(os.path.expanduser('~/Documents/KONAMI/eFootball PES 2021 SEASON UPDATE/2026/save/ML00000005')).data)
nm = lambda t: clubs[t].name[:22] if t in clubs else f'#{t}'
r = Reader(pid_of_game())
model = r.pointer(r.pointer(BASE + 0x3705E10) + 0x48)
raw = r.read(model + 0x1670590, 16 * 700)
print('header', raw[:24].hex(' '))
start = 0x18      # model + 0x16705A8
rank = {}
for k in range(700):
    tm, rk, pts, x = struct.unpack_from('<4I', raw, start + k * 16)
    if tm == 0xFFFFFFFF: print('records', k); break
    rank[(tm >> 14) & 0x1FFFF] = (rk, pts >> 16, pts & 0xFFFF, x >> 16)
comps = r.read(model + COMP, 300 * 0x314)
for i in range(300):
    rec = comps[i * 0x314:(i + 1) * 0x314]
    if struct.unpack_from('<H', rec)[0] == 3:
        n = (struct.unpack_from('<I', rec, 0x308)[0] >> 16) & 0x7F
        ucl = [team(struct.unpack_from('<I', rec, 0x170 + k * 4)[0]) for k in range(n)]
ucl.sort(key=lambda t: rank.get(t, (999,))[0])
for p in range(4):
    print('pot', p + 1, ', '.join(f"{nm(t)} #{rank.get(t, ('?',))[0]}" for t in ucl[p * 9:(p + 1) * 9]))
