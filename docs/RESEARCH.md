# Research notes

What is known, where it came from, and what is still unknown. This file is the
record of the reverse-engineering work so the project does not depend on any
single person's memory.

## Target

| | |
| --- | --- |
| Laptop | Razer Blade 14 (2022) |
| Model | RZ09-0427 |
| USB ID | `1532:028C` |
| BIOS | 3.06 |
| CPU / GPU | Ryzen 9 6900HX / RTX 3070 Ti Laptop |
| OS used for development | Ubuntu 26.04, kernel 7.0, Secure Boot on |

## Prior art

The protocol is not public, but several projects have already mapped large parts
of it. Reading their behaviour (and, where needed, their source) is what made
this project possible. All of them are GPL-2.0; this project is a clean-room
re-implementation under MIT, so no code was copied — only protocol facts, which
are not copyrightable.

| Project | License | What it established |
| --- | --- | --- |
| [OpenRazer](https://github.com/openrazer/openrazer) | GPL-2.0 | hidraw usage, LED command classes, device IDs, udev rules |
| [razer-laptop-control](https://github.com/rnd-ash/razer-laptop-control) | GPL-2.0 | power modes, fan RPM units, per-zone writes |
| [razer-laptop-control-no-dkms](https://github.com/Razer-Linux/razer-laptop-control-no-dkms) | GPL-2.0 | charge limit (BHO) command, per-model feature flags |

Useful facts taken from those projects and then verified against the packet
layout on this machine:

- the control interface is the HID interface with usage page `0xFF00`
- fan speed is expressed in 100 RPM units and this model accepts 35–50
- `manual_fan` in the power-mode packet is what actually hands fan control over
- the charge limit packs "enabled" into bit 7 of the threshold byte
- custom power mode disables manual fan control

## What this project added

- a packet codec with strict CRC/echo validation and retries, covered by tests
- explicit clamping to the ranges observed on this model instead of silently
  writing out-of-range values
- a separate `sysinfo` layer so the UI can show battery state without mixing it
  into protocol code

## How the protocol was confirmed

1. Read the HID report descriptors from `/sys/bus/hid/devices/*/report_descriptor`
   and picked the vendor-defined collection (`0xFF00`).
2. Sent read-only commands (`0x0D/0x82`, `0x0D/0x87`, `0x03/0x83`, `0x07/0x92`)
   and checked that the echoed class/id and status byte were valid.
3. Compared the returned values with what the machine reported before and after
   a change (power profile, charge limit).
4. Only then implemented write commands, one at a time, with clamping.

The read-only probe used for step 1–2 is kept at
`~/Desktop/tools/probe/probe.py` (outside the repository, because it needs root
and is not part of the product).

### Result, 2026-10-25

Every read-only query answered with status `0x02` (successful) and the CRC and
echoed class/id checked out. The decoded values matched the settings the machine
was actually running, which is the evidence that the field offsets are right:

| Query | Raw arguments | Meaning |
| --- | --- | --- |
| `0x0D/0x82` zone 1 | `00 01 00 00` | CPU zone, balanced |
| `0x0D/0x82` zone 2 | `00 02 00 00` | GPU zone, balanced |
| `0x0D/0x87` CPU | `00 01 01 00` | boost level 1 (normal) |
| `0x0D/0x87` GPU | `00 02 01 00` | boost level 1 (normal) |
| `0x03/0x83` | `01 05 FF` | brightness 255 of 255 |
| `0x03/0x82` (logo) | `01 04 00` | logo LED off |
| `0x07/0x92` | `D0` | charge limit enabled, 80% |

Two things this proved that the old notes only assumed:

- the zone byte really sits at `args[1]` and the value at `args[2]`
- the charge-limit byte is `0x80 | threshold`, so `0x50` (80) with bit 7 set
  becomes `0xD0`

It also confirmed that `hid-generic` plus a udev rule is enough: the probe ran
as a normal user, with no kernel module and Secure Boot still enabled.

The logo row above used `0x03/0x82`, which answers `0` no matter what the LED is
doing; the correct getter is `0x03/0x80`. See the note at the end of this file.

### Write commands, 2026-10-25

Each write was followed by a read of the same value, so "read back" below means
the device reported success **and** the new value came back.

| Command | Sent | Result |
| --- | --- | --- |
| brightness | `01 05 80`, then `01 05 FF` | read back `80`, then `FF` |
| charge limit | `D0` (enabled, 80%) | read back `D0`, unchanged |
| fan, balanced/gaming | mode `0`, `manual_fan=1`, setpoint `35`–`50` | setpoint stored and readable via `0x81`, `manual_fan` reports `1`, **fans do not move** |
| fan, custom | mode `4`, `manual_fan=1`, setpoint `50` to both zones | fans audibly spin up; `0x81` reads back `50` |
| fan, back to automatic | mode `4`, `manual_fan=0` | fans return to the firmware curve |
| lighting | static, breathing (single), wave, reactive, starlight, spectrum, each with the parameters from OpenRazer's layouts | every effect visibly ran; there is no query for the current effect |
| per-key frames | six `03/0B` rows plus `03/0A 05 00`, repeated at 24 fps | six horizontal colour bands appeared, then ran as an animation |
| logo LED | `03/03` brightness `FF`, then `03/00` `01 04 01`, transaction `FF` | logo lights up; state reads back `1` via `03/80` |

Fan transitions are gradual: 5000 → 3500 takes about 5–6 seconds, and the fans
ramp smoothly instead of stepping. Listening for two seconds is not enough,
which is exactly why the first rounds of testing looked like a failure.

The logo took a third mistake to solve: Blade laptops answer logo commands only
with transaction id `0xFF`, switch it with the LED *state* command (`03/00` +
its own brightness) rather than an effect, and report it through `03/80`. We
were sending `0x1F` and reading `03/82`, which returns zero regardless of the
hardware — easy to read as "this model has no logo".

### Two mistakes found here, both worth remembering

**The checksum offset was off by one.** The 80 argument bytes are at `9..88`,
the checksum is at 89 and covers `3..88`. This project originally put the
checksum at 88 and covered `2..87`, so every request carried a checksum the EC
did not agree with. Power-mode writes still worked, which hid the problem; reply
validation failed, which was first misdiagnosed as "the firmware echoes the
request checksum".

**Manual fan needs custom mode.** The power-mode packet has a `manual_fan` flag,
and the EC stores the setpoint and reports the flag even in balanced mode. It
only acts on it in custom mode (`4`). Writing the flag and the setpoint in
balanced looked successful in every query and did nothing audible.

### Frame timing

Six row writes plus one activation take about 42 ms with the full
request/response cycle (24 fps), or 18 ms write-only (55 fps). The write-only
path leaves responses queued, which makes later commands read someone else's
reply, so the animation engine sticks to the slower, acknowledged path. Ten
consecutive frames over 140 ms stop the animation and fall back to a static
colour: a slow EC is a warning, not something to push through.

## Open questions and how to attack them
### Frame timing

Six row writes plus one activation take about 42 ms with the full
request/response cycle (24 fps), or 18 ms write-only (55 fps). The write-only
path leaves responses queued, which makes later commands read someone else's
reply, so the animation engine sticks to the slower, acknowledged path. Ten
consecutive frames over 140 ms stop the animation and fall back to a static
colour: a slow EC is a warning, not something to push through.

## Open questions and how to attack them

| Question | Approach |
| --- | --- |
| Actual fan RPM | The EC likely exposes a tachometer read. Not in the command table we know. Candidates: an unused `0x0D` sub-command, or a separate class. Needs a probe sweep + comparison with `sensors`. |
| MUX / Optimus state | Probably an ACPI/WMI call rather than HID. Check `acpi_listen`, DSDT, and the Windows `OphisService` behaviour. |
| Refresh-rate switching | Synapse may push it over the same HID channel; Mutter DBus is the safer Linux-side implementation anyway. |
| GPU TGP limits | Likely `nvidia-smi -pl`, not the EC. |
| Thresholds below 50% | Unknown whether the firmware accepts them; the UI deliberately stops at 50%. |

### Using an agent to inspect Synapse

If the unknown commands above become important, the fastest route is static
analysis of the Windows Synapse components (`RazerCentralService.exe`, the EC
driver DLL) plus USB captures, looking for `0x0D`/`0x07` packets that this
document does not list.

REA (`rea-agents`) was used briefly during the first session and then removed at
the owner's request. If needed again, it installs with:

```bash
npx rea-agents@latest setup
```

Keep it out of the repository and out of the system: it is only a development
aid, and publishing analysis results does not require it.
