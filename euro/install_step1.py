"""Install the 36-club step 1 while the game is closed.

Copies build/euro_rules.dll to modules/ and adds the UEFA36 livecpk root to
sider.ini (right after the UCL32 block, so it wins over UML_Database). The
two only make sense together: the regulation without the DLL would draw 32
clubs into 4 groups of 9. `--remove` takes the root out again.
"""
import shutil
import subprocess
import sys
from pathlib import Path

SIDER = Path(r'D:\FL26\SiderAddons')
HERE = Path(__file__).resolve().parent
INI = SIDER / 'sider.ini'
MARKER = '# UCL32 MOD END'
BEGIN = '# UEFA36 BEGIN - UCL/UEL 36-club league phase (4 groups of 9). Delete these 3 lines to go back.'


def game_running():
    out = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq FL_2026.exe', '/NH'],
                         capture_output=True, text=True).stdout
    return 'FL_2026.exe' in out


def edit_ini(add):
    raw = INI.read_bytes()
    nl = '\r\n' if b'\r\n' in raw else '\n'
    text = raw.decode('utf-8', errors='surrogateescape')
    lines = text.split(nl)
    lines = [l for l in lines if not (l.startswith('# UEFA36 ') or l == 'cpk.root = ".\\livecpk\\UEFA36"')]
    if add:
        at = lines.index(MARKER) + 1
        lines[at:at] = [BEGIN, 'cpk.root = ".\\livecpk\\UEFA36"', '# UEFA36 END']
    INI.write_bytes(nl.join(lines).encode('utf-8', errors='surrogateescape'))


def main():
    if game_running():
        print('FL_2026.exe is running: close the game first')
        return 1
    if '--remove' in sys.argv:
        edit_ini(False)
        print('UEFA36 root removed from sider.ini')
        return 0
    backup = HERE / 'original' / 'sider.ini.bak'
    if not backup.exists():
        shutil.copy2(INI, backup)
    shutil.copy2(HERE / 'build' / 'euro_rules.dll', SIDER / 'modules' / 'euro_rules.dll')
    edit_ini(True)
    print('installed euro_rules.dll and the UEFA36 root')
    return 0


if __name__ == '__main__':
    sys.exit(main())
