import json
from pathlib import Path
import torch
import numpy as np
from PIL import Image
import open_clip
from sklearn.linear_model import LogisticRegression

device = torch.device("cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu"))
model, _, preprocess = open_clip.create_model_and_transforms('ViT-B-32', pretrained='laion2b_s34b_b79k')
tokenizer = open_clip.get_tokenizer('ViT-B-32')
model = model.to(device).eval()

def load_planogram_text_map():
    p_paths = [Path("dataset/planogram.json"), Path("../dataset/planogram.json")]
    p_file = next((p for p in p_paths if p.exists()), None)
    if not p_file:
        return {}
    with open(p_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    text_map = {}
    for cam_id, cam_info in data["Frutas e Legumes"]["cameras"].items():
        for p in cam_info["products"]:
            text_map[p["area_id"]] = p["product_name"]
    return text_map

class Approach4CLIPPipeline:
    def __init__(self):
        self.area_text_map = load_planogram_text_map()
        self.comp_clf = LogisticRegression(max_iter=500)
        self.stock_clf = LogisticRegression(max_iter=1000, class_weight="balanced")

    def extract_features_and_text_scores(self, records):
        img_feats = []
        text_sims = []

        with torch.no_grad():
            for r in records:
                img = Image.open(r["path"]).convert("RGB")
                img_t = preprocess(img).unsqueeze(0).to(device)
                i_emb = model.encode_image(img_t)
                i_emb /= i_emb.norm(dim=-1, keepdim=True)

                pname = self.area_text_map.get(r["area_id"], "fruta legume fresco")
                text_t = tokenizer([f"uma prateleira com {pname}"]).to(device)
                t_emb = model.encode_text(text_t)
                t_emb /= t_emb.norm(dim=-1, keepdim=True)

                sim = (i_emb @ t_emb.T).item()

                img_feats.append(i_emb.cpu().numpy().flatten())
                text_sims.append(sim)

        img_feats = np.array(img_feats)
        text_sims = np.array(text_sims)[:, np.newaxis]
        combined = np.hstack([img_feats, text_sims])
        return img_feats, combined

    def fit(self, X_img, X_comb, y_comp, y_stock):
        self.stock_clf.fit(X_img, [str(s) for s in y_stock])
        self.comp_clf.fit(X_comb, y_comp)

    def predict(self, X_img, X_comb):
        pred_comp = self.comp_clf.predict(X_comb)

        probs = self.stock_clf.predict_proba(X_img)
        classes = list(self.stock_clf.classes_)
        pred_stock = []
        for prob in probs:
            p_map = {classes[i]: prob[i] for i in range(len(classes))}
            p_0, p_05, p_1 = p_map.get("0.0", 0.0), p_map.get("0.5", 0.0), p_map.get("1.0", 0.0)
            s_0 = (p_0 * 1.0) - 2.0 * (p_05 + p_1)
            s_05 = (p_05 * 1.0) - 3.0 * p_0 - 2.0 * p_1
            s_1 = (p_1 * 1.0) - 3.0 * (p_0 + p_05)
            pred_stock.append(max({0.0: s_0, 0.5: s_05, 1.0: s_1}, key=lambda k: {0.0: s_0, 0.5: s_05, 1.0: s_1}[k]))

        return np.array(pred_comp), np.array(pred_stock)