import unittest

from ophis import protocol as p


class PacketTests(unittest.TestCase):
    def test_encode_length_and_header(self):
        pkt = p.Packet.request(p.Class.BATTERY, p.Cmd.BHO_SET, 0x01, bytes([0x80 | 70]))
        raw = pkt.encode()
        self.assertEqual(len(raw), p.PACKET_LEN)
        self.assertEqual(raw[0], 0x00)
        self.assertEqual(raw[1], 0x00)
        self.assertEqual(raw[2], p.TRANSACTION_ID)
        self.assertEqual(raw[6], 0x01)
        self.assertEqual(raw[7], 0x07)
        self.assertEqual(raw[8], 0x12)
        self.assertEqual(raw[9], 0x80 | 70)

    def test_crc_is_xor_of_payload(self):
        pkt = p.Packet.request(p.Class.POWER, p.Cmd.POWER_GET_MODE, 4, bytes([0, 1, 0, 0]))
        raw = pkt.encode()
        expected = 0
        for byte in raw[3:89]:
            expected ^= byte
        self.assertEqual(raw[89], expected)
        self.assertEqual(raw[90], 0x00)

    def test_crc_byte_is_not_an_argument(self):
        # 80 argument bytes live at 9..88, the checksum is the next byte.
        pkt = p.Packet.request(p.Class.LED, p.Cmd.LED_SET_BRIGHTNESS, 3, bytes([1, 5, 0]))
        raw = pkt.encode()
        self.assertEqual(raw[11], 0x00)
        self.assertEqual(raw[88], 0x00)
        self.assertNotEqual(raw[89], 0x00)
        self.assertEqual(p.Packet.decode(raw).arguments[79], 0x00)

    def test_decode_roundtrip(self):
        pkt = p.Packet.request(p.Class.LED, p.Cmd.LED_SET_BRIGHTNESS, 3, bytes([1, 5, 200]))
        decoded = p.Packet.decode(pkt.encode())
        self.assertEqual(decoded.command_class, p.Class.LED)
        self.assertEqual(decoded.command_id, p.Cmd.LED_SET_BRIGHTNESS)
        self.assertEqual(decoded.arguments[2], 200)

    def test_decode_rejects_bad_crc(self):
        raw = bytearray(p.Packet.request(p.Class.LED, p.Cmd.LED_SET_BRIGHTNESS, 3, bytes([1, 5, 200])).encode())
        raw[89] ^= 0xFF
        with self.assertRaises(p.RazerError):
            p.Packet.decode(bytes(raw))

    def test_check_rejects_not_supported(self):
        reply = p.Packet(command_class=0x07, command_id=0x92, data_size=1,
                         arguments=bytes(80), status=p.Status.NOT_SUPPORTED)
        with self.assertRaises(p.NotSupported):
            reply.check()

    def test_check_rejects_mismatched_command(self):
        request = p.Packet.request(p.Class.BATTERY, p.Cmd.BHO_GET, 1, b"\x00")
        reply = p.Packet(command_class=0x0D, command_id=0x82, data_size=4, arguments=bytes(80),
                         status=p.Status.SUCCESSFUL)
        with self.assertRaises(p.RazerError):
            reply.check(request)


class BatteryHealthTests(unittest.TestCase):
    def test_bho_roundtrip(self):
        for enabled in (False, True):
            for threshold in (50, 60, 75, 80):
                raw = p.encode_bho(enabled, threshold)
                self.assertEqual(p.decode_bho(raw), (enabled, threshold))

    def test_bho_flag_bit(self):
        self.assertEqual(p.encode_bho(True, 80), 0x80 | 80)
        self.assertEqual(p.encode_bho(False, 80), 80)

    def test_bho_range(self):
        with self.assertRaises(ValueError):
            p.encode_bho(True, 49)
        with self.assertRaises(ValueError):
            p.encode_bho(True, 81)


class FanTests(unittest.TestCase):
    def test_fan_zero_is_auto(self):
        self.assertEqual(p.fan_to_raw(0), 0)

    def test_fan_rounds_up_to_units(self):
        self.assertEqual(p.fan_to_raw(4200), 42)
        self.assertEqual(p.fan_to_raw(4201), 43)

    def test_fan_clamped_to_range(self):
        self.assertEqual(p.fan_to_raw(1000), 35)
        self.assertEqual(p.fan_to_raw(9000), 50)

    def test_raw_to_fan(self):
        self.assertEqual(p.raw_to_fan(42), 4200)


if __name__ == "__main__":
    unittest.main()
