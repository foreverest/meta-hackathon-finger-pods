#!/usr/bin/env python3
"""Train the Finger Pods keystroke classifier.

Usage (from the repo root, with the project venv active):
    python host/train.py                      # all data/session_*.csv
    python host/train.py data/session_A.csv data/session_B.csv

Each press is one example: features are the baseline-subtracted
magnetometer vector (9) plus button states (9). Because one button can
emit several keys, the button alone cannot determine the label -- the
model has to use the pose. The classifier is a RandomForest; it handles
the mixed continuous/binary features without scaling fuss.

Validation: if the data spans 2+ sessions, this reports leave-one-
session-out accuracy (train on all but one sitting, test on the held-
out sitting -- the honest, re-donned-the-clips number) in addition to a
random stratified split. With a single session only the random split
is possible, and it will look optimistic.
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fingerpods as fp


def load_sessions(paths):
    import pandas as pd

    frames = []
    for p in paths:
        df = pd.read_csv(p)
        missing = [c for c in fp.FEATURE_COLS + ["label"] if c not in df.columns]
        if missing:
            raise SystemExit(f"{p}: missing columns {missing} "
                             "(is this a session CSV from collect.py?)")
        frames.append(df)
    data = pd.concat(frames, ignore_index=True)
    return data


def report(name, y_true, y_pred, labels):
    from sklearn.metrics import accuracy_score, confusion_matrix

    acc = accuracy_score(y_true, y_pred)
    print(f"\n{name}: accuracy {acc:.3f}  ({len(y_true)} presses)")
    cm = confusion_matrix(y_true, y_pred, labels=labels)
    print("confusion (rows=true, cols=pred):")
    print("      " + " ".join(f"{fp.display_label(l):>5}" for l in labels))
    for lab, rowvals in zip(labels, cm):
        print(f"{fp.display_label(lab):>5} "
              + " ".join(f"{v:5d}" for v in rowvals))
    return acc


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csvs", nargs="*", help="session CSVs (default: data/session_*.csv, excluding *_stream.csv)")
    ap.add_argument("--out", default="models/model.pkl", help="model output path")
    ap.add_argument("--estimators", type=int, default=300)
    args = ap.parse_args()

    paths = [Path(p) for p in args.csvs] if args.csvs else sorted(
        p for p in Path("data").glob("session_*.csv")
        if not p.name.endswith("_stream.csv"))
    if not paths:
        raise SystemExit("No session CSVs found - run host/collect.py first.")
    print("Loading:", ", ".join(str(p) for p in paths))

    data = load_sessions(paths)
    labels = sorted(data["label"].unique())
    print(f"{len(data)} presses, {len(labels)} keys: {labels}")
    print("per-key counts:", dict(Counter(data['label'])))
    if len(data) < 30 or min(Counter(data["label"]).values()) < 3:
        print("WARNING: very little data per key - results will be noisy.")

    X = data[fp.FEATURE_COLS].to_numpy(dtype=float)
    y = data["label"].to_numpy()

    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import StratifiedKFold, cross_val_predict

    def make_model():
        return RandomForestClassifier(
            n_estimators=args.estimators, random_state=0, n_jobs=-1)

    results = {}

    # Honest check: hold out whole sessions (clips re-donned between them).
    sessions = data["session"].unique() if "session" in data else []
    if len(sessions) >= 2:
        from sklearn.metrics import accuracy_score

        session_arr = data["session"].to_numpy()
        preds = [None] * len(y)
        per_session = {}
        for held in sessions:
            te = session_arr == held
            tr = ~te
            model = make_model().fit(X[tr], y[tr])
            p = model.predict(X[te])
            for i, pv in zip([i for i, s in enumerate(te) if s], p):
                preds[i] = pv
            per_session[str(held)] = accuracy_score(y[te], p)
        known = [i for i, pv in enumerate(preds) if pv is not None]
        results["leave_one_session_out"] = report(
            "Leave-one-session-out", y[known], [preds[i] for i in known], labels)
        results["per_session_accuracy"] = per_session
    else:
        print("\nOnly one session: skipping leave-one-session-out. "
              "Collect a second session (clips off and back on) for the "
              "accuracy number that actually matters.")

    # Optimistic check: stratified cross-validation over all presses.
    n_splits = min(5, min(Counter(y).values()))
    if n_splits >= 2:
        cv = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=0)
        cv_pred = cross_val_predict(make_model(), X, y, cv=cv)
        results["cv_accuracy"] = report(
            f"Stratified {n_splits}-fold CV (optimistic)", y, cv_pred, labels)

    # Final model on all data.
    model = make_model().fit(X, y)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    import joblib

    joblib.dump({
        "model": model,
        "labels": labels,
        "feature_cols": fp.FEATURE_COLS,
        "layout": "right-hand 3-row QWERTY (top/home/bottom)",
        "n_presses": int(len(data)),
        "sessions": [str(s) for s in sessions],
        "results": {k: (float(v) if isinstance(v, float) else v)
                    for k, v in results.items()},
    }, out)
    print(f"\nSaved model -> {out}")
    (out.with_suffix(".json")).write_text(json.dumps(
        {"labels": labels, "feature_cols": fp.FEATURE_COLS,
         "n_presses": int(len(data)),
         "sessions": [str(s) for s in sessions],
         "results": results}, indent=2, default=str))
    print(f"Saved report -> {out.with_suffix('.json')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
