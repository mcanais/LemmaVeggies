"""Embed every crop listed in <crops>/index.csv with CLIP; only new crops are computed.

Output: <crops>/embeddings.npz (whole crops, for compliance) and <crops>/tile_embeddings.npz
(centre tiles of crops whose product has varieties, e.g. apples, for the variety model).
"""
import argparse
import csv
import time
from pathlib import Path

import cv2

from lemma.categories import family_of
from lemma.crop import inner_tiles
from lemma.embed import Clip, load_cache, save_cache
from lemma.variety import TILES, tile_key

ROOT = Path(__file__).resolve().parent


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--crops", type=Path, default=ROOT / "crops")
    args = ap.parse_args()

    with open(args.crops / "index.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    clip = None

    def embed(keys: list[str], cache_path: Path, load) -> None:
        nonlocal clip
        cache = load_cache(cache_path)
        todo = [k for k in keys if k not in cache]
        print(f"{cache_path.name}: {len(keys)} items, {len(keys) - len(todo)} cached, {len(todo)} to embed")
        if not todo:
            return
        clip = clip or Clip()
        t0 = time.perf_counter()
        for i in range(0, len(todo), 256):
            chunk = todo[i:i + 256]
            cache.update(zip(chunk, clip.images([load(k) for k in chunk])))
            save_cache(cache_path, cache)
            print(f"  {min(i + 256, len(todo))}/{len(todo)}")
        dt = time.perf_counter() - t0
        print(f"  {1000 * dt / len(todo):.1f} ms each")

    embed([r["crop_path"] for r in rows], args.crops / "embeddings.npz",
          lambda k: cv2.imread(str(args.crops / k)))

    tile_keys = [tile_key(r["crop_path"], t) for r in rows if family_of(r["product_name"]) for t in range(TILES)]
    embed(tile_keys, args.crops / "tile_embeddings.npz", lambda k: load_tile(args.crops, k))


def load_tile(crops: Path, key: str):
    path, t = key.rsplit("#", 1)
    return inner_tiles(cv2.imread(str(crops / path)))[int(t)]

if __name__ == "__main__":
    main()
