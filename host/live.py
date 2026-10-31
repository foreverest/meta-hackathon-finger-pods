#!/usr/bin/env python3
"""Live Finger Pods typing: predict keys as you press the pods.

Usage (from the repo root, with the project venv active):
    python host/live.py --port /dev/cu.usbmodemXXXX
    python host/live.py --simulate   # demo without hardware

Calibrates a rest-pose baseline at startup (same as collect.py), then
prints each predicted key on the press edge and accumulates the typed
text. The same button will produce different characters depending on
pose -- that is the model doing its job.
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fingerpods as fp
from collect import (SerialSource, SimulateSource, collect_baseline,
                     find_port, wait_for_press, wait_for_release)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", default=None)
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--model", default="models/model.pkl")
    ap.add_argument("--cal-seconds", type=float, default=3.0)
    ap.add_argument("--simulate", action="store_true",
                    help="demo with fabricated presses (types 'typing' poses)")
    ap.add_argument("--demo-text", default="hjukiolp;nm,./y",
                    help="labels to fake in --simulate mode")
    args = ap.parse_args()

    import joblib

    bundle = joblib.load(args.model)
    model, feature_cols = bundle["model"], bundle["feature_cols"]
    print(f"Model: {bundle.get('n_presses', '?')} training presses, "
          f"labels {bundle['labels']}")

    if args.simulate:
        import random

        source = SimulateSource(seed=1)
        demo = [c for c in args.demo_text if c in fp.KEY_INFO]
    else:
        port = args.port or find_port()
        if not port:
            ap.error("no serial port found - pass --port (or use --simulate)")
        print(f"Opening {port}...")
        source = SerialSource(port, args.baud)
        demo = []
    source_iter = iter(source.frames())
    baseline = collect_baseline(source_iter, args.cal_seconds)
    if args.simulate:
        source.baseline = baseline

    print("\nStart pressing the pods. Ctrl-C to stop.\nTyped: ", end="", flush=True)
    typed = []
    try:
        demo_iter = iter(demo)
        while True:
            if args.simulate:
                label = next(demo_iter, None)
                if label is None:
                    break
                source.pending_label = label
            frame = wait_for_press(source_iter, None, "", timeout_s=3600)
            if frame is None:
                continue
            _th, _td, mag, buttons = frame
            cal = fp.calibrate(mag, baseline)
            feats = fp.feature_vector(cal, buttons)
            # Feature order must match training exactly.
            assert len(feats) == len(feature_cols), (feats, feature_cols)
            pred = model.predict([feats])[0]
            typed.append(pred)
            print(pred, end="", flush=True)
            wait_for_release(source_iter, None, "")
    except KeyboardInterrupt:
        pass
    print(f"\n\nYou typed: {''.join(typed)!r}  ({len(typed)} keys)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
