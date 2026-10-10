"""Load planogram areas from planogram.json."""
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

CORNERS = ("top_left", "top_right", "bottom_right", "bottom_left")


@dataclass
class Area:
    camera_id: str
    area_id: str
    product_id: str
    product_name: str
    quad: np.ndarray  # (4, 2) float32, ordered TL, TR, BR, BL


def load_areas(path: str | Path) -> dict[str, list[Area]]:
    """Return {camera_id: [Area, ...]} from a planogram.json file."""
    with open(path, encoding="utf-8") as f:
        cameras = json.load(f)["Frutas e Legumes"]["cameras"]
    areas = {}
    for camera_id, cam in cameras.items():
        areas[camera_id] = [
            Area(
                camera_id=camera_id,
                area_id=p["area_id"],
                product_id=p["product_id"],
                product_name=p["product_name"],
                quad=np.array([p["image_coordinates"][c] for c in CORNERS], dtype=np.float32),
            )
            for p in cam["products"]
        ]
    return areas
