"""Host animation loop for the Qt application.

The effect classes are shared with the GTK app; only the clock changes. The
controller is written once per frame, so all writes stay on the GUI thread and
the same transaction discipline as the rest of the app applies.
"""

from __future__ import annotations

import time

from PySide6.QtCore import QObject, Qt, QTimer, Signal

from .. import protocol as p
from ..animations import effects

FRAME_INTERVAL_MS = 40  # ~24 fps, the measured ceiling of the request/response cycle
SLOW_FRAME_MS = 140


class QtAnimationEngine(QObject):
    frameReady = Signal(object)

    def __init__(self, backend) -> None:
        super().__init__()
        self.backend = backend
        self.effect = None
        self.last_error: str | None = None
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.timeout.connect(self._tick)
        self._last_tick = 0.0
        self._slow = 0

    @property
    def device(self):
        # Look this up every time: a reconnect replaces backend.device.
        return getattr(self.backend, "device", None)

    @property
    def running(self) -> bool:
        return self._timer.isActive()

    def start(self, name: str, params: effects.Params | None = None) -> None:
        self.stop()
        self.effect = effects.create(name, (params or effects.Params()).copy())
        self.last_error = None
        self._slow = 0
        self._last_tick = time.monotonic()
        if self.effect.animated:
            self._activate_custom()
            self._timer.start(FRAME_INTERVAL_MS)
        else:
            self._render_once()

    def stop(self) -> None:
        if self._timer.isActive():
            self._timer.stop()
        self.effect = None

    def update_params(self, params: effects.Params) -> None:
        if self.effect is not None:
            self.effect.params.apply({key: value for key, value in vars(params).items()})

    # -- internals ----------------------------------------------------------
    def _activate_custom(self) -> None:
        if self.device is None:
            return
        try:
            self.device.activate_custom_frame()
        except (OSError, p.RazerError) as exc:
            self.last_error = str(exc)

    def _write(self, matrix) -> bool:
        if self.device is None:
            return True
        try:
            self.device.write_frame(matrix)
            return True
        except (OSError, p.RazerError) as exc:
            self.last_error = str(exc)
            return False

    def _render_once(self) -> None:
        if self.effect is None:
            return
        matrix = self.effect.render(0.0)
        if self._write(matrix):
            self.frameReady.emit(matrix)
        else:
            self._fallback()

    def _tick(self) -> None:
        if self.effect is None:
            self._timer.stop()
            return
        now = time.monotonic()
        dt = min(0.2, now - self._last_tick)
        self._last_tick = now
        matrix = self.effect.render(dt)
        started = time.monotonic()
        written = self._write(matrix)
        write_ms = (time.monotonic() - started) * 1000
        if not written:
            self._timer.stop()
            self._fallback()
            return
        self.frameReady.emit(matrix)
        self._slow = self._slow + 1 if write_ms > SLOW_FRAME_MS else 0
        if self._slow >= 10:
            self.last_error = "animation stopped: the controller is not keeping up"
            self._timer.stop()
            self._fallback()

    def _fallback(self) -> None:
        if self.device is None:
            return
        try:
            self.device.set_effect(p.Effect.STATIC, (255, 255, 255))
        except (OSError, p.RazerError):
            pass
