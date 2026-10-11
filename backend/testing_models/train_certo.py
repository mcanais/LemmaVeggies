import os
import json
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
import torchvision.models as models
import torchvision.transforms as T
from PIL import Image
from pathlib import Path

# Setup Device
device = torch.device("cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu"))
print(f"Using device: {device}")

# ---------------------------------------------------------
# 1. Model Definition
# ---------------------------------------------------------


class ShelfMultiTaskModel(nn.Module):
    def __init__(self):
        super().__init__()
        # Load pre-trained ConvNeXt Tiny
        self.backbone = models.convnext_tiny(weights=models.ConvNeXt_Tiny_Weights.DEFAULT)
        in_feats = self.backbone.classifier[2].in_features
        self.backbone.classifier[2] = nn.Identity()

        # Head 1: Binary Planogram Compliance (Compliant / Non-Compliant)
        self.comp_head = nn.Sequential(
            nn.Linear(in_feats, 128),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(128, 2)
        )
        # Head 2: Stock Level (Empty=0, Half=1, Full=2)
        self.stock_head = nn.Sequential(
            nn.Linear(in_feats, 128),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(128, 3)
        )

    def forward(self, x):
        feats = self.backbone(x)
        return self.comp_head(feats), self.stock_head(feats)

# ---------------------------------------------------------
# 2. Dataset Definition
# ---------------------------------------------------------


class ProduceDataset(Dataset):
    def __init__(self, human_file, crops_dir, transform=None):
        self.transform = transform
        self.stock_map = {0.0: 0, 0.5: 1, 1.0: 2}
        self.records = []

        with open(human_file, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                item = json.loads(line)
                img_path = Path(crops_dir) / str(item["camera"]) / str(item["area_id"]) / str(item["image"])

                if img_path.exists():
                    self.records.append({
                        "path": str(img_path),
                        "compliant": 1 if item["planogram_compliant"] else 0,
                        "stock_label": self.stock_map.get(float(item["stock_value"]), 0)
                    })

    def __len__(self):
        return len(self.records)

    def __getitem__(self, idx):
        item = self.records[idx]
        img = Image.open(item["path"]).convert("RGB")
        if self.transform:
            img = self.transform(img)
        return img, item["compliant"], item["stock_label"]

# ---------------------------------------------------------
# 3. Training Loop
# ---------------------------------------------------------


def main():
    human_file = "../labels/human.jsonl" if not Path("labels/human.jsonl").exists() else "labels/human.jsonl"

    crops_dir = "crops" if Path("crops").exists() else "backend/crops"

    # Heavy augmentation for robustness
    train_tf = T.Compose([
        T.Resize((224, 224)),
        T.RandomHorizontalFlip(),
        T.RandomVerticalFlip(),
        T.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.2),
        T.ToTensor(),
        T.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
    ])

    dataset = ProduceDataset(human_file, crops_dir, transform=train_tf)
    dataloader = DataLoader(dataset, batch_size=32, shuffle=True, num_workers=2)
    print(f"Loaded {len(dataset)} labeled crops for full-dataset training.")

    model = ShelfMultiTaskModel().to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-4, weight_decay=1e-3)
    scheduler = torch.optim.lr_scheduler.StepLR(optimizer, step_size=5, gamma=0.5)

    crit_comp = nn.CrossEntropyLoss()
    crit_stock = nn.CrossEntropyLoss()

    epochs = 12
    model.train()

    for epoch in range(1, epochs + 1):
        total_loss, total_comp, total_stock = 0, 0, 0
        for imgs, comp_lbl, stock_lbl in dataloader:
            imgs, comp_lbl, stock_lbl = imgs.to(device), comp_lbl.to(device), stock_lbl.to(device)

            optimizer.zero_grad()
            c_logits, s_logits = model(imgs)

            # Weigh stock loss slightly higher due to its severe asymmetric penalties (-3 for overestimating)
            l_comp = crit_comp(c_logits, comp_lbl)
            l_stock = crit_stock(s_logits, stock_lbl)
            loss = l_comp + (1.5 * l_stock)

            loss.backward()
            optimizer.step()

            total_loss += loss.item()
            total_comp += l_comp.item()
            total_stock += l_stock.item()

        scheduler.step()
        print(f"Epoch {epoch}/{epochs} | Loss: {total_loss/len(dataloader):.3f} (Comp: {total_comp/len(dataloader):.3f}, Stock: {total_stock/len(dataloader):.3f})")

    # Save final model
    os.makedirs("models", exist_ok=True)
    save_path = "models/convnext_multitask.pt"
    torch.save(model.state_dict(), save_path)
    print(f"\nTraining complete. Model weights saved to {save_path}")


if __name__ == "__main__":
    main()
