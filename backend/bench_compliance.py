"""Benchmark compliance methods on the team's labels, per engine (clip / dinov2).

Methods (each predicts planogram_compliant per area):
  always        always compliant (baseline)
  area_cosine_0.65  the team's method as in backend/train.py: cosine similarity to the area's
                average labelled-compliant look, flag below 0.65
  area_cosine   the same, with the threshold tuned on the training labels
  classifier    logistic regression "which product is this?" trained on labelled crops
                (compliant ones show their planogram product; empty ones are class __empty__);
                flag when P(expected product) + P(empty) is below a threshold (tuned).
                Products the classifier has never seen are left compliant (abstain).
  text          (clip only) no-label text + prototype score; the share to flag is tuned
  gsd_*         with --gsd: classifier trained on Grocery Store Dataset photos
                (gsd_only) or on them plus the team's labels (classifier+gsd)

Evaluation: every labelled area is predicted by a model that never saw its label.
  images   5 folds grouped by image: new photos from cameras seen in training
           (like the official validation set: same cameras, same day)
  cameras  leave-one-camera-out: cameras never seen in training (a new store layout)
Thresholds are tuned with an inner cross-validation on the training part only.

Outputs (results/): <tag>.md (tables) and <tag>_predictions.csv (every area, every method).
"""
import argparse
import csv
import json
import time
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from embed_areas import area_key
from lemma.categories import category_of, class_key
from lemma.compliance import TextBank, UnsupervisedModel, features, fit_context, points
from lemma.crop import bbox_area
from lemma.embed import load_cache, load_engine
from lemma.labels import load_annotations
from lemma.planogram import load_areas

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
EMPTY = "__empty__"
PROB_GRID = (0.01, 0.02, 0.05, 0.1, 0.15, 0.2, 0.3, 0.4, 0.5)
COS_GRID = tuple(np.round(np.arange(0.30, 0.96, 0.05), 2))
RATE_GRID = (0.0, 0.02, 0.03, 0.05, 0.08, 0.10, 0.15)
LR_C = 1.0
MIN_VARIETY_EXAMPLES = 5  # fewer training examples of the expected variety -> judge at category level
LR_TOL, LR_MAX_ITER = 1e-3, 500  # converges in ~20-50 iterations; tighter only costs time


# ---------------------------------------------------------------- data

def load_rows(images: Path, planogram: Path) -> list[dict]:
    areas = load_areas(planogram)
    rows = []
    for cam_dir in sorted(p for p in images.iterdir() if p.is_dir()):
        for img_path in sorted(cam_dir.glob("*.jpg")):
            for a in areas.get(cam_dir.name, []):
                rows.append({"camera": cam_dir.name, "image": img_path.name, "area_id": a.area_id,
                             "product": a.product_name, "category": category_of(a.product_name),
                             "key": area_key(cam_dir.name, img_path.name, a.area_id)})
    return rows


def load_gsd(engine_name: str, model_id: str, granularity: str):
    """Grocery Store Dataset embeddings + class keys (see embed_gsd.py), or None."""
    path = ROOT / "cache" / f"{engine_name}_gsd.npz"
    cache = load_cache(path, model_id)
    if not cache:
        return None
    with open(ROOT / "cache" / "gsd_labels.json", encoding="utf-8") as f:
        labels = json.load(f)  # key -> {"category": ..., "variety": ...}
    keys = sorted(k for k in cache if k in labels)
    cls = [labels[k]["category"] + (f":{labels[k]['variety']}" if granularity == "variety" and labels[k]["variety"] else "")
           for k in keys]
    return np.stack([cache[k] for k in keys]), np.array(cls)


# ---------------------------------------------------------------- methods
# Each method: fit(train_idx) -> predict(test_idx) -> (ok bool array, score array, predicted class list)

def tune(scores: np.ndarray, y: np.ndarray, grid, flag_below=True) -> float:
    """Threshold maximising challenge points (ties -> fewer flags)."""
    best = None
    for t in grid:
        ok = ~(scores < t) if flag_below else ~(scores > t)
        key = (points(ok, y), -(~ok).sum())
        if best is None or key > best[0]:
            best = (key, t)
    return best[1]


