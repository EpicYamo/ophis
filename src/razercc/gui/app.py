"""GTK4 / libadwaita application entry point."""

from __future__ import annotations

import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio  # noqa: E402

from ..backend import open_backend  # noqa: E402
from .window import ControlWindow  # noqa: E402

APPLICATION_ID = "io.github.theyamo.RazerControl"


class RazerControlApp(Adw.Application):
    def __init__(self, preview: bool = False):
        super().__init__(application_id=APPLICATION_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self.preview = preview
        self.backend = None

    def do_activate(self) -> None:  # noqa: D102
        window = self.props.active_window
        if window is None:
            self.backend = open_backend(self.preview)
            window = ControlWindow(self, self.backend)
        window.present()

    def do_shutdown(self) -> None:  # noqa: D102
        if self.backend is not None:
            self.backend.close()
        Adw.Application.do_shutdown(self)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv if argv is None else argv)
    preview = "--preview" in args
    args = [arg for arg in args if arg != "--preview"]
    app = RazerControlApp(preview=preview)
    return app.run(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
