"""Saved state: one JSON file, no daemon.

The laptop's embedded controller already remembers most settings across a
reboot. This file exists so a *setup* (profile, fan speed, lighting, charge
limit) can be re-applied in one command at login, and so the tray application
knows what to restore.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from . import protocol as p

VERSION = 1

POWER_NAMES = {
    "balanced": p.PowerMode.BALANCED,
    "gaming": p.PowerMode.GAMING,
    "creator": p.PowerMode.CREATOR,
    "custom": p.PowerMode.CUSTOM,
}
POWER_IDS = {int(value): name for name, value in POWER_NAMES.items()}
EFFECT_NAMES = {
    "off": p.Effect.OFF,
    "static": p.Effect.STATIC,
    "breathing": p.Effect.BREATHING,
    "spectrum": p.Effect.SPECTRUM,
    "wave": p.Effect.WAVE,
    "reactive": p.Effect.REACTIVE,
    "starlight": p.Effect.STARLIGHT,
}
EFFECT_IDS = {int(value): name for name, value in EFFECT_NAMES.items()}

DEFAULT: dict[str, Any] = {
    "version": VERSION,
    "power": {"mode": "balanced", "cpu_boost": 1, "gpu_boost": 1},
    "fan": {"mode": "auto"},
    "lighting": {
        "effect": "static",
        "colour": [255, 255, 255],
        "speed": 2,
        "direction": 1,
        "brightness": 255,
        "logo": 0,
    },
    "battery": {"limit_enabled": False, "threshold": 80},
    "curve": {"enabled": False, "points": [[45, 3500], [70, 4200], [85, 5000]]},
    "settings": {"apply_on_start": True, "restore_on_quit": True},
}


def config_path() -> Path:
    if os.name == "nt":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "ophis" / "profile.json"
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "ophis" / "profile.json"


def _merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = value
    return result


def load(path: Path | None = None) -> dict[str, Any]:
    target = path or config_path()
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return json.loads(json.dumps(DEFAULT))
    if not isinstance(data, dict):
        return json.loads(json.dumps(DEFAULT))
    return _merge(DEFAULT, data)


def save(profile: dict[str, Any], path: Path | None = None) -> Path:
    target = path or config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(profile, indent=2) + "\n", encoding="utf-8")
    return target


def capture(backend) -> dict[str, Any]:
    """Read the current state from the device and build a profile from it."""
    state = backend.state
    profile = json.loads(json.dumps(DEFAULT))
    profile["power"] = {
        "mode": POWER_IDS.get(int(state.power_mode), "balanced"),
        "cpu_boost": int(state.cpu_boost),
        "gpu_boost": int(state.gpu_boost),
    }
    profile["fan"] = {"mode": "manual", "rpm": int(state.fan_rpm)} if state.fan_rpm else {"mode": "auto"}
    profile["lighting"].update(
        {
            "effect": EFFECT_IDS.get(state.extra.get("effect"), "static"),
            "colour": list(state.extra.get("color", (255, 255, 255))),
            "speed": int(state.extra.get("speed", 2)),
            "direction": int(state.extra.get("direction", 1)),
            "brightness": int(state.brightness),
            "logo": int(state.logo),
        }
    )
    profile["battery"] = {
        "limit_enabled": bool(state.bho_enabled),
        "threshold": int(state.bho_threshold),
    }
    return profile


def apply(backend, profile: dict[str, Any]) -> list[str]:
    """Push a profile to the device. Returns human readable warnings."""
    warnings: list[str] = []
    power = profile.get("power", {})
    fan = profile.get("fan", {})
    lighting = profile.get("lighting", {})
    battery = profile.get("battery", {})

    mode_name = str(power.get("mode", "balanced"))
    mode = POWER_NAMES.get(mode_name, p.PowerMode.BALANCED)
    manual_fan = fan.get("mode") == "manual" and mode == p.PowerMode.CUSTOM
    cpu_boost = power.get("cpu_boost")
    gpu_boost = power.get("gpu_boost")

    try:
        backend.set_power_mode(mode, cpu_boost, gpu_boost)
    except (p.RazerError, OSError) as exc:
        warnings.append(f"power mode: {exc}")

    try:
        if fan.get("mode") == "manual":
            backend.set_fan_rpm(int(fan.get("rpm", 4000)))
            if mode != p.PowerMode.CUSTOM:
                warnings.append(
                    "manual fan moves the laptop to the custom profile"
                )
        else:
            backend.set_fan_rpm(0)
    except (p.RazerError, OSError, ValueError) as exc:
        warnings.append(f"fan: {exc}")

    try:
        backend.set_brightness(int(lighting.get("brightness", 255)))
    except (p.RazerError, OSError) as exc:
        warnings.append(f"brightness: {exc}")

    effect = EFFECT_NAMES.get(str(lighting.get("effect", "static")), p.Effect.STATIC)
    colour = tuple(int(channel) for channel in lighting.get("colour", (255, 255, 255)))
    try:
        backend.set_effect(
            effect,
            colour,
            int(lighting.get("speed", 2)),
            int(lighting.get("direction", 1)),
        )
    except (p.RazerError, OSError) as exc:
        warnings.append(f"lighting: {exc}")

    try:
        backend.set_logo(int(lighting.get("logo", 0)))
    except (p.RazerError, OSError) as exc:
        warnings.append(f"logo: {exc}")

    if battery.get("limit_enabled"):
        try:
            backend.set_bho(True, int(battery.get("threshold", 80)))
        except (p.RazerError, OSError) as exc:
            warnings.append(f"charge limit: {exc}")

    if profile.get("curve", {}).get("enabled"):
        warnings.append("fan curve needs the app or tray running; skipped")

    _ = manual_fan
    return warnings


def restore_defaults(backend) -> list[str]:
    """Return the laptop to firmware defaults, keeping the charge limit.

    The charge limit is a battery-health setting rather than a cosmetic one, so
    quitting the tray must not silently start charging to 100% again.
    """
    profile = json.loads(json.dumps(DEFAULT))
    try:
        current = profile_load_for_defaults(backend)
    except Exception:
        current = None
    if current is not None:
        profile["battery"] = current
    return apply(backend, profile)


def profile_load_for_defaults(backend) -> dict[str, Any]:
    state = backend.state
    return {
        "limit_enabled": bool(state.bho_enabled),
        "threshold": int(state.bho_threshold),
    }
