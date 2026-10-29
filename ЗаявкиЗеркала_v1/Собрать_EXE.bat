@echo off
chcp 65001 >nul
cd /d "%~dp0"
py -m pip install -r requirements.txt
if errorlevel 1 pause & exit /b 1
py -m PyInstaller --noconfirm --clean --onefile --windowed --name "ЗаявкиЗеркала" --collect-all reportlab app.py
if errorlevel 1 pause & exit /b 1
echo Готово: dist\ЗаявкиЗеркала.exe
pause
