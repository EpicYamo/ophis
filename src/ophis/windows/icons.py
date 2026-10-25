"""Small vector icons and asset lookup, so the Windows build needs no theme."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QByteArray, QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

_SVG = {
    "performance": """
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
          <g fill="none" stroke="{color}" stroke-width="1.8" stroke-linecap="round">
            <path d="M4 20V13"/><path d="M10 20V8"/><path d="M16 20V4"/><path d="M22 20H2"/>
          </g>
        </svg>""",
    "cooling": """
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
          <g fill="none" stroke="{color}" stroke-width="1.8" stroke-linecap="round">
            <path d="M3 8h11a3 3 0 1 0-3-3"/>
            <path d="M3 12h15a3 3 0 1 1-3 3"/>
            <path d="M3 16h9"/>
          </g>
        </svg>""",
    "lighting": """
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
          <g fill="none" stroke="{color}" stroke-width="1.8" stroke-linejoin="round">
            <rect x="2.5" y="6" width="19" height="12" rx="2"/>
            <path d="M6 10h1M9.5 10h1M13 10h1M16.5 10h1M6 14h1M9.5 14h1M13 14h1M16.5 14h1"/>
          </g>
        </svg>""",
    "battery": """
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
          <g fill="none" stroke="{color}" stroke-width="1.8" stroke-linejoin="round">
            <rect x="2.5" y="7" width="17" height="10" rx="2"/>
            <path d="M22 10v4"/>
            <path d="M5.5 10h7v4h-7z" fill="{color}" stroke="none"/>
          </g>
        </svg>""",
    "settings": """
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
          <g fill="none" stroke="{color}" stroke-width="1.8" stroke-linecap="round">
            <path d="M3 7h18M3 12h18M3 17h18"/>
            <circle cx="8" cy="7" r="2.2" fill="#141416"/>
            <circle cx="16" cy="12" r="2.2" fill="#141416"/>
            <circle cx="10" cy="17" r="2.2" fill="#141416"/>
          </g>
        </svg>""",
    "refresh": """
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
          <g fill="none" stroke="{color}" stroke-width="1.8" stroke-linecap="round">
            <path d="M20 11a8 8 0 1 0-2 6"/>
            <path d="M20 4v7h-7"/>
          </g>
        </svg>""",
}

_cache: dict[tuple[str, str, int], QIcon] = {}


def icon(name: str, color: str = "#b8b8b8", size: int = 18) -> QIcon:
    key = (name, color, size)
    cached = _cache.get(key)
    if cached is not None:
        return cached
    svg = _SVG[name].replace("{color}", color)
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    scale = 2
    pixmap = QPixmap(size * scale, size * scale)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(scale)
    result = QIcon(pixmap)
    _cache[key] = result
    return result


def asset_path(name: str) -> Path | None:
    """Find a bundled data file in a checkout, package, or frozen build."""
    here = Path(__file__).resolve()
    candidates = [
        Path(getattr(sys, "_MEIPASS", "")) / "data" / name,
        here.parent.parent / "data" / name,           # ophis/data (package layout)
        here.parent.parent.parent / "data" / name,    # src/ophis -> repo/data
        here.parent.parent.parent.parent / "data" / name,
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def app_icon() -> QIcon:
    path = asset_path("io.github.epicyamo.Ophis.svg")
    if path is not None:
        renderer = QSvgRenderer(str(path))
        for size in (32, 64, 128, 256):
            pixmap = QPixmap(size, size)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            renderer.render(painter)
            painter.end()
            if size == 32:
                result = QIcon(pixmap)
            else:
                result.addPixmap(pixmap)
        return result
    return icon("lighting", "#44d62c", 64)


def icon_size(size: int = 18) -> QSize:
    return QSize(size, size)
