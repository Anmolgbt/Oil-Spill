"""
Near-duplicate leakage check for the CNN's scene-grouped split.

The split groups tiles by the scene id in each file name, and the notebook removes
byte-identical copies (md5). Neither catches the same sea patch saved under a
different scene id, or a rotated / flipped / re-encoded copy of it. If such pairs
straddle train and test, the held-out metrics are optimistic. This measures that
instead of assuming it away.

Method: a 64-bit DCT perceptual hash (pHash) of every manifest tile. Each
evaluation tile is hashed in all eight orientations (four rotations x mirror);
a pair counts as a near-duplicate when the smallest Hamming distance to any
training tile is <= THRESHOLD bits. The frozen model is then re-scored on the
test tiles with no training near-duplicate, using the per-tile probabilities
from scripts/replay_cnn_test_split.py. Nothing is retrained; the reported model
and its metrics are unchanged.

    cd backend
    python scripts/replay_cnn_test_split.py "<clone>/SAR Image Dataset"
    python scripts/check_near_duplicates.py "<clone>/SAR Image Dataset"

Writes handoff/cnn/near_duplicate_report.json.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image
from scipy.fft import dct
from sklearn.metrics import roc_auc_score

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
MANIFEST = ROOT / "handoff" / "cnn" / "cnn_split_manifest.csv"
METRICS = ROOT / "handoff" / "cnn" / "cnn_test_metrics.json"
PREDICTIONS = ROOT / "paper" / "data" / "cnn_test_predictions.csv"
REPORT = ROOT / "handoff" / "cnn" / "near_duplicate_report.json"

# 8 of 64 bits is the conventional "visually the same image" cut-off for pHash;
# 4 is reported alongside it as the strict reading.
THRESHOLD = 8
STRICT = 4


def phash(gray):
    """64-bit pHash: 32x32 resize, 2-D DCT, top-left 8x8 block against its median."""
    small = np.asarray(gray.resize((32, 32), Image.LANCZOS), dtype=np.float64)
    coeffs = dct(dct(small, axis=0, norm="ortho"), axis=1, norm="ortho")[:8, :8]
    bits = (coeffs > np.median(coeffs)).flatten()
    return np.packbits(bits).view(">u8")[0]


def orientations(gray):
    for k in range(4):
        rotated = gray.rotate(90 * k, expand=True)
        yield rotated
        yield rotated.transpose(Image.FLIP_LEFT_RIGHT)


def hamming(a, b):
    """Pairwise Hamming distance between two uint64 vectors."""
    x = np.bitwise_xor(a[:, None], b[None, :])
    return np.unpackbits(x.view(np.uint8).reshape(*x.shape, 8), axis=-1).sum(-1)


def min_distance(queries, reference):
    """Smallest distance from each query (8 orientations) to any reference hash."""
    best = np.full(len(queries), 64, dtype=np.int64)
    for start in range(0, len(queries), 64):
        block = queries[start:start + 64]                       # (n, 8)
        d = hamming(block.reshape(-1), reference).min(1)        # (n*8,)
        best[start:start + 64] = d.reshape(-1, 8).min(1)
    return best


def metrics(frame, threshold):
    y, p = frame.label.to_numpy(), frame.oil_probability.to_numpy()
    pred = (p >= threshold).astype(int)
    tp = int(((pred == 1) & (y == 1)).sum()); tn = int(((pred == 0) & (y == 0)).sum())
    fp = int(((pred == 1) & (y == 0)).sum()); fn = int(((pred == 0) & (y == 1)).sum())
    prec, rec = tp / max(tp + fp, 1), tp / max(tp + fn, 1)
    return {"n": len(frame), "accuracy": (tp + tn) / max(len(frame), 1), "precision": prec,
            "recall": rec, "f1": 2 * prec * rec / max(prec + rec, 1e-9),
            "roc_auc": float(roc_auc_score(y, p)), "tn": tn, "fp": fp, "fn": fn, "tp": tp}


def main():
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    data = Path(sys.argv[1])
    manifest = pd.read_csv(MANIFEST)

    hashes, oriented = [], []
    for row in manifest.itertuples():
        with Image.open(data / str(row.label) / row.file) as im:
            gray = im.convert("L")
            variants = [phash(v) for v in orientations(gray)]
        hashes.append(variants[0])
        oriented.append(variants)
    manifest["phash"] = np.array(hashes, dtype=np.uint64)
    oriented = np.array(oriented, dtype=np.uint64)

    train_idx = manifest.index[manifest.split == "train"].to_numpy()
    train_hashes = manifest.loc[train_idx, "phash"].to_numpy(dtype=np.uint64)
    report = {"method": f"64-bit DCT pHash, 8 orientations, near-duplicate if Hamming <= {THRESHOLD} "
                        f"(strict <= {STRICT})",
              "n_tiles": int(len(manifest)), "partitions": {}}

    for part in ("val", "test"):
        idx = manifest.index[manifest.split == part].to_numpy()
        dist = min_distance(oriented[idx], train_hashes)
        manifest.loc[idx, "min_dist_to_train"] = dist
        report["partitions"][part] = {
            "tiles": int(len(idx)),
            "near_duplicates_of_train": int((dist <= THRESHOLD).sum()),
            "near_duplicates_of_train_strict": int((dist <= STRICT).sum()),
            "exact_hash_matches": int((dist == 0).sum()),
            "scenes_affected": int(manifest.loc[idx[dist <= THRESHOLD], "scene"].nunique()),
        }

    ref = json.loads(METRICS.read_text())
    if PREDICTIONS.exists():
        preds = pd.read_csv(PREDICTIONS).merge(manifest[["file", "min_dist_to_train"]], on="file")
        full = metrics(preds, ref["threshold"])
        clean = metrics(preds[preds.min_dist_to_train > THRESHOLD], ref["threshold"])
        report["frozen_model_on_test"] = {
            "all_tiles": full,
            "without_train_near_duplicates": clean,
            "matches_reported_confusion_matrix": (full["tn"], full["fp"], full["fn"], full["tp"])
                                                 == (ref["tn"], ref["fp"], ref["fn"], ref["tp"]),
        }
    else:
        report["frozen_model_on_test"] = "run scripts/replay_cnn_test_split.py first"

    REPORT.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
