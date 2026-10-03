import struct, sys
sys.path.insert(0, r'D:\FL26\SiderAddons\content\ucl_calendar_guard')
from audit_native_knockout import Reader, BASE
from inspect_live import pid_of_game
r = Reader(pid_of_game())
model = r.pointer(r.pointer(BASE + 0x3705E10) + 0x48)
size = 0x1800000
chunk = 0x100000
found = []
for off in range(0, size, chunk):
    try:
        data = r.read(model + off, chunk + 64)
    except Exception as e:
        print('stop at', hex(off), e); break
    i = data.find(struct.pack('<II', 0x1b4036, 1))
    while i >= 0:
        found.append(off + i)
        i = data.find(struct.pack('<II', 0x1b4036, 1), i + 1)
print('model', hex(model), 'hits', [hex(x) for x in found])
for h in found:
    rec = h - 4
    rows = [struct.unpack('<4I', r.read(model + rec + k * 16, 16)) for k in range(4)]
    print(hex(rec), [[hex(x) for x in w] for w in rows])
