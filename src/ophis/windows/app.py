"""Ophis for Windows: window, tray, profile and CLI entry points."""

from __future__ import annotations

import getpass
import sys
from pathlib import Path

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtGui import QAction, QGuiApplication
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from .. import __version__, build_id, profile
from ..backend import DeviceBackend, MockBackend
from .icons import app_icon
from .sensors import detect_synapse
from .window import MainWindow


def _stylesheet() -> str:
    path = Path(__file__).with_name("theme.qss")
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


class OphisApp:
    def __init__(
        self,
        *,
        preview: bool = False,
        tray: bool = False,
        show: bool = False,
        enable_tray: bool = True,
    ) -> None:
        self.quitting = False
        self.preview = preview
        self.enable_tray = enable_tray
        self.start_hidden = tray and not show
        QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
        self.application = QApplication.instance() or QApplication(sys.argv[:1])
        self.application.setApplicationName("Ophis")
        self.application.setApplicationDisplayName("Ophis")
        self.application.setOrganizationName("EpicYamo")
        self.application.setApplicationVersion(__version__)
        self.application.setWindowIcon(app_icon())
        self.application.setStyle("Fusion")
        self.application.setStyleSheet(_stylesheet())

        # Claim the named pipe before touching the HID device: a second launch
        # must never open the controller just to discover the first one.
        self._claim_instance()

        self.backend = MockBackend() if preview else DeviceBackend()
        if (
            not preview
            and getattr(self.backend, "connected", False)
            and self.profile_setting("apply_on_start", True)
        ):
            try:
                profile.apply(self.backend, profile.load())
                self.backend.refresh()
            except Exception:
                pass

        self.window = MainWindow(self, self.backend, tray_enabled=False)
        self.tray: QSystemTrayIcon | None = None
        self._server: QLocalServer | None = None
        self._configure_tray()
        self.window.tray_enabled = self.tray is not None
        if self.start_hidden and self.tray is not None:
            self.window.hide()
        else:
            self.window.show()
        if self.tray is not None and self.start_hidden:
            self.tray.showMessage(
                "Ophis",
                "Running in the tray. Right-click the icon to quit.",
                QSystemTrayIcon.MessageIcon.Information,
                2500,
            )

    @staticmethod
    def profile_setting(key: str, default):
        return profile.load().get("settings", {}).get(key, default)

    # -- tray ---------------------------------------------------------------
    def _configure_tray(self) -> None:
        if not self.enable_tray or not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(app_icon(), self.application)
        self.tray.setToolTip("Ophis")
        menu = QMenu()
        open_action = QAction("Open Ophis", menu)
        open_action.triggered.connect(self.show_window)
        menu.addAction(open_action)
        defaults_action = QAction("Restore default settings", menu)
        defaults_action.triggered.connect(self.restore_defaults)
        menu.addAction(defaults_action)
        menu.addSeparator()
        quit_action = QAction("Quit", menu)
        quit_action.triggered.connect(self.quit_cleanly)
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _on_tray_activated(self, reason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.show_window()

    def notify_tray(self) -> None:
        if self.tray is not None:
            self.tray.showMessage(
                "Ophis",
                "Still running in the tray. Use Quit to restore defaults.",
                QSystemTrayIcon.MessageIcon.Information,
                1800,
            )

    def show_window(self) -> None:
        self.window.showNormal()
        self.window.raise_()
        self.window.activateWindow()

    # -- actions ------------------------------------------------------------
    def restore_defaults(self) -> None:
        if self.window.lighting is not None:
            self.window.lighting.engine.stop()
        if self.window.curve_switch.isChecked():
            self.window.curve_switch.setChecked(False)
        if getattr(self.backend, "connected", False):
            try:
                profile.restore_defaults(self.backend)
                self.backend.refresh()
            except Exception as exc:
                self.window.toast(str(exc))
        self.window._sync_from_state()  # noqa: SLF001 - shared with the tray
        self.window.toast("Restored default settings")

    def quit_cleanly(self) -> None:
        if self.quitting:
            return
        self.quitting = True
        if self.window.engine is not None:
            self.window.engine.stop()
        if (
            not self.preview
            and getattr(self.backend, "connected", False)
            and self.profile_setting("restore_on_quit", True)
        ):
            try:
                profile.restore_defaults(self.backend)
            except Exception:
                pass
        try:
            self.window.shutdown()
        finally:
            if self.tray is not None:
                self.tray.hide()
            self.application.quit()

    # -- single instance ----------------------------------------------------
    def _claim_instance(self) -> None:
        name = f"ophis-{getpass.getuser()}"
        probe = QLocalSocket()
        probe.connectToServer(name)
        if probe.waitForConnected(250):
            probe.write(b"show")
            probe.flush()
            probe.waitForBytesWritten(250)
            probe.disconnectFromServer()
            raise SystemExit(0)

        QLocalServer.removeServer(name)
        self._server = QLocalServer(self.application)
        self._server.newConnection.connect(self._accept_connection)
        self._server.listen(name)

    def _accept_connection(self) -> None:
        assert self._server is not None
        socket = self._server.nextPendingConnection()
        if socket is None:
            return
        socket.readyRead.connect(lambda: self._handle_socket(socket))
        if socket.bytesAvailable():
            self._handle_socket(socket)

    def _handle_socket(self, socket: QLocalSocket) -> None:
        data = bytes(socket.readAll())
        if b"show" in data:
            self.show_window()
        elif b"quit" in data:
            self.quit_cleanly()
        socket.disconnectFromServer()


# -- CLI --------------------------------------------------------------------
def _probe() -> int:
    backend = DeviceBackend()
    print(f"Ophis {__version__} ({build_id() or 'packaged build'})")
    print(f"connected: {backend.connected}")
    print(f"detail: {backend.detail}")
    if backend.device is not None:
        print(f"model: {backend.device.model}")
        print(f"features: {', '.join(sorted(backend.device.features))}")
    transport = backend.transport
    describe = getattr(transport, "describe", None)
    if callable(describe):
        for key, value in describe().items():
            print(f"{key}: {value}")
    diagnose = getattr(transport, "diagnose", None)
    if callable(diagnose):
        rows = diagnose()
        if rows:
            print("hid interfaces:")
            for row in rows:
                print(f"  {row}")
        else:
            print("hid interfaces: none")
    if backend.connected:
        state = backend.state
        print(f"power mode: {int(state.power_mode)}")
        print(f"fan target: {int(state.fan_rpm)} RPM")
        print(f"brightness: {int(state.brightness)}")
        print(f"logo: {int(state.logo)}")
        print(
            f"charge limit: {bool(state.bho_enabled)} "
            f"at {int(state.bho_threshold)}%"
        )
    razer = detect_synapse()
    print(f"razer processes: {', '.join(razer) if razer else 'none'}")
    connected = backend.connected
    backend.close()
    return 0 if connected else 1


def _restore() -> int:
    backend = DeviceBackend()
    if not backend.connected:
        print(f"not connected: {backend.detail}")
        backend.close()
        return 1
    warnings = profile.restore_defaults(backend)
    for warning in warnings:
        print(f"warning: {warning}")
    backend.close()
    print("restored defaults")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv if argv is None else argv)
    if "--version" in args:
        print(f"Ophis {__version__}")
        return 0
    if "--probe" in args:
        return _probe()
    if "--restore" in args:
        return _restore()
    if "--self-test" in args:
        # Used by CI: build the whole window with a fake device, let the event
        # loop run briefly, then shut down through the normal quit path.
        from PySide6.QtCore import QTimer

        controller = OphisApp(preview=True, tray=False, show=True, enable_tray=False)
        QTimer.singleShot(2000, controller.quit_cleanly)
        code = controller.application.exec()
        print("self-test ok")
        return code

    preview = "--preview" in args
    tray = "--tray" in args
    show = "--show" in args
    no_tray = "--no-tray" in args
    # Unknown arguments are ignored: Windows shortcuts sometimes append flags.
    controller = OphisApp(preview=preview, tray=tray, show=show)
    if no_tray and controller.tray is not None:
        controller.tray.hide()
        controller.tray = None
        controller.window.tray_enabled = False
    return controller.application.exec()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
