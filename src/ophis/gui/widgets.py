"""Custom widgets: the per-key matrix preview and the fan curve editor."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Gsk", "4.0")
gi.require_version("Graphene", "1.0")
from gi.repository import Gdk, Graphene, Gsk, Gtk  # noqa: E402

from ..animations import COLS, ROWS, Matrix, blank  # noqa: E402

MIN_TEMP, MAX_TEMP = 30, 100
MIN_RPM, MAX_RPM = 2000, 5000


class KeyboardView(Gtk.Widget):
    """Draws the 6x16 matrix; clicking a cell reports its coordinates.

    Uses the snapshot API rather than cairo, so the preview works even when
    python3-gi-cairo is missing (GTK's draw_func needs it).
    """

    def __init__(self) -> None:
        super().__init__()
        self.set_size_request(COLS * 28, ROWS * 34)
        self.set_hexpand(True)
        self.set_vexpand(True)
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
        width = self.get_width() or COLS * 28
        height = self.get_height() or ROWS * 34
        col = int(x / (width / COLS))
        row = int(y / (height / ROWS))
        if 0 <= row < ROWS and 0 <= col < COLS:
            return (row, col)
        return None

    def _on_pressed(self, _gesture, _presses, x, y) -> None:
        cell = self._cell_at(x, y)
        if cell is not None:
            self.set_selected(cell)
            if self.on_cell is not None:
                self.on_cell(*cell)

    def do_snapshot(self, snapshot) -> None:  # noqa: N802 - GTK name
        width = float(self.get_width())
        height = float(self.get_height())
        if width <= 0 or height <= 0:
            return

        background = Gdk.RGBA()
        background.parse("#0b0b0d")
        snapshot.append_color(background, Graphene.Rect().init(0, 0, width, height))

        cell_w = width / COLS
        cell_h = height / ROWS
        inset = min(3.0, cell_w / 6.0, cell_h / 6.0)
        radius = min(6.0, cell_w / 4.0, cell_h / 4.0)

        for row in range(ROWS):
            for col in range(COLS):
                red, green, blue = self.matrix[row][col]
                colour = Gdk.RGBA()
                if (red, green, blue) == (0, 0, 0):
                    colour.parse("#26262b")
                else:
                    colour.red = red / 255
                    colour.green = green / 255
                    colour.blue = blue / 255
                    colour.alpha = 1.0

                rect = Graphene.Rect().init(
                    col * cell_w + inset,
                    row * cell_h + inset,
                    cell_w - inset * 2,
                    cell_h - inset * 2,
                )
                rounded = Gsk.RoundedRect()
                rounded.init_from_rect(rect, radius)
                snapshot.push_rounded_clip(rounded)
                snapshot.append_color(colour, rect)
                snapshot.pop()

                if self._selected == (row, col):
                    accent = Gdk.RGBA()
                    accent.parse("#44d62c")
                    widths = [2.0] * 4
                    colours = [accent] * 4
                    snapshot.append_border(rounded, widths, colours)


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
