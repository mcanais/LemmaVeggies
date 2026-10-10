"""Train the variety model (Fuji vs Gala, banana kinds...) and decide how much to trust it.

1. Free training data: crops labelled compliant, or unlabelled crops the compliance model
   (models/compliance.joblib) doesn't flag, show their planogram product.
2. Leave-one-area-out test: for each basket, train on the *other* baskets and predict this
   one. A variety the model only knows from one basket can't be tested this way, and a model
   that recognises crates instead of fruit fails here; that's the point.
3. With labels: pick the mismatch threshold that maximises challenge points when variety
   mismatches are added to the compliance model's flags (or switch it off).

Output: models/variety.joblib
"""
import argparse
import collections
import csv
from pathlib import Path

import joblib
import numpy as np

from lemma.categories import category_of, family_of
from lemma.compliance import TextBank, features, points
from lemma.embed import MODEL_ID, Clip, load_cache
from lemma.labels import load_labels
from lemma.variety import (TILES, VarietyModel, families_with_varieties, fit_family,
                           mismatch_scores, tile_key)

ROOT = Path(__file__).resolve().parent
THRESHOLDS = (0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99)


def short(name: str) -> str:
    return " ".join(name.split()[:3])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--labels", type=Path, nargs="*", default=[], help="label files (.json or .jsonl)")
    ap.add_argument("--keep-unsure", action="store_true")
    ap.add_argument("--crops", type=Path, default=ROOT / "crops")
    ap.add_argument("--compliance-model", type=Path, default=ROOT / "models" / "compliance.joblib")
    ap.add_argument("--out", type=Path, default=ROOT / "models" / "variety.joblib")
    args = ap.parse_args()

    with open(args.crops / "index.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    names = [r["product_name"] for r in rows]
    fams = families_with_varieties(names)
    crop_cache = load_cache(args.crops / "embeddings.npz")
    tile_cache = load_cache(args.crops / "tile_embeddings.npz")
    fam_idx = [i for i, n in enumerate(names) if family_of(n) in fams]
    missing = [rows[i]["crop_path"] for i in fam_idx if tile_key(rows[i]["crop_path"], 0) not in tile_cache]
    if missing or any(r["crop_path"] not in crop_cache for r in rows):
        raise SystemExit("some crops are not embedded yet; run embed_crops.py first")

    # Which crops can be trusted to show their planogram product?
    labels = load_labels(args.labels, args.keep_unsure)
    y = np.array([labels.get((r["camera_id"], r["image"], r["area_id"]), np.nan) for r in rows])
    saved = joblib.load(args.compliance_model)
    cmodel = saved["model"]
    E = np.stack([crop_cache[r["crop_path"]] for r in rows])
    cats = [category_of(n) for n in names]
    area_ids = [r["area_id"] for r in rows]
    X, delta = features(E, cats, area_ids, TextBank.build(Clip()), cmodel.ctx)
    cat_ok = cmodel.proba(X, delta) >= cmodel.threshold
    trusted = (y == 1) | (np.isnan(y) & cat_ok)
    print(f"{len(fams)} families with varieties: " + ", ".join(f"{f} ({len(v)})" for f, v in fams.items()))
    print(f"{len(fam_idx)} crops in those families, {int(trusted[fam_idx].sum())} trusted as training data\n")

    T = {i: np.stack([tile_cache[tile_key(rows[i]["crop_path"], t)] for t in range(TILES)]) for i in fam_idx}
    mismatch = np.zeros(len(rows))
    best_pred = [""] * len(rows)

    # Leave-one-area-out.
    for fam, varieties in fams.items():
        idx = [i for i in fam_idx if family_of(names[i]) == fam]
        areas = sorted({area_ids[i] for i in idx})
        print(f"== {fam}: {len(areas)} areas")
        per_variety = collections.defaultdict(lambda: [0, 0, collections.Counter(), 0])  # ok, n, wrong preds, areas
        for a in areas:
            train = [i for i in idx if area_ids[i] != a and trusted[i]]
            test = [i for i in idx if area_ids[i] == a]
            clf = fit_family(np.stack([T[i] for i in train]), [names[i] for i in train]) if train else None
            expected = names[test[0]]
            pv = per_variety[expected]
            pv[3] += 1
            if clf is None:
                continue
            for i, (m, b, _) in zip(test, mismatch_scores(clf, np.stack([T[i] for i in test]), [names[i] for i in test])):
                mismatch[i], best_pred[i] = m, b
                if trusted[i] and expected in clf.classes_:
                    pv[0] += b == expected
                    pv[1] += 1
                    if b != expected:
                        pv[2][short(b)] += 1
        for v in varieties:
            ok, n, wrong, n_areas = per_variety[v]
            if n:
                conf = ", ".join(f"{k} {c}" for k, c in wrong.most_common(2))
                print(f"  {short(v):28} {ok:3d}/{n:<3d} right on unseen baskets ({ok / n:5.1%})"
                      + (f"   mistaken for: {conf}" if conf else ""))
            else:
                print(f"  {short(v):28} only {n_areas} basket(s): can't be tested on an unseen basket")

    # How much to trust it: points on labelled crops, compliance flags + variety mismatch.
    labelled = ~np.isnan(y)
    unlabelled_fam = np.zeros(len(rows), dtype=bool)
    unlabelled_fam[fam_idx] = True
    unlabelled_fam &= ~labelled
    threshold = float("inf")
    if labelled.any():
        base = points(cat_ok[labelled], y[labelled])
        print(f"\nAdding variety mismatches to the compliance flags (labelled crops: {int(labelled.sum())}):")
        print(f"  {'variety check off':24} points {base:4d}")
        best = base
        for t in THRESHOLDS:
            ok = cat_ok & ~(mismatch > t)
            pts = points(ok[labelled], y[labelled])
            caught = int((~ok & (y == 0)).sum())
            extra = int((~ok & cat_ok & unlabelled_fam).sum())
            print(f"  {'threshold ' + str(t):24} points {pts:4d}   caught {caught}/{int((y == 0).sum())}"
                  f"   extra flags on unlabelled baskets {extra}")
            if pts > best:
                best, threshold = pts, t
        print(f"-> {'threshold ' + str(threshold) if threshold < float('inf') else 'variety check off'}")
    else:
        print("\nno labels: variety check stays off for compliance (variety is still reported)")

    models = {}
    for fam in fams:
        train = [i for i in fam_idx if family_of(names[i]) == fam and trusted[i]]
        clf = fit_family(np.stack([T[i] for i in train]), [names[i] for i in train]) if train else None
        if clf is not None:
            models[fam] = clf
    args.out.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": VarietyModel(models, threshold), "clip": MODEL_ID}, args.out)
    print(f"saved {args.out}")


if __name__ == "__main__":
    main()
