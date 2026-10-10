"""Classify every crop with a trained model and write the submission.

For each crop in <crops>/<camera>/<area_id>/<image>.jpg:
  - stock level: the level with the best expected score under the brief's points
    (correct +1, too low -2, too high -3), from the classifier's probabilities,
  - compliance: cosine similarity to the area's prototype, below the threshold -> not compliant
    (areas without a prototype are assumed compliant).

Output: submission.json in the annotations.json format
{camera: {image: {area_id: {planogram_compliant, stock_level, stock_value}}}}.
To classify new images (e.g. validation), crop them first with crop_areas.py --images ... --out ...
and pass that folder as --crops.
"""
import argparse
import json
from pathlib import Path

import joblib
from sklearn.metrics.pairwise import cosine_similarity

from lemma.features import FeatureExtractor

ROOT = Path(__file__).resolve().parent
VAL_TO_STR = {0.0: "empty", 0.5: "half", 1.0: "full"}


def best_stock_value(probs: dict[str, float]) -> float:
    """Pick the stock value with the highest expected score under the brief's points."""
    p_0 = probs.get("0.0", 0.0)
    p_05 = probs.get("0.5", 0.0)
    p_1 = probs.get("1.0", 0.0)
    expected_scores = {
        0.0: p_0 * 1 - 2 * (p_05 + p_1),
        0.5: p_05 * 1 - 3 * p_0 - 2 * p_1,
        1.0: p_1 * 1 - 3 * (p_0 + p_05),
    }
    return max(expected_scores, key=expected_scores.get)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", type=Path, default=ROOT / "models" / "model.joblib")
    ap.add_argument("--crops", type=Path, default=ROOT / "crops", help="output folder of crop_areas.py")
    ap.add_argument("--out", type=Path, default=ROOT / "submission.json")
    args = ap.parse_args()

    model = joblib.load(args.model)
    clf = model["stock_classifier"]
    area_prototypes = model["area_prototypes"]
    threshold = model["compliance_threshold"]
    print(f"Model from {model['trained_at']}, trained on {model['trained_on']['crops']} crops")
    extract = FeatureExtractor(model["dinov2_model"])

    print(f"Classifying crops in {args.crops}...")
    output_results: dict = {}
    for cam_folder in sorted(p for p in args.crops.iterdir() if p.is_dir() and not p.name.startswith("_")):
        cam_id = cam_folder.name
        output_results[cam_id] = {}
        for area_folder in sorted(p for p in cam_folder.iterdir() if p.is_dir()):
            area_id = area_folder.name
            for img_path in sorted(area_folder.glob("*.jpg")):
                emb = extract(img_path)

                probs = dict(zip(clf.classes_, clf.predict_proba([emb])[0]))
                stock_value = best_stock_value(probs)

                is_compliant = True
                if area_id in area_prototypes:
                    similarity = cosine_similarity([emb], [area_prototypes[area_id]])[0][0]
                    is_compliant = bool(similarity >= threshold)

                output_results[cam_id].setdefault(img_path.name, {})[area_id] = {
                    "planogram_compliant": is_compliant,
                    "stock_level": VAL_TO_STR[stock_value],
                    "stock_value": stock_value,
                }

    with open(args.out, "w", encoding="utf-8") as out_f:
        json.dump(output_results, out_f, indent=4)
    print(f"Done! Submission saved to {args.out}")


if __name__ == "__main__":
    main()
