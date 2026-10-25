"""Custom widgets: the per-key matrix preview and the fan curve editor."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Gsk", "4.0")
gi.require_version("Graphene", "1.0")
gi.require_version("Pango", "1.0")
from gi.repository import Gdk, Graphene, Gsk, Gtk, Pango  # noqa: E402

from .. import layouts  # noqa: E402
from ..animations import COLS, ROWS, Matrix, blank  # noqa: E402

MIN_TEMP, MAX_TEMP = 30, 100
MIN_RPM, MAX_RPM = 2000, 5000


class KeyboardView(Gtk.Widget):
    """Draws the keyboard using the real key map, with a grid fallback.

    Clicking a key reports the matrix cell behind it, so painting is 1:1 with
    the hardware instead of guessing where a cell sits.
    """

    def __init__(self) -> None:
        super().__init__()
        self.set_size_request(640, 250)
        self.set_hexpand(True)
        self.set_vexpand(True)
        self.matrix: Matrix = blank()
        self.on_cell = None
        self._selected: tuple[int, int] | None = None
        self._drag_start = (0.0, 0.0)
        self._last_painted: tuple[int, int] | None = None

        self.mapping = layouts.load_map()
        self.cells = layouts.cell_lookup(self.mapping)

        drag = Gtk.GestureDrag()
        drag.set_button(1)
        drag.connect("drag-begin", self._on_drag_begin)
        drag.connect("drag-update", self._on_drag_update)
        drag.connect("drag-end", self._on_drag_end)
        self.add_controller(drag)

        erase = Gtk.GestureClick()
        erase.set_button(3)
        erase.connect("pressed", self._on_right_pressed)
        self.add_controller(erase)

    # -- data ---------------------------------------------------------------
    def set_matrix(self, matrix: Matrix) -> None:
        self.matrix = matrix
        self.queue_draw()

    def set_selected(self, cell: tuple[int, int] | None) -> None:
        self._selected = cell
        self.queue_draw()

    def reload_map(self) -> None:
        self.mapping = layouts.load_map()
        self.cells = layouts.cell_lookup(self.mapping)
        self.queue_draw()

    # -- geometry -----------------------------------------------------------
    @staticmethod
    def _metrics(width: float, height: float):
        if not (width > 0 and height > 0):
            return 1.0, 0.0, 0.0
        unit = min(width / layouts.WIDTH_UNITS, height / layouts.ROWS)
        origin_x = (width - layouts.WIDTH_UNITS * unit) / 2.0
        origin_y = (height - layouts.ROWS * unit) / 2.0
        return unit, origin_x, origin_y

    @staticmethod
    def _key_rect(key, unit: float, origin_x: float, origin_y: float):
        return (
            origin_x + key.x * unit + 1.5,
            origin_y + key.row * unit + 1.5,
            key.width * unit - 3.0,
            unit - 3.0,
        )

    def _cell_at(self, x: float, y: float) -> tuple[int, int] | None:
        width = float(self.get_width())
        height = float(self.get_height())
        unit, origin_x, origin_y = self._metrics(width, height)
        if self.mapping:
            for key in layouts.LAYOUT:
                left, top, key_w, key_h = self._key_rect(key, unit, origin_x, origin_y)
                if left <= x <= left + key_w and top <= y <= top + key_h:
                    cell = self.mapping.get(key.id)
                    return (cell[0], cell[1]) if cell else None
            return None
        col = int((x - origin_x) / (unit))
        row = int((y - origin_y) / (unit))
        if 0 <= row < layouts.ROWS and 0 <= col < layouts.COLS:
            return (row, col)
        return None

    # -- interaction --------------------------------------------------------
    def _emit(self, cell: tuple[int, int], erase: bool = False) -> None:
        self.set_selected(cell)
        if self.on_cell is not None and (erase or cell != self._last_painted):
            self.on_cell(cell[0], cell[1], erase)
        self._last_painted = cell

    def _on_drag_begin(self, _gesture, start_x, start_y) -> None:
        self._drag_start = (start_x, start_y)
        self._last_painted = None
        cell = self._cell_at(start_x, start_y)
        if cell is not None:
            self._emit(cell)

    def _on_drag_update(self, _gesture, offset_x, offset_y) -> None:
        cell = self._cell_at(
            self._drag_start[0] + offset_x, self._drag_start[1] + offset_y
        )
        if cell is not None:
            self._emit(cell)

    def _on_drag_end(self, _gesture, _offset_x, _offset_y) -> None:
        self._last_painted = None

    def _on_right_pressed(self, _gesture, _presses, x, y) -> None:
        cell = self._cell_at(x, y)
        if cell is not None:
            self._emit(cell, erase=True)

    # -- drawing ------------------------------------------------------------
    def do_snapshot(self, snapshot) -> None:  # noqa: N802 - GTK name
        width = float(self.get_width())
        height = float(self.get_height())
        if width <= 0 or height <= 0:
            return

        background = Gdk.RGBA()
        background.parse("#0b0b0d")
        snapshot.append_color(background, Graphene.Rect().init(0, 0, width, height))

        unit, origin_x, origin_y = self._metrics(width, height)
        if self.mapping:
            self._draw_keys(snapshot, unit, origin_x, origin_y)
        else:
            self._draw_grid(snapshot, unit, origin_x, origin_y)

    def _draw_grid(self, snapshot, unit, origin_x, origin_y) -> None:
        inset = min(3.0, unit / 6.0)
        radius = min(6.0, unit / 4.0)
        for row in range(layouts.ROWS):
            for col in range(layouts.COLS):
                red, green, blue = self.matrix[row][col]
                colour = Gdk.RGBA()
                if (red, green, blue) == (0, 0, 0):
                    colour.parse("#26262b")
                else:
                    colour.red, colour.green, colour.blue = red / 255, green / 255, blue / 255
                    colour.alpha = 1.0
                rect = Graphene.Rect().init(
                    origin_x + col * unit + inset,
                    origin_y + row * unit + inset,
                    unit - inset * 2,
                    unit - inset * 2,
                )
                rounded = Gsk.RoundedRect()
                rounded.init_from_rect(rect, radius)
                snapshot.push_rounded_clip(rounded)
                snapshot.append_color(colour, rect)
                snapshot.pop()

    def _draw_keys(self, snapshot, unit, origin_x, origin_y) -> None:
        radius = min(7.0, unit / 5.0)
        font = Pango.FontDescription("Sans 8")
        for key in layouts.LAYOUT:
            left, top, key_w, key_h = self._key_rect(key, unit, origin_x, origin_y)
            cell = self.mapping.get(key.id)
            if cell is None:
                colour = Gdk.RGBA()
                colour.parse("#1a1a1e")
            else:
                red, green, blue = self.matrix[cell[0]][cell[1]]
                colour = Gdk.RGBA()
                if (red, green, blue) == (0, 0, 0):
                    colour.parse("#26262b")
                else:
                    colour.red, colour.green, colour.blue = red / 255, green / 255, blue / 255
                    colour.alpha = 1.0

            rect = Graphene.Rect().init(left, top, key_w, key_h)
            rounded = Gsk.RoundedRect()
            rounded.init_from_rect(rect, radius)
            snapshot.push_rounded_clip(rounded)
            snapshot.append_color(colour, rect)
            snapshot.pop()

            if self._selected is not None and cell == list(self._selected):
                accent = Gdk.RGBA()
                accent.parse("#44d62c")
                snapshot.append_border(rounded, [2.0] * 4, [accent] * 4)

            if key.legend:
                layout = self.create_pango_layout(key.legend)
                layout.set_font_description(font)
                text_w, text_h = layout.get_pixel_size()
                text = Gdk.RGBA()
                text.parse("rgba(255,255,255,0.75)")
                snapshot.save()
                snapshot.translate(
                    left + (key_w - text_w) / 2.0, top + (key_h - text_h) / 2.0
                )
                snapshot.append_layout(layout, text)
                snapshot.restore()


class CurveEditor(Gtk.Widget):
    """Temperature (x) against fan RPM (y), with three draggable points."""

    def __init__(self, points: list[list[int]] | None = None, on_changed=None) -> None:
        super().__init__()
        self.set_size_request(360, 190)
        self.set_hexpand(True)
        self.on_changed = on_changed
        self.points = self._clean(points or [[45, 3500], [70, 4200], [85, 5000]])
        self._drag_index: int | None = None
        self._drag_origin = (0.0, 0.0)

        drag = Gtk.GestureDrag()
        drag.connect("drag-begin", self._drag_begin)
        drag.connect("drag-update", self._drag_update)
        drag.connect("drag-end", self._drag_end)
        self.add_controller(drag)

    # -- geometry -----------------------------------------------------------
    @staticmethod
    def _clean(points: list[list[int]]) -> list[list[int]]:
        cleaned = []
        for temp, rpm in points:
            cleaned.append(
                [
                    max(MIN_TEMP, min(MAX_TEMP, int(temp))),
                    max(MIN_RPM, min(MAX_RPM, int(rpm))),
                ]
            )
        cleaned.sort(key=lambda point: point[0])
        return cleaned

    def get_points(self) -> list[list[int]]:
        return [list(point) for point in self.points]

    def set_points(self, points: list[list[int]]) -> None:
        self.points = self._clean(points)
        self.queue_draw()

    def _to_widget(self, temp: float, rpm: float, width: float, height: float):
        x = (temp - MIN_TEMP) / (MAX_TEMP - MIN_TEMP) * width
        y = height - (rpm - MIN_RPM) / (MAX_RPM - MIN_RPM) * height
        return x, y

    def _to_values(self, x: float, y: float, width: float, height: float):
        temp = MIN_TEMP + x / max(1.0, width) * (MAX_TEMP - MIN_TEMP)
        rpm = MIN_RPM + (height - y) / max(1.0, height) * (MAX_RPM - MIN_RPM)
        return int(temp), int(rpm)

    # -- interaction --------------------------------------------------------
    def _drag_begin(self, _gesture, start_x, start_y) -> None:
        width, height = self.get_width(), self.get_height()
        best = None
        best_distance = 1e9
        for index, (temp, rpm) in enumerate(self.points):
            x, y = self._to_widget(temp, rpm, width, height)
            distance = (x - start_x) ** 2 + (y - start_y) ** 2
            if distance < best_distance:
                best_distance = distance
                best = index
        if best is None or best_distance > 900:
            self._drag_index = None
            return
        self._drag_index = best
        self._drag_origin = (start_x, start_y)

    def _drag_update(self, _gesture, offset_x, offset_y) -> None:
        if self._drag_index is None:
            return
        temp, rpm = self._to_values(
            self._drag_origin[0] + offset_x,
            self._drag_origin[1] + offset_y,
            self.get_width(),
            self.get_height(),
        )
        self.points[self._drag_index] = [
            max(MIN_TEMP, min(MAX_TEMP, temp)),
            max(MIN_RPM, min(MAX_RPM, rpm)),
        ]
        self.points.sort(key=lambda point: point[0])
        self.queue_draw()

    def _drag_end(self, _gesture, _offset_x, _offset_y) -> None:
        self._drag_index = None
        if self.on_changed is not None:
            self.on_changed(self.get_points())

    # -- drawing ------------------------------------------------------------
    def do_snapshot(self, snapshot) -> None:  # noqa: N802 - GTK name
        width = float(self.get_width())
        height = float(self.get_height())
        if width <= 0 or height <= 0:
            return

        background = Gdk.RGBA()
        background.parse("#101013")
        snapshot.append_color(background, Graphene.Rect().init(0, 0, width, height))

        grid = Gdk.RGBA()
        grid.parse("rgba(255,255,255,0.06)")
        for temp in range(MIN_TEMP, MAX_TEMP + 1, 10):
            x, _ = self._to_widget(temp, MIN_RPM, width, height)
            snapshot.append_color(grid, Graphene.Rect().init(x, 0, 1, height))
        for rpm in range(MIN_RPM, MAX_RPM + 1, 500):
            _, y = self._to_widget(MIN_TEMP, rpm, width, height)
            snapshot.append_color(grid, Graphene.Rect().init(0, y, width, 1))

        accent = Gdk.RGBA()
        accent.parse("#44d62c")
        builder = Gsk.PathBuilder()
        for index, (temp, rpm) in enumerate(self.points):
            x, y = self._to_widget(temp, rpm, width, height)
            if index == 0:
                builder.move_to(x, y)
            else:
                builder.line_to(x, y)
        snapshot.append_stroke(builder.to_path(), Gsk.Stroke.new(3.0), accent)

        dot = Gdk.RGBA()
        dot.parse("#f2f2f2")
        for temp, rpm in self.points:
            x, y = self._to_widget(temp, rpm, width, height)
            rect = Graphene.Rect().init(x - 6, y - 6, 12, 12)
            rounded = Gsk.RoundedRect()
            rounded.init_from_rect(rect, 6.0)
            snapshot.push_rounded_clip(rounded)
            snapshot.append_color(dot, rect)
            snapshot.pop()


def paint_cell(matrix: Matrix, row: int, col: int, colour) -> Matrix:
    """Return a copy of `matrix` with one cell set, for the per-key editor."""
    updated = [list(line) for line in matrix]
    updated[row][col] = tuple(colour)
    return updated


__all__ = ["CurveEditor", "KeyboardView", "paint_cell"]
