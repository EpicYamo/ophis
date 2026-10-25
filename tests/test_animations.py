import unittest

from ophis.animations import COLS, ROWS, Params, create, hue_colour
from ophis.animations import effects


class EffectTests(unittest.TestCase):
    def assert_matrix(self, matrix):
        self.assertEqual(len(matrix), ROWS)
        for row in matrix:
            self.assertEqual(len(row), COLS)
            for colour in row:
                self.assertEqual(len(colour), 3)
                for channel in colour:
                    self.assertGreaterEqual(channel, 0)
                    self.assertLessEqual(channel, 255)

    def test_every_effect_renders_a_valid_matrix(self):
        params = Params(colour=(200, 40, 10), secondary=(0, 90, 255))
        for name in effects.ANIMATIONS:
            effect = create(name, params)
            for frame in (0, 1, 7):
                self.assert_matrix(effect.render(frame, frame * 0.04))

    def test_static_is_uniform(self):
        matrix = create("static", Params(colour=(10, 20, 30))).render(0, 0.0)
        self.assert_matrix(matrix)
        self.assertTrue(all(colour == (10, 20, 30) for row in matrix for colour in row))

    def test_wave_changes_over_time(self):
        effect = create("wave", Params(colour=(255, 0, 0), secondary=(0, 0, 255)))
        first = effect.render(0, 0.0)
        later = effect.render(1, 0.4)
        self.assertNotEqual(first, later)

    def test_breathing_pulses_between_dark_and_bright(self):
        effect = create("breathing", Params(colour=(255, 255, 255), speed=1.0))
        frames = [effect.render(index, index * 0.1) for index in range(40)]
        brightest = max(sum(sum(colour) for row in frame for colour in row) for frame in frames)
        darkest = min(sum(sum(colour) for row in frame for colour in row) for frame in frames)
        self.assertGreater(brightest, darkest * 3)

    def test_unknown_effect_raises(self):
        with self.assertRaises(ValueError):
            create("nope")

    def test_hue_colour_spans_the_wheel(self):
        red = hue_colour(0.0)
        green = hue_colour(1 / 3)
        blue = hue_colour(2 / 3)
        self.assertEqual(red, (255, 0, 0))
        self.assertEqual(green, (0, 255, 0))
        self.assertEqual(blue, (0, 0, 255))


if __name__ == "__main__":
    unittest.main()
