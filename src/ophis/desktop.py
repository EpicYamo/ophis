"""Desktop integration that does not need root: autostart entries."""

from __future__ import annotations

import sys
from pathlib import Path

AUTOSTART_DIR = Path.home() / ".config" / "autostart"
AUTOSTART_FILE = AUTOSTART_DIR / "ophis.desktop"


def autostart_command() -> str:
    """Absolute command, so it also works from a checkout."""
    package = Path(__file__).resolve().parent.parent
    return f"/usr/bin/env PYTHONPATH={package} {sys.executable} -m ophis.tray"


def autostart_enabled() -> bool:
    return AUTOSTART_FILE.exists()


def set_autostart(enabled: bool) -> None:
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
