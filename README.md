# Ophis

A Linux control centre for the **Razer Blade 14 (2022)**, `RZ09-0427`
(USB `1532:028C`): performance profiles, fan control and fan curves, per-key
RGB with host-rendered animations, the lid logo, and the battery charge limit.

No kernel module, no Secure Boot changes, no Razer account, no daemon.

Built from scratch in Python against a protocol that is not documented anywhere.
Every command in this repository was sent to a real laptop and its effect
confirmed, including the three protocol mistakes described further down.

---

## Why this project exists

Synapse does not run on Linux. The community projects that cover this hardware
are either archived, cover only part of it, or need an out-of-tree kernel module
that fights Secure Boot:

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
- **Temperatures** — CPU, GPU and NVMe, read from the kernel sensors.
- **Lighting** — nine host-rendered effects ported from
  [Better RGB](https://github.com/EpicYamo/Better-RGB-for-Tongfang-ITE8291):
  breathing, wave with an adjustable angle, sparkle, wheel, lightning, flame,
  rain, matrix (four styles) and zoned static, each with the same parameter
  ranges and defaults as the original. The firmware's spectrum, reactive and
  starlight effects are still available.
- **Per-key editor** — Static has a paint mode: drag over the keys to paint,
  right-click to erase, and the result is stored in the profile.
- **Lid logo** — on, off, breathing, with its state read back from the device.
- **Battery care** — charge limit between 50% and 80%, stored in the controller
  and therefore independent of the operating system.
- **Tray application** — runs in the background, click to open, right click to
  restore defaults or quit.
- **Profile file** — one JSON file, applied at login if you want it.
- **CLI** — every feature, with `--json` for scripting.

## Install

```bash
git clone https://github.com/EpicYamo/ophis.git
cd ophis

# Let your desktop session talk to the control interface (one sudo, no reboot)
sudo cp data/99-razer-hidraw.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger --action=change --subsystem-match=hidraw

# Optional: a proper tray icon on GNOME
sudo apt install libayatana-appindicator-glib2 gir1.2-ayatanaappindicatorglib-2.0

make test        # 46 unit tests, no hardware needed
make run         # GUI
make tray        # GUI in the background with a tray icon
make preview     # GUI with a fake device
```

Requirements: Linux with `hidraw`, Python 3.11+, PyGObject with GTK 4 and
libadwaita (`python3-gi`, `gir1.2-gtk-4.0`, `gir1.2-adw-1`).

Without the udev rule, the CLI still works with `sudo`:

```bash
sudo PYTHONPATH=src python3 -m ophis.cli info
```

## Usage

From the checkout (no installation needed):

```bash
PYTHONPATH=src python3 -m ophis.cli info
PYTHONPATH=src python3 -m ophis.cli temp
```

Or install it once for the `ophis` command:

```bash
pipx install .       # or: python3 -m pip install --user .
ophis info
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

## The tray application

`ophis-tray` starts hidden and puts an icon in the top bar. Clicking opens the
window; right click offers **Open**, **Restore default settings** and **Quit**.
Quitting restores the defaults (balanced, automatic fans, plain white keyboard)
but leaves the charge limit alone, because that is a battery-health setting and
not decoration.

On GNOME the icon needs the Ubuntu AppIndicators extension (installed by
default on Ubuntu) and the library above. Without it the app runs normally and
prints a note on stderr.

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

```
GTK4 window ─┐
CLI          ─┴─► backend ─► RazerDevice ─► HidrawTransport ─► /dev/hidrawN
                    │        protocol.py      feature reports   1532:028C,
                    │                                           usage page 0xFF00
                    ├─ profile.py   one JSON file
                    ├─ thermal.py   kernel sensors
                    └─ animations/  frame engine
```

- `protocol.py` — the 91-byte packet codec and command constants.
- `transport.py` — `HIDIOCSFEATURE` / `HIDIOCGFEATURE`, plus a fake transport.
- `device.py` — semantic operations: profiles, fan, frames, logo, charge limit.
- `profile.py` — saved state, no daemon.
- `thermal.py` — temperatures for the fan curve.
- `animations/` — host-rendered effects.
- `gui/` — the window, the matrix preview and the curve editor.

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

The charge limit is a controller setting, not an OS one. It survives reboots and
operating system changes, which is why quitting Ophis does not reset it.

## Known limitations

- The fan figure is the setpoint, not a measurement: this controller exposes no
  tachometer.
- The fan curve runs only while the app is open. The controller keeps the last
  speed afterwards.
- Hardware-wave direction (`01`/`02`) is not mapped to physical left/right.
- Logo breathing is sent, but the firmware calls it unsupported.
- Only `1532:028C` is a target. Other Blade models advertise different feature
  sets and fan ranges; the code is structured so adding one is a table entry.

## Development

```bash
make test     # 46 unit tests, no device required
make preview  # GUI against a fake device
```

Layout: `src/ophis/` (code), `tests/` (unit tests), `docs/` (protocol and
research notes), `data/` (udev rule and desktop entry).

## Disclaimer

Not affiliated with, endorsed by, or supported by Razer Inc. "Razer" and product
names are trademarks of their respective owners and are used only to describe
compatibility. Use this software only on hardware you own.

## License

MIT — see [LICENSE](LICENSE).
