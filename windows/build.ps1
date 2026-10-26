# Build the portable Windows folder and zip it.
#
#   powershell -ExecutionPolicy Bypass -File windows/build.ps1
#
# Output:
#   dist/Ophis/Ophis.exe          (windowed app)
#   dist/Ophis/Ophis-cli.exe      (console build for --probe)
#   dist/Ophis-windows.zip

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

python windows/make_icon.py
python -m PyInstaller --noconfirm --clean windows/ophis.spec
python windows/make_zip.py

Write-Host "built $Root/dist/Ophis-windows.zip"
