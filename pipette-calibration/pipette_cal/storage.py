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
import re
import logging
import os
import sqlite3
import sys
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta
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
    operator: str = "Dmitri Trakhtman"     # "Calibrated by" on the certificate
    signer_name: str = "Dmitri Trakhtman"   # person who signs the certificate (printed next to the signature)
    theme: str = "dark"
    default_temperature_c: float = 22.0
    default_humidity_pct: float = 50.0
    default_pressure_hpa: float = 1013.25
    pdf_folder: str = ""
    email_to: str = ""
    demo_mode: bool = False
    auto_connect: bool = True        # try the saved balance address when the program starts
    start_with_windows: bool = True  # register in the user's Run key (applied on first start / Settings)
    auto_capture: bool = True        # save a reading automatically once it is stable
    auto_stable_seconds: float = 2.0     # reading must be unchanged this long (balance flag stable)
    auto_unflagged_seconds: float = 4.0  # ... or this long when the balance never flags stable
    auto_small_mass_mg: float = 15.0     # below this expected mass the stricter small-volume rules apply
    auto_stable_seconds_small: float = 4.0    # stable window for small volumes (P2, P10, P20 low)
    auto_unflagged_seconds_small: float = 8.0 # fallback without the balance flag for small volumes
    reminder_email_to: str = "naama@lifegene.co.il"   # office address: copied on every customer reminder
    email_cc: str = "naama@lifegene.co.il"            # office copy on certificate e-mails
    reminder_days_before: int = 30       # how long before the due date the reminder goes out
    reminder_auto_send: bool = True      # send through Outlook without opening the draft
    reminder_repeat_days: int = 365      # never e-mail the same customer address again within this period
    place_of_calibration: str = "LifeGene Lab, Mevo Horon, Israel"
    next_calibration_months: int = 12
    procedure: str = "W-004-04 Calibration of Pipette"   # "Standard" line on the certificate
    default_air_temperature_c: float = 22.0

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
        if cfg.operator.strip() in ("", "LifeGene Technical Service"):
            cfg.operator = cls.operator          # settings saved by an earlier version
        if cfg.reminder_email_to.strip() in ("", "info@lifegene.co.il"):
            cfg.reminder_email_to = cls.reminder_email_to
        if cfg.auto_stable_seconds <= 1.5 and cfg.auto_unflagged_seconds <= 3.0:
            cfg.auto_stable_seconds, cfg.auto_unflagged_seconds = cls.auto_stable_seconds, cls.auto_unflagged_seconds
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
    customer: str = ""
    customer_email: str = ""
    next_calibration: str = ""   # ISO date
    no_reminder: bool = False    # excluded from the recalibration reminders
    contact_name: str = ""       # person at the customer addressed in e-mails


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
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS reminders (
                   document_no TEXT PRIMARY KEY,
                   sent_at     TEXT NOT NULL,
                   sent_to     TEXT
               )""")
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS reminder_sends (
                   id           INTEGER PRIMARY KEY AUTOINCREMENT,
                   email        TEXT NOT NULL,
                   sent_at      TEXT NOT NULL,
                   document_nos TEXT
               )""")
        self._migrate()
        self._conn.commit()

    def _migrate(self) -> None:
        """Add columns introduced after the first release."""
        cols = {r["name"] for r in self._conn.execute("PRAGMA table_info(calibrations)")}
        for name in ("customer", "customer_email", "next_calibration"):
            if name not in cols:
                self._conn.execute(f"ALTER TABLE calibrations ADD COLUMN {name} TEXT DEFAULT ''")
        if "no_reminder" not in cols:
            self._conn.execute("ALTER TABLE calibrations ADD COLUMN no_reminder INTEGER DEFAULT 0")
        if "contact_name" not in cols:
            self._conn.execute("ALTER TABLE calibrations ADD COLUMN contact_name TEXT DEFAULT ''")
        if "next_calibration" not in cols:          # back-fill from the stored payload
            for row in self._conn.execute("SELECT id, payload FROM calibrations").fetchall():
                try:
                    nxt = json.loads(row["payload"]).get("next_calibration_date", "")
                except ValueError:
                    nxt = ""
                self._conn.execute("UPDATE calibrations SET next_calibration = ? WHERE id = ?", (nxt, row["id"]))

    def close(self) -> None:
        self._conn.close()

    def next_document_number(self, on: date | None = None) -> str:
        """LG-CAL-YYYY-NNNN, sequential within the calendar year."""
        year = (on or date.today()).year
        prefix = f"{DOC_PREFIX}-{year}-"
        # Highest sequence number in this year. Recalibration numbers carry an
        # "-R1" suffix and edited numbers may carry anything, so parse with a
        # pattern instead of trusting the last "-" segment.
        pattern = re.compile(re.escape(prefix) + r"(\d+)(?:-R\d+)?$")
        last = 0
        for row in self._conn.execute("SELECT document_no FROM calibrations WHERE document_no LIKE ?",
                                      (prefix + "%",)):
            m = pattern.match(row["document_no"].strip())
            if m:
                last = max(last, int(m.group(1)))
        return f"{prefix}{last + 1:04d}"

    def add(self, rec: CalibrationRecord) -> int:
        cur = self._conn.execute(
            "INSERT INTO calibrations (document_no, calibrated_at, model, serial_no, tip, "
            "verdict, operator, payload, customer, customer_email, next_calibration, no_reminder, contact_name) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (rec.document_no, rec.calibrated_at, rec.model, rec.serial_no, rec.tip,
             rec.verdict, rec.operator, json.dumps(rec.payload), rec.customer, rec.customer_email,
             rec.next_calibration or rec.payload.get("next_calibration_date", ""), int(rec.no_reminder),
             rec.contact_name))
        self._conn.commit()
        rec.id = cur.lastrowid
        return rec.id

    def list(self, limit: int = 200, search: str = "") -> list[CalibrationRecord]:
        like = f"%{search.strip()}%"
        rows = self._conn.execute(
            "SELECT * FROM calibrations WHERE document_no LIKE ? OR serial_no LIKE ? "
            "OR model LIKE ? OR customer LIKE ? OR contact_name LIKE ? ORDER BY calibrated_at DESC, id DESC LIMIT ?",
            (like, like, like, like, like, limit)).fetchall()
        return [self._to_record(r) for r in rows]

    # ---- recalibration reminders ---------------------------------------
    def due_for_reminder(self, days_before: int, today: date | None = None) -> list[CalibrationRecord]:
        """Latest calibration of each serial number whose next calibration is
        due within *days_before* days (or already overdue) and that has not
        been reminded yet."""
        today = today or date.today()
        horizon = (today + timedelta(days=days_before)).isoformat()
        rows = self._conn.execute(
            "SELECT c.* FROM calibrations c "
            "WHERE c.next_calibration != '' AND c.next_calibration <= ? "
            "AND COALESCE(c.no_reminder, 0) = 0 "
            "AND c.document_no NOT IN (SELECT document_no FROM reminders) "
            "AND c.id = (SELECT MAX(id) FROM calibrations c2 WHERE c2.serial_no = c.serial_no) "
            "ORDER BY c.next_calibration", (horizon,)).fetchall()
        return [self._to_record(r) for r in rows]

    def delete(self, record_ids: list[int]) -> int:
        """Delete calibrations (and their reminder marks). Returns the number removed."""
        if not record_ids:
            return 0
        marks = [r["document_no"] for r in self._conn.execute(
            f"SELECT document_no FROM calibrations WHERE id IN ({','.join('?' * len(record_ids))})", record_ids)]
        if marks:
            self._conn.execute(f"DELETE FROM reminders WHERE document_no IN ({','.join('?' * len(marks))})", marks)
        cur = self._conn.execute(f"DELETE FROM calibrations WHERE id IN ({','.join('?' * len(record_ids))})", record_ids)
        self._conn.commit()
        return cur.rowcount

    def update_customer(self, record_ids: list[int], customer: str | None = None,
                        contact_name: str | None = None, customer_email: str | None = None) -> int:
        """Fill in / change customer details of existing calibrations. A None
        argument leaves that field untouched. The stored payload is updated as
        well so re-created certificates show the new customer."""
        if not record_ids:
            return 0
        n = 0
        for rid in record_ids:
            row = self._conn.execute("SELECT * FROM calibrations WHERE id = ?", (rid,)).fetchone()
            if not row:
                continue
            payload = json.loads(row["payload"])
            values = {
                "customer": row["customer"] if customer is None else customer.strip(),
                "contact_name": (row["contact_name"] or "") if contact_name is None else contact_name.strip(),
                "customer_email": row["customer_email"] if customer_email is None else customer_email.strip(),
            }
            payload.update(values)
            self._conn.execute(
                "UPDATE calibrations SET customer = ?, contact_name = ?, customer_email = ?, payload = ? WHERE id = ?",
                (values["customer"], values["contact_name"], values["customer_email"], json.dumps(payload), rid))
            n += 1
        self._conn.commit()
        return n

    def mark_superseded(self, record_id: int, by_document_no: str) -> None:
        """A failed (as-found) attempt replaced by a recalibration after adjustment:
        excluded from reminders and labelled in the history."""
        row = self._conn.execute("SELECT payload FROM calibrations WHERE id = ?", (record_id,)).fetchone()
        if not row:
            return
        payload = json.loads(row["payload"])
        payload["superseded_by"] = by_document_no
        self._conn.execute("UPDATE calibrations SET payload = ?, no_reminder = 1 WHERE id = ?",
                           (json.dumps(payload), record_id))
        self._conn.commit()

    def recalibration_document_number(self, original: str) -> str:
        """LG-CAL-2026-0003 -> LG-CAL-2026-0003-R1 (R2, R3 ... if those exist already)."""
        base = re.sub(r"-R\d+$", "", original.strip())
        n = 1
        while self._conn.execute("SELECT 1 FROM calibrations WHERE document_no = ?", (f"{base}-R{n}",)).fetchone():
            n += 1
        return f"{base}-R{n}"

    def set_no_reminder(self, record_ids: list[int], value: bool) -> None:
        if record_ids:
            self._conn.execute(f"UPDATE calibrations SET no_reminder = ? WHERE id IN ({','.join('?' * len(record_ids))})",
                               [int(value)] + list(record_ids))
            self._conn.commit()

    def mark_reminded(self, document_no: str, sent_to: str) -> None:
        self._conn.execute("INSERT OR REPLACE INTO reminders (document_no, sent_at, sent_to) VALUES (?,?,?)",
                           (document_no, now_iso(), sent_to))
        self._conn.commit()

    def reminder_marks(self) -> dict[str, tuple[str, str]]:
        """document_no -> (sent_at, sent_to) for every reminded certificate."""
        return {r["document_no"]: (r["sent_at"], r["sent_to"] or "")
                for r in self._conn.execute("SELECT * FROM reminders")}

    def last_reminder_to(self, email: str) -> str | None:
        """ISO timestamp of the last reminder e-mail sent to *email* (case-insensitive)."""
        row = self._conn.execute("SELECT sent_at FROM reminder_sends WHERE lower(email) = lower(?) "
                                 "ORDER BY sent_at DESC LIMIT 1", (email.strip(),)).fetchone()
        return row["sent_at"] if row else None

    def record_reminder_send(self, email: str, document_nos: list[str]) -> None:
        self._conn.execute("INSERT INTO reminder_sends (email, sent_at, document_nos) VALUES (?,?,?)",
                           (email.strip(), now_iso(), ", ".join(document_nos)))
        self._conn.commit()

    def same_customer_same_day(self, rec: CalibrationRecord) -> list[CalibrationRecord]:
        """All calibrations of rec's customer (by e-mail, else by name) made on
        the same day as rec, excluding superseded as-found attempts."""
        day = rec.calibrated_at[:10]
        if rec.customer_email.strip():
            rows = self._conn.execute(
                "SELECT * FROM calibrations WHERE lower(customer_email) = lower(?) AND substr(calibrated_at, 1, 10) = ? "
                "ORDER BY id", (rec.customer_email.strip(), day)).fetchall()
        elif rec.customer.strip():
            rows = self._conn.execute(
                "SELECT * FROM calibrations WHERE customer = ? AND substr(calibrated_at, 1, 10) = ? ORDER BY id",
                (rec.customer.strip(), day)).fetchall()
        else:
            rows = self._conn.execute("SELECT * FROM calibrations WHERE id = ?", (rec.id,)).fetchall()
        return [r for r in (self._to_record(x) for x in rows) if not r.payload.get("superseded_by")]

    def get_by_document(self, document_no: str) -> CalibrationRecord | None:
        row = self._conn.execute("SELECT * FROM calibrations WHERE document_no = ?",
                                 (document_no.strip(),)).fetchone()
        return self._to_record(row) if row else None

    def replace(self, rec: CalibrationRecord) -> int:
        """Overwrite the record that has rec.document_no (same pipette calculated
        again, e.g. after a corrected weight). Returns its id."""
        existing = self.get_by_document(rec.document_no)
        if existing is None:
            return self.add(rec)
        self._conn.execute(
            "UPDATE calibrations SET calibrated_at = ?, model = ?, serial_no = ?, tip = ?, verdict = ?, "
            "operator = ?, payload = ?, customer = ?, customer_email = ?, next_calibration = ?, "
            "no_reminder = ?, contact_name = ? WHERE id = ?",
            (rec.calibrated_at, rec.model, rec.serial_no, rec.tip, rec.verdict, rec.operator,
             json.dumps(rec.payload), rec.customer, rec.customer_email,
             rec.next_calibration or rec.payload.get("next_calibration_date", ""), int(rec.no_reminder),
             rec.contact_name, existing.id))
        self._conn.commit()
        rec.id = existing.id
        return rec.id

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
            payload=json.loads(row["payload"]), customer=row["customer"] or "",
            customer_email=row["customer_email"] or "", next_calibration=row["next_calibration"] or "",
            no_reminder=bool(row["no_reminder"]) if "no_reminder" in row.keys() else False,
            contact_name=(row["contact_name"] or "") if "contact_name" in row.keys() else "")


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat(sep=" ")
