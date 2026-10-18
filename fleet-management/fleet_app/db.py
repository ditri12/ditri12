"""שכבת הנתונים: SQLite דרך הספרייה המובנית של פייתון."""
from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path
from typing import Optional

from .calc import Settings, to_date

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS vehicles (
  id                 INTEGER PRIMARY KEY AUTOINCREMENT,
  plate              TEXT NOT NULL UNIQUE,
  make               TEXT,
  model              TEXT,
  year               INTEGER,
  driver             TEXT,
  test_expiry        TEXT,
  insurance_expiry   TEXT,
  mileage_year_start TEXT,
  notes              TEXT,
  active             INTEGER NOT NULL DEFAULT 1,
  created_at         TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS odometer_readings (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  vehicle_id   INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
  reading_date TEXT NOT NULL,
  km           INTEGER NOT NULL,
  note         TEXT,
  created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_readings_vehicle ON odometer_readings(vehicle_id, reading_date);
CREATE TABLE IF NOT EXISTS services (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  vehicle_id   INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
  service_date TEXT NOT NULL,
  odometer_km  INTEGER,
  garage       TEXT,
  description  TEXT,
  cost         REAL,
  created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_services_vehicle ON services(vehicle_id, service_date);
CREATE TABLE IF NOT EXISTS repairs (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  vehicle_id   INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
  repair_date  TEXT NOT NULL,
  odometer_km  INTEGER,
  garage       TEXT,
  description  TEXT NOT NULL,
  cost         REAL,
  created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_repairs_vehicle ON repairs(vehicle_id, repair_date);
"""


class ValidationError(Exception):
    """שגיאת קלט שמוצגת למשתמש כפי שהיא."""


# ---------- ולידציה ----------

def _opt_date(v, field) -> Optional[str]:
    if v in (None, ""):
        return None
    if isinstance(v, date):
        return v.isoformat()
    d = to_date(v)
    if d is None:
        raise ValidationError(f"תאריך לא תקין בשדה {field}")
    return d.isoformat()


def _req_date(v, field) -> str:
    d = _opt_date(v, field)
    if not d:
        raise ValidationError(f"חובה להזין {field}")
    return d


def _opt_int(v, field, minimum=0) -> Optional[int]:
    if v in (None, ""):
        return None
    try:
        n = int(str(v).replace(",", "").strip())
    except ValueError:
        raise ValidationError(f"ערך לא תקין בשדה {field}")
    if n < minimum:
        raise ValidationError(f"ערך לא תקין בשדה {field}")
    return n


def _req_int(v, field, minimum=0) -> int:
    n = _opt_int(v, field, minimum)
    if n is None:
        raise ValidationError(f"חובה להזין {field}")
    return n


def _opt_num(v, field) -> Optional[float]:
    if v in (None, ""):
        return None
    try:
        n = float(str(v).replace(",", "").strip())
    except ValueError:
        raise ValidationError(f"ערך לא תקין בשדה {field}")
    if n < 0:
        raise ValidationError(f"ערך לא תקין בשדה {field}")
    return n


def _opt_text(v, max_len=2000) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return s[:max_len] if s else None


def _req_text(v, field, max_len=2000) -> str:
    s = _opt_text(v, max_len)
    if not s:
        raise ValidationError(f"חובה להזין {field}")
    return s


def normalize_plate(v) -> str:
    s = "".join(ch for ch in str(v or "") if ch.isalnum())
    if not s:
        raise ValidationError("חובה להזין מספר רישוי")
    return s[:20]


def format_plate(p: str) -> str:
    """מציג מספר רישוי ישראלי עם מקפים: 12-345-67 או 123-45-678."""
    s = str(p or "")
    if s.isdigit() and len(s) == 7:
        return f"{s[:2]}-{s[2:5]}-{s[5:]}"
    if s.isdigit() and len(s) == 8:
        return f"{s[:3]}-{s[3:5]}-{s[5:]}"
    return s


# ---------- Repo ----------

class Repo:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path), timeout=10)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        # יומן DELETE (ברירת המחדל) ולא WAL: WAL אינו אמין על תיקיות רשת משותפות (SMB),
        # והנפח כאן קטן כך שאין צורך בו.
        self.conn.execute("PRAGMA journal_mode = DELETE")
        self.conn.executescript(SCHEMA)
        with self.conn:
            for k, v in Settings().to_dict().items():
                self.conn.execute("INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", (k, str(v)))

    def close(self):
        self.conn.close()

    def has_data(self) -> bool:
        return self.conn.execute("SELECT COUNT(*) FROM vehicles").fetchone()[0] > 0

    def copy_to(self, dest: str | Path) -> None:
        """העתקה בטוחה של כל הנתונים לקובץ אחר (לדוגמה לתיקיית רשת)."""
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        target = sqlite3.connect(str(dest))
        try:
            with target:
                self.conn.backup(target)
        finally:
            target.close()

    # ----- settings -----
    def get_settings(self) -> Settings:
        rows = self.conn.execute("SELECT key, value FROM settings").fetchall()
        return Settings.from_dict({r["key"]: r["value"] for r in rows})

    def update_settings(self, s: Settings) -> None:
        for k, v in s.to_dict().items():
            if int(v) < 0:
                raise ValidationError("ערכי ההגדרות חייבים להיות חיוביים")
        with self.conn:
            for k, v in s.to_dict().items():
                self.conn.execute("INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (k, str(int(v))))

    # ----- vehicles -----
    def list_vehicles(self, include_inactive=True) -> list[dict]:
        sql = "SELECT * FROM vehicles" + ("" if include_inactive else " WHERE active = 1") + " ORDER BY plate"
        return [dict(r) for r in self.conn.execute(sql)]

    def get_vehicle(self, vid: int) -> dict:
        r = self.conn.execute("SELECT * FROM vehicles WHERE id = ?", (vid,)).fetchone()
        if not r:
            raise ValidationError("רכב לא נמצא")
        return dict(r)

    @staticmethod
    def _vehicle_fields(data: dict) -> dict:
        return {
            "plate": normalize_plate(data.get("plate")),
            "make": _opt_text(data.get("make"), 60),
            "model": _opt_text(data.get("model"), 60),
            "year": _opt_int(data.get("year"), "שנת ייצור", minimum=1950),
            "driver": _opt_text(data.get("driver"), 100),
            "test_expiry": _opt_date(data.get("test_expiry"), "תוקף טסט"),
            "insurance_expiry": _opt_date(data.get("insurance_expiry"), "תוקף ביטוח"),
            "mileage_year_start": _opt_date(data.get("mileage_year_start"), "תחילת שנת נסועה"),
            "notes": _opt_text(data.get("notes")),
        }

    def create_vehicle(self, data: dict) -> int:
        f = self._vehicle_fields(data)
        if self.conn.execute("SELECT 1 FROM vehicles WHERE plate = ?", (f["plate"],)).fetchone():
            raise ValidationError("כבר קיים רכב עם מספר רישוי זה")
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO vehicles(plate, make, model, year, driver, test_expiry, insurance_expiry, mileage_year_start, notes) "
                "VALUES (:plate, :make, :model, :year, :driver, :test_expiry, :insurance_expiry, :mileage_year_start, :notes)", f)
            vid = cur.lastrowid
            if data.get("initial_km") not in (None, ""):
                self._insert_reading(vid, {"reading_date": data.get("initial_km_date") or date.today(), "km": data["initial_km"], "note": "קריאה ראשונית"})
            if data.get("last_service_date"):
                self._insert_service(vid, {
                    "service_date": data["last_service_date"], "odometer_km": data.get("last_service_km"),
                    "garage": data.get("last_service_garage"), "description": data.get("last_service_description"),
                    "cost": data.get("last_service_cost"),
                })
        return vid

    def update_vehicle(self, vid: int, data: dict) -> None:
        self.get_vehicle(vid)
        f = self._vehicle_fields(data)
        if self.conn.execute("SELECT 1 FROM vehicles WHERE plate = ? AND id <> ?", (f["plate"], vid)).fetchone():
            raise ValidationError("כבר קיים רכב אחר עם מספר רישוי זה")
        f["id"] = vid
        f["active"] = None if data.get("active") is None else (1 if data["active"] else 0)
        with self.conn:
            self.conn.execute(
                "UPDATE vehicles SET plate=:plate, make=:make, model=:model, year=:year, driver=:driver, test_expiry=:test_expiry, "
                "insurance_expiry=:insurance_expiry, mileage_year_start=:mileage_year_start, notes=:notes, "
                "active=COALESCE(:active, active) WHERE id=:id", f)

    def set_active(self, vid: int, active: bool) -> None:
        with self.conn:
            self.conn.execute("UPDATE vehicles SET active = ? WHERE id = ?", (1 if active else 0, vid))

    def delete_vehicle(self, vid: int) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM vehicles WHERE id = ?", (vid,))

    # ----- history -----
    def readings(self, vid: int) -> list[dict]:
        return [dict(r) for r in self.conn.execute("SELECT * FROM odometer_readings WHERE vehicle_id = ? ORDER BY reading_date DESC, id DESC", (vid,))]

    def services(self, vid: int) -> list[dict]:
        return [dict(r) for r in self.conn.execute("SELECT * FROM services WHERE vehicle_id = ? ORDER BY service_date DESC, id DESC", (vid,))]

    def repairs(self, vid: int) -> list[dict]:
        return [dict(r) for r in self.conn.execute("SELECT * FROM repairs WHERE vehicle_id = ? ORDER BY repair_date DESC, id DESC", (vid,))]

    def history_all(self) -> dict[str, dict[int, list[dict]]]:
        out = {"readings": {}, "services": {}, "repairs": {}}
        for key, table in (("readings", "odometer_readings"), ("services", "services"), ("repairs", "repairs")):
            for r in self.conn.execute(f"SELECT * FROM {table}"):
                out[key].setdefault(r["vehicle_id"], []).append(dict(r))
        return out

    def max_reading_before(self, vid: int, d: str) -> Optional[int]:
        r = self.conn.execute("SELECT MAX(km) AS km FROM odometer_readings WHERE vehicle_id = ? AND reading_date < ?", (vid, d)).fetchone()
        return r["km"] if r and r["km"] is not None else None

    def min_reading_after(self, vid: int, d: str) -> Optional[int]:
        r = self.conn.execute("SELECT MIN(km) AS km FROM odometer_readings WHERE vehicle_id = ? AND reading_date > ?", (vid, d)).fetchone()
        return r["km"] if r and r["km"] is not None else None

    def _insert_reading(self, vid: int, data: dict) -> int:
        row = {
            "vehicle_id": vid,
            "reading_date": _req_date(data.get("reading_date"), "תאריך קריאה"),
            "km": _req_int(data.get("km"), "קילומטראז׳"),
            "note": _opt_text(data.get("note"), 300),
        }
        # בדיקת סבירות - גם להזנה רטרואקטיבית: הערך חייב להיות בין הקריאה שלפניו לקריאה שאחריו
        if not data.get("force"):
            prev = self.max_reading_before(vid, row["reading_date"])
            if prev is not None and row["km"] < prev:
                raise ValidationError(f"הקילומטראז׳ ({row['km']:,}) נמוך מקריאה קודמת ({prev:,}). בדקו את הערך.")
            nxt = self.min_reading_after(vid, row["reading_date"])
            if nxt is not None and row["km"] > nxt:
                raise ValidationError(f"הקילומטראז׳ ({row['km']:,}) גבוה מקריאה מאוחרת יותר ({nxt:,}). בדקו את הערך.")
        cur = self.conn.execute("INSERT INTO odometer_readings(vehicle_id, reading_date, km, note) VALUES (:vehicle_id, :reading_date, :km, :note)", row)
        return cur.lastrowid

    def add_reading(self, vid: int, data: dict) -> int:
        self.get_vehicle(vid)
        with self.conn:
            return self._insert_reading(vid, data)

    def delete_reading(self, rid: int) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM odometer_readings WHERE id = ?", (rid,))

    def _insert_service(self, vid: int, data: dict) -> int:
        row = {
            "vehicle_id": vid,
            "service_date": _req_date(data.get("service_date"), "תאריך טיפול"),
            "odometer_km": _opt_int(data.get("odometer_km"), "קילומטראז׳ בטיפול"),
            "garage": _opt_text(data.get("garage"), 120),
            "description": _opt_text(data.get("description")),
            "cost": _opt_num(data.get("cost"), "עלות"),
        }
        cur = self.conn.execute(
            "INSERT INTO services(vehicle_id, service_date, odometer_km, garage, description, cost) "
            "VALUES (:vehicle_id, :service_date, :odometer_km, :garage, :description, :cost)", row)
        return cur.lastrowid

    def add_service(self, vid: int, data: dict) -> int:
        self.get_vehicle(vid)
        with self.conn:
            return self._insert_service(vid, data)

    def update_service(self, sid: int, data: dict) -> None:
        row = {
            "id": sid,
            "service_date": _req_date(data.get("service_date"), "תאריך טיפול"),
            "odometer_km": _opt_int(data.get("odometer_km"), "קילומטראז׳ בטיפול"),
            "garage": _opt_text(data.get("garage"), 120),
            "description": _opt_text(data.get("description")),
            "cost": _opt_num(data.get("cost"), "עלות"),
        }
        with self.conn:
            self.conn.execute("UPDATE services SET service_date=:service_date, odometer_km=:odometer_km, garage=:garage, description=:description, cost=:cost WHERE id=:id", row)

    def delete_service(self, sid: int) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM services WHERE id = ?", (sid,))

    def add_repair(self, vid: int, data: dict) -> int:
        self.get_vehicle(vid)
        row = {
            "vehicle_id": vid,
            "repair_date": _req_date(data.get("repair_date"), "תאריך תיקון"),
            "odometer_km": _opt_int(data.get("odometer_km"), "קילומטראז׳ בתיקון"),
            "garage": _opt_text(data.get("garage"), 120),
            "description": _req_text(data.get("description"), "תיאור התיקון"),
            "cost": _opt_num(data.get("cost"), "עלות"),
        }
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO repairs(vehicle_id, repair_date, odometer_km, garage, description, cost) "
                "VALUES (:vehicle_id, :repair_date, :odometer_km, :garage, :description, :cost)", row)
            return cur.lastrowid

    def update_repair(self, rid: int, data: dict) -> None:
        row = {
            "id": rid,
            "repair_date": _req_date(data.get("repair_date"), "תאריך תיקון"),
            "odometer_km": _opt_int(data.get("odometer_km"), "קילומטראז׳ בתיקון"),
            "garage": _opt_text(data.get("garage"), 120),
            "description": _req_text(data.get("description"), "תיאור התיקון"),
            "cost": _opt_num(data.get("cost"), "עלות"),
        }
        with self.conn:
            self.conn.execute("UPDATE repairs SET repair_date=:repair_date, odometer_km=:odometer_km, garage=:garage, description=:description, cost=:cost WHERE id=:id", row)

    def delete_repair(self, rid: int) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM repairs WHERE id = ?", (rid,))

    def garages(self) -> list[str]:
        rows = self.conn.execute(
            "SELECT garage FROM (SELECT garage FROM services UNION SELECT garage FROM repairs) "
            "WHERE garage IS NOT NULL AND garage <> '' ORDER BY garage").fetchall()
        return [r["garage"] for r in rows]

    def drivers(self) -> list[str]:
        rows = self.conn.execute("SELECT DISTINCT driver FROM vehicles WHERE driver IS NOT NULL AND driver <> '' ORDER BY driver").fetchall()
        return [r["driver"] for r in rows]
