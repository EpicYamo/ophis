#!/usr/bin/env python3
"""Interactive matrix mapper.

The controller addresses LEDs by (row, column), which says nothing about which
physical key is which. This tool lights one cell at a time. Press the key that
lit up (its hardware keycode is recorded) or click it on the board, whichever
is easier.

    PYTHONPATH=src python3 tools/mapper.py

Progress is saved after every key, so you can stop and continue later.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Gsk", "4.0")
gi.require_version("Graphene", "1.0")
gi.require_version("Pango", "1.0")
from gi.repository import Gdk, GLib, Graphene, Gsk, Gtk, Pango  # noqa: E402

from ophis import animations, layouts  # noqa: E402
from ophis.backend import DeviceBackend  # noqa: E402

# Column 0 has no physical keys on the Blade 14, so the sweep starts at
# column 1. Everything else is still offered, because the map is the truth.
CELLS = [(row, col) for row in range(layouts.ROWS) for col in range(1, layouts.COLS)]


class Board(Gtk.Widget):
    """The German keyboard, showing what is still unmapped."""

    def __init__(self, on_key) -> None:
        super().__init__()
        self.set_size_request(700, 280)
        self.set_hexpand(True)
        self.set_vexpand(True)
        self.on_key = on_key
        self.cells: dict[str, list[int]] = {}
        self.current: tuple[int, int] | None = None

        click = Gtk.GestureClick()
        click.connect("pressed", self._on_pressed)
        self.add_controller(click)

    def update(self, cells: dict[str, list[int]], current) -> None:
        self.cells = cells
        self.current = current
        self.queue_draw()

    def _metrics(self):
        width = float(self.get_width()) or 700.0
        height = float(self.get_height()) or 280.0
        unit = min(width / layouts.WIDTH_UNITS, height / layouts.ROWS)
        return unit, (width - layouts.WIDTH_UNITS * unit) / 2, (height - layouts.ROWS * unit) / 2

    def _on_pressed(self, _gesture, _presses, x, y) -> None:
        unit, origin_x, origin_y = self._metrics()
        for key in layouts.LAYOUT:
            left = origin_x + key.x * unit + 1.5
            top = origin_y + (key.row + key.y_offset) * unit + 1.5
            if (
                left <= x <= left + key.width * unit - 3
                and top <= y <= top + key.height * unit - 3
            ):
                self.on_key(key)
                return

    def do_snapshot(self, snapshot) -> None:  # noqa: N802 - GTK name
        width = float(self.get_width())
        height = float(self.get_height())
        if width <= 0 or height <= 0:
            return

        background = Gdk.RGBA()
        background.parse("#0b0b0d")
        snapshot.append_color(background, Graphene.Rect().init(0, 0, width, height))

        unit, origin_x, origin_y = self._metrics()
        radius = min(6.0, unit / 5.0)
        font = Pango.FontDescription("Sans 7")

        for key in layouts.LAYOUT:
            left = origin_x + key.x * unit + 1.5
            top = origin_y + (key.row + key.y_offset) * unit + 1.5
            key_w = key.width * unit - 3
            key_h = key.height * unit - 3

            cell = self.cells.get(key.code)
            colour = Gdk.RGBA()
            if cell is None:
                colour.parse("#1a1a1e")
            elif self.current is not None and cell == list(self.current):
                colour.parse("#44d62c")
            else:
                colour.parse("#2f4f2c")

            rect = Graphene.Rect().init(left, top, key_w, key_h)
            rounded = Gsk.RoundedRect()
            rounded.init_from_rect(rect, radius)
            snapshot.push_rounded_clip(rounded)
            snapshot.append_color(colour, rect)
            snapshot.pop()

            if key.legend:
                layout = self.create_pango_layout(key.legend)
                layout.set_font_description(font)
                text_w, text_h = layout.get_pixel_size()
                text = Gdk.RGBA()
                text.parse("#d8d8d8" if cell is not None else "rgba(255,255,255,0.45)")
                snapshot.save()
                snapshot.translate(
                    Graphene.Point().init(
                        left + (key_w - text_w) / 2, top + (key_h - text_h) / 2
                    )
                )
                snapshot.append_layout(layout, text)
                snapshot.restore()


class Mapper(Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application, backend) -> None:
        super().__init__(application=app, title="Ophis matrix mapper")
        self.set_default_size(1180, 620)
        self.set_titlebar(Gtk.HeaderBar())

        self.backend = backend
        self.cells = layouts.load_cells()
        self.unused = layouts.load_unused()
        self.history: list[tuple[str, int, int]] = []
        self.current: tuple[int, int] | None = None
        self._last_press = 0.0
        self._timer = 0
        self._countdown = 0
        self._blink_sources: list[int] = []

        root = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=18)
        root.set_margin_top(16)
        root.set_margin_bottom(16)
        root.set_margin_start(16)
        root.set_margin_end(16)
        self.set_child(root)

        self.board = Board(self._on_board_key)
        root.append(self.board)

        side = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        side.set_size_request(300, -1)
        root.append(side)

        title = Gtk.Label(label="Press the lit key", xalign=0)
        title.add_css_class("title-2")
        side.append(title)

        self.cell_label = Gtk.Label(label="", xalign=0)
        self.cell_label.add_css_class("title-1")
        side.append(self.cell_label)

        self.last_label = Gtk.Label(label="No key recorded yet", xalign=0, wrap=True)
        self.last_label.add_css_class("dim-label")
        side.append(self.last_label)

        hint = Gtk.Label(
            label="One key blinks on the laptop. Press that key, or click it on "
            "the board. A cell with no key is skipped automatically after a "
            "few seconds, so you can just wait.",
            xalign=0,
            wrap=True,
        )
        hint.add_css_class("dim-label")
        side.append(hint)

        self.progress = Gtk.Label(label="", xalign=0)
        side.append(self.progress)

        for label, callback in (
            ("Test the lights", self._on_test),
            ("Retry skipped cells", self._on_retry_skipped),
            ("Nothing lit", self._on_nothing),
            ("Fn (no key event)", self._on_fn),
            ("Undo", self._on_undo),
            ("Finish", lambda *_: self.close()),
        ):
            button = Gtk.Button(label=label)
            button.connect("clicked", callback)
            side.append(button)

        self.status = Gtk.Label(label="", xalign=0, wrap=True)
        self.status.add_css_class("dim-label")
        side.append(self.status)

        keys = Gtk.EventControllerKey()
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self._on_key)
        self.add_controller(keys)

        self._next_cell()
        # Flash the whole board once so it is obvious the tool is talking to
        # the keyboard before the first cell appears.
        GLib.idle_add(self._on_test)

    # -- state --------------------------------------------------------------
    def _mapped(self) -> set[tuple[int, int]]:
        return {tuple(cell) for cell in self.cells.values()} | {
            tuple(cell) for cell in self.unused
        }

    def _next_cell(self) -> None:
        mapped = self._mapped()
        remaining = [cell for cell in CELLS if cell not in mapped]
        self.progress.set_text(f"{len(mapped)} of {len(CELLS)} cells recorded")
        if not remaining:
            self.current = None
            self.cell_label.set_text("All cells recorded")
            self.board.update(self.cells, None)
            self._light(None)
            return
        self.current = remaining[0]
        row, col = self.current
        self.cell_label.set_text(f"Cell {row}, {col}")
        self.board.update(self.cells, self.current)
        self._blink(self.current)
        self._arm_auto_skip()

    def _blink(self, cell: tuple[int, int]) -> None:
        """Two short flashes make a single lit key much easier to spot."""
        # Old blink timers may already have fired; their callbacks check that
        # the cell is still the current one, so they can be left alone.
        self._blink_sources = [
            GLib.timeout_add(180, lambda: self._blink_step(cell, None)),
            GLib.timeout_add(380, lambda: self._blink_step(cell, cell)),
            GLib.timeout_add(620, lambda: self._blink_step(cell, None)),
            GLib.timeout_add(820, lambda: self._blink_step(cell, cell)),
        ]

    def _blink_step(self, cell, target):
        if self.current == cell:
            self._light(target)
        self._blink_sources = [source for source in self._blink_sources if source]
        return False

    def _arm_auto_skip(self) -> None:
        self._cancel_timer()
        self._remaining = 6
        self._timer = GLib.timeout_add(1000, self._tick_countdown)

    def _tick_countdown(self) -> bool:
        self._remaining -= 1
        if self._remaining <= 0:
            self._countdown = 0
            self.status.set_text("")
            self._auto_skip()
            return False
        self.status.set_text(
            f"Nothing pressed: skipping this cell in {self._remaining} s"
        )
        return True

    def _cancel_timer(self) -> None:
        if self._timer:
            GLib.source_remove(self._timer)
            self._timer = 0
        self.status.set_text("")

    def _auto_skip(self) -> bool:
        self._timer = 0
        if self.current is None:
            return False
        self.unused.append(list(self.current))
        layouts.save_cells(self.cells, self.unused)
        self.last_label.set_text(
            f"Cell {self.current[0]}, {self.current[1]} was dark, skipped"
        )
        self._next_cell()
        return False

    def _light(self, cell: tuple[int, int] | None) -> None:
        matrix = animations.blank()
        if cell is not None:
            matrix[cell[0]][cell[1]] = (255, 255, 255)
        try:
            self.backend.activate_custom_frame()
            self.backend.write_frame(matrix)
        except Exception as exc:  # pragma: no cover - hardware only
            self.status.set_text(f"device error: {exc}")

    # -- recording ----------------------------------------------------------
    def _on_key(self, _controller, keyval, keycode, _state) -> bool:
        if self.current is None:
            return True
        now = time.monotonic()
        if now - self._last_press < 0.35:
            return True
        self._last_press = now
        self._cancel_timer()
        name = Gdk.keyval_name(keyval) or f"code {keycode}"
        self._assign(str(keycode), name)
        return True

    def _on_board_key(self, key: layouts.Key) -> None:
        self._cancel_timer()
        self._assign(key.code, key.legend or key.code)

    def _assign(self, code: str, name: str) -> None:
        if self.current is None:
            return
        row, col = self.current
        if code in self.cells and self.cells[code] != [row, col]:
            old = self.cells[code]
            self.status.set_text(
                f"{name} is already at {old[0]},{old[1]}; undo that first"
            )
            return
        self.cells[code] = [row, col]
        self.history.append((code, row, col))
        layouts.save_cells(self.cells, self.unused)
        legend = layouts.KEYS_BY_CODE.get(code)
        shown = legend.legend if legend is not None else name
        self.last_label.set_text(f"Recorded {shown} ({name}) at {row}, {col}")
        self._next_cell()

    def _on_nothing(self, *_args) -> None:
        if self.current is None:
            return
        self._cancel_timer()
        self.unused.append(list(self.current))
        layouts.save_cells(self.cells, self.unused)
        self.last_label.set_text(
            f"Cell {self.current[0]}, {self.current[1]} marked unused"
        )
        self._next_cell()

    def _on_retry_skipped(self, *_args) -> None:
        if not self.unused:
            self.status.set_text("Nothing was skipped")
            return
        self.unused.clear()
        layouts.save_cells(self.cells, self.unused)
        self.status.set_text("Skipped cells are back in the sweep")
        self._next_cell()

    def _on_fn(self, *_args) -> None:
        self._assign("fn", "Fn")

    def _on_undo(self, *_args) -> None:
        if self.history:
            code, row, col = self.history.pop()
            self.cells.pop(code, None)
            layouts.save_cells(self.cells, self.unused)
            self.current = (row, col)
            self.cell_label.set_text(f"Cell {row}, {col}")
            self.last_label.set_text("Last entry removed")
            self.board.update(self.cells, self.current)
            self._light(self.current)
        elif self.unused:
            cell = tuple(self.unused.pop())
            layouts.save_cells(self.cells, self.unused)
            self.current = cell
            self.board.update(self.cells, self.current)
            self._light(self.current)

    def _on_test(self, *_args) -> None:
        matrix = [[(255, 255, 255) for _ in range(layouts.COLS)] for _ in range(layouts.ROWS)]
        try:
            self.backend.activate_custom_frame()
            self.backend.write_frame(matrix)
        except Exception as exc:
            self.status.set_text(f"device error: {exc}")

        def restore() -> bool:
            self._light(self.current)
            return False

        GLib.timeout_add(1500, restore)


def main() -> int:
    backend = DeviceBackend()
    if not backend.connected:
        print(backend.detail, file=sys.stderr)
        return 1

    app = Gtk.Application(application_id="io.github.epicyamo.OphisMapper")

    def activate(application):
        window = Mapper(application, backend)
        window.present()

    app.connect("activate", activate)
    result = app.run([])
    backend.set_effect(6, (255, 204, 153))
    backend.close()
    return result


if __name__ == "__main__":
    raise SystemExit(main())
