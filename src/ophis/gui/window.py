"""Main window: a Synapse-shaped control centre.

Left navigation, live device state on the right. Everything the window shows
comes from the device; nothing is remembered locally except the user's profile
preferences.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402

from .. import desktop, profile, protocol as p, sysinfo, thermal  # noqa: E402
from .widgets import CurveEditor, disable_scale_scroll  # noqa: E402

PROFILE_CARDS = [
    ("Balanced", p.PowerMode.BALANCED, "power-profile-balanced-symbolic"),
    ("Gaming", p.PowerMode.GAMING, "power-profile-performance-symbolic"),
    ("Creator", p.PowerMode.CREATOR, "applications-graphics-symbolic"),
    ("Custom", p.PowerMode.CUSTOM, "applications-system-symbolic"),
]
BOOST_LEVELS = ["Low", "Normal", "High", "Boost"]
FIRMWARE_EFFECTS = [
    ("Off", p.Effect.OFF),
    ("Static", p.Effect.STATIC),
    ("Breathing", p.Effect.BREATHING),
    ("Spectrum", p.Effect.SPECTRUM),
    ("Wave", p.Effect.WAVE),
    ("Reactive", p.Effect.REACTIVE),
    ("Starlight", p.Effect.STARLIGHT),
]
HOST_ANIMATIONS = [
    ("None", None),
    ("Rainbow wave", "wave"),
    ("Wheel", "wheel"),
    ("Sparkle", "sparkle"),
    ("Rain", "rain"),
    ("Lightning", "lightning"),
    ("Matrix", "matrix"),
    ("Flame", "flame"),
]
PAGES = [
    ("performance", "Performance", "power-profile-performance-symbolic"),
    ("cooling", "Cooling", "weather-windy-symbolic"),
    ("lighting", "Lighting", "keyboard-brightness-symbolic"),
    ("battery", "Battery", "battery-good-symbolic"),
    ("settings", "Settings", "emblem-system-symbolic"),
]


class ControlWindow(Adw.ApplicationWindow):
    def __init__(self, app, backend, tray_enabled: bool = False) -> None:
        super().__init__(application=app, title="Ophis")
        self.set_default_size(1080, 760)
        self.app = app
        self.backend = backend
        self.state = backend.state
        self.tray_enabled = tray_enabled
        self.profile = profile.load()
        self._syncing = False

        self.engine = None
        self.lighting = None

        self.toasts = Adw.ToastOverlay()
        self.set_content(self.toasts)

        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        device = getattr(backend, "device", None)
        header.set_title_widget(
            Adw.WindowTitle(
                title="Ophis",
                subtitle=device.model if device else "Preview device",
            )
        )
        toolbar.add_top_bar(header)
        self.toasts.set_child(toolbar)

        root = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        root.add_css_class("ophis-root")
        toolbar.set_content(root)

        root.append(self._build_sidebar())

        self.stack = Gtk.Stack()
        self.stack.set_hexpand(True)
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        root.append(self.stack)

        self.stack.add_named(self._build_performance(), "performance")
        self.stack.add_named(self._build_cooling(), "cooling")
        self.stack.add_named(self._build_lighting(), "lighting")
        self.stack.add_named(self._build_battery(), "battery")
        self.stack.add_named(self._build_settings(), "settings")

        self._install_actions(header)
        self.connect("close-request", self._on_close)
        self._sync_from_state()
        self._refresh_battery()
        self._refresh_temperatures()

        GLib.timeout_add_seconds(2, self._refresh_temperatures)
        GLib.timeout_add_seconds(10, self._refresh_battery)
        GLib.timeout_add_seconds(3, self._curve_tick)

    # -- shell --------------------------------------------------------------
    def _build_sidebar(self) -> Gtk.Widget:
        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        sidebar.add_css_class("sidebar")
        sidebar.set_size_request(238, -1)

        brand = Gtk.Label(label="OPHIS", xalign=0)
        brand.add_css_class("brand")
        brand.set_margin_top(22)
        brand.set_margin_start(20)
        sidebar.append(brand)

        device = getattr(self.backend, "device", None)
        model = device.model if device else "Preview device"
        subtitle = Gtk.Label(label=model, xalign=0)
        subtitle.add_css_class("muted")
        subtitle.set_margin_start(20)
        subtitle.set_margin_bottom(14)
        sidebar.append(subtitle)

        self.nav = Gtk.ListBox()
        self.nav.add_css_class("nav")
        self.nav.set_selection_mode(Gtk.SelectionMode.SINGLE)
        for name, title, icon in PAGES:
            row = Gtk.ListBoxRow()
            row.set_name(name)
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            box.set_margin_top(9)
            box.set_margin_bottom(9)
            box.set_margin_start(16)
            box.set_margin_end(16)
            image = Gtk.Image.new_from_icon_name(icon)
            label = Gtk.Label(label=title, xalign=0)
            label.set_hexpand(True)
            box.append(image)
            box.append(label)
            row.set_child(box)
            self.nav.append(row)
        self.nav.connect("row-selected", self._on_nav_selected)
        sidebar.append(self.nav)

        spacer = Gtk.Box()
        spacer.set_vexpand(True)
        sidebar.append(spacer)

        self.sidebar_battery = Gtk.Label(label="", xalign=0)
        self.sidebar_battery.add_css_class("muted")
        self.sidebar_battery.set_margin_start(20)
        self.sidebar_battery.set_margin_bottom(20)
        sidebar.append(self.sidebar_battery)

        GLib.idle_add(self._select_first_row)
        return sidebar

    def _select_first_row(self) -> bool:
        row = self.nav.get_row_at_index(0)
        if row is not None:
            self.nav.select_row(row)
        return False

    def _on_nav_selected(self, _listbox, row) -> None:
        if row is not None:
            self.stack.set_visible_child_name(row.get_name())

    def _on_close(self, *_args) -> bool:
        if self.tray_enabled:
            self.set_visible(False)
            return True
        self.app.quit_cleanly()
        return True

    def _install_actions(self, header: Adw.HeaderBar) -> None:
        group = Gio.SimpleActionGroup()
        entries = [("defaults", self._restore_defaults), ("quit", self.app.quit_cleanly)]
        if self.tray_enabled:
            entries.insert(0, ("minimize", self.hide))
        for name, callback in entries:
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", lambda _action, _param, cb=callback: cb())
            group.add_action(action)
        self.insert_action_group("win", group)

        menu = Gio.Menu()
        if self.tray_enabled:
            menu.append("Minimize to tray", "win.minimize")
        menu.append("Restore default settings", "win.defaults")
        menu.append("Quit", "win.quit")

        button = Gtk.MenuButton(icon_name="open-menu-symbolic")
        button.set_menu_model(menu)
        button.set_tooltip_text("Menu")
        header.pack_end(button)

    def _restore_defaults(self) -> None:
        self.app._restore_defaults()  # noqa: SLF001 - shared with the tray

    def _apply(self, action, *args) -> None:
        if self._syncing:
            return
        try:
            action(*args)
        except Exception as exc:  # device errors must not kill the window
            self.toast(str(exc))

    def toast(self, message: str) -> None:
        self.toasts.add_toast(Adw.Toast(title=message, timeout=4))

    @staticmethod
    def _scale(low: float, high: float, step: float, value: float) -> Gtk.Scale:
        scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, low, high, step)
        scale.set_value(value)
        scale.set_hexpand(True)
        scale.set_size_request(240, -1)
        scale.set_draw_value(True)
        disable_scale_scroll(scale)
        return scale

    @staticmethod
    def _row(title: str, subtitle: str = "") -> Adw.ActionRow:
        row = Adw.ActionRow(title=title)
        if subtitle:
            row.set_subtitle(subtitle)
        return row

    # -- performance --------------------------------------------------------
    def _build_performance(self) -> Gtk.Widget:
        page = Adw.PreferencesPage()
        group = Adw.PreferencesGroup(
            title="Performance profile",
            description="Written straight to the embedded controller",
        )
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        box.set_homogeneous(True)
        box.set_margin_top(4)
        box.set_margin_bottom(4)

        self.profile_buttons: dict[int, Gtk.ToggleButton] = {}
        first: Gtk.ToggleButton | None = None
        for title, mode, icon in PROFILE_CARDS:
            button = Gtk.ToggleButton()
            button.add_css_class("profile-card")
            inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            inner.set_margin_top(14)
            inner.set_margin_bottom(14)
            image = Gtk.Image.new_from_icon_name(icon)
            image.set_pixel_size(26)
            label = Gtk.Label(label=title)
            inner.append(image)
            inner.append(label)
            button.set_child(inner)
            if first is None:
                first = button
            else:
                button.set_group(first)
            button.connect("toggled", self._on_profile_toggled, int(mode))
            self.profile_buttons[int(mode)] = button
            box.append(button)

        wrapper = Adw.ActionRow()
        wrapper.set_child(box)
        wrapper.set_activatable(False)
        group.add(wrapper)
        page.add(group)

        boost_group = Adw.PreferencesGroup(
            title="Boost",
            description="Only used by the Custom profile",
        )
        self.cpu_boost_row = Adw.ComboRow(title="CPU boost")
        self.cpu_boost_row.set_model(Gtk.StringList.new(BOOST_LEVELS))
        self.cpu_boost_row.connect("notify::selected", self._on_boost_changed)
        boost_group.add(self.cpu_boost_row)

        self.gpu_boost_row = Adw.ComboRow(title="GPU boost")
        self.gpu_boost_row.set_model(Gtk.StringList.new(BOOST_LEVELS[:-1]))
        self.gpu_boost_row.connect("notify::selected", self._on_boost_changed)
        boost_group.add(self.gpu_boost_row)
        page.add(boost_group)
        return page

    def _on_profile_toggled(self, button: Gtk.ToggleButton, mode: int) -> None:
        if self._syncing or not button.get_active():
            return

        def write() -> None:
            self.backend.set_power_mode(mode)
            self.state.power_mode = mode
            self.profile["power"]["mode"] = profile.POWER_IDS.get(mode, "balanced")
            self._save_profile()
            self._sync_from_state()

        self._apply(write)

    def _on_boost_changed(self, *_args) -> None:
        if self._syncing:
            return
        cpu = self.cpu_boost_row.get_selected()
        gpu = self.gpu_boost_row.get_selected()

        def write() -> None:
            self.backend.set_power_mode(p.PowerMode.CUSTOM, cpu, gpu)
            self.state.power_mode = p.PowerMode.CUSTOM
            self.state.cpu_boost = cpu
            self.state.gpu_boost = gpu
            self.profile["power"].update(
                {"mode": "custom", "cpu_boost": cpu, "gpu_boost": gpu}
            )
            self._save_profile()
            self._sync_from_state()

        self._apply(write)

    # -- cooling ------------------------------------------------------------
    def _build_cooling(self) -> Gtk.Widget:
        page = Adw.PreferencesPage()

        temps = Adw.PreferencesGroup(
            title="Temperatures",
            description="Read from the kernel sensors, not the controller",
        )
        self.temp_rows: dict[str, tuple[Adw.ActionRow, Gtk.LevelBar]] = {}
        for key, title in (("cpu", "CPU"), ("gpu", "GPU"), ("storage", "NVMe")):
            row = Adw.ActionRow(title=title)
            row.set_subtitle("reading...")
            bar = Gtk.LevelBar()
            bar.set_min_value(0)
            bar.set_max_value(100)
            bar.set_size_request(180, -1)
            bar.set_valign(Gtk.Align.CENTER)
            row.add_suffix(bar)
            temps.add(row)
            self.temp_rows[key] = (row, bar)
        page.add(temps)

        fan = Adw.PreferencesGroup(
            title="Fan",
            description="Fixed speeds switch the laptop to the Custom profile and take a few seconds to settle",
        )
        self.fan_auto = Adw.SwitchRow(
            title="Automatic", subtitle="Let the controller manage the fans"
        )
        self.fan_auto.connect("notify::active", self._on_fan_auto)
        fan.add(self.fan_auto)

        speed_row = self._row("Target speed", "3500 - 5000 RPM")
        self.fan_scale = self._scale(3500, 5000, 100, 4000)
        self.fan_scale.connect("value-changed", self._on_fan_slider)
        speed_row.add_suffix(self.fan_scale)
        fan.add(speed_row)

        self.curve_switch = Adw.SwitchRow(
            title="Fan curve",
            subtitle="Follow the hottest sensor instead of a fixed speed",
        )
        self.curve_switch.connect("notify::active", self._on_curve_switch)
        fan.add(self.curve_switch)

        editor_row = self._row("Curve", "Drag the points: temperature against RPM")
        editor_row.set_activatable(False)
        self.curve_editor = CurveEditor(self.profile["curve"]["points"], self._on_curve_edited)
        holder = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        holder.set_margin_top(8)
        holder.set_margin_bottom(8)
        holder.append(self.curve_editor)
        hint = Gtk.Label(
            label="The curve is applied while the app is running; the controller keeps its last value afterwards.",
            xalign=0,
        )
        hint.add_css_class("muted")
        holder.append(hint)
        editor_row.set_child(holder)
        fan.add(editor_row)

        self.fan_status = self._row("Status", "automatic")
        fan.add(self.fan_status)
        page.add(fan)
        return page

    def _on_fan_auto(self, *_args) -> None:
        if self._syncing:
            return
        automatic = self.fan_auto.get_active()

        def write() -> None:
            if automatic:
                self.backend.set_fan_rpm(0)
                self.state.fan_rpm = 0
            else:
                rpm = int(self.fan_scale.get_value())
                self.backend.set_fan_rpm(rpm)
                self.state.fan_rpm = rpm
            self._remember_fan()
            self._sync_from_state()

        self._apply(write)

    def _on_fan_slider(self, scale: Gtk.Scale) -> None:
        if self._syncing or self.fan_auto.get_active():
            return
        rpm = int(scale.get_value()) // 100 * 100

        def write() -> None:
            self.backend.set_fan_rpm(rpm)
            self.state.fan_rpm = rpm
            self._remember_fan()

        self._apply(write)

    def _remember_fan(self) -> None:
        if self.state.fan_rpm:
            self.profile["fan"] = {"mode": "manual", "rpm": int(self.state.fan_rpm)}
        else:
            self.profile["fan"] = {"mode": "auto"}
        self._save_profile()

    def _on_curve_switch(self, *_args) -> None:
        if self._syncing:
            return
        enabled = self.curve_switch.get_active()
        self.profile["curve"]["enabled"] = enabled
        self._save_profile()
        self.curve_editor.set_sensitive(enabled)
        if enabled:
            self.toast("Fan curve enabled")
        else:
            self.toast("Fan curve disabled")

    def _on_curve_edited(self, points) -> None:
        self.profile["curve"]["points"] = points
        self._save_profile()

    def _curve_tick(self) -> bool:
        if not getattr(self.backend, "connected", False):
            return True
        if not self.curve_switch.get_active():
            return True
        hottest = thermal.read().hottest
        if hottest is None:
            return True
        points = self.curve_editor.get_points()
        rpm = self._interpolate(points, hottest)
        if rpm is None:
            return True
        if abs(rpm - int(self.state.fan_rpm)) >= 150:
            try:
                self.backend.set_fan_rpm(rpm)
                self.state.fan_rpm = rpm
                self.fan_status.set_subtitle(
                    f"curve: {hottest:.0f} C -> {rpm} RPM"
                )
            except Exception as exc:
                self.fan_status.set_subtitle(f"curve error: {exc}")
        return True

    @staticmethod
    def _interpolate(points: list[list[int]], temperature: float) -> int | None:
        if not points:
            return None
        if temperature <= points[0][0]:
            return int(points[0][1])
        for index in range(1, len(points)):
            left_temp, left_rpm = points[index - 1]
            right_temp, right_rpm = points[index]
            if temperature <= right_temp:
                span = max(1, right_temp - left_temp)
                ratio = (temperature - left_temp) / span
                return int(left_rpm + (right_rpm - left_rpm) * ratio)
        return int(points[-1][1])

    # -- lighting -----------------------------------------------------------
    def _build_lighting(self) -> Gtk.Widget:
        from .lighting import LightingPage

        self.lighting = LightingPage(self)
        self.engine = self.lighting.engine
        return self.lighting

    # -- battery ------------------------------------------------------------
    def _build_battery(self) -> Gtk.Widget:
        page = Adw.PreferencesPage()
        group = Adw.PreferencesGroup(
            title="Battery care",
            description="The charge limit lives in the controller and survives reboots",
        )
        self.bho_switch = Adw.SwitchRow(
            title="Charge limit", subtitle="Stop charging at the threshold below"
        )
        self.bho_switch.connect("notify::active", self._on_bho_toggled)
        group.add(self.bho_switch)

        threshold_row = self._row("Threshold", "50 - 80%")
        self.bho_scale = self._scale(p.BHO_MIN, p.BHO_MAX, 5, 80)
        self.bho_scale.connect("value-changed", self._on_bho_threshold)
        threshold_row.add_suffix(self.bho_scale)
        group.add(threshold_row)

        self.battery_row = self._row("Battery", "reading...")
        self.battery_row.set_icon_name("battery-good-symbolic")
        group.add(self.battery_row)
        page.add(group)
        return page

    def _on_bho_toggled(self, *_args) -> None:
        if self._syncing:
            return
        enabled = self.bho_switch.get_active()
        threshold = int(self.bho_scale.get_value())

        def write() -> None:
            self.backend.set_bho(enabled, threshold)
            self.state.bho_enabled = enabled
            self.state.bho_threshold = threshold
            self.profile["battery"] = {
                "limit_enabled": enabled,
                "threshold": threshold,
            }
            self._save_profile()
            self._sync_from_state()

        self._apply(write)

    def _on_bho_threshold(self, scale: Gtk.Scale) -> None:
        if self._syncing or not self.bho_switch.get_active():
            return
        threshold = int(scale.get_value())
        self._apply(self.backend.set_bho, True, threshold)
        self.state.bho_threshold = threshold
        self.profile["battery"]["threshold"] = threshold
        self._save_profile()

    def _refresh_battery(self) -> bool:
        capacity = sysinfo.battery_capacity()
        status = sysinfo.battery_status() or ""
        plugged = "plugged in" if sysinfo.ac_online() else "on battery"
        if capacity is None:
            text = "no battery information"
        else:
            text = f"{capacity}% - {status} - {plugged}".replace(" - - ", " - ")
        self.battery_row.set_subtitle(text)
        self.sidebar_battery.set_text(text)
        return True

    def _refresh_temperatures(self) -> bool:
        reading = thermal.read()
        for key, (row, bar) in self.temp_rows.items():
            value = getattr(reading, key)
            if value is None:
                row.set_subtitle("not available")
                bar.set_value(0)
            else:
                row.set_subtitle(f"{value:.1f} C")
                bar.set_value(value)
        return True

    # -- settings -----------------------------------------------------------
    def _build_settings(self) -> Gtk.Widget:
        page = Adw.PreferencesPage()

        behaviour = Adw.PreferencesGroup(title="Behaviour")
        self.apply_on_start = Adw.SwitchRow(
            title="Apply the saved profile at start",
            subtitle=str(profile.config_path()),
        )
        self.apply_on_start.set_active(
            bool(self.profile["settings"].get("apply_on_start", True))
        )
        self.apply_on_start.connect("notify::active", self._on_settings_toggle)
        behaviour.add(self.apply_on_start)

        self.restore_on_quit = Adw.SwitchRow(
            title="Restore defaults on quit",
            subtitle="Balanced profile, automatic fans, plain white keyboard",
        )
        self.restore_on_quit.set_active(
            bool(self.profile["settings"].get("restore_on_quit", True))
        )
        self.restore_on_quit.connect("notify::active", self._on_settings_toggle)
        behaviour.add(self.restore_on_quit)

        self.autostart_row = Adw.SwitchRow(
            title="Start the tray at login",
            subtitle="Writes ~/.config/autostart/ophis.desktop",
        )
        self.autostart_row.set_active(desktop.autostart_enabled())
        self.autostart_row.connect("notify::active", self._on_autostart)
        behaviour.add(self.autostart_row)
        page.add(behaviour)

        saved = Adw.PreferencesGroup(title="Profile")
        save_row = self._row("Save the current settings", "")
        save_button = Gtk.Button(label="Save")
        save_button.set_valign(Gtk.Align.CENTER)
        save_button.connect("clicked", self._on_save_profile)
        save_row.add_suffix(save_button)
        saved.add(save_row)

        apply_row = self._row("Apply the saved profile", "")
        apply_button = Gtk.Button(label="Apply")
        apply_button.set_valign(Gtk.Align.CENTER)
        apply_button.connect("clicked", self._on_apply_profile)
        apply_row.add_suffix(apply_button)
        saved.add(apply_row)
        page.add(saved)

        about = Adw.PreferencesGroup(title="About")
        from .. import __version__, build_id

        revision = build_id()
        label = f"Ophis {__version__}" + (f" ({revision})" if revision else "")
        about.add(
            self._row(
                label,
                "Control centre for the Razer Blade 14 (2022), USB 1532:028C. Not affiliated with Razer.",
            )
        )
        page.add(about)
        return page

    def _on_settings_toggle(self, *_args) -> None:
        self.profile["settings"]["apply_on_start"] = self.apply_on_start.get_active()
        self.profile["settings"]["restore_on_quit"] = self.restore_on_quit.get_active()
        self._save_profile()

    def _on_autostart(self, row: Gtk.SwitchRow, _param) -> None:
        try:
            desktop.set_autostart(row.get_active())
        except OSError as exc:
            self.toast(str(exc))

    def _on_save_profile(self, *_args) -> None:
        self.profile = profile.capture(self.backend)
        self.profile["settings"] = {
            "apply_on_start": self.apply_on_start.get_active(),
            "restore_on_quit": self.restore_on_quit.get_active(),
        }
        self._save_profile()
        self.toast(f"Saved {profile.config_path()}")

    def _on_apply_profile(self, *_args) -> None:
        warnings = profile.apply(self.backend, self.profile)
        for warning in warnings:
            self.toast(warning)
        self.backend.refresh()
        self._sync_from_state()

    def save_profile(self) -> None:
        self._save_profile()

    def _save_profile(self) -> None:
        try:
            profile.save(self.profile)
        except OSError as exc:
            self.toast(f"could not save the profile: {exc}")

    # -- state -> widgets ---------------------------------------------------
    def _sync_from_state(self) -> None:
        self._syncing = True
        try:
            for mode, button in self.profile_buttons.items():
                if int(self.state.power_mode) == mode:
                    button.set_active(True)
                    break

            custom = int(self.state.power_mode) == int(p.PowerMode.CUSTOM)
            self.cpu_boost_row.set_selected(max(0, min(3, int(self.state.cpu_boost))))
            self.gpu_boost_row.set_selected(max(0, min(2, int(self.state.gpu_boost))))
            self.cpu_boost_row.set_sensitive(custom)
            self.gpu_boost_row.set_sensitive(custom)

            auto = int(self.state.fan_rpm) == 0
            self.fan_auto.set_active(auto)
            self.fan_scale.set_sensitive(not auto)
            if not auto:
                self.fan_scale.set_value(int(self.state.fan_rpm))
            self.fan_status.set_subtitle(
                "automatic" if auto else f"fixed at {int(self.state.fan_rpm)} RPM"
            )

            self.bho_switch.set_active(bool(self.state.bho_enabled))
            self.bho_scale.set_value(int(self.state.bho_threshold))
            self.bho_scale.set_sensitive(bool(self.state.bho_enabled))
        finally:
            self._syncing = False
        if self.lighting is not None:
            self.lighting.sync()
