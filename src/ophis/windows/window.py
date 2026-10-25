"""Main window for the Windows build, shaped like the GTK application."""

from __future__ import annotations

import os

from PySide6.QtCore import QMetaObject, QSize, Qt, QThread, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QSlider,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .. import __version__, build_id, desktop, profile, protocol as p
from ..thermal import Temperatures
from .icons import app_icon, icon
from .lighting import LightingPage
from .sensors import SensorWorker
from .widgets import (
    Card,
    CurveEditor,
    MiniBar,
    PageScroll,
    SettingRow,
    SettingsCard,
    Toast,
    ToggleSwitch,
    label,
    section_label,
)

PROFILE_CARDS = [
    ("Balanced", p.PowerMode.BALANCED, "Quiet and efficient"),
    ("Gaming", p.PowerMode.GAMING, "Maximum performance"),
    ("Creator", p.PowerMode.CREATOR, "Sustained workloads"),
    ("Custom", p.PowerMode.CUSTOM, "Your boost settings"),
]
BOOST_LEVELS = ["Low", "Normal", "High", "Boost"]

PAGES = [
    ("performance", "Performance", "performance"),
    ("cooling", "Cooling", "cooling"),
    ("lighting", "Lighting", "lighting"),
    ("battery", "Battery", "battery"),
    ("settings", "Settings", "settings"),
]


class NavButton(QPushButton):
    def __init__(self, name: str, text: str, glyph: str) -> None:
        super().__init__(text)
        self.page_name = name
        self._glyph = glyph
        self.setObjectName("navButton")
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setIcon(icon(glyph, "#b8b8b8", 18))
        self.setIconSize(QSize(18, 18))
        self.setFixedHeight(42)
        self.toggled.connect(self._paint_icon)

    def _paint_icon(self, checked: bool) -> None:
        self.setIcon(icon(self._glyph, "#44d62c" if checked else "#b8b8b8", 18))


