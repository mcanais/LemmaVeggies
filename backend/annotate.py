"""Crop and classify a whole image set, writing its annotations.json.

PATH has the same layout as dataset/train_test: <camera_id>/<timestamp>.jpg.
Output: {camera_id: {image: {area_id: {planogram_compliant, stock_level, stock_value}}}}

    python annotate.py PATH [--planogram FILE] [--out FILE] [--crops DIR]
"""
import argparse
import io
import json
import sys
from pathlib import Path

import cv2

from classify_dino import DinoProduceClassifier
from lemma.crop import bbox_area
from lemma.planogram import load_areas

ROOT = Path(__file__).resolve().parent
DATASET = ROOT.parent / "dataset"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("images", type=Path, help="folder with one subfolder per camera id")
    ap.add_argument("--planogram", type=Path, help="default: PATH/planogram.json if present, else dataset/planogram.json")
    ap.add_argument("--out", type=Path, help="default: PATH/annotations.json")
    ap.add_argument("--crops", type=Path, help="also save the crops here as <camera_id>/<area_id>/<timestamp>.jpg")
    args = ap.parse_args()

    planogram = args.planogram or next(
        (p for p in (args.images / "planogram.json", DATASET / "planogram.json") if p.exists()), None)
    if planogram is None:
        sys.exit("no planogram.json found; pass --planogram")
    out = args.out or args.images / "annotations.json"

    areas = load_areas(planogram)
    clf = DinoProduceClassifier()
    results = {}
    total = 0

    for cam_dir in sorted(p for p in args.images.iterdir() if p.is_dir()):
        camera_id = cam_dir.name
        if camera_id not in areas:
            print(f"warning: no planogram areas for camera {camera_id}, skipping", file=sys.stderr)
            continue
        images = sorted(cam_dir.glob("*.jpg"))
        cam_results = results.setdefault(camera_id, {})
        for img_path in images:
            img = cv2.imread(str(img_path))
            if img is None:
                print(f"warning: cannot read {img_path}", file=sys.stderr)
                continue
            frame = cam_results.setdefault(img_path.name, {})
            for a in areas[camera_id]:
                crop = bbox_area(img, a.quad)
                # JPEG round-trip so the classifier sees the same input as the crops it was trained on
                ok, buf = cv2.imencode(".jpg", crop)
                if not ok:
                    print(f"warning: cannot encode crop {a.area_id} of {img_path}", file=sys.stderr)
                    continue
                if args.crops:
                    crop_path = args.crops / camera_id / a.area_id / img_path.name
                    crop_path.parent.mkdir(parents=True, exist_ok=True)
                    crop_path.write_bytes(buf.tobytes())
                frame[a.area_id] = clf.predict_image(io.BytesIO(buf.tobytes()))
                total += 1
        print(f"{camera_id}: {len(images)} images x {len(areas[camera_id])} areas")

    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=4)
    print(f"classified {total} crops, wrote {out}")


if __name__ == "__main__":
    main()
