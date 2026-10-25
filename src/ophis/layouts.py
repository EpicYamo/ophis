"""Physical keyboard layout and the key -> matrix-cell map.

The controller addresses LEDs as (row, column); nothing about that says which
physical key is which. Keys are identified by their X11 keycode, which is
layout independent (the German legends come from the layout, not the code), so
the map survives a language change.

``tools/mapper.py`` fills the map by lighting one cell at a time and asking the
owner to press the key that lit up.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

MAP_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "keymap_blade14.json"

ROWS = 6
COLS = 16


@dataclass(frozen=True)
class Key:
    code: str  # X11 keycode as text, or "fn"
    legend: str
    row: int
    x: float
    width: float = 1.0
    height: float = 1.0
    y_offset: float = 0.0
    lit: bool = True  # the Blade 14 has no LED under the space bar


def _row(index: int, keys: list[tuple[str, str, float]]) -> list[Key]:
    result = []
    x = 0.0
    for code, legend, width in keys:
        result.append(Key(code, legend, index, x, width))
        x += width
    return result


# German ISO on the Blade 14 (2022). The row above QWERTZ follows the same
# 1.05-unit pitch as the function row, which is what puts ß under F11/F12.
# Tab is 1.5, Caps 1.75 and left Shift 1.25 — equal to left Ctrl — so the row
# below Tab starts a little left of the one below Caps.
LAYOUT: list[Key] = (
    _row(0, [
        ("9", "Esc", 1.05),
        ("67", "F1", 1.05), ("68", "F2", 1.05), ("69", "F3", 1.05), ("70", "F4", 1.05),
        ("71", "F5", 1.05), ("72", "F6", 1.05), ("73", "F7", 1.05), ("74", "F8", 1.05),
        ("75", "F9", 1.05), ("76", "F10", 1.05), ("95", "F11", 1.05), ("96", "F12", 1.05),
        ("107", "Del", 1.05), ("power", "⏻", 1.05),
    ])
    + _row(1, [
        ("49", "^", 1.05),
        ("10", "1", 1.05), ("11", "2", 1.05), ("12", "3", 1.05), ("13", "4", 1.05),
        ("14", "5", 1.05), ("15", "6", 1.05), ("16", "7", 1.05), ("17", "8", 1.05),
        ("18", "9", 1.05), ("19", "0", 1.05), ("20", "ß", 1.05), ("21", "´", 1.05),
        ("22", "⌫", 2.1),
    ])
    + _row(2, [
        ("23", "Tab", 1.5),
        ("24", "Q", 1.0), ("25", "W", 1.0), ("26", "E", 1.0), ("27", "R", 1.0),
        ("28", "T", 1.0), ("29", "Z", 1.0), ("30", "U", 1.0), ("31", "I", 1.0),
        ("32", "O", 1.0), ("33", "P", 1.0), ("34", "Ü", 1.0), ("35", "+", 1.0),
        ("36", "Enter", 2.25),
    ])
    + _row(3, [
        ("66", "Caps", 1.75),
        ("38", "A", 1.0), ("39", "S", 1.0), ("40", "D", 1.0), ("41", "F", 1.0),
        ("42", "G", 1.0), ("43", "H", 1.0), ("44", "J", 1.0), ("45", "K", 1.0),
        ("46", "L", 1.0), ("47", "Ö", 1.0), ("48", "Ä", 1.0), ("51", "#", 1.0),
    ])
    + _row(4, [
        ("50", "Shift", 1.25),
        ("94", "<", 1.0),
        ("52", "Y", 1.0), ("53", "X", 1.0), ("54", "C", 1.0), ("55", "V", 1.0),
        ("56", "B", 1.0), ("57", "N", 1.0), ("58", "M", 1.0), ("59", ",", 1.0),
        ("60", ".", 1.0), ("61", "-", 1.0),
        ("62", "Shift", 3.5),
    ])
    + _row(5, [
        ("37", "Ctrl", 1.25),
        ("fn", "Fn", 1.0),
        ("133", "Win", 1.0),
        ("64", "Alt", 1.25),
        ("65", "", 6.0),
        ("108", "AltGr", 1.0),
        ("105", "Ctrl", 1.25),
        ("113", "←", 1.0),
        ("111", "↑", 1.0),
        ("114", "→", 1.0),
    ])
)

# The function row is slightly shorter than the letter rows, as on the laptop.
LAYOUT = [
    Key(key.code, key.legend, key.row, key.x, key.width,
        0.88 if key.row == 0 else key.height,
        0.06 if key.row == 0 else key.y_offset, key.lit)
    for key in LAYOUT
]

# Tall Enter: the lower half belongs to row 3 (the renderer notches it).
LAYOUT = [
    Key(key.code, key.legend, key.row, key.x, key.width,
        2.0 if key.code == "36" else key.height, key.y_offset, key.lit)
    for key in LAYOUT
]

# Up and down share one footprint.
_UP = next(key for key in LAYOUT if key.code == "111")
LAYOUT = [
    Key(key.code, key.legend, key.row, key.x, key.width,
        0.5 if key.code == "111" else key.height, key.y_offset, key.lit)
    for key in LAYOUT
]
LAYOUT.append(Key("116", "↓", _UP.row, _UP.x, _UP.width, 0.5, 0.5))

# No LED under the space bar, and the power button is not part of the matrix.
LAYOUT = [
    Key(key.code, key.legend, key.row, key.x, key.width, key.height, key.y_offset,
        False if key.code in ("65", "power") else key.lit)
    for key in LAYOUT
]

def key_rect(key: Key, unit: float, origin_x: float, origin_y: float):
    """Pixel rectangle of a key, including the inset that makes the gaps."""
    return (
        origin_x + key.x * unit + 1.5,
        origin_y + (key.row + key.y_offset) * unit + 1.5,
        key.width * unit - 3.0,
        key.height * unit - 3.0,
    )


def notch_rect(key: Key, unit: float, origin_x: float, origin_y: float):
    """The cut-out in the bottom-left of a tall ISO Enter, or None."""
    if key.code != "36":
        return None
    return (
        origin_x + key.x * unit + 1.5,
        origin_y + (key.row + 1.0) * unit + 1.5,
        0.25 * unit,
        unit - 3.0,
    )


KEYS_BY_CODE = {key.code: key for key in LAYOUT}
WIDTH_UNITS = max(key.x + key.width for key in LAYOUT)


def load_cells(path: Path | None = None) -> dict[str, list[int]]:
    """Return key code -> [row, column]. Missing or broken files mean no map."""
    target = path or MAP_PATH
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    cells = data.get("cells", {})
    result: dict[str, list[int]] = {}
    for code, cell in cells.items():
        if (
            code in KEYS_BY_CODE
            and isinstance(cell, list)
            and len(cell) == 2
            and 0 <= cell[0] < ROWS
            and 0 <= cell[1] < COLS
        ):
            result[code] = [int(cell[0]), int(cell[1])]
    return result


def load_unused(path: Path | None = None) -> list[list[int]]:
    target = path or MAP_PATH
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    unused = data.get("unused", [])
    return [
        [int(cell[0]), int(cell[1])]
        for cell in unused
        if isinstance(cell, list)
        and len(cell) == 2
        and 0 <= cell[0] < ROWS
        and 0 <= cell[1] < COLS
    ]


def save_cells(
    cells: dict[str, list[int]],
    unused: list[list[int]] | None = None,
    path: Path | None = None,
) -> Path:
    target = path or MAP_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 2,
        "model": "RZ09-0427",
        "layout": "de",
        "cells": cells,
        "unused": sorted(unused or []),
    }
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target


def cell_lookup(cells: dict[str, list[int]]) -> dict[tuple[int, int], str]:
    return {(cell[0], cell[1]): code for code, cell in cells.items()}
