"""Windows transport: HID feature reports on the control collection.

On this laptop the 91-byte control report lives in a collection whose
top-level usage is Generic Desktop / Mouse. Windows opens that collection
exclusively for system use, so ``CreateFile`` rejects both ``share mode 0``
and ``GENERIC_READ`` with access denied. Opening it with ``GENERIC_WRITE``
and a shared handle still succeeds, and ``HidD_SetFeature`` /
``HidD_GetFeature`` work through that handle, which is all this transport
needs.

Windows exposes the 91-byte packet as a feature report with report ID 0, the
same layout the Linux hidraw transport uses.
"""

from __future__ import annotations

import ctypes
import os
import time
from ctypes import wintypes

from .protocol import PACKET_LEN, Packet, RazerError

VENDOR_ID = 0x1532
PRODUCT_ID = 0x028C
VENDOR_USAGE_PAGE = 0xFF00

GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3
DIGCF_PRESENT = 0x02
DIGCF_DEVICEINTERFACE = 0x10
ERROR_NO_MORE_ITEMS = 259
ERROR_SHARING_VIOLATION = 32

ULONG_PTR = ctypes.c_size_t


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


# {4D1E55B2-F16F-11CF-88CB-001111000030}
GUID_DEVINTERFACE_HID = GUID(
    0x4D1E55B2,
    0xF16F,
    0x11CF,
    (ctypes.c_ubyte * 8)(0x88, 0xCB, 0x00, 0x11, 0x11, 0x00, 0x00, 0x30),
)


class SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("InterfaceClassGuid", GUID),
        ("Flags", wintypes.DWORD),
        ("Reserved", ULONG_PTR),
    ]


class SP_DEVICE_INTERFACE_DETAIL_DATA_W(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("DevicePath", wintypes.WCHAR * 1),
    ]


class HIDD_ATTRIBUTES(ctypes.Structure):
    _fields_ = [
        ("Size", wintypes.DWORD),
        ("VendorID", wintypes.WORD),
        ("ProductID", wintypes.WORD),
        ("VersionNumber", wintypes.WORD),
    ]


class HIDP_CAPS(ctypes.Structure):
    _fields_ = [
        ("Usage", ctypes.c_ushort),
        ("UsagePage", ctypes.c_ushort),
        ("InputReportByteLength", ctypes.c_ushort),
        ("OutputReportByteLength", ctypes.c_ushort),
        ("FeatureReportByteLength", ctypes.c_ushort),
        ("Reserved", ctypes.c_ushort * 17),
        ("NumberLinkCollectionNodes", ctypes.c_ushort),
        ("NumberInputButtonCaps", ctypes.c_ushort),
        ("NumberInputValueCaps", ctypes.c_ushort),
        ("NumberInputDataIndices", ctypes.c_ushort),
        ("NumberOutputButtonCaps", ctypes.c_ushort),
        ("NumberOutputValueCaps", ctypes.c_ushort),
        ("NumberOutputDataIndices", ctypes.c_ushort),
        ("NumberFeatureButtonCaps", ctypes.c_ushort),
        ("NumberFeatureValueCaps", ctypes.c_ushort),
        ("NumberFeatureDataIndices", ctypes.c_ushort),
    ]


