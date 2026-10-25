import json
import tempfile
import unittest
from pathlib import Path

from ophis import profile
from ophis.backend import MockBackend


class ProfileTests(unittest.TestCase):
    def test_defaults_are_complete(self):
        data = profile.load(Path("/nonexistent/profile.json"))
        self.assertEqual(data["power"]["mode"], "balanced")
        self.assertIn("lighting", data)
        self.assertIn("curve", data)

    def test_save_and_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "profile.json"
            data = profile.load()
            data["power"]["mode"] = "gaming"
            data["fan"] = {"mode": "manual", "rpm": 4200}
            profile.save(data, path)
            loaded = profile.load(path)
            self.assertEqual(loaded["power"]["mode"], "gaming")
            self.assertEqual(loaded["fan"]["rpm"], 4200)
            # unknown keys survive, missing keys are filled in
            self.assertIn("battery", loaded)

    def test_broken_file_falls_back_to_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "profile.json"
            path.write_text("{not json", encoding="utf-8")
            self.assertEqual(profile.load(path)["power"]["mode"], "balanced")

    def test_apply_pushes_every_section(self):
        backend = MockBackend()

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "profile.json"
            data = json.loads(json.dumps(profile.DEFAULT))
            data["power"]["mode"] = "gaming"
            data["fan"] = {"mode": "manual", "rpm": 4500}
            data["lighting"].update({"effect": "breathing", "colour": [1, 2, 3]})
            data["battery"] = {"limit_enabled": True, "threshold": 60}
            profile.save(data, path)
            warnings = profile.apply(backend, profile.load(path))

        # On hardware a manual fan also switches the profile to custom; the
        # mock only records the two writes, and `apply` warns about the switch.
        self.assertEqual(int(backend.state.power_mode), int(profile.POWER_NAMES["gaming"]))
        self.assertEqual(backend.state.fan_rpm, 4500)
        self.assertEqual(backend.state.extra["effect"], 0x03)
        self.assertEqual(backend.state.extra["color"], (1, 2, 3))
        self.assertTrue(backend.state.bho_enabled)
        self.assertEqual(backend.state.bho_threshold, 60)
        self.assertTrue(any("custom profile" in warning for warning in warnings))


if __name__ == "__main__":
    unittest.main()
