"""Read-only system information that does not come from the Razer protocol."""

from __future__ import annotations

from pathlib import Path

BATTERY = Path("/sys/class/power_supply/BAT0")
AC = Path("/sys/class/power_supply/AC0")


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="ascii").strip()
    except OSError:
        return None


def battery_capacity() -> int | None:
    """Charge percentage, or None when no battery is exposed."""
    value = _read(BATTERY / "capacity")
    return int(value) if value is not None else None


def battery_status() -> str | None:
    """Charging / Discharging / Full / Not charging."""
    return _read(BATTERY / "status")


def ac_online() -> bool | None:
    value = _read(AC / "online")
    return None if value is None else value == "1"


def find_ac_adapter() -> Path | None:
    """Locate the AC adapter node; its name differs between machines."""
    for node in Path("/sys/class/power_supply").glob("*"):
        if (_read(node / "type") or "") == "Mains":
            return node
    return None
