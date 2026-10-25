# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller recipe for Ophis on Windows.

Build from the repository root:

    python windows/make_icon.py
    python -m PyInstaller --noconfirm --clean windows/ophis.spec
"""

from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent

datas = [
    (str(ROOT / "data" / "keymap_blade14.json"), "data"),
    (str(ROOT / "data" / "io.github.epicyamo.Ophis.svg"), "data"),
    (str(ROOT / "src" / "ophis" / "windows" / "theme.qss"), "ophis/windows"),
]

icon = ROOT / "windows" / "ophis.ico"

a = Analysis(
    [str(ROOT / "windows" / "entry.py")],
    pathex=[str(ROOT / "src"), str(ROOT / "windows")],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["gi", "gi.repository", "tkinter"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe_gui = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Ophis",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(icon) if icon.is_file() else None,
)

exe_cli = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Ophis-cli",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(icon) if icon.is_file() else None,
)

coll = COLLECT(
    exe_gui,
    exe_cli,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Ophis",
)
