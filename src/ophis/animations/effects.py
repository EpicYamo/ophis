"""Per-key effects, ported from Better RGB.

The maths, the parameter ranges and the defaults follow the original C
implementation so the same settings produce the same look:

    breathing   colour, speed 1-40, smoothness 2-150
    wave        angle 0-359, speed 1-20
    sparkle     speed 1-10, density 3-20 (random colours per spark)
    wheel       reverse, speed 1-20
    lightning   speed 1-10, smoothness 1-20, strike width 1-4, 1-4 strikes
    flame       flicker speed 1-10, smoothness 1-20
    rain        fall speed 1-10, density 1-5, 1-5 colours
    matrix      streak speed 1-10, four styles, density 1-5, 1-3 colours
    static      horizontal/vertical zones with one colour each

The reference runs at one frame per 10 ms. This engine runs at about 24 fps, so
every per-frame increment is multiplied by `dt / 0.010`; the effects move at the
same speed on different frame rates.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field, fields
from typing import Any

ROWS = 6
COLS = 16

Colour = tuple[int, int, int]
Matrix = list[list[Colour]]

BLACK: Colour = (0, 0, 0)
REFERENCE_STEP = 0.010  # seconds per frame in Better RGB

RAIN_PALETTE: list[Colour] = [
    (80, 140, 255),
    (120, 80, 255),
    (80, 220, 255),
    (255, 255, 255),
    (80, 255, 180),
]
MATRIX_PALETTE: list[Colour] = [(0, 255, 60), (0, 180, 255), (255, 0, 120)]
STATIC_PALETTE: list[Colour] = [
    (255, 255, 255),
    (255, 0, 0),
    (0, 255, 0),
    (0, 0, 255),
    (255, 255, 0),
    (255, 0, 255),
    (0, 255, 255),
    (255, 140, 0),
    (140, 0, 255),
    (0, 140, 140),
]


@dataclass(frozen=True)
class Setting:
    """One control in the effect panel."""

    key: str
    label: str
    kind: str = "slider"  # slider | switch | choice | colour | palette
    low: int = 0
    high: int = 0
    step: int = 1
    default: Any = 0
    choices: tuple[str, ...] = ()


@dataclass
class Params:
    colour: Colour = (0, 120, 255)
    speed: int = 5
    smooth: int = 10
    angle: int = 0
    density: int = 3
    width: int = 2
    concurrent: int = 1
    reverse: bool = False
    style: int = 0
    horizontal: bool = True
    zone_count: int = 1
    palette_count: int = 1
    palette: list[Colour] = field(default_factory=lambda: list(RAIN_PALETTE))
    zone_colours: list[Colour] = field(
        default_factory=lambda: list(STATIC_PALETTE)
    )

    def copy(self) -> "Params":
        clone = Params()
        for item in fields(Params):
            setattr(clone, item.name, getattr(self, item.name))
        clone.palette = list(self.palette)
        clone.zone_colours = list(self.zone_colours)
        return clone

    def apply(self, values: dict[str, Any]) -> None:
        for key, value in values.items():
            if hasattr(self, key):
                setattr(self, key, value)


# -- helpers ----------------------------------------------------------------
def blank() -> Matrix:
    return [[BLACK for _ in range(COLS)] for _ in range(ROWS)]


def scale(colour: Colour, factor: float) -> Colour:
    factor = max(0.0, min(1.0, factor))
    return (int(colour[0] * factor), int(colour[1] * factor), int(colour[2] * factor))


def hue_colour(degrees: float) -> Colour:
    """hsv_to_rgb from the reference: full saturation and value."""
    hue = degrees % 360.0
    if hue < 0:
        hue += 360.0
    chroma = 1.0
    x = chroma * (1 - abs((hue / 60.0) % 2 - 1))
    if hue < 60:
        red, green, blue = chroma, x, 0.0
    elif hue < 120:
        red, green, blue = x, chroma, 0.0
    elif hue < 180:
        red, green, blue = 0.0, chroma, x
    elif hue < 240:
        red, green, blue = 0.0, x, chroma
    elif hue < 300:
        red, green, blue = x, 0.0, chroma
    else:
        red, green, blue = chroma, 0.0, x
    return (int(red * 255), int(green * 255), int(blue * 255))


def fill(colour: Colour) -> Matrix:
    return [[colour for _ in range(COLS)] for _ in range(ROWS)]


def compute_prob_count(target: int, low: int, high: int) -> int:
    roll = random.randrange(100)
    if target >= high:
        return high
    if roll < 25:
        return max(low, target - 1)
    if roll < 75:
        return target
    return min(high, target + 1)


def zone_index(value: int, total: int, zones: int) -> int:
    """Split one axis into contiguous zones, as the reference does by row."""
    if zones <= 1:
        return 0
    return min(zones - 1, value * zones // total)


class Effect:
    name = ""
    label = ""
    SETTINGS: tuple[Setting, ...] = ()

    def __init__(self, params: Params | None = None) -> None:
        self.params = params or Params()
        self.elapsed = 0.0
        self.ticks = 0.0

    @property
    def animated(self) -> bool:
        return True

    def _step(self, dt: float) -> float:
        """Frames worth of movement since the last call at the reference rate."""
        return max(0.0, dt) / REFERENCE_STEP

    def render(self, dt: float) -> Matrix:  # pragma: no cover - abstract
        raise NotImplementedError


class Breathing(Effect):
    name = "breathing"
    label = "Breathing"
    SETTINGS = (
        Setting("colour", "Colour", "colour", default=(0, 120, 255)),
        Setting("speed", "Speed", "slider", 1, 40, 1, 12),
        Setting("smooth", "Smoothness", "slider", 2, 150, 1, 60),
    )

    def render(self, dt: float) -> Matrix:
        self.elapsed += (self.params.speed / 100.0) * self._step(dt)
        raw = (math.sin(self.elapsed) + 1.0) / 2.0
        levels = max(2, int(self.params.smooth))
        brightness = math.floor(raw * levels) / float(levels)
        return fill(scale(self.params.colour, brightness))


class Wave(Effect):
    name = "wave"
    label = "Wave"
    SETTINGS = (
        Setting("angle", "Angle (degrees)", "slider", 0, 359, 1, 0),
        Setting("speed", "Speed", "slider", 1, 20, 1, 4),
    )

    def render(self, dt: float) -> Matrix:
        angle = math.radians(self.params.angle)
        dir_x = math.cos(angle)
        dir_y = math.sin(angle)
        matrix = blank()
        for row in range(ROWS):
            for col in range(COLS):
                projection = col * dir_x + row * dir_y
                matrix[row][col] = hue_colour(self.elapsed + projection * 15.0)
        self.elapsed += self.params.speed * self._step(dt)
        return matrix


class Wheel(Effect):
    name = "wheel"
    label = "Wheel"
    SETTINGS = (
        Setting("reverse", "Reverse direction", "switch", default=False),
        Setting("speed", "Speed", "slider", 1, 20, 1, 4),
    )

    def __init__(self, params: Params | None = None) -> None:
        super().__init__(params)
        self.centre_x = (COLS - 1) / 2.0
        self.centre_y = (ROWS - 1) / 2.0

    def render(self, dt: float) -> Matrix:
        direction = -1.0 if self.params.reverse else 1.0
        matrix = blank()
        for row in range(ROWS):
            for col in range(COLS):
                angle = math.degrees(
                    math.atan2(row - self.centre_y, col - self.centre_x)
                )
                matrix[row][col] = hue_colour(self.elapsed * direction + angle)
        self.elapsed += self.params.speed * self._step(dt)
        return matrix


class Sparkle(Effect):
    name = "sparkle"
    label = "Sparkle"
    SETTINGS = (
        Setting("speed", "Speed", "slider", 1, 10, 1, 5),
        Setting("density", "Density (keys lit)", "slider", 3, 20, 1, 8),
    )

    def __init__(self, params: Params | None = None) -> None:
        super().__init__(params)
        self.life = [0.0] * (ROWS * COLS)
        self.max_life = [1.0] * (ROWS * COLS)
        self.colours: list[Colour] = [BLACK] * (ROWS * COLS)

    def render(self, dt: float) -> Matrix:
        step = self._step(dt)
        duration = max(8.0, 50.0 - self.params.speed * 4.0)
        target = int(self.params.density)

        alive = sum(1 for value in self.life if value > 0)
        for _ in range(max(0, target - alive)):
            for _attempt in range(20):
                index = random.randrange(len(self.life))
                if self.life[index] <= 0:
                    self.life[index] = duration
                    self.max_life[index] = duration
                    self.colours[index] = (
                        random.randrange(256),
                        random.randrange(256),
                        random.randrange(256),
                    )
                    break

        matrix = blank()
        for index, life in enumerate(self.life):
            if life <= 0:
                continue
            fade = life / self.max_life[index]
            row, col = divmod(index, COLS)
            matrix[row][col] = scale(self.colours[index], fade)
            self.life[index] = max(0.0, life - step)
        return matrix


class Lightning(Effect):
    name = "lightning"
    label = "Lightning"
    SETTINGS = (
        Setting("speed", "Speed", "slider", 1, 10, 1, 5),
        Setting("smooth", "Smoothness", "slider", 1, 20, 1, 10),
        Setting("width", "Strike width", "slider", 1, 4, 1, 2),
        Setting("concurrent", "Concurrent strikes", "slider", 1, 4, 1, 1),
    )
    MAX_STRIKES = 4

    def __init__(self, params: Params | None = None) -> None:
        super().__init__(params)
        self.head = [150.0] * self.MAX_STRIKES
        self.bolt_x = [COLS / 2.0] * self.MAX_STRIKES
        self.countdown = [10 + random.randrange(30) for _ in range(self.MAX_STRIKES)]

    def render(self, dt: float) -> Matrix:
        step = self._step(dt)
        speed = 0.05 + self.params.speed * 0.08
        band = 0.4 + self.params.smooth * 0.15
        tail = band * 2.5
        finish = ROWS + tail + 0.5
        x_width = 0.35 + (self.params.width - 1) * 0.383
        concurrent = max(1, min(self.MAX_STRIKES, int(self.params.concurrent)))

        brightness = [0.0] * (ROWS * COLS)
        for index in range(concurrent):
            if self.head[index] > finish:
                self.countdown[index] -= step
                if self.countdown[index] <= 0:
                    self.head[index] = -2.0
                    self.bolt_x[index] = float(random.randrange(COLS))
                    self.countdown[index] = 20 + random.randrange(40)
            if self.head[index] > finish:
                continue
            for row in range(ROWS):
                delta_v = self.head[index] - row
                if delta_v < -0.3 or delta_v > tail:
                    continue
                for col in range(COLS):
                    delta_h = abs(col - self.bolt_x[index])
                    if delta_h > x_width:
                        continue
                    vertical = 1.0 if delta_v < 0 else 1.0 - delta_v / tail
                    horizontal = 1.0 - delta_h / x_width
                    value = max(0.0, vertical) * max(0.0, horizontal)
                    position = row * COLS + col
                    if value > brightness[position]:
                        brightness[position] = value
            self.head[index] += speed * step

        matrix = blank()
        for row in range(ROWS):
            for col in range(COLS):
                value = brightness[row * COLS + col]
                if value > 0:
                    level = int(value * 255)
                    matrix[row][col] = (level, level, 255)
                else:
                    matrix[row][col] = (4, 4, 14)
        return matrix


class Flame(Effect):
    name = "flame"
    label = "Flame"
    SETTINGS = (
        Setting("speed", "Flicker speed", "slider", 1, 10, 1, 5),
        Setting("smooth", "Smoothness", "slider", 1, 20, 1, 8),
    )

    def __init__(self, params: Params | None = None) -> None:
        super().__init__(params)
        self.heat = [
            100.0 + random.randrange(60) for _ in range(ROWS * COLS)
        ]
        self.frame_counter = 0.0

    def render(self, dt: float) -> Matrix:
        step = self._step(dt)
        alpha = 1.0 / (1.0 + self.params.smooth * 0.6)
        volatility = 40.0 + self.params.speed * 18.0
        interval = max(1, 11 - int(self.params.speed))
        self.frame_counter += step
        if self.frame_counter >= interval:
            self.frame_counter -= interval
            for row in range(ROWS):
                bias = 40.0 * row / 6.0
                for col in range(COLS):
                    index = row * COLS + col
                    target = 90.0 + bias + (
                        random.random() * volatility - volatility / 2.0
                    )
                    value = self.heat[index] * (1.0 - alpha) + target * alpha
                    self.heat[index] = max(0.0, min(255.0, value))

        matrix = blank()
        for row in range(ROWS):
            for col in range(COLS):
                heat = int(self.heat[row * COLS + col])
                if heat < 85:
                    colour = (heat * 3, 0, 0)
                elif heat < 170:
                    colour = (255, (heat - 85) * 3, 0)
                else:
                    colour = (255, 255, (heat - 170) * 3)
                matrix[row][col] = colour
        return matrix


class Rain(Effect):
    name = "rain"
    label = "Rain"
    SETTINGS = (
        Setting("speed", "Fall speed", "slider", 1, 10, 1, 5),
        Setting("density", "Density (drops)", "slider", 1, 5, 1, 3),
        Setting("palette", "Colours", "palette", 1, 5, 1, 1, RAIN_PALETTE),
    )
    MAX_DROPS = 20

    def __init__(self, params: Params | None = None) -> None:
        super().__init__(params)
        self.drop_x = [float(random.randrange(COLS)) for _ in range(self.MAX_DROPS)]
        self.drop_row = [-float(random.randrange(8)) for _ in range(self.MAX_DROPS)]
        self.colour_index = [random.randrange(5) for _ in range(self.MAX_DROPS)]

    def render(self, dt: float) -> Matrix:
        step = self._step(dt)
        speed = 0.05 + self.params.speed * 0.03
        colour_count = max(1, min(5, self.params.palette_count))
        density = max(1, min(5, int(self.params.density)))
        active = min(self.MAX_DROPS, density * 3)

        matrix = blank()
        for index in range(active):
            colour = self.params.palette[self.colour_index[index] % colour_count]
            for trail in range(ROWS + 1):
                distance = self.drop_row[index] - trail
                if distance < -0.3 or distance > 1.8:
                    continue
                brightness = 1.0 if distance < 0 else 1.0 - distance / 1.8
                col = int(round(self.drop_x[index]))
                if not 0 <= col < COLS:
                    continue
                row = trail
                if 0 <= row < ROWS:
                    existing = matrix[row][col]
                    candidate = scale(colour, brightness)
                    if sum(candidate) > sum(existing):
                        matrix[row][col] = candidate
            self.drop_row[index] += speed * step
            if self.drop_row[index] > ROWS + 2:
                self.drop_row[index] = -float(random.randrange(5))
                self.drop_x[index] = float(random.randrange(COLS))
                self.colour_index[index] = random.randrange(colour_count)
        return matrix


class MatrixRain(Effect):
    name = "matrix"
    label = "Matrix"
    SETTINGS = (
        Setting("speed", "Streak speed", "slider", 1, 10, 1, 5),
        Setting(
            "style",
            "Style",
            "choice",
            0,
            3,
            1,
            0,
            ("Diagonal streaks", "Vertical columns", "Laser sweep", "Ripple"),
        ),
        Setting("density", "Density", "slider", 1, 5, 1, 2),
        Setting("palette", "Colours", "palette", 1, 3, 1, 1, MATRIX_PALETTE),
    )
    STREAKS = 5
    LASERS = 3
    RIPPLES = 3

    def __init__(self, params: Params | None = None) -> None:
        super().__init__(params)
        self.angle = [math.radians(random.randrange(360)) for _ in range(self.STREAKS)]
        self.position = [-20.0 - index * 6.0 for index in range(self.STREAKS)]
        self.streak_speed = [0.2 + random.randrange(100) / 100.0 for _ in range(self.STREAKS)]
        self.streak_colour = [random.randrange(3) for _ in range(self.STREAKS)]

        self.col_position = [-float(random.randrange(8)) for _ in range(COLS)]
        self.col_speed = [0.05 + random.randrange(100) / 300.0 for _ in range(COLS)]
        self.col_colour = [random.randrange(3) for _ in range(COLS)]

        self.laser_angle = [
            random.randrange(4) * (math.pi / 2) for _ in range(self.LASERS)
        ]
        self.laser_position = [-20.0 - index * 8.0 for index in range(self.LASERS)]
        self.laser_speed = [0.6 + random.randrange(100) / 100.0 for _ in range(self.LASERS)]
        self.laser_colour = [random.randrange(3) for _ in range(self.LASERS)]

        self.ripple_x = [float(random.randrange(COLS)) for _ in range(self.RIPPLES)]
        self.ripple_y = [float(random.randrange(ROWS)) for _ in range(self.RIPPLES)]
        self.ripple_radius = [index * 8.0 for index in range(self.RIPPLES)]
        self.ripple_colour = [random.randrange(3) for _ in range(self.RIPPLES)]

        self.reroll = 0.0
        self.active_streaks = 2

    def render(self, dt: float) -> Matrix:
        step = self._step(dt)
        colour_count = max(1, min(3, self.params.palette_count))
        style = int(self.params.style)
        speed_mul = 0.3 + self.params.speed * 0.15
        matrix = blank()

        def paint(row: int, col: int, colour_index: int, brightness: float) -> None:
            colour = self.params.palette[colour_index % colour_count]
            matrix[row][col] = scale(colour, brightness)

        if style == 0:
            self.reroll += step
            if self.reroll >= 60:
                self.active_streaks = compute_prob_count(
                    int(self.params.density), 1, 5
                )
                self.reroll = 0
            for row in range(ROWS):
                for col in range(COLS):
                    best, best_colour = 0.0, 0
                    for index in range(self.active_streaks):
                        dir_x, dir_y = math.cos(self.angle[index]), math.sin(self.angle[index])
                        projection = col * dir_x + row * dir_y
                        distance = abs(projection - self.position[index])
                        if distance < 1.5:
                            value = 1.0 - distance / 1.5
                            if value > best:
                                best, best_colour = value, self.streak_colour[index]
                    paint(row, col, best_colour, min(1.0, best))
            for index in range(self.active_streaks):
                self.position[index] += self.streak_speed[index] * speed_mul * step
                if self.position[index] > 24:
                    self.position[index] = -24.0
                    self.angle[index] = math.radians(random.randrange(360))
                    self.streak_speed[index] = 0.2 + random.randrange(100) / 100.0
                    self.streak_colour[index] = random.randrange(colour_count)

        elif style == 1:
            for row in range(ROWS):
                for col in range(COLS):
                    delta = self.col_position[col] - row
                    brightness = 0.0
                    if -0.3 <= delta < 4.0:
                        brightness = 1.0 if delta < 0 else 1.0 - delta / 4.0
                    paint(row, col, self.col_colour[col], max(0.0, brightness))
            for col in range(COLS):
                self.col_position[col] += self.col_speed[col] * speed_mul * step
                if self.col_position[col] > ROWS + 2:
                    self.col_position[col] = -float(random.randrange(6))
                    self.col_speed[col] = 0.05 + random.randrange(100) / 300.0
                    self.col_colour[col] = random.randrange(colour_count)

        elif style == 2:
            laser_count = 3 if self.params.density >= 4 else 2
            for row in range(ROWS):
                for col in range(COLS):
                    best, best_colour = 0.0, 0
                    for index in range(laser_count):
                        dir_x = math.cos(self.laser_angle[index])
                        dir_y = math.sin(self.laser_angle[index])
                        projection = col * dir_x + row * dir_y
                        distance = abs(projection - self.laser_position[index])
                        if distance < 0.6:
                            value = 1.0 - distance / 0.6
                            if value > best:
                                best, best_colour = value, self.laser_colour[index]
                    paint(row, col, best_colour, min(1.0, best))
            for index in range(laser_count):
                self.laser_position[index] += self.laser_speed[index] * speed_mul * 1.5 * step
                if self.laser_position[index] > 24:
                    self.laser_position[index] = -24.0 - random.randrange(20)
                    self.laser_angle[index] = random.randrange(4) * (math.pi / 2)
                    self.laser_speed[index] = 0.6 + random.randrange(100) / 100.0
                    self.laser_colour[index] = random.randrange(colour_count)

        else:
            for row in range(ROWS):
                for col in range(COLS):
                    best, best_colour = 0.0, 0
                    for index in range(self.RIPPLES):
                        distance = math.hypot(
                            col - self.ripple_x[index], row - self.ripple_y[index]
                        )
                        ring = abs(distance - self.ripple_radius[index])
                        if ring < 1.2:
                            value = 1.0 - ring / 1.2
                            if value > best:
                                best, best_colour = value, self.ripple_colour[index]
                    paint(row, col, best_colour, min(1.0, best))
            for index in range(self.RIPPLES):
                self.ripple_radius[index] += speed_mul * 0.25 * step
                if self.ripple_radius[index] > 20:
                    self.ripple_x[index] = float(random.randrange(COLS))
                    self.ripple_y[index] = float(random.randrange(ROWS))
                    self.ripple_radius[index] = 0.0
                    self.ripple_colour[index] = random.randrange(colour_count)

        return matrix


class Static(Effect):
    name = "static"
    label = "Static"
    SETTINGS = (
        Setting(
            "horizontal",
            "Layout",
            "choice",
            0,
            1,
            1,
            0,
            ("Horizontal zones", "Vertical zones"),
        ),
        Setting("zone_count", "Zone count", "slider", 1, 6, 1, 1),
        Setting("zone_colours", "Zone colours", "zone_colours", 1, 6, 1, 1, STATIC_PALETTE),
    )

    def __init__(self, params: Params | None = None) -> None:
        super().__init__(params)

    @property
    def animated(self) -> bool:
        return False

    def render(self, dt: float) -> Matrix:
        zones = max(1, int(self.params.zone_count))
        matrix = blank()
        for row in range(ROWS):
            for col in range(COLS):
                if self.params.horizontal:
                    zone = zone_index(row, ROWS, min(zones, ROWS))
                else:
                    zone = zone_index(col, COLS, min(zones, COLS))
                matrix[row][col] = self.params.zone_colours[
                    zone % len(self.params.zone_colours)
                ]
        return matrix


EFFECTS: dict[str, type[Effect]] = {
    "breathing": Breathing,
    "wave": Wave,
    "wheel": Wheel,
    "sparkle": Sparkle,
    "lightning": Lightning,
    "flame": Flame,
    "rain": Rain,
    "matrix": MatrixRain,
    "static": Static,
}

ANIMATIONS = [name for name, effect in EFFECTS.items() if effect.animated]


def create(name: str, params: Params | None = None) -> Effect:
    try:
        return EFFECTS[name](params)
    except KeyError:
        raise ValueError(f"unknown animation: {name}") from None


def default_params(name: str) -> Params:
    """Params pre-filled with the reference defaults for one effect."""
    params = Params()
    effect_class = EFFECTS[name]
    for setting in effect_class.SETTINGS:
        if setting.kind == "slider":
            setattr(params, setting.key, setting.default)
        elif setting.kind in ("switch",):
            setattr(params, setting.key, bool(setting.default))
        elif setting.kind == "choice":
            setattr(params, setting.key, int(setting.default))
        elif setting.kind == "colour":
            params.colour = tuple(setting.default)  # type: ignore[assignment]
        elif setting.kind == "palette":
            params.palette = list(setting.choices)
            params.palette_count = int(setting.default)
        elif setting.kind == "zone_colours":
            params.zone_count = int(setting.default)
            params.zone_colours = list(setting.choices)
    return params
