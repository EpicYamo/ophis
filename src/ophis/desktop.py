"""Desktop integration that does not need root: autostart entries."""

from __future__ import annotations

import os
import sys
from pathlib import Path

AUTOSTART_DIR = Path.home() / ".config" / "autostart"
AUTOSTART_FILE = AUTOSTART_DIR / "ophis.desktop"

WINDOWS_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
WINDOWS_VALUE = "Ophis"


def _windows_launcher() -> Path:
    """A tiny launcher for running from a checkout on Windows.

    A packaged build starts its own .exe directly; this path is only used when
    the app runs from a source checkout during development.
    """
    appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    launcher = Path(appdata) / "ophis" / "ophis-tray.cmd"
    launcher.parent.mkdir(parents=True, exist_ok=True)
    package = Path(__file__).resolve().parent.parent
    pythonw = Path(sys.executable)
    if pythonw.name.lower() == "python.exe":
        pythonw = pythonw.with_name("pythonw.exe")
    launcher.write_text(
        "@echo off\r\n"
        f'set "PYTHONPATH={package}"\r\n'
        f'start "" "{pythonw}" -m ophis.windows.app --tray\r\n',
        encoding="utf-8",
    )
    return launcher


def autostart_command() -> str:
    if os.name == "nt":
        if getattr(sys, "frozen", False):
            return f'"{sys.executable}" --tray'
        return f'"{_windows_launcher()}"'
    package = Path(__file__).resolve().parent.parent
    return f"/usr/bin/env PYTHONPATH={package} {sys.executable} -m ophis.tray"


def autostart_enabled() -> bool:
    if os.name == "nt":
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, WINDOWS_RUN_KEY) as key:
                winreg.QueryValueEx(key, WINDOWS_VALUE)
            return True
        except OSError:
            return False
    return AUTOSTART_FILE.exists()


def set_autostart(enabled: bool) -> None:
    if os.name == "nt":
        import winreg

        with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER,
            WINDOWS_RUN_KEY,
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            if enabled:
                winreg.SetValueEx(
                    key,
                    WINDOWS_VALUE,
                    0,
                    winreg.REG_SZ,
                    autostart_command(),
                )
            else:
                try:
                    winreg.DeleteValue(key, WINDOWS_VALUE)
                except FileNotFoundError:
                    pass
        return

    if not enabled:
        AUTOSTART_FILE.unlink(missing_ok=True)
        return
    AUTOSTART_DIR.mkdir(parents=True, exist_ok=True)
    AUTOSTART_FILE.write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=Ophis\n"
        "Comment=Razer Blade control center\n"
        f"Exec={autostart_command()}\n"
        "Icon=input-keyboard-symbolic\n"
        "Terminal=false\n"
        "X-GNOME-Autostart-enabled=true\n",
        encoding="utf-8",
    )
