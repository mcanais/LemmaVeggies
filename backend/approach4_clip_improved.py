import json
import re
from pathlib import Path
import torch
import numpy as np
from PIL import Image
import open_clip
from sklearn.linear_model import LogisticRegression

device = torch.device("cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu"))

# 1. Higher-capacity CLIP model (ViT-B-16 yields clearer fine-grained texture representations)
model, _, preprocess = open_clip.create_model_and_transforms('ViT-B-16', pretrained='laion2b_s34b_b88k')
tokenizer = open_clip.get_tokenizer('ViT-B-16')
model = model.to(device).eval()

# ---------------------------------------------------------
# Translation & Sanitization Table for Portuguese Supermarket Names
# ---------------------------------------------------------
TRANSLATION_MAP = {
    "banana": "bananas",
    "maca": "apples",
    "maçã": "apples",
    "pera": "pears",
    "melancia": "watermelons",
    "melao": "melons",
    "melão": "melons",
    "meloa": "cantaloupe melons",
    "limao": "lemons",
    "limão": "lemons",
    "lima": "limes",
    "kiwi": "kiwis",
    "laranja": "oranges",
    "clementina": "clementines",
    "alface": "lettuce",
    "abacate": "avocados",
    "pimento": "bell peppers",
    "couve": "cabbage",
    "beringela": "eggplants",
    "chuchu": "chayote squash",
    "feijao": "green beans",
    "feijão": "green beans",
    "pepino": "cucumbers",
    "curgete": "zucchini",
    "tomate": "tomatoes",
    "morango": "strawberries",
    "manga": "mangoes",
    "uva": "grapes",
    "cereja": "cherries",
    "abacaxi": "pineapples",
    "pitaya": "dragon fruits",
    "goiaba": "guavas",
    "maracuja": "passion fruits",
    "maracujá": "passion fruits",
    "granadilha": "passion fruits",
    "mamao": "papayas",
    "mamão": "papayas",
    "papaia": "papayas",
    "alperce": "apricots",
    "pessego": "peaches",
    "pêssego": "peaches",
    "nectarina": "nectarines",
    "batata": "potatoes",
    "gengibre": "ginger roots",
    "abobora": "pumpkins",
    "abóbora": "pumpkins",
    "cebola": "onions",
    "cebolinha": "spring onions",
    "alho": "garlic bulbs",
}

def clean_produce_name(raw_name: str) -> str:
    """Removes packaging/caliber noise and extracts the clean English produce term."""
    lower = raw_name.lower()
    for pt_word, en_word in TRANSLATION_MAP.items():
        if pt_word in lower:
            # Check for specific modifiers (e.g. green, red, cherry)
            if "cherry" in lower:
                return f"cherry {en_word}"
            if "vermelh" in lower:
                return f"red {en_word}"
            if "verd" in lower:
                return f"green {en_word}"
            if "rox" in lower:
                return f"purple {en_word}"
            return en_word
    
    # Fallback: strip technical supermarket acronyms
    cleaned = re.sub(r'\b(cnt|cal|kg|imp|emb|sc|bio|r0|int|gr|g|cal\.\d+/\d+|\d+/\d+|\d+g|\d+kg)\b', '', lower)
    return cleaned.strip()

def load_planogram_text_map():
    p_paths = [Path("dataset/planogram.json"), Path("../dataset/planogram.json")]
    p_file = next((p for p in p_paths if p.exists()), None)
    if not p_file:
        return {}
    with open(p_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    text_map = {}
    for _, cam_info in data["Frutas e Legumes"]["cameras"].items():
        for p in cam_info["products"]:
            text_map[p["area_id"]] = clean_produce_name(p["product_name"])
    return text_map

class Approach4CLIPPipeline:
    def __init__(self):
        self.area_text_map = load_planogram_text_map()
        self.comp_clf = LogisticRegression(max_iter=1000, class_weight="balanced")
        self.stock_clf = LogisticRegression(max_iter=1000, class_weight="balanced")
        
        # Precompute prompt embeddings for the empty state
        empty_prompts = [
            "an empty grocery store shelf bin",
            "an empty retail crate with no produce",
            "a vacant store shelf divider with nothing inside"
        ]
        with torch.no_grad():
            t_tok = tokenizer(empty_prompts).to(device)
            e_embs = model.encode_text(t_tok)
            e_embs /= e_embs.norm(dim=-1, keepdim=True)
            self.empty_emb = e_embs.mean(dim=0, keepdim=True)

    def get_product_prototype(self, product_en: str):
        prompts = [
            f"a photo of fresh {product_en} on a grocery store shelf",
            f"a crate filled with {product_en} in a supermarket",
            f"fresh organic {product_en} displayed loose in a store bin",
            f"close up photo of {product_en}"
        ]
        with torch.no_grad():
            tokens = tokenizer(prompts).to(device)
            embs = model.encode_text(tokens)
            embs /= embs.norm(dim=-1, keepdim=True)
            return embs.mean(dim=0, keepdim=True)

    def extract_features_and_text_scores(self, records):
        img_feats = []
        similarity_features = []

        # Cache product prototypes so we only compute them once per unique name
        proto_cache = {}

        with torch.no_grad():
            for r in records:
                img = Image.open(r["path"]).convert("RGB")
                img_t = preprocess(img).unsqueeze(0).to(device)
                i_emb = model.encode_image(img_t)
                i_emb /= i_emb.norm(dim=-1, keepdim=True)

                pname_en = self.area_text_map.get(r["area_id"], "fresh produce")
                if pname_en not in proto_cache:
                    proto_cache[pname_en] = self.get_product_prototype(pname_en)
                
                target_proto = proto_cache[pname_en]

                # Semantic cues:
                sim_target = (i_emb @ target_proto.T).item()
                sim_empty = (i_emb @ self.empty_emb.T).item()
                contrast_score = sim_target - sim_empty

                img_feats.append(i_emb.cpu().numpy().flatten())
                similarity_features.append([sim_target, sim_empty, contrast_score])

        img_feats = np.array(img_feats)
        similarity_features = np.array(similarity_features)

        # Concatenate visual embedding with the semantic prompt signals
        combined_features = np.hstack([img_feats, similarity_features])
        return img_feats, combined_features

    def fit(self, X_img, X_comb, y_comp, y_stock):
        self.stock_clf.fit(X_comb, [str(s) for s in y_stock])
        self.comp_clf.fit(X_comb, y_comp)

    def predict(self, X_img, X_comb):
        pred_comp = self.comp_clf.predict(X_comb)

        probs = self.stock_clf.predict_proba(X_comb)
        classes = list(self.stock_clf.classes_)
        pred_stock = []
        
        for prob in probs:
            p_map = {classes[i]: prob[i] for i in range(len(classes))}
            p_0 = p_map.get("0.0", 0.0)
            p_05 = p_map.get("0.5", 0.0)
            p_1 = p_map.get("1.0", 0.0)
            
            # Risk-weighted stock decision (+1 / -2 / -3)
            s_0 = (p_0 * 1.0) - 2.0 * (p_05 + p_1)
            s_05 = (p_05 * 1.0) - 3.0 * p_0 - 2.0 * p_1
            s_1 = (p_1 * 1.0) - 3.0 * (p_0 + p_05)
            
            pred_stock.append(max({0.0: s_0, 0.5: s_05, 1.0: s_1}, key=lambda k: {0.0: s_0, 0.5: s_05, 1.0: s_1}[k]))

        return np.array(pred_comp), np.array(pred_stock)