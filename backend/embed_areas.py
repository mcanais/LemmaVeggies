"""Embed every planogram area of every camera image with an engine (clip / dinov2); cached.

Crops are cut in memory from the original images (lemma.crop.bbox_area), so training,
evaluation and prediction all see exactly the same pixels.

Output: cache/<engine>_store.npz, keys "<camera_id>/<image>/<area_id>"
"""
import argparse
import time
from pathlib import Path

import cv2

from lemma.crop import bbox_area
from lemma.embed import ENGINES, load_cache, load_engine, save_cache
from lemma.planogram import load_areas

ROOT = Path(__file__).resolve().parent
DATASET = ROOT.parent / "dataset"


def area_key(camera_id: str, image: str, area_id: str) -> str:
    return f"{camera_id}/{image}/{area_id}"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--engine", choices=ENGINES, required=True)
    ap.add_argument("--images", type=Path, default=DATASET / "train_test")
    ap.add_argument("--planogram", type=Path, default=DATASET / "planogram.json")
    args = ap.parse_args()

    engine = load_engine(args.engine)
    cache_path = ROOT / "cache" / f"{args.engine}_store.npz"
    cache = load_cache(cache_path, engine.model_id)
    areas = load_areas(args.planogram)
    n_new, t_embed = 0, 0.0
    for cam_dir in sorted(p for p in args.images.iterdir() if p.is_dir()):
        for img_path in sorted(cam_dir.glob("*.jpg")):
            cam_areas = areas.get(cam_dir.name, [])
            keys = [area_key(cam_dir.name, img_path.name, a.area_id) for a in cam_areas]
            if all(k in cache for k in keys):
                continue
            img = cv2.imread(str(img_path))
            t0 = time.perf_counter()
            cache.update(zip(keys, engine.images([bbox_area(img, a.quad) for a in cam_areas])))
            t_embed += time.perf_counter() - t0
            n_new += len(keys)
        save_cache(cache_path, cache, engine.model_id)
        print(f"  camera {cam_dir.name} done")
    msg = f", {1000 * t_embed / n_new:.1f} ms/crop" if n_new else ""
    print(f"{args.engine}: {len(cache)} areas cached, {n_new} new{msg} -> {cache_path}")


if __name__ == "__main__":
    main()
