"""Delivery of a generated certificate: open, print, e-mail."""
from __future__ import annotations

import os
import subprocess
import sys
import webbrowser
from pathlib import Path
from urllib.parse import quote


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

    Outlook (COM, Windows + pywin32) is used when available. The draft is
    opened with Outlook's own default signature: reading ``GetInspector``
    makes Outlook insert it, and the message text is placed above it. With
    ``send=True`` the message is sent immediately instead of being shown.
    Without Outlook the default mail client is opened through a mailto link
    and the files have to be attached by hand.
    """
    if sys.platform.startswith("win"):
        try:
            import win32com.client  # type: ignore
            outlook = win32com.client.Dispatch("Outlook.Application")
            mail = outlook.CreateItem(0)
            mail.To = to
            if cc:
                mail.CC = cc
            mail.Subject = subject
            mail.GetInspector                      # loads the default signature into HTMLBody
            signature_html = mail.HTMLBody or ""
            text_html = html or "<br>".join(_html_escape(line) for line in body.splitlines())
            mail.HTMLBody = (f'<div style="font-family:Calibri,Arial,sans-serif;font-size:11pt">'
                             f'{text_html}</div><br>{signature_html}')
            for path in attachments:
                mail.Attachments.Add(str(Path(path).resolve()))
            if send:
                mail.Send()
                return f"E-mail sent to {to} with {len(attachments)} attachment(s)."
            mail.Display(False)
            return (f"Outlook message opened with {len(attachments)} certificate(s) attached "
                    "and your signature.")
        except ImportError:
            pass
        except Exception as exc:  # noqa: BLE001 - COM errors are not typed
            raise RuntimeError(f"Outlook could not be started: {exc}") from exc
    webbrowser.open(f"mailto:{quote(to)}?subject={quote(subject)}&body={quote(body)}"
                    + (f"&cc={quote(cc)}" if cc else ""))
    files = "\n".join(str(Path(p).resolve()) for p in attachments)
    return f"Your mail client was opened. Please attach the file(s) manually:\n{files}"


def email_file(path: Path, to: str, subject: str, body: str) -> str:
    """Create an e-mail with one certificate attached (kept for compatibility)."""
    return compose_email(to, subject, body, [path])
