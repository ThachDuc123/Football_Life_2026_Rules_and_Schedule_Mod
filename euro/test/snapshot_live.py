"""Read-only dump of the model tables the league generator touches (for test_format36)."""
import struct, sys
from pathlib import Path
sys.path.insert(0, r'D:\FL26\SiderAddons\content\ucl_calendar_guard')
from audit_native_knockout import Reader, BASE
from inspect_live import pid_of_game
out = Path(sys.argv[1]); out.mkdir(exist_ok=True)
r = Reader(pid_of_game())
model = r.pointer(r.pointer(BASE + 0x3705E10) + 0x48)
for name, off, size in (('comps', 0xC12E9C, 300 * 0x314), ('count', 0xD0BCF4, 4), ('rounds', 0xD65F64, 2000 * 0x208),
                        ('events', 0xE9FF08, 13000 * 0x254), ('calendar', 0x16038A8, 0x6CD00), ('ranking', 0x16705A8, 16 * 1024)):
    (out / f'{name}.bin').write_bytes(r.read(model + off, size))
print('dumped', out)
