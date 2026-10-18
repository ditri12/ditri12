#!/usr/bin/env python3
"""הפעלת מערכת ניהול צי הרכב: python fleet_manager.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fleet_app.main import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
