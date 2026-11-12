"""Persistent configuration and calibration history.

* config.json      user settings (scale address, operator, theme, ...)
* history.sqlite   every completed calibration, used for the document
                   number sequence and the History tab.

Files live in the per-user application-data folder so the program folder
stays read-only (works from a network share or a packaged .exe).
"""
from __future__ import annotations

import dataclasses
import json
import logging
import os
import sqlite3
import sys
from dataclasses import dataclass, asdict
from datetime import date, datetime
from pathlib import Path

log = logging.getLogger(__name__)

ORGANISATION = "LifeGene"
APP_DIR_NAME = "PipetteCalibration"
DOC_PREFIX = "LG-CAL"


def app_data_dir() -> Path:
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    path = base / ORGANISATION / APP_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass
class AppConfig:
    scale_ip: str = "10.0.0.112"
    scale_port: int = 4001
    poll_interval_s: float = 0.25
    balance_id: str = ""
    balance_readability_mg: float = 0.001
    operator: str = ""
    theme: str = "dark"
    default_temperature_c: float = 22.0
    default_humidity_pct: float = 50.0
    default_pressure_hpa: float = 1013.25
    pdf_folder: str = ""
    email_to: str = ""
    demo_mode: bool = False
    place_of_calibration: str = "LifeGene Lab, Mevo Horon, Israel"
    next_calibration_months: int = 12

    @classmethod
    def path(cls) -> Path:
        return app_data_dir() / "config.json"

    @classmethod
    def load(cls) -> "AppConfig":
        cfg = cls()
        try:
            data = json.loads(cls.path().read_text(encoding="utf-8"))
        except FileNotFoundError:
            return cfg
        except (OSError, ValueError) as exc:
            log.warning("could not read config: %s", exc)
            return cfg
        known = {f.name: f.type for f in dataclasses.fields(cls)}
        for key, value in data.items():
            if key in known:
                setattr(cfg, key, value)
        return cfg

    def save(self) -> None:
        try:
            self.path().write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        except OSError as exc:
            log.warning("could not save config: %s", exc)


@dataclass
class CalibrationRecord:
    document_no: str
    calibrated_at: str          # ISO date-time
    model: str
    serial_no: str
    tip: str
    verdict: str
    operator: str
    payload: dict                # full result (levels, env, etc.) for re-printing
    id: int | None = None


class History:
    """SQLite-backed store of completed calibrations."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or app_data_dir() / "history.sqlite"
        self._conn = sqlite3.connect(str(self.path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS calibrations (
                   id            INTEGER PRIMARY KEY AUTOINCREMENT,
                   document_no   TEXT UNIQUE NOT NULL,
                   calibrated_at TEXT NOT NULL,
                   model         TEXT NOT NULL,
                   serial_no     TEXT,
                   tip           TEXT,
                   verdict       TEXT NOT NULL,
                   operator      TEXT,
                   payload       TEXT NOT NULL
               )""")
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def next_document_number(self, on: date | None = None) -> str:
        """LG-CAL-YYYY-NNNN, sequential within the calendar year."""
        year = (on or date.today()).year
        prefix = f"{DOC_PREFIX}-{year}-"
        row = self._conn.execute(
            "SELECT document_no FROM calibrations WHERE document_no LIKE ? "
            "ORDER BY document_no DESC LIMIT 1", (prefix + "%",)).fetchone()
        last = int(row["document_no"].rsplit("-", 1)[1]) if row else 0
        return f"{prefix}{last + 1:04d}"

    def add(self, rec: CalibrationRecord) -> int:
        cur = self._conn.execute(
            "INSERT INTO calibrations (document_no, calibrated_at, model, serial_no, tip, "
            "verdict, operator, payload) VALUES (?,?,?,?,?,?,?,?)",
            (rec.document_no, rec.calibrated_at, rec.model, rec.serial_no, rec.tip,
             rec.verdict, rec.operator, json.dumps(rec.payload)))
        self._conn.commit()
        rec.id = cur.lastrowid
        return rec.id

    def list(self, limit: int = 200, search: str = "") -> list[CalibrationRecord]:
        like = f"%{search.strip()}%"
        rows = self._conn.execute(
            "SELECT * FROM calibrations WHERE document_no LIKE ? OR serial_no LIKE ? "
            "OR model LIKE ? ORDER BY calibrated_at DESC, id DESC LIMIT ?",
            (like, like, like, limit)).fetchall()
        return [self._to_record(r) for r in rows]

    def get(self, record_id: int) -> CalibrationRecord | None:
        row = self._conn.execute("SELECT * FROM calibrations WHERE id = ?",
                                 (record_id,)).fetchone()
        return self._to_record(row) if row else None

    def last_for_serial(self, serial_no: str) -> CalibrationRecord | None:
        if not serial_no.strip():
            return None
        row = self._conn.execute(
            "SELECT * FROM calibrations WHERE serial_no = ? "
            "ORDER BY calibrated_at DESC LIMIT 1", (serial_no.strip(),)).fetchone()
        return self._to_record(row) if row else None

    @staticmethod
    def _to_record(row: sqlite3.Row) -> CalibrationRecord:
        return CalibrationRecord(
            id=row["id"], document_no=row["document_no"], calibrated_at=row["calibrated_at"],
            model=row["model"], serial_no=row["serial_no"] or "", tip=row["tip"] or "",
            verdict=row["verdict"], operator=row["operator"] or "",
            payload=json.loads(row["payload"]))


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat(sep=" ")
