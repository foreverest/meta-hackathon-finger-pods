"""Press latching for the Finger Pods streamer.

Kept free of board imports (like ``sensor_discovery.py``) so the logic
can be unit-tested on a desktop.

Why this exists: magnetometer reads block for milliseconds, so buttons
can only be sampled between reads. A quick tap can start and end
between two *emitted samples*. Polling alone is therefore not enough --
a press seen by any poll is latched until it has been included in one
emitted sample, so no observed press is ever dropped. ``pending``
additionally lets the streamer emit a sample the moment a new press is
seen instead of waiting for the end of the magnetometer cycle.
"""


class PressLatch:
    """Latches button presses until they are emitted once."""

    def __init__(self, n_buttons):
        self._latched = [0] * n_buttons
        self._prev = [0] * n_buttons
        self._pending = False

    def poll(self, states):
        """Sample the current button states (1 = pressed).

        Call this as often as possible -- in the streamer, after every
        single magnetometer read. Any newly pressed button is latched
        and marks the latch pending (a new press worth emitting now).
        """
        for i, pressed in enumerate(states):
            if pressed:
                if not self._prev[i] and not self._latched[i]:
                    self._pending = True
                self._latched[i] = 1
        self._prev = list(states)

    @property
    def pending(self):
        """True when a new press has been latched but not yet emitted."""
        return self._pending

    def take_output(self, states):
        """Button values for the next emitted sample.

        Merges the latch with the current states (so held buttons keep
        reporting 1 after their latch is spent), then clears the latch:
        each distinct press is reported by at least one sample, and a
        tap that already ended still shows up exactly here, once.
        """
        out = [1 if (lat or cur) else 0
               for lat, cur in zip(self._latched, states)]
        self._latched = [0] * len(self._latched)
        self._pending = False
        return out
