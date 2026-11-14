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
        self.assertAlmostEqual(rain.speed, 2.025, places=2)
        self.assertEqual((rain.density, rain.palette_count), (3, 1))
        diagonal = default_params("matrix_diagonal")
        self.assertAlmostEqual(diagonal.speed, 0.293, places=2)
        self.assertEqual(diagonal.density, 2)
        self.assertEqual(
            {"matrix_diagonal", "matrix_columns", "matrix_ripple"} & set(effects.EFFECTS),
            {"matrix_diagonal", "matrix_columns", "matrix_ripple"},
        )
        self.assertNotIn("matrix", effects.EFFECTS)

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
                self.assertGreaterEqual(setting.default, setting.low)
                self.assertLessEqual(setting.default, setting.high)

    def test_custom_lightning_uses_a_hue_coherent_gradient(self):
        orange_to_red = effects.blend_hsv((255, 165, 0), (255, 0, 0), 0.5)
        self.assertEqual(orange_to_red, (255, 82, 0))
        green_to_blue = effects.blend_hsv((0, 255, 0), (0, 0, 255), 0.5)
        self.assertGreater(green_to_blue[1], 200)
        self.assertGreater(green_to_blue[2], 200)

        params = default_params("lightning")
        params.custom_colors = True
        params.background_colour = (255, 165, 0)
        params.strike_colour = (255, 0, 0)
        effect = effects.create("lightning", params)
        effect.head[0] = 1.0
        effect.bolt_x[0] = 5.0
        matrix = effect.render(0.0)
        self.assertEqual(matrix[1][5], params.strike_colour)
        self.assertTrue(
            any(cell[0] == 255 and 0 < cell[1] < 165 and cell[2] == 0
                for row in matrix for cell in row)
        )

    def test_lightning_background_brightness_only_affects_custom_colours(self):
        params = default_params("lightning")
        params.custom_colors = True
        params.background_colour = (200, 40, 20)
        params.background_brightness = 25
        self.assertEqual(params.copy().background_brightness, 25)
        custom = effects.create("lightning", params).render(0.0)
        self.assertTrue(all(cell == (200, 40, 20) for row in custom for cell in row))

        params.custom_colors = False
        original = effects.create("lightning", params).render(0.0)
        self.assertTrue(all(cell == (4, 4, 14) for row in original for cell in row))

    def test_rain_backlight_and_motion_smoothing(self):
        params = default_params("rain")
        params.backlight = True
        params.backlight_colour = (0, 100, 200)
        params.backlight_brightness = 10
        effect = effects.create("rain", params)
        effect.drop_row = [100.0] * effect.MAX_DROPS
        effect.colour_index = [0] * effect.MAX_DROPS
        self.assertTrue(
            all(cell == (0, 10, 20) for row in effect.render(0.04) for cell in row)
        )

        def rendered_cells(smoothness):
            values = default_params("rain")
            values.speed = 4.5
            values.smooth = smoothness
            values.density = 1
            rain = effects.create("rain", values)
            rain.drop_row = [100.0] * rain.MAX_DROPS
            rain.drop_row[0] = 0.0
            rain.drop_x = [5.0] * rain.MAX_DROPS
            rain.colour_index = [0] * rain.MAX_DROPS
            frame = rain.render(0.2)
            return sum(sum(cell) for row in frame for cell in row)

        self.assertGreater(rendered_cells(100), rendered_cells(0))

    def test_backlight_is_available_on_each_matrix_animation(self):
        for name in ("matrix_diagonal", "matrix_columns", "matrix_ripple"):
            params = default_params(name)
            params.backlight = True
            params.backlight_colour = (100, 40, 20)
            params.backlight_brightness = 25
            effect = effects.create(name, params)
            frame = effect.render(0.0)
            self.assert_matrix(frame)
            self.assertIn((25, 10, 5), [cell for row in frame for cell in row])

    def test_diagonal_streaks_keep_their_path_and_finish_when_density_drops(self):
        params = default_params("matrix_diagonal")
        params.speed = 0.8
        effect = effects.create("matrix_diagonal", params)
        angles = list(effect.angle)
        colours = list(effect.streak_colour)

        effect.params.density = 1
        effect.render(0.04)
        self.assertEqual(sum(effect.streak_enabled), 2)
        self.assertEqual(sum(effect.streak_retiring), 1)

        for _ in range(400):
            effect.render(0.04)
        self.assertEqual(effect.angle, angles)
        self.assertEqual(effect.streak_colour, colours)
        self.assertEqual(sum(effect.streak_enabled), 1)
        self.assertEqual(sum(effect.streak_retiring), 0)

    def test_vertical_column_density_selects_more_columns(self):
        def lit_columns(density):
            params = default_params("matrix_columns")
            params.density = density
            effect = effects.create("matrix_columns", params)
            effect.col_position = [1.0] * COLS
            frame = effect.render(0.0)
            return sum(any(frame[row][col] != effects.BLACK for row in range(ROWS))
                       for col in range(COLS))

        self.assertEqual(lit_columns(1), 4)
        self.assertEqual(lit_columns(5), COLS)

    def test_ripple_density_increases_simultaneous_ripples(self):
        def lit_keys(density):
            params = default_params("matrix_ripple")
            params.density = density
            effect = effects.create("matrix_ripple", params)
            effect.ripple_x = [0.0] * effect.RIPPLES
            effect.ripple_y = [0.0] * effect.RIPPLES
            effect.ripple_radius = [float(index) for index in range(effect.RIPPLES)]
            frame = effect.render(0.0)
            return sum(cell != effects.BLACK for row in frame for cell in row)

        self.assertGreater(lit_keys(5), lit_keys(1))

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
