"""Tray icon helper.

GNOME's AppIndicators extension understands ``com.canonical.dbusmenu``.
libayatana-appindicator3 (GTK3) exports exactly that, while the newer
GLib-only library exports ``org.gtk.Menus``, which the extension ignores.

GTK3 and GTK4 cannot share a process, so this helper runs as a child of the
GTK4 application, owns the icon and menu, and forwards clicks as D-Bus action
activations on the application.
"""

from __future__ import annotations

import sys

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("AyatanaAppIndicator3", "0.1")
from gi.repository import AyatanaAppIndicator3 as AppIndicator3  # noqa: E402
from gi.repository import Gio, GLib, Gtk  # noqa: E402

APP_ID = "io.github.epicyamo.Ophis"
APP_PATH = "/io/github/epicyamo/Ophis"

MENU = [
    ("Open Ophis", "show"),
    ("Restore default settings", "defaults"),
    ("Quit", "quit-app"),
]


class Helper:
    def __init__(self) -> None:
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)

        self.indicator = AppIndicator3.Indicator.new(
            "ophis",
            "input-keyboard-symbolic",
            AppIndicator3.IndicatorCategory.APPLICATION_STATUS,
        )
        self.indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
        self.indicator.set_title("Ophis")

        menu = Gtk.Menu()
        for label, action in MENU:
            item = Gtk.MenuItem(label=label)
            item.connect("activate", self._on_item, action)
            menu.append(item)
        menu.show_all()
        self.indicator.set_menu(menu)

        GLib.timeout_add_seconds(2, self._check_app)

    def _on_item(self, _item, action: str) -> None:
        try:
            self.bus.call_sync(
                APP_ID,
                APP_PATH,
                "org.gtk.Actions",
                "Activate",
                GLib.Variant("(sava{sv})", (action, [], {})),
                None,
                Gio.DBusCallFlags.NONE,
                2000,
                None,
            )
        except GLib.Error as exc:
            print(f"action {action}: {exc}", file=sys.stderr)

    def _check_app(self) -> bool:
        try:
            reply = self.bus.call_sync(
                "org.freedesktop.DBus",
                "/org/freedesktop/DBus",
                "org.freedesktop.DBus",
                "NameHasOwner",
                GLib.Variant("(s)", (APP_ID,)),
                GLib.VariantType.new("(b)"),
                Gio.DBusCallFlags.NONE,
                1000,
                None,
            )
            owned = bool(reply.unpack()[0])
        except GLib.Error:
            owned = False
        if not owned:
            Gtk.main_quit()
            return False
        return True


def main() -> int:
    Helper()
    Gtk.main()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
