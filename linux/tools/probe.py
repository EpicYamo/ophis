#!/usr/bin/env python3
"""Read-only protocol probe for the Razer Blade 14 (2022), USB 1532:028C.

Sends only "get" commands. Nothing on the device is modified, so it is safe to
run before trusting the rest of the project.

    sudo python3 tools/probe/probe.py
"""

from __future__ import annotations

import fcntl
import glob
import os
import struct
import sys
import time

VENDOR_ID = "1532"
PRODUCT_ID = "028C"
PACKET_LEN = 91

_IOC_WRITE = 1
_IOC_READ = 2


def _ioc(direction: int, nr: int, size: int) -> int:
    return (direction << 30) | (size << 16) | (ord("H") << 8) | nr


HIDIOCSFEATURE = _ioc(_IOC_WRITE | _IOC_READ, 0x06, PACKET_LEN)
HIDIOCGFEATURE = _ioc(_IOC_WRITE | _IOC_READ, 0x07, PACKET_LEN)


def build(command_class: int, command_id: int, data_size: int, args: list[int]) -> bytearray:
    packet = bytearray(PACKET_LEN)
    packet[0] = 0x00  # report number
    packet[2] = 0x1F  # transaction id
    packet[6] = data_size
    packet[7] = command_class
    packet[8] = command_id
    packet[9 : 9 + len(args)] = bytes(args)
    crc = 0
    for byte in packet[2:88]:
        crc ^= byte
    packet[88] = crc
    return packet


def find_control_node() -> tuple[str, str] | tuple[None, None]:
    for device in glob.glob(f"/sys/bus/hid/devices/*{VENDOR_ID}:{PRODUCT_ID}*"):
        hidraw_dir = os.path.join(device, "hidraw")
        if not os.path.isdir(hidraw_dir):
            continue
        nodes = os.listdir(hidraw_dir)
        if not nodes:
            continue
        try:
            descriptor = open(os.path.join(device, "report_descriptor"), "rb").read()
        except OSError:
            continue
        if b"\x06\x00\xff" in descriptor:  # vendor-defined usage page 0xFF00
            return "/dev/" + nodes[0], os.path.basename(device)
    return None, None


def transact(fd: int, packet: bytearray, label: str, expect_id: int | None = None):
    try:
        fcntl.ioctl(fd, HIDIOCSFEATURE, packet)
    except OSError as exc:
        print(f"  [!] {label}: send failed: {exc}")
        return None
    time.sleep(0.05)
    response = bytearray(PACKET_LEN)
    response[0] = 0x00
    try:
        fcntl.ioctl(fd, HIDIOCGFEATURE, response)
    except OSError as exc:
        print(f"  [!] {label}: receive failed: {exc}")
        return None

    status = response[1]
    command_id = response[8]
    args = bytes(response[9:89])
    status_name = {
        0x00: "NEW",
        0x01: "BUSY",
        0x02: "OK",
        0x03: "FAIL",
        0x04: "TIMEOUT",
        0x05: "NOT_SUPPORTED",
    }.get(status, f"0x{status:02x}")

    wanted = expect_id if expect_id is not None else packet[8]
    if command_id not in (wanted, packet[8]):
        print(f"  [?] {label}: unexpected reply cmd=0x{command_id:02x} status={status_name}")
        return args
    print(f"  [+] {label}: status={status_name} args[0:8]={args[:8].hex(' ')}")
    return args


def main() -> int:
    node, device = find_control_node()
    if node is None:
        print("Razer control interface (usage page 0xFF00) not found.")
        return 1
    print(f"Control interface : {node}  ({device})")
    try:
        fd = os.open(node, os.O_RDWR)
    except PermissionError:
        print(f"Permission denied. Run: sudo python3 {sys.argv[0]}")
        return 1

    print("\n--- READ-ONLY QUERIES ---")

    for zone, name in ((1, "CPU"), (2, "GPU")):
        args = transact(fd, build(0x0D, 0x82, 0x04, [0x00, zone, 0, 0]), f"power mode ({name})")
        if args:
            print(f"      mode = {args[2]}  (0=balanced 1=gaming 2=creator 4=custom)")

    for index, name in ((1, "CPU boost"), (2, "GPU boost")):
        args = transact(fd, build(0x0D, 0x87, 0x03, [0x00, index, 0]), name)
        if args:
            print(f"      level = {args[2]}")

    args = transact(fd, build(0x03, 0x83, 0x03, [0x01, 0x05, 0x00]), "keyboard brightness")
    if args:
        print(f"      brightness = {args[2]}")

    args = transact(fd, build(0x03, 0x82, 0x03, [0x01, 0x04]), "logo LED")
    if args:
        print(f"      state = {args[2]}")

    args = transact(fd, build(0x07, 0x92, 0x01, [0x00]), "charge limit", expect_id=0x92)
    if args:
        raw = args[0]
        print(f"      raw=0x{raw:02x} enabled={bool(raw & 0x80)} threshold={raw & 0x7F}%")

    os.close(fd)
    print("\nDone. No setting was changed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
