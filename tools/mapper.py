#!/usr/bin/env python3
"""Interactive matrix mapper.

The controller addresses LEDs by (row, column), which says nothing about which
physical key is which. This tool lights one cell at a time; you click the key
that lit up, and it saves the answer to ``data/keymap_blade14.json``.

Run it with the laptop keyboard in front of you:

    PYTHONPATH=src python3 tools/mapper.py

Progress is saved after every key, so you can stop and continue later.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib  # noqa: E402

from ophis import animations, layouts  # noqa: E402
from ophis.backend import DeviceBackend  # noqa: E402

UNIT = 46
CELLS = [(row, col) for row in range(layouts.ROWS) for col in range(layouts.COLS)]


class Mapper(Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application, backend) -> None:
        super().__init__(application=app, title="Ophis matrix mapper")
        self.set_default_size(1180, 620)
        self.backend = backend
        self.mapping = layouts.load_map()
        self.unused = layouts.load_unused()
        self.history: list[tuple[str, int, int]] = []
        self.current: tuple[int, int] | None = None

        root = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        root.set_margin_top(16)
        root.set_margin_bottom(16)
        root.set_margin_start(16)
        root.set_margin_end(16)
        self.set_child(root)

        fixed = Gtk.Fixed()
        fixed.set_size_request(int(layouts.WIDTH_UNITS * UNIT) + 8, layouts.ROWS * UNIT + 8)
        for key in layouts.LAYOUT:
            button = Gtk.Button(label=key.legend or " ")
            button.add_css_class("key")
            button.set_size_request(int(key.width * UNIT) - 4, UNIT - 4)
            button.connect("clicked", self._on_key, key.id)
            fixed.put(button, int(key.x * UNIT) + 2, key.row * UNIT + 2)
        root.append(fixed)

        side = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        side.set_size_request(260, -1)
        root.append(side)

        self.cell_label = Gtk.Label(label="", xalign=0)
        self.cell_label.add_css_class("title-2")
        side.append(self.cell_label)

        self.hint = Gtk.Label(
            label="Click the key that is lit on the laptop. "
            "Right click erases a wrong entry.",
            xalign=0,
            wrap=True,
        )
        self.hint.add_css_class("dim-label")
        side.append(self.hint)

        self.progress = Gtk.Label(label="", xalign=0)
        side.append(self.progress)

        nothing = Gtk.Button(label="Nothing lit")
        nothing.connect("clicked", self._on_nothing)
        side.append(nothing)

        undo = Gtk.Button(label="Undo")
        undo.connect("clicked", self._on_undo)
        side.append(undo)

        self.finish = Gtk.Button(label="Finish")
        self.finish.connect("clicked", lambda *_: self.close())
        side.append(self.finish)

        self.toast = Gtk.Label(label="", xalign=0)
        self.toast.add_css_class("dim-label")
        side.append(self.toast)

        self._next_cell()

    # -- state --------------------------------------------------------------
    def _mapped(self) -> set[tuple[int, int]]:
        return {tuple(cell) for cell in self.mapping.values()} | set(self.unused)

    def _next_cell(self) -> None:
        mapped = self._mapped()
        remaining = [cell for cell in CELLS if cell not in mapped]
        self._draw_progress(len(mapped))
        if not remaining:
            self.current = None
            self.cell_label.set_text("All cells mapped")
            self._light(None)
            return
        self.current = remaining[0]
        row, col = self.current
        self.cell_label.set_text(f"Cell row {row}, column {col}")
        self._light(self.current)

    def _draw_progress(self, done: int) -> None:
        self.progress.set_text(f"{done} of {len(CELLS)} cells mapped")

    def _light(self, cell: tuple[int, int] | None) -> None:
        matrix = animations.blank()
        if cell is not None:
            matrix[cell[0]][cell[1]] = (255, 255, 255)
        try:
            self.backend.activate_custom_frame()
            self.backend.write_frame(matrix)
        except Exception as exc:  # pragma: no cover - hardware only
            self.toast.set_text(f"device error: {exc}")

    # -- actions ------------------------------------------------------------
    def _on_key(self, _button, key_id: str) -> None:
        if self.current is None:
            return
        row, col = self.current
        self.mapping[key_id] = [row, col]
        self.history.append((key_id, row, col))
        layouts.save_map(self.mapping, self.unused)
        self.toast.set_text(f"{key_id} -> {row},{col}")
        self._next_cell()

    def _on_nothing(self, *_args) -> None:
        if self.current is None:
            return
        self.unused.append(list(self.current))
        layouts.save_map(self.mapping, self.unused)
        self.toast.set_text(f"{self.current[0]},{self.current[1]} unused")
        self._next_cell()

    def _on_undo(self, *_args) -> None:
        if self.history:
            key_id, row, col = self.history.pop()
            self.mapping.pop(key_id, None)
            layouts.save_map(self.mapping, self.unused)
            self.current = (row, col)
            self.cell_label.set_text(f"Cell row {row}, column {col}")
            self._light(self.current)
        elif self.unused:
            cell = tuple(self.unused.pop())
            layouts.save_map(self.mapping, self.unused)
            self.current = cell
            self._light(self.current)


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