class AreaCosine:
    name = "area_cosine"

    def __init__(self, E, rows, y, groups):
        self.E, self.rows, self.y, self.groups = E, rows, y, groups
        self.area = np.array([r["area_id"] for r in rows])

    def _sims(self, train, idx):
        """Cosine to the area prototype built from compliant crops in train (leave-self-out)."""
        sums, counts = {}, defaultdict(int)
        for i in train:
            if self.y[i] == 1:
                sums[self.area[i]] = sums.get(self.area[i], 0) + self.E[i]
                counts[self.area[i]] += 1
        train_set = set(train.tolist())
        out = np.full(len(idx), np.inf)  # no prototype -> never flagged
        for j, i in enumerate(idx):
            a = self.area[i]
            s, n = sums.get(a), counts[a]
            if s is None:
                continue
            if i in train_set and self.y[i] == 1:
                if n < 2:
                    continue
                s = s - self.E[i]
            out[j] = float(self.E[i] @ (s / np.linalg.norm(s)))
        return out

    def fit_predict(self, train, test):
        t = tune(self._sims(train, train), self.y[train], COS_GRID)
        s = self._sims(train, test)
        return s >= t, s, [""] * len(test), t


class AreaCosineFixed(AreaCosine):
    """The team's current setting (backend/train.py): fixed cosine threshold 0.65."""
    name = "area_cosine_0.65"

    def fit_predict(self, train, test):
        s = self._sims(train, test)
        return s >= 0.65, s, [""] * len(test), 0.65


class Classifier:
    def __init__(self, name, E, rows, y, stock, groups, granularity, gsd=None, use_labels=True, fixed_threshold=None):
        self.name, self.E, self.rows, self.y, self.stock = name, E, rows, y, stock
        self.fixed_threshold = fixed_threshold
        self.groups, self.gsd, self.use_labels = groups, gsd, use_labels
        self.expected = np.array([class_key(r["product"], granularity) for r in rows])
        self._fixed = None

    def _train_set(self, train):
        X, c = [], []
        if self.use_labels:
            for i in train:
                if self.y[i] == 1:
                    X.append(self.E[i])
                    c.append(EMPTY if self.stock[i] == "empty" else self.expected[i])
        if self.gsd is not None:
            X.extend(self.gsd[0])
            c.extend(self.gsd[1])
        return np.array(X), np.array(c)

    def _fit(self, train):
        X, c = self._train_set(train)
        if len(set(c)) < 2:
            return None
        self._counts = dict(zip(*np.unique(c, return_counts=True)))
        if not self.use_labels and self._fixed is not None:
            return self._fixed  # trained on external photos only: the same model for every fold
        clf = make_pipeline(StandardScaler(), LogisticRegression(C=LR_C, max_iter=LR_MAX_ITER, tol=LR_TOL)).fit(X, c)
        if not self.use_labels:
            self._fixed = clf
        return clf

    def _score(self, clf, idx):
        """P(expected) + P(empty); 1.0 (abstain) when the expected product is unknown to the model."""
        if clf is None:
            return np.ones(len(idx)), [""] * len(idx)
        classes = list(clf.classes_)
        P = clf.predict_proba(self.E[idx])
        e_col = classes.index(EMPTY) if EMPTY in classes else None
        score = np.ones(len(idx))
        cat_of = np.array([c.split(":")[0] for c in classes])
        counts = getattr(self, "_counts", {})
        for j, i in enumerate(idx):
            exp = self.expected[i]
            empty = P[j, e_col] if e_col is not None else 0
            if ":" in exp and counts.get(exp, 0) < MIN_VARIETY_EXAMPLES:
                # Too few examples of this variety to judge it: any variety of the same category counts.
                same = cat_of == exp.split(":")[0]
                if same.any():
                    score[j] = P[j, same].sum() + empty
            elif exp in classes:
                score[j] = P[j, classes.index(exp)] + empty
        return score, [classes[k] for k in P.argmax(axis=1)]

    def fit_predict(self, train, test):
        if self.fixed_threshold is not None:
            s, pred = self._score(self._fit(train), test)
            return s >= self.fixed_threshold, s, pred, self.fixed_threshold
        # Honest scores on the training part (inner 3-fold by the same grouping) to tune the threshold.
        inner = np.zeros(len(train))
        g = self.groups[train]
        n_inner = min(3, len(set(g)))
        if n_inner >= 2:
            for tr, te in GroupKFold(n_splits=n_inner).split(train, groups=g):
                inner[te] = self._score(self._fit(train[tr]), train[te])[0]
            t = tune(inner, self.y[train], PROB_GRID)
        else:
            t = PROB_GRID[0]
        clf = self._fit(train)
        s, pred = self._score(clf, test)
        return s >= t, s, pred, t


