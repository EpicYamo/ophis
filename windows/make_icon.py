"""Render the app SVG into the Windows .ico used by PyInstaller."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    source = ROOT / "data" / "io.github.epicyamo.Ophis.svg"
    target = ROOT / "windows" / "ophis.ico"
    renderer = QSvgRenderer(str(source))
    image = QImage(256, 256, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    renderer.render(painter)
    painter.end()
    if not image.save(str(target), "ICO"):
        print(f"warning: could not write {target}; using the committed icon")
        return 0
    print(f"wrote {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
