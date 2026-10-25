# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-10-25

### Added

- 91-byte Razer HID packet codec with CRC and echo validation
- hidraw transport using feature-report ioctls (no hidapi, no kernel module)
- automatic discovery of the control interface by usage page `0xFF00`
- device API: power profiles, CPU/GPU boost, fan RPM, keyboard brightness,
  logo LED, lighting effects, battery charge limit
- GTK4/libadwaita control window with a hardware-free preview mode
- `razercc` CLI with JSON output for scripting
- battery and AC state from `/sys/class/power_supply`
- udev rule for non-root access to the control interface
- protocol and research documentation
- unit tests for packets, checksums, charge-limit packing and fan units

### Notes

- Hardware verification is still pending; see `ROADMAP.md` M1.
- Only `1532:028C` (Blade 14 2022) is a known target. Other models advertise
  different feature sets and fan ranges.

[0.1.0]: https://github.com/TheYamo/razer-control-center/releases/tag/v0.1.0
