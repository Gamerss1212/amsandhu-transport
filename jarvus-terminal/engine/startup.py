"""Start Jarvus when Windows starts, so the AI keeps trading without you opening anything.

Per-user (HKCU\\...\\Run): no administrator rights, nothing outside your own account, and removing the entry
undoes it. The entry runs the program minimised with --background, which starts the bot engine and does not open
a browser window; open http://127.0.0.1:8787 (or the shortcut you made) whenever you want to look.

Only the packaged Windows program can do this; from source or on other systems the setting explains why it is off.
"""

from __future__ import annotations

import os
import sys
from typing import Optional

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
NAME = "Jarvus"


def _winreg():
    try:
        import winreg
        return winreg
    except ImportError:
        return None


def supported(reg=None) -> bool:
    return (reg or _winreg()) is not None and sys.platform == "win32" and getattr(sys, "frozen", False)


def command(exe: Optional[str] = None) -> str:
    exe = exe or sys.executable
    return f'cmd /c start "" /min "{exe}" --background'


def _read(reg) -> Optional[str]:
    try:
        with reg.OpenKey(reg.HKEY_CURRENT_USER, RUN_KEY, 0, reg.KEY_READ) as k:
            return reg.QueryValueEx(k, NAME)[0]
    except OSError:
        return None


def status(reg=None, force: bool = False) -> dict:
    reg = reg or _winreg()
    if reg is None or not (force or supported(reg)):
        return {"supported": False, "enabled": False,
                "note": "Starting with Windows is available in the Windows app (JarvusTerminal.exe). From source, add "
                        "run.py to your system's startup items yourself."}
    cur = _read(reg)
    return {"supported": True, "enabled": bool(cur) and os.path.basename(sys.executable).lower() in cur.lower(),
            "command": command(), "note": "Runs minimised in the background when you sign in to Windows, with no "
                                          "browser window. Turn it off here at any time."}


def set_enabled(on: bool, reg=None, force: bool = False) -> dict:
    reg = reg or _winreg()
    if reg is None or not (force or supported(reg)):
        raise ValueError(status(reg, force)["note"])
    key = reg.CreateKeyEx(reg.HKEY_CURRENT_USER, RUN_KEY, 0, reg.KEY_SET_VALUE)
    try:
        if on:
            reg.SetValueEx(key, NAME, 0, reg.REG_SZ, command())
        else:
            try:
                reg.DeleteValue(key, NAME)
            except OSError:
                pass                                              # already absent
    finally:
        reg.CloseKey(key)
    return status(reg, force)
