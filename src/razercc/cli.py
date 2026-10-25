"""Command line interface: ``razercc``.

Requires write access to the hidraw control node: run it as root, or install
``data/99-razer-hidraw.rules`` so your desktop session gets access.
"""

from __future__ import annotations

import argparse
import json
import sys

from . import protocol as p
from . import sysinfo
from .backend import DeviceBackend

POWER_NAMES = {
    "balanced": p.PowerMode.BALANCED,
    "gaming": p.PowerMode.GAMING,
    "creator": p.PowerMode.CREATOR,
    "custom": p.PowerMode.CUSTOM,
}
EFFECT_NAMES = {
    "off": p.Effect.OFF,
    "static": p.Effect.STATIC,
    "breathing": p.Effect.BREATHING,
    "spectrum": p.Effect.SPECTRUM,
    "wave": p.Effect.WAVE,
    "reactive": p.Effect.REACTIVE,
    "starlight": p.Effect.STARLIGHT,
}
LOGO_NAMES = {"off": 0, "on": 1, "breathing": 2}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="razercc",
        description="Control Razer Blade 14 (2022) fan, power and lighting on Linux.",
    )
    parser.add_argument("--json", action="store_true", help="machine readable output")
    parser.add_argument(
        "--preview", action="store_true", help="use an in-memory device (no hardware)"
    )

    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("info", help="show device information and current settings")

    get_parser = sub.add_parser("get", help="read one setting")
    get_parser.add_argument(
        "setting",
        nargs="?",
        default="all",
        choices=["all", "power", "fan", "brightness", "logo", "battery"],
    )

    set_parser = sub.add_parser("set", help="change one setting")
    target = set_parser.add_subparsers(dest="target", required=True)

    power = target.add_parser("power", help="performance profile")
    power.add_argument("mode", choices=list(POWER_NAMES))

    fan = target.add_parser("fan", help="fan speed: 'auto' or 3500-5000")
    fan.add_argument("value", help="'auto' or an RPM value")

    brightness = target.add_parser("brightness", help="keyboard backlight, 0-255")
    brightness.add_argument("value", type=int)

    bho = target.add_parser("bho", help="battery charge limit")
    bho.add_argument("value", choices=["on", "off"])
    bho.add_argument("--threshold", type=int, default=80, choices=range(50, 81))

    logo = target.add_parser("logo", help="lid logo LED")
    logo.add_argument("value", choices=list(LOGO_NAMES))

    effect = target.add_parser("effect", help="keyboard lighting effect")
    effect.add_argument("value", choices=list(EFFECT_NAMES))
    effect.add_argument("--color", default=None, help="RRGGBB, used by the static effect")

    return parser


def parse_color(value: str) -> tuple[int, int, int]:
    text = value.lstrip("#")
    if len(text) != 6:
        raise ValueError("color must be six hex digits, e.g. FF8800")
    return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))


def snapshot(backend) -> dict:
    state = backend.state
    device = getattr(backend, "device", None)
    return {
        "model": device.model if device is not None else "Preview device (no hardware)",
        "connected": backend.connected,
        "power_mode": int(state.power_mode),
        "power_mode_name": p.PowerMode(state.power_mode).name.lower(),
        "cpu_boost": state.cpu_boost,
        "gpu_boost": state.gpu_boost,
        "fan_rpm": state.fan_rpm,
        "fan_auto": state.fan_rpm == 0,
        "brightness": state.brightness,
        "logo": state.logo,
        "effect": state.extra.get("effect"),
        "battery": {
            "charge_limit_enabled": state.bho_enabled,
            "charge_limit": state.bho_threshold,
            "capacity": sysinfo.battery_capacity(),
            "status": sysinfo.battery_status(),
            "ac_online": sysinfo.ac_online(),
        },
    }


def print_human(data: dict) -> None:
    print(f"Device      : {data['model']}")
    print(f"Power mode  : {data['power_mode_name']}")
    print(f"CPU boost   : {data['cpu_boost']}")
    print(f"GPU boost   : {data['gpu_boost']}")
    print(f"Fan         : {'automatic' if data['fan_auto'] else str(data['fan_rpm']) + ' RPM'}")
    print(f"Backlight   : {data['brightness']}")
    print(f"Logo LED    : {['off', 'on', 'breathing'][data['logo']] if data['logo'] in (0, 1, 2) else data['logo']}")
    battery = data["battery"]
    limit = (
        f"{battery['charge_limit']}% (enabled)"
        if battery["charge_limit_enabled"]
        else "disabled"
    )
    print(f"Charge limit: {limit}")
    if battery["capacity"] is not None:
        print(f"Battery     : {battery['capacity']}% {battery['status'] or ''}".rstrip())


def emit(data: dict, as_json: bool, human: bool = False) -> None:
    if as_json:
        print(json.dumps(data, indent=2))
    elif human:
        print_human(data)
    else:
        print("OK")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.preview:
        from .backend import MockBackend

        backend = MockBackend()
    else:
        backend = DeviceBackend()

    try:
        if not backend.connected:
            print(backend.detail or "device not available", file=sys.stderr)
            return 2

        if args.command == "info":
            emit(snapshot(backend), args.json, human=True)
            return 0

        if args.command == "get":
            data = snapshot(backend)
            if args.setting == "power":
                data = {"power_mode": data["power_mode"], "mode": data["power_mode_name"]}
            elif args.setting == "fan":
                data = {"rpm": data["fan_rpm"], "auto": data["fan_auto"]}
            elif args.setting == "brightness":
                data = {"brightness": data["brightness"]}
            elif args.setting == "logo":
                data = {"logo": data["logo"]}
            elif args.setting == "battery":
                data = data["battery"]
            emit(data, args.json, human=True)
            return 0

        if args.target == "power":
            backend.set_power_mode(POWER_NAMES[args.mode])
        elif args.target == "fan":
            if args.value == "auto":
                backend.set_fan_rpm(0)
            else:
                try:
                    backend.set_fan_rpm(int(args.value))
                except ValueError:
                    print("fan value must be 'auto' or an integer RPM", file=sys.stderr)
                    return 2
        elif args.target == "brightness":
            backend.set_brightness(args.value)
        elif args.target == "bho":
            features = getattr(getattr(backend, "device", None), "features", {"bho"})
            if "bho" not in features:
                print("this model has no charge limit support", file=sys.stderr)
                return 1
            backend.set_bho(args.value == "on", args.threshold)
        elif args.target == "logo":
            backend.set_logo(LOGO_NAMES[args.value])
        elif args.target == "effect":
            effect = EFFECT_NAMES[args.value]
            if effect == p.Effect.STATIC:
                try:
                    red, green, blue = parse_color(args.color or "FFFFFF")
                except ValueError as exc:
                    print(f"error: {exc}", file=sys.stderr)
                    return 2
                backend.set_color(red, green, blue)
            else:
                backend.set_effect(effect)

        emit(snapshot(backend), args.json)
        return 0
    except (p.RazerError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        backend.close()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
