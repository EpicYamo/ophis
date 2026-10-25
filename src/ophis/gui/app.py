"""Application entry point: window, tray, profile at startup."""

from __future__ import annotations

import importlib.resources
import signal
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gdk, Gio, Gtk  # noqa: E402

from .. import profile  # noqa: E402
from ..backend import open_backend  # noqa: E402
from ..tray import Tray  # noqa: E402
from .window import ControlWindow  # noqa: E402

APPLICATION_ID = "io.github.epicyamo.Ophis"


class OphisApp(Adw.Application):
    def __init__(self, preview: bool = False, tray: bool = False) -> None:
        super().__init__(
            application_id=APPLICATION_ID,
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )
        self.preview = preview
        self.want_tray = tray
        self.backend = None
        self.window: ControlWindow | None = None
        self.tray: Tray | None = None
        self.profile = profile.load()
        self._started = False

    # -- lifecycle ----------------------------------------------------------
    def do_startup(self) -> None:
        Adw.Application.do_startup(self)
        self._load_css()
        manager = Adw.StyleManager.get_default()
        manager.set_color_scheme(Adw.ColorScheme.FORCE_DARK)

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
        if not (first and self.want_tray):
            self.window.present()

    # -- tray ---------------------------------------------------------------
    def _start_tray(self) -> None:
        self.tray = Tray(
            on_open=self._show_window,
            on_restore_defaults=self._restore_defaults,
            on_quit=self.quit_cleanly,
        )
        if not self.tray.available:
            print(
                "tray unavailable: install libayatana-appindicator-glib2 and "
                "gir1.2-ayatanaappindicatorglib-2.0",
                file=sys.stderr,
            )

    def _show_window(self) -> None:
        if self.window is not None:
            self.window.set_visible(True)
            self.window.present()

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
        if self.window is not None and self.window.engine is not None:
            self.window.engine.stop()
        if self.backend is not None:
            self.backend.close()
        if self.tray is not None:
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
    args = [arg for arg in args if arg not in ("--preview", "--tray")]
    app = OphisApp(preview=preview, tray=tray)

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