def _load_libraries():
    if os.name != "nt":
        raise RazerError("the Windows HID transport is only available on Windows")
    setupapi = ctypes.WinDLL("setupapi", use_last_error=True)
    hid = ctypes.WinDLL("hid", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    setupapi.SetupDiGetClassDevsW.argtypes = [
        ctypes.POINTER(GUID),
        wintypes.LPCWSTR,
        wintypes.HWND,
        wintypes.DWORD,
    ]
    setupapi.SetupDiGetClassDevsW.restype = wintypes.HANDLE
    setupapi.SetupDiEnumDeviceInterfaces.argtypes = [
        wintypes.HANDLE,
        ctypes.c_void_p,
        ctypes.POINTER(GUID),
        wintypes.DWORD,
        ctypes.POINTER(SP_DEVICE_INTERFACE_DATA),
    ]
    setupapi.SetupDiEnumDeviceInterfaces.restype = wintypes.BOOL
    setupapi.SetupDiGetDeviceInterfaceDetailW.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(SP_DEVICE_INTERFACE_DATA),
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        ctypes.c_void_p,
    ]
    setupapi.SetupDiGetDeviceInterfaceDetailW.restype = wintypes.BOOL
    setupapi.SetupDiDestroyDeviceInfoList.argtypes = [wintypes.HANDLE]
    setupapi.SetupDiDestroyDeviceInfoList.restype = wintypes.BOOL

    kernel32.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    hid.HidD_GetAttributes.argtypes = [wintypes.HANDLE, ctypes.POINTER(HIDD_ATTRIBUTES)]
    hid.HidD_GetAttributes.restype = ctypes.c_ubyte
    hid.HidD_GetPreparsedData.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.HANDLE),
    ]
    hid.HidD_GetPreparsedData.restype = ctypes.c_ubyte
    hid.HidD_FreePreparsedData.argtypes = [wintypes.HANDLE]
    hid.HidD_FreePreparsedData.restype = ctypes.c_ubyte
    hid.HidP_GetCaps.argtypes = [wintypes.HANDLE, ctypes.POINTER(HIDP_CAPS)]
    hid.HidP_GetCaps.restype = wintypes.LONG
    hid.HidD_SetFeature.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.ULONG]
    hid.HidD_SetFeature.restype = ctypes.c_ubyte
    hid.HidD_GetFeature.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.ULONG]
    hid.HidD_GetFeature.restype = ctypes.c_ubyte

    return setupapi, hid, kernel32


def _error_text(code: int | None = None) -> str:
    code = ctypes.get_last_error() if code is None else code
    if code == ERROR_SHARING_VIOLATION:
        return (
            "the Razer control interface is in use by another program "
            "(close Razer Synapse, then retry)"
        )
    if code:
        return f"{ctypes.FormatError(code)} (error {code})"
    return "unknown Windows error"


def _hid_interface_paths(setupapi, kernel32) -> list[str]:
    """Every present HID device interface path."""
    paths: list[str] = []
    info = setupapi.SetupDiGetClassDevsW(
        ctypes.byref(GUID_DEVINTERFACE_HID),
        None,
        None,
        DIGCF_PRESENT | DIGCF_DEVICEINTERFACE,
    )
    if info in (None, -1, ctypes.c_void_p(-1).value):
        raise RazerError(f"cannot enumerate HID devices: {_error_text()}")

    try:
        index = 0
        while True:
            interface = SP_DEVICE_INTERFACE_DATA()
            interface.cbSize = ctypes.sizeof(interface)
            if not setupapi.SetupDiEnumDeviceInterfaces(
                info,
                None,
                ctypes.byref(GUID_DEVINTERFACE_HID),
                index,
                ctypes.byref(interface),
            ):
                if ctypes.get_last_error() == ERROR_NO_MORE_ITEMS:
                    break
                break

            needed = wintypes.DWORD(0)
            setupapi.SetupDiGetDeviceInterfaceDetailW(
                info,
                ctypes.byref(interface),
                None,
                0,
                ctypes.byref(needed),
                None,
            )
            if needed.value:
                buffer = ctypes.create_string_buffer(needed.value)
                detail = ctypes.cast(
                    buffer, ctypes.POINTER(SP_DEVICE_INTERFACE_DETAIL_DATA_W)
                )
                # The documented size of this structure is 8 bytes on 64-bit
                # Windows and 6 bytes on 32-bit Windows, not sizeof().
                detail.contents.cbSize = 8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 6
                if setupapi.SetupDiGetDeviceInterfaceDetailW(
                    info,
                    ctypes.byref(interface),
                    detail,
                    needed.value,
                    ctypes.byref(needed),
                    None,
                ):
                    # DevicePath is a one-character array in the struct; read
                    # the NUL-terminated string that follows the cbSize field.
                    offset = SP_DEVICE_INTERFACE_DETAIL_DATA_W.DevicePath.offset
                    paths.append(
                        ctypes.wstring_at(ctypes.addressof(detail.contents) + offset)
                    )
            index += 1
    finally:
        setupapi.SetupDiDestroyDeviceInfoList(info)
    return paths


