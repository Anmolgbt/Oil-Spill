"""
Replay the training notebook's held-out test split through THIS backend's CNN code.

The notebook saved its split (handoff/cnn/cnn_split_manifest.csv) and its test
result (handoff/cnn/cnn_test_metrics.json). If the checkpoint, preprocessing,
temperature and threshold in backend/ml/ are the ones the notebook used, replaying
the test tiles must reproduce the notebook's confusion matrix exactly.

    cd backend
    python scripts/replay_cnn_test_split.py "<folder containing sub-folders 0 and 1>"

The tiles are not bundled (the public dataset is ~160 MB). Clone it once:
    git clone --depth 1 https://github.com/Saisamarth21/Oil-Spill-Detection-in-Marine-Environments-Using-AIS-and-Satellite-Data.git
and pass  "<clone>/SAR Image Dataset".  Takes about a minute on CPU.
"""
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import pandas as pd  # noqa: E402

from ml.cnn_inference import load_model, predict_image  # noqa: E402

HANDOFF = BACKEND.parent / "handoff" / "cnn"


def main():
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    data = Path(sys.argv[1])
    _, _, report = load_model()
    if not report["loaded_cleanly"]:
        raise SystemExit(f"checkpoint does not match the architecture: {report}")

    manifest = pd.read_csv(HANDOFF / "cnn_split_manifest.csv")
    test = manifest[manifest.split == "test"]
    tn = fp = fn = tp = 0
    for row in test.itertuples():
        got = predict_image(image_path=data / str(row.label) / row.file)["class_id"]
        if row.label == 1:
            tp, fn = tp + (got == 1), fn + (got == 0)
        else:
            tn, fp = tn + (got == 0), fp + (got == 1)

    ref = json.loads((HANDOFF / "cnn_test_metrics.json").read_text())
    mine, theirs = (tn, fp, fn, tp), (ref["tn"], ref["fp"], ref["fn"], ref["tp"])
    print(f"{len(test)} test tiles | replay TN/FP/FN/TP = {mine} | notebook = {theirs}")
    print("IDENTICAL" if mine == theirs else "MISMATCH")
    raise SystemExit(0 if mine == theirs else 1)


if __name__ == "__main__":
    main()
