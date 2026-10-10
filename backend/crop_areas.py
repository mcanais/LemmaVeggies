"""Crop every planogram area out of every camera image.

Output: <out>/<camera_id>/<area_id>/<timestamp>.png plus <out>/index.csv
(merged with an existing index, so new image batches can be added to the same folder)
(and <out>/_overlays/<camera_id>.jpg with --overlays).
"""
import argparse
import csv
import sys
from pathlib import Path

import cv2

from lemma.crop import bbox_area, draw_areas, warp_area
from lemma.planogram import load_areas

ROOT = Path(__file__).resolve().parent
DATASET = ROOT.parent / "dataset"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--images", type=Path, default=DATASET / "train_test")
    ap.add_argument("--planogram", type=Path, default=DATASET / "planogram.json")
    ap.add_argument("--out", type=Path, default=ROOT / "crops")
    ap.add_argument("--mode", choices=("warp", "bbox"), default="bbox",
                    help="bbox: original pixels, no distortion (default); warp: perspective-rectified")
    ap.add_argument("--no-mask", action="store_true", help="bbox mode: keep pixels outside the area polygon")
    ap.add_argument("--size", type=int, help="resize warped crops to SIZE x SIZE")
    ap.add_argument("--overlays", action="store_true", help="save one annotated image per camera")
    args = ap.parse_args()

    areas = load_areas(args.planogram)
    args.out.mkdir(parents=True, exist_ok=True)
    rows = []

    for cam_dir in sorted(p for p in args.images.iterdir() if p.is_dir()):
        camera_id = cam_dir.name
        if camera_id not in areas:
            print(f"warning: no planogram areas for camera {camera_id}, skipping", file=sys.stderr)
            continue
        images = sorted(cam_dir.glob("*.jpg"))
        for i, img_path in enumerate(images):
            img = cv2.imread(str(img_path))
            if img is None:
                print(f"warning: cannot read {img_path}", file=sys.stderr)
                continue
            if args.overlays and i == len(images) // 2:  # mid-day frame (early ones may be covered)
                overlay_dir = args.out / "_overlays"
                overlay_dir.mkdir(exist_ok=True)
                cv2.imwrite(str(overlay_dir / f"{camera_id}.jpg"), draw_areas(img, areas[camera_id]))
            for a in areas[camera_id]:
                if args.mode == "warp":
                    size = (args.size, args.size) if args.size else None
                    crop = warp_area(img, a.quad, size)
                else:
                    crop = bbox_area(img, a.quad, mask_outside=not args.no_mask)
                # PNG (lossless): JPEG re-compression shifts embeddings vs. cropping in memory at predict time
                crop_path = args.out / camera_id / a.area_id / f"{img_path.stem}.png"
                crop_path.parent.mkdir(parents=True, exist_ok=True)
                cv2.imwrite(str(crop_path), crop)
                rows.append({
                    "camera_id": camera_id,
                    "image": img_path.name,
                    "area_id": a.area_id,
                    "product_id": a.product_id,
                    "product_name": a.product_name,
                    "crop_path": crop_path.relative_to(args.out).as_posix(),
                })
        print(f"{camera_id}: {len(images)} images x {len(areas[camera_id])} areas")

    # Merge with an existing index so new image batches can be added to the same output folder.
    index_path = args.out / "index.csv"
    merged = {}
    if index_path.exists():
        with open(index_path, encoding="utf-8") as f:
            merged = {r["crop_path"]: r for r in csv.DictReader(f)}
    merged.update((r["crop_path"], r) for r in rows)
    with open(index_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ["crop_path"])
        w.writeheader()
        w.writerows(merged.values())
    print(f"wrote {len(rows)} crops to {args.out} ({len(merged)} in index)")


if __name__ == "__main__":
    main()
