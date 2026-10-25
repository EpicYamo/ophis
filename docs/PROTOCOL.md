# Protocol

Everything below was established by inspecting how the laptop's keyboard/EC
interface behaves, cross-checked against the behaviour of existing open source
implementations (see [RESEARCH.md](RESEARCH.md)). No vendor code is copied.

## Transport

| Property | Value |
| --- | --- |
| USB ID | `1532:028C` (Razer Blade 14 2022) |
| Interface | HID interface whose report descriptor declares **Usage Page `0xFF00`** (vendor-defined) |
| On this machine | `hidraw5`, `DRIVER=hid-generic` |
| Direction | HID **feature report**, 91 bytes, both ways |
| Permissions | normally `root` only; a udev rule grants the desktop session access |

The kernel driver `hid-generic` is enough. No out-of-tree module is required,
which also means Secure Boot can stay enabled.

## Packet layout

All multi-byte integers are little endian. Total length is fixed at 91 bytes.

| Offset | Size | Field | Notes |
| --- | --- | --- | --- |
| 0 | 1 | `report` | always `0x00` |
| 1 | 1 | `status` | see status codes |
| 2 | 1 | `transaction_id` | `0x1F` for requests |
| 3 | 2 | `remaining_packets` | `0x0000` for single-packet commands |
| 5 | 1 | `protocol_type` | `0x00` |
| 6 | 1 | `data_size` | number of meaningful argument bytes |
| 7 | 1 | `command_class` | see command table |
| 8 | 1 | `command_id` | see command table |
| 9 | 80 | `arguments` | zero padded |
| 89 | 1 | `crc` | XOR of bytes **2..87** |
| 90 | 1 | `reserved` | `0x00` |

### Status codes

| Value | Meaning |
| --- | --- |
| `0x00` | new / idle |
| `0x01` | busy |
| `0x02` | successful |
| `0x03` | failure |
| `0x04` | timeout |
| `0x05` | not supported |

A response echoes the request's `command_class` and `command_id`. Compare both
and require status `0x02` before trusting the arguments.

### Checksum

```python
crc = 0
for byte in packet[2:88]:
    crc ^= byte
packet[88] = crc
```

Note the range: the last argument byte (offset 88) is **not** part of the XOR.

### Replies reuse the request's checksum

This firmware does **not** recompute the checksum when it answers. It leaves
the request's byte 88 in place, so a reply that carries data fails a strict
check. Verified on hardware by varying an unused request argument and watching
byte 88 of the reply follow it while the reply data stayed identical:

| Request byte 10 | Request byte 88 | Reply byte 88 |
| --- | --- | --- |
| `00` | `98` | `98` |
| `11` | `89` | `89` |
| `AA` | `32` | `32` |
| `FF` | `67` | `67` |

So a reply is accepted when its checksum matches either the recomputed value or
the checksum the request carried. `Packet.decode(..., accept_crc=...)` does
exactly that, and `HidrawTransport` always passes the request checksum. The
status byte and the echoed command class/id are still validated, which is what
actually catches a misbehaving device.

Byte 89 comes back non-zero on replies (`0x9F`, `0xCE`, ...) and is not part of
either checksum; requests send `0x00` there and are accepted.

## Commands

`zone` is `1` for the CPU and `2` for the GPU. Write commands are sent for both
zones so the two halves of the cooling system agree.

### Power and fan — class `0x0D`

| Command | ID | `data_size` | Arguments | Response |
| --- | --- | --- | --- | --- |
| Set power mode | `0x02` | 4 | `00`, `zone`, `mode`, `manual_fan` | status only |
| Set fan RPM | `0x01` | 3 | `00`, `zone`, `rpm/100` | status only |
| Set boost | `0x07` | 3 | `00`, `which`, `level` | status only |
| Get power mode | `0x82` | 4 | `00`, `zone`, `00`, `00` | `args[2]` = mode |
| Get boost | `0x87` | 3 | `00`, `which`, `00` | `args[2]` = level |

- `mode`: `0` balanced, `1` gaming, `2` creator, `4` custom.
- `manual_fan`: `1` when a fixed RPM was set, `0` for automatic. Changing a fan
  setting therefore requires re-sending the power mode with the new flag.
- `which`: `1` CPU, `2` GPU. Boosts are only meaningful in custom mode.
- `level`: `0` low, `1` normal, `2` high, `3` boost (CPU only on models that
  advertise the `boost` feature).
- `rpm/100`: fan speed in 100 RPM units. This model accepts 3500–5000 RPM, so
  the value is 35–50. `0` means "automatic".
- In custom mode the fan is managed by the firmware; RPM writes are ignored.

### Battery Health Optimizer — class `0x07`

| Command | ID | `data_size` | Arguments | Response |
| --- | --- | --- | --- | --- |
| Set | `0x12` | 1 | packed byte | status only |
| Get | `0x92` | 1 | `00` | `args[0]` = packed byte |

Packed byte:

```
bit 7      : 1 = charge limit enabled, 0 = disabled
bits 0..6  : threshold in percent
```

The UI range is 50–80%. `0x80 | 80` means "enabled, stop at 80%".

### Lighting — class `0x03`

| Command | ID | `data_size` | Arguments |
| --- | --- | --- | --- |
| Set brightness | `0x03` | 3 | `VARSTORE`, `BACKLIGHT_LED`, `0..255` |
| Get brightness | `0x83` | 3 | `VARSTORE`, `BACKLIGHT_LED`, `00` |
| Set logo mode | `0x00` | 3 | `VARSTORE`, `LOGO_LED`, `0|1` |
| Set logo breathing | `0x02` | 3 | `VARSTORE`, `LOGO_LED`, `0x02` |
| Set standard effect | `0x0A` | 80 | `effect_id`, params… |
| Set custom frame | `0x0B` | 52 | `0xFF`, `row`, `00`, `0x0F`, 45 colour bytes at offset 7 |

Constants: `NOSTORE = 0x00`, `VARSTORE = 0x01`, `LOGO_LED = 0x04`,
`BACKLIGHT_LED = 0x05`.

Effect ids: `0x00` off, `0x01` wave, `0x02` reactive, `0x03` breathing,
`0x04` spectrum, `0x05` custom frame, `0x06` static, `0x19` starlight.

Static colour is `effect_id = 0x06` followed by `R`, `G`, `B`.

## Sequence for a write

1. Build the packet, pad arguments to 80 bytes, compute the CRC.
2. `HIDIOCSFEATURE(91)` with the buffer (first byte is the report number `0`).
3. Wait a few milliseconds.
4. `HIDIOCGFEATURE(91)` into a zeroed buffer.
5. Decode, accept the CRC if it matches the reply **or** the request, verify the
   echoed class/id, require status `0x02`.
6. Retry up to 3 times; the device occasionally answers late.

Measuring with `strace -e ioctl` is enough to see the exchange; `HIDIOCGFEATURE`
returns all 91 bytes, so no `read()` loop is needed.

## Open questions

These are not needed for the features above, but are the interesting next steps
(see [ROADMAP.md](../ROADMAP.md)):

- reading the **actual** fan RPM (only the target is writable today)
- MUX switch / Optimus state
- display refresh-rate switching on models that Synapse handles
- GPU TGP limits
