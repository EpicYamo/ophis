"""Temperatures, battery and Razer-process detection for Windows.

Nothing here installs a driver. The GPU is read through NVML's command line,
the CPU and NVMe through ACPI/storage CIM classes, and the battery through
Win32_Battery. The calls are slow, so they run in a worker thread and the
results are cached.
"""

from __future__ import annotations

import json
import os
import subprocess
import time

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from .. import sysinfo, thermal
from ..thermal import Temperatures

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_SYNAPSE_PATTERNS = (
    "razer",
    "synapse",
    "game manager",
    "chroma",
)


def _run(command: list[str], timeout: float = 6.0) -> str | None:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _powershell(script: str, timeout: float = 7.0) -> str | None:
    return _run(
        [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            script,
        ],
        timeout=timeout,
    )


def _powershell_json(script: str) -> dict | None:
    output = _powershell(script)
    if not output:
        return None
    output = output.lstrip("\ufeff")
    try:
        data = json.loads(output)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


class _CimCache:
    """CPU and NVMe readings change slowly; PowerShell is expensive."""

    def __init__(self) -> None:
        self.cpu: float | None = None
        self.storage: float | None = None
        self.at = 0.0

    def get(self) -> tuple[float | None, float | None]:
        if time.monotonic() - self.at < 10.0:
            return self.cpu, self.storage
        self.at = time.monotonic()
        self.cpu, self.storage = _read_cim()
        return self.cpu, self.storage


_cim = _CimCache()


def _read_cim() -> tuple[float | None, float | None]:
    data = _powershell_json(
        "$cpu = (Get-CimInstance -Namespace root/WMI -ClassName "
        "MSAcpi_ThermalZoneTemperature -ErrorAction SilentlyContinue | "
        "Measure-Object -Property CurrentTemperature -Maximum).Maximum; "
        "$disk = (Get-PhysicalDisk -ErrorAction SilentlyContinue | "
        "Get-StorageReliabilityCounter -ErrorAction SilentlyContinue | "
        "Measure-Object -Property Temperature -Maximum).Maximum; "
        "@{cpu=$cpu; disk=$disk} | ConvertTo-Json -Compress"
    )
    if not data:
        return None, None
    cpu = data.get("cpu")
    storage = data.get("disk")
    cpu_value = None
    storage_value = None
    try:
        if cpu is not None:
            # ACPI thermal zones report tenths of a kelvin.
            value = float(cpu) / 10.0 - 273.15
            if 20.0 <= value <= 120.0:
                cpu_value = round(value, 1)
    except (TypeError, ValueError):
        pass
    try:
        if storage is not None:
            value = float(storage)
            if 0.0 <= value <= 120.0:
                storage_value = round(value, 1)
    except (TypeError, ValueError):
        pass
    return cpu_value, storage_value


def _read_gpu() -> float | None:
    commands = [
        ["nvidia-smi"],
        [r"C:\Windows\System32\nvidia-smi.exe"],
        [r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe"],
    ]
    for base in commands:
        output = _run(
            base
            + [
                "--query-gpu=temperature.gpu",
                "--format=csv,noheader,nounits",
            ],
            timeout=3.0,
        )
        if not output:
            continue
        for line in output.splitlines():
            try:
                value = float(line.strip())
            except ValueError:
                continue
            if 0.0 <= value <= 120.0:
                return value
    return None


def read_temperatures() -> Temperatures:
    if os.name != "nt":
        return thermal.read()
    cpu, storage = _cim.get()
    return Temperatures(cpu=cpu, gpu=_read_gpu(), storage=storage)


def _read_battery_windows() -> dict:
    data = _powershell_json(
        "Get-CimInstance Win32_Battery -ErrorAction SilentlyContinue | "
        "Select-Object -First 1 EstimatedChargeRemaining,BatteryStatus | "
        "ConvertTo-Json -Compress"
    )
    if not data:
        return {"capacity": None, "status": "no battery information", "plugged": None}
    try:
        capacity = int(data.get("EstimatedChargeRemaining"))
    except (TypeError, ValueError):
        capacity = None
    status_code = data.get("BatteryStatus")
    status_map = {
        1: ("discharging", False),
        2: ("AC power", True),
        3: ("full", True),
        4: ("low", False),
        5: ("critical", False),
        6: ("charging", True),
        7: ("charging", True),
        8: ("charging", True),
        9: ("charging", True),
        10: ("unknown", None),
        11: ("partially charged", True),
    }
    status, plugged = status_map.get(status_code, ("unknown", None))
    return {"capacity": capacity, "status": status, "plugged": plugged}


def read_battery() -> dict:
    if os.name != "nt":
        return {
            "capacity": sysinfo.battery_capacity(),
            "status": sysinfo.battery_status() or "unknown",
            "plugged": sysinfo.ac_online(),
        }
    return _read_battery_windows()


def detect_synapse() -> list[str]:
    if os.name != "nt":
        return []
    output = _run(["tasklist", "/FO", "CSV", "/NH"], timeout=4.0)
    if not output:
        return []
    found: set[str] = set()
    for line in output.splitlines():
        name = line.split(",")[0].strip('"')
        lowered = name.lower()
        if any(pattern in lowered for pattern in _SYNAPSE_PATTERNS):
            found.add(name)
    return sorted(found)


class SensorWorker(QObject):
    temperatures = Signal(object)
    battery = Signal(object)
    synapse = Signal(list)

    def __init__(self) -> None:
        super().__init__()
        self._timer: QTimer | None = None
        self._tick = 0

    @Slot()
    def start(self) -> None:
        self._timer = QTimer(self)
        self._timer.setInterval(2000)
        self._timer.timeout.connect(self.poll)
        self._timer.start()
        self.poll()

    @Slot()
    def stop(self) -> None:
        if self._timer is not None:
            self._timer.stop()
            self._timer = None

    @Slot()
    def poll(self) -> None:
        try:
            self.temperatures.emit(read_temperatures())
        except Exception:
            self.temperatures.emit(Temperatures())
        self._tick += 1
        if self._tick % 5:
            return
        try:
            self.battery.emit(read_battery())
        except Exception:
            self.battery.emit(
                {"capacity": None, "status": "not available", "plugged": None}
            )
        if self._tick % 10 == 0:
            try:
                self.synapse.emit(detect_synapse())
            except Exception:
                self.synapse.emit([])
