@echo off
rem Cai euro_rules.dll va ucl32_format_v111.dll moi nhat (tat game truoc).
cd /d "%~dp0"
python install_step2.py
if errorlevel 1 (
    echo.
    echo Chua cai duoc. Hay tat han game FL26 roi bam lai file nay.
) else (
    echo.
    echo Da cai xong. Mo game, kiem tra D:\FL26\euro_rules.log va D:\FL26\ucl32_format.log.
)
pause
