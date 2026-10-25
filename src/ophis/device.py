"""High-level device API: turns protocol packets into meaningful operations."""

from __future__ import annotations

from dataclasses import dataclass, field

from . import protocol as p
from .transport import Transport

# Features known to be present on the tested model.
DEFAULT_FEATURES = {"logo", "boost", "bho"}


@dataclass
class DeviceState:
    """Last known values. The device is the source of truth after a refresh."""

    power_mode: int = p.PowerMode.BALANCED
    cpu_boost: int = 2
    gpu_boost: int = 2
    fan_rpm: int = 0  # 0 = automatic
    brightness: int = 100
    logo: int = 1
    bho_enabled: bool = False
    bho_threshold: int = 80
    extra: dict = field(default_factory=dict)


class RazerDevice:
    """Read/write operations for the Razer Blade 14 (2022), USB 1532:028C."""

    def __init__(
        self,
        transport: Transport,
        model: str = "Blade 14 (2022) - RZ09-0427",
        features: set[str] | None = None,
        fan_range: tuple[int, int] = (3500, 5000),
    ):
        self.transport = transport
        self.model = model
        self.features = features if features is not None else set(DEFAULT_FEATURES)
        self.fan_range = fan_range
        self.state = DeviceState()

    # -- low level ---------------------------------------------------------
    def _call(
        self, command_class: int, command_id: int, data_size: int, args: bytes = b""
    ) -> p.Packet:
        request = p.Packet.request(command_class, command_id, data_size, args)
        return self.transport.transact(request)

    def _require(self, feature: str) -> None:
        if feature not in self.features:
            raise p.NotSupported(f"this model does not expose the '{feature}' feature")

    # -- power / performance -----------------------------------------------
    def get_power_state(self, zone: int = 1) -> tuple[int, bool]:
        """Return (mode, manual_fan) as the device reports them."""
        reply = self._call(
            p.Class.POWER, p.Cmd.POWER_GET_MODE, 0x04, bytes([0x00, zone, 0x00, 0x00])
        )
        return reply.arguments[2], bool(reply.arguments[3])

    def get_power_mode(self, zone: int = 1) -> int:
        return self.get_power_state(zone)[0]

    def get_fan_target(self, zone: int = 1) -> int:
        """Fan setpoint in RPM; 0 means the firmware is in charge."""
        reply = self._call(
            p.Class.POWER, p.Cmd.FAN_GET_RPM, 0x03, bytes([0x00, zone, 0x00])
        )
        return reply.arguments[2] * 100

    def get_boost(self, which: int = 1) -> int:
        """`which`: 1 = CPU, 2 = GPU."""
        reply = self._call(p.Class.POWER, p.Cmd.BOOST_GET, 0x03, bytes([0x00, which, 0x00]))
        return reply.arguments[2]

    def _set_boost(self, which: int, level: int) -> None:
        level = max(0, min(3, level))
        if level == 3:
            self._require("boost")
        self._call(p.Class.POWER, p.Cmd.BOOST_SET, 0x03, bytes([0x00, which, level]))

    def _set_power_zone(self, zone: int, mode: int, manual_fan: bool) -> None:
        self._call(
            p.Class.POWER,
            p.Cmd.POWER_SET_MODE,
            0x04,
            bytes([0x00, zone, mode, int(manual_fan)]),
        )

    def set_power_mode(
        self, mode: int, cpu_boost: int | None = None, gpu_boost: int | None = None
    ) -> None:
        """0 = balanced, 1 = gaming, 2 = creator, 4 = custom.

        Manual fan speed only takes effect in custom mode on this model, so
        leaving custom hands the fans back to the firmware.
        """
        mode = int(mode)
        if mode not in (0, 1, 2, 4):
            raise ValueError(f"invalid power mode: {mode}")
        manual = mode == p.PowerMode.CUSTOM and self.state.fan_rpm > 0

        for zone in (1, 2):
            self._set_power_zone(zone, mode, manual)
        self.state.power_mode = mode

        if mode != p.PowerMode.CUSTOM:
            self.state.fan_rpm = 0
            return

        cpu_boost = self.state.cpu_boost if cpu_boost is None else cpu_boost
        gpu_boost = self.state.gpu_boost if gpu_boost is None else gpu_boost
        self._set_boost(1, cpu_boost)
        self._set_boost(2, gpu_boost)
        self.state.cpu_boost = cpu_boost
        self.state.gpu_boost = gpu_boost

    # -- fan ---------------------------------------------------------------
    def set_fan_rpm(self, rpm: int) -> None:
        """0 = automatic, otherwise 3500-5000 RPM.

        A fixed speed requires custom mode: with balanced or gaming the EC
        stores the value but keeps its own fan curve, so the switch is made
        here. Both zones get the mode write first, then the setpoint.
        """
        manual = rpm > 0
        mode = self.state.power_mode
        if manual and mode != p.PowerMode.CUSTOM:
            mode = p.PowerMode.CUSTOM

        for zone in (1, 2):
            self._set_power_zone(zone, mode, manual)

        if not manual:
            self.state.fan_rpm = 0
            self.state.power_mode = mode
            return

        units = p.fan_to_raw(rpm, *self.fan_range)
        for zone in (1, 2):
            self._call(p.Class.POWER, p.Cmd.FAN_SET_RPM, 0x03, bytes([0x00, zone, units]))

        if mode == p.PowerMode.CUSTOM and int(self.state.power_mode) != int(mode):
            # Entering custom mode from another profile also needs the boosts.
            self._set_boost(1, self.state.cpu_boost)
            self._set_boost(2, self.state.gpu_boost)

        self.state.power_mode = mode
        self.state.fan_rpm = units * 100

    # -- battery -----------------------------------------------------------
    def get_bho(self) -> tuple[bool, int]:
        self._require("bho")
        reply = self._call(p.Class.BATTERY, p.Cmd.BHO_GET, 0x01, bytes([0x00]))
        return p.decode_bho(reply.arguments[0])

    def set_bho(self, enabled: bool, threshold: int) -> None:
        self._require("bho")
        raw = p.encode_bho(enabled, threshold)
        self._call(p.Class.BATTERY, p.Cmd.BHO_SET, 0x01, bytes([raw]))
        self.state.bho_enabled = enabled
        self.state.bho_threshold = threshold

    # -- keyboard / RGB ----------------------------------------------------
    def get_brightness(self) -> int:
        reply = self._call(
            p.Class.LED,
            p.Cmd.LED_GET_BRIGHTNESS,
            0x03,
            bytes([p.VARSTORE, p.BACKLIGHT_LED, 0x00]),
        )
        return reply.arguments[2]

    def set_brightness(self, value: int) -> None:
        value = max(0, min(255, int(value)))
        self._call(
            p.Class.LED,
            p.Cmd.LED_SET_BRIGHTNESS,
            0x03,
            bytes([p.VARSTORE, p.BACKLIGHT_LED, value]),
        )
        self.state.brightness = value

    def _logo_call(self, command_id: int, args: bytes) -> p.Packet:
        """Logo LED commands use transaction id 0xFF, not the usual 0x1F."""
        request = p.Packet(
            command_class=p.Class.LED,
            command_id=command_id,
            data_size=len(args),
            arguments=args,
            transaction_id=p.LOGO_TRANSACTION_ID,
        )
        reply = self.transport.transact(request)
        reply.check(request)
        return reply

    def get_logo(self) -> int:
        """0 = off, 1 = on. The EC reports breathing as on."""
        self._require("logo")
        reply = self._logo_call(
            p.Cmd.LED_GET_STATE, bytes([p.VARSTORE, p.LOGO_LED, 0x00])
        )
        return reply.arguments[2]

    def set_logo(self, mode: int) -> None:
        """0 = off, 1 = on, 2 = breathing."""
        self._require("logo")
        mode = max(0, min(2, int(mode)))
        if mode == 0:
            self._logo_call(
                p.Cmd.LED_SET_EFFECT, bytes([p.VARSTORE, p.LOGO_LED, 0x00])
            )
        else:
            # The LED only comes on when its own brightness is not zero.
            self._logo_call(
                p.Cmd.LED_SET_BRIGHTNESS, bytes([p.VARSTORE, p.LOGO_LED, 0xFF])
            )
            command = p.Cmd.LED_SET_EFFECT if mode == 1 else p.Cmd.LED_SET_LOGO_EFFECT
            self._logo_call(
                command,
                bytes([p.VARSTORE, p.LOGO_LED, 0x01 if mode == 1 else 0x02]),
            )
        self.state.logo = mode

    def set_effect(
        self,
        effect: int,
        colour: tuple[int, int, int] | None = None,
        speed: int = 2,
        direction: int = 1,
    ) -> None:
        """Apply a keyboard effect with the parameters that effect needs.

        The EC wants the real argument count in `data_size`; a full 80-byte
        payload is accepted too, but there is no reason to send it.
        """
        effect = int(effect)
        red, green, blue = colour or (255, 255, 255)
        speed = max(1, min(4, int(speed)))

        if effect == p.Effect.STATIC:
            args = [p.Effect.STATIC, red, green, blue]
        elif effect == p.Effect.BREATHING:
            # 0x01 = single colour, 0x03 = random
            args = [p.Effect.BREATHING, 0x01, red, green, blue]
        elif effect == p.Effect.WAVE:
            args = [p.Effect.WAVE, 1 if int(direction) == 1 else 2]
        elif effect == p.Effect.REACTIVE:
            args = [p.Effect.REACTIVE, min(speed, 4), red, green, blue]
        elif effect == p.Effect.STARLIGHT:
            args = [
                p.Effect.STARLIGHT, 0x01, min(speed, 3),
                red, green, blue, 0x00, 0x00, 0x00,
            ]
        elif effect == p.Effect.SPECTRUM:
            args = [p.Effect.SPECTRUM]
        else:
            args = [effect]

        self._call(p.Class.LED, p.Cmd.LED_SET_STANDARD_EFFECT, len(args), bytes(args))
        self.state.extra["effect"] = effect
        if effect in (p.Effect.STATIC, p.Effect.BREATHING, p.Effect.REACTIVE,
                      p.Effect.STARLIGHT):
            self.state.extra["color"] = (red, green, blue)

    # -- per-key frames ----------------------------------------------------
    def write_frame(self, rows: list[list[tuple[int, int, int]]]) -> None:
        """Paint the whole 6x16 matrix. Each row is one feature report."""
        for index, row in enumerate(rows):
            args = [0xFF, index, 0x00, 0x0F]
            for red, green, blue in row:
                args += [red, green, blue]
            self._call(
                p.Class.LED, p.Cmd.LED_SET_CUSTOM_FRAME, len(args), bytes(args)
            )

    def activate_custom_frame(self) -> None:
        """Show what was written by `write_frame`."""
        self._call(
            p.Class.LED,
            p.Cmd.LED_SET_STANDARD_EFFECT,
            2,
            bytes([p.Effect.CUSTOM_FRAME, 0x00]),
        )

    def set_static_color(self, red: int, green: int, blue: int) -> None:
        self.set_effect(p.Effect.STATIC, (red, green, blue))
