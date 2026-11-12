@echo off
REM One-time setup on Windows: installs the Python packages the program needs.
cd /d "%~dp0"
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo Installation failed. Make sure Python 3.10+ is installed and on the PATH.
  pause
  exit /b 1
)
echo.
echo Done. Start the program with run.bat
pause
