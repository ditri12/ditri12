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


def email_file(path: Path, to: str, subject: str, body: str) -> str:
    """Create an e-mail with the certificate attached.

    Uses Outlook through COM when available (Windows + pywin32). The draft is
    opened with Outlook's own default signature: reading ``GetInspector``
    makes Outlook insert the signature into the body, and the message text is
    then placed above it. Otherwise the default mail client is opened with a
    pre-filled message and the file has to be attached manually.
    """
    if sys.platform.startswith("win"):
        try:
            import win32com.client  # type: ignore
            outlook = win32com.client.Dispatch("Outlook.Application")
            mail = outlook.CreateItem(0)
            mail.To = to
            mail.Subject = subject
            mail.GetInspector                      # loads the default signature into HTMLBody
            signature_html = mail.HTMLBody or ""
            text_html = "<br>".join(_html_escape(line) for line in body.splitlines())
            mail.HTMLBody = (f'<div style="font-family:Calibri,Arial,sans-serif;font-size:11pt">'
                             f'{text_html}</div><br>{signature_html}')
            mail.Attachments.Add(str(path.resolve()))
            mail.Display(False)
            return "Outlook message opened with the certificate attached and your signature."
        except ImportError:
            pass
        except Exception as exc:  # noqa: BLE001 - COM errors are not typed
            raise RuntimeError(f"Outlook could not be started: {exc}") from exc
    webbrowser.open(f"mailto:{quote(to)}?subject={quote(subject)}&body={quote(body)}")
    return ("Your mail client was opened. Please attach the certificate manually:\n"
            f"{path.resolve()}")
