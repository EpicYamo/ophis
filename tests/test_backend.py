"""Backend plumbing tests that do not need hardware."""

from __future__ import annotations

import unittest

from ophis import protocol as p
from ophis.backend import DeviceBackend, MockBackend
from ophis.device import DeviceState


class StubDevice:
    def __init__(self) -> None:
        self.calls: list[tuple[int, int | None, int | None]] = []
        self.actual_fan_rpm = {1: 2300, 2: 2700}

    def set_power_mode(self, mode, cpu_boost=None, gpu_boost=None) -> None:
        self.calls.append((int(mode), cpu_boost, gpu_boost))

    def get_fan_actual_rpm(self, zone: int) -> int:
        return self.actual_fan_rpm[zone]


def device_backend() -> DeviceBackend:
    backend = DeviceBackend.__new__(DeviceBackend)
    backend.transport = None
    backend.device = StubDevice()
    backend.state = DeviceState()
    backend.connected = True
    backend.detail = ""
    return backend


class BackendTests(unittest.TestCase):
    def test_set_power_mode_accepts_explicit_boosts(self) -> None:
        backend = device_backend()
        backend.set_power_mode(p.PowerMode.CUSTOM, 3, 2)

        self.assertEqual(backend.device.calls, [(4, 3, 2)])
        self.assertEqual(int(backend.state.power_mode), int(p.PowerMode.CUSTOM))
        self.assertEqual(backend.state.cpu_boost, 3)
        self.assertEqual(backend.state.gpu_boost, 2)

    def test_set_power_mode_uses_state_when_boosts_are_omitted(self) -> None:
        backend = device_backend()
        backend.state.cpu_boost = 1
        backend.state.gpu_boost = 0

        backend.set_power_mode(p.PowerMode.CUSTOM)

        self.assertEqual(backend.device.calls, [(4, 1, 0)])

    def test_mock_backend_accepts_boosts(self) -> None:
        backend = MockBackend()
        backend.set_power_mode(p.PowerMode.CUSTOM, 2, 1)

        self.assertEqual(int(backend.state.power_mode), int(p.PowerMode.CUSTOM))
        self.assertEqual(backend.state.cpu_boost, 2)
        self.assertEqual(backend.state.gpu_boost, 1)

    def test_refresh_fan_rpm_updates_both_measured_zones(self) -> None:
        backend = device_backend()

        self.assertEqual(backend.refresh_fan_rpm(), (2300, 2700))
        self.assertEqual(backend.state.fan_actual_rpm, (2300, 2700))


if __name__ == "__main__":
    unittest.main()
