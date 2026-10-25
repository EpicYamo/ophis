# Roadmap

Milestones are cumulative. A milestone is done when its checkbox is ticked and
the corresponding section of the README is accurate.

## M0 — Protocol foundation

- [x] Document the 91-byte feature-report layout in `docs/PROTOCOL.md`
- [x] Packet encoder/decoder with CRC and echo validation
- [x] Unit tests for packets, checksums, BHO packing and fan units
- [x] Fake transport so everything runs without hardware
- [x] Identify the control interface automatically (usage page `0xFF00`)

## M1 — Hardware verification

Read-only verification completed on 2026-10-25 on the target laptop
(Blade 14 2022, `1532:028C`, `/dev/hidraw5`, driver `hid-generic`,
BIOS 3.06). Recorded values:

| Query | Reply arguments | Decoded |
| --- | --- | --- |
| power mode, CPU | `00 01 00 00` | zone 1, mode 0 (balanced) |
| power mode, GPU | `00 02 00 00` | zone 2, mode 0 (balanced) |
| CPU boost | `00 01 01 00` | level 1 (normal) |
| GPU boost | `00 02 01 00` | level 1 (normal) |
| keyboard brightness | `01 05 FF` | `VARSTORE`, `BACKLIGHT_LED`, 255 |
| logo LED | `01 04 00` | `VARSTORE`, `LOGO_LED`, off |
| charge limit | `D0` | enabled, threshold 80% |

- [x] Run the read-only probe on the target laptop and record the real values
- [x] Verify `get power mode` reports the profile the firmware was running
      (balanced on both zones)
- [x] Verify `get charge limit` returns the configured 80% limit
- [x] Confirm the reply offsets in `docs/PROTOCOL.md` against real packets
      (zone at `args[1]`, value at `args[2]`, BHO packed byte at `args[0]`)
- [x] Write a single, reversible command: brightness 255 → 128 → 255, each step
      read back from the device
- [x] Write the charge limit with its current value (enabled, 80%) and read it
      back unchanged — the write path works without altering behaviour
- [ ] Confirm the battery actually stops at the threshold (needs a charge cycle)
- [x] Write fan RPM and confirm the audible change: only custom mode applies it,
      and the fans ramp over 5-6 seconds (5000 -> 3500 was clearly audible)
- [x] Send every keyboard effect with its parameters (colour, speed, wave
      direction) and confirm each animation runs
- [x] Switch the lid logo on and off and read its state back (transaction id
      `0xFF`, state command `0x03/0x00`, getter `0x03/0x80`)
- [x] Document any command that behaves differently from `docs/PROTOCOL.md`:
      the checksum is at byte 89 over `3..88` (it was one byte off), and a fixed
      fan speed is only applied in custom mode

## M2 — Daemon

- [ ] `razerd` root daemon: owns the hidraw node, applies state at boot
- [ ] D-Bus API on the system bus with polkit authorization
- [ ] Per-power-source profiles (AC vs battery), applied automatically
- [ ] Restore last state on login and after resume
- [ ] systemd unit + udev rule shipped in `data/`

## M3 — GUI

- [x] GTK4/libadwaita window with all four groups
- [x] Preview mode without hardware
- [ ] Talk to the daemon over D-Bus instead of opening the device directly
- [ ] Menu-bar / tray icon with quick profile switching
- [ ] Keyboard lighting preview (per-key editor)
- [ ] Turkish and English translations via gettext

## M4 — Packaging

- [ ] Debian package (`debian/` or `nfpm`)
- [ ] Flatpak or AppImage build in CI
- [ ] GitHub Actions: tests + lint on push
- [ ] Tagged release with changelog

## M5 — Beyond Synapse

- [ ] Read the actual fan RPM
- [ ] Fan curve editor driven by CPU/GPU temperature
- [ ] Temperature and power draw readouts
- [ ] Display refresh-rate switching
- [ ] MUX / Optimus state (research first, see `docs/RESEARCH.md`)
