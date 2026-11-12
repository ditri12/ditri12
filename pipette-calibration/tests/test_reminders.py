from datetime import date

from pipette_cal.reminders import build_customer_reminder, build_internal_reminder, check_and_send
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


def test_customer_reminder_is_hebrew_and_personal():
    a = _rec("LG-CAL-2025-0001", "SN-1", "2025-11-20", "2026-11-20")
    a.contact_name = "דניאל"
    subject, body, html = build_customer_reminder(
        [a, _rec("LG-CAL-2024-0009", "SN-3", "2024-10-01", "2025-10-01")], date(2026, 11, 12))
    assert subject.startswith("תזכורת") and "2 פיפטורים" in subject
    assert body.startswith("שלום דניאל,") and "הצעת מחיר" in body and "naama@lifegene.co.il" in body
    assert "SN-1" in body and "בעוד 8 ימים" in body and "עבר לפני" in body
    assert "dir='rtl'" in html and "naama@lifegene.co.il" in html
    assert 'color:#2e7db6">LIFE</span><span style="color:#77b957">GENE' in html   # brand word in logo colours
    assert "LifeGene Ltd" not in html                                               # Outlook signature follows
    # without a contact person the company name is used
    assert build_customer_reminder([_rec("LG-CAL-2025-0002", "SN-2", "2025-11-20", "2026-11-20")],
                                   date(2026, 11, 12))[1].startswith("שלום Lab A,")


def test_internal_reminder_for_missing_email():
    subject, body, html = build_internal_reminder([_rec("LG-CAL-2025-0001", "SN-1", "2025-11-20", "2026-11-20",
                                                        customer="Walk-in", email="")], date(2026, 11, 12))
    assert "without a customer e-mail" in subject and "Walk-in" in body and "<table" in html


def test_check_and_send_groups_by_customer_and_copies_office(tmp_path, monkeypatch):
    h = History(tmp_path / "h.sqlite")
    cfg = AppConfig()
    assert cfg.reminder_email_to == "naama@lifegene.co.il"
    assert check_and_send(h, cfg)[0] == 0
    h.add(_rec("LG-CAL-2025-0001", "SN-1", "2025-11-20", "2026-11-20", "Lab A", "a@example.com"))
    h.add(_rec("LG-CAL-2025-0002", "SN-2", "2025-11-21", "2026-11-21", "Lab A", "A@example.com"))
    h.add(_rec("LG-CAL-2025-0003", "SN-3", "2025-11-22", "2026-11-22", "Lab B", "b@example.com"))
    h.add(_rec("LG-CAL-2025-0004", "SN-4", "2025-11-23", "2026-11-23", "Walk-in", ""))
    sent = []

    def fake_compose(to, subject, body, attachments, send=False, html=None, cc=""):
        sent.append((to, cc, subject, send))
        return "ok"
    monkeypatch.setattr("pipette_cal.reminders.compose_email", fake_compose)
    n, msg = check_and_send(h, cfg, date(2026, 11, 12))
    assert n == 4 and len(sent) == 3
    assert ("a@example.com", "naama@lifegene.co.il") in {(t, c) for t, c, _, _ in sent}
    assert sum(1 for t, c, s_, _ in sent if t == "a@example.com" and "2 פיפטורים" in s_) == 1
    assert ("naama@lifegene.co.il", "") in {(t, c) for t, c, _, _ in sent}       # internal message
    assert all(send is True for *_, send in sent)
    assert check_and_send(h, cfg, date(2026, 11, 12))[0] == 0      # reminded only once
    # a new pipette of Lab A becomes due a month later: the customer was contacted
    # recently, so nothing is sent and the certificate is marked as covered
    h.add(_rec("LG-CAL-2025-0005", "SN-5", "2025-12-20", "2026-12-20", "Lab A", "a@example.com"))
    sent.clear()
    n, msg = check_and_send(h, cfg, date(2026, 12, 12))
    assert n == 0 and sent == [] and "skipped" in msg
    assert h.reminder_marks()["LG-CAL-2025-0005"][1].startswith("not sent")
    assert h.last_reminder_to("A@Example.com") is not None
    # after the repeat period the same customer may be contacted again
    h.add(_rec("LG-CAL-2026-0006", "SN-6", "2026-12-01", "2027-12-01", "Lab A", "a@example.com"))
    n, _ = check_and_send(h, cfg, date(2027, 11, 20))
    assert n == 1 and sent[0][0] == "a@example.com"
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


