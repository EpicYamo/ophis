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

    def test_set_fan_switches_to_custom_mode(self):
        self.device.state.power_mode = p.PowerMode.BALANCED
        self.device.set_fan_rpm(4200)
        power_writes = [r for r in self.transport.requests if r.command_id == p.Cmd.POWER_SET_MODE]
        self.assertEqual([r.arguments[1] for r in power_writes], [1, 2])
        self.assertTrue(all(r.arguments[2] == p.PowerMode.CUSTOM for r in power_writes))
        self.assertTrue(all(r.arguments[3] == 1 for r in power_writes))
        self.assertEqual(self.device.state.power_mode, p.PowerMode.CUSTOM)

    def test_set_fan_writes_modes_before_setpoints(self):
        self.device.set_fan_rpm(4200)
        ids = [r.command_id for r in self.transport.requests][:4]
        self.assertEqual(ids, [p.Cmd.POWER_SET_MODE, p.Cmd.POWER_SET_MODE,
                               p.Cmd.FAN_SET_RPM, p.Cmd.FAN_SET_RPM])
        setpoints = [r for r in self.transport.requests if r.command_id == p.Cmd.FAN_SET_RPM]
        self.assertEqual([r.arguments[1] for r in setpoints], [1, 2])
        self.assertEqual([r.arguments[2] for r in setpoints], [42, 42])

    def test_set_fan_zero_disables_manual_mode(self):
        self.device.state.power_mode = p.PowerMode.CUSTOM
        self.device.state.fan_rpm = 4200
        self.device.set_fan_rpm(0)
        power_writes = [r for r in self.transport.requests if r.command_id == p.Cmd.POWER_SET_MODE]
        self.assertTrue(all(r.arguments[3] == 0 for r in power_writes))
        self.assertFalse(any(r.command_id == p.Cmd.FAN_SET_RPM for r in self.transport.requests))
        self.assertEqual(self.device.state.fan_rpm, 0)

    def test_leaving_custom_mode_returns_the_fans_to_the_firmware(self):
        self.device.state.fan_rpm = 4200
        self.device.set_power_mode(p.PowerMode.BALANCED)
        self.assertEqual(self.device.state.fan_rpm, 0)
        power_writes = [r for r in self.transport.requests if r.command_id == p.Cmd.POWER_SET_MODE]
        self.assertTrue(all(r.arguments[3] == 0 for r in power_writes))

    def test_get_fan_target_reads_args_2_in_100_rpm_units(self):
        self.transport.set_response(0x0D, 0x81, [0x00, 0x02, 0x23])
        self.assertEqual(self.device.get_fan_target(2), 3500)

    def test_get_power_state_reads_the_manual_flag(self):
        self.transport.set_response(0x0D, 0x82, [0x00, 0x01, 0x04, 0x01])
        self.assertEqual(self.device.get_power_state(1), (p.PowerMode.CUSTOM, True))

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

    def test_set_logo_uses_the_blade_state_command(self):
        self.device.set_logo(1)
        state = [r for r in self.transport.requests if r.command_id == p.Cmd.LED_SET_EFFECT]
        self.assertEqual(state[-1].arguments[:3], bytes([p.VARSTORE, p.LOGO_LED, 1]))
        self.assertTrue(all(r.transaction_id == p.LOGO_TRANSACTION_ID
                            for r in self.transport.requests))

    def test_set_logo_off_only_writes_the_state(self):
        self.device.set_logo(0)
        ids = [r.command_id for r in self.transport.requests]
        self.assertEqual(ids, [p.Cmd.LED_SET_EFFECT])
        self.assertEqual(self.last().arguments[:3], bytes([p.VARSTORE, p.LOGO_LED, 0]))

    def test_get_logo_reads_the_state_command(self):
        self.transport.set_response(0x03, 0x80, [p.VARSTORE, p.LOGO_LED, 0x01])
        self.assertEqual(self.device.get_logo(), 1)
        self.assertEqual(self.last().command_id, p.Cmd.LED_GET_STATE)
        self.assertEqual(self.last().transaction_id, p.LOGO_TRANSACTION_ID)

    def test_missing_feature_raises(self):
        device = RazerDevice(self.transport, features={"logo"})
        with self.assertRaises(p.NotSupported):
            device.set_bho(True, 80)

    def test_invalid_power_mode_rejected(self):
        with self.assertRaises(ValueError):
            self.device.set_power_mode(7)


if __name__ == "__main__":
    unittest.main()
