# Effects

The keyboard is a 6x16 RGB matrix. Ophis renders it on the CPU and writes whole
frames, which is the only way to get effects the firmware does not have.

The effects, their parameter ranges and their defaults come from
[Better RGB](https://github.com/EpicYamo/Better-RGB-for-Tongfang-ITE8291), a C
application written for an ITE8291 keyboard. The maths is ported directly:

| Effect | Parameters (range, default) |
| --- | --- |
| Breathing | colour, speed 1–40 (12), smoothness 2–150 (60) |
| Wave | angle 0–359° (0), speed 1–20 (4) |
| Sparkle | speed 1–10 (5), density 3–20 keys (8) |
| Wheel | reverse (off), speed 1–20 (4) |
| Lightning | speed 1–10 (5), smoothness 1–20 (10), strike width 1–4 (2), concurrent strikes 1–4 (1) |
| Flame | flicker speed 1–10 (5), smoothness 1–20 (8) |
| Rain | fall speed 1–10 (5), density 1–5 (3), colour count 1–5 (1) |
| Matrix | streak speed 1–10 (5), style (diagonal / columns / laser / ripple), density 1–5 (2), colour count 1–3 (1) |
| Static | horizontal or vertical zones, 1–6 zones, one colour each |

Each effect declares its controls as `SETTINGS` on the class, and the window
builds the panel from that declaration. Adding a parameter to an effect is one
line; there is no separate UI code to keep in sync.

## Reference behaviour that is reproduced

- **Breathing** quantises the sine into `smoothness` levels, which is why it
  looks stepped at low values instead of perfectly smooth.
- **Wave** projects each cell on the angle vector and steps the hue by 15° per
  unit of projection, so the angle changes the stripe width as well as the
  direction.
- **Sparkle** gives every spark a random colour and fades it over
  `50 - speed*4` frames (minimum 8); the chosen colour is not used.
- **Wheel** uses the angle from the matrix centre, and reverse flips the
  rotation direction rather than the colours.
- **Lightning** uses a blue-white bolt over a near-black background, with the
  strike width and glow controlled independently.
- **Flame** integrates a heat value per cell towards a row-biased random target
  and maps heat to black/red/yellow/white.
- **Rain** trails are drawn towards the nearest cell in each row, because the
  reference keymap is not a perfect grid.
- **Matrix** has four styles; density only affects the diagonal and laser
  styles, exactly as in the original panel.
- **Static** splits rows (horizontal) or columns (vertical) into zones.

## Frame rate

The reference runs one frame per 10 ms. Ophis runs at about 24 fps, so every
per-frame increment is multiplied by `dt / 0.010`. A wave therefore takes the
same number of seconds to cross the keyboard at either frame rate.

| Method | Frame time | Frames per second |
| --- | --- | --- |
| Write + read the response for every row | 42 ms | ~24 |
| Write only (`HIDIOCSFEATURE`, no read) | 18 ms | ~55 |

The acknowledged path is used: it is slower, but no stale responses are left
queued for the next command. If ten frames in a row take more than 140 ms, the
engine stops and leaves a static colour instead of hammering the controller.

## Frame protocol

| Report | `data_size` | Arguments |
| --- | --- | --- |
| `0x03/0x0B` | 52 | `FF`, row `0..5`, `00`, `0F`, 16 x `R G B` |
| `0x03/0x0A` | 2 | `05 00` — activate the custom frame |

Activation is needed once; rows can then be rewritten continuously.

## Adding an effect

1. Subclass `Effect` in `src/ophis/animations/effects.py`.
2. Declare `SETTINGS` for the controls it needs.
3. Register it in `EFFECTS` and add a row to `HOST_EFFECTS` in
   `src/ophis/gui/lighting.py`.
4. Give it defaults in `default_params`.

The window builds the panel automatically from `SETTINGS`.
