"""Lighting page: host animations on one side, the keyboard's own on the other.

The custom side is generated from each effect's `SETTINGS`, which is what makes
the effect settings behave like the reference app: only the controls that
matter for the selected effect appear, with the original ranges and defaults.

The device side lists the effects the embedded controller renders itself. The
controller never reports its frames back, so that side shows no matrix preview
and only the parameters the firmware accepts for the selected effect.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gdk, GLib, Gtk  # noqa: E402

from .. import animations, profile, protocol as p  # noqa: E402
from ..animations import AnimationEngine, Params  # noqa: E402
from .widgets import KeyboardView, disable_scale_scroll, paint_cell  # noqa: E402

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
DEVICE_LABELS = {name: label for name, label, _effect in DEVICE_EFFECTS}
DEVICE_IDS = {name: effect for name, _label, effect in DEVICE_EFFECTS}

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
    "off": "The backlight is off. The brightness slider above still applies.",
    "static": "One constant colour for the whole keyboard.",
    "breathing": "The keyboard fades a single colour in and out.",
    "spectrum": "The controller cycles through the full spectrum on its own.",
    "wave": "A band of colour sweeps across the keyboard.",
    "reactive": "Keys light up while you type. The controller handles it, so no "
    "input permissions are needed.",
    "starlight": "A dark background with random keys twinkling.",
}


class LightingPage(Gtk.Box):
    def __init__(self, window) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self.set_margin_top(18)
        self.set_margin_bottom(18)
        self.set_margin_start(18)
        self.set_margin_end(18)

        self.window = window
        self.backend = window.backend
        self.state = window.state
        self.profile = window.profile
        self._syncing = False
        self._mode = "custom"
        self._frame = animations.blank()
        self._paint_mode = False
        self._custom_save = 0
        self._settings_widgets: dict[str, Gtk.Widget] = {}
        self._logo_healed = False
        self._current = "static"
        self._device_values = self._stored_device()
        self._device_name = self._device_values["effect"]

        device = getattr(self.backend, "device", None)
        self.engine = AnimationEngine(device, on_frame=self._on_frame) if device else None

        self.stack = Gtk.Stack()
        self.stack.set_vexpand(True)
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack.set_transition_duration(150)
        self.stack.add_titled(self._build_custom_page(), "custom", "Custom effects")
        self.stack.add_titled(self._build_device_page(), "device", "Device effects")
        self.stack.connect("notify::visible-child-name", self._on_mode_changed)

        self.append(self._build_switcher())
        self.append(self.stack)
        self.append(self._build_footer())

        stored_mode = self.profile.get("lighting", {}).get("mode", "custom")
        self._activate_mode("device" if stored_mode == "device" else "custom")

    # -- top bar ------------------------------------------------------------
    def _build_switcher(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        switcher = Gtk.StackSwitcher()
        switcher.set_stack(self.stack)
        switcher.set_halign(Gtk.Align.START)
        box.append(switcher)
        return box

    # -- custom page --------------------------------------------------------
    def _build_custom_page(self) -> Gtk.Widget:
        page = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=18)
        page.append(self._build_custom_list())
        page.append(self._build_custom_panel())
        return page

    def _build_custom_list(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_size_request(220, -1)

        heading = Gtk.Label(label="EFFECTS", xalign=0)
        heading.add_css_class("section-title")
        box.append(heading)

        note = Gtk.Label(
            label="Rendered by Ophis and sent to the keyboard frame by frame.",
            xalign=0,
            wrap=True,
        )
        note.add_css_class("muted")
        box.append(note)

        self.listbox = Gtk.ListBox()
        self.listbox.add_css_class("effect-list")
        self.listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        for name, label in HOST_EFFECTS:
            row = Gtk.ListBoxRow()
            row.set_name(name)
            text = Gtk.Label(label=label, xalign=0)
            text.set_margin_top(10)
            text.set_margin_bottom(10)
            text.set_margin_start(14)
            text.set_margin_end(14)
            row.set_child(text)
            self.listbox.append(row)
        self.listbox.connect("row-selected", self._on_row_selected)
        box.append(self.listbox)

        spacer = Gtk.Box()
        spacer.set_vexpand(True)
        box.append(spacer)
        return box

    def _build_custom_panel(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        box.set_hexpand(True)

        preview_frame = Gtk.Frame()
        preview_frame.add_css_class("preview")
        self.keyboard = KeyboardView()
        self.keyboard.set_hexpand(True)
        self.keyboard.set_vexpand(True)
        self.keyboard.on_cell = self._on_cell_clicked
        self.keyboard.on_unmapped = self._on_unmapped_key
        preview_frame.set_child(self.keyboard)
        box.append(preview_frame)

        self.map_hint = Gtk.Label(
            label="Key positions are not mapped yet: run "
            "`PYTHONPATH=src python3 tools/mapper.py` once to get the real keyboard layout.",
            xalign=0,
            wrap=True,
        )
        self.map_hint.add_css_class("muted")
        self.map_hint.set_visible(not self.keyboard.mapping)
        box.append(self.map_hint)

        controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.paint_hint = Gtk.Label(label="Drag to paint, right-click to erase")
        self.paint_hint.add_css_class("muted")
        controls.append(self.paint_hint)

        self.brush_button = Gtk.ColorDialogButton(dialog=Gtk.ColorDialog())
        self.brush_button.set_valign(Gtk.Align.CENTER)
        self.brush_button.set_tooltip_text("Brush colour")
        brush = Gdk.RGBA()
        brush.parse("#ffffff")
        self.brush_button.set_rgba(brush)
        controls.append(self.brush_button)

        self.fill_button = Gtk.Button(label="Fill")
        self.fill_button.connect("clicked", self._on_fill)
        controls.append(self.fill_button)

        self.clear_button = Gtk.Button(label="Clear")
        self.clear_button.connect("clicked", self._on_clear)
        controls.append(self.clear_button)

        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        controls.append(spacer)
        box.append(controls)

        settings_holder = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.settings_title = Gtk.Label(label="Settings", xalign=0)
        self.settings_title.add_css_class("effect-title")
        settings_holder.append(self.settings_title)
        self.settings_box = Gtk.ListBox()
        self.settings_box.add_css_class("boxed-list")
        self.settings_box.set_selection_mode(Gtk.SelectionMode.NONE)
        settings_holder.append(self.settings_box)
        settings_frame = Gtk.Frame()
        settings_frame.add_css_class("settings")
        settings_frame.set_child(settings_holder)
        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sw.set_child(settings_frame)
        sw.set_vexpand(True)
        box.append(sw)
        return box

    # -- device page --------------------------------------------------------
    def _build_device_page(self) -> Gtk.Widget:
        page = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=18)

        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        left.set_size_request(220, -1)

        heading = Gtk.Label(label="DEVICE EFFECTS", xalign=0)
        heading.add_css_class("section-title")
        left.append(heading)

        note = Gtk.Label(
            label="Rendered by the keyboard controller: no CPU cost, no input "
            "permissions and fewer parameters.",
            xalign=0,
            wrap=True,
        )
        note.add_css_class("muted")
        left.append(note)

        self.device_listbox = Gtk.ListBox()
        self.device_listbox.add_css_class("effect-list")
        self.device_listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        for name, label, _effect in DEVICE_EFFECTS:
            row = Gtk.ListBoxRow()
            row.set_name(name)
            text = Gtk.Label(label=label, xalign=0)
            text.set_margin_top(10)
            text.set_margin_bottom(10)
            text.set_margin_start(14)
            text.set_margin_end(14)
            row.set_child(text)
            self.device_listbox.append(row)
        self.device_listbox.connect("row-selected", self._on_device_row_selected)
        left.append(self.device_listbox)

        spacer = Gtk.Box()
        spacer.set_vexpand(True)
        left.append(spacer)
        page.append(left)

        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        right.set_hexpand(True)

        self.device_title = Gtk.Label(label="Settings", xalign=0)
        self.device_title.add_css_class("effect-title")
        right.append(self.device_title)

        self.device_note = Gtk.Label(label="", xalign=0, wrap=True)
        self.device_note.add_css_class("muted")
        right.append(self.device_note)

        self.device_settings_box = Gtk.ListBox()
        self.device_settings_box.add_css_class("boxed-list")
        self.device_settings_box.set_selection_mode(Gtk.SelectionMode.NONE)
        settings_frame = Gtk.Frame()
        settings_frame.add_css_class("settings")
        settings_frame.set_child(self.device_settings_box)
        right.append(settings_frame)

        spacer = Gtk.Box()
        spacer.set_vexpand(True)
        right.append(spacer)

        page.append(right)
        return page

    def _build_device_settings(self, name: str) -> None:
        while self.device_settings_box.get_first_child() is not None:
            self.device_settings_box.remove(self.device_settings_box.get_first_child())

        label = DEVICE_LABELS[name]
        self.device_title.set_text(label)
        self.device_note.set_text(DEVICE_NOTES[name])

        keys = DEVICE_SETTINGS[name]
        if not keys:
            row = Adw.ActionRow(title="No settings")
            row.set_subtitle("This effect has nothing to configure.")
            row.set_activatable(False)
            self.device_settings_box.append(row)
            return

        if "colour" in keys:
            row = Adw.ActionRow(title="Colour")
            row.set_activatable(False)
            button = Gtk.ColorDialogButton(dialog=Gtk.ColorDialog())
            button.set_valign(Gtk.Align.CENTER)
            self._set_button_colour(button, self._device_values["colour"])
            button.connect("notify::rgba", self._on_device_colour)
            row.add_suffix(button)
            self.device_settings_box.append(row)

        if "speed" in keys:
            high = DEVICE_SPEED_MAX.get(name, 4)
            speed = max(1, min(high, int(self._device_values["speed"])))
            self._device_values["speed"] = speed
            row = Adw.ActionRow(title="Speed")
            row.set_activatable(False)
            scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 1, high, 1)
            scale.set_value(speed)
            scale.set_size_request(280, -1)
            scale.set_draw_value(True)
            disable_scale_scroll(scale)
            scale.connect("value-changed", self._on_device_speed, name)
            row.add_suffix(scale)
            self.device_settings_box.append(row)

        if "direction" in keys:
            row = Adw.ActionRow(title="Direction")
            row.set_activatable(False)
            combo = Gtk.ComboBoxText()
            combo.append_text("Left to right")
            combo.append_text("Right to left")
            combo.set_active(0 if int(self._device_values["direction"]) == 1 else 1)
            combo.connect("changed", self._on_device_direction)
            row.add_suffix(combo)
            self.device_settings_box.append(row)

    # -- footer -------------------------------------------------------------
    def _build_footer(self) -> Gtk.Widget:
        frame = Gtk.Frame()
        frame.add_css_class("settings")
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)

        box.append(Gtk.Label(label="Brightness"))
        self.brightness = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 255, 5)
        self.brightness.set_size_request(220, -1)
        self.brightness.set_draw_value(True)
        disable_scale_scroll(self.brightness)
        self.brightness.connect("value-changed", self._on_brightness)
        box.append(self.brightness)

        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        box.append(spacer)

        box.append(Gtk.Label(label="Lid logo"))
        self.logo_combo = Gtk.ComboBoxText()
        for option in ("Off", "On", "Breathing"):
            self.logo_combo.append_text(option)
        self.logo_combo.connect("changed", self._on_logo_changed)
        box.append(self.logo_combo)

        frame.set_child(box)
        return frame

    # -- mode ---------------------------------------------------------------
    def _activate_mode(self, mode: str) -> None:
        self._mode = mode
        self._syncing = True
        try:
            self.stack.set_visible_child_name(mode)
        finally:
            self._syncing = False

        if mode == "device":
            self._flush_custom()
            if self.engine is not None:
                self.engine.stop()
            self._select_device(self._device_values["effect"], apply=True)
        else:
            self._select_effect(self._stored_effect())

    def _on_mode_changed(self, stack: Gtk.Stack, _param) -> None:
        if self._syncing:
            return
        mode = stack.get_visible_child_name()
        if mode not in ("custom", "device"):
            return
        self._mode = mode
        self.profile.setdefault("lighting", {})["mode"] = mode
        self.window.save_profile()
        if mode == "device":
            self._flush_custom()
            if self.engine is not None:
                self.engine.stop()
            self._select_device(self._device_values["effect"], apply=True)
        else:
            self._select_effect(self._current)

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

    # -- custom selection ---------------------------------------------------
    def _on_row_selected(self, _listbox, row) -> None:
        if row is None or self._syncing:
            return
        self._select_effect(row.get_name())

    def _select_effect(self, name: str) -> None:
        self._flush_custom()
        self._current = name
        was_syncing = self._syncing
        self._syncing = True
        try:
            for index, (row_name, _label) in enumerate(HOST_EFFECTS):
                if row_name == name:
                    self.listbox.select_row(self.listbox.get_row_at_index(index))
                    break
        finally:
            self._syncing = was_syncing

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
        for widget in (self.brush_button, self.paint_hint, self.fill_button, self.clear_button):
            widget.set_visible(paint)

        if paint:
            if self.engine is not None:
                self.engine.stop()
            self._frame = self._load_custom_frame()
            self.keyboard.set_matrix(self._frame)
            self._write_frame()
            return

        if self.engine is not None:
            self.engine.start(name, params)
            if self.engine.last_error:
                self.window.toast(self.engine.last_error)
        else:
            self._frame = animations.create(name, params).render(0.016)
            self.keyboard.set_matrix(self._frame)

    # -- custom settings panel ---------------------------------------------
    def _build_settings(self, name: str, params: Params) -> None:
        while self.settings_box.get_first_child() is not None:
            self.settings_box.remove(self.settings_box.get_first_child())
        self._settings_widgets.clear()

        self.settings_title.set_text(animations.EFFECTS[name].label)
        for setting in animations.EFFECTS[name].SETTINGS:
            self.settings_box.append(self._setting_row(name, setting, params))

    def _setting_row(self, name: str, setting, params: Params) -> Gtk.Widget:
        row = Adw.ActionRow(title=setting.label)
        row.set_activatable(False)

        if setting.kind == "slider":
            scale = Gtk.Scale.new_with_range(
                Gtk.Orientation.HORIZONTAL, setting.low, setting.high, setting.step
            )
            scale.set_value(getattr(params, setting.key))
            scale.set_size_request(280, -1)
            scale.set_draw_value(True)
            disable_scale_scroll(scale)
            scale.connect(
                "value-changed", self._on_slider, name, setting.key, params
            )
            row.add_suffix(scale)
            self._settings_widgets[setting.key] = scale

        elif setting.kind == "percent":
            actual = float(getattr(params, setting.key))
            span = setting.actual_high - setting.actual_low
            percent = 1.0 + (actual - setting.actual_low) / span * 99.0
            scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 1, 100, 1)
            scale.set_value(round(percent))
            scale.set_size_request(280, -1)
            scale.set_draw_value(False)
            disable_scale_scroll(scale)
            value_label = Gtk.Label(label=f"{int(round(percent))}%")
            value_label.set_size_request(48, -1)
            scale.connect(
                "value-changed",
                self._on_percent,
                name,
                setting,
                params,
                value_label,
            )
            row.add_suffix(scale)
            row.add_suffix(value_label)
            self._settings_widgets[setting.key] = scale

        elif setting.kind == "switch":
            switch = Gtk.Switch()
            switch.set_active(bool(getattr(params, setting.key)))
            switch.set_valign(Gtk.Align.CENTER)
            switch.connect("notify::active", self._on_switch, name, setting.key, params)
            row.add_suffix(switch)

        elif setting.kind == "choice":
            combo = Gtk.ComboBoxText()
            for choice in setting.choices:
                combo.append_text(choice)
            combo.set_active(int(getattr(params, setting.key)))
            combo.connect("changed", self._on_choice, name, setting.key, params)
            row.add_suffix(combo)

        elif setting.kind == "colour":
            button = Gtk.ColorDialogButton(dialog=Gtk.ColorDialog())
            button.set_valign(Gtk.Align.CENTER)
            self._set_button_colour(button, params.colour)
            button.connect("notify::rgba", self._on_colour, name, params, None)
            row.add_suffix(button)

        elif setting.kind == "palette":
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            count = Gtk.Scale.new_with_range(
                Gtk.Orientation.HORIZONTAL, setting.low, setting.high, 1
            )
            count.set_value(params.palette_count)
            count.set_size_request(120, -1)
            count.set_draw_value(True)
            disable_scale_scroll(count)
            count.connect("value-changed", self._on_palette_count, name, params)
            box.append(count)
            for index in range(setting.high):
                button = Gtk.ColorDialogButton(dialog=Gtk.ColorDialog())
                button.set_valign(Gtk.Align.CENTER)
                self._set_button_colour(button, params.palette[index])
                button.set_visible(index < int(params.palette_count))
                button.connect("notify::rgba", self._on_palette_colour, name, params, index)
                box.append(button)
            row.add_suffix(box)

        elif setting.kind == "zone_colours":
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            for index in range(min(int(params.zone_count), setting.high)):
                button = Gtk.ColorDialogButton(dialog=Gtk.ColorDialog())
                button.set_valign(Gtk.Align.CENTER)
                self._set_button_colour(button, params.zone_colours[index])
                button.connect("notify::rgba", self._on_zone_colour, name, params, index)
                box.append(button)
            row.add_suffix(box)

        return row

    @staticmethod
    def _set_button_colour(button: Gtk.ColorDialogButton, colour) -> None:
        rgba = Gdk.RGBA()
        rgba.red, rgba.green, rgba.blue = (channel / 255 for channel in colour)
        rgba.alpha = 1.0
        button.set_rgba(rgba)

    @staticmethod
    def _colour_of(button: Gtk.ColorDialogButton) -> tuple[int, int, int]:
        rgba = button.get_rgba()
        return (int(rgba.red * 255), int(rgba.green * 255), int(rgba.blue * 255))

    # -- custom settings handlers ------------------------------------------
    def _changed(self, name: str, params: Params, restart: bool = False) -> None:
        if self.engine is not None:
            if restart:
                self.engine.start(name, params)
            else:
                self.engine.update_params(params)
        else:
            self._frame = animations.create(name, params).render(0.016)
            self.keyboard.set_matrix(self._frame)
        self._remember(name, params)

    def _on_slider(self, scale: Gtk.Scale, name: str, key: str, params: Params) -> None:
        setattr(params, key, int(scale.get_value()))
        if name == "static" and key == "zone_count":
            self._build_settings(name, params)
            self._changed(name, params, restart=True)
            return
        self._changed(name, params)

    def _on_percent(
        self,
        scale: Gtk.Scale,
        name: str,
        setting,
        params: Params,
        value_label: Gtk.Label,
    ) -> None:
        percent = float(scale.get_value())
        span = setting.actual_high - setting.actual_low
        actual = setting.actual_low + (percent - 1.0) / 99.0 * span
        value_label.set_text(f"{int(percent)}%")
        setattr(params, setting.key, round(actual, 2))
        self._changed(name, params, restart=(name == "static"))

    def _on_switch(self, switch: Gtk.Switch, _param, name: str, key: str, params: Params) -> None:
        setattr(params, key, bool(switch.get_active()))
        if key == "paint":
            self._remember(name, params)
            self._apply_paint_mode(name, params)
            return
        self._changed(name, params)

    def _on_choice(self, combo: Gtk.ComboBoxText, name: str, key: str, params: Params) -> None:
        setattr(params, key, int(combo.get_active()))
        self._changed(name, params, restart=name in ("matrix", "static"))

    def _on_colour(self, button, _pspec, name: str, params: Params, _index) -> None:
        params.colour = self._colour_of(button)
        self._changed(name, params, restart=(name == "static"))

    def _on_palette_count(self, scale: Gtk.Scale, name: str, params: Params) -> None:
        params.palette_count = int(scale.get_value())
        self._build_settings(name, params)
        self._changed(name, params)

    def _on_palette_colour(self, button, _pspec, name: str, params: Params, index: int) -> None:
        params.palette[index] = self._colour_of(button)
        self._changed(name, params)

    def _on_zone_count(self, scale: Gtk.Scale, name: str, params: Params) -> None:
        params.zone_count = int(scale.get_value())
        self._changed(name, params, restart=True)

    def _on_zone_colour(self, button, _pspec, name: str, params: Params, index: int) -> None:
        params.zone_colours[index] = self._colour_of(button)
        self._changed(name, params, restart=True)

    def _on_unmapped_key(self, key) -> None:
        if not key.lit:
            self.window.toast("This key has no LED on this model")
        else:
            self.window.toast(f"{key.legend or key.code} is not mapped yet")

    # -- device selection / handlers ---------------------------------------
    def _on_device_row_selected(self, _listbox, row) -> None:
        if row is None or self._syncing:
            return
        self._select_device(row.get_name(), apply=True)

    def _select_device(self, name: str, apply: bool = False) -> None:
        if name not in DEVICE_LABELS:
            name = "static"
        self._device_name = name
        self._device_values["effect"] = name
        was_syncing = self._syncing
        self._syncing = True
        try:
            for index, (row_name, _label, _effect) in enumerate(DEVICE_EFFECTS):
                if row_name == name:
                    self.device_listbox.select_row(
                        self.device_listbox.get_row_at_index(index)
                    )
                    break
        finally:
            self._syncing = was_syncing
        self._build_device_settings(name)
        if apply:
            self._apply_device_effect()

    def _on_device_colour(self, button, _pspec) -> None:
        if self._syncing:
            return
        self._device_values["colour"] = self._colour_of(button)
        self._apply_device_effect()

    def _on_device_speed(self, scale: Gtk.Scale, _name: str) -> None:
        if self._syncing:
            return
        self._device_values["speed"] = int(scale.get_value())
        self._apply_device_effect()

    def _on_device_direction(self, combo: Gtk.ComboBoxText) -> None:
        if self._syncing:
            return
        self._device_values["direction"] = 1 if combo.get_active() == 0 else 2
        self._apply_device_effect()

    def _apply_device_effect(self) -> None:
        name = self._device_name
        effect = DEVICE_IDS[name]
        colour = tuple(self._device_values["colour"])
        speed = int(self._device_values["speed"])
        direction = int(self._device_values["direction"])

        if self.engine is not None:
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
        # The flat keys are what profile.apply() replays at startup.
        lighting["effect"] = name
        lighting["colour"] = list(colour)
        lighting["speed"] = speed
        lighting["direction"] = direction
        self.window.save_profile()

    # -- preview / painting -------------------------------------------------
    def _on_frame(self, matrix) -> None:
        self._frame = matrix
        self.keyboard.set_matrix(matrix)
        return False

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

    def _touch_custom(self) -> None:
        if self._custom_save:
            GLib.source_remove(self._custom_save)
        self._custom_save = GLib.timeout_add(600, self._flush_custom)

    def _flush_custom(self) -> bool:
        self._custom_save = 0
        if not self._paint_mode:
            return False
        self.profile.setdefault("lighting", {})["custom"] = [
            list(cell) for row in self._frame for cell in row
        ]
        self.profile["lighting"]["animation"] = "custom"
        self.profile["lighting"]["mode"] = "custom"
        self.window.save_profile()
        return False

    def _write_frame(self) -> None:
        try:
            self.backend.activate_custom_frame()
            self.backend.write_frame(self._frame)
        except Exception as exc:
            self.window.toast(str(exc))

    def _on_cell_clicked(self, row: int, col: int, erase: bool = False) -> None:
        if not self._paint_mode:
            return
        if erase:
            colour = (0, 0, 0)
        else:
            rgba = self.brush_button.get_rgba()
            colour = (int(rgba.red * 255), int(rgba.green * 255), int(rgba.blue * 255))
        self._frame = paint_cell(self._frame, row, col, colour)
        self.keyboard.set_matrix(self._frame)
        try:
            self.backend.write_frame(self._frame)
        except Exception as exc:
            self.window.toast(str(exc))
        self._touch_custom()

    def _on_fill(self, *_args) -> None:
        rgba = self.brush_button.get_rgba()
        colour = (int(rgba.red * 255), int(rgba.green * 255), int(rgba.blue * 255))
        self._frame = [[colour for _ in range(animations.COLS)] for _ in range(animations.ROWS)]
        self.keyboard.set_matrix(self._frame)
        self._write_frame()
        self._touch_custom()

    def _on_clear(self, *_args) -> None:
        self._frame = animations.blank()
        self.keyboard.set_matrix(self._frame)
        self._write_frame()
        self._touch_custom()

    def _on_brightness(self, scale: Gtk.Scale) -> None:
        if self._syncing:
            return
        value = int(scale.get_value())
        try:
            self.backend.set_brightness(value)
            self.state.brightness = value
            self.profile["lighting"]["brightness"] = value
            self.window.save_profile()
        except Exception as exc:
            self.window.toast(str(exc))

    def _on_logo_changed(self, combo: Gtk.ComboBoxText) -> None:
        if self._syncing:
            return
        mode = int(combo.get_active())
        try:
            self.backend.set_logo(mode)
            self.state.logo = mode
            self.profile["lighting"]["logo"] = mode
            self.window.save_profile()
        except Exception as exc:
            self.window.toast(str(exc))

    # -- state --------------------------------------------------------------
    def sync(self) -> None:
        self._syncing = True
        try:
            self.brightness.set_value(int(self.state.brightness))
            logo = int(self.state.logo) if int(self.state.logo) in (0, 1, 2) else 0
            self.logo_combo.set_active(logo)
        finally:
            self._syncing = False

        if not self._logo_healed:
            self._logo_healed = True
            if int(self.state.logo) in (1, 2):
                # The EC can report the logo as on while its brightness is zero
                # (for example after a controller reset). Re-apply it once.
                try:
                    self.backend.set_logo(int(self.state.logo))
                except Exception:
                    pass
