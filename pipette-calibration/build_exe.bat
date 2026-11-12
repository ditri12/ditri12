@echo off
REM Builds a single-file Windows executable: dist\PipetteCalibration.exe
cd /d "%~dp0"
python -m pip install -r requirements-dev.txt
python -m PyInstaller --noconfirm --clean --onefile --windowed --name PipetteCalibration ^
  --add-data "assets;assets" gilson_calibration.py
echo.
echo Build finished: dist\PipetteCalibration.exe
pause
