"""הגדרות מקומיות של התוכנה (לא של הצי): בעיקר התיקייה שבה נשמרים הנתונים.

ברירת המחדל: תיקיית הנתונים של המשתמש (ב-Windows: %APPDATA%\\FleetManager).
אפשר לבחור כל תיקייה אחרת - כולל תיקייה משותפת ברשת (למשל \\\\server\\share\\FleetData) -
כדי שכל העובדים יעבדו על אותו רישום. שם הקובץ בתוך התיקייה קבוע: fleet.db
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from . import APP_NAME

DB_FILENAME = "fleet.db"


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


def default_data_dir() -> Path:
    return app_data_dir()


def default_db_path() -> Path:
    return default_data_dir() / DB_FILENAME


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


def is_configured() -> bool:
    """האם המשתמש כבר בחר היכן לשמור את הנתונים (או שכבר קיים קובץ בברירת המחדל)."""
    cfg = load()
    return bool(cfg.get("data_dir") or cfg.get("db_path")) or default_db_path().exists()


def data_dir() -> Path:
    """התיקייה שבה נשמר קובץ הנתונים."""
    env = os.environ.get("FLEET_DB")
    if env:
        return Path(env).parent
    cfg = load()
    if cfg.get("data_dir"):
        return Path(cfg["data_dir"])
    if cfg.get("db_path"):  # תאימות לגרסה קודמת שבה נשמר נתיב לקובץ
        return Path(cfg["db_path"]).parent
    return default_data_dir()


def db_path() -> Path:
    env = os.environ.get("FLEET_DB")
    if env:
        return Path(env)
    cfg = load()
    if cfg.get("db_path") and not cfg.get("data_dir"):
        return Path(cfg["db_path"])
    return data_dir() / DB_FILENAME


def set_data_dir(path: str | os.PathLike | None) -> None:
    """שמירת תיקיית הנתונים; None מחזיר לברירת המחדל."""
    cfg = load()
    cfg.pop("db_path", None)
    if path:
        cfg["data_dir"] = str(path)
    else:
        cfg.pop("data_dir", None)
    save(cfg)


def check_writable(folder: str | os.PathLike) -> str | None:
    """בודק שאפשר לכתוב לתיקייה. מחזיר הודעת שגיאה בעברית או None אם תקין."""
    p = Path(folder)
    try:
        p.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return f"לא ניתן ליצור או לגשת לתיקייה:\n{p}\n\n{e}"
    probe = p / ".fleet_write_test"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as e:
        return f"אין הרשאת כתיבה לתיקייה:\n{p}\n\n{e}"
    return None
