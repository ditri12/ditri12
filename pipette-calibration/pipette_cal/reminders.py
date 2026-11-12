"""Recalibration reminders.

A pipette is due for recalibration one year after its calibration (the
"next calibration" date on the certificate). ``check_and_send`` finds every
pipette whose due date falls within the configured number of days, sends ONE
e-mail listing them to the office address, and records each document number
so it is reminded only once. The check runs when the program starts and can
be triggered from the History tab.
"""
from __future__ import annotations

import logging
from datetime import date

from .report import compose_email
from .storage import AppConfig, CalibrationRecord, History

log = logging.getLogger(__name__)


def _html_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _fmt(iso: str) -> str:
    try:
        return date.fromisoformat(iso).strftime("%d/%m/%Y")
    except ValueError:
        return iso or "-"


def build_reminder(records: list[CalibrationRecord], today: date | None = None) -> tuple[str, str, str]:
    """Return (subject, plain-text body, HTML body) for the reminder e-mail."""
    today = today or date.today()
    subject = f"Pipette recalibration due - {len(records)} pipette{'s' if len(records) != 1 else ''}"
    intro = ("The following pipettes calibrated by LifeGene are due for their annual recalibration "
             "within the next weeks. Please contact the customer and offer a recalibration appointment.")
    lines = [intro, ""]
    rows = []
    for r in records:
        due = date.fromisoformat(r.next_calibration) if r.next_calibration else None
        days = (due - today).days if due else None
        status = ("OVERDUE" if days is not None and days < 0 else f"in {days} days" if days is not None else "-")
        lines.append(f"- {r.model} S/N {r.serial_no or '-'} | customer: {r.customer or '-'}"
                     f"{' <' + r.customer_email + '>' if r.customer_email else ''} | calibrated "
                     f"{r.calibrated_at[:10]} ({r.document_no}) | due {_fmt(r.next_calibration)} ({status})")
        rows.append("<tr>" + "".join(f"<td style='padding:4px 10px;border:1px solid #ccc'>{_html_escape(c)}</td>" for c in (
            r.model, r.serial_no or "-", r.customer or "-", r.customer_email or "-",
            r.calibrated_at[:10], r.document_no, _fmt(r.next_calibration), status)) + "</tr>")
    lines += ["", "Suggested message to the customer:",
              "  \"Your pipette(s) listed above reach the recommended recalibration date soon. "
              "LifeGene offers a gravimetric calibration with a certificate; please contact us to schedule it.\"",
              "", "This reminder was generated automatically by the LifeGene Pipette Calibration program."]
    header = "".join(f"<th style='padding:4px 10px;border:1px solid #ccc;background:#f2f2f2;text-align:left'>{h}</th>"
                     for h in ("Model", "Serial", "Customer", "Customer e-mail", "Calibrated", "Certificate", "Due", "Status"))
    html = (f"<p>{_html_escape(intro)}</p><table style='border-collapse:collapse;font-size:10pt'>"
            f"<tr>{header}</tr>{''.join(rows)}</table>"
            "<p><b>Suggested message to the customer:</b><br><i>Your pipette(s) listed above reach the recommended "
            "recalibration date soon. LifeGene offers a gravimetric calibration with a certificate; please contact us "
            "to schedule it.</i></p><p style='color:#777;font-size:9pt'>This reminder was generated automatically by "
            "the LifeGene Pipette Calibration program.</p>")
    return subject, "\n".join(lines), html


def check_and_send(history: History, cfg: AppConfig, today: date | None = None) -> tuple[int, str]:
    """Send the reminder if anything is due. Returns (number of pipettes, message)."""
    to = cfg.reminder_email_to.strip()
    if not to:
        return 0, "No reminder address is configured (Settings)."
    due = history.due_for_reminder(cfg.reminder_days_before, today)
    if not due:
        return 0, "No pipette is due for recalibration in the next %d days." % cfg.reminder_days_before
    subject, body, html = build_reminder(due, today)
    msg = compose_email(to, subject, body, [], send=cfg.reminder_auto_send, html=html)
    for r in due:
        history.mark_reminded(r.document_no, to)
    log.info("reminder for %d pipette(s) -> %s: %s", len(due), to, msg)
    return len(due), msg
