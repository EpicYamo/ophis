# Roadmap

Milestones are cumulative. A milestone is done when its boxes are ticked and the
README describes reality.

## M0 — Protocol foundation

- [x] Document the 91-byte feature-report layout in `docs/PROTOCOL.md`
- [x] Packet codec with checksum and echo validation
- [x] Unit tests for packets, checksums, charge-limit packing and fan units
- [x] Fake transport so everything runs without hardware
- [x] Identify the control interface automatically (usage page `0xFF00`)

## M1 — Hardware verification

Recorded on 2026-10-25 on the target laptop (Blade 14 2022, `1532:028C`,
`/dev/hidraw5`, driver `hid-generic`, BIOS 3.06). Every value below was read
back from the device, not assumed:

| Query | Reply arguments | Decoded |
| --- | --- | --- |
| power mode, CPU / GPU | `00 01 00 00` / `00 02 00 00` | balanced on both zones |
| CPU / GPU boost | `00 01 01 00` / `00 02 01 00` | level 1 (normal) |
| keyboard brightness | `01 05 FF` | 255 |
| logo state (`03/80`) | `01 04 00` | off |
| charge limit | `D0` | enabled, 80% |
| fan setpoint (`0D/81`) | `00 01 32` | 5000 RPM |

- [x] Read the current state and confirm every field offset
- [x] Write the brightness, 255 -> 128 -> 255, reading it back each time
- [x] Write the charge limit with its current value and read it back unchanged
- [x] Write a fan speed and confirm the audible change (custom profile)
- [x] Switch the lid logo and read its state back
- [x] Send every firmware effect and confirm the animation runs
- [x] Write per-key frames and confirm cell-level control
- [ ] Confirm the battery stops at the threshold (needs a full charge cycle)

## M2 — Background app

- [x] Tray icon through `libayatana-appindicator-glib`
- [x] Click opens the window, right click restores defaults or quits
- [x] Restore defaults on quit, keeping the charge limit
- [x] Profile file at `~/.config/ophis/profile.json`
- [x] `ophis save` / `ophis apply`
- [x] Autostart entry in `~/.config/autostart`
- [ ] Apply the profile on AC/battery transitions
- [ ] Reconnect automatically when the device disappears (suspend/resume)

## M3 — Window

- [x] Sidebar layout with Performance, Cooling, Lighting, Battery, Settings
- [x] Live temperatures and battery state
- [x] Fan curve editor with draggable points
- [x] Per-key matrix preview and paint mode
- [x] Preview mode with a fake device
- [ ] Drag the window to a second monitor without losing the animation timer
- [ ] Translations through gettext

## M4 — Lighting

- [x] Firmware effects with colour, speed and direction
- [x] Host-rendered effects at 24 fps, ported from Better RGB with the same
      parameter ranges and defaults
- [x] A settings panel generated per effect
- [x] Per-key frames, paint mode and the `0x0B` activation sequence
- [x] Per-effect settings stored in the profile
- [ ] Store and share whole lighting presets
- [ ] Keypress-reactive effect (needs read access to the keyboard input node)

## M5 — Packaging

- [x] User-level install: commands, desktop entry and icon in `~/.local`
- [ ] Debian package (`debian/` or `nfpm`)
- [ ] Flatpak or AppImage build in CI
- [ ] GitHub Actions: tests on push
- [ ] Tagged release with changelog and screenshots

## M6 — Beyond Synapse

- [x] Temperature readouts
- [x] Temperature-driven fan curve
- [ ] Read the actual fan speed (no tachometer command known)
- [ ] Display refresh-rate switching
- [ ] MUX / Optimus state (research first, see `docs/RESEARCH.md`)
- [ ] GPU power limits through `nvidia-smi`
