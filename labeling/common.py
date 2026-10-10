"""Shared helpers for the labelling tools: planogram, images and label files."""

import csv
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parent.parent
PLANOGRAM = REPO / "dataset" / "planogram.json"
IMAGES_DIR = REPO / "dataset" / "train_test"
LABELS_DIR = REPO / "labels"
HUMAN_LABELS = LABELS_DIR / "human.jsonl"
GUIDE = Path(__file__).resolve().parent / "labeling_guide.md"
# Output of backend/crop_areas.py (crops + index.csv).
CROPS_DIR = REPO / "backend" / "crops"

STORE_TZ = ZoneInfo("Europe/Lisbon")
# Suggested subset: per camera, the images closest to these local times, plus the last image
# of the day (closest in time to the validation images). Early frames are skipped because
# some shelves are still covered.
SUGGESTED_TIMES = ("10:45", "15:00")

STOCK_VALUES = {"empty": 0.0, "half": 0.5, "full": 1.0}
CORNERS = ("top_left", "top_right", "bottom_right", "bottom_left")


def load_planogram():
    """Return {camera: [area dict, ...]} with corners as a list of [x, y] in order."""
    data = json.loads(PLANOGRAM.read_text())
    cameras = {}
    for cam, v in data["Frutas e Legumes"]["cameras"].items():
        cameras[cam] = [
            {
                "area_id": p["area_id"],
                "product_name": p["product_name"],
                "polygon": [p["image_coordinates"][c] for c in CORNERS],
            }
            for p in v["products"]
        ]
    return cameras


def list_images():
    """Return sorted [(camera, filename)] for every image."""
    return sorted((p.parent.name, p.name) for p in IMAGES_DIR.glob("*/*.jpg"))


def suggested_images(images):
    """Return the set of (camera, image) to label first: a few spread over each camera's day."""
    by_cam = {}
    for cam, img in images:
        by_cam.setdefault(cam, []).append(img)
    picks = set()
    for cam, imgs in by_cam.items():
        local = {i: datetime.fromtimestamp(int(Path(i).stem), STORE_TZ) for i in imgs}
        minutes = {i: t.hour * 60 + t.minute for i, t in local.items()}
        for hhmm in SUGGESTED_TIMES:
            h, m = map(int, hhmm.split(":"))
            picks.add((cam, min(imgs, key=lambda i: abs(minutes[i] - (h * 60 + m)))))
        picks.add((cam, max(imgs)))
    return picks


def load_crop_index():
    """Return {(camera, image, area_id): crop file} from the cropper's index.csv, or {} if absent."""
    index = CROPS_DIR / "index.csv"
    if not index.exists():
        return {}
    with index.open(newline="", encoding="utf-8") as f:
        return {(r["camera_id"], r["image"], r["area_id"]): CROPS_DIR / r["crop_path"] for r in csv.DictReader(f)}


def load_human_labels():
    """Return {(camera, image, area_id): label} from labels/human.jsonl. Later lines win."""
    if not HUMAN_LABELS.exists():
        return {}
    rows = [json.loads(line) for line in HUMAN_LABELS.read_text().splitlines() if line.strip()]
    return {(r["camera"], r["image"], r["area_id"]): r for r in rows}
