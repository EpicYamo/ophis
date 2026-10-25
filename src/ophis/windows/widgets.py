"""Qt widgets that mirror the GTK interface: cards, rows, switches, clocks."""

from __future__ import annotations

import math
from typing import Callable, Iterable

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPointF,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QAbstractButton,
    QButtonGroup,
    QColorDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .. import layouts
from ..animations import COLS, ROWS, Matrix, blank

MUTED = "rgba(255, 255, 255, 0.45)"


# -- small building blocks --------------------------------------------------
def label(text: str = "", *, muted: bool = False, wrap: bool = False) -> QLabel:
    widget = QLabel(text)
    if muted:
        widget.setProperty("muted", True)
    if wrap:
        widget.setWordWrap(True)
    return widget


def section_label(text: str) -> QLabel:
    widget = QLabel(text.upper())
    widget.setObjectName("sectionTitle")
    font = QFont(widget.font())
    font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2.0)
    widget.setFont(font)
    return widget


def page_header(title: str, subtitle: str = "") -> QWidget:
    holder = QWidget()
    box = QVBoxLayout(holder)
    box.setContentsMargins(0, 0, 0, 0)
    box.setSpacing(4)
    heading = QLabel(title)
    heading.setObjectName("pageTitle")
    box.addWidget(heading)
    if subtitle:
        note = QLabel(subtitle)
        note.setObjectName("pageSubtitle")
        note.setWordWrap(True)
        box.addWidget(note)
    return holder


class Card(QFrame):
    def __init__(self, spacing: int = 12) -> None:
        super().__init__()
        self.setObjectName("card")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(16, 14, 16, 14)
        self.body.setSpacing(spacing)

    def add(self, widget: QWidget) -> QWidget:
        self.body.addWidget(widget)
        return widget


class SettingsCard(Card):
    """A card whose children are setting rows separated by hairlines."""

    def __init__(self) -> None:
        super().__init__(spacing=0)

    def add_row(self, row: QWidget) -> QWidget:
        if self.body.count():
            line = QFrame()
            line.setObjectName("separator")
            line.setFixedHeight(1)
            self.body.addWidget(line)
        self.body.addWidget(row)
        return row


class SettingRow(QWidget):
    def __init__(self, title: str, subtitle: str = "") -> None:
        super().__init__()
        self._outer = QHBoxLayout(self)
        self._outer.setContentsMargins(0, 10, 0, 10)
        self._outer.setSpacing(16)

        text = QVBoxLayout()
        text.setContentsMargins(0, 0, 0, 0)
        text.setSpacing(2)
        self.title = QLabel(title)
        self.title.setWordWrap(True)
        text.addWidget(self.title)
        self.subtitle = QLabel(subtitle)
        self.subtitle.setProperty("muted", True)
        self.subtitle.setWordWrap(True)
        self.subtitle.setVisible(bool(subtitle))
        text.addWidget(self.subtitle)
        self._outer.addLayout(text, 1)

        self.controls = QWidget()
        self.controls_layout = QHBoxLayout(self.controls)
        self.controls_layout.setContentsMargins(0, 0, 0, 0)
        self.controls_layout.setSpacing(8)
        self._outer.addWidget(self.controls, 0, Qt.AlignmentFlag.AlignVCenter)

    def add_control(self, widget: QWidget) -> QWidget:
        self.controls_layout.addWidget(widget, 0, Qt.AlignmentFlag.AlignVCenter)
        return widget

    def set_subtitle(self, text: str) -> None:
        self.subtitle.setText(text)
        self.subtitle.setVisible(bool(text))


class ToggleSwitch(QAbstractButton):
    """A 44x24 pill switch with a short slide animation."""

    def __init__(self, checked: bool = False) -> None:
        super().__init__()
        self.setCheckable(True)
        self._offset = 1.0 if checked else 0.0
        self._animation = QPropertyAnimation(self, b"offset", self)
        self._animation.setDuration(120)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.setChecked(checked)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(44, 24)
        self.toggled.connect(self._animate)

    def sizeHint(self) -> QSize:
        return QSize(44, 24)

    def _get_offset(self) -> float:
        return self._offset

    def _set_offset(self, value: float) -> None:
        self._offset = value
        self.update()

    offset = Property(float, _get_offset, _set_offset)

    def _animate(self, checked: bool) -> None:
        self._animation.stop()
        self._animation.setStartValue(self._offset)
        self._animation.setEndValue(1.0 if checked else 0.0)
        self._animation.start()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        track = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#44d62c") if self.isChecked() else QColor("#3a3a40"))
        painter.drawRoundedRect(track, 12, 12)
        radius = 9.0
        x = 3.0 + self._offset * (self.width() - 6.0 - radius * 2)
        painter.setBrush(QColor("#ffffff"))
        painter.drawEllipse(QRectF(x, 3.0, radius * 2, radius * 2))


