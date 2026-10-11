import json
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import ConfusionMatrixDisplay, classification_report
from sklearn.model_selection import StratifiedKFold
import torch
import torchvision.transforms as T

HUMAN_FILE = "/Users/laurasofia/programming/extras/junxtion-hackathon/LemmaVeggies/labels/human.jsonl"

# ==========================================
# 1. Setup DINOv2 & Transforms
# ==========================================
device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
dinov2 = torch.hub.load("facebookresearch/dinov2", "dinov2_vits14").to(device)
dinov2.eval()

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


# ==========================================
# 2. Load human.jsonl Data
# ==========================================
X, y = [], []
with open(HUMAN_FILE, "r", encoding="utf-8") as f:
    for line in f:
        data = json.loads(line)
        img_path = Path(f"crops/{data['camera']}/{data['area_id']}/{data['image']}")
        if not img_path.exists():
            continue
        X.append(extract_feature(img_path))
        y.append(str(data["stock_value"]))

X = np.array(X)
y = np.array(y)

# ==========================================
# 3. Stratified 5-Fold with Expected Value Decision
# ==========================================
skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
y_pred_risk = np.empty_like(y)

for train_idx, val_idx in skf.split(X, y):
    X_train_f, X_val_f = X[train_idx], X[val_idx]
    y_train_f = y[train_idx]

    clf = LogisticRegression(max_iter=1000, class_weight="balanced")
    clf.fit(X_train_f, y_train_f)

    # Predict probabilities on out-of-fold validation crops
    val_probs = clf.predict_proba(X_val_f)
    classes = [str(c) for c in clf.classes_]

    for i, probs in enumerate(val_probs):
        prob_dict = {classes[j]: probs[j] for j in range(len(classes))}
        p_0 = prob_dict.get("0.0", 0.0)
        p_05 = prob_dict.get("0.5", 0.0)
        p_1 = prob_dict.get("1.0", 0.0)

        # Expected value scoring from challenge rules (+1 correct, -2 under, -3 over)
        score_if_0 = (p_0 * 1.0) - 2.0 * (p_05 + p_1)
        score_if_05 = (p_05 * 1.0) - 3.0 * p_0 - 2.0 * p_1
        score_if_1 = (p_1 * 1.0) - 3.0 * (p_0 + p_05)

        expected_scores = {"0.0": score_if_0, "0.5": score_if_05, "1.0": score_if_1}
        best_decision = max(expected_scores, key=expected_scores.get)
        y_pred_risk[val_idx[i]] = best_decision

# ==========================================
# 4. Evaluation & Score Computation
# ==========================================
print("\n--- Classification Report (Risk-Weighted Expected Value) ---")
print(classification_report(y, y_pred_risk, target_names=["Empty (0.0)", "Half (0.5)", "Full (1.0)"]))

# Calculate official point yield across the cross-validated dataset
total_points = 0
for true_val, pred_val in zip(y.astype(float), y_pred_risk.astype(float)):
    if pred_val == true_val:
        total_points += 1
    elif pred_val < true_val:
        total_points -= 2
    else:
        total_points -= 3

print(f"Total simulated stock score: {total_points} points (Max possible: {len(y)})")

# ==========================================
# 5. Plot and Save Confusion Matrix
# ==========================================
disp = ConfusionMatrixDisplay.from_predictions(
    y,
    y_pred_risk,
    labels=["0.0", "0.5", "1.0"],
    display_labels=["Empty (0.0)", "Half (0.5)", "Full (1.0)"],
    cmap=plt.cm.Blues
)
plt.title("Stock Level Confusion Matrix (Risk-Weighted Expected Value)")
plt.savefig("confusion_matrix_risk_weighted.png", dpi=300, bbox_inches="tight")
print("Saved matrix to 'confusion_matrix_risk_weighted.png'.")
