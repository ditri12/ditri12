from datetime import date

from pipette_cal.reminders import build_reminder, check_and_send
from pipette_cal.storage import AppConfig, CalibrationRecord, History


def _rec(doc, serial, cal, nxt, customer="Lab A", email="lab@example.com"):
    return CalibrationRecord(doc, f"{cal} 10:00:00", "P200", serial, "DF200", "PASS", "op",
                             {"next_calibration_date": nxt}, customer=customer, customer_email=email,
                             next_calibration=nxt)


def test_due_for_reminder_picks_latest_per_serial_and_only_once(tmp_path):
    h = History(tmp_path / "h.sqlite")
    h.add(_rec("LG-CAL-2025-0001", "SN-1", "2025-11-20", "2026-11-20"))   # due in 8 days
    h.add(_rec("LG-CAL-2025-0002", "SN-2", "2025-12-30", "2026-12-30"))   # due in 48 days
    h.add(_rec("LG-CAL-2025-0003", "SN-1", "2026-03-01", "2027-03-01"))   # SN-1 recalibrated -> not due
    h.add(_rec("LG-CAL-2024-0009", "SN-3", "2024-10-01", "2025-10-01"))   # overdue
    today = date(2026, 11, 12)
    due = h.due_for_reminder(30, today)
    assert [r.document_no for r in due] == ["LG-CAL-2024-0009"]          # SN-1 superseded, SN-2 too far
    h.mark_reminded("LG-CAL-2024-0009", "office@example.com")
    assert h.due_for_reminder(30, today) == []
    assert [r.document_no for r in h.due_for_reminder(60, today)] == ["LG-CAL-2025-0002"]
    h.close()


def test_build_reminder_lists_customer_and_status():
    subject, body, html = build_reminder([_rec("LG-CAL-2025-0001", "SN-1", "2025-11-20", "2026-11-20"),
                                          _rec("LG-CAL-2024-0009", "SN-3", "2024-10-01", "2025-10-01")],
                                         date(2026, 11, 12))
    assert "2 pipettes" in subject
    assert "SN-1" in body and "Lab A" in body and "in 8 days" in body and "OVERDUE" in body
    assert "<table" in html and "lab@example.com" in html


def test_check_and_send_without_address_or_without_due(tmp_path, monkeypatch):
    h = History(tmp_path / "h.sqlite")
    cfg = AppConfig()
    assert check_and_send(h, cfg)[0] == 0
    cfg.reminder_email_to = "office@example.com"
    assert check_and_send(h, cfg)[0] == 0
    h.add(_rec("LG-CAL-2025-0001", "SN-1", "2025-11-20", "2026-11-20"))
    sent = {}

    def fake_compose(to, subject, body, attachments, send=False, html=None):
        sent.update(to=to, subject=subject, send=send, n=len(attachments))
        return "ok"
    monkeypatch.setattr("pipette_cal.reminders.compose_email", fake_compose)
    n, msg = check_and_send(h, cfg, date(2026, 11, 12))
    assert n == 1 and sent["to"] == "office@example.com" and sent["send"] is True and sent["n"] == 0
    assert check_and_send(h, cfg, date(2026, 11, 12))[0] == 0      # reminded only once
    h.close()


def test_history_migration_adds_columns(tmp_path):
    import sqlite3
    db = tmp_path / "old.sqlite"
    con = sqlite3.connect(db)
    con.execute("""CREATE TABLE calibrations (id INTEGER PRIMARY KEY AUTOINCREMENT, document_no TEXT UNIQUE NOT NULL,
                   calibrated_at TEXT NOT NULL, model TEXT NOT NULL, serial_no TEXT, tip TEXT, verdict TEXT NOT NULL,
                   operator TEXT, payload TEXT NOT NULL)""")
    con.execute("INSERT INTO calibrations (document_no, calibrated_at, model, serial_no, tip, verdict, operator, payload) "
                "VALUES ('LG-CAL-2025-0001','2025-11-20 10:00:00','P200','SN-1','DF200','PASS','op',"
                "'{\"next_calibration_date\": \"2026-11-20\"}')")
    con.commit(); con.close()
    h = History(db)
    rec = h.list()[0]
    assert rec.next_calibration == "2026-11-20" and rec.customer == ""
    assert [r.document_no for r in h.due_for_reminder(30, date(2026, 11, 12))] == ["LG-CAL-2025-0001"]
    h.close()
