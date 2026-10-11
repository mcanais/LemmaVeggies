import json
import os
from pathlib import Path
import numpy as np
import cv2
from PIL import Image
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
import torchvision.models as models
import torchvision.transforms as T
from sklearn.model_selection import StratifiedKFold
from sklearn.neural_network import MLPClassifier
from sklearn.linear_model import LogisticRegression
import random

from eval_utils import compute_competition_score, load_human_dataset

device = torch.device("cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu"))
print(f"Running benchmark on device: {device}")

# =====================================================================
# 1. ConvNeXt Setup (Approach 1)
# =====================================================================


class ShelfMultiTaskModel(nn.Module):
    def __init__(self):
        super().__init__()
        backbone = models.convnext_tiny(weights=models.ConvNeXt_Tiny_Weights.DEFAULT)
        in_feats = backbone.classifier[2].in_features
        backbone.classifier[2] = nn.Identity()
        self.backbone = backbone
        self.comp_head = nn.Sequential(nn.Linear(in_feats, 128), nn.ReLU(), nn.Linear(128, 2))
        self.stock_head = nn.Sequential(nn.Linear(in_feats, 128), nn.ReLU(), nn.Linear(128, 3))

    def forward(self, x):
        feats = self.backbone(x)
        return self.comp_head(feats), self.stock_head(feats)


class TorchProduceDataset(Dataset):
    def __init__(self, records, transform=None):
        self.records = records
        self.transform = transform
        self.stock_map = {0.0: 0, 0.5: 1, 1.0: 2}

    def __len__(self):
        return len(self.records)

    def __getitem__(self, idx):
        item = self.records[idx]
        img = Image.open(item["path"]).convert("RGB")
        if self.transform:
            img = self.transform(img)
        comp_lbl = 1 if item["compliant"] else 0
        stock_lbl = self.stock_map.get(float(item["stock_value"]), 0)
        return img, comp_lbl, stock_lbl


convnext_train_tf = T.Compose([
    T.Resize((224, 224)),
    T.RandomHorizontalFlip(),
    T.ColorJitter(brightness=0.15, contrast=0.15),
    T.ToTensor(),
    T.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
])

convnext_val_tf = T.Compose([
    T.Resize((224, 224)),
    T.ToTensor(),
    T.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
])


def evaluate_convnext(train_recs, val_recs, epochs=4):
    model = ShelfMultiTaskModel().to(device)
    train_loader = DataLoader(TorchProduceDataset(train_recs, convnext_train_tf), batch_size=16, shuffle=True)
    val_loader = DataLoader(TorchProduceDataset(val_recs, convnext_val_tf), batch_size=16, shuffle=False)

    crit_comp = nn.CrossEntropyLoss()
    crit_stock = nn.CrossEntropyLoss()
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-4, weight_decay=1e-3)

    model.train()
    for _ in range(epochs):
        for imgs, comp_lbl, stock_lbl in train_loader:
            imgs, comp_lbl, stock_lbl = imgs.to(device), comp_lbl.to(device), stock_lbl.to(device)
            optimizer.zero_grad()
            c_logits, s_logits = model(imgs)
            loss = crit_comp(c_logits, comp_lbl) + 1.2 * crit_stock(s_logits, stock_lbl)
            loss.backward()
            optimizer.step()

    model.eval()
    pred_comps, pred_stocks = [], []
    stock_inv = {0: 0.0, 1: 0.5, 2: 1.0}

    with torch.no_grad():
        for imgs, _, _ in val_loader:
            imgs = imgs.to(device)
            c_logits, s_logits = model(imgs)
            pred_comps.extend([bool(cp) for cp in torch.argmax(c_logits, dim=1).cpu().numpy()])

            s_probs = torch.softmax(s_logits, dim=1).cpu().numpy()
            for prob in s_probs:
                p_0, p_05, p_1 = prob[0], prob[1], prob[2]
                s_0 = (p_0 * 1.0) - 2.0 * (p_05 + p_1)
                s_05 = (p_05 * 1.0) - 3.0 * p_0 - 2.0 * p_1
                s_1 = (p_1 * 1.0) - 3.0 * (p_0 + p_05)
                best_cls = max({0: s_0, 1: s_05, 2: s_1}, key=lambda k: {0: s_0, 1: s_05, 2: s_1}[k])
                pred_stocks.append(stock_inv[best_cls])

    return np.array(pred_comps), np.array(pred_stocks)

# =====================================================================
# 2. Risk-Weighted Stock Scoring for DINOv2
# =====================================================================


