# razer-control-center

A Linux control center for the **Razer Blade 14 (2022), RZ09-0427** — the parts
of Razer Synapse that actually matter:

- performance profiles (Balanced / Gaming / Creator / Custom)
- CPU and GPU boost levels
- fan control (automatic or fixed 3500–5000 RPM)
- keyboard backlight brightness, logo LED and lighting effects
- battery charge limit (Battery Health Optimizer)

No DKMS module, no Secure Boot changes, no cloud account. It talks to the
laptop's embedded controller over the HID feature-report protocol that Synapse
itself uses.

> **Status: pre-alpha.** The protocol layer is unit-tested against captured
> packet layouts; the GUI is functional but has not been verified on hardware
> yet. See [ROADMAP.md](ROADMAP.md).

## Why this exists

Synapse does not run on Linux, and the existing community projects are either
unmaintained or cover only part of the hardware:

| Project | RGB | Fan | Power | Charge limit | State |
| --- | --- | --- | --- | --- | --- |
| [OpenRazer](https://github.com/openrazer/openrazer) | yes | no | no | no | active |
| [razer-laptop-control](https://github.com/rnd-ash/razer-laptop-control) | yes | yes | yes | no | archived (2022) |
| [razer-laptop-control-no-dkms](https://github.com/Razer-Linux/razer-laptop-control-no-dkms) | yes | yes | yes | yes | maintenance mode (2025) |
| **this project** | yes | yes | yes | yes | in development |

This project is written from scratch (MIT) against the documented protocol
behaviour, not as a fork. See [docs/PROTOCOL.md](docs/PROTOCOL.md) and
[docs/RESEARCH.md](docs/RESEARCH.md).

## Requirements

- Linux with the `hidraw` subsystem (any modern distro; developed on Ubuntu 26.04)
- Python 3.11+
- `python3-gi`, `gir1.2-gtk-4.0`, `gir1.2-adw-1` (GUI only)
- write access to the Razer control interface (see below)

## Install

```bash
git clone https://github.com/TheYamo/razer-control-center.git
cd razer-control-center

# give your desktop session access to the control interface (recommended)
sudo cp data/99-razer-hidraw.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger

make test        # unit tests, no hardware needed
make run         # start the GUI
make preview     # GUI with a fake device, no hardware, no permissions
```

Without the udev rule you can always run the CLI with `sudo`:

```bash
sudo PYTHONPATH=src python3 -m razercc.cli info
```

## Usage

```bash
razercc info                          # everything at a glance
razercc get battery --json            # charge limit + live capacity
razercc set power gaming
razercc set fan 4200                  # or: razercc set fan auto
razercc set brightness 180
razercc set bho on --threshold 80     # stop charging at 80%
razercc set effect static --color FF5500
razercc set logo breathing
```

Every command accepts `--json` for scripting, and `--preview` to exercise the
CLI without hardware.

## How it works

```
GUI (GTK4/libadwaita)  ─┐
CLI (argparse)         ─┴─►  RazerDevice  ─►  HidrawTransport  ─►  /dev/hidrawN
                              protocol.py                       (1532:028C, page 0xFF00)
```

- `protocol.py` — 91-byte packet encoder/decoder, command constants, unit
  conversions. Hardware independent, fully covered by tests.
- `transport.py` — hidraw feature-report ioctls, plus a fake transport for tests.
- `device.py` — semantic operations (set profile, set fan, set charge limit).
- `backend.py` — the seam the GUI/CLI use.
- `sysinfo.py` — battery and AC state from `/sys/class/power_supply`.

## Safety

The protocol is the same one Razer's own software uses, but it is undocumented
vendor behaviour. This project only sends commands that Synapse sends, with
values clamped to the ranges observed on this model (fan 3500–5000 RPM, charge
threshold 50–80%). Wrong values are more likely to be rejected than to damage
anything, but you run it at your own risk.

## Disclaimer

Not affiliated with, endorsed by, or supported by Razer Inc. "Razer" and product
names are trademarks of their respective owners and are used only to describe
compatibility. Use this software only on hardware you own.

## License

MIT — see [LICENSE](LICENSE).
