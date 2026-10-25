import unittest

from razercc import protocol as p
from razercc.device import RazerDevice
from razercc.transport import FakeTransport


class DeviceTests(unittest.TestCase):
    def setUp(self):
        self.transport = FakeTransport()
        self.device = RazerDevice(self.transport)

    def last(self) -> p.Packet:
        return self.transport.requests[-1]

    def test_get_power_mode_reads_args_2(self):
        self.transport.set_response(0x0D, 0x82, [0x00, 0x01, 0x01, 0x00])
        self.assertEqual(self.device.get_power_mode(1), 1)

    def test_get_boost_reads_args_2(self):
        self.transport.set_response(0x0D, 0x87, [0x00, 0x01, 0x03])
        self.assertEqual(self.device.get_boost(1), 3)

    def test_set_power_mode_balanced_writes_both_zones(self):
        self.device.set_power_mode(p.PowerMode.GAMING)
        modes = [r for r in self.transport.requests if r.command_id == p.Cmd.POWER_SET_MODE]
        self.assertEqual(len(modes), 2)
        self.assertEqual(modes[0].arguments[:4], bytes([0, 1, 1, 0]))
        self.assertEqual(modes[1].arguments[:4], bytes([0, 2, 1, 0]))

    def test_set_fan_sets_manual_flag_then_rpm(self):
        self.device.state.power_mode = p.PowerMode.BALANCED
        self.device.set_fan_rpm(4200)
        self.assertEqual(self.last().command_class, p.Class.POWER)
        self.assertEqual(self.last().command_id, p.Cmd.FAN_SET_RPM)
        self.assertEqual(self.last().arguments[2], 42)
        power_writes = [r for r in self.transport.requests if r.command_id == p.Cmd.POWER_SET_MODE]
        self.assertTrue(all(r.arguments[3] == 1 for r in power_writes))

    def test_set_fan_zero_disables_manual_mode(self):
        self.device.set_fan_rpm(0)
        power_writes = [r for r in self.transport.requests if r.command_id == p.Cmd.POWER_SET_MODE]
        self.assertTrue(all(r.arguments[3] == 0 for r in power_writes))
        self.assertFalse(any(r.command_id == p.Cmd.FAN_SET_RPM for r in self.transport.requests))

    def test_set_bho_encodes_flag_and_threshold(self):
        self.device.set_bho(True, 75)
        self.assertEqual(self.last().command_class, p.Class.BATTERY)
        self.assertEqual(self.last().command_id, p.Cmd.BHO_SET)
        self.assertEqual(self.last().arguments[0], 0x80 | 75)

    def test_get_bho_decodes_response(self):
        self.transport.set_response(0x07, 0x92, [0x80 | 60])
        self.assertEqual(self.device.get_bho(), (True, 60))

    def test_set_brightness(self):
        self.device.set_brightness(180)
        self.assertEqual(self.last().arguments[:3], bytes([p.VARSTORE, p.BACKLIGHT_LED, 180]))

    def test_set_static_color_sends_effect_and_rgb(self):
        self.device.set_static_color(10, 20, 30)
        self.assertEqual(self.last().command_id, p.Cmd.LED_SET_STANDARD_EFFECT)
        self.assertEqual(self.last().arguments[:4], bytes([p.Effect.STATIC, 10, 20, 30]))

    def test_missing_feature_raises(self):
        device = RazerDevice(self.transport, features={"logo"})
        with self.assertRaises(p.NotSupported):
            device.set_bho(True, 80)

    def test_invalid_power_mode_rejected(self):
        with self.assertRaises(ValueError):
            self.device.set_power_mode(7)


if __name__ == "__main__":
    unittest.main()
