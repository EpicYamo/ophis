"""Temperature sensors from /sys/class/hwmon.

There is no fan tachometer on this laptop, but the CPU, GPU and NVMe sensors
are all exposed by the kernel, which is enough for a fan curve.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

HWMON = Path("/sys/class/hwmon")

# hwmon driver name -> (attribute used for the reading, label)
_SENSORS = {
    "k10temp": "cpu",
    "coretemp": "cpu",
    "amdgpu": "gpu",
    "nouveau": "gpu",
    "nvme": "storage",
    "acpitz": "chassis",
}


@dataclass
class Temperatures:
    cpu: float | None = None
    gpu: float | None = None
    storage: float | None = None
    chassis: float | None = None

    @property
    def hottest(self) -> float | None:
        values = [value for value in (self.cpu, self.gpu) if value is not None]
        return max(values) if values else None

    def as_dict(self) -> dict[str, float | None]:
        return {
            "cpu": self.cpu,
            "gpu": self.gpu,
            "storage": self.storage,
            "chassis": self.chassis,
        }


def _read_millidegrees(path: Path) -> float | None:
    try:
        return int(path.read_text(encoding="ascii").strip()) / 1000.0
    except (OSError, ValueError):
        return None


def read() -> Temperatures:
    """Read every sensor once. Missing sensors stay None."""
    result = Temperatures()
    if not HWMON.is_dir():
        return result

    for node in sorted(HWMON.glob("hwmon*")):
        try:
            name = (node / "name").read_text(encoding="ascii").strip()
        except OSError:
            continue
        kind = _SENSORS.get(name)
        if kind is None:
            continue
        # temp1 is Tctl/edge/composite on all of these drivers; temp2 is Tdie
        # on some Ryzen parts, which is closer to the real junction.
        candidate = _read_millidegrees(node / "temp2_input")
        if candidate is None:
            candidate = _read_millidegrees(node / "temp1_input")
        if candidate is None:
            continue
        current = getattr(result, kind)
        if current is None or candidate > current:
            setattr(result, kind, round(candidate, 1))
    return result


def sensor_names() -> dict[str, str]:
    """Map of hwmon driver name to the field it fills, for diagnostics."""
    found: dict[str, str] = {}
    for node in sorted(HWMON.glob("hwmon*")):
        try:
            name = (node / "name").read_text(encoding="ascii").strip()
        except OSError:
            continue
        if name in _SENSORS:
            found[name] = _SENSORS[name]
    return found
