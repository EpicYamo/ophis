# Animations

The keyboard is a 6x16 RGB matrix. The firmware can run its own effects, but
they are limited and cannot be controlled beyond colour, speed and direction.
Ophis takes the other route: it renders the matrix itself and writes whole
frames.

## Frame protocol

One frame is six feature reports plus one activation command:

| Report | `data_size` | Arguments |
| --- | --- | --- |
| `0x03/0x0B` | 52 | `FF`, row `0..5`, `00`, `0F`, 16 x `R G B` |
| `0x03/0x0A` | 2 | `05 00` — activate the custom frame |

`0x03/0x0B` carries the row index at `args[1]`, the start column (`0x00`), the
end column (`0x0F`) and 48 colour bytes. The leading `0xFF` is part of the
frame encoding, not a transaction id.

The activation command only has to be sent once when entering custom-frame
mode; the rows can then be updated continuously.

## Frame rate

Measured on the Blade 14 (2022):

| Method | Frame time | Frames per second |
| --- | --- | --- |
| Write + read the response for every row | 42 ms | ~24 |
| Write only (`HIDIOCSFEATURE`, no read) | 18 ms | ~55 |

Ophis uses the full request/response cycle at 24 fps. It is slower than the
write-only path, but every frame is acknowledged by the controller, and 24 fps
is already smoother than Synapse's own per-key effects on this machine.

Two safety rules in `engine.py`:

- a frame that takes longer than 140 ms is counted as slow,
- ten slow frames in a row stop the animation and leave a static colour.

## Effects

Each effect subclasses `Effect` and implements:

```python
def render(self, frame: int, seconds: float) -> Matrix
```

`Matrix` is `list[list[(r, g, b)]]` with `6` rows and `16` columns. Stateful
effects (sparkle, rain, lightning, matrix, flame) keep their own buffers and
advance them from `seconds`, so they stay smooth if a frame is dropped.

Parameters live in `Params`: primary and secondary colour, speed, wave angle,
sparkle density.

| Name | State | Notes |
| --- | --- | --- |
| `static` | no | fills the matrix, used by the per-key editor |
| `breathing` | no | sine pulse of the primary colour |
| `wave` | no | projection on `angle`, blends primary and secondary |
| `wheel` | no | radial rainbow rotating around the centre |
| `sparkle` | yes | random cells fade out, refilled up to `density` |
| `rain` | yes | one head per column, four-cell trail |
| `lightning` | yes | short vertical bolts with decay |
| `matrix` | yes | green rain, bright head, per-column speeds |
| `flame` | yes | noise flicker weighted towards the bottom row |

## Adding an effect

1. Subclass `Effect` in `src/ophis/animations/effects.py`.
2. Register it in the `EFFECTS` dictionary.
3. Add a row to `HOST_ANIMATIONS` in `src/ophis/gui/window.py` if it should be
   selectable in the window.

No protocol knowledge is needed: render a matrix and the engine does the rest.
