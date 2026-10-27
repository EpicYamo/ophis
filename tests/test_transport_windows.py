"""Unit tests for the Windows transport's packet path (no hardware needed)."""

from __future__ import annotations

import ctypes
import unittest

from ophis import protocol as p
from ophis.transport_windows import (
    HIDP_CAPS,
    WindowsHidTransport,
    _is_control_collection,
    _looks_like_razer,
)


class FakeHid:
    def __init__(self) -> None:
        self.request = b""
        self.response = b""

    def HidD_SetFeature(self, _handle, buffer, length):
        self.request = ctypes.string_at(buffer, length)
        request = p.Packet.decode(self.request)
        args = request.arguments[: request.data_size]
        reply = p.Packet(
            command_class=request.command_class,
            command_id=request.command_id,
            data_size=len(args),
            arguments=bytes(args) + bytes(80 - len(args)),
            status=p.Status.SUCCESSFUL,
        )
        self.response = reply.encode()
        return 1

    def HidD_GetFeature(self, _handle, buffer, length):
        ctypes.memmove(buffer, self.response, length)
        return 1


class FakeKernel:
    def CloseHandle(self, _handle):
        return 1


class WindowsTransportTests(unittest.TestCase):
    def test_path_filter(self) -> None:
        self.assertTrue(
            _looks_like_razer(r"\\?\hid#vid_1532&pid_028c&mi_03&col03#7&1234")
        )
        self.assertFalse(
            _looks_like_razer(r"\\?\hid#vid_046d&pid_c52b&mi_00#8&5678")
        )

    def test_control_collection_by_feature_length(self) -> None:
        caps = HIDP_CAPS()
        caps.UsagePage = 0x0001  # Generic Desktop: the top-level mouse collection
        caps.Usage = 0x0002
        caps.FeatureReportByteLength = p.PACKET_LEN
        self.assertTrue(_is_control_collection(caps))

        caps.FeatureReportByteLength = 0
        self.assertFalse(_is_control_collection(caps))

        caps.UsagePage = 0xFF00
        caps.FeatureReportByteLength = 0
        self.assertTrue(_is_control_collection(caps))

        self.assertFalse(_is_control_collection(None))

    def test_transact_roundtrip(self) -> None:
        transport = WindowsHidTransport(settle=0.0, gap=0.0)
        transport._handle = 1
        transport._hid = FakeHid()
        transport._kernel32 = FakeKernel()
        request = p.Packet.request(
            p.Class.LED, p.Cmd.LED_SET_BRIGHTNESS, 3, bytes([0x01, 0x05, 0x80])
        )
        reply = transport.transact(request)
        self.assertEqual(reply.command_class, p.Class.LED)
        self.assertEqual(reply.command_id, p.Cmd.LED_SET_BRIGHTNESS)
        self.assertEqual(reply.arg, bytes([0x01, 0x05, 0x80]))
        self.assertEqual(len(transport._hid.request), p.PACKET_LEN)
        self.assertEqual(transport._hid.request[0], 0)


if __name__ == "__main__":
    unittest.main()
