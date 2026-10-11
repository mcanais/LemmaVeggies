import torch
import numpy as np
from PIL import Image
from sklearn.neural_network import MLPClassifier
from sklearn.linear_model import LogisticRegression
import torchvision.transforms as T
from eval_utils import compute_competition_score

device = torch.device("cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu"))
dinov2 = torch.hub.load("facebookresearch/dinov2", "dinov2_vitb14").to(device).eval()

transform = T.Compose([
    T.Resize((224, 224)),
    T.ToTensor(),
    T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
])

def extract_features(img_paths):
    feats = []
    with torch.no_grad():
        for p in img_paths:
            img = Image.open(p).convert("RGB")
            t = transform(img).unsqueeze(0).to(device)
            f = dinov2(t).cpu().numpy().flatten()
            feats.append(f)
    return np.array(feats)

class Approach1DINOv2Pipeline:
    def __init__(self):
        self.comp_clf = MLPClassifier(hidden_layer_sizes=(128, 64), max_iter=500, random_state=42)
        self.stock_clf = LogisticRegression(max_iter=1000, class_weight="balanced")

    def fit(self, X_train, y_comp_train, y_stock_train):
        self.comp_clf.fit(X_train, y_comp_train)
        self.stock_clf.fit(X_train, [str(s) for s in y_stock_train])

    def predict(self, X_val):
        pred_comp = self.comp_clf.predict(X_val)

        probs = self.stock_clf.predict_proba(X_val)
        classes = list(self.stock_clf.classes_)

        pred_stock = []
        for prob in probs:
            p_map = {classes[i]: prob[i] for i in range(len(classes))}
            p_0 = p_map.get("0.0", 0.0)
            p_05 = p_map.get("0.5", 0.0)
            p_1 = p_map.get("1.0", 0.0)

            # Asymmetric penalty optimization (+1, -2, -3)
            s_0 = (p_0 * 1.0) - 2.0 * (p_05 + p_1)
            s_05 = (p_05 * 1.0) - 3.0 * p_0 - 2.0 * p_1
            s_1 = (p_1 * 1.0) - 3.0 * (p_0 + p_05)

            best_val = max({0.0: s_0, 0.5: s_05, 1.0: s_1}, key=lambda k: {0.0: s_0, 0.5: s_05, 1.0: s_1}[k])
            pred_stock.append(best_val)

        return np.array(pred_comp), np.array(pred_stock)