def test_delete_and_no_reminder_flag(tmp_path):
    h = History(tmp_path / "h.sqlite")
    a = _rec("LG-CAL-2025-0001", "SN-1", "2025-11-20", "2026-11-20")
    b = _rec("LG-CAL-2025-0002", "SN-2", "2025-11-21", "2026-11-21")
    c = _rec("LG-CAL-2025-0003", "SN-3", "2025-11-22", "2026-11-22")
    for r in (a, b, c):
        h.add(r)
    today = date(2026, 11, 12)
    assert len(h.due_for_reminder(30, today)) == 3
    h.set_no_reminder([b.id], True)
    assert h.get(b.id).no_reminder is True
    assert [r.serial_no for r in h.due_for_reminder(30, today)] == ["SN-1", "SN-3"]
    h.set_no_reminder([b.id], False)
    assert len(h.due_for_reminder(30, today)) == 3
    h.mark_reminded(a.document_no, "x")
    assert h.delete([a.id, c.id]) == 2
    assert [r.document_no for r in h.list()] == ["LG-CAL-2025-0002"]
    assert a.document_no not in h.reminder_marks()
    assert h.delete([]) == 0
    h.close()


def test_manual_reminder_ignores_flags_and_guards(tmp_path, monkeypatch):
    from pipette_cal.reminders import send_manual
    h = History(tmp_path / "h.sqlite")
    cfg = AppConfig()
    a = _rec("LG-CAL-2025-0001", "SN-1", "2025-11-20", "2026-11-20", "Lab A", "a@example.com")
    b = _rec("LG-CAL-2025-0002", "SN-2", "2025-11-21", "2026-11-21", "Walk-in", "")
    h.add(a); h.add(b)
    h.set_no_reminder([a.id], True)
    h.mark_reminded(a.document_no, "a@example.com; cc office")
    h.record_reminder_send("a@example.com", [a.document_no])
    sent = []
    monkeypatch.setattr("pipette_cal.reminders.compose_email",
                        lambda to, subject, body, attachments, send=False, html=None, cc="": sent.append((to, cc)) or "ok")
    msg = send_manual(h, cfg, [h.get(a.id)], date(2026, 11, 12))
    assert sent == [("a@example.com", "naama@lifegene.co.il")] and "1 pipette" in msg
    assert "(manual)" in h.reminder_marks()[a.document_no][1]
    import pytest
    with pytest.raises(ValueError):
        send_manual(h, cfg, [h.get(b.id)], date(2026, 11, 12))
    send_manual(h, cfg, [h.get(a.id), h.get(b.id)], date(2026, 11, 12), email_override="x@example.com")
    assert sent[-1][0] == "x@example.com"
    h.close()


def test_update_customer_details(tmp_path):
    h = History(tmp_path / "h.sqlite")
    a = _rec("LG-CAL-2025-0001", "SN-1", "2025-11-20", "2026-11-20", customer="", email="")
    b = _rec("LG-CAL-2025-0002", "SN-2", "2025-11-21", "2026-11-21", customer="Lab B", email="b@example.com")
    h.add(a); h.add(b)
    assert h.update_customer([a.id, b.id], customer="Hospital", contact_name="Dana", customer_email=None) == 2
    ra, rb = h.get(a.id), h.get(b.id)
    assert ra.customer == "Hospital" and ra.contact_name == "Dana" and ra.customer_email == ""
    assert rb.customer == "Hospital" and rb.customer_email == "b@example.com"      # None keeps the value
    assert ra.payload["customer"] == "Hospital" and ra.payload["contact_name"] == "Dana"
    h.update_customer([a.id], customer_email="a@example.com")
    assert [r.document_no for r in h.due_for_reminder(30, date(2026, 11, 12)) if r.customer_email == "a@example.com"]
    assert h.list(search="Dana")[0].document_no in ("LG-CAL-2025-0001", "LG-CAL-2025-0002")
    h.close()


def test_autostart_command_and_noop_outside_windows():
    from pipette_cal import autostart
    cmd = autostart.launch_command()
    assert "gilson_calibration.py" in cmd or ".exe" in cmd
    if not autostart.is_supported():
        assert autostart.is_enabled() is False
        autostart.set_enabled(True)          # no-op, must not raise
