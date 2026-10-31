# Finger Pods — data collection, training, live typing

Right hand only, three QWERTY rows. One physical button can emit
different keystrokes depending on hand pose: the button index tells the
model *which finger/button fired*, the magnetometer vector at the press
moment tells it *which key that finger was reaching for*.

| Row | Keys (right hand) |
| --- | --- |
| Top | `y u i o p` |
| Home | `h j k l ;` |
| Bottom | `n m , . /` |
| Thumb | `SPACE` |

Finger assignment is standard touch-typing: index covers `y/u, h/j, n/m`,
middle `i, k, ,`, ring `o, l, .`, pinky `p, ;, /`.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r host/requirements.txt
```

## 1. Flash the streaming firmware

Copy [firmware/stream.py](../firmware/stream.py) to the QT Py as
`code.py`, together with `firmware/button_latch.py` (with
`adafruit_mlx90393` and `adafruit_tca9548a` in `lib/`).
It streams `t_ms, 9x magnetometer, 9x buttons` as CSV at 115200 baud.
Buttons are polled between magnetometer reads and presses are latched
until emitted, and the magnetometers use a fast conversion setting
(~3 ms/read instead of the ~220 ms library default), so quick taps
are not lost between samples.
Check the `# buttons:` / `# sensors` diagnostics in a serial console —
and make sure `BUTTON_PIN_NAMES` order in that file matches your wiring.

## 2. Collect data

```bash
python host/collect.py --port /dev/cu.usbmodemXXXX --reps 20
```

Rest your hand for the 3 s calibration, then press the pod for each
prompted key. Prompts are shuffled, never blocked by key. Output lands
in `data/` as `session_*.csv` (one row per press, model-ready), a raw
`*_stream.csv`, and a `.json` with the rest-pose baseline.

Pressed the wrong key? While the next prompt is waiting, press
Backspace (or Delete, or `u`) on the host keyboard: the most recent
press is deleted, its key is re-prompted next, and the deletion is
counted as `presses_deleted` in the session `.json`. Only undo a
genuinely wrong key — a correct-but-sloppy press is useful training
data, so keep those.

Collect **at least two sessions, taking the clips off and putting them
back on in between**. One session can look great and still fail the
moment the clips move.

No hardware handy? `python host/collect.py --simulate --reps 5`
fabricates a synthetic session so the rest of the pipeline can be tried.

## 3. Train

```bash
python host/train.py            # uses all data/session_*.csv
```

Prints a confusion matrix, stratified CV accuracy, and — with 2+
sessions — leave-one-session-out accuracy, which is the number to
trust. Saves `models/model.pkl` plus a `models/model.json` report.

## 4. Type live

```bash
python host/live.py --port /dev/cu.usbmodemXXXX
python host/live.py --simulate  # hardware-free demo of the model
```

Calibrates at startup, then prints predicted keys as you press.