class WindowsHidTransport:
    """Feature-report transport for the Razer control collection."""

    def __init__(self, path: str | None = None, settle: float = 0.001, gap: float = 0.008):
        self.path = path
        self._handle = None
        self._setupapi = None
        self._hid = None
        self._kernel32 = None
        self._caps: HIDP_CAPS | None = None
        self._settle = settle
        self._gap = gap
        self.last_open_error = ""

    # -- lifecycle ---------------------------------------------------------
    def open(self) -> None:
        if self._handle is not None:
            return
        self._setupapi, self._hid, self._kernel32 = _load_libraries()
        if self.path is None:
            self.path = self._find_control_interface()
        self._open_path(self.path)

    def close(self) -> None:
        if self._handle is not None and self._kernel32 is not None:
            self._kernel32.CloseHandle(self._handle)
        self._handle = None
        self._caps = None

    def __enter__(self) -> "WindowsHidTransport":
        self.open()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- discovery ---------------------------------------------------------
    def _find_control_interface(self) -> str:
        assert self._setupapi is not None and self._kernel32 is not None
        paths = _hid_interface_paths(self._setupapi, self._kernel32)
        candidates = [p for p in paths if _looks_like_razer(p)]
        if not candidates:
            raise RazerError(
                "Razer control interface not found "
                f"(expected USB ID {VENDOR_ID:04x}:{PRODUCT_ID:04x}). "
                "Is the laptop's Razer HID device enabled in Device Manager?"
            )

        probes: list[tuple[str, HIDP_CAPS]] = []
        sharing_error = False
        other_error = ""
        for path in candidates:
            handle = self._create_shared(path)
            if handle is None:
                code = ctypes.get_last_error()
                if code == ERROR_SHARING_VIOLATION:
                    sharing_error = True
                elif code:
                    other_error = _error_text(code)
                continue
            try:
                attributes = HIDD_ATTRIBUTES()
                attributes.Size = ctypes.sizeof(attributes)
                if not self._hid.HidD_GetAttributes(
                    handle, ctypes.byref(attributes)
                ):
                    continue
                if (
                    attributes.VendorID != VENDOR_ID
                    or attributes.ProductID != PRODUCT_ID
                ):
                    continue
                caps = _caps(self._hid, handle)
                if caps is not None:
                    probes.append((path, caps))
            finally:
                self._kernel32.CloseHandle(handle)

        if not probes:
            if sharing_error:
                raise RazerError(
                    "could not inspect the Razer HID interfaces because another "
                    "program holds them. Close Razer Synapse and any other HID "
                    "tool, then retry."
                )
            raise RazerError(
                "Razer HID interfaces could not be inspected"
                + (f": {other_error}" if other_error else "")
            )

        # The control interface is the one with the 91-byte feature report.
        # Its top-level usage page is often Generic Desktop (mouse), with a
        # vendor-defined collection nested inside, so UsagePage alone is not
        # enough to identify it.
        selected = [
            path
            for path, caps in probes
            if caps.FeatureReportByteLength == PACKET_LEN
        ]
        if not selected:
            selected = [
                path for path, caps in probes if caps.UsagePage == VENDOR_USAGE_PAGE
            ]
        if not selected:
            detail = ", ".join(
                f"{caps.UsagePage:04x}:{caps.Usage:04x}/{caps.FeatureReportByteLength}b"
                for _path, caps in probes
            )
            raise RazerError(
                "Razer HID device found, but no interface exposes the 91-byte "
                f"feature report (saw {detail})"
            )
        return selected[0]

    def _create_shared(self, path: str, access: int = 0):
        assert self._kernel32 is not None
        handle = self._kernel32.CreateFileW(
            path,
            access,
            FILE_SHARE_READ | FILE_SHARE_WRITE,
            None,
            OPEN_EXISTING,
            0,
            None,
        )
        if handle is None or handle == ctypes.c_void_p(-1).value:
            return None
        return handle

    def _open_path(self, path: str) -> None:
        assert self._hid is not None and self._kernel32 is not None
        handle = self._create_shared(path, GENERIC_WRITE)
        if handle is None:
            self.last_open_error = _error_text()
            raise RazerError(self.last_open_error)

        attributes = HIDD_ATTRIBUTES()
        attributes.Size = ctypes.sizeof(attributes)
        if not self._hid.HidD_GetAttributes(handle, ctypes.byref(attributes)):
            self._kernel32.CloseHandle(handle)
            raise RazerError(f"cannot read HID attributes: {_error_text()}")
        if attributes.VendorID != VENDOR_ID or attributes.ProductID != PRODUCT_ID:
            self._kernel32.CloseHandle(handle)
            raise RazerError(
                "not the Razer Blade control interface "
                f"(found {attributes.VendorID:04x}:{attributes.ProductID:04x})"
            )
        caps = _caps(self._hid, handle)
        if not _is_control_collection(caps):
            self._kernel32.CloseHandle(handle)
            raise RazerError(
                "this HID interface does not expose the 91-byte control report"
            )

        self._handle = handle
        self._caps = caps
        self.last_open_error = ""

    # -- diagnostics -------------------------------------------------------
    def diagnose(self) -> list[dict]:
        """Describe every Razer HID interface, without requiring a lock."""
        if self._setupapi is None or self._kernel32 is None:
            try:
                self._setupapi, self._hid, self._kernel32 = _load_libraries()
            except RazerError as exc:
                return [{"error": str(exc)}]
        assert self._setupapi is not None
        assert self._hid is not None
        assert self._kernel32 is not None
        try:
            paths = _hid_interface_paths(self._setupapi, self._kernel32)
        except RazerError as exc:
            return [{"error": str(exc)}]
        rows: list[dict] = []
        for path in paths:
            if not _looks_like_razer(path):
                continue
            row: dict = {"path": path}
            handle = self._create_shared(path)
            if handle is None:
                row["error"] = _error_text()
                rows.append(row)
                continue
            try:
                attributes = HIDD_ATTRIBUTES()
                attributes.Size = ctypes.sizeof(attributes)
                if self._hid.HidD_GetAttributes(handle, ctypes.byref(attributes)):
                    row["usb"] = f"{attributes.VendorID:04x}:{attributes.ProductID:04x}"
                caps = _caps(self._hid, handle)
                if caps is not None:
                    row["usage_page"] = f"0x{caps.UsagePage:04x}"
                    row["usage"] = f"0x{caps.Usage:04x}"
                    row["feature_bytes"] = caps.FeatureReportByteLength
                    row["control"] = _is_control_collection(caps)
            finally:
                self._kernel32.CloseHandle(handle)
            rows.append(row)
        return rows

    # -- operation ---------------------------------------------------------
    def transact(self, packet: Packet, retries: int = 3) -> Packet:
        if self._handle is None:
            self.open()
        assert self._handle is not None and self._hid is not None
        request = packet.encode()
        last_error: Exception | None = None

        for _ in range(retries):
            try:
                send = ctypes.create_string_buffer(request, PACKET_LEN)
                if not self._hid.HidD_SetFeature(
                    self._handle, ctypes.cast(send, ctypes.c_void_p), PACKET_LEN
                ):
                    raise OSError(_error_text())
                time.sleep(self._settle)
                response = ctypes.create_string_buffer(PACKET_LEN)
                response[0] = b"\x00"
                if not self._hid.HidD_GetFeature(
                    self._handle, ctypes.cast(response, ctypes.c_void_p), PACKET_LEN
                ):
                    raise OSError(_error_text())
                reply = Packet.decode(response.raw)
                reply.check(packet)
                return reply
            except (OSError, RazerError) as exc:
                last_error = exc
                time.sleep(self._gap)
        raise RazerError(f"device did not respond: {last_error}")

    def describe(self) -> dict:
        return {
            "path": self.path,
            "feature_bytes": self._caps.FeatureReportByteLength if self._caps else None,
            "usage_page": self._caps.UsagePage if self._caps else None,
            "handle": int(self._handle) if self._handle else None,
        }


def _looks_like_razer(path: str) -> bool:
    lowered = path.lower()
    return "vid_1532" in lowered and "pid_028c" in lowered


def _caps(hid, handle) -> HIDP_CAPS | None:
    preparsed = wintypes.HANDLE()
    if not hid.HidD_GetPreparsedData(handle, ctypes.byref(preparsed)):
        return None
    try:
        caps = HIDP_CAPS()
        if hid.HidP_GetCaps(preparsed, ctypes.byref(caps)) < 0:
            return None
        return caps
    finally:
        hid.HidD_FreePreparsedData(preparsed)


def _is_control_collection(caps: HIDP_CAPS | None) -> bool:
    if caps is None:
        return False
    # The vendor page is the strongest signal, but on this laptop the control
    # collection is nested under a Generic Desktop/mouse top-level collection.
    # Its 91-byte feature report is then the reliable marker.
    return (
        caps.UsagePage == VENDOR_USAGE_PAGE
        or caps.FeatureReportByteLength == PACKET_LEN
    )
