"""Custom widgets: the per-key matrix preview and the fan curve editor."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from ..animations import COLS, ROWS, Matrix, blank  # noqa: E402

MIN_TEMP, MAX_TEMP = 30, 100
MIN_RPM, MAX_RPM = 2000, 5000


class KeyboardView(Gtk.DrawingArea):
    """Draws the 6x16 matrix; clicking a cell reports its coordinates."""

    def __init__(self) -> None:
        super().__init__()
        self.set_content_width(COLS * 34)
        self.set_content_height(ROWS * 34)
        self.set_draw_func(self._draw)
        self.matrix: Matrix = blank()
        self.on_cell = None
        self._selected: tuple[int, int] | None = None

        click = Gtk.GestureClick()
        click.connect("pressed", self._on_pressed)
        self.add_controller(click)

    def set_matrix(self, matrix: Matrix) -> None:
        self.matrix = matrix
        self.queue_draw()

    def set_selected(self, cell: tuple[int, int] | None) -> None:
        self._selected = cell
        self.queue_draw()

    def _cell_at(self, x: float, y: float) -> tuple[int, int] | None:
        col = int(x // 34)
        row = int(y // 34)
        if 0 <= row < ROWS and 0 <= col < COLS:
            return (row, col)
        return None

    def _on_pressed(self, _gesture, _presses, x, y) -> None:
        cell = self._cell_at(x, y)
        if cell is not None:
            self.set_selected(cell)
            if self.on_cell is not None:
                self.on_cell(*cell)

    def _draw(self, _area, context, width, height) -> None:
        context.set_source_rgb(0.06, 0.06, 0.07)
        context.rectangle(0, 0, width, height)
        context.fill()

        cell_w = 34
        cell_h = 34
        inset = 3.0
        radius = 5.0
        for row in range(ROWS):
            for col in range(COLS):
                red, green, blue = self.matrix[row][col]
                if (red, green, blue) == (0, 0, 0):
                    context.set_source_rgb(0.16, 0.16, 0.18)
                else:
                    context.set_source_rgb(red / 255, green / 255, blue / 255)
                x = col * cell_w + inset
                y = row * cell_h + inset
                w = cell_w - inset * 2
                h = cell_h - inset * 2
                context.rectangle(x, y, w, h)
                context.fill()

                if self._selected == (row, col):
                    context.set_source_rgb(0.27, 0.84, 0.17)
                    context.set_line_width(2.0)
                    context.rectangle(x, y, w, h)
                    context.stroke()


class CurveEditor(Gtk.DrawingArea):
    """Temperature (x) against fan RPM (y), with three draggable points."""

    def __init__(self, points: list[list[int]] | None = None, on_changed=None) -> None:
        super().__init__()
        self.set_content_height(190)
        self.set_hexpand(True)
        self.set_draw_func(self._draw)
        self.on_changed = on_changed
        self.points = self._clean(points or [[45, 3500], [70, 4200], [85, 5000]])
        self._drag_index: int | None = None

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
        width = self.get_width()
        height = self.get_height()
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
        origin_x, origin_y = self._drag_origin
        temp, rpm = self._to_values(
            origin_x + offset_x,
            origin_y + offset_y,
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
    def _draw(self, _area, context, width, height) -> None:
        context.set_source_rgb(0.09, 0.09, 0.10)
        context.rectangle(0, 0, width, height)
        context.fill()

        context.set_line_width(1.0)
        for temp in range(30, 101, 10):
            x, _ = self._to_widget(temp, MIN_RPM, width, height)
            context.set_source_rgba(1, 1, 1, 0.06)
            context.move_to(x, 0)
            context.line_to(x, height)
            context.stroke()
        for rpm in range(2000, 5001, 500):
            _, y = self._to_widget(MIN_TEMP, rpm, width, height)
            context.set_source_rgba(1, 1, 1, 0.06)
            context.move_to(0, y)
            context.line_to(width, y)
            context.stroke()

        context.set_source_rgb(0.27, 0.84, 0.17)
        context.set_line_width(3.0)
        for index, (temp, rpm) in enumerate(self.points):
            x, y = self._to_widget(temp, rpm, width, height)
            if index == 0:
                context.move_to(x, y)
            else:
                context.line_to(x, y)
        context.stroke()

        for temp, rpm in self.points:
            x, y = self._to_widget(temp, rpm, width, height)
            context.set_source_rgb(0.95, 0.95, 0.95)
            context.arc(x, y, 6.0, 0, 6.2832)
            context.fill()


def paint_cell(matrix: Matrix, row: int, col: int, colour) -> Matrix:
    """Return a copy of `matrix` with one cell set, for the per-key editor."""
    updated = [list(line) for line in matrix]
    updated[row][col] = tuple(colour)
    return updated


__all__ = ["CurveEditor", "KeyboardView", "paint_cell"]
