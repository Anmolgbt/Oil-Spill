"""
OILTRACE AI - CNN module
========================
Single source of truth for the SAR oil-spill CNN: the SAME model class and preprocessing are used
for training (notebook) and for deployment (backend), so they cannot drift apart.

What this model IS
    A binary image-patch classifier (oil-like dark patch vs. not) trained on 400x400 Sentinel-1 tiles.
What it is NOT
    * It is NOT a trained segmentation network. The "mask" produced here is a weakly-supervised
      Grad-CAM region refined by darkness - an APPROXIMATION for visualisation and rough geometry.
    * It cannot separate oil from specific look-alikes (biofilm, low-wind area ...): it only has two
      classes. Look-alike percentages must be supplied by another component and labelled accordingly.
    * Probabilities are only meaningful for imagery resembling the training data.
"""
from __future__ import annotations

import base64
import io
import json
import os
from typing import Dict, List, Optional, Sequence, Tuple, Union

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from PIL import Image, ImageFilter
from torchvision import transforms

__all__ = ["ConvBlock", "OilSpillCNN", "build_transforms", "OilSpillPredictor", "CLASS_NAMES", "DISCLAIMER"]

CLASS_NAMES = {0: "NO OIL SPILL", 1: "OIL SPILL"}
DISCLAIMER = ("Image-patch classifier trained on Sentinel-1 tiles. Dark SAR features are not automatically oil; "
              "mask and geometry are approximate (Grad-CAM derived), not a trained segmentation.")


