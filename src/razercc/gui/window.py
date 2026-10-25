"""GTK4 / libadwaita control window."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gdk, GLib, Gtk  # noqa: E402

from .. import protocol as p  # noqa: E402
from .. import sysinfo  # noqa: E402
from ..backend import Backend  # noqa: E402

POWER_MODES = [
    ("Balanced", p.PowerMode.BALANCED),
    ("Gaming", p.PowerMode.GAMING),
    ("Creator", p.PowerMode.CREATOR),
    ("Custom", p.PowerMode.CUSTOM),
]
BOOST_LEVELS = ["Low", "Normal", "High", "Boost"]
EFFECTS = [
    ("Off", p.Effect.OFF),
    ("Static", p.Effect.STATIC),
    ("Breathing", p.Effect.BREATHING),
    ("Spectrum", p.Effect.SPECTRUM),
    ("Wave", p.Effect.WAVE),
    ("Reactive", p.Effect.REACTIVE),
    ("Starlight", p.Effect.STARLIGHT),
]
LOGO_STATES = ["Off", "On", "Breathing"]


class ControlWindow(Adw.ApplicationWindow):
    def __init__(self, app: Adw.Application, backend: Backend):
        super().__init__(application=app, title="Razer Control")
        self.set_default_size(560, 800)
        self.backend = backend
        self.state = backend.state
        self._syncing = False

        self.toasts = Adw.ToastOverlay()
        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(Adw.HeaderBar())
        self.toasts.set_child(toolbar)
        self.set_content(self.toasts)

        banner = Adw.Banner(title=backend.detail)
        banner.set_revealed(True)
        toolbar.add_top_bar(banner)

        page = Adw.PreferencesPage()
        toolbar.set_content(page)
        page.set_sensitive(backend.connected)

        page.add(self._build_performance())
        page.add(self._build_fan())
        page.add(self._build_keyboard())
        page.add(self._build_battery())

        self._sync_from_state()

        GLib.timeout_add_seconds(20, self._refresh_battery_row)

    # -- helpers -----------------------------------------------------------
    def _apply(self, action, *args) -> None:
        if self._syncing:
            return
        try:
            action(*args)
        except Exception as exc:  # surface device errors instead of crashing
            self._toast(str(exc))

    def _toast(self, message: str) -> None:
        self.toasts.add_toast(Adw.Toast(title=message, timeout=4))

    @staticmethod
    def _combo(title: str, subtitle: str, options: list[str]) -> Adw.ComboRow:
        row = Adw.ComboRow(title=title, subtitle=subtitle)
        row.set_model(Gtk.StringList.new(options))
        return row

    # -- groups ------------------------------------------------------------
    def _build_performance(self) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup(
            title="Performance",
            description="Power profile sent to the embedded controller",
        )

        self.power_row = self._combo(
            "Profile", "Balanced, Gaming, Creator or Custom", [name for name, _ in POWER_MODES]
        )
        self.power_row.connect("notify::selected", self._on_power_changed)
        group.add(self.power_row)

        self.cpu_row = self._combo("CPU boost", "Only used by the Custom profile", BOOST_LEVELS)
        self.cpu_row.connect("notify::selected", lambda *_: self._apply(
            self._write_boosts
        ))
        group.add(self.cpu_row)

        self.gpu_row = self._combo("GPU boost", "Only used by the Custom profile", BOOST_LEVELS[:-1])
        self.gpu_row.connect("notify::selected", lambda *_: self._apply(
            self._write_boosts
        ))
        group.add(self.gpu_row)
        return group

    def _build_fan(self) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup(
            title="Fan",
            description="Manual control is overridden by Custom power profile",
        )
        self.fan_auto = Adw.SwitchRow(
            title="Automatic", subtitle="Let the embedded controller manage fan speed"
        )
        self.fan_auto.connect("notify::active", self._on_fan_auto_changed)
        group.add(self.fan_auto)

        self.fan_rpm = Adw.SpinRow.new_with_range(3500, 5000, 100)
        self.fan_rpm.set_title("Target speed")
        self.fan_rpm.set_subtitle("RPM")
        self.fan_rpm.connect("notify::value", self._on_fan_rpm_changed)
        group.add(self.fan_rpm)
        return group

    def _build_keyboard(self) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup(title="Keyboard", description="Per-key RGB backlight")

        self.effect_row = self._combo(
            "Effect", "Hardware effect stored in the keyboard", [name for name, _ in EFFECTS]
        )
        self.effect_row.connect("notify::selected", self._on_effect_changed)
        group.add(self.effect_row)

        color_row = Adw.ActionRow(title="Colour", subtitle="Used by the Static effect")
        self.color_button = Gtk.ColorDialogButton(dialog=Gtk.ColorDialog())
        self.color_button.set_valign(Gtk.Align.CENTER)
        self.color_button.connect("notify::rgba", self._on_color_changed)
        color_row.add_suffix(self.color_button)
        color_row.set_activatable_widget(self.color_button)
        group.add(color_row)

        self.brightness = Adw.SpinRow.new_with_range(0, 255, 5)
        self.brightness.set_title("Brightness")
        self.brightness.set_subtitle("0 - 255")
        self.brightness.connect("notify::value", self._on_brightness_changed)
        group.add(self.brightness)

        self.logo_row = self._combo("Logo LED", "Lid logo", LOGO_STATES)
        self.logo_row.connect("notify::selected", self._on_logo_changed)
        group.add(self.logo_row)
        return group

    def _build_battery(self) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup(
            title="Battery",
            description="Battery Health Optimizer keeps the pack below a charge threshold",
        )
        self.bho_switch = Adw.SwitchRow(
            title="Charge limit", subtitle="Only charge up to the threshold below"
        )
        self.bho_switch.connect("notify::active", self._on_bho_toggled)
        group.add(self.bho_switch)

        self.bho_threshold = Adw.SpinRow.new_with_range(p.BHO_MIN, p.BHO_MAX, 5)
        self.bho_threshold.set_title("Threshold")
        self.bho_threshold.set_subtitle("Percent")
        self.bho_threshold.connect("notify::value", self._on_bho_threshold_changed)
        group.add(self.bho_threshold)

        self.battery_row = Adw.ActionRow(title="Battery", subtitle="Reading…")
        self.battery_row.set_icon_name("battery-good-symbolic")
        group.add(self.battery_row)
        return group

    # -- state -> widgets --------------------------------------------------
    def _sync_from_state(self) -> None:
        self._syncing = True
        try:
            modes = [int(mode) for _, mode in POWER_MODES]
            if int(self.state.power_mode) in modes:
                self.power_row.set_selected(modes.index(int(self.state.power_mode)))
            self.cpu_row.set_selected(max(0, min(3, self.state.cpu_boost)))
            self.gpu_row.set_selected(max(0, min(2, self.state.gpu_boost)))
            custom = int(self.state.power_mode) == int(p.PowerMode.CUSTOM)
            self.cpu_row.set_sensitive(custom)
            self.gpu_row.set_sensitive(custom)

            self.fan_auto.set_active(self.state.fan_rpm == 0)
            self.fan_rpm.set_value(self.state.fan_rpm or 3500)
            self.fan_rpm.set_sensitive(self.state.fan_rpm > 0 and not custom)

            self.brightness.set_value(self.state.brightness)
            effect = self.state.extra.get("effect")
            effect_values = [int(value) for _, value in EFFECTS]
            if effect in effect_values:
                self.effect_row.set_selected(effect_values.index(effect))

            color = self.state.extra.get("color", (255, 255, 255))
            rgba = Gdk.RGBA()
            rgba.red, rgba.green, rgba.blue = (channel / 255 for channel in color)
            rgba.alpha = 1.0
            self.color_button.set_rgba(rgba)

            self.logo_row.set_selected(self.state.logo)
            self.bho_switch.set_active(self.state.bho_enabled)
            self.bho_threshold.set_value(self.state.bho_threshold)
            self.bho_threshold.set_sensitive(self.state.bho_enabled)
        finally:
            self._syncing = False
        self._refresh_battery_row()

    def _refresh_battery_row(self) -> bool:
        capacity = sysinfo.battery_capacity()
        status = sysinfo.battery_status() or ""
        if capacity is None:
            self.battery_row.set_subtitle("No battery information available")
        else:
            plugged = "plugged in" if sysinfo.ac_online() else "on battery"
            self.battery_row.set_subtitle(f"{capacity}% - {status} - {plugged}".replace(" - - ", " - "))
        return True

    # -- widget -> device --------------------------------------------------
    def _on_power_changed(self, *_args) -> None:
        if self._syncing:
            return

        def write() -> None:
            index = self.power_row.get_selected()
            mode = int(POWER_MODES[index][1])
            self.backend.set_power_mode(mode)
            self.state.power_mode = mode
            self._sync_from_state()

        self._apply(write)

    def _write_boosts(self) -> None:
        if self._syncing:
            return
        level_cpu = self.cpu_row.get_selected()
        level_gpu = self.gpu_row.get_selected()
        self.backend.set_power_mode(
            int(p.PowerMode.CUSTOM), cpu_boost=level_cpu, gpu_boost=level_gpu
        )
        self.state.cpu_boost = level_cpu
        self.state.gpu_boost = level_gpu

    def _on_fan_auto_changed(self, *_args) -> None:
        if self._syncing:
            return
        if self.fan_auto.get_active():
            self._apply(self.backend.set_fan_rpm, 0)
            self.state.fan_rpm = 0
        else:
            self._apply(self.backend.set_fan_rpm, int(self.fan_rpm.get_value()))
            self.state.fan_rpm = int(self.fan_rpm.get_value())
        self._sync_from_state()

    def _on_fan_rpm_changed(self, *_args) -> None:
        if self._syncing or self.fan_auto.get_active():
            return
        value = int(self.fan_rpm.get_value())
        self._apply(self.backend.set_fan_rpm, value)
        self.state.fan_rpm = value

    def _on_effect_changed(self, *_args) -> None:
        if self._syncing:
            return
        effect = int(EFFECTS[self.effect_row.get_selected()][1])
        self._apply(self.backend.set_effect, effect)
        self.state.extra["effect"] = effect

    def _on_color_changed(self, *_args) -> None:
        if self._syncing:
            return
        rgba = self.color_button.get_rgba()
        red = int(rgba.red * 255)
        green = int(rgba.green * 255)
        blue = int(rgba.blue * 255)
        self._apply(self.backend.set_color, red, green, blue)
        self.state.extra["color"] = (red, green, blue)
        self.state.extra["effect"] = int(p.Effect.STATIC)
        self._sync_from_state()

    def _on_brightness_changed(self, *_args) -> None:
        if self._syncing:
            return
        value = int(self.brightness.get_value())
        self._apply(self.backend.set_brightness, value)
        self.state.brightness = value

    def _on_logo_changed(self, *_args) -> None:
        if self._syncing:
            return
        mode = self.logo_row.get_selected()
        self._apply(self.backend.set_logo, mode)
        self.state.logo = mode

    def _on_bho_toggled(self, *_args) -> None:
        if self._syncing:
            return
        enabled = self.bho_switch.get_active()
        threshold = int(self.bho_threshold.get_value())

        def write() -> None:
            self.backend.set_bho(enabled, threshold)
            self.state.bho_enabled = enabled
            self._sync_from_state()

        self._apply(write)

    def _on_bho_threshold_changed(self, *_args) -> None:
        if self._syncing or not self.bho_switch.get_active():
            return
        threshold = int(self.bho_threshold.get_value())
        self._apply(self.backend.set_bho, True, threshold)
        self.state.bho_threshold = threshold
