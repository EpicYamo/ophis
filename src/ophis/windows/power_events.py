"""Windows power/display notifications used to restore the controller after resume."""

from __future__ import annotations

import ctypes
import os
import uuid
from ctypes import wintypes
from typing import Callable

from PySide6.QtCore import QAbstractNativeEventFilter

WM_POWERBROADCAST = 0x0218
PBT_APMSUSPEND = 0x0004
PBT_APMRESUMECRITICAL = 0x0006
PBT_APMRESUMESUSPEND = 0x0007
PBT_APMRESUMEAUTOMATIC = 0x0012
PBT_POWERSETTINGCHANGE = 0x8013

DEVICE_NOTIFY_WINDOW_HANDLE = 0


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class _POWERBROADCAST_SETTING(ctypes.Structure):
    _fields_ = [
        ("PowerSetting", _GUID),
        ("DataLength", wintypes.DWORD),
        ("Data", ctypes.c_ubyte * 1),
    ]


_POWER_SETTING_GUIDS = {
    # Monitor/display on or off, AC/DC source, Windows power-saver state, and
    # the active power-scheme personality (best power efficiency/balanced/best
    # performance on modern Windows).
    uuid.UUID("6FE69556-704A-47A0-8F24-C28D936FDA47"),  # console display
    uuid.UUID("2B84C20E-AD23-4DDF-93DB-05FFBD7EFCA5"),  # session display
    uuid.UUID("5D3E9A59-E9D5-4B00-A6BD-FF34FF516548"),  # AC/DC source
    uuid.UUID("E00958C0-C213-4ACE-AC77-FECCED2EEEA5"),  # power saver
    uuid.UUID("245D8541-3943-4422-B025-13A784F679B7"),  # scheme personality
}
_DISPLAY_STATE_GUIDS = {
    uuid.UUID("6FE69556-704A-47A0-8F24-C28D936FDA47"),
    uuid.UUID("2B84C20E-AD23-4DDF-93DB-05FFBD7EFCA5"),
}


def _guid_value(value: _GUID) -> uuid.UUID:
    return uuid.UUID(bytes_le=ctypes.string_at(ctypes.addressof(value), 16))


class WindowsPowerEventFilter(QAbstractNativeEventFilter):
    """Translate Windows sleep, display, and power-plan events into callbacks."""

    def __init__(
        self,
        hwnd: int,
        on_suspend: Callable[[], None],
        on_resume: Callable[[], None],
        on_power_change: Callable[[], None],
    ) -> None:
        super().__init__()
        self._on_suspend = on_suspend
        self._on_resume = on_resume
        self._on_power_change = on_power_change
        self._user32 = None
        self._registrations: list[object] = []
        if os.name == "nt":
            try:
                self._register(hwnd)
            except (OSError, AttributeError, TypeError):
                self.close()

    def _register(self, hwnd: int) -> None:
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        register = self._user32.RegisterPowerSettingNotification
        register.argtypes = [wintypes.HANDLE, ctypes.POINTER(_GUID), wintypes.DWORD]
        register.restype = wintypes.HANDLE

        for value in _POWER_SETTING_GUIDS:
            guid = _GUID.from_buffer_copy(value.bytes_le)
            handle = register(
                wintypes.HANDLE(hwnd),
                ctypes.byref(guid),
                DEVICE_NOTIFY_WINDOW_HANDLE,
            )
            if handle:
                self._registrations.append(handle)

    def close(self) -> None:
        if self._user32 is None:
            return
        unregister = getattr(self._user32, "UnregisterPowerSettingNotification", None)
        if unregister is None:
            self._registrations.clear()
            return
        unregister.argtypes = [wintypes.HANDLE]
        unregister.restype = wintypes.BOOL
        for handle in self._registrations:
            unregister(handle)
        self._registrations.clear()

    def nativeEventFilter(self, eventType, message):  # noqa: N802 - Qt virtual
        if os.name != "nt" or bytes(eventType) != b"windows_generic_MSG":
            return False
        try:
            msg = ctypes.cast(
                int(message), ctypes.POINTER(wintypes.MSG)
            ).contents
            if msg.message != WM_POWERBROADCAST:
                return False

            event = int(msg.wParam)
            if event == PBT_APMSUSPEND:
                self._on_suspend()
            elif event in (
                PBT_APMRESUMECRITICAL,
                PBT_APMRESUMESUSPEND,
                PBT_APMRESUMEAUTOMATIC,
            ):
                self._on_resume()
            elif event == PBT_POWERSETTINGCHANGE and msg.lParam:
                setting = ctypes.cast(
                    msg.lParam, ctypes.POINTER(_POWERBROADCAST_SETTING)
                ).contents
                guid = _guid_value(setting.PowerSetting)
                if guid in _DISPLAY_STATE_GUIDS and setting.DataLength:
                    state = ctypes.c_ubyte.from_address(
                        int(msg.lParam)
                        + _POWERBROADCAST_SETTING.Data.offset
                    ).value
                    (self._on_resume if state else self._on_suspend)()
                elif guid in _POWER_SETTING_GUIDS:
                    self._on_power_change()
        except (ValueError, OSError, TypeError, ctypes.ArgumentError):
            # Native messages must never prevent Qt from dispatching normally.
            return False
        return False
