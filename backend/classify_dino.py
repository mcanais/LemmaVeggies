import sys
import json
from pathlib import Path
import torch
from PIL import Image
import torchvision.transforms as T
import numpy as np
import joblib

HERE = Path(__file__).resolve().parent

device = torch.device("cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu"))


class DinoProduceClassifier:
    def __init__(self):
        print(f"Loading models on {device}...")
        self.dinov2 = torch.hub.load("facebookresearch/dinov2", "dinov2_vitb14").to(device)
        self.dinov2.eval()

        self.transform = T.Compose([
            T.Resize((224, 224)),
            T.ToTensor(),
            T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ])

        models_dir = Path("backend/models") if Path("backend/models").exists() else Path("models")

        try:
            self.comp_clf = joblib.load(models_dir / "dino_comp_clf.joblib")
            self.stock_clf = joblib.load(models_dir / "dino_stock_clf.joblib")
        except Exception as e:
            raise FileNotFoundError(f"Could not load trained models from {models_dir}. Run train_dino.py first.\n{e}")

        self.stock_classes = list(self.stock_clf.classes_)
        self.stock_str = {0.0: "empty", 0.5: "half", 1.0: "full"}

    def predict_image(self, img_path):
        """Extracts DINOv2 feature, predicts compliance, and applies asymmetric stock risk logic."""
        img = Image.open(img_path).convert("RGB")
        t = self.transform(img).unsqueeze(0).to(device)

        with torch.no_grad():
            feat = self.dinov2(t).cpu().numpy().flatten().reshape(1, -1)

        # 1. Compliance
        comp_pred = bool(self.comp_clf.predict(feat)[0])

        # 2. Stock (Risk-Weighted +1, -2, -3)
        probs = self.stock_clf.predict_proba(feat)[0]
        p_map = {self.stock_classes[i]: probs[i] for i in range(len(self.stock_classes))}

        p_0 = p_map.get("0.0", 0.0)
        p_05 = p_map.get("0.5", 0.0)
        p_1 = p_map.get("1.0", 0.0)

        s_0 = (p_0 * 1.0) - 2.0 * (p_05 + p_1)
        s_05 = (p_05 * 1.0) - 3.0 * p_0 - 2.0 * p_1
        s_1 = (p_1 * 1.0) - 3.0 * (p_0 + p_05)

        expected_scores = {0.0: s_0, 0.5: s_05, 1.0: s_1}
        best_stock_val = max(expected_scores, key=expected_scores.get)

        return {
            "planogram_compliant": comp_pred,
            "stock_level": self.stock_str[best_stock_val],
            "stock_value": best_stock_val
        }


def generate_submission(classifier, crops_dir="crops"):
    crops_path = Path(crops_dir) if Path(crops_dir).exists() else Path("backend/crops")
    output_results = {}
    total_images = 0
    # 35 36

    print(f"\nProcessing all crops in {crops_path.resolve()}...")

    for cam_folder in crops_path.iterdir():
        if not cam_folder.is_dir():
            continue
        cam_id = cam_folder.name
        output_results[cam_id] = {}

        for area_folder in cam_folder.iterdir():
            if not area_folder.is_dir():
                continue
            area_id = area_folder.name

            for img_path in area_folder.glob("*.jpg"):
                timestamp = img_path.name

                prediction = classifier.predict_image(img_path)

                if timestamp not in output_results[cam_id]:
                    output_results[cam_id][timestamp] = {}

                output_results[cam_id][timestamp][area_id] = prediction
                total_images += 1

    out_file = HERE / "annotations.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(output_results, f, indent=4)
    print(f"Processed {total_images} images. Output saved to {out_file}")


if __name__ == "__main__":
    clf = DinoProduceClassifier()

    if len(sys.argv) > 1:
        target = sys.argv[1]
        print(f"Predicting for {target}:")
        print(json.dumps(clf.predict_image(target), indent=4))
    else:
        generate_submission(clf)
