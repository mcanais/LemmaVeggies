import os
import json
import torch
import numpy as np
from pathlib import Path
from PIL import Image
import torchvision.transforms as T
from sklearn.linear_model import LogisticRegression
from sklearn.metrics.pairwise import cosine_similarity

# ==========================================
# 1. Setup DINOv2 (Metal GPU Accelerated)
# ==========================================
device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
print(f"Loading DINOv2 on {device}...")
dinov2 = torch.hub.load("facebookresearch/dinov2", "dinov2_vits14").to(device)
dinov2.eval()


HUMAN_FILE = "human.jsonl"


# DINOv2 requires 224x224 crops with ImageNet normalization
transform = T.Compose([
    T.Resize((224, 224)),
    T.ToTensor(),
    T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
])


def extract_feature(image_path):
    img = Image.open(image_path).convert("RGB")
    tensor = transform(img).unsqueeze(0).to(device)
    with torch.no_grad():
        feature = dinov2(tensor)
    return feature.cpu().numpy().flatten()


def main():
    # ==========================================
    # 2. Parse human.jsonl & Extract Training Embeddings
    # ==========================================
    print("Extracting features from human.jsonl...")
    X_train, y_stock = [], []
    compliant_embeddings_by_area = {}

    with open(HUMAN_FILE, "r") as f:
        for line in f:
            data = json.loads(line)
            # Construct the path to the crop: backend/crops/<camera>/<area_id>/<image>
            img_path = Path(f"crops/{data['camera']}/{data['area_id']}/{data['image']}")

            if not img_path.exists():
                continue

            emb = extract_feature(img_path)

            # Save for Stock Classifier
            X_train.append(emb)
            y_stock.append(str(data["stock_value"]))
            # 0.0, 0.5, or 1.0

            # Save for Compliance Prototypes (only if it is actually compliant)
            if data["planogram_compliant"]:
                area = data["area_id"]
                if area not in compliant_embeddings_by_area:
                    compliant_embeddings_by_area[area] = []
                compliant_embeddings_by_area[area].append(emb)

    X_train = np.array(X_train)
    y_stock = np.array(y_stock)

    # ==========================================
    # 3. Train Logistic Regression
    # ==========================================
    print("Training Stock Classifier...")
    clf = LogisticRegression(max_iter=1000, class_weight="balanced")
    clf.fit(X_train, y_stock)

    # Store the classes the model learned so we map probabilities correctly
    classes = clf.classes_

    # Calculate prototypes (average embedding) for each area
    area_prototypes = {}
    for area, embs in compliant_embeddings_by_area.items():
        area_prototypes[area] = np.mean(embs, axis=0)

    # ==========================================
    # 4. Evaluate the Entire Store (All Crops)
    # ==========================================
    print("Evaluating all crops...")
    output_results = {}
    crops_dir = Path("crops")

    for cam_folder in crops_dir.iterdir():
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

                # 1. Extract feature
                emb = extract_feature(img_path)

                # 2. Determine Optimal Stock Level (Risk-Weighted)
                probs = clf.predict_proba([emb])[0]
                prob_dict = {classes[i]: probs[i] for i in range(len(classes))}

                p_0 = prob_dict.get("0.0", 0.0)

                p_05 = prob_dict.get("0.5", 0.0)
                p_1 = prob_dict.get("1.0", 0.0)

                # Apply the explicit penalty math from the brief:
                # Correct: +1, Underestimate: -2, Overestimate: -3
                score_if_0 = (p_0 * 1) - 2*(p_05 + p_1)
                score_if_05 = (p_05 * 1) - 3*(p_0) - 2*(p_1)
                score_if_1 = (p_1 * 1) - 3*(p_0 + p_05)

                expected_scores = {0.0: score_if_0, 0.5: score_if_05, 1.0: score_if_1}
                best_guess_value = max(expected_scores, key=expected_scores.get)

                val_to_str = {0.0: "empty", 0.5: "half", 1.0: "full"}
                stock_level = val_to_str[best_guess_value]

                # 3. Determine Compliance via Cosine Similarity
                is_compliant = True
                if area_id in area_prototypes:
                    prototype = area_prototypes[area_id]
                    similarity = cosine_similarity([emb], [prototype])[0][0]
                    # If similarity drops below threshold, flag as non-compliant
                    if similarity < 0.65:
                        is_compliant = False

                # 4. Save format
                if timestamp not in output_results[cam_id]:
                    output_results[cam_id][timestamp] = {}

                output_results[cam_id][timestamp][area_id] = {
                    "planogram_compliant": is_compliant,
                    "stock_level": stock_level,
                    "stock_value": best_guess_value
                }

    with open("submission.json", "w", encoding="utf-8") as out_f:
        json.dump(output_results, out_f, indent=4)

    print("Done! Submission saved to submission.json.")


if __name__ == "__main__":
    main()
