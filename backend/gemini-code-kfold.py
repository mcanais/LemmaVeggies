import os
import json
import torch
import numpy as np
from pathlib import Path
from PIL import Image
import torchvision.transforms as T
from sklearn.linear_model import LogisticRegression
from sklearn.metrics.pairwise import cosine_similarity
import matplotlib.pyplot as plt
from sklearn.model_selection import cross_val_predict
from sklearn.metrics import classification_report, ConfusionMatrixDisplay

# ==========================================
# 1. Setup DINOv2 (Metal GPU Accelerated)
# ==========================================
device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
print(f"Loading DINOv2 on {device}...")
dinov2 = torch.hub.load("facebookresearch/dinov2", "dinov2_vits14").to(device)
dinov2.eval()

HUMAN_FILE = "/Users/laurasofia/programming/extras/junxtion-hackathon/LemmaVeggies/labels/human.jsonl"

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

            # Save for Stock Classifier (Convert to string to avoid continuous regression error)
            X_train.append(emb)
            y_stock.append(str(data["stock_value"]))

            # Save for Compliance Prototypes (only if it is actually compliant)
            if data["planogram_compliant"]:
                area = data["area_id"]
                if area not in compliant_embeddings_by_area:
                    compliant_embeddings_by_area[area] = []
                compliant_embeddings_by_area[area].append(emb)

    X_train = np.array(X_train)
    y_stock = np.array(y_stock)

    # ==========================================
    # 3. Evaluation Visualization (Cross-Validation)
    # ==========================================
    print("\nEvaluating model via 5-Fold Cross Validation...")
    eval_clf = LogisticRegression(max_iter=1000, class_weight="balanced")

    # Get cross-validated predictions for all labeled images
    y_pred_cv = cross_val_predict(eval_clf, X_train, y_stock, cv=5)

    print("\n--- Classification Report ---")
    print(classification_report(y_stock, y_pred_cv))

    disp = ConfusionMatrixDisplay.from_predictions(
        y_stock,
        y_pred_cv,
        display_labels=["Empty (0.0)", "Half (0.5)", "Full (1.0)"],
        cmap=plt.cm.Blues
    )
    plt.title("Stock Level Confusion Matrix (Cross-Validated)")
    plt.savefig("confusion_matrix.png", dpi=300, bbox_inches="tight")
    print("Saved visualization to 'confusion_matrix.png'.\n")

    # ==========================================
    # 4. Train Production Logistic Regression
    # ==========================================
    print("Training Final Stock Classifier...")
    clf = LogisticRegression(max_iter=1000, class_weight="balanced")
    clf.fit(X_train, y_stock)

    classes = clf.classes_

    # Calculate prototypes (average embedding) for each area
    area_prototypes = {}
    for area, embs in compliant_embeddings_by_area.items():
        area_prototypes[area] = np.mean(embs, axis=0)

    # ==========================================
    # 5. Evaluate the Entire Store (All Crops)
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
                prob_dict = {str(classes[i]): probs[i] for i in range(len(classes))}

                p_0 = prob_dict.get("0.0", 0.0)
                p_05 = prob_dict.get("0.5", 0.0)
                p_1 = prob_dict.get("1.0", 0.0)

                # Apply the explicit penalty math from the brief:
                # Correct: +1, Underestimate: -2, Overestimate: -3[span_0](start_span)[span_0](end_span)[span_1](start_span)[span_1](end_span)
                score_if_0 = (p_0 * 1) - 2*(p_05 + p_1)
                score_if_05 = (p_05 * 1) - 3*(p_0) - 2*(p_1)
                score_if_1 = (p_1 * 1) - 3*(p_0 + p_05)

                expected_scores = {"0.0": score_if_0, "0.5": score_if_05, "1.0": score_if_1}
                best_guess_str = max(expected_scores, key=expected_scores.get)
                best_guess_val = float(best_guess_str)

                val_to_str = {0.0: "empty", 0.5: "half", 1.0: "full"}
                stock_level = val_to_str[best_guess_val]

                # 3. Determine Compliance via Cosine Similarity
                is_compliant = True
                if area_id in area_prototypes:
                    prototype = area_prototypes[area_id]
                    similarity = cosine_similarity([emb], [prototype])[0][0]
                    # If similarity drops below threshold, flag as non-compliant
                    if similarity < 0.65:
                        is_compliant = False

                # 4. Save format matching annotations structure[span_2](start_span)[span_2](end_span)
                if timestamp not in output_results[cam_id]:
                    output_results[cam_id][timestamp] = {}

                output_results[cam_id][timestamp][area_id] = {
                    "planogram_compliant": is_compliant,
                    "stock_level": stock_level,
                    "stock_value": best_guess_val
                }

    with open("submissionKfold.json", "w", encoding="utf-8") as out_f:
        json.dump(output_results, out_f, indent=4)

    print("Done! Submission saved to submission.json.")


if __name__ == "__main__":
    main()
