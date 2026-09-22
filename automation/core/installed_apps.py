"""Whether an app is installed on this PC, the way FlowShield's picker finds it.

Since the picker lists a suggested app only when it is installed (so every row
carries the app's own icon), UI tests that click a suggestion skip on a PC
without that app instead of failing.
"""
from __future__ import annotations

import os
import winreg
from pathlib import Path

_UNINSTALL = r"Software\Microsoft\Windows\CurrentVersion\Uninstall"
_HIVES = [
    (winreg.HKEY_CURRENT_USER, _UNINSTALL),
    (winreg.HKEY_LOCAL_MACHINE, _UNINSTALL),
    (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
]


def is_installed(exe_name: str) -> bool:
    """True if a Start Menu shortcut or an uninstall entry's DisplayIcon points at exe_name."""
    exe = exe_name.lower()
    for hive, path in _HIVES:
        try:
            root = winreg.OpenKey(hive, path)
        except OSError:
            continue
        with root:
            for i in range(winreg.QueryInfoKey(root)[0]):
                try:
                    with winreg.OpenKey(root, winreg.EnumKey(root, i)) as key:
                        icon = str(winreg.QueryValueEx(key, "DisplayIcon")[0])
                except OSError:
                    continue
                if Path(icon.split(",")[0].strip().strip('"')).name.lower() == exe:
                    return True
    for root in (os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu"),
                 os.path.expandvars(r"%PROGRAMDATA%\Microsoft\Windows\Start Menu")):
        for link in Path(root).rglob("*.lnk"):
            if link.stem.lower() == Path(exe).stem:
                return True
    return False


STEAM_INSTALLED = is_installed("steam.exe")
