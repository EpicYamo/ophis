# Effects

The keyboard is a 6x16 RGB matrix. Ophis renders it on the CPU and writes whole
frames, which is the only way to get effects the firmware does not have.

The effects, their parameter ranges and their defaults come from
[Better RGB](https://github.com/EpicYamo/Better-RGB-for-Tongfang-ITE8291), a C
application written for an ITE8291 keyboard. The maths is ported directly:

| Effect | Parameters |
| --- | --- |
| Breathing | colour, speed 0.2–8, smoothness 8–120 (both as percentages) |
| Wave | angle 0–359° (0), speed 0.5–12 (percentage) |
| Sparkle | speed 1–10 (5), density 3–20 keys (8) |
| Wheel | reverse (off), speed 0.5–12 (percentage) |
| Lightning | Custom mode (off), backlight colour and brightness 0–100% (5%), strike colour, speed 0.5–6 (percentage), smoothness 1–20 (10), strike width 1–4 (2), concurrent strikes 1–4 (1) |
| Flame | flicker speed 1–10 (5), smoothness 1–20 (8) |
| Rain | fall speed 0–4.5 (percentage, default 2.025), motion smoothness 0–100% (80%), density 1–5 (3), colour count 1–5 (1), optional backlight colour and brightness |
| Diagonal streaks | streak speed 0.02–0.8 (percentage), concurrent streaks 1–5 (2), colour count 1–3 (1), optional backlight colour and brightness |
| Vertical columns | column speed 0.1–2 (percentage), density 1–5 (2; 4–16 columns), colour count 1–3 (1), optional backlight colour and brightness |
| Ripple | ripple speed 0.1–2 (percentage), density 1–5 (2; 3–6 ripples), colour count 1–3 (1), optional backlight colour and brightness |
| Static | horizontal or vertical zones, 1–6 zones with one colour each, plus per-key paint |

Where the reference exposed a raw number that means nothing to a human, the
slider is a percentage over the range that actually works. Breathing above a
speed of about 8 stops looking like breathing and starts flickering; wave and
wheel above 12 are too fast to follow, and lightning above 6 skips whole rows.
Rain's lower speed floor is deliberately slower than the reference; its
motion-smoothing control samples travel between frames to reduce jumps. The
percentages map onto usable ranges instead of exposing raw reference values.

Each effect declares its controls as `SETTINGS` on the class, and the window
builds the panel from that declaration. Adding a parameter to an effect is one
line; there is no separate UI code to keep in sync.

Lightning's backlight brightness uses the same 0–100% linear scale as Rain and
the other Matrix-derived effects. Its colour and brightness controls remain
hidden until Custom mode is enabled.

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
- **Lightning** keeps the original blue-white bolt and near-black background
  unless Custom mode is enabled. In custom mode it interpolates the
  background-to-strike gradient along the shortest HSV hue path, so related
  colours blend naturally and unrelated colours still transition smoothly.
- **Flame** integrates a heat value per cell towards a row-biased random target
  and maps heat to black/red/yellow/white.
- **Rain** trails are drawn towards the nearest cell in each row, because the
  reference keymap is not a perfect grid.
- **Diagonal streaks**, **Vertical columns**, and **Ripple** are listed as
  separate effects. Each has an optional colour/brightness backlight. Diagonal
  streaks keep a consistent direction and staggered spacing; lowering density
  lets active streaks finish before retiring instead of cutting them off.
  Column density selects a distributed subset of keys, while ripple density
  increases the number of simultaneously expanding rings. The
  original laser sweep was dropped: it produced streaks that were cut in half
  at the board edges, and no speed looked right on a 6x16 matrix.
- **Static** splits rows (horizontal) or columns (vertical) into zones. Its
  per-key paint switch hands the board over to a manual 6x16 frame: drag to
  paint, right-click to erase, Fill and Clear for the whole board. The frame is
  stored in the profile and restored at startup.

## Frame rate

The reference runs one frame per 10 ms. Ophis runs at about 24 fps, so every
per-frame increment is multiplied by `dt / 0.010`. A wave therefore takes the
same number of seconds to cross the keyboard at either frame rate. Rain samples
the drop path within each rendered frame according to its motion-smoothing
setting, reducing visible jumps when the frame interval grows.

| Method | Frame time | Frames per second |
| --- | --- | --- |
| Write + read the response for every row | 42 ms | ~24 |
| Write only (`HIDIOCSFEATURE`, no read) | 18 ms | ~55 |

The acknowledged path is used: it is slower, but no stale responses are left
queued for the next command. If ten frames in a row take more than 140 ms, the
engine stops and leaves a static colour instead of hammering the controller.

## The key map

`data/keymap_blade14.json` maps X11 keycodes to matrix cells, produced with
`linux/tools/mapper.py`: the tool lights one cell, the owner presses the key that lit
up, and the keycode is recorded. Column 0 has no physical keys, and the space
bar has no LED on this model, so neither appears in the map.

The window draws the German ISO layout from `src/ophis/layouts.py`: tall
Enter with the ISO notch, right Shift resting above the arrow cluster, up/down
sharing one key width, and the function row slightly shorter than the rest.
The laptop has no PrtSc key: the last two keys are Del and the power button.
The space bar has no matrix LED; the power button does.

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
