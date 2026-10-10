"""DINOv2 image embeddings for area crops (shared by training and classification)."""
from pathlib import Path

import numpy as np
import torch
import torchvision.transforms as T
from PIL import Image

DINOV2_MODEL = "dinov2_vits14"

# DINOv2 expects 224x224 crops with ImageNet normalization
_transform = T.Compose([
    T.Resize((224, 224)),
    T.ToTensor(),
    T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
])


class FeatureExtractor:
    """Loads DINOv2 once (Metal GPU when available) and embeds crops."""

    def __init__(self, model_name: str = DINOV2_MODEL):
        self.device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
        print(f"Loading DINOv2 ({model_name}) on {self.device}...")
        self.model = torch.hub.load("facebookresearch/dinov2", model_name).to(self.device)
        self.model.eval()
        self.model_name = model_name

    def __call__(self, image_path: str | Path) -> np.ndarray:
        img = Image.open(image_path).convert("RGB")
        tensor = _transform(img).unsqueeze(0).to(self.device)
        with torch.no_grad():
            feature = self.model(tensor)
        return feature.cpu().numpy().flatten()
