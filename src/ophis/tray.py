"""Tray lifecycle: spawn and stop the GTK3 helper.

The icon itself lives in :mod:`ophis.tray_helper` because GNOME's AppIndicators
extension needs ``com.canonical.dbusmenu``, which only the GTK3 library
exports. Clicks arrive at the application as D-Bus actions, so this class only
has to keep the child process alive.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path


class Tray:
    def __init__(self, on_open=None, on_restore_defaults=None, on_quit=None) -> None:
        self.on_open = on_open
        self.on_restore_defaults = on_restore_defaults
        self.on_quit = on_quit
        self.process: subprocess.Popen | None = None

    def start(self) -> bool:
        """Launch the helper; False when GTK3 appindicator is not installed."""
        package = str(Path(__file__).resolve().parent.parent)
        environment = os.environ.copy()
        existing = environment.get("PYTHONPATH")
        environment["PYTHONPATH"] = (
            f"{package}:{existing}" if existing else package
        )
        try:
            self.process = subprocess.Popen(
                [sys.executable, "-m", "ophis.tray_helper"],
                env=environment,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
        except OSError as exc:
            print(f"tray helper failed: {exc}", file=sys.stderr)
            return False

        # Give it a moment: a missing GI namespace exits immediately.
        time.sleep(0.5)
        if self.process.poll() is not None:
            message = ""
            if self.process.stderr is not None:
                message = self.process.stderr.read().decode("utf-8", "replace").strip()
            print(
                "tray unavailable: install gir1.2-ayatanaappindicator3-0.1"
                + (f" ({message})" if message else ""),
                file=sys.stderr,
            )
            self.process = None
            return False
        return True

    @property
    def available(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def close(self) -> None:
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
        self.process = None


def main(argv: list[str] | None = None) -> int:
    from .gui.app import main as gui_main

    return gui_main(["--tray", *(argv or [])])


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
