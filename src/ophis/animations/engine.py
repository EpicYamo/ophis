"""Frame loop for the host-driven effects."""

from __future__ import annotations

import time

import gi

gi.require_version("GLib", "2.0")
from gi.repository import GLib  # noqa: E402

from .. import protocol as p  # noqa: E402
from . import effects  # noqa: E402

FRAME_INTERVAL_MS = 40  # ~24 fps, measured ceiling with the request/response cycle
SLOW_FRAME_MS = 140  # if a frame takes longer than this, the EC is struggling


class AnimationEngine:
    """Runs one effect at a time on a GLib timeout.

    Errors never propagate into the UI: if the device stops answering, the
    animation stops and the keyboard is put back on a hardware effect.
    """

    def __init__(self, device, on_frame=None) -> None:
        self.device = device
        self.on_frame = on_frame
        self.effect = None
        self._source = 0
        self._last_tick = 0.0
        self._slow = 0
        self.last_error: str | None = None

    @property
    def running(self) -> bool:
        return self._source != 0

    def start(self, name: str, params: effects.Params | None = None) -> None:
        self.stop()
        self.effect = effects.create(name, (params or effects.Params()).copy())
        self._slow = 0
        self._last_tick = time.monotonic()
        self.last_error = None

        if self.effect.animated:
            self.device.activate_custom_frame()
            self._source = GLib.timeout_add(FRAME_INTERVAL_MS, self._tick)
        else:
            self._render_once()

    def stop(self) -> None:
        if self._source:
            GLib.source_remove(self._source)
            self._source = 0
        self.effect = None

    def update_params(self, params: effects.Params) -> None:
        if self.effect is not None:
            self.effect.params.apply(
                {key: value for key, value in vars(params).items()}
            )

    def _render_once(self) -> None:
        assert self.effect is not None
        matrix = self.effect.render(0.0)
        try:
            self.device.write_frame(matrix)
            self.device.activate_custom_frame()
        except (OSError, p.RazerError) as exc:
            self.last_error = str(exc)
            return
        if self.on_frame is not None:
            self.on_frame(matrix)

    def _tick(self) -> bool:
        assert self.effect is not None
        now = time.monotonic()
        dt = min(0.2, now - self._last_tick)
        self._last_tick = now

        matrix = self.effect.render(dt)
        try:
            self.device.write_frame(matrix)
        except (OSError, p.RazerError) as exc:
            self.last_error = str(exc)
            self._source = 0
            self._fallback()
            return False

        if self.on_frame is not None:
            self.on_frame(matrix)

        self._slow = self._slow + 1 if dt * 1000 > SLOW_FRAME_MS else 0
        if self._slow >= 10:
            self.last_error = "animation stopped: the controller is not keeping up"
            self._source = 0
            self._fallback()
            return False
        return True

    def _fallback(self) -> None:
        try:
            self.device.set_effect(p.Effect.STATIC, (255, 255, 255))
        except (OSError, p.RazerError):
            pass
