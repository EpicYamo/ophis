"""Host-driven per-key effects.

The keyboard exposes a 6x16 matrix through ``0x03/0x0B`` and can be updated
fast enough for real animation (about 24 frames per second with the full
request/response cycle). Everything here renders one frame at a time and hands
it to the device; nothing depends on the firmware's own effects.
"""

from __future__ import annotations

import colorsys
import math
import random
from dataclasses import dataclass, field

ROWS = 6
COLS = 16

Colour = tuple[int, int, int]
Matrix = list[list[Colour]]

BLACK: Colour = (0, 0, 0)


@dataclass
class Params:
    colour: Colour = (255, 255, 255)
    secondary: Colour = (0, 0, 0)
    speed: float = 1.0
    angle: float = 0.0
    density: float = 0.25
    rainbow: bool = False


def blank() -> Matrix:
    return [[BLACK for _ in range(COLS)] for _ in range(ROWS)]


def scale(colour: Colour, factor: float) -> Colour:
    factor = max(0.0, min(1.0, factor))
    return (int(colour[0] * factor), int(colour[1] * factor), int(colour[2] * factor))


def blend(first: Colour, second: Colour, amount: float) -> Colour:
    amount = max(0.0, min(1.0, amount))
    return (
        int(first[0] + (second[0] - first[0]) * amount),
        int(first[1] + (second[1] - first[1]) * amount),
        int(first[2] + (second[2] - first[2]) * amount),
    )


def hue_colour(hue: float, value: float = 1.0) -> Colour:
    red, green, blue = colorsys.hsv_to_rgb(hue % 1.0, 1.0, max(0.0, min(1.0, value)))
    return (int(red * 255), int(green * 255), int(blue * 255))


class Effect:
    """Base class: a pure function of (frame counter, seconds)."""

    name = "effect"
    animated = True

    def __init__(self, params: Params | None = None) -> None:
        self.params = params or Params()

    def render(self, frame: int, seconds: float) -> Matrix:  # pragma: no cover - abstract
        raise NotImplementedError


class Static(Effect):
    name = "static"
    animated = False

    def render(self, frame: int, seconds: float) -> Matrix:
        return [[self.params.colour for _ in range(COLS)] for _ in range(ROWS)]


class Breathing(Effect):
    name = "breathing"

    def render(self, frame: int, seconds: float) -> Matrix:
        phase = 0.5 + 0.5 * math.sin(seconds * self.params.speed * 2.0)
        value = 0.08 + 0.92 * phase
        colour = scale(self.params.colour, value)
        return [[colour for _ in range(COLS)] for _ in range(ROWS)]


class Wave(Effect):
    """A gradient band moving along `angle`, like Better RGB's wave."""

    name = "wave"

    def render(self, frame: int, seconds: float) -> Matrix:
        radians = math.radians(self.params.angle)
        dx, dy = math.cos(radians), math.sin(radians)
        # Normalise so the projection spans the whole grid regardless of angle.
        span = abs(dx) * (COLS - 1) + abs(dy) * (ROWS - 1)
        span = span or 1.0
        matrix = blank()
        for row in range(ROWS):
            for col in range(COLS):
                projection = col * dx + row * dy
                position = projection / span
                if self.params.rainbow:
                    matrix[row][col] = hue_colour(
                        position - seconds * self.params.speed * 0.15
                    )
                else:
                    phase = 0.5 + 0.5 * math.sin(
                        (position * 2.0 - seconds * self.params.speed) * math.pi
                    )
                    matrix[row][col] = blend(
                        self.params.colour, self.params.secondary, phase
                    )
        return matrix


class Wheel(Effect):
    """Radial rainbow rotating around the matrix centre."""

    name = "wheel"

    def render(self, frame: int, seconds: float) -> Matrix:
        centre_row = (ROWS - 1) / 2
        centre_col = (COLS - 1) / 2
        matrix = blank()
        for row in range(ROWS):
            for col in range(COLS):
                angle = math.atan2(row - centre_row, col - centre_col)
                distance = math.hypot(row - centre_row, col - centre_col)
                hue = angle / (2 * math.pi) + seconds * self.params.speed * 0.1
                brightness = 0.45 + 0.55 * (1.0 - min(1.0, distance / 9.0))
                matrix[row][col] = hue_colour(hue, brightness)
        return matrix


