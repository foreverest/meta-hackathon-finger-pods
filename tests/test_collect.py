"""Tests for the undo-last-press behaviour in host/collect.py.

Run:  python3 -m unittest discover -s tests -v
"""

import contextlib
import csv
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "host"))
import collect


def frame(buttons, t=1.0):
    return (t, int(t * 1000), [0.0] * 9, buttons)


REST = [0] * 9
PRESS = [1] + [0] * 8


class FakePoller:
    """UndoPoller stand-in returning a scripted sequence of poll() results."""

    def __init__(self, results=()):
        self._results = iter(results)

    def poll(self):
        return next(self._results, False)

    def open(self):
        return self

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class UndoInputTest(unittest.TestCase):
    def test_recognises_undo_keys(self):
        for data in ("u", "U", "\x7f", "\x08", "\x1b[3~"):
            self.assertTrue(collect.is_undo_input(data), repr(data))

    def test_ignores_other_keys(self):
        for data in ("", "x", "\r", "\n", "k"):
            self.assertFalse(collect.is_undo_input(data), repr(data))


class WaitForPressUndoTest(unittest.TestCase):
    def test_undo_returns_sentinel_before_press_is_consumed(self):
        press_frame = frame(PRESS, t=2.0)
        source = iter([frame(REST), frame(REST), press_frame])
        result = collect.wait_for_press(
            source, None, "h", undo_poller=FakePoller([False, True]))
        self.assertIs(result, collect.UNDO)
        self.assertIs(next(source), press_frame)

    def test_press_still_returned_without_undo(self):
        press_frame = frame(PRESS, t=2.0)
        source = iter([frame(REST), press_frame])
        result = collect.wait_for_press(
            source, None, "h", undo_poller=FakePoller())
        self.assertIs(result, press_frame)

    def test_wait_for_release_latches_undo_until_release(self):
        source = iter([frame(PRESS), frame(REST, t=2.0)])
        result = collect.wait_for_release(
            source, None, "h", undo_poller=FakePoller([True, False]))
        self.assertTrue(result)
        with self.assertRaises(StopIteration):
            next(source)

    def test_wait_for_release_without_undo_returns_false(self):
        source = iter([frame(REST)])
        self.assertFalse(collect.wait_for_release(
            source, None, "h", undo_poller=FakePoller()))


class UndoLastPressTest(unittest.TestCase):
    def test_pops_last_row_and_requeues_its_label_first(self):
        rows = [["s", 0, "h"], ["s", 1, "y"]]
        queue = ["k", "l"]
        removed = collect.undo_last_press(rows, queue)
        self.assertEqual(removed[2], "y")
        self.assertEqual([r[2] for r in rows], ["h"])
        self.assertEqual(queue, ["y", "k", "l"])

    def test_nothing_to_undo_is_a_noop(self):
        rows, queue = [], ["k"]
        self.assertIsNone(collect.undo_last_press(rows, queue))
        self.assertEqual(queue, ["k"])


class MainUndoIntegrationTest(unittest.TestCase):
    def test_simulated_session_deletes_and_reprompts(self):
        # Poll script: no undo on the first press, undo while it is
        # released, then no undo for the re-prompted press.
        scripted = FakePoller([False, True, False, False])
        original_poller = collect.UndoPoller
        original_argv = sys.argv
        collect.UndoPoller = lambda stream=None: scripted
        try:
            with tempfile.TemporaryDirectory() as tmp:
                sys.argv = ["collect.py", "--simulate", "--reps", "1",
                            "--keys", "h", "--out", tmp,
                            "--cal-seconds", "0.05", "--seed", "0",
                            "--no-stream"]
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(collect.main(), 0)
                csvs = list(Path(tmp).glob("session_*.csv"))
                metas = list(Path(tmp).glob("session_*.json"))
                self.assertEqual(len(csvs), 1)
                self.assertEqual(len(metas), 1)
                with open(csvs[0], newline="") as f:
                    rows = list(csv.DictReader(f))
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["label"], "h")
                self.assertEqual(rows[0]["press_idx"], "0")
                meta = json.loads(metas[0].read_text())
                self.assertEqual(meta["presses_recorded"], 1)
                self.assertEqual(meta["presses_deleted"], 1)
        finally:
            collect.UndoPoller = original_poller
            sys.argv = original_argv


if __name__ == "__main__":
    unittest.main()
