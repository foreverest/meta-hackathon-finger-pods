"""Stdlib-only tests for the shared host definitions.

Run:  python3 -m unittest discover -s tests -v
"""

import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "host"))
import fingerpods as fp


class LayoutTest(unittest.TestCase):
    def test_three_rows_right_hand(self):
        self.assertEqual(len(fp.LABELS), 15)
        self.assertEqual(len(set(fp.LABELS)), 15)
        rows = {r: [k for k, (_f, rr) in fp.KEY_INFO.items() if rr == r]
                for r in fp.ROWS}
        self.assertEqual(sorted(rows["top"]), sorted(list("yuiop")))
        self.assertEqual(sorted(rows["home"]), sorted(["h", "j", "k", "l", ";"]))
        self.assertEqual(sorted(rows["bottom"]), sorted(["n", "m", ",", ".", "/"]))

    def test_one_button_can_emit_several_keys(self):
        # In simulation each finger owns one button, yet the index finger
        # alone must map to six different labels -- pose disambiguates.
        rng = random.Random(0)
        buttons_by_label = {}
        for label in fp.LABELS:
            _mag, buttons = fp.synthetic_press(label, rng)
            buttons_by_label[label] = fp.active_button(buttons)
        self.assertEqual(buttons_by_label["y"], buttons_by_label["h"])
        self.assertEqual(buttons_by_label["y"], buttons_by_label["n"])
        self.assertEqual(len({buttons_by_label[k] for k in "yuhjnm"}), 1)


class ProtocolTest(unittest.TestCase):
    def test_parse_roundtrip_shape(self):
        line = "123," + ",".join(["1.5"] * 9) + "," + ",".join(["0"] * 8 + ["1"])
        t_ms, mag, buttons = fp.parse_stream_line(line)
        self.assertEqual(t_ms, 123)
        self.assertEqual(len(mag), 9)
        self.assertEqual(fp.active_button(buttons), 8)

    def test_parse_ignores_diagnostics_and_junk(self):
        self.assertIsNone(fp.parse_stream_line("# hello"))
        self.assertIsNone(fp.parse_stream_line(""))
        self.assertIsNone(fp.parse_stream_line("1,2,3"))
        self.assertIsNone(fp.parse_stream_line("a,b,c"))

    def test_calibration_and_features(self):
        mag = [10.0] * 9
        cal = fp.calibrate(mag, [4.0] * 9)
        self.assertEqual(cal, [6.0] * 9)
        feats = fp.feature_vector(cal, [1] + [0] * 8)
        self.assertEqual(len(feats), len(fp.FEATURE_COLS))
        self.assertEqual(feats[-9], 1.0)

    def test_prompts_randomised_counts(self):
        prompts = fp.shuffled_prompts(3, seed=42)
        self.assertEqual(len(prompts), 45)
        for label in fp.LABELS:
            self.assertEqual(prompts.count(label), 3)


if __name__ == "__main__":
    unittest.main()
