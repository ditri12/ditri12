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


# LIFE in the logo blue, GENE in the logo green; dir="ltr" keeps the order
# inside right-to-left (Hebrew) text.
BRAND_HTML = ('<span dir="ltr" style="font-weight:bold;letter-spacing:0.5px;unicode-bidi:isolate">'
              '<span style="color:#2e7db6">LIFE</span><span style="color:#77b957">GENE</span></span>')
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


def _split_addresses(text: str) -> list[str]:
    return [a.strip() for a in text.replace(",", ";").split(";") if a.strip()]


def email_file(path: Path, to: str, subject: str, body: str) -> str:
    """Create an e-mail with one certificate attached (kept for compatibility)."""
    return compose_email(to, subject, body, [path])
