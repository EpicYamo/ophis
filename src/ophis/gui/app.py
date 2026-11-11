"""Application entry point: window, tray, profile at startup."""

from __future__ import annotations

import importlib.resources
import signal
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

from .. import profile  # noqa: E402
from ..backend import open_backend  # noqa: E402
from ..tray import Tray  # noqa: E402
from .window import ControlWindow  # noqa: E402

APPLICATION_ID = "io.github.epicyamo.Ophis"


class OphisApp(Adw.Application):
    def __init__(self, preview: bool = False, tray: bool = False, show: bool = False) -> None:
        super().__init__(
            application_id=APPLICATION_ID,
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )
        self.preview = preview
        self.want_tray = tray
        self.show_on_start = show
        self.backend = None
        self.window: ControlWindow | None = None
        self.tray: Tray | None = None
        self.profile = profile.load()
        self._started = False
        self._power_subscriptions: list[tuple[Gio.DBusConnection, int]] = []
        self._power_recovery_source = 0
        self._power_retries = 0
        self._power_reapply_profile = False

    # -- lifecycle ----------------------------------------------------------
    def do_startup(self) -> None:
        Adw.Application.do_startup(self)
        self._watch_system_power()
        self._load_css()
        manager = Adw.StyleManager.get_default()
        manager.set_color_scheme(Adw.ColorScheme.FORCE_DARK)

        # The tray helper activates these over D-Bus. "quit" is reserved by
        # GApplication, so ours is "quit-app".
        for name, callback in (
            ("show", self._show_window),
            ("defaults", self._restore_defaults),
            ("quit-app", self.quit_cleanly),
        ):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", lambda _a, _p, cb=callback: cb())
            self.add_action(action)

    def do_activate(self) -> None:
        first = not self._started
        if first:
            self._started = True
            self.backend = open_backend(self.preview)
            if (
                not self.preview
                and self.profile["settings"].get("apply_on_start", True)
                and getattr(self.backend, "connected", False)
            ):
                profile.apply(self.backend, self.profile)
                self.backend.refresh()
            if self.want_tray:
                self._start_tray()
            tray_ready = bool(self.tray is not None and self.tray.available)
            if tray_ready:
                # Keep running after the window is hidden.
                self.hold()
            self.window = ControlWindow(self, self.backend, tray_enabled=tray_ready)

        assert self.window is not None
        if not (first and self.want_tray) or self.show_on_start:
            self.window.present()

    # -- tray ---------------------------------------------------------------
    def _start_tray(self) -> None:
        self.tray = Tray()
        self.tray.start()

    def _show_window(self) -> None:
        if self.window is not None:
            self.window.set_visible(True)
            self.window.present()

    # -- system power/display recovery ------------------------------------
    def _watch_system_power(self) -> None:
        """Subscribe to logind, GNOME screensaver, and power-profiles-daemon."""
        try:
            system_bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
            subscription = system_bus.signal_subscribe(
                "org.freedesktop.login1",
                "org.freedesktop.login1.Manager",
                "PrepareForSleep",
                "/org/freedesktop/login1",
                None,
                Gio.DBusSignalFlags.NONE,
                self._on_prepare_for_sleep,
            )
            self._power_subscriptions.append((system_bus, subscription))

            power_profile_subscription = system_bus.signal_subscribe(
                "org.freedesktop.UPower.PowerProfiles",
                "org.freedesktop.DBus.Properties",
                "PropertiesChanged",
                "/org/freedesktop/UPower/PowerProfiles",
                "org.freedesktop.UPower.PowerProfiles",
                Gio.DBusSignalFlags.NONE,
                self._on_power_profile_changed,
            )
            self._power_subscriptions.append((system_bus, power_profile_subscription))
        except GLib.Error:
            # Some minimal Ubuntu installations do not expose the system bus.
            pass

        try:
            session_bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            for name, path, interface in (
                (
                    "org.gnome.ScreenSaver",
                    "/org/gnome/ScreenSaver",
                    "org.gnome.ScreenSaver",
                ),
                (
                    "org.freedesktop.ScreenSaver",
                    "/org/freedesktop/ScreenSaver",
                    "org.freedesktop.ScreenSaver",
                ),
            ):
                subscription = session_bus.signal_subscribe(
                    name,
                    interface,
                    "ActiveChanged",
                    path,
                    None,
                    Gio.DBusSignalFlags.NONE,
                    self._on_screensaver_changed,
                )
                self._power_subscriptions.append((session_bus, subscription))
        except GLib.Error:
            pass

    def _on_prepare_for_sleep(self, _connection, _sender, _path, _interface, _signal,
                              parameters, _data) -> None:
        sleeping = bool(parameters.unpack()[0])
        if self.window is not None and self.window.lighting is not None:
            if sleeping:
                self.window.lighting.pause_for_power_change()
            else:
                self._schedule_power_recovery(reapply_profile=False)

    def _on_screensaver_changed(self, _connection, _sender, _path, _interface,
                                _signal, parameters, _data) -> None:
        active = bool(parameters.unpack()[0])
        if self.window is not None and self.window.lighting is not None:
            if active:
                self.window.lighting.pause_for_power_change()
            else:
                self._schedule_power_recovery(reapply_profile=False)

    def _on_power_profile_changed(self, _connection, _sender, _path, _interface,
                                  _signal, parameters, _data) -> None:
        try:
            interface, changed, _invalidated = parameters.unpack()
        except (TypeError, ValueError):
            return
        if (
            interface == "org.freedesktop.UPower.PowerProfiles"
            and "ActiveProfile" in changed
        ):
            self._schedule_power_recovery(reapply_profile=True)

    def _schedule_power_recovery(self, *, reapply_profile: bool) -> None:
        self._power_reapply_profile |= reapply_profile
        if self._power_recovery_source:
            GLib.source_remove(self._power_recovery_source)
        self._power_recovery_source = GLib.timeout_add(
            1200, self._recover_after_power_change
        )

    def _recover_after_power_change(self) -> bool:
        self._power_recovery_source = 0
        if self.backend is None or self.window is None:
            return False

        reconnect = getattr(self.backend, "reconnect", None)
        if callable(reconnect) and not self.preview:
            try:
                reconnect()
            except Exception:
                pass

        if not getattr(self.backend, "connected", False):
            self._power_retries += 1
            if self._power_retries <= 5:
                self._power_recovery_source = GLib.timeout_add(
                    2000, self._recover_after_power_change
                )
            else:
                self._power_retries = 0
                self.window.toast("Controller did not reconnect after the power change")
            return False

        self._power_retries = 0
        if self._power_reapply_profile:
            try:
                warnings = profile.apply(self.backend, self.window.profile)
                if warnings:
                    self.window.toast(warnings[0])
            except Exception as exc:
                self.window.toast(f"could not restore the saved profile: {exc}")
        self._power_reapply_profile = False
        try:
            self.backend.refresh()
        except Exception:
            pass
        self.window._sync_from_state()
        if self.window.lighting is not None:
            self.window.lighting.restore_after_power_change()
        return False

    def _restore_defaults(self) -> None:
        if self.backend is not None and getattr(self.backend, "connected", False):
            profile.restore_defaults(self.backend)
            self.backend.refresh()
        if self.window is not None:
            self.window._sync_from_state()  # noqa: SLF001 - deliberate refresh
            self.window.toast("Restored default settings")

    # -- shutdown -----------------------------------------------------------
    def quit_cleanly(self) -> None:
        if (
            not self.preview
            and self.backend is not None
            and getattr(self.backend, "connected", False)
            and self.profile["settings"].get("restore_on_quit", True)
        ):
            try:
                profile.restore_defaults(self.backend)
            except Exception:
                pass
        self.quit()

    def do_shutdown(self) -> None:
        if self._power_recovery_source:
            GLib.source_remove(self._power_recovery_source)
            self._power_recovery_source = 0
        for connection, subscription in self._power_subscriptions:
            connection.signal_unsubscribe(subscription)
        self._power_subscriptions.clear()
        if self.window is not None and self.window.engine is not None:
            self.window.engine.stop()
        if self.backend is not None:
            self.backend.close()
        if self.tray is not None:
            self.tray.close()
            self.tray = None
        Adw.Application.do_shutdown(self)

    # -- styling ------------------------------------------------------------
    def _load_css(self) -> None:
        try:
            css = importlib.resources.files("ophis.gui").joinpath("style.css").read_text()
        except (OSError, ModuleNotFoundError):
            return
        provider = Gtk.CssProvider()
        provider.load_from_data(css.encode("utf-8"))
        display = Gdk.Display.get_default()
        if display is not None:
            Gtk.StyleContext.add_provider_for_display(
                display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv if argv is None else argv)
    preview = "--preview" in args
    tray = "--tray" in args
    show = "--show" in args
    args = [arg for arg in args if arg not in ("--preview", "--tray", "--show")]
    app = OphisApp(preview=preview, tray=tray, show=show)

    def stop(*_args) -> bool:
        app.quit_cleanly()
        return False

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            from gi.repository import GLib

            GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, sig, stop)
        except Exception:
            pass

    return app.run(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
