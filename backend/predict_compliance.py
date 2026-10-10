"""Predict planogram compliance for camera images and write it in the annotations.json format.

  {camera_id: {image: {area_id: {"planogram_compliant": bool}}}}

Stock fields are left to the stock model. Needs a model from train_compliance.py
(run it without --labels for the unsupervised fallback). If models/variety.joblib exists
(train_variety.py), variety mismatches are flagged when it was found to help, and
--with-variety adds the predicted variety per area (for the app; not part of the submission).
"""
import argparse
import json
import sys
import time
from pathlib import Path

import cv2
import joblib

from lemma.categories import category_of
from lemma.compliance import TextBank, features
from lemma.categories import family_of
from lemma.crop import bbox_area, inner_tiles
from lemma.embed import MODEL_ID, Clip
from lemma.planogram import load_areas
from lemma.variety import TILES

ROOT = Path(__file__).resolve().parent
DATASET = ROOT.parent / "dataset"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--images", type=Path, default=DATASET / "train_test")
    ap.add_argument("--planogram", type=Path, default=DATASET / "planogram.json")
    ap.add_argument("--model", type=Path, default=ROOT / "models" / "compliance.joblib")
    ap.add_argument("--with-proba", action="store_true", help="also write p_compliant per area")
    ap.add_argument("--variety-model", type=Path, default=ROOT / "models" / "variety.joblib")
    ap.add_argument("--with-variety", action="store_true", help="also write predicted_variety per area")
    ap.add_argument("--out", type=Path, default=ROOT / "predictions" / "compliance.json")
    args = ap.parse_args()

    if not args.model.exists():
        sys.exit(f"no model at {args.model}; run train_compliance.py (without --labels for the unsupervised fallback)")
    saved = joblib.load(args.model)
    if saved["clip"] != MODEL_ID:
        sys.exit(f"{args.model} was trained with {saved['clip']}, not {MODEL_ID}; retrain it")
    model = saved["model"]
    variety = None
    if args.variety_model.exists():
        vsaved = joblib.load(args.variety_model)
        if vsaved["clip"] == MODEL_ID:
            variety = vsaved["model"]
    use_variety = variety is not None and (args.with_variety or variety.threshold < float("inf"))

    areas = load_areas(args.planogram)
    clip = Clip()
    bank = TextBank.build(clip)
    out, n_images, t0 = {}, 0, time.perf_counter()

    for cam_dir in sorted(p for p in args.images.iterdir() if p.is_dir()):
        camera_id = cam_dir.name
        if camera_id not in areas:
            print(f"warning: no planogram areas for camera {camera_id}, skipping", file=sys.stderr)
            continue
        cam_areas = areas[camera_id]
        cats = [category_of(a.product_name) for a in cam_areas]
        area_ids = [a.area_id for a in cam_areas]
        for img_path in sorted(cam_dir.glob("*.jpg")):
            img = cv2.imread(str(img_path))
            if img is None:
                print(f"warning: cannot read {img_path}", file=sys.stderr)
                continue
            crops = [bbox_area(img, a.quad) for a in cam_areas]
            E = clip.images(crops)
            X, delta = features(E, cats, area_ids, bank, model.ctx)
            p = model.proba(X, delta)
            # Variety tiles only when they can change the answer or were asked for (they cost time).
            check = [
                j for j, a in enumerate(cam_areas)
                if use_variety and family_of(a.product_name) in variety.models
            ]
            tiles = clip.images([t for j in check for t in inner_tiles(crops[j])]) if check else None
            checks = {j: variety.check(cam_areas[j].product_name, tiles[k * TILES:(k + 1) * TILES])
                      for k, j in enumerate(check)}
            result = {}
            for j, (a, pi) in enumerate(zip(cam_areas, p)):
                r = {"planogram_compliant": bool(pi >= model.threshold)}
                if args.with_proba:
                    r["p_compliant"] = round(float(pi), 4)
                if j in checks:
                    m, best, pb = checks[j]
                    if m > variety.threshold:
                        r["planogram_compliant"] = False
                    if args.with_variety:
                        r["predicted_variety"], r["p_variety"] = best, round(pb, 4)
                result[a.area_id] = r
            out.setdefault(camera_id, {})[img_path.name] = result
            n_images += 1

    dt = time.perf_counter() - t0
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    n_areas = sum(len(a) for imgs in out.values() for a in imgs.values())
    flagged = sum(not v["planogram_compliant"] for imgs in out.values() for a in imgs.values() for v in a.values())
    print(f"{type(model).__name__}: {n_images} images, {n_areas} areas, {flagged} flagged non-compliant")
    print(f"{1000 * dt / max(n_images, 1):.0f} ms/image on CPU (crop + embed + classify) -> {args.out}")


if __name__ == "__main__":
    main()
