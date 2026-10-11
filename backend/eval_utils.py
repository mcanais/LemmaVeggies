import json
from pathlib import Path
import numpy as np


def compute_competition_score(y_comp_true, y_comp_pred, y_stock_true, y_stock_pred):
    """
    Official Sensei Challenge Scoring:
    - Identification: +1 if correct, -2 if wrong
    - Stock:
        +1 if correct
        -2 if predicted < true (underestimate)
        -3 if predicted > true (overestimate)
    """
    total_score = 0
    id_correct, id_wrong = 0, 0
    stock_correct, stock_under, stock_over = 0, 0, 0

    for c_true, c_pred, s_true, s_pred in zip(y_comp_true, y_comp_pred, y_stock_true, y_stock_pred):
        # 1. Identification
        if bool(c_true) == bool(c_pred):
            total_score += 1
            id_correct += 1
        else:
            total_score -= 2
            id_wrong += 1

        # 2. Stock Level
        s_true_val = float(s_true)
        s_pred_val = float(s_pred)
        if np.isclose(s_true_val, s_pred_val):
            total_score += 1
            stock_correct += 1
        elif s_pred_val < s_true_val:
            total_score -= 2
            stock_under += 1
        else:
            total_score -= 3
            stock_over += 1

    max_possible = len(y_comp_true) * 2
    return {
        "total_score": total_score,
        "max_possible": max_possible,
        "id_accuracy": id_correct / len(y_comp_true),
        "stock_accuracy": stock_correct / len(y_stock_true),
        "details": {
            "id_correct": id_correct,
            "id_wrong": id_wrong,
            "stock_correct": stock_correct,
            "stock_under": stock_under,
            "stock_over": stock_over,
        }
    }


def load_human_dataset():
    paths_to_try = [
        Path("labels/human.jsonl"),
        Path("../labels/human.jsonl"),
        Path("/Users/laurasofia/programming/extras/junxtion-hackathon/LemmaVeggies/labels/human.jsonl")
    ]
    human_file = next((p for p in paths_to_try if p.exists()), None)
    if not human_file:
        raise FileNotFoundError("Could not find labels/human.jsonl")

    crops_bases = [Path("backend/crops"), Path("crops"), Path("../backend/crops")]
    crops_dir = next((p for p in crops_bases if p.exists()), None)
    if not crops_dir:
        raise FileNotFoundError("Could not find backend/crops or crops directory")

    records = []
    with open(human_file, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            item = json.loads(line)
            img_path = crops_dir / str(item["camera"]) / str(item["area_id"]) / str(item["image"])
            if img_path.exists():
                records.append({
                    "path": str(img_path),
                    "camera": str(item["camera"]),
                    "area_id": str(item["area_id"]),
                    "image": str(item["image"]),
                    "compliant": bool(item["planogram_compliant"]),
                    "stock_value": float(item["stock_value"])
                })
    return records
