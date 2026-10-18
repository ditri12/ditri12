@echo off
chcp 65001 >nul
REM הפעלת מערכת ניהול צי הרכב מקוד המקור (נדרש Python 3.10 ומעלה מותקן)
cd /d "%~dp0"
where py >nul 2>nul && set PY=py -3 || set PY=python
%PY% -c "import PySide6" 2>nul || (
  echo מתקין רכיבים נדרשים בפעם הראשונה...
  %PY% -m pip install --user -r requirements.txt
)
start "" %PY% fleet_manager.py
