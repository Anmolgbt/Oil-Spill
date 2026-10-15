"""
Re-export the AIS behaviour model under the scikit-learn version this backend pins.

Pickled estimators are only safe to load under the scikit-learn version that wrote
them, so the artifact that ships in backend/artifacts/ must be produced with the
version in requirements.txt. This runs exactly the AIS notebook's steps
(OILTRACE_AIS_Final.ipynb, sections 3-5) over the same reference corpus:

    clean_ais  ->  build_features  ->  AISAnomalyModel(300 trees, contamination 0.02).fit

Usage (from backend/, inside the project virtualenv):
    python scripts/train_ais_model.py
"""
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import pandas as pd  # noqa: E402

from core.config import AIS_REFERENCE_FILE, MODEL_ARTIFACTS_DIR  # noqa: E402
from ml import oiltrace_ais as A  # noqa: E402


def main():
    raw = pd.read_csv(AIS_REFERENCE_FILE)
    clean, report = A.clean_ais(raw)
    feat = A.build_features(clean)
    model = A.AISAnomalyModel(n_estimators=300, contamination=0.02, random_state=42).fit(feat)
    path = model.save(str(MODEL_ARTIFACTS_DIR))
    print("cleaning report:", report)
    print("saved:", path)
    print("meta:", model.meta)


if __name__ == "__main__":
    main()
