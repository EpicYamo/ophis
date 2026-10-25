"""PyInstaller entry point for the Windows build."""

from __future__ import annotations

from ophis.windows.app import main

if __name__ == "__main__":
    raise SystemExit(main())
