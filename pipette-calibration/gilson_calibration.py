#!/usr/bin/env python3
"""Launcher kept for compatibility with the original single-file program.

Run:  python gilson_calibration.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipette_cal.app import main  # noqa: E402

if __name__ == "__main__":
    main()
