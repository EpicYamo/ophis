"""Lighting page for the Windows build.

Custom effects are rendered by Ophis and written frame by frame. Device
effects run inside the keyboard controller; that side has no readable frames,
so it shows only the parameters the firmware accepts.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .. import animations, protocol as p
from ..animations import Params
from .engine import QtAnimationEngine
from .widgets import (
    Card,
    ColorButton,
    KeyboardView,
    SegmentedControl,
    SettingRow,
    SettingsCard,
    ToggleSwitch,
    label,
    section_label,
)

HOST_EFFECTS = [
    ("static", "Static"),
    ("breathing", "Breathing"),
    ("wave", "Wave"),
    ("wheel", "Wheel"),
    ("sparkle", "Sparkle"),
    ("lightning", "Lightning"),
    ("flame", "Flame"),
    ("rain", "Rain"),
    ("matrix", "Matrix"),
]

DEVICE_EFFECTS = [
    ("off", "Off", p.Effect.OFF),
    ("static", "Static", p.Effect.STATIC),
    ("breathing", "Breathing", p.Effect.BREATHING),
    ("spectrum", "Spectrum", p.Effect.SPECTRUM),
    ("wave", "Wave", p.Effect.WAVE),
    ("reactive", "Reactive", p.Effect.REACTIVE),
    ("starlight", "Starlight", p.Effect.STARLIGHT),
]
DEVICE_LABELS = {name: text for name, text, _effect in DEVICE_EFFECTS}
DEVICE_IDS = {name: effect for name, _text, effect in DEVICE_EFFECTS}

DEVICE_SETTINGS = {
    "off": (),
    "static": ("colour",),
    "breathing": ("colour",),
    "spectrum": (),
    "wave": ("direction",),
    "reactive": ("colour", "speed"),
    "starlight": ("colour", "speed"),
}
DEVICE_SPEED_MAX = {"reactive": 4, "starlight": 3}
DEVICE_NOTES = {
    "off": "The backlight is off. The brightness slider still applies.",
    "static": "One constant colour for the whole keyboard.",
    "breathing": "The keyboard fades a single colour in and out.",
    "spectrum": "The controller cycles through the full spectrum on its own.",
    "wave": "A band of colour sweeps across the keyboard.",
    "reactive": "Keys light up while you type. The controller handles it, so no input permissions are needed.",
    "starlight": "A dark background with random keys twinkling.",
}


def paint_cell(matrix, row: int, col: int, colour):
    updated = [list(line) for line in matrix]
    updated[row][col] = tuple(colour)
    return updated


class LightingPage(QWidget):
    def __init__(self, window) -> None:
        super().__init__()
        self.window = window
        self.backend = window.backend
        self.state = window.state
        self.profile = window.profile
        self._syncing = False
        self._mode = "custom"
        self._frame = animations.blank()
        self._paint_mode = False
        self._settings_widgets: dict[str, QWidget] = {}
        self._logo_healed = False
        self._current = "static"
        self._device_values = self._stored_device()
        self._device_name = self._device_values["effect"]

        self.engine = QtAnimationEngine(self.backend)
        self.engine.frameReady.connect(self._on_frame)

        self._custom_save = QTimer(self)
        self._custom_save.setSingleShot(True)
        self._custom_save.setInterval(600)
        self._custom_save.timeout.connect(self._flush_custom)

        root = QVBoxLayout(self)
        root.setContentsMargins(30, 24, 30, 24)
        root.setSpacing(14)

        self.segmented = SegmentedControl(
            (("custom", "Custom effects"), ("device", "Device effects"))
        )
        self.segmented.changed.connect(self._on_mode_changed)
        root.addWidget(self.segmented, 0, Qt.AlignmentFlag.AlignLeft)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_custom_page())
        self.stack.addWidget(self._build_device_page())
        root.addWidget(self.stack, 1)

        root.addWidget(self._build_footer())

        stored_mode = self.profile.get("lighting", {}).get("mode", "custom")
        self._activate_mode("device" if stored_mode == "device" else "custom")

    # -- custom page --------------------------------------------------------
    def _build_custom_page(self) -> QWidget:
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(18)

        left = QVBoxLayout()
        left.setSpacing(8)
        left.addWidget(section_label("Effects"))
        left.addWidget(
            label(
                "Rendered by Ophis and sent to the keyboard frame by frame.",
                muted=True,
                wrap=True,
            )
        )
        self.effect_list = QListWidget()
        self.effect_list.setObjectName("effectList")
        self.effect_list.setMinimumWidth(220)
        self.effect_list.setMaximumWidth(250)
        self.effect_list.setMinimumHeight(320)
        self.effect_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        for _name, text in HOST_EFFECTS:
            self.effect_list.addItem(text)
        self.effect_list.currentRowChanged.connect(self._on_host_row)
        left.addWidget(self.effect_list, 1)
        layout.addLayout(left)

        right = QVBoxLayout()
        right.setSpacing(12)

        preview_card = Card(spacing=0)
        preview_card.body.setContentsMargins(0, 0, 0, 0)
        self.keyboard = KeyboardView()
        self.keyboard.on_cell = self._on_cell
        self.keyboard.on_unmapped = self._on_unmapped
        preview_card.add(self.keyboard)
        right.addWidget(preview_card, 1)

        paint_row = QHBoxLayout()
        paint_row.setSpacing(10)
        self.paint_hint = label("Drag to paint, right-click to erase", muted=True)
        paint_row.addWidget(self.paint_hint)
        self.brush = ColorButton("#ffffff")
        paint_row.addWidget(self.brush)
        self.fill_button = self._small_button("Fill", self._on_fill)
        paint_row.addWidget(self.fill_button)
        self.clear_button = self._small_button("Clear", self._on_clear)
        paint_row.addWidget(self.clear_button)
        paint_row.addStretch(1)
        self.paint_widgets = [
            self.paint_hint,
            self.brush,
            self.fill_button,
            self.clear_button,
        ]
        right.addLayout(paint_row)

        self.settings_title = QLabel("Settings")
        self.settings_title.setObjectName("effectTitle")
        right.addWidget(self.settings_title)

        self.settings_card = SettingsCard()
        settings_scroll = QScrollArea()
        settings_scroll.setWidgetResizable(True)
        settings_scroll.setFrameShape(QFrame.Shape.NoFrame)
        settings_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        settings_scroll.setWidget(self.settings_card)
        settings_scroll.setMinimumHeight(190)
        settings_scroll.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        right.addWidget(settings_scroll, 1)

        layout.addLayout(right, 1)
        return page

    @staticmethod
    def _small_button(text: str, callback) -> QWidget:
        from PySide6.QtWidgets import QPushButton

        button = QPushButton(text)
        button.clicked.connect(callback)
        return button

    # -- device page --------------------------------------------------------
    def _build_device_page(self) -> QWidget:
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(18)

        left = QVBoxLayout()
        left.setSpacing(8)
        left.addWidget(section_label("Device effects"))
        left.addWidget(
            label(
                "Rendered by the keyboard controller: no CPU cost, no input "
                "permissions and fewer parameters.",
                muted=True,
                wrap=True,
            )
        )
        self.device_list = QListWidget()
        self.device_list.setObjectName("effectList")
        self.device_list.setMinimumWidth(220)
        self.device_list.setMaximumWidth(250)
        self.device_list.setMinimumHeight(280)
        self.device_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        for _name, text, _effect in DEVICE_EFFECTS:
            self.device_list.addItem(text)
        self.device_list.currentRowChanged.connect(self._on_device_row)
        left.addWidget(self.device_list, 1)
        layout.addLayout(left)

        right = QVBoxLayout()
        right.setSpacing(8)
        self.device_title = QLabel("Settings")
        self.device_title.setObjectName("effectTitle")
        right.addWidget(self.device_title)
        self.device_note = label("", muted=True, wrap=True)
        right.addWidget(self.device_note)
        self.device_card = SettingsCard()
        right.addWidget(self.device_card)
        right.addStretch(1)
        layout.addLayout(right, 1)
        return page

    # -- footer -------------------------------------------------------------
    def _build_footer(self) -> QWidget:
        card = Card(spacing=0)
        card.body.setContentsMargins(16, 10, 16, 10)
        row = QHBoxLayout()
        row.setSpacing(12)
        row.addWidget(QLabel("Brightness"))
        self.brightness = QSlider(Qt.Orientation.Horizontal)
        self.brightness.setRange(0, 255)
        self.brightness.setSingleStep(5)
        self.brightness.setPageStep(25)
        self.brightness.setFixedWidth(230)
        self.brightness.valueChanged.connect(self._on_brightness)
        row.addWidget(self.brightness)
        self.brightness_value = QLabel("0")
        self.brightness_value.setProperty("muted", True)
        self.brightness_value.setFixedWidth(30)
        row.addWidget(self.brightness_value)
        row.addStretch(1)
        row.addWidget(QLabel("Lid logo"))
        self.logo_combo = QComboBox()
        self.logo_combo.addItems(["Off", "On", "Breathing"])
        self.logo_combo.currentIndexChanged.connect(self._on_logo)
        row.addWidget(self.logo_combo)
        card.body.addLayout(row)
        return card

    # -- persistence --------------------------------------------------------
    def _stored_effect(self) -> str:
        stored = self.profile.get("lighting", {}).get("animation")
        if stored == "custom":
            return "static"
        return stored if stored in animations.EFFECTS else "static"

    def _stored_values(self, name: str) -> dict:
        data = self.profile.get("lighting", {}).get("animations", {}).get(name, {})
        return data if isinstance(data, dict) else {}

    def _stored_device(self) -> dict:
        lighting = self.profile.get("lighting", {})
        data = lighting.get("device")
        if not isinstance(data, dict):
            data = {}
        name = str(data.get("effect", lighting.get("effect", "static")))
        if name not in DEVICE_LABELS:
            name = "static"
        colour = data.get("colour", lighting.get("colour", (255, 255, 255)))
        try:
            colour = tuple(max(0, min(255, int(channel))) for channel in colour)[:3]
        except (TypeError, ValueError):
            colour = (255, 255, 255)
        if len(colour) != 3:
            colour = (255, 255, 255)
        try:
            speed = max(1, min(4, int(data.get("speed", lighting.get("speed", 2)))))
        except (TypeError, ValueError):
            speed = 2
        try:
            direction = 2 if int(data.get("direction", lighting.get("direction", 1))) == 2 else 1
        except (TypeError, ValueError):
            direction = 1
        return {
            "effect": name,
            "colour": colour,
            "speed": speed,
            "direction": direction,
        }

    def _remember(self, name: str, params: Params) -> None:
        self.profile.setdefault("lighting", {}).setdefault("animations", {})[name] = {
            "colour": list(params.colour),
            "speed": params.speed,
            "smooth": params.smooth,
            "angle": params.angle,
            "density": params.density,
            "width": params.width,
            "concurrent": params.concurrent,
            "reverse": params.reverse,
            "style": params.style,
            "horizontal": params.horizontal,
            "paint": params.paint,
            "zone_count": params.zone_count,
            "palette_count": params.palette_count,
            "palette": [list(c) for c in params.palette],
            "zone_colours": [list(c) for c in params.zone_colours],
        }
        self.profile["lighting"]["animation"] = name
        self.profile["lighting"]["mode"] = "custom"
        self.window.save_profile()

    # -- mode ---------------------------------------------------------------
    def _activate_mode(self, mode: str) -> None:
        self._mode = mode
        self.segmented.set_current(mode)
        self.stack.setCurrentIndex(0 if mode == "custom" else 1)
        if mode == "device":
            self._flush_custom()
            self.engine.stop()
            self._select_device(self._device_values["effect"], apply=True)
        else:
            self._select_effect(self._stored_effect())

    def _on_mode_changed(self, mode: str) -> None:
        if mode == self._mode:
            return
        self._mode = mode
        self.stack.setCurrentIndex(0 if mode == "custom" else 1)
        self.profile.setdefault("lighting", {})["mode"] = mode
        self.window.save_profile()
        if mode == "device":
            self._flush_custom()
            self.engine.stop()
            self._select_device(self._device_values["effect"], apply=True)
        else:
            self._select_effect(self._current)

    # -- host selection -----------------------------------------------------
    def _on_host_row(self, index: int) -> None:
        if self._syncing or index < 0 or index >= len(HOST_EFFECTS):
            return
        self._select_effect(HOST_EFFECTS[index][0])

    def _select_effect(self, name: str) -> None:
        self._flush_custom()
        self._current = name
        for index, (row_name, _text) in enumerate(HOST_EFFECTS):
            if row_name == name:
                self._syncing = True
                self.effect_list.setCurrentRow(index)
                self._syncing = False
                break

        params = animations.default_params(name)
        saved = self._stored_values(name)
        if saved:
            for key, value in saved.items():
                if key in ("palette", "zone_colours"):
                    setattr(params, key, [tuple(item) for item in value])
                elif hasattr(params, key):
                    setattr(params, key, value)

        self._build_settings(name, params)
        self.params = params
        self._apply_paint_mode(name, params)

    def _apply_paint_mode(self, name: str, params: Params) -> None:
        paint = name == "static" and bool(getattr(params, "paint", False))
        self._paint_mode = paint
        for widget in self.paint_widgets:
            widget.setVisible(paint)

        if paint:
            self.engine.stop()
            self._frame = self._load_custom_frame()
            self.keyboard.set_matrix(self._frame)
            if self.isVisible():
                self._write_frame()
            return

        if not getattr(self.backend, "connected", False):
            self.engine.stop()
            self._frame = animations.create(name, params).render(0.016)
            self.keyboard.set_matrix(self._frame)
            return

        if not self.isVisible():
            # Do not animate in the background: a tray-only start should leave
            # the controller alone until the user opens this page.
            self.engine.stop()
            self._frame = animations.create(name, params).render(0.016)
            self.keyboard.set_matrix(self._frame)
            return

        self.engine.start(name, params)
        if self.engine.last_error:
            self.window.toast(self.engine.last_error)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._mode != "custom":
            return
        if self._paint_mode:
            self._write_frame()
            return
        if getattr(self, "params", None) is None:
            return
        if not getattr(self.backend, "connected", False):
            return
        self.engine.start(self._current, self.params)
        if self.engine.last_error:
            self.window.toast(self.engine.last_error)

    def hideEvent(self, event) -> None:
        self.engine.stop()
        super().hideEvent(event)

    def refresh_connection(self) -> None:
        """Restart a stopped animation after a reconnect."""
        if self._mode != "custom" or not self.isVisible():
            return
        if getattr(self.backend, "connected", False) and not self._paint_mode:
            self.engine.start(self._current, self.params)
            if self.engine.last_error:
                self.window.toast(self.engine.last_error)

    # -- host settings ------------------------------------------------------
    def _clear_card(self, card: SettingsCard) -> None:
        while card.body.count():
            item = card.body.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _build_settings(self, name: str, params: Params) -> None:
        self._clear_card(self.settings_card)
        self._settings_widgets.clear()
        self.settings_title.setText(animations.EFFECTS[name].label)
        for setting in animations.EFFECTS[name].SETTINGS:
            self.settings_card.add_row(self._setting_row(name, setting, params))

    def _setting_row(self, name: str, setting, params: Params) -> SettingRow:
        row = SettingRow(setting.label)

        if setting.kind == "slider":
            scale = QSlider(Qt.Orientation.Horizontal)
            scale.setRange(int(setting.low), int(setting.high))
            scale.setSingleStep(max(1, int(setting.step)))
            scale.setPageStep(max(1, int(setting.step) * 5))
            scale.setValue(int(getattr(params, setting.key)))
            scale.setFixedWidth(280)
            value = QLabel(str(scale.value()))
            value.setProperty("muted", True)
            value.setFixedWidth(38)
            scale.valueChanged.connect(
                lambda v, n=name, k=setting.key, p=params, lbl=value: self._on_slider(
                    v, n, k, p, lbl
                )
            )
            row.add_control(scale)
            row.add_control(value)
            self._settings_widgets[setting.key] = scale

        elif setting.kind == "percent":
            actual = float(getattr(params, setting.key))
            span = setting.actual_high - setting.actual_low
            percent = 1.0 + (actual - setting.actual_low) / span * 99.0
            scale = QSlider(Qt.Orientation.Horizontal)
            scale.setRange(1, 100)
            scale.setValue(round(percent))
            scale.setFixedWidth(280)
            value = QLabel(f"{int(round(percent))}%")
            value.setProperty("muted", True)
            value.setFixedWidth(48)
            scale.valueChanged.connect(
                lambda v, n=name, s=setting, p=params, lbl=value: self._on_percent(
                    v, n, s, p, lbl
                )
            )
            row.add_control(scale)
            row.add_control(value)
            self._settings_widgets[setting.key] = scale

        elif setting.kind == "switch":
            switch = ToggleSwitch(bool(getattr(params, setting.key)))
            switch.toggled.connect(
                lambda checked, n=name, k=setting.key, p=params: self._on_switch(
                    checked, n, k, p
                )
            )
            row.add_control(switch)

        elif setting.kind == "choice":
            combo = QComboBox()
            combo.addItems(setting.choices)
            combo.setCurrentIndex(int(getattr(params, setting.key)))
            combo.currentIndexChanged.connect(
                lambda index, n=name, k=setting.key, p=params: self._on_choice(
                    index, n, k, p
                )
            )
            row.add_control(combo)

        elif setting.kind == "colour":
            button = ColorButton(params.colour)
            button.colorChanged.connect(
                lambda colour, n=name, p=params: self._on_colour(colour, n, p)
            )
            row.add_control(button)

        elif setting.kind == "palette":
            count = QSlider(Qt.Orientation.Horizontal)
            count.setRange(int(setting.low), int(setting.high))
            count.setValue(int(params.palette_count))
            count.setFixedWidth(110)
            count.valueChanged.connect(
                lambda value, n=name, p=params: self._on_palette_count(value, n, p)
            )
            row.add_control(count)
            for index in range(setting.high):
                button = ColorButton(params.palette[index])
                button.setVisible(index < int(params.palette_count))
                button.colorChanged.connect(
                    lambda colour, n=name, p=params, i=index: self._on_palette_colour(
                        colour, n, p, i
                    )
                )
                row.add_control(button)

        elif setting.kind == "zone_colours":
            for index in range(min(int(params.zone_count), setting.high)):
                button = ColorButton(params.zone_colours[index])
                button.colorChanged.connect(
                    lambda colour, n=name, p=params, i=index: self._on_zone_colour(
                        colour, n, p, i
                    )
                )
                row.add_control(button)

        return row

    # -- host handlers ------------------------------------------------------
    def _changed(self, name: str, params: Params, restart: bool = False) -> None:
        if restart:
            self.engine.start(name, params)
        else:
            self.engine.update_params(params)
        self._remember(name, params)

    def _on_slider(self, value: int, name: str, key: str, params: Params, label: QLabel) -> None:
        label.setText(str(value))
        setattr(params, key, int(value))
        if name == "static" and key == "zone_count":
            self._build_settings(name, params)
            self._changed(name, params, restart=True)
            return
        self._changed(name, params)

    def _on_percent(self, value: int, name: str, setting, params: Params, label: QLabel) -> None:
        label.setText(f"{value}%")
        span = setting.actual_high - setting.actual_low
        actual = setting.actual_low + (value - 1.0) / 99.0 * span
        setattr(params, setting.key, round(actual, 2))
        self._changed(name, params, restart=(name == "static"))

    def _on_switch(self, checked: bool, name: str, key: str, params: Params) -> None:
        setattr(params, key, bool(checked))
        if key == "paint":
            self._remember(name, params)
            self._apply_paint_mode(name, params)
            return
        self._changed(name, params)

    def _on_choice(self, index: int, name: str, key: str, params: Params) -> None:
        setattr(params, key, int(index))
        self._changed(name, params, restart=name in ("matrix", "static"))

    def _on_colour(self, colour, name: str, params: Params) -> None:
        params.colour = (colour.red(), colour.green(), colour.blue())
        self._changed(name, params, restart=(name == "static"))

    def _on_palette_count(self, value: int, name: str, params: Params) -> None:
        params.palette_count = int(value)
        self._build_settings(name, params)
        self._changed(name, params)

    def _on_palette_colour(self, colour, name: str, params: Params, index: int) -> None:
        params.palette[index] = (colour.red(), colour.green(), colour.blue())
        self._changed(name, params)

    def _on_zone_count(self, value: int, name: str, params: Params) -> None:
        params.zone_count = int(value)
        self._changed(name, params, restart=True)

    def _on_zone_colour(self, colour, name: str, params: Params, index: int) -> None:
        params.zone_colours[index] = (colour.red(), colour.green(), colour.blue())
        self._changed(name, params, restart=True)

    def _on_unmapped(self, key) -> None:
        if not key.lit:
            self.window.toast("This key has no LED on this model")
        else:
            self.window.toast(f"{key.legend or key.code} is not mapped yet")

    def _on_cell(self, row: int, col: int, erase: bool = False) -> None:
        if not self._paint_mode:
            return
        colour = (0, 0, 0) if erase else (
            self.brush.color().red(),
            self.brush.color().green(),
            self.brush.color().blue(),
        )
        self._frame = paint_cell(self._frame, row, col, colour)
        self.keyboard.set_matrix(self._frame)
        try:
            self.backend.write_frame(self._frame)
        except Exception as exc:
            self.window.toast(str(exc))
        self._custom_save.start()

    def _on_fill(self) -> None:
        colour = (
            self.brush.color().red(),
            self.brush.color().green(),
            self.brush.color().blue(),
        )
        self._frame = [[colour for _ in range(animations.COLS)] for _ in range(animations.ROWS)]
        self.keyboard.set_matrix(self._frame)
        self._write_frame()
        self._custom_save.start()

    def _on_clear(self) -> None:
        self._frame = animations.blank()
        self.keyboard.set_matrix(self._frame)
        self._write_frame()
        self._custom_save.start()

    def _on_frame(self, matrix) -> None:
        self._frame = matrix
        self.keyboard.set_matrix(matrix)

    def _load_custom_frame(self):
        stored = self.profile.get("lighting", {}).get("custom")
        matrix = animations.blank()
        if isinstance(stored, list):
            for index, colour in enumerate(stored[: animations.ROWS * animations.COLS]):
                if isinstance(colour, list) and len(colour) == 3:
                    matrix[index // animations.COLS][index % animations.COLS] = (
                        int(colour[0]),
                        int(colour[1]),
                        int(colour[2]),
                    )
        return matrix

    def _flush_custom(self) -> None:
        self._custom_save.stop()
        if not self._paint_mode:
            return
        self.profile.setdefault("lighting", {})["custom"] = [
            list(cell) for row in self._frame for cell in row
        ]
        self.profile["lighting"]["animation"] = "custom"
        self.profile["lighting"]["mode"] = "custom"
        self.window.save_profile()

    def _write_frame(self) -> None:
        try:
            self.backend.activate_custom_frame()
            self.backend.write_frame(self._frame)
        except Exception as exc:
            self.window.toast(str(exc))

    # -- device selection ---------------------------------------------------
    def _on_device_row(self, index: int) -> None:
        if self._syncing or index < 0 or index >= len(DEVICE_EFFECTS):
            return
        self._select_device(DEVICE_EFFECTS[index][0], apply=True)

    def _select_device(self, name: str, apply: bool = False) -> None:
        if name not in DEVICE_LABELS:
            name = "static"
        self._device_name = name
        self._device_values["effect"] = name
        for index, (row_name, _text, _effect) in enumerate(DEVICE_EFFECTS):
            if row_name == name:
                self._syncing = True
                self.device_list.setCurrentRow(index)
                self._syncing = False
                break
        self._build_device_settings(name)
        if apply:
            self._apply_device_effect()

    def _build_device_settings(self, name: str) -> None:
        self._clear_card(self.device_card)
        self.device_title.setText(DEVICE_LABELS[name])
        self.device_note.setText(DEVICE_NOTES[name])

        keys = DEVICE_SETTINGS[name]
        if not keys:
            row = SettingRow("No settings", "This effect has nothing to configure.")
            self.device_card.add_row(row)
            return

        if "colour" in keys:
            row = SettingRow("Colour")
            button = ColorButton(self._device_values["colour"])
            button.colorChanged.connect(self._on_device_colour)
            row.add_control(button)
            self.device_card.add_row(row)

        if "speed" in keys:
            high = DEVICE_SPEED_MAX.get(name, 4)
            speed = max(1, min(high, int(self._device_values["speed"])))
            self._device_values["speed"] = speed
            row = SettingRow("Speed")
            scale = QSlider(Qt.Orientation.Horizontal)
            scale.setRange(1, high)
            scale.setValue(speed)
            scale.setFixedWidth(280)
            value = QLabel(str(speed))
            value.setProperty("muted", True)
            value.setFixedWidth(26)
            scale.valueChanged.connect(
                lambda v, lbl=value: (lbl.setText(str(v)), self._on_device_speed(v))
            )
            row.add_control(scale)
            row.add_control(value)
            self.device_card.add_row(row)

        if "direction" in keys:
            row = SettingRow("Direction")
            combo = QComboBox()
            combo.addItems(["Left to right", "Right to left"])
            combo.setCurrentIndex(0 if int(self._device_values["direction"]) == 1 else 1)
            combo.currentIndexChanged.connect(self._on_device_direction)
            row.add_control(combo)
            self.device_card.add_row(row)

    def _on_device_colour(self, colour) -> None:
        self._device_values["colour"] = (colour.red(), colour.green(), colour.blue())
        self._apply_device_effect()

    def _on_device_speed(self, value: int) -> None:
        self._device_values["speed"] = int(value)
        self._apply_device_effect()

    def _on_device_direction(self, index: int) -> None:
        self._device_values["direction"] = 1 if index == 0 else 2
        self._apply_device_effect()

    def _apply_device_effect(self) -> None:
        name = self._device_name
        effect = DEVICE_IDS[name]
        colour = tuple(self._device_values["colour"])
        speed = int(self._device_values["speed"])
        direction = int(self._device_values["direction"])
        self.engine.stop()
        try:
            self.backend.set_effect(effect, colour, speed, direction)
        except Exception as exc:
            self.window.toast(str(exc))
            return

        self.state.extra["effect"] = int(effect)
        self.state.extra["speed"] = speed
        self.state.extra["direction"] = direction
        if effect != p.Effect.OFF:
            self.state.extra["color"] = colour

        lighting = self.profile.setdefault("lighting", {})
        lighting["mode"] = "device"
        lighting["device"] = {
            "effect": name,
            "colour": list(colour),
            "speed": speed,
            "direction": direction,
        }
        lighting["effect"] = name
        lighting["colour"] = list(colour)
        lighting["speed"] = speed
        lighting["direction"] = direction
        self.window.save_profile()

    # -- footer handlers ----------------------------------------------------
    def _on_brightness(self, value: int) -> None:
        self.brightness_value.setText(str(value))
        if self._syncing:
            return
        try:
            self.backend.set_brightness(value)
            self.state.brightness = value
            self.profile["lighting"]["brightness"] = value
            self.window.save_profile()
        except Exception as exc:
            self.window.toast(str(exc))

    def _on_logo(self, index: int) -> None:
        if self._syncing:
            return
        try:
            self.backend.set_logo(index)
            self.state.logo = index
            self.profile["lighting"]["logo"] = index
            self.window.save_profile()
        except Exception as exc:
            self.window.toast(str(exc))

    # -- state --------------------------------------------------------------
    def sync(self) -> None:
        self._syncing = True
        try:
            brightness = int(self.state.brightness)
            self.brightness.setValue(brightness)
            self.brightness_value.setText(str(brightness))
            logo = int(self.state.logo) if int(self.state.logo) in (0, 1, 2) else 0
            self.logo_combo.setCurrentIndex(logo)
        finally:
            self._syncing = False

        if not self._logo_healed:
            self._logo_healed = True
            if int(self.state.logo) in (1, 2):
                try:
                    self.backend.set_logo(int(self.state.logo))
                except Exception:
                    pass
