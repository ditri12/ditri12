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


def email_file(path: Path, to: str, subject: str, body: str) -> str:
    """Create an e-mail with the certificate attached.

    Uses Outlook through COM when available (Windows + pywin32); otherwise
    opens the default mail client with a pre-filled message and returns a
    hint that the file must be attached manually.
    """
    if sys.platform.startswith("win"):
        try:
            import win32com.client  # type: ignore
            outlook = win32com.client.Dispatch("Outlook.Application")
            mail = outlook.CreateItem(0)
            mail.To = to
            mail.Subject = subject
            mail.Body = body
            mail.Attachments.Add(str(path.resolve()))
            mail.Display(False)
            return "Outlook message opened with the certificate attached."
        except ImportError:
            pass
        except Exception as exc:  # noqa: BLE001 - COM errors are not typed
            raise RuntimeError(f"Outlook could not be started: {exc}") from exc
    webbrowser.open(f"mailto:{quote(to)}?subject={quote(subject)}&body={quote(body)}")
    return ("Your mail client was opened. Please attach the certificate manually:\n"
            f"{path.resolve()}")
