"""Shared definitions for Finger Pods host tools.

Right-hand-only layout over three QWERTY rows. One physical button can
emit different keystrokes depending on hand pose: the button index is a
feature, not the label. The magnetometer vector at the press moment is
what disambiguates keys that share a button/finger.

Stream protocol (from firmware/stream.py), one CSV line per sample:
    t_ms,m0x,m0y,m0z,m1x,m1y,m1z,m2x,m2y,m2z,b0,...,b8
Lines starting with '#' are diagnostics and are ignored here.
"""

import random

# --- Layout: right hand, 3 rows -----------------------------------------
# (label, finger, row) -- standard touch-typing assignment for the
# right hand. ';' and '/' etc. are literal key labels.
KEYS = [
    # top row
    ("y", "index", "top"), ("u", "index", "top"),
    ("i", "middle", "top"),
    ("o", "ring", "top"),
    ("p", "pinky", "top"),
    # home row
    ("h", "index", "home"), ("j", "index", "home"),
    ("k", "middle", "home"),
    ("l", "ring", "home"),
    (";", "pinky", "home"),
    # bottom row
    ("n", "index", "bottom"), ("m", "index", "bottom"),
    (",", "middle", "bottom"),
    (".", "ring", "bottom"),
    ("/", "pinky", "bottom"),
]

LABELS = [label for label, _finger, _row in KEYS]
KEY_INFO = {label: (finger, row) for label, finger, row in KEYS}
FINGERS = ["thumb", "index", "middle", "ring", "pinky"]
ROWS = ["top", "home", "bottom"]

N_MAG = 9       # 3 magnetometers x XYZ
N_BUTTONS = 9   # b0..b8 as streamed by the firmware

MAG_COLS = [f"m{i}{axis}" for i in range(3) for axis in "xyz"]
CAL_COLS = [f"c{i}{axis}" for i in range(3) for axis in "xyz"]  # baseline-subtracted
BUTTON_COLS = [f"b{i}" for i in range(N_BUTTONS)]
FEATURE_COLS = CAL_COLS + BUTTON_COLS

# Columns of one recorded press in a session CSV.
SESSION_COLS = (
    ["session", "press_idx", "label", "finger", "row", "active_button",
     "t_device_ms", "t_host_s"]
    + [f"raw_{c}" for c in MAG_COLS]
    + CAL_COLS
    + BUTTON_COLS
)


def parse_stream_line(line):
    """Parse one firmware CSV line.

    Returns (t_ms, mag[9], buttons[9]) or None for diagnostics,
    blank lines, and malformed input.
    """
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    parts = line.split(",")
    if len(parts) != 1 + N_MAG + N_BUTTONS:
        return None
    try:
        t_ms = int(float(parts[0]))
        mag = [float(v) for v in parts[1:1 + N_MAG]]
        buttons = [int(float(v)) for v in parts[1 + N_MAG:]]
    except ValueError:
        return None
    return t_ms, mag, buttons


def active_button(buttons):
    """Index of the first pressed button, or -1 when none is pressed."""
    for i, b in enumerate(buttons):
        if b:
            return i
    return -1


def calibrate(mag, baseline):
    """Subtract a rest-pose baseline (list of 9) from a mag reading."""
    return [m - b for m, b in zip(mag, baseline)]


def feature_vector(cal_mag, buttons):
    """Model input: calibrated magnetometers + raw button states."""
    return list(cal_mag) + [float(b) for b in buttons]


# --- Synthetic data (hardware-free testing / demos) ----------------------
# Each finger owns one "primary" button in simulation, so several labels
# share a button exactly like the real device. Poses differ per key.
_SIM_BUTTON = {"index": 0, "middle": 1, "ring": 2, "pinky": 3, "thumb": 4}
_SIM_ROW_OFFSET = {"top": -18.0, "home": 0.0, "bottom": 18.0}
_SIM_FINGER_BASE = {
    "index": [35.0, -20.0, 55.0, 10.0, 25.0, -30.0, -15.0, 5.0, 40.0],
    "middle": [5.0, 30.0, 20.0, -25.0, -10.0, 45.0, 20.0, -35.0, 10.0],
    "ring": [-20.0, 10.0, 35.0, 30.0, -40.0, 5.0, -5.0, 20.0, -25.0],
    "pinky": [50.0, 15.0, -10.0, -30.0, 20.0, 25.0, 35.0, -15.0, -5.0],
    "thumb": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
}
# Index covers two columns per row (y/u, h/j, n/m): offset by column.
_SIM_COL_OFFSET = {"y": -12.0, "u": 12.0, "h": -12.0, "j": 12.0,
                   "n": -12.0, "m": 12.0}


def synthetic_press(label, rng, baseline=None):
    """Fake (mag, buttons) for one press of `label`. For tests/demos."""
    finger, row = KEY_INFO[label]
    base = _SIM_FINGER_BASE[finger]
    row_off = _SIM_ROW_OFFSET[row]
    col_off = _SIM_COL_OFFSET.get(label, 0.0)
    mag = []
    for i, b in enumerate(base):
        v = b + (row_off if i % 3 == 0 else 0.0) + (col_off if i % 3 == 1 else 0.0)
        v += rng.gauss(0.0, 3.0)
        if baseline is not None:
            v += baseline[i]
        mag.append(round(v, 2))
    buttons = [0] * N_BUTTONS
    buttons[_SIM_BUTTON[finger]] = 1
    return mag, buttons


def synthetic_baseline(rng):
    return [rng.gauss(20.0, 2.0) for _ in range(N_MAG)]


def shuffled_prompts(reps, labels=None, seed=None):
    """Randomised prompt order -- never blocked by label, so slow drift
    (fatigue, clip slip) cannot correlate with the label."""
    labels = list(labels) if labels else list(LABELS)
    prompts = labels * reps
    random.Random(seed).shuffle(prompts)
    return prompts
