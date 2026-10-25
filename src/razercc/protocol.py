"""Razer HID control protocol (91-byte feature report).

This module is completely hardware independent: it builds and parses packets,
so the test suite runs without a device attached.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import IntEnum

PACKET_LEN = 91
TRANSACTION_ID = 0x1F
CRC_START = 2
CRC_END = 88  # exclusive: bytes 2..87

ARGS_LEN = 80


class Status(IntEnum):
    NEW = 0x00
    BUSY = 0x01
    SUCCESSFUL = 0x02
    FAILURE = 0x03
    TIMEOUT = 0x04
    NOT_SUPPORTED = 0x05


class Class(IntEnum):
    """Values of the packet `command_class` field."""

    LED = 0x03
    BATTERY = 0x07
    POWER = 0x0D


class Cmd(IntEnum):
    """Values of the packet `command_id` field."""

    # 0x03 - LED
    LED_SET_EFFECT = 0x00
    LED_SET_LOGO_EFFECT = 0x02
    LED_SET_BRIGHTNESS = 0x03
    LED_SET_STANDARD_EFFECT = 0x0A
    LED_SET_CUSTOM_FRAME = 0x0B
    LED_GET_LOGO_EFFECT = 0x82
    LED_GET_BRIGHTNESS = 0x83

    # 0x07 - Battery Health Optimizer
    BHO_SET = 0x12
    BHO_GET = 0x92

    # 0x0D - Power and fan
    FAN_SET_RPM = 0x01
    POWER_SET_MODE = 0x02
    BOOST_SET = 0x07
    POWER_GET_MODE = 0x82
    BOOST_GET = 0x87


class Effect(IntEnum):
    OFF = 0x00
    WAVE = 0x01
    REACTIVE = 0x02
    BREATHING = 0x03
    SPECTRUM = 0x04
    CUSTOM_FRAME = 0x05
    STATIC = 0x06
    STARLIGHT = 0x19


class PowerMode(IntEnum):
    BALANCED = 0
    GAMING = 1
    CREATOR = 2
    CUSTOM = 4


# LED targets
NOSTORE = 0x00
VARSTORE = 0x01
LOGO_LED = 0x04
BACKLIGHT_LED = 0x05


class RazerError(Exception):
    """Protocol-level failure."""


class NotSupported(RazerError):
    """The device does not implement the requested feature."""


class DeviceTimeout(RazerError):
    """The device did not answer in time."""


def checksum(data: bytes) -> int:
    """Razer CRC: XOR of bytes 2..87."""
    crc = 0
    for byte in data[CRC_START:CRC_END]:
        crc ^= byte
    return crc


@dataclass(frozen=True, slots=True)
class Packet:
    command_class: int
    command_id: int
    data_size: int = 0
    arguments: bytes = b""
    status: int = Status.NEW
    transaction_id: int = TRANSACTION_ID
    protocol_type: int = 0x00
    remaining_packets: int = 0
    crc: int = 0
    reserved: int = 0x00

    # -- construction ------------------------------------------------------
    @classmethod
    def request(
        cls,
        command_class: int,
        command_id: int,
        data_size: int = 0,
        arguments: bytes = b"",
    ) -> "Packet":
        if len(arguments) > ARGS_LEN:
            raise ValueError(f"arguments cannot exceed {ARGS_LEN} bytes")
        return cls(
            command_class=int(command_class),
            command_id=int(command_id),
            data_size=data_size,
            arguments=bytes(arguments),
        )

    # -- serialization -----------------------------------------------------
    def encode(self) -> bytes:
        buf = bytearray(PACKET_LEN)
        buf[0] = 0x00  # report number
        buf[1] = self.status & 0xFF
        buf[2] = self.transaction_id
        buf[3:5] = struct.pack("<H", self.remaining_packets)
        buf[5] = self.protocol_type
        buf[6] = self.data_size
        buf[7] = self.command_class
        buf[8] = self.command_id
        buf[9 : 9 + len(self.arguments)] = self.arguments
        buf[88] = checksum(bytes(buf))
        buf[89] = self.reserved
        return bytes(buf)

    @classmethod
    def decode(cls, data: bytes, accept_crc: int | None = None) -> "Packet":
        """Parse a reply.

        The firmware does not recompute the checksum for replies: it keeps the
        one from the request in byte 88. So a reply that carries data (fan rpm,
        brightness, charge limit) fails a strict check. Pass the request's
        checksum as `accept_crc` to accept that echo as well; the status byte
        and the echoed command class/id are still validated by `check()`.
        """
        if len(data) != PACKET_LEN:
            raise ValueError(f"expected {PACKET_LEN} bytes, got {len(data)}")
        expected = checksum(data)
        actual = data[88]
        if expected != actual and actual != accept_crc:
            raise RazerError(f"CRC mismatch: expected 0x{expected:02x}, got 0x{actual:02x}")
        return cls(
            command_class=data[7],
            command_id=data[8],
            data_size=data[6],
            arguments=data[9:89],
            status=data[1],
            transaction_id=data[2],
            protocol_type=data[5],
            remaining_packets=struct.unpack("<H", data[3:5])[0],
            crc=actual,
            reserved=data[89],
        )

    # -- helpers -----------------------------------------------------------
    @property
    def arg(self) -> bytes:
        return self.arguments[: self.data_size] if self.data_size else self.arguments

    def check(self, request: "Packet | None" = None) -> None:
        """Raise if this response is not a successful reply to `request`."""
        if request is not None and (
            self.command_class != request.command_class
            or self.command_id != request.command_id
        ):
            raise RazerError(
                "response does not match request: "
                f"sent 0x{request.command_class:02x}/0x{request.command_id:02x}, "
                f"received 0x{self.command_class:02x}/0x{self.command_id:02x}"
            )
        if self.status == Status.NOT_SUPPORTED:
            raise NotSupported("device does not support this command")
        if self.status == Status.TIMEOUT:
            raise DeviceTimeout("device timed out")
        if self.status not in (Status.SUCCESSFUL, Status.NEW):
            raise RazerError(f"command failed (status=0x{self.status:02x})")

    def __str__(self) -> str:  # pragma: no cover - display only
        name = (
            Status(self.status).name
            if self.status in Status._value2member_map_
            else f"0x{self.status:02x}"
        )
        return (
            f"Packet(class=0x{self.command_class:02x} cmd=0x{self.command_id:02x} "
            f"size={self.data_size} status={name} args={self.arg.hex(' ')})"
        )


# --- Battery Health Optimizer --------------------------------------------
BHO_FLAG = 0x80
BHO_MIN, BHO_MAX = 50, 80


def encode_bho(enabled: bool, threshold: int) -> int:
    if not BHO_MIN <= threshold <= BHO_MAX:
        raise ValueError(f"charge threshold must be between {BHO_MIN} and {BHO_MAX}")
    return (BHO_FLAG if enabled else 0) | threshold


def decode_bho(raw: int) -> tuple[bool, int]:
    return bool(raw & BHO_FLAG), raw & ~BHO_FLAG


def fan_to_raw(rpm: int, low: int = 3500, high: int = 5000) -> int:
    """Convert RPM to the 100-RPM units the device expects (rounded up)."""
    if rpm <= 0:
        return 0
    clamped = max(low, min(high, rpm))
    return (clamped + 99) // 100


def raw_to_fan(units: int) -> int:
    return units * 100
