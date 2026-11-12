@echo off
REM Builds a single-file Windows executable: dist\PipetteCalibration.exe
cd /d "%~dp0"
python -m pip install -r requirements-dev.txt
python -m PyInstaller --noconfirm --clean --onefile --windowed --name PipetteCalibration ^
  --icon assets\app.ico --add-data "assets;assets" ^
  --collect-submodules win32com --hidden-import win32timezone gilson_calibration.py
echo.
echo Build finished: dist\PipetteCalibration.exe
pause
