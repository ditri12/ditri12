#!/usr/bin/env sh
# הפעלה מקוד המקור ב-Linux / macOS
cd "$(dirname "$0")"
python3 -c "import PySide6" 2>/dev/null || python3 -m pip install --user -r requirements.txt
exec python3 fleet_manager.py
