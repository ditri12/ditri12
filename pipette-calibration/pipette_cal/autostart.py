"""Start the program automatically when the user logs on to Windows.

Implemented with the per-user Run key in the registry
(HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Run), which
needs no administrator rights. On other platforms the functions are no-ops.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

log = logging.getLogger(__name__)

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "LifeGenePipetteCalibration"


def launch_command() -> str:
    """Command that starts this program the way it is currently installed."""
    if getattr(sys, "frozen", False):
        return f'"{Path(sys.executable).resolve()}"'
    launcher = Path(__file__).resolve().parent.parent / "gilson_calibration.py"
    python = Path(sys.executable)
    pythonw = python.with_name("pythonw.exe")
    return f'"{pythonw if pythonw.exists() else python}" "{launcher}"'


def is_supported() -> bool:
    return sys.platform.startswith("win")


def is_enabled() -> bool:
    if not is_supported():
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, VALUE_NAME)
            return True
    except OSError:
        return False


def set_enabled(enabled: bool) -> None:
    """Register or remove the auto-start entry for the current user."""
    if not is_supported():
        return
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, launch_command())
            log.info("auto-start enabled: %s", launch_command())
        else:
            try:
                winreg.DeleteValue(key, VALUE_NAME)
                log.info("auto-start disabled")
            except FileNotFoundError:
                pass