class TextUnsupervised:
    name = "text"

    def __init__(self, E, rows, y, clip_engine):
        cats = [r["category"] for r in rows]
        aids = [r["area_id"] for r in rows]
        ctx = fit_context(E, cats, aids, np.full(len(rows), np.nan))
        self.X, _ = features(E, cats, aids, TextBank.build(clip_engine), ctx)
        self.y = y
        self.models = {r: UnsupervisedModel.fit(self.X, ctx, r) for r in RATE_GRID if r > 0}

    def _ok(self, rate, idx):
        if rate == 0:
            return np.ones(len(idx), dtype=bool)
        m = self.models[rate]
        return m.proba(self.X[idx]) >= m.threshold

    def fit_predict(self, train, test):
        rate = max(RATE_GRID, key=lambda r: (points(self._ok(r, train), self.y[train]), -r))
        m = self.models.get(rate)
        s = m.proba(self.X[test]) if m else np.ones(len(test))
        return self._ok(rate, test), s, [""] * len(test), rate


# ---------------------------------------------------------------- evaluation

def evaluate(method, labelled, groups, n_splits=None):
    """Out-of-fold predictions for every labelled index."""
    ok = np.zeros(len(method.y), dtype=bool)
    score = np.full(len(method.y), np.nan)
    pred = [""] * len(method.y)
    thresholds = []
    splitter = GroupKFold(n_splits=n_splits or len(set(groups[labelled])))
    folds = list(splitter.split(labelled, groups=groups[labelled]))
    for k, (tr, te) in enumerate(folds, 1):
        print(f"      {method.name}: fold {k}/{len(folds)}", flush=True)
        train, test = labelled[tr], labelled[te]
        o, s, p, t = method.fit_predict(train, test)
        ok[test], score[test] = o, s
        for i, pi in zip(test, p):
            pred[i] = pi
        thresholds.append(t)
    return ok, score, pred, thresholds


def summarize(ok, y, rows, idx, expected=None, pred=None, stock=None):
    yy, oo = y[idx].astype(bool), ok[idx]
    correct = oo == yy
    by_image = defaultdict(list)
    for i, c in zip(idx, correct):
        by_image[(rows[i]["camera"], rows[i]["image"])].append(c)
    res = {
        "points": points(oo, y[idx]),
        "correct": int(correct.sum()),
        "n": len(idx),
        "caught": int((~oo & ~yy).sum()),
        "neg": int((~yy).sum()),
        "false_alarms": int((~oo & yy).sum()),
        "images_all_correct": sum(all(v) for v in by_image.values()),
        "n_images": len(by_image),
    }
    if pred is not None:
        # Product identification: compliant, non-empty crops whose prediction exists.
        ids = [i for i in idx if y[i] == 1 and stock[i] != "empty" and pred[i]]
        res["id_correct"] = sum(pred[i] == expected[i] for i in ids)
        res["id_n"] = len(ids)
    return res


