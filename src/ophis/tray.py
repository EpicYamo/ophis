"""Tray icon built on libayatana-appindicator-glib.

GNOME has no legacy tray; the Ubuntu AppIndicators extension speaks the
StatusNotifierItem protocol, and this library implements it properly. Writing
that protocol by hand here was a mistake: malformed menu replies can take the
shell down, which is exactly what happened once.

The library is optional. Without it the app still runs, it just has no icon.
Install it with:

    sudo apt install libayatana-appindicator-glib2 \\
                     gir1.2-ayatanaappindicatorglib-2.0
"""

from __future__ import annotations

import time

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

ICON_NAME = "input-keyboard-symbolic"
APP_ID = "ophis"


def _load_indicator():
    """Import the GI namespace, which is spelled differently across versions."""
    for namespace, version in (
        ("AyatanaAppIndicatorGlib", "2.0"),
        ("AyatanaAppIndicator", "2.0"),
        ("AyatanaAppIndicator", "0.1"),
    ):
        try:
            gi.require_version(namespace, version)
            module = __import__("gi.repository", fromlist=[namespace])
            return getattr(module, namespace)
        except (ValueError, ImportError, AttributeError):
            continue
    return None


class Tray:
    """Click to open, right click for defaults and quit."""

    def __init__(
        self,
        on_open=None,
        on_restore_defaults=None,
        on_quit=None,
        open_cooldown: float = 1.0,
    ) -> None:
        self.on_open = on_open
        self.on_restore_defaults = on_restore_defaults
        self.on_quit = on_quit
        self.open_cooldown = open_cooldown
        self._last_open = 0.0
        self._indicator = None

        module = _load_indicator()
        if module is None:
            return

        category = getattr(module, "IndicatorCategory", None) or getattr(
            module, "Category", None
        )
        status = getattr(module, "IndicatorStatus", None) or getattr(module, "Status", None)
        if category is None or status is None:
            return

        try:
            self._indicator = module.Indicator.new(
                APP_ID, ICON_NAME, category.APPLICATION_STATUS
            )
            self._actions = Gio.SimpleActionGroup()
            for name, callback in (
                ("open", self._open),
                ("defaults", self._defaults),
                ("quit", self._quit),
            ):
                action = Gio.SimpleAction.new(name, None)
                action.connect("activate", lambda _a, _p, cb=callback: cb())
                self._actions.add_action(action)

            menu = Gio.Menu()
            menu.append("Open Ophis", "indicator.open")
            menu.append("Restore default settings", "indicator.defaults")
            menu.append("Quit", "indicator.quit")

            self._indicator.set_status(status.ACTIVE)
            self._indicator.set_menu(menu)
            # Without an action group the library never registers with the
            # StatusNotifierWatcher, so the icon never appears.
            self._indicator.set_actions(self._actions)
        except Exception:
            self._indicator = None
            return

        for signal in ("activate", "secondary-activate"):
            try:
                self._indicator.connect(signal, self._on_activate)
            except TypeError:
                pass

    @property
    def available(self) -> bool:
        return self._indicator is not None

    # -- callbacks ----------------------------------------------------------
    def _on_activate(self, *_args) -> None:
        self._open()

    def _open(self) -> None:
        # A double click delivers two signals; the second one is noise.
        now = time.monotonic()
        if now - self._last_open < self.open_cooldown:
            return
        self._last_open = now
        if self.on_open is not None:
            GLib.idle_add(self._safe, self.on_open)

    def _defaults(self) -> None:
        if self.on_restore_defaults is not None:
            self.on_restore_defaults()

    def _quit(self) -> None:
        if self.on_quit is not None:
            self.on_quit()

    @staticmethod
    def _safe(callback) -> bool:
        try:
            callback()
        except Exception:
            pass
        return False


def main(argv: list[str] | None = None) -> int:
    from .gui.app import main as gui_main

    args = list(argv or [])
    return gui_main(["--tray", *args])


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
