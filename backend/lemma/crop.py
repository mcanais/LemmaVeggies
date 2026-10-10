"""Crop planogram areas (four-sided quads) out of camera images."""
import cv2
import numpy as np


def _edge(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.linalg.norm(a - b))


def warp_area(img: np.ndarray, quad: np.ndarray, out_size: tuple[int, int] | None = None) -> np.ndarray:
    """Perspective-rectify the quad (TL, TR, BR, BL) into an upright rectangle.

    Parts of the quad outside the image (negative coords) are filled with black.
    out_size is (width, height); by default it follows the quad's own edge lengths.
    """
    tl, tr, br, bl = quad
    if out_size is None:
        w = max(_edge(tl, tr), _edge(bl, br))
        h = max(_edge(tl, bl), _edge(tr, br))
        out_size = (max(1, round(w)), max(1, round(h)))
    w, h = out_size
    dst = np.array([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]], dtype=np.float32)
    m = cv2.getPerspectiveTransform(quad.astype(np.float32), dst)
    return cv2.warpPerspective(img, m, (w, h), flags=cv2.INTER_LINEAR,
                               borderMode=cv2.BORDER_CONSTANT, borderValue=0)


def bbox_area(img: np.ndarray, quad: np.ndarray, pad: int = 0, mask_outside: bool = True) -> np.ndarray:
    """Axis-aligned bounding box of the quad (clipped to the image), no geometric distortion.

    With mask_outside, pixels outside the quad (e.g. neighbouring baskets) are blacked out.
    """
    ih, iw = img.shape[:2]
    pts = np.round(quad).astype(np.int32)
    mask = np.zeros((ih, iw), dtype=np.uint8)
    cv2.fillPoly(mask, [pts], 255)
    x0, y0 = np.maximum(pts.min(axis=0) - pad, 0)
    x1, y1 = np.minimum(pts.max(axis=0) + pad + 1, [iw, ih])
    crop = img[y0:y1, x0:x1].copy()
    if mask_outside:
        crop[mask[y0:y1, x0:x1] == 0] = 0
    return crop


def draw_areas(img: np.ndarray, areas) -> np.ndarray:
    """Draw each area's polygon and area_id on a copy of the image."""
    out = img.copy()
    for a in areas:
        pts = np.round(a.quad).astype(np.int32)
        cv2.polylines(out, [pts], isClosed=True, color=(0, 255, 255), thickness=2)
        x, y = pts.mean(axis=0).astype(int)
        cv2.putText(out, a.area_id, (x - 30, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 3)
        cv2.putText(out, a.area_id, (x - 30, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
    return out


def inner_tiles(crop: np.ndarray, keep: float = 0.7, grid: int = 2) -> list[np.ndarray]:
    """Centre `keep` share of a crop (drops crate borders and price labels), cut into grid x grid tiles.

    Used for variety recognition, so the model looks at the fruit rather than the crate.
    """
    h, w = crop.shape[:2]
    mh, mw = int(h * (1 - keep) / 2), int(w * (1 - keep) / 2)
    inner = crop[mh:h - mh, mw:w - mw]
    ih, iw = inner.shape[:2]
    return [
        inner[r * ih // grid:(r + 1) * ih // grid, c * iw // grid:(c + 1) * iw // grid]
        for r in range(grid) for c in range(grid)
    ]
