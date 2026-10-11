import sys
import json
import cv2
import torch
import numpy as np
import joblib
from pathlib import Path
from PIL import Image
import torchvision.transforms as T

from sam2.build_sam import build_sam2
from sam2.automatic_mask_generator import SAM2AutomaticMaskGenerator

device = torch.device("cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu"))

class SamDinoClassifier:
    def __init__(self):
        print(f"Loading SAM 2 and DINOv2 on {device}...")
        
        # 1. Load SAM 2
        sam_checkpoint = self._resolve_path(["sam2_s.pt", "backend/sam2_s.pt", "../sam2_s.pt"])
        self.sam2_model = build_sam2("sam2_hiera_s.yaml", str(sam_checkpoint), device=device)
        self.mask_generator = SAM2AutomaticMaskGenerator(self.sam2_model)
        
        # 2. Load DINOv2
        self.dinov2 = torch.hub.load("facebookresearch/dinov2", "dinov2_vitb14").to(device).eval()
        self.transform = T.Compose([
            T.Resize((224, 224)),
            T.ToTensor(),
            T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ])
        
        # 3. Load MLP
        models_dir = self._resolve_path(["backend/models", "models"])
        self.comp_clf = joblib.load(models_dir / "sam_dino_comp_clf.joblib")
        
        self.stock_str = {0.0: "empty", 0.5: "half", 1.0: "full"}

    def _resolve_path(self, candidates):
        for p in candidates:
            if Path(p).exists(): return Path(p).resolve()
        return Path(candidates[-1])

    def predict_image(self, img_path):
        img_bgr = cv2.imread(str(img_path))
        img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        h, w = img_rgb.shape[:2]
        total_pixels = h * w
        
        # 1. SAM 2 Foreground Masking
        with torch.no_grad():
            sam_result = self.mask_generator.generate(img_rgb)
            
        combined_mask = np.zeros((h, w), dtype=np.uint8)
        for mask_dict in sam_result:
            if mask_dict['area'] < (total_pixels * 0.95):
                combined_mask = cv2.bitwise_or(combined_mask, mask_dict['segmentation'].astype(np.uint8))
                
        # 2. Deterministic Stock Calculation (Pixel Ratio)
        foreground_ratio = np.sum(combined_mask) / total_pixels
        
        # Strict thresholds to avoid overestimation penalties
        if foreground_ratio < 0.20:
            stock_val = 0.0
        elif foreground_ratio < 0.65:
            stock_val = 0.5
        else:
            stock_val = 1.0

        # 3. Fast-Path for Empty Shelves
        if stock_val == 0.0:
            return {
                "planogram_compliant": True, # Empty shelves are technically compliant (no wrong products)
                "stock_level": self.stock_str[stock_val],
                "stock_value": stock_val
            }

        # 4. Compliance Classification for non-empty shelves
        img_masked = cv2.bitwise_and(img_rgb, img_rgb, mask=combined_mask)
        pil_masked = Image.fromarray(img_masked)
        
        with torch.no_grad():
            t = self.transform(pil_masked).unsqueeze(0).to(device)
            feat = self.dinov2(t).cpu().numpy().flatten().reshape(1, -1)
            
        comp_pred = bool(self.comp_clf.predict(feat)[0])
        
        return {
            "planogram_compliant": comp_pred,
            "stock_level": self.stock_str[stock_val],
            "stock_value": stock_val
        }

def generate_submission(classifier, crops_dir="crops"):
    crops_path = Path(crops_dir) if Path(crops_dir).exists() else Path("../backend/crops")
    output_results = {}
    total_images = 0
    
    print(f"\nProcessing all crops in {crops_path.resolve()}...")
    
    for cam_folder in crops_path.iterdir():
        if not cam_folder.is_dir(): continue
        cam_id = cam_folder.name
        output_results[cam_id] = {}
        
        for area_folder in cam_folder.iterdir():
            if not area_folder.is_dir(): continue
            area_id = area_folder.name
            
            for img_path in area_folder.glob("*.jpg"):
                timestamp = img_path.name
                output_results[cam_id][timestamp] = output_results[cam_id].get(timestamp, {})
                output_results[cam_id][timestamp][area_id] = classifier.predict_image(img_path)
                total_images += 1
                
    out_file = "submission_sam_dino.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(output_results, f, indent=4)
    print(f"Processed {total_images} images. Output saved to {out_file}")

if __name__ == "__main__":
    clf = SamDinoClassifier()
    
    if len(sys.argv) > 1:
        print(json.dumps(clf.predict_image(sys.argv[1]), indent=4))
    else:
        generate_submission(clf)