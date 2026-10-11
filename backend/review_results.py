"""Review one method's compliance verdicts from a benchmark run: per-camera table + image grids.

  python review_results.py --tag phase2 --column dinov2:classifier+gsd:images

Writes results/<tag>_<method>_review.md and contact sheets of the crops it got wrong
(missed wrong products, false alarms) and of what it flags on unlabelled areas.
"""
import argparse
import csv
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

from lemma.crop import bbox_area
from lemma.planogram import load_areas

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent


def sheet(items, images_dir, areas, path, cols=6, size=(200, 150)):
    """Grid of crops with a caption per crop."""
    if not items:
        return False
    tiles = []
    for cam, image, area_id, caption in items:
        img = cv2.imread(str(images_dir / cam / image))
        quad = next(a.quad for a in areas[cam] if a.area_id == area_id)
        t = cv2.resize(bbox_area(img, quad), size)
        t = cv2.copyMakeBorder(t, 34, 0, 0, 0, cv2.BORDER_CONSTANT, value=(255, 255, 255))
        for k, line in enumerate(caption.split("\n")[:2]):
            cv2.putText(t, line[:30], (3, 13 + 16 * k), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 0), 1)
        tiles.append(t)
    blank = np.full_like(tiles[0], 255)
    tiles += [blank] * (-len(tiles) % cols)
    grid = np.vstack([np.hstack(tiles[i:i + cols]) for i in range(0, len(tiles), cols)])
    cv2.imwrite(str(path), grid)
    return True


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--column", required=True, help="<engine>:<method>:<scheme>, e.g. dinov2:classifier:images")
    ap.add_argument("--images", type=Path, default=REPO / "dataset" / "train_test")
    ap.add_argument("--planogram", type=Path, default=REPO / "dataset" / "planogram.json")
    args = ap.parse_args()

    out = ROOT / "results"
    with open(out / f"{args.tag}_predictions.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    engine, method, scheme = args.column.split(":")
    final = f"{engine}:{method}:final"
    col = args.column
    areas = load_areas(args.planogram)

    per_cam = defaultdict(lambda: [0, 0, 0, 0, 0])  # labelled, correct, caught, missed, false alarms
    missed, alarms, unlabelled_flags = [], [], []
    for r in rows:
        lab = r["label_compliant"]
        pred_col = r.get(f"{final}:pred", "")
        if lab and r.get(f"{col}:ok", "") != "":
            ok, truth = r[f"{col}:ok"] == "True", lab == "True"
            c = per_cam[r["camera"]]
            c[0] += 1
            c[1] += ok == truth
            c[2] += (not ok) and (not truth)
            c[3] += ok and (not truth)
            c[4] += (not ok) and truth
            pred = r.get(f"{col}:pred", "")
            cap = f"{r['area_id']} {r['category']}\nsees: {pred or '-'} s={float(r[f'{col}:score']):.2f}"
            if ok and not truth:
                missed.append((r["camera"], r["image"], r["area_id"], cap))
            elif not ok and truth:
                alarms.append((r["camera"], r["image"], r["area_id"], cap))
        elif not lab and r.get(f"{final}:ok") == "False":
            cap = f"{r['area_id']} {r['category']}\nsees: {pred_col} s={float(r[f'{final}:score']):.2f}"
            unlabelled_flags.append((r["camera"], r["image"], r["area_id"], cap))

    name = f"{args.tag}_{engine}_{method}_{scheme}".replace("+", "_")
    lines = [f"# Review: `{col}` ({args.tag})\n",
             "| Camera | Labelled | Correct | Wrong products caught | Missed | False alarms |",
             "|---|---|---|---|---|---|"]
    tot = [0] * 5
    for cam in sorted(per_cam):
        c = per_cam[cam]
        tot = [a + b for a, b in zip(tot, c)]
        lines.append(f"| {cam} | {c[0]} | {c[1]} | {c[2]} | {c[3]} | {c[4]} |")
    lines.append(f"| **all** | {tot[0]} | {tot[1]} | {tot[2]} | {tot[3]} | {tot[4]} |\n")
    for title, items, suffix in (("Missed wrong products", missed, "missed"),
                                 ("False alarms", alarms, "false_alarms"),
                                 ("Flagged on unlabelled areas (final model)", unlabelled_flags, "unlabelled_flags")):
        img = f"{name}_{suffix}.jpg"
        has = sheet(items, args.images, areas, out / img)
        lines.append(f"## {title}: {len(items)}\n")
        if has:
            lines.append(f"![{title}]({img})\n")
        by_area = defaultdict(int)
        for cam, image, area_id, _ in items:
            by_area[area_id] += 1
        if by_area:
            lines.append(", ".join(f"{a} ×{n}" for a, n in sorted(by_area.items(), key=lambda kv: -kv[1])) + "\n")
    with open(out / f"{name}_review.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
