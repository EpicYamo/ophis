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

## Open questions and how to attack them

| Question | Approach |
| --- | --- |
| Actual fan RPM | The EC likely exposes a tachometer read. Not in the command table we know. Candidates: an unused `0x0D` sub-command, or a separate class. Needs a probe sweep + comparison with `sensors`. |
| MUX / Optimus state | Probably an ACPI/WMI call rather than HID. Check `acpi_listen`, DSDT, and the Windows `RazerControlService` behaviour. |
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
