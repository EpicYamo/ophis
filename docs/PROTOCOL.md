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
| 89 | 1 | `crc` | XOR of bytes **3..88** |
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
for byte in packet[3:89]:
    crc ^= byte
packet[89] = crc
```

The checksum sits **after** the 80 argument bytes, so the arguments are at
`9..88` and the byte at 89 is not an argument. Getting this off by one is easy
and misleading: the EC still accepts most writes, so the mistake survives unit
tests and a first round of hardware testing. It only shows up when a reply is
validated, or when a command is acknowledged but does nothing.

Byte 90 is reserved and stays `0x00`; the EC returns it as `0x00` too.

A response echoes the request's `command_class` and `command_id` and carries a
recomputed checksum, so both directions validate the same way.

## Commands

`zone` is `1` for the CPU and `2` for the GPU. Write commands are sent for both
zones so the two halves of the cooling system agree.

### Power and fan — class `0x0D`

| Command | ID | `data_size` | Arguments | Response |
| --- | --- | --- | --- | --- |
| Set power mode | `0x02` | 4 | `00`, `zone`, `mode`, `manual_fan` | status only |
| Set fan RPM | `0x01` | 3 | `00`, `zone`, `rpm/100` | status only |
| Set boost | `0x07` | 3 | `00`, `which`, `level` | status only |
| Get power mode | `0x82` | 4 | `00`, `zone`, `00`, `00` | `args[2]` = mode, `args[3]` = manual fan |
| Get fan target | `0x81` | 3 | `00`, `zone`, `00` | `args[2]` = RPM / 100 |
| Get boost | `0x87` | 3 | `00`, `which`, `00` | `args[2]` = level |

- `mode`: `0` balanced, `1` gaming, `2` creator, `4` custom. Value `3` is
  undefined; the reference implementations report that it trips an EC failsafe
  which runs the fans at maximum, so never send it.
- `manual_fan`: `1` puts the fan under host control, `0` returns it to the
  firmware curve.
- `which`: `1` CPU, `2` GPU. Boosts are only meaningful in custom mode.
- `level`: `0` low, `1` normal, `2` high, `3` boost (CPU only on models that
  advertise the `boost` feature).
- `rpm/100`: fan speed in 100 RPM units. This model accepts 3500–5000 RPM, so
  the value is 35–50.

#### Manual fan needs custom mode

This is the part that is easy to get wrong, and it is not obvious from the
arguments alone: with `mode` 0 or 1 the EC happily stores the setpoint and even
reports `manual_fan = 1`, but the fans keep following the firmware curve. The
setpoint is only acted on together with `mode = 4` (custom).

Working sequence for a fixed speed:

1. `0x02` for zone 1 and zone 2 with `mode = 4`, `manual_fan = 1`
2. `0x01` for zone 1 and zone 2 with the setpoint
3. in custom mode, optionally `0x07` for CPU and GPU boost levels

Both mode writes go out before any setpoint, which is the order the reference
implementations use. Returning to automatic is just step 1 with
`manual_fan = 0`; no setpoint write is needed.

The fans ramp rather than jump: a 5000 → 3500 change takes roughly 5–6 seconds,
which is why a quick listen can miss it.

### Battery Health Optimizer — class `0x07`
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
| Set LED state | `0x00` | 3 | `VARSTORE`, `target`, `0|1` |
| Get LED state | `0x80` | 3 | `VARSTORE`, `target`, `00` → `args[2]` |
| Set logo effect | `0x02` | 3 | `VARSTORE`, `LOGO_LED`, `0x02` (breathing) |
| Set brightness | `0x03` | 3 | `VARSTORE`, `target`, `0..255` |
| Get brightness | `0x83` | 3 | `VARSTORE`, `target`, `00` → `args[2]` |
| Set standard effect | `0x0A` | 1-9 | `effect_id`, params (see below) |
| Set custom frame | `0x0B` | 52 | `0xFF`, `row`, `00`, `0x0F`, 45 colour bytes at offset 7 |

Constants: `NOSTORE = 0x00`, `VARSTORE = 0x01`, `LOGO_LED = 0x04`,
`BACKLIGHT_LED = 0x05`.

Effect ids: `0x00` off, `0x01` wave, `0x02` reactive, `0x03` breathing,
`0x04` spectrum, `0x05` custom frame, `0x06` static, `0x19` starlight.

#### Keyboard effects

`data_size` is the real argument count. A padded 80-byte payload is accepted
too, which is why it worked before the layouts were known, but there is no
reason to send it.

| Effect | `data_size` | Arguments |
| --- | --- | --- |
| off | 1 | `00` |
| wave | 2 | `01`, direction (`01` or `02`) |
| reactive | 5 | `02`, speed `1..4`, `R G B` |
| breathing, one colour | 5 | `03 01 R G B` |
| breathing, random | 2 | `03 03` |
| spectrum | 1 | `04` |
| static | 4 | `06 R G B` |
| starlight, one colour | 9 | `19 01 speed 1..3 R G B 00 00 00` |
| starlight, random | 3 | `19 03 speed 1..3` |

All of them were sent to the 2022 Blade 14 and produced the expected animation.
The mapping of wave direction `01`/`02` to physical left/right is not confirmed.

#### The logo LED is special

Three things differ from every other LED command, and all three have to be
right or the command is acknowledged with nothing happening:

- **transaction id `0xFF`**, not `0x1F`
- **state, not effect**: `0x03/0x00` with `0|1` switches it. `0x03/0x02` with
  `0x02` is the documented breathing mode, but the Blade firmware calls it
  unsupported and it has not been verified here
- **its own brightness**: `0x03/0x03` with `LOGO_LED` must be non-zero, so turn
  the brightness up before switching the state on

Reading it back uses `0x03/0x80` (get LED state), **not** `0x03/0x82`. The `0x82`
variant answers `0` no matter what the LED is doing, which is a convincing way
to conclude the hardware has no logo at all.

Verified sequence on this model (the lid logo visibly lights up):

```
03/03  01 04 FF    logo brightness to maximum
03/00  01 04 01    logo on
03/80  01 04 00    read state -> args[2] = 1
```

## Sequence for a write

1. Build the packet, pad arguments to 80 bytes, compute the CRC.
2. `HIDIOCSFEATURE(91)` with the buffer (first byte is the report number `0`).
3. Wait a few milliseconds.
4. `HIDIOCGFEATURE(91)` into a zeroed buffer.
5. Decode, verify the reply checksum, verify the echoed class/id and that
   `data_size` matches, require status `0x02`.
6. Retry up to 3 times; the device occasionally answers late.

Measuring with `strace -e ioctl` is enough to see the exchange; `HIDIOCGFEATURE`
returns all 91 bytes, so no `read()` loop is needed.

## Open questions

These are not needed for the features above, but are the interesting next steps
(see [ROADMAP.md](../ROADMAP.md)):

- reading the **actual** fan RPM: `0x0D/0x81` returns the setpoint, and no
  tachometer command is known for this model
- MUX switch / Optimus state
- display refresh-rate switching on models that Synapse handles
- GPU TGP limits
