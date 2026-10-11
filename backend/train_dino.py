import os
import json
from pathlib import Path
import torch
from PIL import Image
import torchvision.transforms as T
import numpy as np
import joblib
from sklearn.neural_network import MLPClassifier
from sklearn.linear_model import LogisticRegression

device = torch.device("cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu"))
print(f"Using device: {device}")

def resolve_path(candidates):
    for p in candidates:
        if Path(p).exists():
            return Path(p).resolve()
    return None

def main():
    # 1. Resolve Paths
    human_file = resolve_path(["labels/human.jsonl", "../labels/human.jsonl"])
    crops_dir = resolve_path(["backend/crops", "crops", "../backend/crops"])

    if not human_file:
        raise FileNotFoundError("Could not find labels/human.jsonl")
    if not crops_dir:
        raise FileNotFoundError("Could not find crops folder")

    # 2. Parse human.jsonl
    records = []
    with open(human_file, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip(): continue
            item = json.loads(line)
            img_path = crops_dir / str(item["camera"]) / str(item["area_id"]) / str(item["image"])
            
            if img_path.exists():
                records.append({
                    "path": img_path,
                    "compliant": 1 if item["planogram_compliant"] else 0,
                    "stock_label": str(item["stock_value"]) # LR needs string classes
                })

    if not records:
        raise ValueError("Dataset is empty. Check your paths.")
    
    print(f"Loaded {len(records)} labeled crops. Loading DINOv2 ViT-B/14...")

    # 3. Load DINOv2 (Frozen)
    dinov2 = torch.hub.load("facebookresearch/dinov2", "dinov2_vitb14").to(device)
    dinov2.eval()

    transform = T.Compose([
        T.Resize((224, 224)),
        T.ToTensor(),
        T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ])

    # 4. Extract Features
    print("Extracting embeddings (this will take a moment)...")
    X_train, y_comp, y_stock = [], [], []
    
    with torch.no_grad():
        for i, r in enumerate(records):
            img = Image.open(r["path"]).convert("RGB")
            t = transform(img).unsqueeze(0).to(device)
            feat = dinov2(t).cpu().numpy().flatten()
            
            X_train.append(feat)
            y_comp.append(r["compliant"])
            y_stock.append(r["stock_label"])
            
            if (i + 1) % 100 == 0:
                print(f"  Extracted {i + 1}/{len(records)} images...")

    X_train = np.array(X_train)

    # 5. Train Classifiers
    print("\nTraining Compliance MLP...")
    comp_clf = MLPClassifier(hidden_layer_sizes=(128, 64), max_iter=500, random_state=42)
    comp_clf.fit(X_train, y_comp)

    print("Training Stock Logistic Regression...")
    stock_clf = LogisticRegression(max_iter=1000, class_weight="balanced", random_state=42)
    stock_clf.fit(X_train, y_stock)

    # 6. Save Models
    models_dir = Path("backend/models") if Path("backend").exists() else Path("models")
    models_dir.mkdir(parents=True, exist_ok=True)
    
    joblib.dump(comp_clf, models_dir / "dino_comp_clf.joblib")
    joblib.dump(stock_clf, models_dir / "dino_stock_clf.joblib")
    
    print(f"\nTraining complete. Models saved to {models_dir.resolve()}")

if __name__ == "__main__":
    main()