# --------------------------------------------------------------------------
# Model
# --------------------------------------------------------------------------
class ConvBlock(nn.Module):
    def __init__(self, in_channels: int, out_channels: int):
        super().__init__()
        self.block = nn.Sequential(
            nn.Conv2d(in_channels, out_channels, 3, padding=1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
            nn.Conv2d(out_channels, out_channels, 3, padding=1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2),
        )

    def forward(self, x):
        return self.block(x)


class OilSpillCNN(nn.Module):
    """4 conv blocks (2x Conv-BN-ReLU each) + global average pooling + small MLP head."""

    def __init__(self, dropout: float = 0.30, num_classes: int = 2):
        super().__init__()
        self.features = nn.Sequential(
            ConvBlock(3, 32), ConvBlock(32, 64), ConvBlock(64, 128), ConvBlock(128, 256),
            nn.AdaptiveAvgPool2d((1, 1)),
        )
        self.classifier = nn.Sequential(
            nn.Flatten(), nn.Dropout(dropout), nn.Linear(256, 128), nn.ReLU(inplace=True),
            nn.Dropout(dropout), nn.Linear(128, num_classes),
        )

    def forward(self, x):
        return self.classifier(self.features(x))


def build_transforms(image_size: int = 224, mean: float = 0.5, std: float = 0.5, train: bool = False):
    """Grayscale SAR -> 3 identical channels -> [-1, 1]. `train=True` adds mild geometric augmentation."""
    aug = ([transforms.RandomHorizontalFlip(0.5), transforms.RandomVerticalFlip(0.5),
            transforms.RandomRotation(15)] if train else [])
    return transforms.Compose([
        transforms.Resize((image_size, image_size)), *aug,
        transforms.Grayscale(num_output_channels=3), transforms.ToTensor(),
        transforms.Normalize([mean] * 3, [std] * 3),
    ])


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
ImageLike = Union[str, bytes, np.ndarray, Image.Image]


def _to_gray_pil(img: ImageLike) -> Image.Image:
    if isinstance(img, Image.Image):
        return img.convert("L")
    if isinstance(img, (bytes, bytearray)):
        return Image.open(io.BytesIO(img)).convert("L")
    if isinstance(img, np.ndarray):
        a = img
        if a.ndim == 3:
            a = a[..., :3].astype(np.float64).mean(axis=2)
        if a.dtype != np.uint8:
            # float / 16-bit rasters (e.g. dB backscatter): NaN-safe 1-99 percentile stretch to 8 bit.
            # NOTE: the training JPEGs' exact stretch is unknown - verify on your own scenes.
            a = a.astype(np.float64)
            finite = np.isfinite(a)
            if not finite.any():
                a = np.zeros(a.shape, np.uint8)
            else:
                lo, hi = np.percentile(a[finite], [1, 99])
                a = np.nan_to_num(a, nan=lo, posinf=hi, neginf=lo)
                a = (np.clip((a - lo) / (hi - lo + 1e-9), 0, 1) * 255).astype(np.uint8)
        return Image.fromarray(a).convert("L")
    with Image.open(img) as im:
        return im.convert("L")


def _otsu(values: np.ndarray) -> float:
    hist, edges = np.histogram(values, bins=64)
    p = hist / max(hist.sum(), 1)
    centers = (edges[:-1] + edges[1:]) / 2
    w0, w1 = np.cumsum(p), 1 - np.cumsum(p)
    m0 = np.cumsum(p * centers) / np.maximum(w0, 1e-9)
    mt = (p * centers).sum()
    m1 = (mt - np.cumsum(p * centers)) / np.maximum(w1, 1e-9)
    return float(centers[np.argmax(w0 * w1 * (m0 - m1) ** 2)])


def _geometry(mask: np.ndarray, pixel_size_m: float) -> Dict:
    from scipy import ndimage as ndi
    n = int(mask.sum())
    px_km2 = (pixel_size_m / 1000.0) ** 2
    out = {"area_km2": round(n * px_km2, 4), "pixel_count": n, "coverage_fraction": round(n / mask.size, 4),
           "length_km": None, "width_km": None, "orientation_deg": None, "n_components": 0}
    if n < 50:
        return out
    lab, k = ndi.label(mask)
    out["n_components"] = int(k)
    sizes = ndi.sum(mask, lab, index=range(1, k + 1))
    big = lab == (int(np.argmax(sizes)) + 1)
    ys, xs = np.nonzero(big)
    pts = np.stack([xs, -ys], 1).astype(float)
    pts -= pts.mean(0)
    evals, evecs = np.linalg.eigh(np.cov(pts.T))
    major, minor = evecs[:, 1], evecs[:, 0]
    pm, pn = pts @ major, pts @ minor
    out["length_km"] = round(float((pm.max() - pm.min() + 1) * pixel_size_m / 1000), 3)
    out["width_km"] = round(float((pn.max() - pn.min() + 1) * pixel_size_m / 1000), 3)
    out["orientation_deg"] = round(float((np.degrees(np.arctan2(major[0], major[1])) + 360) % 180), 1)
    return out


# --------------------------------------------------------------------------
# Predictor
# --------------------------------------------------------------------------
class OilSpillPredictor:
    """
    Deployment wrapper. Loads weights + cnn_config.json produced by the training notebook.

        pred = OilSpillPredictor.load("OILTRACE_models")
        pred.predict("tile.jpg")                 # patch-level result (with test-time augmentation)
        pred.analyze(big_scene_array, pixel_size_m=10)   # tiles a large scene, mask + geometry
    """

    def __init__(self, model: nn.Module, config: Dict, device: Optional[str] = None):
        self.cfg = config
        self.device = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
        self.model = model.to(self.device).eval()
        self.size = int(config["image_size"])
        self.threshold = float(config["decision_threshold"])
        self.temperature = float(config.get("temperature", 1.0))
        self.tf = build_transforms(self.size, config["normalize_mean"], config["normalize_std"], train=False)
        self.tile = int(config.get("native_tile_px", 400))

    # ---- construction
    @classmethod
    def load(cls, model_dir: str, device: Optional[str] = None) -> "OilSpillPredictor":
        with open(os.path.join(model_dir, "cnn_config.json"), encoding="utf-8") as f:
            cfg = json.load(f)
        model = OilSpillCNN(dropout=cfg.get("dropout", 0.30))
        state = torch.load(os.path.join(model_dir, cfg.get("weights_file", "oilspill_cnn_best.pth")),
                           map_location="cpu")
        model.load_state_dict(state)
        return cls(model, cfg, device)

    # ---- core inference
    @torch.no_grad()
    def _logits(self, batch: torch.Tensor) -> torch.Tensor:
        return self.model(batch.to(self.device))

    def _prob_from_logits(self, logits: torch.Tensor) -> torch.Tensor:
        return torch.softmax(logits / self.temperature, dim=1)[:, 1]

    @torch.no_grad()
    def predict_tile(self, img: ImageLike, tta: bool = True) -> Dict:
        """Classify ONE tile. With tta=True the probability is averaged over 4 flips (std = uncertainty)."""
        pil = _to_gray_pil(img)
        flat = float(np.asarray(pil, dtype=np.float32).std()) < 2.0
        x = self.tf(pil).unsqueeze(0)
        views = [x] + ([x.flip(-1), x.flip(-2), x.flip(-1).flip(-2)] if tta else [])
        probs = torch.cat([self._prob_from_logits(self._logits(v)) for v in views]).cpu().numpy()
        p, sd = float(probs.mean()), float(probs.std())
        out = self._package(p, sd)
        out["warnings"] = ["Image is almost uniform (blank / no-data?) - result is unreliable"] if flat else []
        return out

    def _package(self, p: float, sd: float) -> Dict:
        label = int(p >= self.threshold)
        decisiveness = max(p, 1 - p)
        conf = ("High" if decisiveness >= 0.85 and sd <= 0.10 else
                "Medium" if decisiveness >= 0.65 and sd <= 0.20 else "Low")
        return {
            "oil_probability": round(p, 4), "prediction": CLASS_NAMES[label], "class": label,
            "confidence": conf, "tta_std": round(sd, 4), "decision_threshold": self.threshold,
            "lookalike_analysis": {
                "oil_like": round(p, 4), "not_oil_like": round(1 - p, 4), "breakdown_available": False,
                "note": "Binary model: cannot split the non-oil share into biofilm / low-wind / other. "
                        "Any such split shown in the UI must come from another component and be labelled demo.",
            },
        }

    def predict(self, img: ImageLike, tta: bool = True) -> Dict:
        """Alias of predict_tile for a single tile/patch."""
        return self.predict_tile(img, tta=tta)

    def predict_batch(self, images: Sequence[ImageLike], batch_size: int = 32) -> np.ndarray:
        """Oil probabilities (no TTA) for many tiles - used for evaluation/consistency checks."""
        out = []
        for i in range(0, len(images), batch_size):
            xb = torch.stack([self.tf(_to_gray_pil(im)) for im in images[i:i + batch_size]])
            out.append(self._prob_from_logits(self._logits(xb)).cpu().numpy())
        return np.concatenate(out) if out else np.array([])

    # ---- explainability
    def gradcam(self, img: ImageLike) -> np.ndarray:
        """Grad-CAM for the 'oil' class on one tile, resized to the tile, values in [0, 1]."""
        pil = _to_gray_pil(img)
        x = self.tf(pil).unsqueeze(0).to(self.device)
        store = {}
        h = self.model.features[3].register_forward_hook(lambda m, i, o: store.__setitem__("a", o))
        try:
            with torch.enable_grad():
                logits = self.model(x)
                grads = torch.autograd.grad(logits[0, 1], store["a"])[0]
        finally:
            h.remove()
        a = store["a"].detach()
        w = grads.mean(dim=(2, 3), keepdim=True)
        cam = F.relu((w * a).sum(1, keepdim=True))
        cam = F.interpolate(cam, size=(pil.height, pil.width), mode="bilinear", align_corners=False)[0, 0]
        cam = cam.cpu().numpy()
        return cam / cam.max() if cam.max() > 0 else cam

    def tile_mask(self, img: ImageLike, cam_threshold: float = 0.5, refine_dark: bool = True) -> Tuple[np.ndarray, np.ndarray]:
        """Approximate slick mask for ONE tile: Grad-CAM >= threshold, optionally restricted to dark pixels."""
        pil = _to_gray_pil(img)
        cam = self.gradcam(pil)
        mask = cam >= cam_threshold
        if refine_dark and mask.sum() > 100:
            g = np.asarray(pil.filter(ImageFilter.GaussianBlur(2)), dtype=float)
            t = _otsu(g[mask])                    # dark/bright split inside the CAM region
            mask = mask & (g <= t)
            from scipy import ndimage as ndi
            mask = ndi.binary_opening(mask, iterations=1)
            mask = ndi.binary_closing(mask, iterations=2)
        return mask, cam

    # ---- scene level
    def analyze(self, img: ImageLike, pixel_size_m: float = 10.0, stride: Optional[int] = None,
                max_tiles: int = 400) -> Dict:
        """
        Full analysis of a tile or a LARGE scene.
        Tiles the image (native tile size, 50 % overlap), classifies every tile, builds a probability
        map, and for tiles above threshold derives the approximate mask; then computes geometry.

        pixel_size_m is an ASSUMPTION unless you know the scene's ground sampling distance
        (Sentinel-1 GRD IW is ~10 m). Area/length/width scale with it.
        """
        pil = _to_gray_pil(img)
        W, H = pil.size
        T = self.tile
        stride = stride or T // 2
        mask = np.zeros((H, W), bool)
        prob_map = np.zeros((H, W), np.float32)
        count = np.zeros((H, W), np.float32)
        tile_results = []

        if W <= T * 1.25 and H <= T * 1.25:
            boxes = [(0, 0, W, H)]
        else:
            xs = list(range(0, max(W - T, 0) + 1, stride))
            ys = list(range(0, max(H - T, 0) + 1, stride))
            if xs[-1] + T < W:
                xs.append(W - T)
            if ys[-1] + T < H:
                ys.append(H - T)
            boxes = [(x, y, min(x + T, W), min(y + T, H)) for y in ys for x in xs]
            if len(boxes) > max_tiles:
                raise ValueError(f"{len(boxes)} tiles exceed max_tiles={max_tiles}; increase stride/max_tiles")

        for (x0, y0, x1, y1) in boxes:
            crop = pil.crop((x0, y0, x1, y1))
            r = self.predict_tile(crop, tta=True)
            tile_results.append({"box": [x0, y0, x1, y1], "oil_probability": r["oil_probability"],
                                 "tta_std": r["tta_std"], "warnings": r["warnings"]})
            prob_map[y0:y1, x0:x1] += r["oil_probability"]
            count[y0:y1, x0:x1] += 1
            if r["class"] == 1:
                m, _ = self.tile_mask(crop)
                mask[y0:y1, x0:x1] |= m
        prob_map /= np.maximum(count, 1)

        probs = np.array([t["oil_probability"] for t in tile_results])
        best = tile_results[int(probs.argmax())]
        scene = self._package(float(probs.max()), float(best["tta_std"]))
        scene["warnings"] = sorted({w for t in tile_results for w in t["warnings"]})
        scene["scene_decision_rule"] = ("scene P(oil) = highest tile probability; in very large scenes this rule "
                                        "raises the false-alarm rate - check n_positive_tiles")
        scene.update({
            "n_tiles": len(boxes), "n_positive_tiles": int((probs >= self.threshold).sum()),
            "best_tile": best, "image_size_px": [W, H],
            "geometry": _geometry(mask, pixel_size_m), "pixel_size_m": pixel_size_m,
            "geometry_assumption": "Approximate (Grad-CAM-derived mask). pixel_size_m must match the scene.",
            "disclaimer": DISCLAIMER,
        })
        return {"result": scene, "mask": mask, "prob_map": prob_map, "gray": np.asarray(pil)}

    # ---- rendering for the UI
    @staticmethod
    def render_overlay(gray: np.ndarray, mask: np.ndarray, alpha: float = 0.45) -> Image.Image:
        base = np.stack([gray] * 3, -1).astype(float)
        col = np.array([255, 110, 30], float)
        out = base.copy()
        out[mask] = (1 - alpha) * base[mask] + alpha * col
        return Image.fromarray(out.astype(np.uint8))

    @staticmethod
    def to_base64_png(img: Union[Image.Image, np.ndarray]) -> str:
        if isinstance(img, np.ndarray):
            img = Image.fromarray(img.astype(np.uint8) * (255 if img.dtype == bool else 1))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("ascii")
