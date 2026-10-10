"""Train the stock classifier and compliance prototypes from labelled crops, and save them.

Reads the labels (one JSON object per line: camera, image, area_id, stock_value,
planogram_compliant), embeds each labelled crop with DINOv2 and saves:
  - a logistic regression from embedding to stock value (0.0 / 0.5 / 1.0),
  - one prototype per area: the mean embedding of its crops labelled compliant.

Output: models/model.joblib, used by classify.py.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression

from lemma.features import FeatureExtractor

ROOT = Path(__file__).resolve().parent
COMPLIANCE_THRESHOLD = 0.65  # cosine similarity below this -> not compliant


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--labels", type=Path, default=ROOT / "human.jsonl")
    ap.add_argument("--crops", type=Path, default=ROOT / "crops", help="output folder of crop_areas.py")
    ap.add_argument("--model", type=Path, default=ROOT / "models" / "model.joblib")
    args = ap.parse_args()

    extract = FeatureExtractor()

    print(f"Extracting features from {args.labels}...")
    X_train, y_stock = [], []
    compliant_embeddings_by_area: dict[str, list[np.ndarray]] = {}
    with open(args.labels) as f:
        for line in f:
            data = json.loads(line)
            img_path = args.crops / data["camera"] / data["area_id"] / data["image"]
            if not img_path.exists():
                continue
            emb = extract(img_path)
            X_train.append(emb)
            y_stock.append(str(data["stock_value"]))  # "0.0", "0.5" or "1.0"
            if data["planogram_compliant"]:
                compliant_embeddings_by_area.setdefault(data["area_id"], []).append(emb)

    print(f"Training stock classifier on {len(X_train)} crops...")
    clf = LogisticRegression(max_iter=1000, class_weight="balanced")
    clf.fit(np.array(X_train), np.array(y_stock))

    area_prototypes = {area: np.mean(embs, axis=0) for area, embs in compliant_embeddings_by_area.items()}

    args.model.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({
        "stock_classifier": clf,
        "area_prototypes": area_prototypes,
        "compliance_threshold": COMPLIANCE_THRESHOLD,
        "dinov2_model": extract.model_name,
        "trained_on": {"labels": str(args.labels), "crops": len(X_train)},
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }, args.model)
    print(f"Saved model to {args.model}")


if __name__ == "__main__":
    main()
