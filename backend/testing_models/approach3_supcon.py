import torch
import torch.nn as nn
import numpy as np
from PIL import Image
from sklearn.linear_model import LogisticRegression
from sklearn.metrics.pairwise import cosine_similarity
import torchvision.transforms as T

device = torch.device("cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu"))
dinov2 = torch.hub.load("facebookresearch/dinov2", "dinov2_vits14").to(device).eval()

transform = T.Compose([
    T.Resize((224, 224)),
    T.ToTensor(),
    T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
])

class MetricProjector(nn.Module):
    def __init__(self, in_dim=384, proj_dim=128):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(in_dim, 256),
            nn.LayerNorm(256),
            nn.ReLU(),
            nn.Linear(256, proj_dim)
        )

    def forward(self, x):
        z = self.net(x)
        return nn.functional.normalize(z, p=2, dim=-1)

def extract_base_feats(records):
    feats = []
    with torch.no_grad():
        for r in records:
            img = Image.open(r["path"]).convert("RGB")
            t = transform(img).unsqueeze(0).to(device)
            f = dinov2(t).cpu().numpy().flatten()
            feats.append(f)
    return np.array(feats)

class Approach3MetricPipeline:
    def __init__(self):
        self.projector = MetricProjector().to(device)
        self.stock_clf = LogisticRegression(max_iter=1000, class_weight="balanced")

    def fit(self, X_train, records_train, epochs=25):
        # 1. Train stock model on raw embeddings
        y_stock = [str(r["stock_value"]) for r in records_train]
        self.stock_clf.fit(X_train, y_stock)

        # 2. Train metric projection layer with pairwise cosine loss
        optimizer = torch.optim.Adam(self.projector.parameters(), lr=1e-3)
        criterion = nn.CosineEmbeddingLoss(margin=0.3)
        X_t = torch.tensor(X_train, dtype=torch.float32).to(device)

        self.projector.train()
        for _ in range(epochs):
            idx1 = np.random.randint(0, len(records_train), size=64)
            idx2 = np.random.randint(0, len(records_train), size=64)

            labels = []
            for i1, i2 in zip(idx1, idx2):
                same_area = records_train[i1]["area_id"] == records_train[i2]["area_id"]
                both_comp = records_train[i1]["compliant"] and records_train[i2]["compliant"]
                labels.append(1.0 if (same_area and both_comp) else -1.0)

            z1 = self.projector(X_t[idx1])
            z2 = self.projector(X_t[idx2])
            target = torch.tensor(labels, dtype=torch.float32).to(device)

            loss = criterion(z1, z2, target)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

        # 3. Cache area prototypes
        self.projector.eval()
        with torch.no_grad():
            Z_train = self.projector(X_t).cpu().numpy()

        self.prototypes = {}
        for r, z in zip(records_train, Z_train):
            if r["compliant"]:
                aid = r["area_id"]
                if aid not in self.prototypes:
                    self.prototypes[aid] = []
                self.prototypes[aid].append(z)

        for aid in self.prototypes:
            self.prototypes[aid] = np.mean(self.prototypes[aid], axis=0, keepdims=True)

    def predict(self, X_val, records_val, threshold=0.70):
        # Stock predictions with risk weighting
        probs = self.stock_clf.predict_proba(X_val)
        classes = list(self.stock_clf.classes_)
        pred_stock = []
        for prob in probs:
            p_map = {classes[i]: prob[i] for i in range(len(classes))}
            p_0, p_05, p_1 = p_map.get("0.0", 0.0), p_map.get("0.5", 0.0), p_map.get("1.0", 0.0)
            s_0 = (p_0 * 1.0) - 2.0 * (p_05 + p_1)
            s_05 = (p_05 * 1.0) - 3.0 * p_0 - 2.0 * p_1
            s_1 = (p_1 * 1.0) - 3.0 * (p_0 + p_05)
            pred_stock.append(max({0.0: s_0, 0.5: s_05, 1.0: s_1}, key=lambda k: {0.0: s_0, 0.5: s_05, 1.0: s_1}[k]))

        # Metric compliance predictions
        self.projector.eval()
        with torch.no_grad():
            X_t = torch.tensor(X_val, dtype=torch.float32).to(device)
            Z_val = self.projector(X_t).cpu().numpy()

        pred_comp = []
        for r, z in zip(records_val, Z_val):
            aid = r["area_id"]
            if aid in self.prototypes:
                sim = cosine_similarity([z], self.prototypes[aid])[0][0]
                pred_comp.append(bool(sim >= threshold))
            else:
                pred_comp.append(True)

        return np.array(pred_comp), np.array(pred_stock)