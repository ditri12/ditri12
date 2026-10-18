"""הגדרות מקומיות של התוכנה (לא של הצי): בעיקר מיקום קובץ הנתונים.

ברירת המחדל: תיקיית הנתונים של המשתמש (ב-Windows: %APPDATA%\\FleetManager).
אפשר להפנות לקובץ על כונן רשת משותף כדי שכל העובדים יעבדו על אותם נתונים.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from . import APP_NAME


def app_data_dir() -> Path:
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = str(Path.home() / "Library" / "Application Support")
    else:
        base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    d = Path(base) / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def config_path() -> Path:
    return app_data_dir() / "config.json"


def default_db_path() -> Path:
    return app_data_dir() / "fleet.db"


def load() -> dict:
    p = config_path()
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    return {}


def save(cfg: dict) -> None:
    config_path().write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def db_path() -> Path:
    env = os.environ.get("FLEET_DB")
    if env:
        return Path(env)
    cfg = load()
    if cfg.get("db_path"):
        return Path(cfg["db_path"])
    return default_db_path()


def set_db_path(path: str | None) -> None:
    cfg = load()
    if path:
        cfg["db_path"] = str(path)
    else:
        cfg.pop("db_path", None)
    save(cfg)