class ColorButton(QPushButton):
    colorChanged = Signal(QColor)

    def __init__(self, color: QColor | str | tuple[int, int, int] = "#ffffff") -> None:
        super().__init__()
        self._color = QColor()
        self.setColor(color)
        self.setFixedSize(46, 28)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Choose a colour")

    def color(self) -> QColor:
        return QColor(self._color)

    def setColor(self, color: QColor | str | tuple[int, int, int]) -> None:
        if isinstance(color, QColor):
            self._color = QColor(color)
        elif isinstance(color, str):
            self._color = QColor(color)
        else:
            self._color = QColor(int(color[0]), int(color[1]), int(color[2]))
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        painter.setPen(QPen(QColor(255, 255, 255, 45), 1))
        painter.setBrush(self._color)
        painter.drawRoundedRect(rect, 7, 7)
        painter.setPen(QPen(QColor(0, 0, 0, 90), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect.adjusted(3, 3, -3, -3), 4, 4)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            chosen = QColorDialog.getColor(self._color, self, "Choose colour")
            if chosen.isValid():
                self.setColor(chosen)
                self.colorChanged.emit(self.color())
        else:
            super().mousePressEvent(event)


class MiniBar(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._value = 0.0
        self.setFixedSize(160, 8)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def setValue(self, value: float | None) -> None:
        self._value = max(0.0, min(100.0, float(value or 0)))
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        track = QRectF(0, 1, self.width(), 6)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#2f2f35"))
        painter.drawRoundedRect(track, 3, 3)
        if self._value <= 0:
            return
        if self._value < 70:
            colour = QColor("#44d62c")
        elif self._value < 85:
            colour = QColor("#f0a63a")
        else:
            colour = QColor("#e5534b")
        painter.setBrush(colour)
        painter.drawRoundedRect(
            QRectF(0, 1, self.width() * self._value / 100.0, 6), 3, 3
        )


class SegmentedControl(QFrame):
    changed = Signal(str)

    def __init__(self, options: Iterable[tuple[str, str]]) -> None:
        super().__init__()
        self.setObjectName("segmentBar")
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        box = QHBoxLayout(self)
        box.setContentsMargins(3, 3, 3, 3)
        box.setSpacing(2)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: dict[str, QPushButton] = {}
        for key, text in options:
            button = QPushButton(text)
            button.setObjectName("segment")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            self._group.addButton(button)
            self._buttons[key] = button
            button.clicked.connect(lambda _checked=False, k=key: self._select(k))
            box.addWidget(button)

    def set_current(self, key: str, emit: bool = False) -> None:
        button = self._buttons.get(key)
        if button is None:
            return
        button.setChecked(True)
        if emit:
            self.changed.emit(key)

    def current(self) -> str:
        for key, button in self._buttons.items():
            if button.isChecked():
                return key
        return ""

    def _select(self, key: str) -> None:
        self.set_current(key)
        self.changed.emit(key)


class Toast(QLabel):
    """A transient message in the bottom centre of the main window."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("toast")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setWordWrap(True)
        self.setMaximumWidth(560)
        self.hide()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

    def show_message(self, text: str, milliseconds: int = 4000) -> None:
        self.setText(text)
        self.adjustSize()
        self.reposition()
        self.show()
        self.raise_()
        self._timer.start(milliseconds)

    def reposition(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        self.adjustSize()
        x = max(12, (parent.width() - self.width()) // 2)
        y = max(12, parent.height() - self.height() - 28)
        self.move(x, y)


class PageScroll(QScrollArea):
    """A page with a title and a vertical list of cards."""

    def __init__(self, title: str, subtitle: str = "") -> None:
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        self.body = QVBoxLayout(content)
        self.body.setContentsMargins(30, 24, 30, 30)
        self.body.setSpacing(18)
        self.body.addWidget(page_header(title, subtitle))
        self.setWidget(content)

    def finish(self) -> None:
        self.body.addStretch(1)


# -- keyboard preview -------------------------------------------------------
class KeyboardView(QWidget):
    """Draw the real German ISO layout, or a plain grid without a key map."""

    def __init__(self) -> None:
        super().__init__()
        self.setMinimumSize(480, 220)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.matrix: Matrix = blank()
        self.on_cell: Callable[[int, int, bool], None] | None = None
        self.on_unmapped: Callable[[object], None] | None = None
        self._selected: tuple[int, int] | None = None
        self._drag = False
        self._last: tuple[int, int] | None = None
        self._mapping = layouts.load_cells()
        self._cells = layouts.cell_lookup(self._mapping)

    def set_matrix(self, matrix: Matrix) -> None:
        self.matrix = matrix
        self.update()

    def set_selected(self, cell: tuple[int, int] | None) -> None:
        self._selected = cell
        self.update()

    def reload_map(self) -> None:
        self._mapping = layouts.load_cells()
        self._cells = layouts.cell_lookup(self._mapping)
        self.update()

    # -- geometry -----------------------------------------------------------
    def _metrics(self) -> tuple[float, float, float]:
        width = float(self.width())
        height = float(self.height())
        if width <= 0 or height <= 0:
            return 1.0, 0.0, 0.0
        unit = min(width / layouts.WIDTH_UNITS, height / layouts.ROWS)
        return (
            unit,
            (width - layouts.WIDTH_UNITS * unit) / 2.0,
            (height - layouts.ROWS * unit) / 2.0,
        )

    def _cell_at(self, x: float, y: float) -> tuple[int, int] | None:
        unit, ox, oy = self._metrics()
        if self._mapping:
            for key in layouts.LAYOUT:
                left, top, width, height = layouts.key_rect(key, unit, ox, oy)
                if left <= x <= left + width and top <= y <= top + height:
                    cell = self._mapping.get(key.code)
                    if cell is None:
                        if self.on_unmapped is not None:
                            self.on_unmapped(key)
                        return None
                    return (cell[0], cell[1])
            return None
        col = int((x - ox) / unit)
        row = int((y - oy) / unit)
        if 0 <= row < ROWS and 0 <= col < COLS:
            return (row, col)
        return None

    # -- interaction --------------------------------------------------------
    def _emit(self, cell: tuple[int, int], erase: bool = False) -> None:
        self.set_selected(cell)
        if self.on_cell is not None and (erase or cell != self._last):
            self.on_cell(cell[0], cell[1], erase)
        self._last = cell

    def mousePressEvent(self, event) -> None:
        cell = self._cell_at(event.position().x(), event.position().y())
        if cell is None:
            return
        if event.button() == Qt.MouseButton.RightButton:
            self._emit(cell, erase=True)
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag = True
            self._last = None
            self._emit(cell)

    def mouseMoveEvent(self, event) -> None:
        if not self._drag:
            return
        cell = self._cell_at(event.position().x(), event.position().y())
        if cell is not None:
            self._emit(cell)

    def mouseReleaseEvent(self, _event) -> None:
        self._drag = False
        self._last = None

    # -- drawing ------------------------------------------------------------
    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#0b0b0d"))
        unit, ox, oy = self._metrics()
        if self._mapping:
            self._draw_keys(painter, unit, ox, oy)
        else:
            self._draw_grid(painter, unit, ox, oy)

    def _draw_grid(self, painter: QPainter, unit: float, ox: float, oy: float) -> None:
        inset = min(3.0, unit / 6.0)
        radius = min(6.0, unit / 4.0)
        for row in range(ROWS):
            for col in range(COLS):
                red, green, blue = self.matrix[row][col]
                colour = QColor("#26262b") if (red, green, blue) == (0, 0, 0) else QColor(red, green, blue)
                rect = QRectF(
                    ox + col * unit + inset,
                    oy + row * unit + inset,
                    unit - inset * 2,
                    unit - inset * 2,
                )
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(colour)
                painter.drawRoundedRect(rect, radius, radius)

    def _draw_keys(self, painter: QPainter, unit: float, ox: float, oy: float) -> None:
        radius = min(7.0, unit / 5.0)
        font = QFont("Segoe UI", 7)
        painter.setFont(font)
        for key in layouts.LAYOUT:
            left, top, width, height = layouts.key_rect(key, unit, ox, oy)
            cell = self._mapping.get(key.code)
            if cell is None or not key.lit:
                colour = QColor("#1a1a1e")
            else:
                red, green, blue = self.matrix[cell[0]][cell[1]]
                colour = QColor("#26262b") if (red, green, blue) == (0, 0, 0) else QColor(red, green, blue)

            rect = QRectF(left, top, width, height)
            path = QPainterPath()
            path.addRoundedRect(rect, radius, radius)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(colour)
            painter.drawPath(path)

            notch = layouts.notch_rect(key, unit, ox, oy)
            if notch is not None:
                cut = QRectF(*notch)
                painter.setBrush(QColor("#0b0b0d"))
                painter.drawRoundedRect(cut, radius, radius)

            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(0, 0, 0, 140), 1.2))
            painter.drawPath(path)

            if self._selected is not None and cell is not None and tuple(cell) == self._selected:
                painter.setPen(QPen(QColor("#44d62c"), 2))
                painter.drawPath(path)

            if key.legend:
                painter.setPen(QColor(255, 255, 255, 190))
                painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, key.legend)


# -- fan curve --------------------------------------------------------------
MIN_TEMP, MAX_TEMP = 30, 100
MIN_RPM, MAX_RPM = 2000, 5000


class CurveEditor(QWidget):
    pointsChanged = Signal(list)

    def __init__(self, points: list[list[int]] | None = None) -> None:
        super().__init__()
        self.setMinimumHeight(190)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.points = self._clean(points or [[45, 3500], [70, 4200], [85, 5000]])
        self._drag_index: int | None = None
        self._padding_left = 42
        self._padding_bottom = 20
        self._padding_top = 10
        self._padding_right = 10

    @staticmethod
    def _clean(points: list[list[int]]) -> list[list[int]]:
        cleaned = [
            [max(MIN_TEMP, min(MAX_TEMP, int(temp))), max(MIN_RPM, min(MAX_RPM, int(rpm)))]
            for temp, rpm in points
        ]
        cleaned.sort(key=lambda point: point[0])
        return cleaned

    def get_points(self) -> list[list[int]]:
        return [list(point) for point in self.points]

    def set_points(self, points: list[list[int]]) -> None:
        self.points = self._clean(points)
        self.update()

    def _plot_rect(self) -> QRectF:
        return QRectF(
            self._padding_left,
            self._padding_top,
            max(10.0, self.width() - self._padding_left - self._padding_right),
            max(10.0, self.height() - self._padding_top - self._padding_bottom),
        )

    def _to_widget(self, temp: float, rpm: float) -> QPointF:
        rect = self._plot_rect()
        x = rect.left() + (temp - MIN_TEMP) / (MAX_TEMP - MIN_TEMP) * rect.width()
        y = rect.bottom() - (rpm - MIN_RPM) / (MAX_RPM - MIN_RPM) * rect.height()
        return QPointF(x, y)

    def _to_values(self, x: float, y: float) -> tuple[int, int]:
        rect = self._plot_rect()
        temp = MIN_TEMP + (x - rect.left()) / max(1.0, rect.width()) * (MAX_TEMP - MIN_TEMP)
        rpm = MIN_RPM + (rect.bottom() - y) / max(1.0, rect.height()) * (MAX_RPM - MIN_RPM)
        return int(temp), int(rpm)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#101013"))
        rect = self._plot_rect()

        grid = QPen(QColor(255, 255, 255, 16), 1)
        painter.setPen(grid)
        for temp in range(MIN_TEMP, MAX_TEMP + 1, 10):
            x = self._to_widget(temp, MIN_RPM).x()
            painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
        for rpm in range(MIN_RPM, MAX_RPM + 1, 500):
            y = self._to_widget(MIN_TEMP, rpm).y()
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))

        painter.setPen(QColor(255, 255, 255, 110))
        small = QFont("Segoe UI", 7)
        painter.setFont(small)
        for temp in (MIN_TEMP, 50, 70, 90, MAX_TEMP):
            x = self._to_widget(temp, MIN_RPM).x()
            painter.drawText(
                QRectF(x - 18, rect.bottom() + 2, 36, 16),
                Qt.AlignmentFlag.AlignHCenter,
                f"{temp}°",
            )
        for rpm in (MIN_RPM, MAX_RPM):
            y = self._to_widget(MIN_TEMP, rpm).y()
            painter.drawText(
                QRectF(0, y - 8, self._padding_left - 5, 16),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                str(rpm),
            )

        points = [self._to_widget(temp, rpm) for temp, rpm in self.points]
        path = QPainterPath(points[0])
        for point in points[1:]:
            path.lineTo(point)
        painter.setPen(QPen(QColor("#44d62c"), 2.4))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#f2f2f2"))
        for point in points:
            painter.drawEllipse(point, 6, 6)

    def mousePressEvent(self, event) -> None:
        best = None
        best_distance = 1e9
        for index, (temp, rpm) in enumerate(self.points):
            point = self._to_widget(temp, rpm)
            distance = (point.x() - event.position().x()) ** 2 + (point.y() - event.position().y()) ** 2
            if distance < best_distance:
                best_distance = distance
                best = index
        self._drag_index = best if best is not None and best_distance <= 900 else None
        if self._drag_index is not None:
            self._update_point(event.position().x(), event.position().y())

    def mouseMoveEvent(self, event) -> None:
        if self._drag_index is not None:
            self._update_point(event.position().x(), event.position().y())

    def mouseReleaseEvent(self, _event) -> None:
        if self._drag_index is not None:
            self._drag_index = None
            self.pointsChanged.emit(self.get_points())

    def _update_point(self, x: float, y: float) -> None:
        temp, rpm = self._to_values(x, y)
        self.points[self._drag_index] = [
            max(MIN_TEMP, min(MAX_TEMP, temp)),
            max(MIN_RPM, min(MAX_RPM, rpm)),
        ]
        self.points.sort(key=lambda point: point[0])
        self.update()
