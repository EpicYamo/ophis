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

- [ ] Run the read-only probe on the target laptop and record the real values
- [ ] Verify `get power mode` matches what the firmware had before the probe
- [ ] Verify `get charge limit` returns the value Synapse would show
- [ ] Write a single, reversible command (brightness) and confirm it applies
- [ ] Write the charge limit and confirm the battery stops at the threshold
- [ ] Write fan RPM and confirm the audible change
- [ ] Document any command that behaves differently from `docs/PROTOCOL.md`

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
