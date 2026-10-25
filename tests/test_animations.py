import unittest

from ophis.animations import COLS, ROWS, default_params, hue_colour
from ophis.animations import effects


class EffectTests(unittest.TestCase):
    def assert_matrix(self, matrix):
        self.assertEqual(len(matrix), ROWS)
        for row in matrix:
            self.assertEqual(len(row), COLS)
            for colour in row:
                self.assertEqual(len(colour), 3)
                for channel in colour:
                    self.assertGreaterEqual(channel, 0, colour)
                    self.assertLessEqual(channel, 255, colour)

    def test_every_effect_renders_a_valid_matrix(self):
        for name in effects.EFFECTS:
            effect = effects.create(name, default_params(name))
            for _ in range(3):
                self.assert_matrix(effect.render(0.04))

    def test_static_uses_one_colour_per_zone(self):
        params = default_params("static")
        params.zone_count = 1
        params.zone_colours[0] = (10, 20, 30)
        matrix = effects.create("static", params).render(0.04)
        self.assert_matrix(matrix)
        self.assertTrue(all(cell == (10, 20, 30) for row in matrix for cell in row))

    def test_static_vertical_zones_split_columns(self):
        params = default_params("static")
        params.horizontal = False
        params.zone_count = 2
        params.zone_colours[0] = (255, 0, 0)
        params.zone_colours[1] = (0, 0, 255)
        matrix = effects.create("static", params).render(0.04)
        self.assertEqual(matrix[0][0], (255, 0, 0))
        self.assertEqual(matrix[0][COLS - 1], (0, 0, 255))

    def test_wave_changes_between_frames(self):
        params = default_params("wave")
        effect = effects.create("wave", params)
        first = effect.render(0.04)
        later = effect.render(0.04)
        self.assertNotEqual(first, later)

    def test_breathing_pulses(self):
        params = default_params("breathing")
        effect = effects.create("breathing", params)
        levels = []
        for _ in range(80):
            matrix = effect.render(0.04)
            levels.append(sum(sum(cell) for row in matrix for cell in row))
        self.assertGreater(max(levels), min(levels) * 3)

    def test_reference_defaults(self):
        wave = default_params("wave")
        self.assertEqual(wave.angle, 0)
        self.assertAlmostEqual(wave.speed, 3.87, places=2)
        breathing = default_params("breathing")
        # Percentages of the range that actually works: 0.2-8 speed and
        # 8-120 smoothness, not the reference's 1-40 and 2-150.
        self.assertGreaterEqual(breathing.speed, 0.2)
        self.assertLessEqual(breathing.speed, 8.0)
        self.assertGreaterEqual(breathing.smooth, 8.0)
        self.assertLessEqual(breathing.smooth, 120.0)
        sparkle = default_params("sparkle")
        self.assertEqual((sparkle.speed, sparkle.density), (5, 8))
        lightning = default_params("lightning")
        self.assertAlmostEqual(lightning.speed, 5.0, places=2)
        self.assertEqual(
            (lightning.smooth, lightning.width, lightning.concurrent), (10, 2, 1)
        )
        wheel = default_params("wheel")
        self.assertFalse(wheel.reverse)
        self.assertAlmostEqual(wheel.speed, 3.87, places=2)
        flame = default_params("flame")
        self.assertEqual((flame.speed, flame.smooth), (5, 8))
        rain = default_params("rain")
        self.assertAlmostEqual(rain.speed, 2.0, places=2)
        self.assertEqual((rain.density, rain.palette_count), (3, 1))
        matrix = default_params("matrix")
        self.assertEqual((matrix.speed, matrix.style, matrix.density), (5, 0, 2))

    def test_every_effect_declares_settings(self):
        for name, effect in effects.EFFECTS.items():
            self.assertTrue(effect.SETTINGS, name)
            for setting in effect.SETTINGS:
                self.assertIn(
                    setting.kind,
                    ("slider", "percent", "switch", "choice", "colour", "palette", "zone_colours"),
                )

    def test_animation_speeds_respect_their_ceilings(self):
        self.assertLessEqual(default_params("lightning").speed, 6.0)
        for name in ("wave", "wheel"):
            params = default_params(name)
            self.assertLessEqual(params.speed, 12.0)
            self.assertGreater(params.speed, 0.0)

    def test_percent_settings_stay_inside_their_range(self):
        for effect_class in effects.EFFECTS.values():
            for setting in effect_class.SETTINGS:
                if setting.kind != "percent":
                    continue
                self.assertLess(setting.actual_low, setting.actual_high)
                self.assertGreaterEqual(setting.default, 1)
                self.assertLessEqual(setting.default, 100)

    def test_unknown_effect_raises(self):
        with self.assertRaises(ValueError):
            effects.create("nope")

    def test_hue_colour_matches_the_reference(self):
        self.assertEqual(hue_colour(0), (255, 0, 0))
        self.assertEqual(hue_colour(120), (0, 255, 0))
        self.assertEqual(hue_colour(240), (0, 0, 255))
        self.assertEqual(hue_colour(360), (255, 0, 0))


if __name__ == "__main__":
    unittest.main()
