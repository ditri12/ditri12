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
by other means. Each certificate is reminded once (table ``reminders``).
"""
from __future__ import annotations

import logging
from datetime import date

from .report import compose_email
from .storage import AppConfig, CalibrationRecord, History

log = logging.getLogger(__name__)

OFFICE_PHONE = "+972-(0)8-6444314"
OFFICE_EMAIL = "info@lifegene.co.il"


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _fmt(iso: str) -> str:
    try:
        return date.fromisoformat(iso).strftime("%d/%m/%Y")
    except ValueError:
        return iso or "-"


def _status(r: CalibrationRecord, today: date) -> str:
    try:
        days = (date.fromisoformat(r.next_calibration) - today).days
    except ValueError:
        return "-"
    if days < 0:
        return f"overdue by {-days} days"
    return "due today" if days == 0 else f"due in {days} days"


def _table_html(records: list[CalibrationRecord], today: date, internal: bool) -> str:
    heads = ["Pipette", "Serial number", "Certificate", "Calibrated on", "Recalibration due", "Status"]
    if internal:
        heads = ["Customer"] + heads
    th = "".join(f"<th style='padding:5px 10px;border:1px solid #cfd8e3;background:#eef3f8;text-align:left'>{h}</th>"
                 for h in heads)
    rows = []
    for r in records:
        cells = [f"Gilson {r.model}", r.serial_no or "-", r.document_no, r.calibrated_at[:10],
                 _fmt(r.next_calibration), _status(r, today)]
        if internal:
            cells = [r.customer or "-"] + cells
        rows.append("<tr>" + "".join(f"<td style='padding:5px 10px;border:1px solid #cfd8e3'>{_esc(c)}</td>"
                                     for c in cells) + "</tr>")
    return f"<table style='border-collapse:collapse;font-size:10.5pt'><tr>{th}</tr>{''.join(rows)}</table>"


def build_customer_reminder(records: list[CalibrationRecord], today: date,
                            office_email: str = OFFICE_EMAIL) -> tuple[str, str, str]:
    """(subject, plain text, HTML) of the message sent to one customer."""
    customer = next((r.customer for r in records if r.customer), "")
    n = len(records)
    subject = ("Annual pipette calibration due soon - " +
               (f"{n} pipettes" if n > 1 else f"Gilson {records[0].model} S/N {records[0].serial_no or '-'}"))
    greeting = f"Dear {customer}," if customer else "Dear customer,"
    p1 = (f"Our records show that the annual calibration of the following pipette{'s' if n > 1 else ''} "
          "calibrated by LifeGene is approaching its due date. Regular calibration keeps your results "
          "accurate and traceable, and we recommend recalibrating before the date below.")
    p2 = ("We would be pleased to send you a quotation for the recalibration. To request one, or to "
          f"schedule a convenient date, simply reply to this e-mail or contact our office at "
          f"{office_email} / {OFFICE_PHONE}.")
    p3 = "Thank you for choosing LifeGene. We look forward to assisting you."
    sign = "LifeGene Ltd. - Technical Service\nMevo Horon, Israel\n" + f"{OFFICE_PHONE} | {office_email}"
    lines = [greeting, "", p1, ""]
    for r in records:
        lines.append(f"  - Gilson {r.model}, S/N {r.serial_no or '-'}, certificate {r.document_no}, "
                     f"calibrated {r.calibrated_at[:10]}, recalibration due {_fmt(r.next_calibration)} "
                     f"({_status(r, today)})")
    lines += ["", p2, "", p3, "", sign]
    html = (f"<p>{_esc(greeting)}</p><p>{_esc(p1)}</p>{_table_html(records, today, internal=False)}"
            f"<p>{_esc(p2)}</p><p>{_esc(p3)}</p>"
            f"<p style='color:#555'>LifeGene Ltd. - Technical Service<br>Mevo Horon, Israel<br>"
            f"{OFFICE_PHONE} | <a href='mailto:{office_email}'>{office_email}</a></p>")
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
    for email, recs in by_customer.items():
        subject, body, html = build_customer_reminder(recs, today, office)
        messages.append(compose_email(email, subject, body, [], send=cfg.reminder_auto_send, html=html, cc=office))
        for r in recs:
            history.mark_reminded(r.document_no, f"{email}; cc {office}")
        log.info("reminder: %d pipette(s) -> %s (cc %s)", len(recs), email, office)
    if internal:
        subject, body, html = build_internal_reminder(internal, today)
        messages.append(compose_email(office, subject, body, [], send=cfg.reminder_auto_send, html=html))
        for r in internal:
            history.mark_reminded(r.document_no, office)
        log.info("internal reminder: %d pipette(s) -> %s", len(internal), office)
    summary = (f"Reminders for {len(due)} pipette(s): {len(by_customer)} customer e-mail(s)"
               + (f" and 1 internal e-mail" if internal else "") + f", office copy to {office}.")
    return len(due), summary + "\n" + "\n".join(messages)
