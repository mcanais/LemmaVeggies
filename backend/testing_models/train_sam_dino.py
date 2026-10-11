import os
import json
import torch
import numpy as np
import cv2
import joblib
from pathlib import Path
from PIL import Image
import torchvision.transforms as T
from sklearn.neural_network import MLPClassifier

# SAM 2 Imports
from sam2.build_sam import build_sam2
from sam2.automatic_mask_generator import SAM2AutomaticMaskGenerator

device = torch.device("cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu"))
print(f"Using device: {device}")

def resolve_path(candidates):
    for p in candidates:
        if Path(p).exists():
            return Path(p).resolve()
    return None

def main():
    human_file = resolve_path(["labels/human.jsonl", "../labels/human.jsonl"])
    crops_dir = resolve_path(["backend/crops", "crops", "../backend/crops"])
    sam_checkpoint = resolve_path(["sam2_s.pt", "backend/sam2_s.pt", "../sam2_s.pt"])

    if not human_file or not crops_dir or not sam_checkpoint:
        raise FileNotFoundError("Could not find human.jsonl, crops directory, or sam2_s.pt weights.")

    # 1. Initialize SAM 2 (Small)
    print("Loading SAM 2...")
    model_cfg = "sam2_hiera_s.yaml" 
    sam2_model = build_sam2(model_cfg, str(sam_checkpoint), device=device)
    mask_generator = SAM2AutomaticMaskGenerator(sam2_model)

    # 2. Initialize DINOv2
    print("Loading DINOv2 ViT-B/14...")
    dinov2 = torch.hub.load("facebookresearch/dinov2", "dinov2_vitb14").to(device).eval()
    transform = T.Compose([
        T.Resize((224, 224)),
        T.ToTensor(),
        T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ])

    records = []
    with open(human_file, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip(): continue
            item = json.loads(line)
            img_path = crops_dir / str(item["camera"]) / str(item["area_id"]) / str(item["image"])
            if img_path.exists():
                records.append({
                    "path": img_path,
                    "compliant": 1 if item["planogram_compliant"] else 0
                })

    X_train, y_comp = [], []
    
    print(f"Extracting masked features for {len(records)} crops...")
    with torch.no_grad():
        for i, r in enumerate(records):
            img_bgr = cv2.imread(str(r["path"]))
            img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
            
            # Generate SAM 2 Masks
            sam_result = mask_generator.generate(img_rgb)
            
            # Combine all valid foreground masks
            h, w = img_rgb.shape[:2]
            combined_mask = np.zeros((h, w), dtype=np.uint8)
            for mask_dict in sam_result:
                # Filter out massive background masks (e.g., bounding boxes covering >95% of the image)
                if mask_dict['area'] < (h * w * 0.95):
                    combined_mask = cv2.bitwise_or(combined_mask, mask_dict['segmentation'].astype(np.uint8))
            
            # Apply Mask to Image (Blackout background)
            img_masked = cv2.bitwise_and(img_rgb, img_rgb, mask=combined_mask)
            
            # Extract DINOv2 features from the isolated produce
            pil_masked = Image.fromarray(img_masked)
            t = transform(pil_masked).unsqueeze(0).to(device)
            feat = dinov2(t).cpu().numpy().flatten()
            
            X_train.append(feat)
            y_comp.append(r["compliant"])
            
            if (i + 1) % 50 == 0:
                print(f"  Processed {i + 1}/{len(records)}")

    # 3. Train the Compliance Classifier
    print("\nTraining Compliance MLP on masked features...")
    comp_clf = MLPClassifier(hidden_layer_sizes=(128, 64), max_iter=500, random_state=42)
    comp_clf.fit(np.array(X_train), y_comp)

    models_dir = Path("backend/models") if Path("backend").exists() else Path("models")
    models_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(comp_clf, models_dir / "sam_dino_comp_clf.joblib")
    print(f"Model saved to {models_dir.resolve()}")

if __name__ == "__main__":
    main()