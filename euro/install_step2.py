"""Install the 36-club league phase (step 2) while the game is closed.

Copies build/euro_rules.dll (1.2.0) and ../build/ucl32_format_v111.dll (2.0.0)
to modules/ and makes sure the UEFA36 livecpk root is in sider.ini (see
install_step1.py). The Lua and Python parts are already in place.
"""
import shutil
import sys
from pathlib import Path

import install_step1 as step1

HERE = Path(__file__).resolve().parent
MODULES = step1.SIDER / 'modules'


def main():
    if step1.game_running():
        print('FL_2026.exe is running: close the game first')
        return 1
    shutil.copy2(HERE / 'build' / 'euro_rules.dll', MODULES / 'euro_rules.dll')
    shutil.copy2(HERE.parent / 'build' / 'ucl32_format_v111.dll', MODULES / 'ucl32_format_v111.dll')
    step1.edit_ini(True)
    for name, src in (('euro_rules.dll', HERE / 'build' / 'euro_rules.dll'),
                      ('ucl32_format_v111.dll', HERE.parent / 'build' / 'ucl32_format_v111.dll')):
        if (MODULES / name).read_bytes() != src.read_bytes():
            print('copy check failed for', name)
            return 2
    print('installed euro_rules and ucl32_format from build/ and the UEFA36 root')
    return 0


if __name__ == '__main__':
    sys.exit(main())
