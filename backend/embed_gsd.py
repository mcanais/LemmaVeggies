"""Embed the Grocery Store Dataset (Klasson et al. 2019, MIT) for an engine, mapped to our classes.

Each fine class is mapped to one of our categories (lemma/categories.py) and, for apples and
pears, a variety. Produce we don't sell becomes an "other:<name>" class: extra examples of
"not the expected product". Packaged drinks and dairy are skipped.

Get the data first:  git clone --depth 1 https://github.com/marcusklasson/GroceryStoreDataset external/GroceryStoreDataset
Output: cache/<engine>_gsd.npz and cache/gsd_labels.json
"""
import argparse
import csv
import json
import time
from pathlib import Path

import cv2

from lemma.categories import all_categories
from lemma.embed import ENGINES, load_cache, load_engine, save_cache

ROOT = Path(__file__).resolve().parent
GSD = ROOT / "external" / "GroceryStoreDataset" / "dataset"

# Grocery Store fine class -> (our category, variety or None)
MAPPING = {
    "Golden-Delicious": ("yellow apples", "golden"),
    "Granny-Smith": ("green apples", "granny smith"),
    "Pink-Lady": ("red apples", "pink lady"),
    "Red-Delicious": ("red apples", "red delicious"),
    "Royal-Gala": ("red apples", "gala"),
    "Avocado": ("avocados", None),
    "Banana": ("bananas", None),
    "Kiwi": ("kiwis", None),
    "Lemon": ("lemons", None),
    "Lime": ("limes", None),
    "Mango": ("mangoes", None),
    "Cantaloupe": ("melons", None),
    "Galia-Melon": ("melons", None),
    "Honeydew-Melon": ("melons", None),
    "Watermelon": ("watermelons", None),
    "Nectarine": ("nectarines", None),
    "Orange": ("oranges", None),
    "Papaya": ("papayas", None),
    "Passion-Fruit": ("passion fruits", None),
    "Peach": ("peaches", None),
    "Anjou": ("pears", "anjou"),
    "Conference": ("pears", "conference"),
    "Kaiser": ("pears", "kaiser"),
    "Pineapple": ("pineapples", None),
    "Satsumas": ("clementines", None),
    "Aubergine": ("eggplants", None),
    "Cabbage": ("white cabbages", None),
    "Cucumber": ("cucumbers", None),
    "Garlic": ("garlic", None),
    "Ginger": ("ginger", None),
    "Yellow-Onion": ("onions", None),
    "Green-Bell-Pepper": ("green bell peppers", None),
    "Red-Bell-Pepper": ("red bell peppers", None),
    "Floury-Potato": ("potatoes", None),
    "Solid-Potato": ("potatoes", None),
    "Sweet-Potato": ("sweet potatoes", None),
    "Beef-Tomato": ("beefsteak tomatoes", None),
    "Regular-Tomato": ("tomatoes", None),
    "Vine-Tomato": ("vine tomatoes", None),
    "Zucchini": ("zucchinis", None),
    # produce not in our planogram: distractors
    "Plum": ("other:plums", None),
    "Pomegranate": ("other:pomegranates", None),
    "Red-Grapefruit": ("other:grapefruits", None),
    "Asparagus": ("other:asparagus", None),
    "Carrots": ("other:carrots", None),
    "Leek": ("other:leeks", None),
    "Brown-Cap-Mushroom": ("other:mushrooms", None),
    "Red-Beet": ("other:beets", None),
    "Orange-Bell-Pepper": ("other:orange bell peppers", None),
    "Yellow-Bell-Pepper": ("other:yellow bell peppers", None),
}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--engine", choices=ENGINES, required=True)
    args = ap.parse_args()

    known = set(all_categories())
    for cat, _ in MAPPING.values():
        assert cat in known or cat.startswith("other:"), cat
    with open(GSD / "classes.csv", encoding="utf-8") as f:
        id_to_name = {r["Class ID (int)"]: r["Class Name (str)"] for r in csv.DictReader(f)}

    labels = {}
    for split in ("train", "val", "test"):
        with open(GSD / f"{split}.txt", encoding="utf-8") as f:
            for line in f:
                path, fine_id, _ = [x.strip() for x in line.split(",")]
                name = id_to_name[fine_id]
                if name in MAPPING:
                    cat, variety = MAPPING[name]
                    labels[path] = {"category": cat, "variety": variety, "gsd_class": name}
    (ROOT / "cache").mkdir(exist_ok=True)
    with open(ROOT / "cache" / "gsd_labels.json", "w", encoding="utf-8") as f:
        json.dump(labels, f)

    engine = load_engine(args.engine)
    cache_path = ROOT / "cache" / f"{args.engine}_gsd.npz"
    cache = load_cache(cache_path, engine.model_id)
    todo = [k for k in labels if k not in cache]
    print(f"{len(labels)} produce photos ({len({v['gsd_class'] for v in labels.values()})} classes), {len(todo)} to embed")
    t0 = time.perf_counter()
    for i in range(0, len(todo), 256):
        chunk = todo[i:i + 256]
        cache.update(zip(chunk, engine.images([cv2.imread(str(GSD / k)) for k in chunk])))
        save_cache(cache_path, cache, engine.model_id)
    if todo:
        print(f"{1000 * (time.perf_counter() - t0) / len(todo):.1f} ms/photo -> {cache_path}")


if __name__ == "__main__":
    main()
