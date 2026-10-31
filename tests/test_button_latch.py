"""Tests for firmware/button_latch.py (stdlib only).

Regression: buttons used to be sampled once per magnetometer cycle
(~660 ms with default MLX90393 conversion settings), so a quick tap
that started and ended inside one cycle never appeared in the output.

Run:  python3 -m unittest discover -s tests -v
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "firmware"))
import button_latch


def states(*pressed):
    s = [0] * 9
    for i in pressed:
        s[i] = 1
    return s


class PressLatchTest(unittest.TestCase):
    def test_quick_tap_between_outputs_is_not_lost(self):
        # Press and release both happen between two emitted samples:
        # intermediate polls (taken between magnetometer reads) see the
        # press, and the next output must still report it exactly once.
        latch = button_latch.PressLatch(9)
        self.assertEqual(latch.take_output(states()), states())
        latch.poll(states(2))          # tap starts
        latch.poll(states())            # tap already over
        self.assertEqual(latch.take_output(states()), states(2))
        self.assertEqual(latch.take_output(states()), states())

    def test_new_press_is_pending_immediately_for_event_output(self):
        latch = button_latch.PressLatch(9)
        self.assertFalse(latch.pending)
        latch.poll(states(0))
        self.assertTrue(latch.pending)
        latch.take_output(states(0))
        self.assertFalse(latch.pending)

    def test_held_button_does_not_retrigger_pending(self):
        latch = button_latch.PressLatch(9)
        latch.poll(states(1))
        latch.take_output(states(1))   # event emitted, still held
        latch.poll(states(1))
        self.assertFalse(latch.pending)
        # ...but ordinary samples still show the held button via the
        # current state, not the latch.
        self.assertEqual(latch.take_output(states(1)), states(1))

    def test_simultaneous_and_successive_buttons(self):
        latch = button_latch.PressLatch(9)
        latch.poll(states(0, 8))
        latch.poll(states(8))           # b0 released, b8 still down
        self.assertEqual(latch.take_output(states(8)), states(0, 8))
        latch.poll(states(3))
        self.assertEqual(latch.take_output(states()), states(3))


if __name__ == "__main__":
    unittest.main()