def get_risk_weighted_stock_predictions(stock_clf, X_val):
    probs = stock_clf.predict_proba(X_val)
    classes = list(stock_clf.classes_)
    pred_stock = []
    for prob in probs:
        p_map = {classes[i]: prob[i] for i in range(len(classes))}
        p_0 = p_map.get("0.0", 0.0)
        p_05 = p_map.get("0.5", 0.0)
        p_1 = p_map.get("1.0", 0.0)

        s_0 = (p_0 * 1.0) - 2.0 * (p_05 + p_1)
        s_05 = (p_05 * 1.0) - 3.0 * p_0 - 2.0 * p_1
        s_1 = (p_1 * 1.0) - 3.0 * (p_0 + p_05)
        pred_stock.append(max({0.0: s_0, 0.5: s_05, 1.0: s_1}, key=lambda k: {0.0: s_0, 0.5: s_05, 1.0: s_1}[k]))
    return np.array(pred_stock)

# =====================================================================
# 3. Main Comparative Benchmark
# =====================================================================


def main():
    records = load_human_dataset()
    random.seed(42)
    records = random.sample(records, 200)
    print(f"Loaded {len(records)} verified crop annotations from human.jsonl.")

    # -------------------------------------------------------------
    # Step A: Pre-extract Raw DINOv2 Embeddings
    # -------------------------------------------------------------
    print("\n[1/3] Extracting raw DINOv2 ViT-B/14 features...")
    dinov2 = torch.hub.load("facebookresearch/dinov2", "dinov2_vitb14").to(device).eval()
    dino_tf = T.Compose([
        T.Resize((224, 224)),
        T.ToTensor(),
        T.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
    ])

    X_raw_dino = []
    with torch.no_grad():
        for i, r in enumerate(records):
            img = Image.open(r["path"]).convert("RGB")
            t = dino_tf(img).unsqueeze(0).to(device)
            X_raw_dino.append(dinov2(t).cpu().numpy().flatten())
            if (i + 1) % 250 == 0:
                print(f"  Processed {i + 1}/{len(records)} raw crops")
    X_raw_dino = np.array(X_raw_dino)

    # -------------------------------------------------------------
    # Step B: Precompute SAM 2 Foreground Masks & Masked DINO Embeddings
    # -------------------------------------------------------------
    print("\n[2/3] Extracting SAM 2 masks and masked DINOv2 features...")
    from sam2.build_sam import build_sam2
    from sam2.automatic_mask_generator import SAM2AutomaticMaskGenerator

    sam_ckpt = next(p for p in [Path("sam2_s.pt"), Path("backend/sam2_s.pt"), Path("../sam2_s.pt")] if p.exists())
    sam_model = build_sam2("sam2_hiera_s.yaml", str(sam_ckpt), device=device)
    mask_gen = SAM2AutomaticMaskGenerator(sam_model)

    sam_stock_ratios = []
    X_masked_dino = []

    with torch.no_grad():
        for i, r in enumerate(records):
            img_bgr = cv2.imread(str(r["path"]))
            img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
            h, w = img_rgb.shape[:2]
            total_pixels = h * w

            masks = mask_gen.generate(img_rgb)
            combined_mask = np.zeros((h, w), dtype=np.uint8)
            for m in masks:
                if m["area"] < (total_pixels * 0.95):
                    combined_mask = cv2.bitwise_or(combined_mask, m["segmentation"].astype(np.uint8))

            ratio = np.sum(combined_mask) / float(total_pixels)
            sam_stock_ratios.append(ratio)

            img_masked = cv2.bitwise_and(img_rgb, img_rgb, mask=combined_mask)
            pil_masked = Image.fromarray(img_masked)
            t = dino_tf(pil_masked).unsqueeze(0).to(device)
            X_masked_dino.append(dinov2(t).cpu().numpy().flatten())

            if (i + 1) % 100 == 0:
                print(f"  Segmented and masked {i + 1}/{len(records)} crops")

    sam_stock_ratios = np.array(sam_stock_ratios)
    X_masked_dino = np.array(X_masked_dino)

    # -------------------------------------------------------------
    # Step C: Stratified 5-Fold Cross Validation
    # -------------------------------------------------------------
    print("\n[3/3] Running Stratified 5-Fold Cross-Validation...")
    strat_keys = [f"{r['compliant']}_{r['stock_value']}" for r in records]
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)

    results = {
        "Multi-Task ConvNeXt": {"scores": [], "id_acc": [], "stock_acc": []},
        "DINOv2 (Without SAM)": {"scores": [], "id_acc": [], "stock_acc": []},
        "SAM 2 + DINOv2": {"scores": [], "id_acc": [], "stock_acc": []}
    }

    for fold, (train_idx, val_idx) in enumerate(skf.split(records, strat_keys), 1):
        print(f"\n--- Fold {fold}/5 ---")
        train_recs = [records[i] for i in train_idx]
        val_recs = [records[i] for i in val_idx]

        y_comp_train = [r["compliant"] for r in train_recs]
        y_stock_train = [str(r["stock_value"]) for r in train_recs]
        y_comp_val = [r["compliant"] for r in val_recs]
        y_stock_val = [r["stock_value"] for r in val_recs]

        # 1. Multi-Task ConvNeXt
        c_p1, s_p1 = evaluate_convnext(train_recs, val_recs, epochs=4)
        sc1 = compute_competition_score(y_comp_val, c_p1, y_stock_val, s_p1)
        results["Multi-Task ConvNeXt"]["scores"].append(sc1["total_score"])
        results["Multi-Task ConvNeXt"]["id_acc"].append(sc1["id_accuracy"])
        results["Multi-Task ConvNeXt"]["stock_acc"].append(sc1["stock_accuracy"])

        # 2. DINOv2 (Without SAM)
        comp_mlp_raw = MLPClassifier(hidden_layer_sizes=(128, 64), max_iter=500, random_state=42)
        comp_mlp_raw.fit(X_raw_dino[train_idx], y_comp_train)
        c_p2 = comp_mlp_raw.predict(X_raw_dino[val_idx])

        stock_lr = LogisticRegression(max_iter=1000, class_weight="balanced", random_state=42)
        stock_lr.fit(X_raw_dino[train_idx], y_stock_train)
        s_p2 = get_risk_weighted_stock_predictions(stock_lr, X_raw_dino[val_idx])

        sc2 = compute_competition_score(y_comp_val, c_p2, y_stock_val, s_p2)
        results["DINOv2 (Without SAM)"]["scores"].append(sc2["total_score"])
        results["DINOv2 (Without SAM)"]["id_acc"].append(sc2["id_accuracy"])
        results["DINOv2 (Without SAM)"]["stock_acc"].append(sc2["stock_accuracy"])

        # 3. SAM 2 + DINOv2
        comp_mlp_masked = MLPClassifier(hidden_layer_sizes=(128, 64), max_iter=500, random_state=42)
        comp_mlp_masked.fit(X_masked_dino[train_idx], y_comp_train)
        raw_comp_pred = comp_mlp_masked.predict(X_masked_dino[val_idx])

        val_ratios = sam_stock_ratios[val_idx]
        c_p3, s_p3 = [], []
        for r_val, c_val in zip(val_ratios, raw_comp_pred):
            if r_val < 0.20:
                s_p3.append(0.0)
                c_p3.append(True)  # Empty shelves contain no misplaced product
            elif r_val < 0.65:
                s_p3.append(0.5)
                c_p3.append(bool(c_val))
            else:
                s_p3.append(1.0)
                c_p3.append(bool(c_val))

        sc3 = compute_competition_score(y_comp_val, c_p3, y_stock_val, s_p3)
        results["SAM 2 + DINOv2"]["scores"].append(sc3["total_score"])
        results["SAM 2 + DINOv2"]["id_acc"].append(sc3["id_accuracy"])
        results["SAM 2 + DINOv2"]["stock_acc"].append(sc3["stock_accuracy"])

    # -------------------------------------------------------------
    # Step D: Final Summary Table
    # -------------------------------------------------------------
    print("\n" + "=" * 70)
    print("FINAL 3-WAY BENCHMARK RESULTS (Sensei Official Rubric)")
    print("=" * 70)
    print(f"{'Model Architecture':26s} | {'Score (pts)':16s} | {'ID Acc':8s} | {'Stock Acc':9s}")
    print("-" * 70)

    best_model, best_score = None, -float("inf")
    for name, data in results.items():
        mean_score = np.mean(data["scores"])
        std_score = np.std(data["scores"])
        mean_id = np.mean(data["id_acc"]) * 100
        mean_stock = np.mean(data["stock_acc"]) * 100

        print(f"{name:26s} | {mean_score:5.1f} ± {std_score:4.1f} pts  | {mean_id:5.1f}%  | {mean_stock:5.1f}%")

        if mean_score > best_score:
            best_score = mean_score
            best_model = name

    print("-" * 70)
    print(f"Winner: {best_model} ({best_score:.1f} pts)")
    print("=" * 70)


if __name__ == "__main__":
    main()
