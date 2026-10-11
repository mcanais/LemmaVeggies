import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
import torchvision.models as models
import torchvision.transforms as T
from PIL import Image
import numpy as np

device = torch.device("cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu"))

class ShelfMultiTaskModel(nn.Module):
    def __init__(self):
        super().__init__()
        backbone = models.convnext_tiny(weights=models.ConvNeXt_Tiny_Weights.DEFAULT)
        in_feats = backbone.classifier[2].in_features
        backbone.classifier[2] = nn.Identity()
        self.backbone = backbone

        # Head 1: Binary Planogram Compliance
        self.comp_head = nn.Sequential(
            nn.Linear(in_feats, 128),
            nn.ReLU(),
            nn.Linear(128, 2)
        )
        # Head 2: Stock Level (0.0, 0.5, 1.0)
        self.stock_head = nn.Sequential(
            nn.Linear(in_feats, 128),
            nn.ReLU(),
            nn.Linear(128, 3)
        )

    def forward(self, x):
        feats = self.backbone(x)
        return self.comp_head(feats), self.stock_head(feats)

class ProduceDataset(Dataset):
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
        comp_label = 1 if item["compliant"] else 0
        stock_label = self.stock_map.get(float(item["stock_value"]), 0)
        return img, comp_label, stock_label

train_tf = T.Compose([
    T.Resize((224, 224)),
    T.RandomHorizontalFlip(),
    T.ColorJitter(brightness=0.15, contrast=0.15),
    T.ToTensor(),
    T.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
])

val_tf = T.Compose([
    T.Resize((224, 224)),
    T.ToTensor(),
    T.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
])

def train_multitask(train_records, val_records, epochs=8, lr=1e-4):
    model = ShelfMultiTaskModel().to(device)
    train_loader = DataLoader(ProduceDataset(train_records, train_tf), batch_size=16, shuffle=True)
    val_loader = DataLoader(ProduceDataset(val_records, val_tf), batch_size=16, shuffle=False)

    crit_comp = nn.CrossEntropyLoss()
    crit_stock = nn.CrossEntropyLoss()
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-3)

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
            comp_preds = torch.argmax(c_logits, dim=1).cpu().numpy()
            pred_comps.extend([bool(cp) for cp in comp_preds])

            s_probs = torch.softmax(s_logits, dim=1).cpu().numpy()
            for prob in s_probs:
                p_0, p_05, p_1 = prob[0], prob[1], prob[2]
                s_0 = (p_0 * 1.0) - 2.0 * (p_05 + p_1)
                s_05 = (p_05 * 1.0) - 3.0 * p_0 - 2.0 * p_1
                s_1 = (p_1 * 1.0) - 3.0 * (p_0 + p_05)
                best_cls = max({0: s_0, 1: s_05, 2: s_1}, key=lambda k: {0: s_0, 1: s_05, 2: s_1}[k])
                pred_stocks.append(stock_inv[best_cls])

    return np.array(pred_comps), np.array(pred_stocks)