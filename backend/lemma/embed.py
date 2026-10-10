"""CLIP image/text embeddings (frozen pretrained model, CPU)."""
from pathlib import Path

import cv2
import numpy as np
import torch
from PIL import Image

MODEL_NAME = "ViT-B-32"
PRETRAINED = "laion2b_s34b_b79k"
MODEL_ID = f"{MODEL_NAME}/{PRETRAINED}"


def pad_to_square(img_bgr: np.ndarray) -> np.ndarray:
    """Pad with black to a square, so CLIP's centre-crop doesn't cut off the sides of wide baskets."""
    h, w = img_bgr.shape[:2]
    s = max(h, w)
    top, left = (s - h) // 2, (s - w) // 2
    return cv2.copyMakeBorder(img_bgr, top, s - h - top, left, s - w - left, cv2.BORDER_CONSTANT, value=0)


class Clip:
    def __init__(self, batch_size: int = 32):
        import open_clip

        self.model, _, self.preprocess = open_clip.create_model_and_transforms(MODEL_NAME, pretrained=PRETRAINED)
        self.model.eval()
        self.tokenizer = open_clip.get_tokenizer(MODEL_NAME)
        self.batch_size = batch_size

    @torch.no_grad()
    def images(self, imgs_bgr: list[np.ndarray]) -> np.ndarray:
        """(N, D) L2-normalised embeddings of BGR images (as read by cv2)."""
        out = []
        for i in range(0, len(imgs_bgr), self.batch_size):
            batch = [
                self.preprocess(Image.fromarray(cv2.cvtColor(pad_to_square(im), cv2.COLOR_BGR2RGB)))
                for im in imgs_bgr[i:i + self.batch_size]
            ]
            e = self.model.encode_image(torch.stack(batch))
            out.append(torch.nn.functional.normalize(e, dim=-1).numpy())
        return np.concatenate(out).astype(np.float32)

    @torch.no_grad()
    def texts(self, prompts: list[str]) -> np.ndarray:
        e = self.model.encode_text(self.tokenizer(prompts))
        return torch.nn.functional.normalize(e, dim=-1).numpy().astype(np.float32)

    def prompt_set(self, prompt_lists: list[list[str]]) -> np.ndarray:
        """One embedding per entry: the normalised mean of its prompts' embeddings."""
        flat = [p for ps in prompt_lists for p in ps]
        e = self.texts(flat)
        out, i = [], 0
        for ps in prompt_lists:
            v = e[i:i + len(ps)].mean(axis=0)
            out.append(v / np.linalg.norm(v))
            i += len(ps)
        return np.stack(out)


def load_cache(path: Path) -> dict[str, np.ndarray]:
    """{crop_path: embedding} from an embeddings.npz, empty if missing or made with another model."""
    if not path.exists():
        return {}
    z = np.load(path, allow_pickle=False)
    if str(z["model_id"]) != MODEL_ID:
        return {}
    return dict(zip(z["paths"].tolist(), z["emb"]))


def save_cache(path: Path, cache: dict[str, np.ndarray]) -> None:
    paths = sorted(cache)
    np.savez(path, model_id=MODEL_ID, paths=np.array(paths), emb=np.stack([cache[p] for p in paths]))
