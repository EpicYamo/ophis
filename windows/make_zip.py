"""Create the portable zip with forward-slash entries.

PowerShell's Compress-Archive writes backslash separators on Windows, which
some extraction tools treat as literal characters. Python's zipfile writes the
portable form everywhere.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "dist" / "Ophis"
TARGET = ROOT / "dist" / "Ophis-windows.zip"


def main() -> int:
    if not SOURCE.is_dir():
        raise SystemExit(f"missing build output: {SOURCE}")
    if TARGET.exists():
        TARGET.unlink()
    with zipfile.ZipFile(TARGET, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(SOURCE.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(SOURCE).as_posix())
    print(f"wrote {TARGET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
