"""Annual recalibration reminders.

Every certificate carries a "next calibration" date one year after the
calibration. ``check_and_send`` looks for pipettes whose date falls within
the configured number of days (or has passed), takes the latest calibration
of each serial number, groups them by customer e-mail and sends ONE message
per customer:

    To:  the customer address stored with the calibration
    CC:  the LifeGene office (info@lifegene.co.il by default)

Pipettes recorded without a customer e-mail are listed in a separate
internal message to the office only, so the office can contact the customer
by other means.

Two guards keep customers from being pestered:

* each certificate is reminded once (table ``reminders``);
* a customer address that already received a reminder within
  ``reminder_repeat_days`` (default one year) is not e-mailed again: any
  further pipette of that customer that becomes due is marked as covered by
  that earlier contact (table ``reminder_sends``) and only reported to the
  office summary.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from .report import brand_html, compose_email
from .storage import AppConfig, CalibrationRecord, History

log = logging.getLogger(__name__)

OFFICE_PHONE = "+972-(0)8-6444314"
OFFICE_EMAIL = "naama@lifegene.co.il"


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _fmt(iso: str) -> str:
    try:
        return date.fromisoformat(iso).strftime("%d/%m/%Y")
    except ValueError:
        return iso or "-"


def _days_left(r: CalibrationRecord, today: date) -> int | None:
    try:
        return (date.fromisoformat(r.next_calibration) - today).days
    except ValueError:
        return None


def _status(r: CalibrationRecord, today: date) -> str:
    days = _days_left(r, today)
    if days is None:
        return "-"
    if days < 0:
        return f"overdue by {-days} days"
    return "due today" if days == 0 else f"due in {days} days"


def _status_he(r: CalibrationRecord, today: date) -> str:
    days = _days_left(r, today)
    if days is None:
        return "-"
    if days < 0:
        return f"עבר לפני {-days} ימים"
    return "היום" if days == 0 else f"בעוד {days} ימים"


def _table_html(records: list[CalibrationRecord], today: date, internal: bool) -> str:
    heads = ["Pipette", "Serial number", "Certificate", "Calibrated on", "Recalibration due", "Status"]
    if internal:
        heads = ["Customer", "Contact"] + heads
    th = "".join(f"<th style='padding:5px 10px;border:1px solid #cfd8e3;background:#eef3f8;text-align:left'>{h}</th>"
                 for h in heads)
    rows = []
    for r in records:
        cells = [f"Gilson {r.model}", r.serial_no or "-", r.document_no, r.calibrated_at[:10],
                 _fmt(r.next_calibration), _status(r, today)]
        if internal:
            cells = [r.customer or "-", r.contact_name or "-"] + cells
        rows.append("<tr>" + "".join(f"<td style='padding:5px 10px;border:1px solid #cfd8e3'>{_esc(c)}</td>"
                                     for c in cells) + "</tr>")
    return f"<table style='border-collapse:collapse;font-size:10.5pt'><tr>{th}</tr>{''.join(rows)}</table>"


def _table_html_he(records: list[CalibrationRecord], today: date) -> str:
    heads = ["פיפטור", "מספר סידורי", "מספר תעודה", "תאריך כיול", "מועד כיול חוזר", "סטטוס"]
    th = "".join(f"<th style='padding:5px 10px;border:1px solid #cfd8e3;background:#eef3f8;text-align:right'>{h}</th>"
                 for h in heads)
    rows = []
    for r in records:
        cells = [f"Gilson {r.model}", r.serial_no or "-", r.document_no, _fmt(r.calibrated_at[:10]),
                 _fmt(r.next_calibration), _status_he(r, today)]
        rows.append("<tr>" + "".join(f"<td style='padding:5px 10px;border:1px solid #cfd8e3;text-align:right'>"
                                     f"{_esc(c)}</td>" for c in cells) + "</tr>")
    return (f"<table dir='rtl' style='border-collapse:collapse;font-size:10.5pt;direction:rtl'>"
            f"<tr>{th}</tr>{''.join(rows)}</table>")


def greeting_name(records: list[CalibrationRecord]) -> str:
    """Contact person if recorded, otherwise the customer / department name."""
    return (next((r.contact_name for r in records if r.contact_name.strip()), "")
            or next((r.customer for r in records if r.customer.strip()), "")).strip()


def build_customer_reminder(records: list[CalibrationRecord], today: date,
                            office_email: str = OFFICE_EMAIL) -> tuple[str, str, str]:
    """(subject, plain text, HTML) of the Hebrew message sent to one customer."""
    n = len(records)
    name = greeting_name(records)
    first = records[0]
    subject = ("תזכורת: מועד הכיול השנתי של הפיפטור מתקרב - " +
               (f"{n} פיפטורים" if n > 1 else f"Gilson {first.model} S/N {first.serial_no or '-'}"))
    greeting = f"שלום {name}," if name else "שלום רב,"
    many = n > 1
    p1 = ("לפי הרישומים שלנו, מועד הכיול השנתי של " +
          ("הפיפטורים הבאים שכוילו" if many else "הפיפטור הבא שכויל") +
          " על ידי LIFEGENE מתקרב. כיול תקופתי שומר על דיוק התוצאות ועל עקיבותן, "
          "ואנו ממליצים לבצע כיול חוזר לפני המועד המצוין.")
    p2_text = ("נשמח לשלוח לך הצעת מחיר לכיול החוזר. לקבלת הצעה או לתיאום מועד נוח, ניתן להשיב למייל זה "
               "או לפנות למשרדנו: ")
    p2 = f"{p2_text}{office_email} | {OFFICE_PHONE}."
    # e-mail address and phone number kept left-to-right inside the Hebrew sentence
    p2_html = (f"{brand_html(p2_text)}<span dir='ltr' style='unicode-bidi:isolate'>"
               f"<a href='mailto:{office_email}'>{office_email}</a> | {OFFICE_PHONE}</span>.")
    p3 = "תודה שבחרתם ב-LIFEGENE, נשמח לעמוד לשירותכם."
    sign_lines = ["LifeGene Ltd. - שירות טכני", "מבוא חורון, ישראל", f"{OFFICE_PHONE} | {office_email}"]
    lines = [greeting, "", p1, ""]
    for r in records:
        lines.append(f"  - Gilson {r.model}, מספר סידורי {r.serial_no or '-'}, תעודה {r.document_no}, "
                     f"כויל ב-{_fmt(r.calibrated_at[:10])}, מועד כיול חוזר {_fmt(r.next_calibration)} "
                     f"({_status_he(r, today)})")
    lines += ["", p2, "", p3, ""] + sign_lines
    # The HTML version ends after the thanks: Outlook appends the sender's own
    # signature. The plain-text version (used only without Outlook) keeps a
    # minimal company signature.
    html = (f"<div dir='rtl' style='direction:rtl;text-align:right'>"
            f"<p>{_esc(greeting)}</p><p>{brand_html(p1)}</p>{_table_html_he(records, today)}"
            f"<p>{p2_html}</p><p>{brand_html(p3)}</p></div>")
    return subject, "\n".join(lines), html


def build_internal_reminder(records: list[CalibrationRecord], today: date) -> tuple[str, str, str]:
    """Office-only message for pipettes that have no customer e-mail on record."""
    n = len(records)
    subject = f"Recalibration due - {n} pipette{'s' if n != 1 else ''} without a customer e-mail"
    intro = ("The following pipettes reach their annual recalibration date soon, but no customer e-mail "
             "was recorded with the calibration. Please contact the customer and offer a quotation for "
             "the recalibration.")
    lines = [intro, ""]
    for r in records:
        lines.append(f"  - {r.customer or '(no customer)'}: Gilson {r.model}, S/N {r.serial_no or '-'}, "
                     f"certificate {r.document_no}, due {_fmt(r.next_calibration)} ({_status(r, today)})")
    lines += ["", "Generated automatically by the LifeGene Pipette Calibration program."]
    html = (f"<p>{_esc(intro)}</p>{_table_html(records, today, internal=True)}"
            "<p style='color:#777;font-size:9pt'>Generated automatically by the LifeGene Pipette Calibration program.</p>")
    return subject, "\n".join(lines), html


def send_manual(history: History, cfg: AppConfig, records: list[CalibrationRecord],
                today: date | None = None, email_override: str = "") -> str:
    """Send the customer reminder for the given calibrations NOW, ignoring the
    'no reminder' flag, earlier reminders and the per-customer repeat guard.
    Records are grouped by customer address (or all sent to *email_override*).
    Every send is recorded like an automatic one."""
    today = today or date.today()
    office = cfg.reminder_email_to.strip() or OFFICE_EMAIL
    groups: dict[str, list[CalibrationRecord]] = {}
    for r in records:
        email = (email_override or r.customer_email).strip().lower()
        if not email:
            raise ValueError(f"{r.document_no} ({r.model} S/N {r.serial_no or '-'}) has no customer e-mail. "
                             "Enter an address to send to.")
        groups.setdefault(email, []).append(r)
    messages = []
    for email, recs in groups.items():
        subject, body, html = build_customer_reminder(recs, today, office)
        messages.append(compose_email(email, subject, body, [], send=cfg.reminder_auto_send, html=html, cc=office))
        history.record_reminder_send(email, [r.document_no for r in recs])
        for r in recs:
            history.mark_reminded(r.document_no, f"{email}; cc {office} (manual)")
        log.info("manual reminder: %d pipette(s) -> %s (cc %s)", len(recs), email, office)
    return (f"Reminder for {len(records)} pipette(s) sent to {len(groups)} address(es), office copy to {office}.\n"
            + "\n".join(messages))


def check_and_send(history: History, cfg: AppConfig, today: date | None = None) -> tuple[int, str]:
    """Send the reminders that are due. Returns (number of pipettes, message)."""
    today = today or date.today()
    office = cfg.reminder_email_to.strip() or OFFICE_EMAIL
    due = history.due_for_reminder(cfg.reminder_days_before, today)
    if not due:
        return 0, f"No pipette is due for recalibration in the next {cfg.reminder_days_before} days."
    by_customer: dict[str, list[CalibrationRecord]] = {}
    internal: list[CalibrationRecord] = []
    for r in due:
        (by_customer.setdefault(r.customer_email.strip().lower(), []) if r.customer_email.strip() else internal).append(r)
    messages = []
    suppressed = 0
    for email, recs in by_customer.items():
        last = history.last_reminder_to(email)
        if last:
            try:
                last_dt = datetime.fromisoformat(last).date()
            except ValueError:
                last_dt = None
            if last_dt and today - last_dt < timedelta(days=cfg.reminder_repeat_days):
                # customer already contacted recently: do not e-mail again
                for r in recs:
                    history.mark_reminded(r.document_no, f"not sent - {email} already contacted on {last[:10]}")
                suppressed += len(recs)
                log.info("reminder suppressed for %s (contacted %s): %s", email, last[:10],
                         ", ".join(r.document_no for r in recs))
                continue
        subject, body, html = build_customer_reminder(recs, today, office)
        messages.append(compose_email(email, subject, body, [], send=cfg.reminder_auto_send, html=html, cc=office))
        history.record_reminder_send(email, [r.document_no for r in recs])
        for r in recs:
            history.mark_reminded(r.document_no, f"{email}; cc {office}")
        log.info("reminder: %d pipette(s) -> %s (cc %s)", len(recs), email, office)
    if internal:
        subject, body, html = build_internal_reminder(internal, today)
        messages.append(compose_email(office, subject, body, [], send=cfg.reminder_auto_send, html=html))
        for r in internal:
            history.mark_reminded(r.document_no, office)
        log.info("internal reminder: %d pipette(s) -> %s", len(internal), office)
    sent_customers = len(messages) - (1 if internal else 0)
    summary = (f"{len(due)} pipette(s) due: {sent_customers} customer e-mail(s) sent"
               + (f", {suppressed} pipette(s) skipped because the customer was contacted recently" if suppressed else "")
               + (", 1 internal e-mail" if internal else "") + f"; office copy to {office}.")
    if not messages:
        return 0, summary
    return len(due), summary + "\n" + "\n".join(messages)
