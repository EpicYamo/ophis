"""Transport layer: one request/response per feature report.

The protocol is identical on every platform; only the way a 91-byte feature
report reaches the device changes. Linux uses hidraw, Windows uses the HID
class API with an exclusive handle. `default_transport()` picks the right one
without importing platform-specific modules on the other OS.
"""

from __future__ import annotations

import os
from typing import Protocol

from .protocol import Packet

VENDOR_ID = 0x1532
PRODUCT_ID = 0x028C


class Transport(Protocol):
    def transact(self, packet: Packet, retries: int = 3) -> Packet: ...


def default_transport():
    """Return the native transport for this operating system."""
    if os.name == "nt":
        from .transport_windows import WindowsHidTransport

        return WindowsHidTransport()
    from .transport_linux import HidrawTransport

    return HidrawTransport()


class FakeTransport:
    """Records requests and returns canned responses (tests / preview)."""

    def __init__(self, responses: dict[tuple[int, int], tuple[list[int], int]] | None = None):
        self.requests: list[Packet] = []
        self._responses = dict(responses or {})

    def set_response(
        self,
        command_class: int,
        command_id: int,
        args: list[int],
        status: int = 0x02,
    ) -> None:
        self._responses[(command_class, command_id)] = (list(args), status)

    def transact(self, packet: Packet, retries: int = 3) -> Packet:
        self.requests.append(packet)
        args, status = self._responses.get((packet.command_class, packet.command_id), ([], 0x02))
        payload = bytes(args) + bytes(80 - len(args))
        return Packet(
            command_class=packet.command_class,
            command_id=packet.command_id,
            data_size=len(args),
            arguments=payload,
            status=status,
        )
