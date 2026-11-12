@echo off
cd /d "%~dp0"
pythonw gilson_calibration.py
if errorlevel 1 python gilson_calibration.py