class Sparkle(Effect):
    """Random cells light up and fade out."""

    name = "sparkle"

    def __init__(self, params: Params | None = None) -> None:
        super().__init__(params)
        self.cells: dict[tuple[int, int], float] = {}

    def render(self, frame: int, seconds: float) -> Matrix:
        matrix = blank()
        wanted = max(1, int(ROWS * COLS * self.params.density))
        attempts = 0
        while len(self.cells) < wanted and attempts < 40:
            attempts += 1
            self.cells[(random.randrange(ROWS), random.randrange(COLS))] = 1.0
        for cell in list(self.cells):
            level = self.cells[cell] - 0.05 * self.params.speed
            if level <= 0:
                del self.cells[cell]
                continue
            self.cells[cell] = level
            matrix[cell[0]][cell[1]] = scale(self.params.colour, level)
        return matrix


class Rain(Effect):
    """Falling columns with a short trail."""

    name = "rain"

    def __init__(self, params: Params | None = None) -> None:
        super().__init__(params)
        self.heads = [random.uniform(-ROWS, 0) for _ in range(COLS)]

    def render(self, frame: int, seconds: float) -> Matrix:
        matrix = blank()
        for col, head in enumerate(self.heads):
            head += 0.35 * self.params.speed
            if head > ROWS + 3:
                head = -random.uniform(1, 6)
            self.heads[col] = head
            for trail in range(4):
                row = int(head) - trail
                if 0 <= row < ROWS:
                    matrix[row][col] = scale(
                        self.params.colour, 1.0 - trail * 0.22
                    )
        return matrix


class Lightning(Effect):
    """Short vertical bolts with a decaying glow."""

    name = "lightning"

    def __init__(self, params: Params | None = None) -> None:
        super().__init__(params)
        self.bolts: list[tuple[int, int, float]] = []

    def render(self, frame: int, seconds: float) -> Matrix:
        matrix = blank()
        if random.random() < 0.06 * self.params.speed:
            self.bolts.append((random.randrange(COLS), random.randrange(ROWS), 1.0))
        for bolt in list(self.bolts):
            col, row, life = bolt
            if life <= 0:
                self.bolts.remove(bolt)
                continue
            self.bolts[self.bolts.index(bolt)] = (col, row, life - 0.12)
            for offset in range(-1, 2):
                if 0 <= col + offset < COLS and 0 <= row < ROWS:
                    matrix[row][col + offset] = scale(
                        self.params.colour, max(0.0, life - abs(offset) * 0.25)
                    )
        return matrix


class MatrixRain(Effect):
    """Green code rain with a bright head, for the obvious name."""

    name = "matrix"

    def __init__(self, params: Params | None = None) -> None:
        super().__init__(params)
        self.heads = [random.uniform(-ROWS * 2, 0) for _ in range(COLS)]
        self.speeds = [random.uniform(0.25, 0.6) for _ in range(COLS)]

    def render(self, frame: int, seconds: float) -> Matrix:
        green = self.params.colour
        matrix = blank()
        for col, head in enumerate(self.heads):
            head += self.speeds[col] * self.params.speed
            if head > ROWS + 4:
                head = -random.uniform(1, 8)
            self.heads[col] = head
            for trail in range(5):
                row = int(head) - trail
                if 0 <= row < ROWS:
                    level = 1.0 - trail * 0.18
                    matrix[row][col] = (
                        (210, 255, 210) if trail == 0 else scale(green, level)
                    )
        return matrix


class Flame(Effect):
    """Warm flicker rising from the bottom row."""

    name = "flame"

    def __init__(self, params: Params | None = None) -> None:
        super().__init__(params)
        self.noise = [[random.random() for _ in range(COLS)] for _ in range(ROWS)]

    def render(self, frame: int, seconds: float) -> Matrix:
        matrix = blank()
        for row in range(ROWS):
            for col in range(COLS):
                value = self.noise[row][col]
                value += 0.12 * self.params.speed
                if value > 1.0:
                    value -= 1.0
                self.noise[row][col] = value
                height = 1.0 - row / ROWS
                intensity = max(0.0, math.sin(value * math.pi) * height)
                hue = 0.02 + 0.09 * intensity
                matrix[row][col] = hue_colour(hue, intensity)
        return matrix


EFFECTS: dict[str, type[Effect]] = {
    "static": Static,
    "breathing": Breathing,
    "wave": Wave,
    "wheel": Wheel,
    "sparkle": Sparkle,
    "rain": Rain,
    "lightning": Lightning,
    "matrix": MatrixRain,
    "flame": Flame,
}


def create(name: str, params: Params | None = None) -> Effect:
    try:
        return EFFECTS[name](params)
    except KeyError:
        raise ValueError(f"unknown animation: {name}") from None


ANIMATIONS = [name for name, effect in EFFECTS.items() if effect.animated]