def time_end_to_end(engine, method_fit, rows, images_dir, planogram, n_images=20):
    """ms per camera image: read + crop all areas + embed + classify (model already trained)."""
    areas = load_areas(planogram)
    imgs = sorted({(r["camera"], r["image"]) for r in rows})[:: max(1, len({(r['camera'], r['image']) for r in rows}) // n_images)][:n_images]
    t0 = time.perf_counter()
    n_areas = 0
    for cam, image in imgs:
        img = cv2.imread(str(images_dir / cam / image))
        crops = [bbox_area(img, a.quad) for a in areas[cam]]
        E = engine.images(crops)
        if method_fit is not None:
            method_fit.predict_proba(E)
        n_areas += len(crops)
    dt = time.perf_counter() - t0
    return 1000 * dt / len(imgs), 1000 * dt / n_areas


# ---------------------------------------------------------------- main

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--engines", nargs="+", default=["clip", "dinov2"])
    ap.add_argument("--labels", type=Path, nargs="+", default=[REPO / "labels" / "human.jsonl"])
    ap.add_argument("--images", type=Path, default=REPO / "dataset" / "train_test")
    ap.add_argument("--planogram", type=Path, default=REPO / "dataset" / "planogram.json")
    ap.add_argument("--granularity", choices=("category", "variety"), default="category")
    ap.add_argument("--gsd", action="store_true", help="add Grocery Store Dataset methods (run embed_gsd.py first)")
    ap.add_argument("--tag", default=None, help="output name (default: phase1 / phase2)")
    ap.add_argument("--schemes", nargs="+", default=["images", "cameras"], help="evaluation schemes to run")
    ap.add_argument("--folds", type=int, default=5, help="folds for the images scheme")
    ap.add_argument("--methods", nargs="+", default=None, help="only these methods (default: all)")
    ap.add_argument("--threshold", type=float, default=None,
                    help="fixed threshold for the classifiers instead of tuning it (much faster)")
    args = ap.parse_args()
    tag = args.tag or ("phase2" if args.gsd else "phase1") + ("_variety" if args.granularity == "variety" else "")

    rows = load_rows(args.images, args.planogram)
    ann = load_annotations(args.labels)
    y = np.array([float(ann[k]["planogram_compliant"]) if (k := (r["camera"], r["image"], r["area_id"])) in ann else np.nan
                  for r in rows])
    stock = np.array([ann.get((r["camera"], r["image"], r["area_id"]), {}).get("stock_level", "") for r in rows])
    labelled = np.where(~np.isnan(y))[0]
    groups = {
        "images": np.array([f"{r['camera']}/{r['image']}" for r in rows]),
        "cameras": np.array([r["camera"] for r in rows]),
    }
    groups = {k: v for k, v in groups.items() if k in args.schemes}
    print(f"{len(rows)} areas, {len(labelled)} labelled ({int((y[labelled] == 0).sum())} non-compliant), "
          f"{len({(rows[i]['camera'], rows[i]['image']) for i in labelled})} labelled images, granularity {args.granularity}")

    out_rows = [dict(r, label_compliant="" if np.isnan(y[i]) else bool(y[i]), label_stock=stock[i])
                for i, r in enumerate(rows)]
    results, timings = [], []
    for eng_name in args.engines:
        print(f"== {eng_name}", flush=True)
        engine = load_engine(eng_name)
        cache = load_cache(ROOT / "cache" / f"{eng_name}_store.npz", engine.model_id)
        missing = [r["key"] for r in rows if r["key"] not in cache]
        if missing:
            raise SystemExit(f"{len(missing)} areas not embedded for {eng_name}; run embed_areas.py --engine {eng_name}")
        E = np.stack([cache[r["key"]] for r in rows])
        gsd = load_gsd(eng_name, engine.model_id, args.granularity) if args.gsd else None
        if args.gsd and gsd is None:
            raise SystemExit(f"no Grocery Store embeddings for {eng_name}; run embed_gsd.py --engine {eng_name}")

        for scheme, g in groups.items():
            ft = args.threshold
            methods = [AreaCosineFixed(E, rows, y, g), AreaCosine(E, rows, y, g),
                       Classifier("classifier", E, rows, y, stock, g, args.granularity, fixed_threshold=ft)]
            if gsd is not None:
                methods += [Classifier("gsd_only", E, rows, y, stock, g, args.granularity, gsd, use_labels=False, fixed_threshold=ft),
                            Classifier("classifier+gsd", E, rows, y, stock, g, args.granularity, gsd, fixed_threshold=ft)]
            if engine.has_text and (args.methods is None or "text" in args.methods):
                methods.append(TextUnsupervised(E, rows, y, engine))
            if args.methods:
                methods = [m for m in methods if m.name in args.methods]
            base = summarize(np.ones(len(rows), dtype=bool), y, rows, labelled)
            results.append(dict(engine=eng_name, scheme=scheme, method="always", **base, threshold=""))
            for m in methods:
                t0 = time.perf_counter()
                ok, score, pred, th = evaluate(m, labelled, g, n_splits=args.folds if scheme == "images" else None)
                dt = time.perf_counter() - t0
                expected = getattr(m, "expected", None)
                res = summarize(ok, y, rows, labelled, expected, pred if expected is not None else None, stock)
                ths = sorted(set(th))
                results.append(dict(engine=eng_name, scheme=scheme, method=m.name, **res,
                                    threshold=",".join(str(t) for t in ths), eval_s=round(dt, 1)))
                col = f"{eng_name}:{m.name}:{scheme}"
                for i in labelled:
                    out_rows[i][col + ":ok"] = bool(ok[i])
                    out_rows[i][col + ":score"] = round(float(score[i]), 4)
                    if pred[i]:
                        out_rows[i][col + ":pred"] = pred[i]
                print(f"  {eng_name:7} {scheme:8} {m.name:16} points {res['points']:5d}  correct {res['correct']}/{res['n']}"
                      f"  caught {res['caught']}/{res['neg']}  false alarms {res['false_alarms']}"
                      + (f"  product id {res['id_correct']}/{res['id_n']}" if "id_n" in res else "") + f"  ({dt:.0f}s)", flush=True)

        # Final models on all labels -> prediction for every area (labelled or not), and timing.
        gi = np.array([f"{r['camera']}/{r['image']}" for r in rows])
        finals = [Classifier("classifier", E, rows, y, stock, gi, args.granularity, fixed_threshold=args.threshold)]
        if gsd is not None:
            finals.append(Classifier("classifier+gsd", E, rows, y, stock, gi, args.granularity, gsd, fixed_threshold=args.threshold))
        if args.methods:
            finals = [m for m in finals if m.name in args.methods] or finals[-1:]
        all_idx = np.arange(len(rows))
        for m in finals:
            ok, score, pred, t = m.fit_predict(labelled, all_idx)
            col = f"{eng_name}:{m.name}:final"
            for i in all_idx:
                out_rows[i][col + ":ok"] = bool(ok[i])
                out_rows[i][col + ":score"] = round(float(score[i]), 4)
                out_rows[i][col + ":pred"] = pred[i]
            print(f"  {eng_name:7} final {m.name}: threshold {t}, flags {int((~ok).sum())} of {len(rows)} areas", flush=True)
        t_fit = time.perf_counter()
        clf = finals[-1]._fit(labelled)
        t_fit = time.perf_counter() - t_fit
        ms_img, ms_area = time_end_to_end(engine, clf, rows, args.images, args.planogram)
        timings.append(dict(engine=eng_name, ms_per_image=round(ms_img), ms_per_area=round(ms_area, 1),
                            train_s=round(t_fit, 1)))
        print(f"  {eng_name:7} time: {ms_img:.0f} ms/image, {ms_area:.1f} ms/area, training {t_fit:.1f}s")

    out = ROOT / "results"
    out.mkdir(exist_ok=True)
    cols = list(dict.fromkeys(k for r in out_rows for k in r))
    with open(out / f"{tag}_predictions.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(out_rows)
    with open(out / f"{tag}.md", "w", encoding="utf-8") as f:
        f.write(f"# Compliance benchmark: {tag}\n\n")
        f.write(f"{len(labelled)} labelled areas ({int((y[labelled] == 0).sum())} non-compliant), "
                f"granularity `{args.granularity}`. Points: +1 correct, -2 wrong.\n\n")
        for scheme in groups:
            f.write(f"## {'New photos, seen cameras' if scheme == 'images' else 'Unseen cameras'} (`{scheme}`)\n\n")
            f.write("| Engine | Method | Points | Correct | Caught | False alarms | Images all correct | Product id | Threshold(s) |\n")
            f.write("|---|---|---|---|---|---|---|---|---|\n")
            for r in results:
                if r["scheme"] != scheme:
                    continue
                pid = f"{r['id_correct']}/{r['id_n']}" if "id_n" in r else ""
                f.write(f"| {r['engine']} | {r['method']} | {r['points']} | {r['correct']}/{r['n']} | "
                        f"{r['caught']}/{r['neg']} | {r['false_alarms']} | {r['images_all_correct']}/{r['n_images']} | "
                        f"{pid} | {r['threshold']} |\n")
            f.write("\n")
        f.write("## Time (CPU)\n\n| Engine | ms / camera image | ms / area | training (s) |\n|---|---|---|---|\n")
        for t in timings:
            f.write(f"| {t['engine']} | {t['ms_per_image']} | {t['ms_per_area']} | {t['train_s']} |\n")
    print(f"wrote {out / (tag + '.md')} and {out / (tag + '_predictions.csv')}")


if __name__ == "__main__":
    main()