class MainWindow(QMainWindow):
    def __init__(self, app, backend, tray_enabled: bool = False) -> None:
        super().__init__()
        self.app = app
        self.backend = backend
        self.state = backend.state
        self.tray_enabled = tray_enabled
        self.profile = profile.load()
        self._syncing = False
        self._temperatures = Temperatures()
        self._battery = {"capacity": None, "status": "reading...", "plugged": None}
        self._synapse: list[str] = []
        self.engine = None
        self.lighting: LightingPage | None = None
        self._sensor_thread: QThread | None = None
        self._sensors: SensorWorker | None = None
        self._dark_title = False

        self.setWindowTitle("Ophis")
        self.setWindowIcon(app_icon())
        self.resize(1120, 790)
        self.setMinimumSize(980, 680)

        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        shell = QHBoxLayout(root)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)

        shell.addWidget(self._build_sidebar())

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        self.banner_wrap = self._build_banner()
        content_layout.addWidget(self.banner_wrap)
        self.stack = QStackedWidget()
        content_layout.addWidget(self.stack, 1)
        shell.addWidget(content, 1)

        self.pages: dict[str, int] = {}
        for name, page in (
            ("performance", self._build_performance()),
            ("cooling", self._build_cooling()),
            ("lighting", self._build_lighting()),
            ("battery", self._build_battery()),
            ("settings", self._build_settings()),
        ):
            self.pages[name] = self.stack.addWidget(page)

        self.toast_widget = Toast(root)
        self._select_page("performance", initial=True)
        self._sync_from_state()
        self._refresh_device_status()
        self._refresh_battery()
        self._refresh_temperatures(self._temperatures)

        self.curve_timer = QTimer(self)
        self.curve_timer.setInterval(3000)
        self.curve_timer.timeout.connect(self._curve_tick)
        self.curve_timer.start()

        self._start_sensors()

    # -- shell --------------------------------------------------------------
    def _build_sidebar(self) -> QWidget:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(238)
        box = QVBoxLayout(sidebar)
        box.setContentsMargins(12, 22, 12, 18)
        box.setSpacing(4)

        brand = QLabel("OPHIS")
        brand.setObjectName("brand")
        font = QFont(brand.font())
        font.setPointSize(17)
        font.setWeight(QFont.Weight.Black)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 6.0)
        brand.setFont(font)
        box.addWidget(brand)

        device = getattr(self.backend, "device", None)
        if device is not None:
            model = device.model
        elif str(getattr(self.backend, "detail", "")).lower().startswith("preview"):
            model = "Preview device"
        else:
            model = "Razer Blade 14 (2022)"
        subtitle = QLabel(model)
        subtitle.setObjectName("model")
        subtitle.setWordWrap(True)
        box.addWidget(subtitle)
        box.addSpacing(12)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_buttons: dict[str, NavButton] = {}
        for name, text, glyph in PAGES:
            button = NavButton(name, text, glyph)
            self.nav_group.addButton(button)
            button.clicked.connect(lambda _checked=False, n=name: self._select_page(n))
            box.addWidget(button)
            self.nav_buttons[name] = button

        box.addStretch(1)
        self.sidebar_status = label("", muted=True, wrap=True)
        self.sidebar_status.setContentsMargins(8, 0, 8, 4)
        box.addWidget(self.sidebar_status)
        self.sidebar_battery = label("", muted=True, wrap=True)
        self.sidebar_battery.setContentsMargins(8, 0, 8, 0)
        box.addWidget(self.sidebar_battery)
        return sidebar

    def _build_banner(self) -> QWidget:
        wrap = QWidget()
        outer = QVBoxLayout(wrap)
        outer.setContentsMargins(30, 16, 30, 0)
        self.banner = QFrame()
        self.banner.setObjectName("banner")
        row = QHBoxLayout(self.banner)
        row.setContentsMargins(14, 10, 14, 10)
        row.setSpacing(12)
        self.banner_text = label("", wrap=True)
        row.addWidget(self.banner_text, 1)
        retry = QPushButton("Retry")
        retry.clicked.connect(self._retry_device)
        row.addWidget(retry)
        outer.addWidget(self.banner)
        wrap.hide()
        return wrap

    def _select_page(self, name: str, initial: bool = False) -> None:
        index = self.pages.get(name)
        if index is None:
            return
        self.stack.setCurrentIndex(index)
        button = self.nav_buttons.get(name)
        if button is not None and not button.isChecked():
            self._syncing = True
            button.setChecked(True)
            self._syncing = False

    def toast(self, message: str) -> None:
        if hasattr(self, "toast_widget"):
            self.toast_widget.show_message(message)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._dark_title:
            return
        self._dark_title = True
        if os.name != "nt":
            return
        try:
            import ctypes

            hwnd = int(self.winId())
            for attribute in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE
                value = ctypes.c_int(1)
                result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value)
                )
                if result == 0:
                    break
        except Exception:
            pass

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "toast_widget"):
            self.toast_widget.reposition()

    # -- performance --------------------------------------------------------
    def _build_performance(self) -> QWidget:
        page = PageScroll(
            "Performance",
            "Power limits written straight to the embedded controller",
        )
        profile_card = Card()
        profile_card.add(section_label("Performance profile"))
        row = QHBoxLayout()
        row.setSpacing(10)
        self.profile_group = QButtonGroup(self)
        self.profile_group.setExclusive(True)
        self.profile_buttons: dict[int, QPushButton] = {}
        for title, mode, hint in PROFILE_CARDS:
            button = QPushButton(title)
            button.setObjectName("profileCard")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setMinimumHeight(86)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            button.setToolTip(hint)
            self.profile_group.addButton(button)
            button.toggled.connect(
                lambda checked, m=int(mode): self._on_profile(checked, m)
            )
            row.addWidget(button)
            self.profile_buttons[int(mode)] = button
        profile_card.body.addLayout(row)
        page.body.addWidget(profile_card)

        boost_card = SettingsCard()
        boost_card.body.addWidget(section_label("Boost"))
        cpu_row = SettingRow("CPU boost", "Only used by the Custom profile")
        self.cpu_boost = QComboBox()
        self.cpu_boost.addItems(BOOST_LEVELS)
        self.cpu_boost.currentIndexChanged.connect(self._on_boost)
        cpu_row.add_control(self.cpu_boost)
        boost_card.add_row(cpu_row)

        gpu_row = SettingRow("GPU boost", "Only used by the Custom profile")
        self.gpu_boost = QComboBox()
        self.gpu_boost.addItems(BOOST_LEVELS[:-1])
        self.gpu_boost.currentIndexChanged.connect(self._on_boost)
        gpu_row.add_control(self.gpu_boost)
        boost_card.add_row(gpu_row)
        page.body.addWidget(boost_card)

        note = label(
            "Boost settings apply when the Custom profile is selected. "
            "Manual fan speeds also move the laptop to Custom.",
            muted=True,
            wrap=True,
        )
        page.body.addWidget(note)
        page.finish()
        return page

    def _on_profile(self, checked: bool, mode: int) -> None:
        if self._syncing or not checked:
            return
        try:
            self.backend.set_power_mode(mode)
        except Exception as exc:
            self.toast(str(exc))
            self._sync_from_state()
            return
        self.state.power_mode = mode
        self.profile["power"]["mode"] = profile.POWER_IDS.get(mode, "balanced")
        self._save_profile()
        self._sync_from_state()

    def _on_boost(self, _index: int) -> None:
        if self._syncing:
            return
        cpu = self.cpu_boost.currentIndex()
        gpu = self.gpu_boost.currentIndex()
        try:
            self.backend.set_power_mode(p.PowerMode.CUSTOM, cpu, gpu)
        except Exception as exc:
            self.toast(str(exc))
            return
        self.state.power_mode = p.PowerMode.CUSTOM
        self.state.cpu_boost = cpu
        self.state.gpu_boost = gpu
        self.profile["power"].update(
            {"mode": "custom", "cpu_boost": cpu, "gpu_boost": gpu}
        )
        self._save_profile()
        self._sync_from_state()

    # -- cooling ------------------------------------------------------------
    def _build_cooling(self) -> QWidget:
        page = PageScroll(
            "Cooling",
            "Temperatures are read without a driver; the fan is written to the controller",
        )
        temps = SettingsCard()
        temps.body.addWidget(section_label("Temperatures"))
        self.temp_rows: dict[str, tuple[QLabel, MiniBar]] = {}
        for key, title in (("cpu", "CPU"), ("gpu", "GPU"), ("storage", "NVMe")):
            row = SettingRow(title)
            value = QLabel("--")
            value.setFixedWidth(64)
            value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            bar = MiniBar()
            row.add_control(bar)
            row.add_control(value)
            temps.add_row(row)
            self.temp_rows[key] = (value, bar)
        page.body.addWidget(temps)

        fan = SettingsCard()
        fan.body.addWidget(section_label("Fan"))
        auto_row = SettingRow("Automatic", "Let the controller manage the fans")
        self.fan_auto = ToggleSwitch()
        self.fan_auto.toggled.connect(self._on_fan_auto)
        auto_row.add_control(self.fan_auto)
        fan.add_row(auto_row)

        speed_row = SettingRow("Target speed", "3500 - 5000 RPM")
        self.fan_scale = QSlider(Qt.Orientation.Horizontal)
        self.fan_scale.setRange(3500, 5000)
        self.fan_scale.setSingleStep(100)
        self.fan_scale.setPageStep(500)
        self.fan_scale.setFixedWidth(260)
        self.fan_scale.valueChanged.connect(self._on_fan_slider)
        self.fan_value = QLabel("4000")
        self.fan_value.setFixedWidth(52)
        self.fan_value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        speed_row.add_control(self.fan_scale)
        speed_row.add_control(self.fan_value)
        fan.add_row(speed_row)

        curve_row = SettingRow(
            "Fan curve", "Follow the hottest sensor instead of a fixed speed"
        )
        self.curve_switch = ToggleSwitch()
        self.curve_switch.toggled.connect(self._on_curve_switch)
        curve_row.add_control(self.curve_switch)
        fan.add_row(curve_row)

        self.fan_status_row = SettingRow("Status", "automatic")
        fan.add_row(self.fan_status_row)
        page.body.addWidget(fan)

        curve_card = Card()
        curve_card.add(section_label("Curve"))
        curve_card.add(
            label("Drag the points: temperature against RPM.", muted=True, wrap=True)
        )
        self.curve_editor = CurveEditor(self.profile["curve"]["points"])
        self.curve_editor.pointsChanged.connect(self._on_curve_edited)
        curve_card.add(self.curve_editor)
        curve_card.add(
            label(
                "The curve runs while Ophis is open. The controller keeps the last "
                "value after the app closes.",
                muted=True,
                wrap=True,
            )
        )
        page.body.addWidget(curve_card)
        page.finish()
        return page

    def _on_fan_auto(self, checked: bool) -> None:
        if self._syncing:
            return
        try:
            if checked:
                self.backend.set_fan_rpm(0)
                self.state.fan_rpm = 0
            else:
                rpm = int(self.fan_scale.value()) // 100 * 100
                self.backend.set_fan_rpm(rpm)
                self.state.fan_rpm = rpm
        except Exception as exc:
            self.toast(str(exc))
            self._sync_from_state()
            return
        self._remember_fan()
        self._sync_from_state()

    def _on_fan_slider(self, value: int) -> None:
        rpm = int(value) // 100 * 100
        self.fan_value.setText(str(rpm))
        if self._syncing or self.fan_auto.isChecked():
            return
        try:
            self.backend.set_fan_rpm(rpm)
        except Exception as exc:
            self.toast(str(exc))
            return
        self.state.fan_rpm = rpm
        self._remember_fan()
        self.fan_status_row.set_subtitle(f"fixed at {rpm} RPM")

    def _remember_fan(self) -> None:
        if self.state.fan_rpm:
            self.profile["fan"] = {"mode": "manual", "rpm": int(self.state.fan_rpm)}
        else:
            self.profile["fan"] = {"mode": "auto"}
        self._save_profile()

    def _on_curve_switch(self, checked: bool) -> None:
        if self._syncing:
            return
        self.profile["curve"]["enabled"] = checked
        self.curve_editor.setEnabled(checked)
        self._save_profile()
        self.toast("Fan curve enabled" if checked else "Fan curve disabled")

    def _on_curve_edited(self, points) -> None:
        self.profile["curve"]["points"] = points
        self._save_profile()

    def _curve_tick(self) -> None:
        if not self.curve_switch.isChecked():
            return
        if not getattr(self.backend, "connected", False):
            return
        hottest = self._temperatures.hottest
        if hottest is None:
            return
        rpm = self._interpolate(self.curve_editor.get_points(), hottest)
        if rpm is None:
            return
        if abs(rpm - int(self.state.fan_rpm)) >= 150:
            try:
                self.backend.set_fan_rpm(rpm)
            except Exception as exc:
                self.fan_status_row.set_subtitle(f"curve error: {exc}")
                return
            self.state.fan_rpm = rpm
            self.fan_status_row.set_subtitle(f"curve: {hottest:.0f} °C -> {rpm} RPM")

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
    def _build_lighting(self) -> QWidget:
        self.lighting = LightingPage(self)
        self.engine = self.lighting.engine
        return self.lighting

    # -- battery ------------------------------------------------------------
    def _build_battery(self) -> QWidget:
        page = PageScroll(
            "Battery",
            "The charge limit lives in the controller and survives reboots",
        )
        card = SettingsCard()
        card.body.addWidget(section_label("Battery care"))
        limit_row = SettingRow("Charge limit", "Stop charging at the threshold below")
        self.bho_switch = ToggleSwitch()
        self.bho_switch.toggled.connect(self._on_bho)
        limit_row.add_control(self.bho_switch)
        card.add_row(limit_row)

        threshold_row = SettingRow("Threshold", "50 - 80%")
        self.bho_scale = QSlider(Qt.Orientation.Horizontal)
        self.bho_scale.setRange(p.BHO_MIN, p.BHO_MAX)
        self.bho_scale.setSingleStep(5)
        self.bho_scale.setPageStep(10)
        self.bho_scale.setFixedWidth(260)
        self.bho_scale.valueChanged.connect(self._on_bho_threshold)
        self.bho_value = QLabel("80")
        self.bho_value.setFixedWidth(42)
        self.bho_value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        threshold_row.add_control(self.bho_scale)
        threshold_row.add_control(self.bho_value)
        card.add_row(threshold_row)

        self.battery_row = SettingRow("Battery", "reading...")
        card.add_row(self.battery_row)
        page.body.addWidget(card)
        page.finish()
        return page

    def _on_bho(self, checked: bool) -> None:
        if self._syncing:
            return
        threshold = int(self.bho_scale.value())
        try:
            self.backend.set_bho(checked, threshold)
        except Exception as exc:
            self.toast(str(exc))
            self._sync_from_state()
            return
        self.state.bho_enabled = checked
        self.state.bho_threshold = threshold
        self.profile["battery"] = {
            "limit_enabled": checked,
            "threshold": threshold,
        }
        self._save_profile()
        self._sync_from_state()

    def _on_bho_threshold(self, value: int) -> None:
        self.bho_value.setText(str(value))
        if self._syncing or not self.bho_switch.isChecked():
            return
        try:
            self.backend.set_bho(True, int(value))
        except Exception as exc:
            self.toast(str(exc))
            return
        self.state.bho_threshold = int(value)
        self.profile["battery"]["threshold"] = int(value)
        self._save_profile()

    # -- settings -----------------------------------------------------------
    def _build_settings(self) -> QWidget:
        page = PageScroll(
            "Settings",
            "Ophis is a single user-space app; it installs no driver and needs no service",
        )
        behaviour = SettingsCard()
        behaviour.body.addWidget(section_label("Behaviour"))

        apply_row = SettingRow(
            "Apply the saved profile at start",
            str(profile.config_path()),
        )
        self.apply_on_start = ToggleSwitch()
        self.apply_on_start.setChecked(
            bool(self.profile["settings"].get("apply_on_start", True))
        )
        self.apply_on_start.toggled.connect(self._on_settings_toggle)
        apply_row.add_control(self.apply_on_start)
        behaviour.add_row(apply_row)

        restore_row = SettingRow(
            "Restore defaults on quit",
            "Balanced profile, automatic fans, plain white keyboard",
        )
        self.restore_on_quit = ToggleSwitch()
        self.restore_on_quit.setChecked(
            bool(self.profile["settings"].get("restore_on_quit", True))
        )
        self.restore_on_quit.toggled.connect(self._on_settings_toggle)
        restore_row.add_control(self.restore_on_quit)
        behaviour.add_row(restore_row)

        autostart_row = SettingRow(
            "Start the tray at login",
            "Adds Ophis to the current user's startup entries",
        )
        self.autostart = ToggleSwitch()
        try:
            self.autostart.setChecked(desktop.autostart_enabled())
        except OSError:
            pass
        self.autostart.toggled.connect(self._on_autostart)
        autostart_row.add_control(self.autostart)
        behaviour.add_row(autostart_row)
        page.body.addWidget(behaviour)

        profile_card = SettingsCard()
        profile_card.body.addWidget(section_label("Profile"))
        save_row = SettingRow("Save the current settings")
        save_button = QPushButton("Save")
        save_button.clicked.connect(self._on_save_profile)
        save_row.add_control(save_button)
        profile_card.add_row(save_row)

        apply_profile_row = SettingRow("Apply the saved profile")
        apply_button = QPushButton("Apply")
        apply_button.clicked.connect(self._on_apply_profile)
        apply_profile_row.add_control(apply_button)
        profile_card.add_row(apply_profile_row)
        self.profile_path = label(str(profile.config_path()), muted=True, wrap=True)
        profile_card.add_row(self.profile_path)
        page.body.addWidget(profile_card)

        device_card = SettingsCard()
        device_card.body.addWidget(section_label("Device"))
        self.device_detail = SettingRow("Controller", "checking...")
        recheck = QPushButton("Check again")
        recheck.clicked.connect(self._retry_device)
        self.device_detail.add_control(recheck)
        device_card.add_row(self.device_detail)
        self.synapse_detail = SettingRow("Razer processes", "checking...")
        device_card.add_row(self.synapse_detail)
        device_card.add_row(
            label(
                "Ophis opens the vendor HID collection exclusively. That keeps "
                "Razer Synapse and other tools from writing the same controller "
                "state while Ophis is running.",
                muted=True,
                wrap=True,
            )
        )
        page.body.addWidget(device_card)

        about = SettingsCard()
        about.body.addWidget(section_label("About"))
        revision = build_id()
        version = f"Ophis {__version__}" + (f" ({revision})" if revision else "")
        about.add_row(
            label(
                version
                + " — control centre for the Razer Blade 14 (2022), USB 1532:028C. "
                "Not affiliated with Razer.",
                muted=True,
                wrap=True,
            )
        )
        page.body.addWidget(about)
        page.finish()
        return page

    def _on_settings_toggle(self, _checked: bool) -> None:
        if self._syncing:
            return
        self.profile["settings"]["apply_on_start"] = self.apply_on_start.isChecked()
        self.profile["settings"]["restore_on_quit"] = self.restore_on_quit.isChecked()
        self._save_profile()

    def _on_autostart(self, checked: bool) -> None:
        if self._syncing:
            return
        try:
            desktop.set_autostart(checked)
        except (OSError, ImportError) as exc:
            self.toast(str(exc))
            self._syncing = True
            self.autostart.setChecked(not checked)
            self._syncing = False

    def _on_save_profile(self) -> None:
        old = self.profile
        captured = profile.capture(self.backend)
        for key in ("curve",):
            if key in old:
                captured[key] = old[key]
        for key in ("mode", "device", "animations", "custom"):
            value = old.get("lighting", {}).get(key)
            if value is not None:
                captured["lighting"][key] = value
        captured["settings"] = {
            "apply_on_start": self.apply_on_start.isChecked(),
            "restore_on_quit": self.restore_on_quit.isChecked(),
        }
        self.profile = captured
        self.lighting.profile = self.profile
        self._save_profile()
        self.toast(f"Saved {profile.config_path()}")

    def _on_apply_profile(self) -> None:
        warnings = profile.apply(self.backend, self.profile)
        for warning in warnings:
            self.toast(warning)
        try:
            self.backend.refresh()
        except Exception as exc:
            self.toast(str(exc))
        self._sync_from_state()

    # -- device status ------------------------------------------------------
    def _refresh_device_status(self) -> None:
        connected = bool(getattr(self.backend, "connected", False))
        self.banner_wrap.setVisible(not connected)
        detail = getattr(self.backend, "detail", "") or "not connected"
        if not connected:
            self.banner_text.setText(
                f"{detail} If Razer Synapse is open, quit it and press Retry. "
                "Ophis needs the controller to itself."
            )
        self.device_detail.set_subtitle(detail)
        if self._synapse:
            names = ", ".join(self._synapse[:4])
            self.synapse_detail.set_subtitle(f"running: {names}")
            self.sidebar_status.setText("Razer software is running")
        else:
            self.synapse_detail.set_subtitle("not detected")
            if str(getattr(self.backend, "detail", "")).lower().startswith("preview"):
                self.sidebar_status.setText("Preview mode")
            else:
                self.sidebar_status.setText(
                    "Controller locked by Ophis" if connected else "Controller not connected"
                )

    def _retry_device(self) -> None:
        reconnect = getattr(self.backend, "reconnect", None)
        if reconnect is None:
            self.toast("This backend cannot reconnect")
            return
        reconnect()
        self._refresh_device_status()
        if getattr(self.backend, "connected", False):
            self.toast("Controller connected")
        else:
            self.toast(getattr(self.backend, "detail", "could not connect"))
        self._sync_from_state()
        if self.lighting is not None:
            self.lighting.refresh_connection()

    # -- sensors ------------------------------------------------------------
    def _start_sensors(self) -> None:
        self._sensor_thread = QThread(self)
        self._sensors = SensorWorker()
        self._sensors.moveToThread(self._sensor_thread)
        self._sensor_thread.started.connect(self._sensors.start)
        self._sensors.temperatures.connect(self._refresh_temperatures)
        self._sensors.battery.connect(self._refresh_battery)
        self._sensors.synapse.connect(self._on_synapse)
        self._sensor_thread.start()

    def _refresh_temperatures(self, reading: Temperatures) -> None:
        self._temperatures = reading
        for key, (value_label, bar) in self.temp_rows.items():
            value = getattr(reading, key)
            if value is None:
                value_label.setText("not available")
                bar.setValue(0)
            else:
                value_label.setText(f"{value:.1f} °C")
                bar.setValue(value)

    def _refresh_battery(self, data: dict | None = None) -> None:
        if data is not None:
            self._battery = data
        capacity = self._battery.get("capacity")
        status = self._battery.get("status") or "unknown"
        plugged = self._battery.get("plugged")
        if capacity is None:
            text = "no battery information"
        else:
            suffix = (
                "plugged in"
                if plugged is True
                else "on battery"
                if plugged is False
                else ""
            )
            text = f"{capacity}% - {status}" + (f" - {suffix}" if suffix else "")
        self.battery_row.set_subtitle(text)
        self.sidebar_battery.setText(text)

    def _on_synapse(self, processes: list[str]) -> None:
        self._synapse = list(processes)
        self._refresh_device_status()

    # -- state -> widgets ---------------------------------------------------
    def _sync_from_state(self) -> None:
        self._syncing = True
        try:
            for mode, button in self.profile_buttons.items():
                if int(self.state.power_mode) == int(mode):
                    button.setChecked(True)
                    break
            custom = int(self.state.power_mode) == int(p.PowerMode.CUSTOM)
            self.cpu_boost.setCurrentIndex(max(0, min(3, int(self.state.cpu_boost))))
            self.gpu_boost.setCurrentIndex(max(0, min(2, int(self.state.gpu_boost))))
            self.cpu_boost.setEnabled(custom)
            self.gpu_boost.setEnabled(custom)

            auto = int(self.state.fan_rpm) == 0
            self.fan_auto.setChecked(auto)
            self.fan_scale.setEnabled(not auto)
            if not auto:
                self.fan_scale.setValue(int(self.state.fan_rpm))
                self.fan_value.setText(str(int(self.state.fan_rpm)))
            self.fan_status_row.set_subtitle(
                "automatic" if auto else f"fixed at {int(self.state.fan_rpm)} RPM"
            )

            self.bho_switch.setChecked(bool(self.state.bho_enabled))
            self.bho_scale.setValue(int(self.state.bho_threshold))
            self.bho_scale.setEnabled(bool(self.state.bho_enabled))
            self.bho_value.setText(str(int(self.state.bho_threshold)))

            self.curve_switch.setChecked(bool(self.profile["curve"].get("enabled")))
            self.curve_editor.set_points(self.profile["curve"].get("points", []))
            self.curve_editor.setEnabled(self.curve_switch.isChecked())
        finally:
            self._syncing = False
        if self.lighting is not None:
            self.lighting.sync()

    # -- persistence / lifecycle -------------------------------------------
    def save_profile(self) -> None:
        self._save_profile()

    def _save_profile(self) -> None:
        try:
            profile.save(self.profile)
        except OSError as exc:
            self.toast(f"could not save the profile: {exc}")

    def shutdown(self) -> None:
        if self.engine is not None:
            self.engine.stop()
        if self.curve_timer.isActive():
            self.curve_timer.stop()
        if self._sensor_thread is not None:
            if self._sensors is not None:
                try:
                    QMetaObject.invokeMethod(
                        self._sensors,
                        "stop",
                        Qt.ConnectionType.BlockingQueuedConnection,
                    )
                except RuntimeError:
                    pass
            try:
                self._sensor_thread.quit()
                self._sensor_thread.wait(2000)
            except RuntimeError:
                pass
            self._sensor_thread = None
            self._sensors = None
        self.backend.close()

    def closeEvent(self, event) -> None:
        if self.tray_enabled and not getattr(self.app, "quitting", False):
            self.hide()
            self.app.notify_tray()
            event.ignore()
            return
        self.app.quit_cleanly()
        event.accept()
