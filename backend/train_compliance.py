"""Train the compliance model from yes/no labels and report how it would score.

Two kinds of model are compared:
  unsupervised  flags the crops that look least like their expected product; the labels
                only tune how many to flag (works with no labels at all: 5%)
  supervised    logistic regression trained on the labels (optionally + area nudge)
Evaluation is leave-one-camera-out: tune/train on all labelled cameras but one, predict
that one, repeat. Scores use the challenge's identification points (+1 / -2). The kind
that scores best is retrained on all labels and saved.

Output: models/compliance.joblib
"""
import argparse
import csv
from pathlib import Path

import joblib
import numpy as np

from lemma.categories import category_of
from lemma.compliance import (DEFAULT_THRESHOLD, MAIN_FEATURES, ComplianceModel, TextBank,
                              UnsupervisedModel, features, fit_context, points)
from lemma.embed import MODEL_ID, Clip, load_cache
from lemma.labels import load_labels

ROOT = Path(__file__).resolve().parent
FLAG_RATES = (0.02, 0.03, 0.05, 0.08, 0.10, 0.15)


def load_data(crops: Path, label_files: list[Path], keep_unsure: bool = False):
    with open(crops / "index.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    cache = load_cache(crops / "embeddings.npz")
    missing = [r["crop_path"] for r in rows if r["crop_path"] not in cache]
    if missing:
        raise SystemExit(f"{len(missing)} crops not embedded yet; run embed_crops.py first")
    labels = load_labels(label_files or [], keep_unsure)
    E = np.stack([cache[r["crop_path"]] for r in rows])
    y = np.array([labels.get((r["camera_id"], r["image"], r["area_id"]), np.nan) for r in rows], dtype=float)
    return rows, E, y, len(labels)


def report(name: str, pred: np.ndarray, y: np.ndarray) -> int:
    pts = points(pred, y)
    acc = (pred == y.astype(bool)).mean()
    caught = int((~pred & (y == 0)).sum())
    false_alarms = int((~pred & (y == 1)).sum())
    print(f"  {name:40} points {pts:5d}   accuracy {acc:6.1%}   "
          f"caught {caught}/{int((y == 0).sum())}   false alarms {false_alarms}")
    return pts


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--labels", type=Path, nargs="*", default=[], help="label files: annotations.json format or labelling-tool .jsonl")
    ap.add_argument("--keep-unsure", action="store_true", help="also use labels marked unsure (.jsonl)")
    ap.add_argument("--crops", type=Path, default=ROOT / "crops")
    ap.add_argument("--out", type=Path, default=ROOT / "models" / "compliance.joblib")
    ap.add_argument("--area-max-shift", type=float, default=0.05,
                    help="max change of P(compliant) from area consistency (0 = off)")
    ap.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD,
                    help="flag non-compliant when P(compliant) < this (default 1/3, from the +1/-2 scoring)")
    ap.add_argument("--flag-rate", type=float, default=None,
                    help="unsupervised model: share of crops to flag (default: tuned on the labels; 5%% without labels)")
    args = ap.parse_args()

    rows, E, y, n_labels = load_data(args.crops, args.labels, args.keep_unsure)
    labelled = ~np.isnan(y)
    print(f"{n_labels} labels, {labelled.sum()} matched to crops "
          f"({int((y[labelled] == 0).sum())} non-compliant)")
    if labelled.sum() < n_labels:
        print(f"  warning: {n_labels - labelled.sum()} labels have no crop (run crop_areas.py on those images)")

    cats = [category_of(r["product_name"]) for r in rows]
    area_ids = [r["area_id"] for r in rows]
    cams = np.array([r["camera_id"] for r in rows])
    bank = TextBank.build(Clip())

    # Unsupervised model: features use no labels, so they are computed once on every crop.
    ctx_u = fit_context(E, cats, area_ids, np.full(len(rows), np.nan))
    X_u, _ = features(E, cats, area_ids, bank, ctx_u)
    unsup_by_rate = {r: UnsupervisedModel.fit(X_u, ctx_u, r) for r in FLAG_RATES}
    pred_by_rate = {r: m.proba(X_u) >= m.threshold for r, m in unsup_by_rate.items()}
    if not labelled.any():
        rate = args.flag_rate or 0.05
        save(args.out, UnsupervisedModel.fit(X_u, ctx_u, rate))
        print(f"no labels: saved unsupervised model (flags ~{rate:.0%} of crops)")
        return

    def best_rate(mask) -> float:
        """Flag rate scoring best on the labelled crops in mask (ties -> fewer flags)."""
        if args.flag_rate:
            return args.flag_rate
        return max(FLAG_RATES, key=lambda r: (points(pred_by_rate[r][mask], y[mask]), -r))

    # Leave-one-camera-out: anything tuned or trained only sees the other cameras' labels.
    test_cams = sorted(set(cams[labelled]))
    cv = {}
    if len(test_cams) < 2:
        print("need labels from at least 2 cameras for cross-validation; skipping evaluation")
    else:
        y_all, p_un, p_main, p_nudge = [], [], [], []
        for cam in test_cams:
            train = labelled & (cams != cam)
            test = labelled & (cams == cam)
            idx = np.where(test)[0]
            y_all.append(y[idx])
            p_un.append(pred_by_rate[best_rate(train)][idx])
            y_train = np.where(train, y, np.nan)  # held-out camera's labels are hidden
            ctx = fit_context(E, cats, area_ids, y_train)
            X, delta = features(E, cats, area_ids, bank, ctx, self_labels=y_train)
            try:
                model = ComplianceModel.fit(X[train], delta[train], y[train], ctx, args.area_max_shift, args.threshold)
                p_main.append(model.proba(X[idx], delta[idx], nudge=False) >= args.threshold)
                p_nudge.append(model.proba(X[idx], delta[idx], nudge=True) >= args.threshold)
            except ValueError:
                print(f"  camera {cam}: other cameras have a single class; supervised model counted as always compliant")
                p_main.append(np.ones(len(idx), dtype=bool))
                p_nudge.append(np.ones(len(idx), dtype=bool))
        yv = np.concatenate(y_all)
        print(f"\nLeave-one-camera-out over {len(yv)} labelled crops:")
        report("always compliant (baseline)", np.ones(len(yv), dtype=bool), yv)
        cv["unsupervised"] = report("unsupervised (flag rate tuned)", np.concatenate(p_un), yv)
        cv["supervised"] = report("supervised", np.concatenate(p_main), yv)
        cv["supervised+nudge"] = report(f"supervised + area nudge (±{args.area_max_shift})", np.concatenate(p_nudge), yv)

    # Final models on all labels; keep the kind that scored best in cross-validation.
    rate = best_rate(labelled)
    unsup = unsup_by_rate.get(rate) or UnsupervisedModel.fit(X_u, ctx_u, rate)
    choice = max(cv, key=cv.get) if cv else "unsupervised"
    if choice == "unsupervised":
        print(f"\nkeeping the unsupervised model (flag rate {rate:.0%}, chosen on all labels)")
        save(args.out, unsup)
        return
    ctx = fit_context(E, cats, area_ids, y)
    X, delta = features(E, cats, area_ids, bank, ctx, self_labels=y)
    max_shift = args.area_max_shift if choice == "supervised+nudge" else 0.0
    model = ComplianceModel.fit(X[labelled], delta[labelled], y[labelled], ctx, max_shift, args.threshold)
    coefs = model.clf[-1].coef_[0]
    print(f"\nkeeping the {choice} model; weights (standardised): "
          + ", ".join(f"{n} {c:+.2f}" for n, c in zip(MAIN_FEATURES, coefs)))
    print(f"area nudge weight {model.nudge_w} (max shift ±{model.max_shift})")
    save(args.out, model)


def save(path: Path, model) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": model, "clip": MODEL_ID}, path)
    print(f"saved {path}")

if __name__ == "__main__":
    main()
