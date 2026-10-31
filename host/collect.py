#!/usr/bin/env python3
"""Prompted data collection for Finger Pods.

Shows one character at a time (right hand, 3 rows, randomised order);
you press the pod button as if typing that key. The magnetometer vector
at the press edge is recorded as one labelled example. One physical
button will produce several different labels -- that is expected, the
pose is what the model learns to read.

Usage (from the repo root, with the project venv active):
    python host/collect.py --port /dev/cu.usbmodemXXXX --reps 20
    python host/collect.py --simulate --reps 5   # no hardware, fake data

Output (in data/ by default), one set per sitting:
    session_YYYYmmdd_HHMMSS.csv    one row per press (model-ready)
    session_YYYYmmdd_HHMMSS_stream.csv  raw stream while collecting
    session_YYYYmmdd_HHMMSS.json   metadata incl. rest-pose baseline

Take the clips off and put them back on between sessions: cross-session
accuracy is the number that matters, so collect at least two sessions.
"""

import argparse
import csv
import glob
import json
import random
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fingerpods as fp


def find_port():
    for pattern in ("/dev/cu.usbmodem*", "/dev/cu.usbserial*",
                    "/dev/ttyACM*", "/dev/ttyUSB*"):
        hits = sorted(glob.glob(pattern))
        if hits:
            return hits[0]
    return None


class SerialSource:
    """Yields (t_host_s, t_device_ms, mag, buttons) from the QT Py."""

    def __init__(self, port, baud):
        import serial  # pyserial, imported lazily so --simulate needs less

        self.ser = serial.Serial(port, baud, timeout=0.2)
        self.start = time.monotonic()

    def frames(self):
        while True:
            raw = self.ser.readline()
            if not raw:
                yield None
                continue
            try:
                line = raw.decode("utf-8", errors="replace")
            except Exception:
                continue
            if line.startswith("#"):
                print("  [device]", line.strip())
                continue
            parsed = fp.parse_stream_line(line)
            if parsed is None:
                continue
            t_ms, mag, buttons = parsed
            yield (time.monotonic() - self.start, t_ms, mag, buttons)


class SimulateSource:
    """Fabricates frames so the whole pipeline runs without hardware."""

    def __init__(self, seed=0):
        self.rng = random.Random(seed)
        self.baseline = fp.synthetic_baseline(self.rng)
        self.start = time.monotonic()
        self.pending_label = None

    def frames(self):
        # Rest frames until a prompt arms a press, then one press frame.
        while True:
            time.sleep(0.02)
            t = time.monotonic() - self.start
            if self.pending_label is None:
                mag = [b + self.rng.gauss(0, 1.0) for b in self.baseline]
                yield (t, int(t * 1000), mag, [0] * fp.N_BUTTONS)
            else:
                mag, buttons = fp.synthetic_press(
                    self.pending_label, self.rng, self.baseline)
                self.pending_label = None
                yield (t, int(t * 1000), mag, buttons)
                yield (t + 0.05, int(t * 1000) + 50,
                       list(mag), [0] * fp.N_BUTTONS)


def collect_baseline(source_iter, seconds):
    """Average magnetometer readings while the hand rests, no presses."""
    print(f"Rest your hand in typing position for {seconds:.0f}s "
          "(calibrating)...")
    mags, deadline = [], time.monotonic() + seconds
    for frame in source_iter:
        if frame is None:
            continue
        _th, _td, mag, buttons = frame
        if not any(buttons):
            mags.append(mag)
        if time.monotonic() >= deadline:
            break
    if not mags:
        raise RuntimeError("No rest frames received - is the device streaming?")
    baseline = [sum(col) / len(col) for col in zip(*mags)]
    print(f"  baseline from {len(mags)} frames: "
          + ", ".join(f"{v:.1f}" for v in baseline))
    return baseline


def wait_for_press(source_iter, stream_writer, prompt_label):
    """Wait for a button press edge, however long that takes.

    There is deliberately no timeout: a prompt waits until a button is
    pressed. Returns the press frame, or None only if the source is
    exhausted. Caller guarantees buttons start released, so the first
    frame with a pressed button is the edge (the snapshot we train on).
    """
    for frame in source_iter:
        if frame is None:
            continue
        t_host, t_dev, mag, buttons = frame
        if stream_writer:
            stream_writer.writerow(
                [f"{t_host:.3f}", t_dev]
                + [f"{v:.2f}" for v in mag] + buttons + [prompt_label])
        if any(buttons):
            return frame
    return None


