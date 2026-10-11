"""Image embeddings from frozen pretrained models ("engines"), CPU.

  clip    CLIP ViT-B/32 (open_clip, LAION-2B): image + text, so it can also match text prompts
  dinov2  DINOv2 ViT-S/14 (timm, same weights as torch.hub dinov2_vits14): image only

All embeddings are L2-normalised.
"""
from pathlib import Path

import cv2
import numpy as np
import torch
from PIL import Image

ENGINES = ("clip", "dinov2")


def pad_to_square(img_bgr: np.ndarray) -> np.ndarray:
    """Pad with black to a square, so wide baskets are neither cut off nor squashed."""
    h, w = img_bgr.shape[:2]
    s = max(h, w)
    top, left = (s - h) // 2, (s - w) // 2
    return cv2.copyMakeBorder(img_bgr, top, s - h - top, left, s - w - left, cv2.BORDER_CONSTANT, value=0)


def _to_pil(img_bgr: np.ndarray) -> Image.Image:
    return Image.fromarray(cv2.cvtColor(pad_to_square(img_bgr), cv2.COLOR_BGR2RGB))


class Clip:
    name = "clip"
    model_id = "ViT-B-32/laion2b_s34b_b79k"
    has_text = True

    def __init__(self, batch_size: int = 32):
        import open_clip

        arch, pretrained = self.model_id.split("/")
        self.model, _, self.preprocess = open_clip.create_model_and_transforms(arch, pretrained=pretrained)
        self.model.eval()
        self.tokenizer = open_clip.get_tokenizer(arch)
        self.batch_size = batch_size

    @torch.no_grad()
    def images(self, imgs_bgr: list[np.ndarray]) -> np.ndarray:
        out = []
        for i in range(0, len(imgs_bgr), self.batch_size):
            batch = torch.stack([self.preprocess(_to_pil(im)) for im in imgs_bgr[i:i + self.batch_size]])
            out.append(torch.nn.functional.normalize(self.model.encode_image(batch), dim=-1).numpy())
        return np.concatenate(out).astype(np.float32)

    @torch.no_grad()
    def texts(self, prompts: list[str]) -> np.ndarray:
        e = self.model.encode_text(self.tokenizer(prompts))
        return torch.nn.functional.normalize(e, dim=-1).numpy().astype(np.float32)

    def prompt_set(self, prompt_lists: list[list[str]]) -> np.ndarray:
        """One embedding per entry: the normalised mean of its prompts' embeddings."""
        e = self.texts([p for ps in prompt_lists for p in ps])
        out, i = [], 0
        for ps in prompt_lists:
            v = e[i:i + len(ps)].mean(axis=0)
            out.append(v / np.linalg.norm(v))
            i += len(ps)
        return np.stack(out)


class Dinov2:
    name = "dinov2"
    model_id = "vit_small_patch14_dinov2.lvd142m@224"
    has_text = False

    def __init__(self, batch_size: int = 32):
        import timm

        # 224 px input (the team's script uses 224 too; timm's default 518 is ~5x slower).
        self.model = timm.create_model("vit_small_patch14_dinov2.lvd142m", pretrained=True, num_classes=0, img_size=224)
        self.model.eval()
        cfg = timm.data.resolve_data_config({}, model=self.model)
        cfg["input_size"] = (3, 224, 224)
        cfg["crop_pct"] = 1.0
        self.preprocess = timm.data.create_transform(**cfg)
        self.batch_size = batch_size

    @torch.no_grad()
    def images(self, imgs_bgr: list[np.ndarray]) -> np.ndarray:
        out = []
        for i in range(0, len(imgs_bgr), self.batch_size):
            batch = torch.stack([self.preprocess(_to_pil(im)) for im in imgs_bgr[i:i + self.batch_size]])
            out.append(torch.nn.functional.normalize(self.model(batch), dim=-1).numpy())
        return np.concatenate(out).astype(np.float32)


def load_engine(name: str):
    return {"clip": Clip, "dinov2": Dinov2}[name]()


def load_cache(path: Path, model_id: str) -> dict[str, np.ndarray]:
    """{key: embedding} from an .npz cache, empty if missing or made with another model."""
    if not path.exists():
        return {}
    z = np.load(path, allow_pickle=False)
    if str(z["model_id"]) != model_id:
        return {}
    return dict(zip(z["keys"].tolist(), z["emb"]))


def save_cache(path: Path, cache: dict[str, np.ndarray], model_id: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    keys = sorted(cache)
    np.savez(path, model_id=model_id, keys=np.array(keys), emb=np.stack([cache[k] for k in keys]))
