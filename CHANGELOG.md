# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.2] - 2026-10-30

### Fixed

- Linux: the `.deb` wrappers passed `--tray --show` as one quoted argument, so
  launching Ophis from the application menu failed with
  `Unknown option --tray --show`. The wrappers now pass each flag separately
  and preserve the user's arguments.
- Windows: open the control collection with a shared, write-only handle.
  Windows owns the mouse top-level collection that carries the 91-byte report,
  so `share mode 0` and `GENERIC_READ` fail with access denied; every
  `CreateFile` on the real control interface used to fail and the app reported
  "no interface exposes the 91-byte feature report".
- Windows: `Ophis-cli.exe --probe` exits 0 when the controller is connected.
  It used to check `connected` after closing the handle, so it always returned
  1.
- Power: the Custom profile's CPU/GPU boost combo boxes no longer raise
  `set_power_mode() takes 2 positional arguments but 4 were given`; the backend
  and both GUIs now accept boost levels, and applying a saved profile restores
  its stored boost values.
- Windows: host lighting animations keep running when the Lighting tab is not
  visible or the window is hidden to the tray. They resume after a reconnect
  and on the first window show; a tray-only start still leaves the controller
  alone until then.

## [0.3.1] - 2026-10-28

### Fixed

- Windows: the control interface is now identified by its 91-byte feature
  report, not only by the top-level usage page. On this laptop the vendor
  collection is nested under a Generic Desktop/mouse interface, so the old
  check skipped it and reported the keyboard interface's sharing error as
  "close Razer Synapse" even when Synapse was not running.
- Windows: `Ophis-cli.exe --probe` now lists every Razer HID interface with
  its usage page, feature-report size and whether it is the control interface.

## [0.3.0] - 2026-10-26

### Added

- Windows build: a PySide6 window with the same pages, tray, single-instance
  pipe, autostart through `HKCU\...\Run`, and a portable `Ophis-windows.zip`
  built by CI
- Windows HID transport using `SetupAPI` and `HidD_SetFeature` /
  `HidD_GetFeature`; the controller is opened with share mode 0 and there is no
  shared fallback, so a second writer gets a clear error instead of corrupting
  the controller state
- Windows temperatures (NVML for the GPU, ACPI/storage CIM for CPU and NVMe)
  and a Razer-process probe, without installing a sensor driver
- Lighting has a custom/device switch: the device side lists the effects the
  controller renders itself, with only the settings the firmware accepts
  (colour, speed, wave direction)
- shared core: the effect engine and the transport are platform-specific, while
  protocol, device operations, effects and profile are shared
- CI builds and tests both platforms and attaches the `.deb` and the Windows zip
  to tagged releases

### Changed

- repository layout split into `linux/` and `windows/`; the root `Makefile`
  still delegates `make deb`, `make run` and the other Linux targets
- the GTK engine is imported lazily, so `ophis.animations` works without
  PyGObject on Windows

### Fixed

- the keyboard effects section was a clipped combo box that did nothing; it is
  now a list whose entries apply immediately
- the lid logo could report "on" with zero brightness after a controller reset;
  the state is re-applied once when the page opens
- connecting to a missing device no longer raises out of `DeviceBackend`; the
  backend stays in a disconnected state and can reconnect from the UI

## [0.2.0] - 2026-10-25

Renamed from `razer-control-center` to `ophis`, and it grew from a settings
window into a background app with animations.

### Added

- charge limit, performance profiles, fan control and lighting verified on the
  target laptop
- host-rendered effects at 24 fps, ported from Better RGB: breathing, wave,
  sparkle, wheel, lightning, flame, rain, matrix and zoned static, with the
  original parameter ranges and defaults
- per-effect settings panel generated from each effect's declaration;
  speeds that had unusable raw ranges are percentages over the range that
  works (breathing 0.2-8, wave and wheel 0.5-12)
- paint mode that activates the custom frame before writing cells
- per-key matrix preview with paint mode
- fan curves driven by the hottest kernel sensor, with a draggable editor
- temperature readouts for CPU, GPU and NVMe
- tray application (StatusNotifierItem through a GTK3 appindicator helper)
  with open, restore-defaults and quit entries
- profile file at `~/.config/ophis/profile.json`, `save` and `apply` commands
- autostart entry for the tray
- `ophis animate`, `ophis temp`, `ophis autostart` commands
- Debian package (`make deb`) with the commands, desktop entry, icon and udev
  rule, plus a CI workflow that tests every push and publishes the package on
  tags
- new window: sidebar navigation, profile cards, live values

### Fixed

- colour buttons did nothing at all: the `notify::rgba` handlers were missing
  the property argument, so every change raised inside GTK and was dropped
- matrix speeds above 2, and the laser sweep style, which cut streaks in half
  at the board edges
- the window had no title bar, so it could not be moved, minimised or closed

- the checksum is at byte 89 over bytes 3-88; it had been one byte off, so every
  packet carried a checksum the controller disagreed with
- a fixed fan speed is only applied in the Custom profile; setting one now
  switches profiles, and the setpoint and manual flag are read on startup
- the lid logo needs transaction id `0xFF`, its own brightness, and the LED
  state command; the getter is `0x03/0x80`, not `0x82`
- keyboard effects were sent with the effect id alone, so breathing, reactive
  and starlight used firmware defaults instead of the chosen colour and speed

### Removed

- the hand-written StatusNotifierItem implementation. Malformed menu replies
  could take the GNOME shell down; the library replaces it.

## [0.1.0] - 2026-10-25

### Added

- 91-byte packet codec with checksum and echo validation
- hidraw transport using feature-report ioctls (no hidapi, no kernel module)
- automatic discovery of the control interface by usage page `0xFF00`
- device API: profiles, boost, fan RPM, brightness, logo, effects, charge limit
- GTK4/libadwaita window with a hardware-free preview mode
- CLI with JSON output
- battery and AC state from `/sys/class/power_supply`
- udev rule for non-root access
- protocol and research documentation
- unit tests

[0.2.0]: https://github.com/EpicYamo/ophis/releases/tag/v0.2.0
[0.1.0]: https://github.com/EpicYamo/ophis/releases/tag/v0.1.0
