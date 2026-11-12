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


def _html_escape(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def compose_email(to: str, subject: str, body: str, attachments: list[Path],
                  send: bool = False, html: str | None = None, cc: str = "") -> str:
    """Create an e-mail with *attachments*.

    Outlook (COM, Windows + pywin32) is used when available.

    * ``send=False``: the draft is opened for review. Reading ``GetInspector``
      makes Outlook insert the user's default signature, and the message text
      is placed above it.
    * ``send=True``: the message is sent immediately without touching the
      inspector (opening it before ``Send`` makes some Outlook versions fail
      with "The parameter is incorrect"). If sending still fails, the draft is
      opened instead so nothing is lost, and the returned text says so.

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
                text_html = html or "<br>".join(_html_escape(line) for line in body.splitlines())
                step = "attach files"
                for path in attachments:
                    mail.Attachments.Add(str(Path(path).resolve()))
                if send:
                    step = "set body"
                    mail.HTMLBody = (f'<div style="font-family:Calibri,Arial,sans-serif;font-size:11pt">'
                                     f'{text_html}</div>')
                    step = "send"
                    try:
                        mail.Send()
                        return f"E-mail sent to {to} with {len(attachments)} attachment(s)."
                    except Exception as exc:  # noqa: BLE001
                        log.warning("Outlook Send failed (%s); opening the draft instead", exc)
                        mail.Display(False)
                        return (f"Outlook refused to send automatically ({exc}).\n"
                                "The message was opened as a draft instead - please press Send in Outlook.")
                step = "load signature"
                try:
                    mail.GetInspector                   # Outlook inserts the default signature
                    signature_html = mail.HTMLBody or ""
                except Exception as exc:  # noqa: BLE001
                    log.warning("could not load the Outlook signature: %s", exc)
                    signature_html = ""
                step = "set body"
                mail.HTMLBody = (f'<div style="font-family:Calibri,Arial,sans-serif;font-size:11pt">'
                                 f'{text_html}</div><br>{signature_html}')
                step = "open draft"
                mail.Display(False)
                return (f"Outlook message opened with {len(attachments)} attachment(s)"
                        + (" and your signature." if signature_html else "."))
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
