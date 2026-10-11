import sys
import json
import torch
import torch.nn as nn
import torchvision.models as models
import torchvision.transforms as T
from PIL import Image
from pathlib import Path

device = torch.device("cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu"))

# ---------------------------------------------------------
# 1. Load Model Definition
# ---------------------------------------------------------
class ShelfMultiTaskModel(nn.Module):
    def __init__(self):
        super().__init__()
        self.backbone = models.convnext_tiny(weights=None)
        in_feats = self.backbone.classifier[2].in_features
        self.backbone.classifier[2] = nn.Identity()
        
        self.comp_head = nn.Sequential(
            nn.Linear(in_feats, 128), nn.ReLU(), nn.Dropout(0.2), nn.Linear(128, 2)
        )
        self.stock_head = nn.Sequential(
            nn.Linear(in_feats, 128), nn.ReLU(), nn.Dropout(0.2), nn.Linear(128, 3)
        )

    def forward(self, x):
        feats = self.backbone(x)
        return self.comp_head(feats), self.stock_head(feats)

# ---------------------------------------------------------
# 2. Classifier Class
# ---------------------------------------------------------
class ProduceClassifier:
    def __init__(self, weights_path="models/convnext_multitask.pt"):
        self.model = ShelfMultiTaskModel().to(device)
        if not Path(weights_path).exists():
            raise FileNotFoundError(f"Weights not found at {weights_path}. Run train.py first.")
            
        self.model.load_state_dict(torch.load(weights_path, map_location=device))
        self.model.eval()
        
        self.transform = T.Compose([
            T.Resize((224, 224)),
            T.ToTensor(),
            T.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
        ])
        
        self.stock_inv = {0: 0.0, 1: 0.5, 2: 1.0}
        self.stock_str = {0.0: "empty", 0.5: "half", 1.0: "full"}

    def predict_image(self, img_path):
        """Runs a single image through the network and applies the competition risk logic."""
        img = Image.open(img_path).convert("RGB")
        tensor = self.transform(img).unsqueeze(0).to(device)

        with torch.no_grad():
            c_logits, s_logits = self.model(tensor)
            
            # Compliance Prediction
            comp_pred = bool(torch.argmax(c_logits, dim=1).item())
            
            # Stock Prediction (with explicit asymmetric risk handling)
            s_probs = torch.softmax(s_logits, dim=1)[0].cpu().numpy()
            p_0, p_05, p_1 = s_probs[0], s_probs[1], s_probs[2]
            
            # Calculate expected points based on the scoring rubric (+1, -2, -3)
            s_0 = (p_0 * 1.0) - 2.0 * (p_05 + p_1)
            s_05 = (p_05 * 1.0) - 3.0 * p_0 - 2.0 * p_1
            s_1 = (p_1 * 1.0) - 3.0 * (p_0 + p_05)
            
            best_idx = max({0: s_0, 1: s_05, 2: s_1}, key=lambda k: {0: s_0, 1: s_05, 2: s_1}[k])
            stock_val = self.stock_inv[best_idx]
            
        return {
            "planogram_compliant": comp_pred,
            "stock_level": self.stock_str[stock_val],
            "stock_value": stock_val
        }

# ---------------------------------------------------------
# 3. Execution Router
# ---------------------------------------------------------
def generate_submission(classifier, crops_dir="crops"):
    """Evaluates all crops in the directory and writes submission.json."""
    crops_path = Path(crops_dir)
    if not crops_path.exists():
        crops_path = Path("../backend/crops")
        
    output_results = {}
    total_images = 0
    
    for cam_folder in crops_path.iterdir():
        if not cam_folder.is_dir(): continue
        cam_id = cam_folder.name
        output_results[cam_id] = {}
        
        for area_folder in cam_folder.iterdir():
            if not area_folder.is_dir(): continue
            area_id = area_folder.name
            
            for img_path in area_folder.glob("*.jpg"):
                timestamp = img_path.name
                
                prediction = classifier.predict_image(img_path)
                
                if timestamp not in output_results[cam_id]:
                    output_results[cam_id][timestamp] = {}
                    
                output_results[cam_id][timestamp][area_id] = prediction
                total_images += 1
                
    with open("submission.json", "w", encoding="utf-8") as f:
        json.dump(output_results, f, indent=4)
    print(f"Processed {total_images} images. Output saved to submission.json")


if __name__ == "__main__":
    clf = ProduceClassifier()
    
    # If a specific image path is passed as an argument, classify just that image
    if len(sys.argv) > 1:
        target = sys.argv[1]
        print(f"Predicting for {target}:")
        print(json.dumps(clf.predict_image(target), indent=4))
    else:
        # Otherwise, process the whole store and generate submission.json
        print("No image provided. Processing all crops to generate submission.json...")
        generate_submission(clf)