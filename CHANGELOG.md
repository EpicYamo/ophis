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
- `ophis` CLI with JSON output for scripting
- battery and AC state from `/sys/class/power_supply`
- udev rule for non-root access to the control interface
- protocol and research documentation
- unit tests for packets, checksums, charge-limit packing and fan units

### Fixed

- the checksum was one byte off: it lives at byte 89 and covers bytes 3-88, not
  at byte 88 over 2-87. Every request carried a checksum the EC disagreed with,
  and replies failed validation, which was first misread as the firmware
  echoing the request checksum
- a fixed fan speed was ignored unless the laptop was in custom mode; setting
  one now switches profiles, and the fan setpoint and manual flag are read back
  on startup instead of guessed
- the lid logo never lit up: logo commands need transaction id `0xFF`, the LED
  brightness set first, and the state command `0x03/0x00`; the state getter is
  `0x03/0x80` (the `0x82` variant always answers zero)
- keyboard effects were sent with the effect id alone, so breathing, reactive
  and starlight fell back to firmware defaults; each effect now carries its
  colour, speed and direction with the argument count it actually needs

### Notes

- Reads, lighting, the charge limit and fan control are verified on the target
  laptop. The battery cut-off itself still needs a full charge cycle.
- Only `1532:028C` (Blade 14 2022) is a known target. Other models advertise
  different feature sets and fan ranges.

[0.1.0]: https://github.com/EpicYamo/ophis/releases/tag/v0.1.0
