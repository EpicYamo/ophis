"""Backends the UI and CLI talk to.

`MockBackend` runs without hardware (development, screenshots, CI).
`DeviceBackend` wraps the real device; it needs write access to the hidraw
node (root, or the udev rule from ``linux/data/``).
"""

from __future__ import annotations

from typing import Protocol

from . import protocol as p
from .device import DeviceState, RazerDevice
from .transport import Transport, default_transport


class Backend(Protocol):
    state: DeviceState
    connected: bool
    detail: str

    def set_power_mode(self, mode: int) -> None: ...
    def set_fan_rpm(self, rpm: int) -> None: ...
    def set_brightness(self, value: int) -> None: ...
    def set_effect(
        self,
        effect: int,
        colour: tuple[int, int, int] | None = None,
        speed: int = 2,
        direction: int = 1,
    ) -> None: ...
    def set_color(self, red: int, green: int, blue: int) -> None: ...
    def write_frame(self, rows) -> None: ...
    def activate_custom_frame(self) -> None: ...
    def set_bho(self, enabled: bool, threshold: int) -> None: ...
    def set_logo(self, mode: int) -> None: ...
    def close(self) -> None: ...


class MockBackend:
    """In-memory state so the interface can be explored without hardware."""

    connected = True

    def __init__(self) -> None:
        self.state = DeviceState()
        self.detail = "Preview mode - nothing is written to the device"

    def set_power_mode(self, mode: int) -> None:
        self.state.power_mode = mode

    def set_fan_rpm(self, rpm: int) -> None:
        self.state.fan_rpm = rpm

    def set_brightness(self, value: int) -> None:
        self.state.brightness = value

    def set_effect(
        self,
        effect: int,
        colour: tuple[int, int, int] | None = None,
        speed: int = 2,
        direction: int = 1,
    ) -> None:
        self.state.extra["effect"] = int(effect)
        self.state.extra["speed"] = speed
        self.state.extra["direction"] = direction
        if colour is not None:
            self.state.extra["color"] = colour

    def set_color(self, red: int, green: int, blue: int) -> None:
        self.state.extra["color"] = (red, green, blue)
        self.state.extra["effect"] = int(p.Effect.STATIC)

    def set_bho(self, enabled: bool, threshold: int) -> None:
        self.state.bho_enabled = enabled
        self.state.bho_threshold = threshold

    def write_frame(self, rows) -> None:
        self.frame = rows

    def activate_custom_frame(self) -> None:
        pass

    def set_logo(self, mode: int) -> None:
        self.state.logo = mode

    def close(self) -> None:
        pass


class DeviceBackend:
    """Real hardware. On failure, ``detail`` explains why."""

    def __init__(self, transport: Transport | None = None) -> None:
        self.transport = transport
        self.device: RazerDevice | None = None
        self.state = DeviceState()
        self.connected = False
        self.detail = ""
        self._connect()

    def _connect(self) -> None:
        try:
            if self.transport is None:
                self.transport = default_transport()
            if self.device is None:
                self.device = RazerDevice(self.transport)
            else:
                self.device.transport = self.transport
            self.device.state = self.state
            self.transport.open()
            self.connected = True
            self.detail = f"Connected: {self.device.model}"
            self.refresh()
        except (OSError, p.RazerError) as exc:
            self.connected = False
            self.detail = f"Not connected: {exc}"

    def reconnect(self) -> None:
        """Drop the handle and try again; useful after Razer Synapse closes."""
        self.close()
        self.transport = None
        self.device = None
        self._connect()

    def _device(self) -> RazerDevice:
        if not self.connected:
            self._connect()
        if self.device is None or not self.connected:
            raise p.RazerError(self.detail or "device is not connected")
        return self.device

    def refresh(self) -> None:
        """Read the current settings; unsupported queries are skipped."""
        if not self.connected or self.device is None:
            return
        try:
            mode, manual = self.device.get_power_state(1)
            self.state.power_mode = mode
            self.state.fan_rpm = self.device.get_fan_target(1) if manual else 0
        except p.RazerError:
            pass
        for which, attr in ((1, "cpu_boost"), (2, "gpu_boost")):
            try:
                setattr(self.state, attr, self.device.get_boost(which))
            except p.RazerError:
                pass
        try:
            self.state.brightness = self.device.get_brightness()
        except p.RazerError:
            pass
        if "logo" in self.device.features:
            try:
                self.state.logo = self.device.get_logo()
            except p.RazerError:
                pass
        if "bho" in self.device.features:
            try:
                self.state.bho_enabled, self.state.bho_threshold = self.device.get_bho()
            except p.RazerError:
                pass

    def set_power_mode(self, mode: int) -> None:
        self._device().set_power_mode(mode, self.state.cpu_boost, self.state.gpu_boost)

    def set_fan_rpm(self, rpm: int) -> None:
        self._device().set_fan_rpm(rpm)

    def set_brightness(self, value: int) -> None:
        self._device().set_brightness(value)

    def set_effect(
        self,
        effect: int,
        colour: tuple[int, int, int] | None = None,
        speed: int = 2,
        direction: int = 1,
    ) -> None:
        self._device().set_effect(effect, colour, speed, direction)

    def set_color(self, red: int, green: int, blue: int) -> None:
        self._device().set_static_color(red, green, blue)

    def set_bho(self, enabled: bool, threshold: int) -> None:
        self._device().set_bho(enabled, threshold)

    def write_frame(self, rows) -> None:
        self._device().write_frame(rows)

    def activate_custom_frame(self) -> None:
        self._device().activate_custom_frame()

    def set_logo(self, mode: int) -> None:
        self._device().set_logo(mode)

    def close(self) -> None:
        if self.transport is not None:
            try:
                self.transport.close()
            except OSError:
                pass
        self.connected = False


def open_backend(preview: bool = False) -> Backend:
    """Return the preview backend, or the real one with its connection state."""
    if preview:
        return MockBackend()
    return DeviceBackend()
