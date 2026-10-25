"""Linux transport: talk to the Razer control interface through hidraw.

The device exposes feature reports on the vendor-defined usage page 0xFF00.
``hidraw`` lets us send and receive them with two ioctls, so no third-party
HID library is needed.
"""

from __future__ import annotations

import fcntl
import glob
import os
import time

from .protocol import PACKET_LEN, Packet, RazerError

VENDOR_ID = "1532"
PRODUCT_ID = "028c"

_IOC_WRITE = 1
_IOC_READ = 2


def _ioc(direction: int, nr: int, size: int) -> int:
    return (direction << 30) | (size << 16) | (ord("H") << 8) | nr


HIDIOCSFEATURE = lambda size: _ioc(_IOC_WRITE | _IOC_READ, 0x06, size)  # noqa: E731
HIDIOCGFEATURE = lambda size: _ioc(_IOC_WRITE | _IOC_READ, 0x07, size)  # noqa: E731


def find_control_node() -> str:
    """Return the hidraw node that exposes the vendor-defined usage page 0xFF00."""
    pattern = f"/sys/bus/hid/devices/*{VENDOR_ID}:{PRODUCT_ID.upper()}*"
    for dev in sorted(glob.glob(pattern)):
        hidraw_dir = os.path.join(dev, "hidraw")
        if not os.path.isdir(hidraw_dir):
            continue
        nodes = os.listdir(hidraw_dir)
        if not nodes:
            continue
        try:
            descriptor = open(os.path.join(dev, "report_descriptor"), "rb").read()
        except OSError:
            continue
        if b"\x06\x00\xff" in descriptor:  # Usage Page (Vendor-Defined 0xFF00)
            return "/dev/" + nodes[0]
    raise RazerError(
        "Razer control interface not found. Is the device connected? "
        f"(expected USB ID {VENDOR_ID}:{PRODUCT_ID})"
    )


class HidrawTransport:
    """Synchronous request/response over a single hidraw node."""

    def __init__(self, path: str | None = None, settle: float = 0.001, gap: float = 0.008):
        self.path = path or find_control_node()
        self._fd: int | None = None
        self._settle = settle
        self._gap = gap

    # -- lifecycle ---------------------------------------------------------
    def open(self) -> None:
        if self._fd is None:
            self._fd = os.open(self.path, os.O_RDWR)

    def close(self) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None

    def __enter__(self) -> "HidrawTransport":
        self.open()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- operation ---------------------------------------------------------
    def transact(self, packet: Packet, retries: int = 3) -> Packet:
        if self._fd is None:
            self.open()
        assert self._fd is not None
        request = bytearray(packet.encode())
        last_error: Exception | None = None

        for _ in range(retries):
            try:
                fcntl.ioctl(self._fd, HIDIOCSFEATURE(PACKET_LEN), request)
                time.sleep(self._settle)
                response = bytearray(PACKET_LEN)
                response[0] = 0x00
                fcntl.ioctl(self._fd, HIDIOCGFEATURE(PACKET_LEN), response)
                reply = Packet.decode(bytes(response))
                reply.check(packet)
                return reply
            except (OSError, RazerError) as exc:
                last_error = exc
                time.sleep(self._gap)
        raise RazerError(f"device did not respond: {last_error}")
