@echo off
cd /d "%~dp0"
python -m PyInstaller --noconfirm --onefile --windowed --name GenshinDamageCalc --clean main.py
echo.
echo 打包完成，产物在 dist\GenshinDamageCalc.exe
pause