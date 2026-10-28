# Ophis

A control centre for the **Razer Blade 14 (2022)**, `RZ09-0427`
(USB `1532:028C`): performance profiles, fan control and fan curves, per-key
RGB with host-rendered animations, the lid logo, and the battery charge limit —
on **Linux and Windows**.

No kernel module, no driver, no daemon, no Razer account on either platform.

Built from scratch in Python against a protocol that is not documented anywhere.
Every command in this repository was sent to a real laptop and its effect
confirmed, including the three protocol mistakes described further down.

---

## Why this project exists

Synapse does not run on Linux. On Windows it works, but only as a background
stack of services that keeps the controller busy and has no reason to run while
you are gaming. Ophis talks to the same vendor HID collection directly and needs
no service. On Windows the 91-byte control report sits in a mouse collection
that Windows owns exclusively, so Ophis shares that handle and uses feature
reports only; keep Razer's own lighting path closed.

The community projects that cover this hardware are either archived, cover only
part of it, or need an out-of-tree kernel module that fights Secure Boot:

| Project | RGB | Fan | Power | Charge limit | State |
| --- | --- | --- | --- | --- | --- |
| [OpenRazer](https://github.com/openrazer/openrazer) | yes | no | no | no | active |
| [razer-laptop-control](https://github.com/rnd-ash/razer-laptop-control) | yes | yes | yes | no | archived (2022) |
| [razer-laptop-control-no-dkms](https://github.com/Razer-Linux/razer-laptop-control-no-dkms) | yes | yes | yes | yes | maintenance |
| **Ophis** | yes | yes | yes | yes | in development |

This is not a fork and no vendor code is used. The protocol was mapped by
sending feature reports to the laptop's vendor HID interface and checking what
the hardware actually did — including the parts where a command is accepted,
acknowledged, and silently ignored.

## What it does

- **Performance profiles** — Balanced, Gaming, Creator, Custom, plus CPU and GPU
  boost levels.
- **Fan control** — automatic, a fixed 3500–5000 RPM target, or a temperature
  driven curve that runs while the app is open.
- **Temperatures** — CPU, GPU and NVMe. Linux uses `hwmon`; Windows uses NVML
  and ACPI/storage CIM classes, without installing a sensor driver.
- **Lighting** — nine host-rendered effects ported from
  [Better RGB](https://github.com/EpicYamo/Better-RGB-for-Tongfang-ITE8291):
  breathing, wave with an adjustable angle, sparkle, wheel, lightning, flame,
  rain, matrix (three styles) and zoned static, each with the same parameter
  ranges and defaults as the original. A **Device effects** page lists the
  animations the controller renders itself — off, static, breathing, spectrum,
  wave, reactive and starlight — with only the colour, speed or direction each
  one accepts. Those run without CPU cost, and reactive works without input
  permissions because the keyboard handles it.
- **Per-key editor** — Static has a paint mode: drag over the keys to paint,
  right-click to erase, and the result is stored in the profile.
- **Lid logo** — on, off, breathing, with its state read back from the device.
- **Battery care** — charge limit between 50% and 80%, stored in the controller
  and therefore independent of the operating system.
- **Tray application** — runs in the background, click to open, right click to
  restore defaults or quit. Closing the window hides it when the tray is
  available; quitting restores the firmware defaults.
- **Normal window behaviour** — title bar, drag to move, menu with restore
  defaults and quit. Ctrl+C in a terminal goes through the same shutdown path,
  so the keyboard is never left in a half-applied state.
- **Profile file** — one JSON file per platform (`~/.config/ophis/profile.json`
  on Linux, `%APPDATA%\ophis\profile.json` on Windows), applied at login if you
  want it.
- **CLI on Linux** — every feature, with `--json` for scripting. On Windows the
  UI is the main interface, with `Ophis-cli.exe --probe` for diagnostics.

## Install

### Linux: Debian package

Download `ophis_<version>_all.deb` from the
[releases page](https://github.com/EpicYamo/ophis/releases) and install it:

```bash
sudo apt install ./ophis_0.3.1_all.deb
```

It installs `ophis`, `ophis-gui` and `ophis-tray`, the desktop entry, the icon
and the udev rule, and pulls in the GTK/PyGObject dependencies. Build it
yourself with `make deb`.

### Linux: from a checkout

```bash
git clone https://github.com/EpicYamo/ophis.git
cd ophis

# Let your desktop session talk to the control interface (one sudo, no reboot)
sudo cp linux/data/99-razer-hidraw.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger --action=change --subsystem-match=hidraw

# Optional: a proper tray icon on GNOME
sudo apt install gir1.2-ayatanaappindicator3-0.1

make test        # 51 unit tests, no hardware needed
make run         # GTK4 GUI
make tray        # GUI in the background with a tray icon
make preview     # GUI with a fake device
```

Requirements: Linux with `hidraw`, Python 3.11+, PyGObject with GTK 4 and
libadwaita (`python3-gi`, `gir1.2-gtk-4.0`, `gir1.2-adw-1`).

Without the udev rule, the CLI still works with `sudo`:

```bash
sudo PYTHONPATH=src python3 -m ophis.cli info
```

### Windows: portable build

Download **`Ophis-windows.zip`** from the
[releases page](https://github.com/EpicYamo/ophis/releases), extract it
anywhere and run **`Ophis.exe`**.

Before the first run, quit **Razer Synapse** (and remove it from startup if you
do not need it for firmware updates). Windows already owns the mouse collection
that carries the control report, so Ophis cannot lock it; keep Synapse's own
lighting path closed instead. `Ophis-cli.exe --probe` prints the HID usage page
and feature-report size of every Razer interface, whether it is the control
interface, and any Razer processes that are still running.

Ophis needs **no administrator rights** and installs **no driver**. It is a
normal user-mode HID application. The executable is unsigned, so Windows
SmartScreen may ask for confirmation the first time.

### Windows: from source

```powershell
git clone https://github.com/EpicYamo/ophis.git
cd ophis
py -3 -m pip install -e ".[windows]"
py -3 -m ophis.windows.app
```

Build the portable folder and zip:

```powershell
powershell -ExecutionPolicy Bypass -File windows/build.ps1
```

Output: `dist/Ophis/Ophis.exe`, `dist/Ophis/Ophis-cli.exe` and
`dist/Ophis-windows.zip`.

## Usage

From the Linux checkout (no installation needed):

```bash
PYTHONPATH=src python3 -m ophis.cli info
PYTHONPATH=src python3 -m ophis.cli temp
```

Install the commands and a desktop entry (no root, everything under
`~/.local`):

```bash
make install         # ophis, ophis-gui, ophis-tray + app-grid icon
make uninstall       # removes them again
```

```bash
ophis set power gaming
ophis set fan 4200                # fixed speed, switches to the Custom profile
ophis set fan auto
ophis set effect breathing --color A020F0 --speed 3
ophis set effect wave --direction right
ophis set logo on
ophis set bho on --threshold 80

ophis animate matrix --seconds 20 --color 00FF66
ophis animate wave --angle 45 --rainbow

ophis save                        # store the current state as the profile
ophis apply                       # push the profile back to the device
ophis autostart on                # start the tray at login
ophis temp --json
```

Every command accepts `--json` and `--preview`. A fixed fan speed takes five or
six seconds to settle — that is the hardware, not the app.

On Windows, `Ophis.exe` opens the window and adds a tray icon. Autostart adds a
value under `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`, so it does not
need administrator rights. `Ophis.exe --tray` starts hidden;
`Ophis.exe --show` starts with the window visible.

## Single writer

The controller has one vendor HID collection, and two writers are one writer too
many. Ophis therefore:

- opens the control collection with a **shared, write-only handle** on Windows.
  Windows opens that mouse top-level collection for system use, so share mode 0
  and `GENERIC_READ` are rejected; `HidD_SetFeature` / `HidD_GetFeature` still
  work through the shared handle;
- serialises every command through one transport. There is no parallel writer
  in the app, and the animation engine stops if the controller falls behind;
- holds a single-instance named pipe before it touches the device, so launching
  Ophis twice cannot create two writers.

The OS-level lock is not available on this laptop, so keep Synapse closed while
Ophis is running; Ophis does not need it.

## The tray application

On Linux, `ophis-tray` starts hidden and puts an icon in the top bar. On GNOME
the icon needs the Ubuntu AppIndicators extension (installed by default on
Ubuntu) and `libayatana-appindicator3`. The indicator itself lives in a small
GTK3 child process (`ophis.tray_helper`), because the extension only understands
`com.canonical.dbusmenu`; GTK3 cannot share a process with GTK4.

On Windows the tray is native (`QSystemTrayIcon`), so there is no helper process
and no extra package.

Clicking the icon opens the window; right click offers **Open**, **Restore
default settings** and **Quit**. Quitting restores the defaults (balanced,
automatic fans, plain white keyboard) but leaves the charge limit alone, because
that is a battery-health setting and not decoration.

## Animations

The firmware has no per-key animation engine worth using, but it does accept
whole-matrix frames. Ophis renders them on the CPU at about **24 frames per
second** — the measured ceiling of the request/response cycle — and pushes six
feature reports per frame:

```
frame -> 6 x 0x03/0x0B (one per row, 48 colour bytes)
      -> 0x03/0x0A with 0x05/0x00 (activate the custom frame)
```

| Effect | Controls |
| --- | --- |
| Breathing | colour, speed, smoothness |
| Wave | angle, speed |
| Sparkle | speed, density |
| Wheel | reverse, speed |
| Lightning | speed, smoothness, strike width, concurrent strikes |
| Flame | flicker speed, smoothness |
| Rain | fall speed, density, colour count |
| Matrix | streak speed, style (diagonal / columns / laser / ripple), density, colour count |
| Static | horizontal or vertical zones with one colour each, plus per-key painting |

Selecting an effect builds its settings panel from the effect's own
declaration, so only the controls that matter appear — the same idea as the
reference application's effect panel. See [docs/EFFECTS.md](docs/EFFECTS.md)
for the parameter ranges and the maths that was ported.

If the controller starts missing frames the engine stops itself and leaves a
static colour rather than hammering the EC.

## How it works

The protocol, device operations, effects and profile are shared. Only the
transport and the window are platform-specific:

```
Linux:   GTK4 window ─┐                    ┌─ HidrawTransport ─► /dev/hidrawN
CLI      ─────────────┼─► backend ─► RazerDevice ─► protocol.py
Windows: Qt window  ──┘                    └─ WindowsHidTransport ─► hid.dll
```

- `protocol.py` — the 91-byte packet codec and command constants.
- `transport.py` — the interface plus a fake transport for tests and previews.
- `transport_linux.py` — `HIDIOCSFEATURE` / `HIDIOCGFEATURE`.
- `transport_windows.py` — `SetupAPI` + `HidD_SetFeature` / `HidD_GetFeature`
  on the shared mouse collection's feature-report handle.
- `device.py` — semantic operations: profiles, fan, frames, logo, charge limit.
- `profile.py` — saved state, no daemon; platform-specific config path.
- `thermal.py` / `sysinfo.py` — Linux sensors and battery.
- `windows/sensors.py` — Windows temperatures, battery and Razer-process probe.
- `animations/` — host-rendered effects.
- `linux/` — GTK4 window, tray helper, packaging, udev rule, mapper.
- `windows/` — Qt window, tray, packaging, icons.

## What the protocol taught us

Three findings are worth repeating, because each one looks like a broken
feature rather than a broken packet:

1. **The checksum is at byte 89**, over bytes 3–88. One byte off and most writes
   still work, which is why it survived a full round of testing before replies
   started failing validation.
2. **A fixed fan speed only applies in the Custom profile.** In Balanced or
   Gaming the controller stores the setpoint, reports `manual_fan = 1`, and
   keeps running its own curve. Nothing errors, the fans just do not move.
3. **The logo LED needs transaction id `0xFF`**, its own brightness set first,
   and the LED *state* command (`0x03/0x00`). Its state getter is `0x03/0x80`;
   the `0x82` variant answers zero no matter what the hardware is doing.

All three are documented with packet dumps in
[docs/PROTOCOL.md](docs/PROTOCOL.md) and [docs/RESEARCH.md](docs/RESEARCH.md).

## Safety

The protocol is undocumented vendor behaviour. Ophis sends only the commands
Synapse sends, clamps values to the ranges observed on this model, and stops an
animation if the controller falls behind. Even so: run it at your own risk.

On Windows, Ophis deliberately avoids kernel drivers and sensor libraries such
as WinRing0. That keeps it user-mode and avoids the driver category that
anti-cheat software tends to block. If a temperature source is unavailable, the
UI says so; it does not install a driver to get one.

The charge limit is a controller setting, not an OS one. It survives reboots and
operating system changes, which is why quitting Ophis does not reset it.

## Known limitations

- The fan figure is the setpoint, not a measurement: this controller exposes no
  tachometer.
- The Blade 14 (2022) has **no LED under the space bar**, and no PrtSc key
  (the last keys are Del and the power button, which does have an LED).
- The fan curve runs only while the app is open. The controller keeps the last
  speed afterwards.
- On Windows, host animations keep running while the app is open, even after
  you switch to another tab or hide the window to the tray. A tray-only start
  leaves the controller alone until the window is first shown. Device effects
  run inside the keyboard either way.
- Hardware-wave direction (`01`/`02`) is not mapped to physical left/right.
- Logo breathing is sent, but the firmware calls it unsupported.
- Only `1532:028C` is a target. Other Blade models advertise different feature
  sets and fan ranges; the code is structured so adding one is a table entry.
- Windows CPU and NVMe temperatures depend on what the firmware exposes through
  ACPI and storage counters. GPU temperature comes from `nvidia-smi`. If the
  CPU reading is missing, the fan curve follows the GPU instead.
- Razer firmware updates, macros and per-app profiles remain Synapse features.
  Ophis replaces the control surface, not the updater.
- The Windows executable is unsigned. SmartScreen may warn on first launch.

## Development

```bash
make test     # 51 unit tests, no device required
make preview  # Linux GUI against a fake device
```

Windows:

```powershell
py -3 -m pip install -e ".[windows]"
py -3 -m ophis.windows.app --preview
powershell -ExecutionPolicy Bypass -File windows/build.ps1
```

Layout: `src/ophis/` (shared core), `src/ophis/gui/` (GTK4),
`src/ophis/windows/` (Qt and Windows transport), `linux/` (Linux packaging,
udev, mapper), `windows/` (PyInstaller recipe), `tests/`, `docs/`.

## Author

Built by **Arda Aycan** ([@EpicYamo](https://github.com/EpicYamo)).

## Disclaimer

Not affiliated with, endorsed by, or supported by Razer Inc. "Razer" and product
names are trademarks of their respective owners and are used only to describe
compatibility. Use this software only on hardware you own.

## License

MIT — see [LICENSE](LICENSE).
