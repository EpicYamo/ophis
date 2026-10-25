"""Physical keyboard layouts for the matrix preview.

A 6x16 matrix says nothing about where the keys are. The layout here describes
the visible keyboard (German ISO on the Blade 14) and the map file ties each
key to the matrix cell the controller uses.

The map is produced by ``tools/mapper.py``: it lights one cell at a time and the
owner clicks the key that lit up.
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
    id: str
    legend: str
    row: int
    x: float
    width: float = 1.0


def _row(index: int, keys: list[tuple[str, str, float]], start: float = 0.0) -> list[Key]:
    result = []
    x = start
    for key_id, legend, width in keys:
        result.append(Key(key_id, legend, index, x, width))
        x += width
    return result


# German ISO layout: QWERTZ, umlauts, and the compact arrow cluster Razer uses
# on the 14" chassis.
LAYOUT: list[Key] = (
    _row(0, [
        ("esc", "Esc", 1.0),
        ("f1", "F1", 1.0), ("f2", "F2", 1.0), ("f3", "F3", 1.0), ("f4", "F4", 1.0),
        ("f5", "F5", 1.0), ("f6", "F6", 1.0), ("f7", "F7", 1.0), ("f8", "F8", 1.0),
        ("f9", "F9", 1.0), ("f10", "F10", 1.0), ("f11", "F11", 1.0), ("f12", "F12", 1.0),
        ("print", "PrtSc", 1.0), ("del", "Del", 1.0),
    ])
    + _row(1, [
        ("grave", "^", 1.0),
        ("1", "1", 1.0), ("2", "2", 1.0), ("3", "3", 1.0), ("4", "4", 1.0),
        ("5", "5", 1.0), ("6", "6", 1.0), ("7", "7", 1.0), ("8", "8", 1.0),
        ("9", "9", 1.0), ("0", "0", 1.0), ("ss", "ß", 1.0), ("acute", "´", 1.0),
        ("backspace", "⌫", 2.0),
    ])
    + _row(2, [
        ("tab", "Tab", 1.5),
        ("q", "Q", 1.0), ("w", "W", 1.0), ("e", "E", 1.0), ("r", "R", 1.0),
        ("t", "T", 1.0), ("z", "Z", 1.0), ("u", "U", 1.0), ("i", "I", 1.0),
        ("o", "O", 1.0), ("p", "P", 1.0), ("ue", "Ü", 1.0), ("plus", "+", 1.0),
        ("enter", "Enter", 1.5),
    ])
    + _row(3, [
        ("caps", "Caps", 1.75),
        ("a", "A", 1.0), ("s", "S", 1.0), ("d", "D", 1.0), ("f", "F", 1.0),
        ("g", "G", 1.0), ("h", "H", 1.0), ("j", "J", 1.0), ("k", "K", 1.0),
        ("l", "L", 1.0), ("oe", "Ö", 1.0), ("ae", "Ä", 1.0), ("hash", "#", 1.0),
        ("enter2", "", 0.75),
    ])
    + _row(4, [
        ("shift", "Shift", 1.75),
        ("iso", "<", 1.0),
        ("y", "Y", 1.0), ("x", "X", 1.0), ("c", "C", 1.0), ("v", "V", 1.0),
        ("b", "B", 1.0), ("n", "N", 1.0), ("m", "M", 1.0), ("comma", ",", 1.0),
        ("period", ".", 1.0), ("minus", "-", 1.0), ("shift2", "Shift", 1.75),
        ("up", "↑", 0.75),
    ])
    + _row(5, [
        ("ctrl", "Ctrl", 1.25),
        ("fn", "Fn", 1.0),
        ("win", "Win", 1.0),
        ("alt", "Alt", 1.25),
        ("space", "", 5.75),
        ("altgr", "AltGr", 1.0),
        ("menu", "≡", 1.0),
        ("ctrl2", "Ctrl", 1.25),
        ("left", "←", 0.75), ("down", "↓", 0.75), ("right", "→", 0.75),
    ])
)

KEYS_BY_ID = {key.id: key for key in LAYOUT}
WIDTH_UNITS = max(key.x + key.width for key in LAYOUT)


def load_map(path: Path | None = None) -> dict[str, list[int]]:
    """Return key id -> [row, column]. Missing or broken files mean no map."""
    target = path or MAP_PATH
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    keys = data.get("keys", {})
    result: dict[str, list[int]] = {}
    for key_id, cell in keys.items():
        if (
            key_id in KEYS_BY_ID
            and isinstance(cell, list)
            and len(cell) == 2
            and 0 <= cell[0] < ROWS
            and 0 <= cell[1] < COLS
        ):
            result[key_id] = [int(cell[0]), int(cell[1])]
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


def save_map(
    mapping: dict[str, list[int]],
    unused: list[list[int]] | None = None,
    path: Path | None = None,
) -> Path:
    target = path or MAP_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "model": "RZ09-0427",
        "layout": "de",
        "keys": mapping,
        "unused": sorted(unused or []),
    }
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target


def cell_lookup(mapping: dict[str, list[int]]) -> dict[tuple[int, int], str]:
    return {(cell[0], cell[1]): key_id for key_id, cell in mapping.items()}