def wait_for_release(source_iter, stream_writer, prompt_label):
    for frame in source_iter:
        if frame is None:
            continue
        t_host, t_dev, mag, buttons = frame
        if stream_writer:
            stream_writer.writerow(
                [f"{t_host:.3f}", t_dev]
                + [f"{v:.2f}" for v in mag] + buttons + [prompt_label])
        if not any(buttons):
            return


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", default=None,
                    help="serial port (default: auto-detect)")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--reps", type=int, default=20,
                    help="presses per key (default 20; 16 keys x 20 = 320)")
    ap.add_argument("--keys", default=None,
                    help="comma-separated subset of labels, e.g. 'h,j,k,l' "
                         "(use SPACE for the space key)")
    ap.add_argument("--out", default="data", help="output directory")
    ap.add_argument("--cal-seconds", type=float, default=3.0)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--simulate", action="store_true",
                    help="fabricate data, no hardware needed")
    ap.add_argument("--no-stream", action="store_true",
                    help="do not save the raw stream CSV")
    args = ap.parse_args()

    labels = (fp.parse_key_subset(args.keys)
              if args.keys else list(fp.LABELS))
    unknown = [k for k in labels if k not in fp.KEY_INFO]
    if unknown:
        ap.error(f"unknown key labels: {unknown}; "
                 f"valid: {[fp.display_label(l) for l in fp.LABELS]}")

    if args.simulate:
        source = SimulateSource(seed=args.seed or 0)
        port_name = "SIMULATED"
    else:
        port_name = args.port or find_port()
        if not port_name:
            ap.error("no serial port found - pass --port (or use --simulate)")
        print(f"Opening {port_name} at {args.baud} baud...")
        source = SerialSource(port_name, args.baud)
    source_iter = iter(source.frames())

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    session = f"session_{stamp}"
    csv_path = out_dir / f"{session}.csv"
    stream_path = out_dir / f"{session}_stream.csv"
    meta_path = out_dir / f"{session}.json"

    prompts = fp.shuffled_prompts(args.reps, labels, seed=args.seed)
    rows, skipped = [], 0
    baseline = None

    stream_f = stream_w = None
    try:
        if not args.no_stream:
            stream_f = open(stream_path, "w", newline="")
            stream_w = csv.writer(stream_f)
            stream_w.writerow(["t_host_s", "t_device_ms"]
                              + [f"raw_{c}" for c in fp.MAG_COLS]
                              + fp.BUTTON_COLS + ["prompt_label"])

        baseline = collect_baseline(source_iter, args.cal_seconds)
        if args.simulate:
            source.baseline = baseline  # keep sim poses relative to rest

        print(f"\n{len(prompts)} prompts ({args.reps} x {len(labels)} keys). "
              "Press the pod as if typing the shown key. Ctrl-C to stop.\n")
        for idx, label in enumerate(prompts, 1):
            finger, row = fp.KEY_INFO[label]
            where = "thumb" if label == " " else f"{finger}, {row} row"
            print(f"[{idx}/{len(prompts)}]  >>>  '{fp.display_label(label)}'  "
                  f"({where})  ", end="", flush=True)
            if args.simulate:
                source.pending_label = label
            frame = wait_for_press(source_iter, stream_w, label)
            if frame is None:
                print("... skipped (input ended)")
                skipped += 1
                continue
            t_host, t_dev, mag, buttons = frame
            btn = fp.active_button(buttons)
            cal = fp.calibrate(mag, baseline)
            rows.append(
                [session, len(rows), label, finger, row, btn, t_dev,
                 f"{t_host:.3f}"]
                + [f"{v:.2f}" for v in mag]
                + [f"{v:.2f}" for v in cal]
                + buttons)
            print(f"ok (button b{btn})")
            wait_for_release(source_iter, stream_w, label)
    except KeyboardInterrupt:
        print("\nStopped early - saving what we have.")
    finally:
        if stream_f:
            stream_f.close()

    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(fp.SESSION_COLS)
        w.writerows(rows)
    meta = {
        "session": session, "created": datetime.now().isoformat(),
        "port": port_name, "simulated": args.simulate,
        "reps_requested": args.reps, "labels": labels,
        "presses_recorded": len(rows), "prompts_skipped": skipped,
        "baseline_ut": baseline,
        "layout": "right-hand 3-row QWERTY (top/home/bottom)",
        "feature_note": "features = calibrated mag (raw - baseline) + buttons",
    }
    meta_path.write_text(json.dumps(meta, indent=2))

    print(f"\nRecorded {len(rows)} presses ({skipped} skipped).")
    print(f"  presses : {csv_path}")
    if not args.no_stream:
        print(f"  stream  : {stream_path}")
    print(f"  metadata: {meta_path}")
    if len(rows) < len(labels) * 2:
        print("WARNING: very few presses - train.py needs several per key.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
