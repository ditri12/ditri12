@echo off
chcp 65001 >nul
REM בניית קובץ הפעלה יחיד ל-Windows (FleetManager.exe) על מחשב Windows עם Python
cd /d "%~dp0\.."
python -m pip install --upgrade pip pyinstaller -r requirements.txt
python build\make_icon.py build\icon.ico
python -m PyInstaller --noconfirm --clean --onefile --windowed --name FleetManager --icon build\icon.ico fleet_manager.py
echo.
echo הקובץ נוצר: dist\FleetManager.exe
pause
