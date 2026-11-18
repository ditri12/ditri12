"""Delivery of a generated certificate: open, print, e-mail."""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import webbrowser
from pathlib import Path
from urllib.parse import quote

log = logging.getLogger(__name__)


def open_file(path: Path) -> None:
    if sys.platform.startswith("win"):
        os.startfile(str(path))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def print_file(path: Path) -> None:
    """Send the PDF to the default printer (shows the OS print dialog on Windows)."""
    if sys.platform.startswith("win"):
        os.startfile(str(path), "print")  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["lpr", str(path)])
    else:
        subprocess.Popen(["lp", str(path)])


# As in the real logo: LIFE in green, GENE in blue; dir="ltr" keeps the order
# inside right-to-left (Hebrew) text.
BRAND_HTML = ('<span dir="ltr" style="font-weight:bold;letter-spacing:0.5px;unicode-bidi:isolate">'
              '<span style="color:#77b957">LIFE</span><span style="color:#2e7db6">GENE</span></span>')
_BRAND_WORDS = ("LifeGene", "LIFEGENE", "Lifegene")


def _html_escape(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def brand_html(text: str) -> str:
    """Escape *text* for HTML and show every 'LifeGene' as the coloured brand word."""
    out = _html_escape(text)
    for word in _BRAND_WORDS:
        out = out.replace(word, BRAND_HTML)
    return out


def compose_email(to: str, subject: str, body: str, attachments: list[Path],
                  send: bool = False, html: str | None = None, cc: str = "") -> str:
    """Create an e-mail with *attachments*.

    Outlook (COM, Windows + pywin32) is used when available. The message is
    always opened first with ``Display``: that is what makes Outlook insert the
    user's default signature, which is then kept below the message text.

    * ``send=False``: the draft stays open for review.
    * ``send=True``: ``Send`` is called right away (the window closes). If
      Outlook refuses, the draft stays open and the returned text says so, so
      nothing is lost.

    Without Outlook the default mail client is opened through a mailto link
    and the files have to be attached by hand.
    """
    if sys.platform.startswith("win"):
        try:
            import win32com.client  # type: ignore
        except ImportError:
            win32com = None  # type: ignore[assignment]
        if win32com is not None:
            step = "start Outlook"
            try:
                outlook = win32com.client.Dispatch("Outlook.Application")
                step = "create message"
                mail = outlook.CreateItem(0)
                step = "add recipients"
                for addr in _split_addresses(to):
                    mail.Recipients.Add(addr).Type = 1          # olTo
                for addr in _split_addresses(cc):
                    mail.Recipients.Add(addr).Type = 2          # olCC
                mail.Recipients.ResolveAll()
                mail.Subject = subject
                step = "attach files"
                for path in attachments:
                    mail.Attachments.Add(str(Path(path).resolve()))
                step = "open draft"
                mail.Display(False)                 # Outlook inserts the default signature here
                step = "load signature"
                try:
                    signature_html = mail.HTMLBody or ""
                except Exception as exc:  # noqa: BLE001
                    log.warning("could not read the Outlook signature: %s", exc)
                    signature_html = ""
                step = "set body"
                text_html = html or "<br>".join(brand_html(line) for line in body.splitlines())
                mail.HTMLBody = (f'<div style="font-family:Calibri,Arial,sans-serif;font-size:11pt">'
                                 f'{text_html}</div><br>{signature_html}')
                if not send:
                    return (f"Outlook message opened with {len(attachments)} attachment(s)"
                            + (" and your signature." if signature_html else "."))
                step = "send"
                try:
                    mail.Send()
                    return f"E-mail sent to {to} with {len(attachments)} attachment(s)."
                except Exception as exc:  # noqa: BLE001
                    log.warning("Outlook Send failed (%s); the draft stays open", exc)
                    return (f"Outlook refused to send automatically ({exc}).\n"
                            "The message is open as a draft - please press Send in Outlook.")
            except Exception as exc:  # noqa: BLE001 - COM errors are not typed
                raise RuntimeError(f"Outlook failed at step '{step}': {exc}") from exc
    webbrowser.open(f"mailto:{quote(to)}?subject={quote(subject)}&body={quote(body)}"
                    + (f"&cc={quote(cc)}" if cc else ""))
    files = "\n".join(str(Path(p).resolve()) for p in attachments)
    return f"Your mail client was opened. Please attach the file(s) manually:\n{files}"


def certificate_email(records, contact: str, customer: str, office_email: str) -> tuple[str, str, str]:
    """(subject, plain-text body, HTML body) of the Hebrew e-mail that carries the
    certificate PDFs. *records* are CalibrationRecord objects (one per PDF)."""
    from datetime import date as _date
    n = len(records)
    first = records[0]
    many = n > 1

    def fmt(iso: str) -> str:
        try:
            return _date.fromisoformat(iso[:10]).strftime("%d/%m/%Y") if iso else "-"
        except ValueError:
            return iso

    if many:
        subject = f"תעודות כיול לפיפטורים - {n} פיפטורים" + (f" - {customer}" if customer else "")
        intro = f"מצורפות תעודות הכיול של {n} הפיפטורים שלכם."
    else:
        subject = f"תעודת כיול לפיפטור - Gilson {first.model} S/N {first.serial_no} ({first.document_no})"
        intro = f"מצורפת תעודת הכיול {first.document_no} של הפיפטור שלכם."
    greeting = f"שלום {contact}," if contact else "שלום רב,"
    items = []
    for r in records:
        nxt = r.next_calibration or r.payload.get("next_calibration_date", "")
        verdict = "תקין (PASS)" if r.verdict == "PASS" else "לא תקין (FAIL)"
        items.append((f"Gilson {r.model}", r.serial_no or "-", verdict, r.document_no,
                      fmt(r.calibrated_at), fmt(nxt)))
    p_cert = ("התעודה מפרטת את הנפחים שנמדדו, את השגיאה השיטתית והאקראית מול גבולות הקבלה, "
              "ואת המועד המומלץ לכיול הבא. נשלח לכם תזכורת סמוך למועד זה.")
    p_contact_text = "לכל שאלה על התוצאות או לתיאום הכיול הבא, ניתן להשיב למייל זה או לפנות למשרדנו: "
    p_thanks = "תודה שבחרתם ב-LIFEGENE, נשמח לעמוד לשירותכם."

    lines = [greeting, "", intro, ""]
    for model, sn, verdict, doc, cal, nxt in items:
        lines.append(f"  - {model}, מספר סידורי {sn}: {verdict} (תעודה {doc}, כויל ב-{cal}, כיול הבא {nxt})")
    lines += ["", p_cert, "", p_contact_text + office_email + ".", "", p_thanks]

    heads = ["פיפטור", "מספר סידורי", "תוצאה", "מספר תעודה", "תאריך כיול", "כיול הבא"]
    th = "".join(f"<th style='padding:5px 10px;border:1px solid #cfd8e3;background:#eef3f8;text-align:right'>{h}</th>"
                 for h in heads)
    rows = "".join("<tr>" + "".join(
        f"<td style='padding:5px 10px;border:1px solid #cfd8e3;text-align:right'>{_html_escape(c)}</td>"
        for c in item) + "</tr>" for item in items)
    html = (f"<div dir='rtl' style='direction:rtl;text-align:right'>"
            f"<p>{_html_escape(greeting)}</p><p>{_html_escape(intro)}</p>"
            f"<table dir='rtl' style='border-collapse:collapse;font-size:10.5pt;direction:rtl'><tr>{th}</tr>{rows}</table>"
            f"<p>{_html_escape(p_cert)}</p>"
            f"<p>{_html_escape(p_contact_text)}<span dir='ltr' style='unicode-bidi:isolate'>"
            f"<a href='mailto:{office_email}'>{office_email}</a></span>.</p>"
            f"<p>{brand_html(p_thanks)}</p></div>")
    return subject, "\n".join(lines), html


def _split_addresses(text: str) -> list[str]:
    return [a.strip() for a in text.replace(",", ";").split(";") if a.strip()]


def email_file(path: Path, to: str, subject: str, body: str) -> str:
    """Create an e-mail with one certificate attached (kept for compatibility)."""
    return compose_email(to, subject, body, [path])
