"""
Result figures for the paper, drawn from the frozen artifacts only.

Nothing here trains or re-fits anything. Inputs:
  handoff/cnn/cnn_test_metrics.json, cnn_training_history.csv, cnn_split_manifest.csv
  paper/data/cnn_test_predictions.csv        (scripts/replay_cnn_test_split.py)
  handoff/cnn/example_overlay_*.png           (Grad-CAM overlays from the CNN notebook)
  data/simulation/fleet.json + a live t3 scan (the constructed integration scenario)
Optional: the dataset folder, to replay the VALIDATION tiles and report
calibration error before and after temperature scaling.

    cd backend
    pip install -r ../paper/requirements-figures.txt
    python scripts/make_paper_figures.py ["<clone>/SAR Image Dataset"]

Writes paper/figures/*.pdf and paper/data/figure_numbers.json.
"""
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.metrics import (average_precision_score, precision_recall_curve,  # noqa: E402
                             roc_auc_score, roc_curve)

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

HANDOFF = ROOT / "handoff" / "cnn"
FIGURES = ROOT / "paper" / "figures"
NUMBERS = ROOT / "paper" / "data" / "figure_numbers.json"
PREDICTIONS = ROOT / "paper" / "data" / "cnn_test_predictions.csv"

# Validated categorical slots (light surface) + neutral ink for a print figure.
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, MUTED, GRID = "#0b0b0b", "#52514e", "#d9d8d4"
COLUMN_IN = 3.45  # IEEE two-column width

plt.rcParams.update({
    "font.family": "serif", "font.size": 7.5, "axes.titlesize": 8, "axes.labelsize": 7.5,
    "xtick.labelsize": 7, "ytick.labelsize": 7, "legend.fontsize": 6.8, "axes.edgecolor": MUTED,
    "axes.labelcolor": INK, "xtick.color": MUTED, "ytick.color": MUTED, "axes.grid": True,
    "grid.color": GRID, "grid.linewidth": 0.5, "axes.spines.top": False,
    "axes.spines.right": False, "lines.linewidth": 1.6, "savefig.bbox": "tight",
    "savefig.pad_inches": 0.02, "pdf.fonttype": 42,
})


def ece(y, p, bins=10):
    """Same definition as the CNN notebook: 10 equal-width bins, first bin closed."""
    edges = np.linspace(0, 1, bins + 1); total = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (p > lo) & (p <= hi) if lo > 0 else (p >= lo) & (p <= hi)
        if m.any():
            total += m.mean() * abs(y[m].mean() - p[m].mean())
    return float(total)


def reliability_points(y, p, bins=10, min_count=5):
    edges = np.linspace(0, 1, bins + 1); xs, ys, ns = [], [], []
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (p > lo) & (p <= hi) if lo > 0 else (p >= lo) & (p <= hi)
        if m.sum() >= min_count:
            xs.append(p[m].mean()); ys.append(y[m].mean()); ns.append(int(m.sum()))
    return np.array(xs), np.array(ys), ns


def save(fig, name):
    FIGURES.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURES / f"{name}.pdf"); plt.close(fig)
    print("  wrote", (FIGURES / f"{name}.pdf").relative_to(ROOT))


def confusion(metrics):
    cm = np.array([[metrics["tn"], metrics["fp"]], [metrics["fn"], metrics["tp"]]])
    fig, ax = plt.subplots(figsize=(1.9, 1.75))
    ax.imshow(cm, cmap="Blues", vmin=0, vmax=cm.max() * 1.15, interpolation="nearest"); ax.grid(False)
    for (i, j), v in np.ndenumerate(cm):
        ax.text(j, i, f"{v}", ha="center", va="center", fontsize=9,
                color="white" if v > cm.max() * 0.55 else INK)
    ax.set_xticks([0, 1], ["no oil", "oil"]); ax.set_yticks([0, 1], ["no oil", "oil"])
    ax.set_xlabel("Predicted"); ax.set_ylabel("Label")
    for s in ax.spines.values():
        s.set_visible(False)
    save(fig, "fig_confusion")


def roc_pr(preds):
    y, p = preds.label.to_numpy(), preds.oil_probability.to_numpy()
    fpr, tpr, _ = roc_curve(y, p); prec, rec, _ = precision_recall_curve(y, p)
    auc, ap = roc_auc_score(y, p), average_precision_score(y, p)
    fig, (a, b) = plt.subplots(1, 2, figsize=(COLUMN_IN, 1.65))
    a.plot([0, 1], [0, 1], ls=":", color=MUTED, lw=0.8)
    a.plot(fpr, tpr, color=BLUE); a.set_title(f"ROC (AUC {auc:.4f})")
    a.set_xlabel("False-positive rate"); a.set_ylabel("True-positive rate")
    b.plot(rec, prec, color=BLUE); b.set_title(f"Precision-recall (AP {ap:.4f})")
    b.set_xlabel("Recall"); b.set_ylabel("Precision"); b.set_ylim(0.5, 1.01)
    for ax in (a, b):
        ax.set_xlim(-0.01, 1.01)
    fig.tight_layout(w_pad=1.2)
    save(fig, "fig_roc_pr")
    return {"test_roc_auc_replayed": auc, "test_average_precision_replayed": ap}


def training(history):
    fig, (a, b) = plt.subplots(1, 2, figsize=(COLUMN_IN, 1.65))
    a.plot(history.epoch, history.train_loss, color=BLUE, label="train")
    a.plot(history.epoch, history.val_loss, color=ORANGE, label="validation")
    a.set_title("Cross-entropy loss"); a.set_xlabel("Epoch"); a.legend(frameon=False)
    b.plot(history.epoch, history.val_auc, color=BLUE, label="ROC-AUC")
    b.plot(history.epoch, history.val_f1, color=ORANGE, label="F1 @ 0.5")
    b.set_title("Validation"); b.set_xlabel("Epoch"); b.set_ylim(0.3, 1.0)
    b.legend(frameon=False, loc="lower right")
    fig.tight_layout(w_pad=1.2)
    save(fig, "fig_training")
    tail = history[history.epoch > history.epoch.max() - 8]
    return {"best_epoch_val_auc": float(history.val_auc.max()),
            "epoch_of_max_val_auc": int(history.loc[history.val_auc.idxmax(), "epoch"]),
            "last8_val_auc_min": float(tail.val_auc.min()),
            "last8_val_auc_max": float(tail.val_auc.max()),
            "lr_final": float(history.lr.iloc[-1])}


def validation_probabilities(data_dir):
    """Replay the validation tiles through the frozen checkpoint; raw and calibrated."""
    from PIL import Image

    from ml.cnn_inference import build_transform, config, load_model
    torch = __import__("torch")
    model, device, _ = load_model(); tf = build_transform()
    temperature = float(config()["temperature"])
    val = pd.read_csv(HANDOFF / "cnn_split_manifest.csv").query("split == 'val'")
    raw, cal = [], []
    with torch.no_grad():
        for start in range(0, len(val), 64):
            chunk = val.iloc[start:start + 64]
            x = torch.stack([tf(Image.open(data_dir / str(r.label) / r.file).convert("L"))
                             for r in chunk.itertuples()]).to(device)
            logits = model(x).float().cpu()
            raw.append(torch.softmax(logits, 1)[:, 1].numpy())
            cal.append(torch.softmax(logits / temperature, 1)[:, 1].numpy())
    return val.label.to_numpy(), np.concatenate(raw), np.concatenate(cal)


def reliability(preds, val):
    y_t, p_t = preds.label.to_numpy(), preds.oil_probability.to_numpy()
    out = {"test_ece_calibrated": ece(y_t, p_t)}
    fig, ax = plt.subplots(figsize=(1.9, 1.85))
    ax.plot([0, 1], [0, 1], ls=":", color=MUTED, lw=0.8)
    if val is not None:
        y_v, raw, cal = val
        out.update(val_ece_raw=ece(y_v, raw), val_ece_calibrated=ece(y_v, cal))
        xs, ys, _ = reliability_points(y_v, cal)
        ax.plot(xs, ys, "s-", color=ORANGE, ms=3.5, label="validation")
    xs, ys, _ = reliability_points(y_t, p_t)
    ax.plot(xs, ys, "o-", color=BLUE, ms=3.5, label="test")
    ax.set_xlabel("Calibrated P(oil)"); ax.set_ylabel("Observed oil fraction")
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.legend(frameon=False, loc="upper left")
    save(fig, "fig_reliability")
    return out


def gradcam():
    fig, axes = plt.subplots(1, 2, figsize=(COLUMN_IN, 1.75))
    for ax, name, title in zip(axes, ("clean", "oil"), ("Label: no oil", "Label: oil")):
        ax.imshow(plt.imread(HANDOFF / f"example_overlay_{name}.png")); ax.set_title(title)
        ax.axis("off")
    fig.tight_layout(w_pad=0.6)
    save(fig, "fig_gradcam")


def scenario():
    from services.fleet_pipeline import load_fleet, run_fleet_scan
    fleet = load_fleet(); scan = run_fleet_scan("t3")
    det = scan["spills"][0]; spill, source = det["spill"], det["source"]
    radius_km = det["affected_area"]["area_km2"] and (det["affected_area"]["area_km2"] / np.pi) ** 0.5
    top = {c["ship_id"]: c for c in det["candidates"][:3]}

    lat0 = spill["latitude"]; kx = 111.32 * np.cos(np.radians(lat0)); ky = 110.57
    to_km = lambda lat, lon: ((lon - spill["longitude"]) * kx, (lat - lat0) * ky)  # noqa: E731

    fig, ax = plt.subplots(figsize=(COLUMN_IN, 3.0))
    label_offset = {1: (4, 2), 2: (5, -7), 3: (-6, 6)}
    for ship in fleet["ships"]:
        xs, ys = to_km(np.array([p["lat"] for p in ship["track"]]),
                       np.array([p["lon"] for p in ship["track"]]))
        lead = ship["id"] in top
        ax.plot(xs, ys, color=BLUE if lead else GRID, lw=1.4 if lead else 1.0, zorder=3 if lead else 2)
        if lead:
            rank = top[ship["id"]]["rank"]
            ax.annotate(f"{ship['name']} (#{rank})", (xs[-1], ys[-1]), fontsize=6.3, color=INK,
                        xytext=label_offset[rank], textcoords="offset points",
                        ha="right" if label_offset[rank][0] < 0 else "left")
    ax.add_patch(plt.Circle((0, 0), radius_km, fill=False, ls="--", lw=1.0, ec=ORANGE, zorder=4))
    sx, sy = to_km(source["latitude"], source["longitude"])
    ax.plot([sx, 0], [sy, 0], color=MUTED, lw=0.8, zorder=4)
    ax.plot(0, 0, ls="none", marker="*", ms=9, color=ORANGE, mec="white", mew=0.6, zorder=5,
            label="Oil-positive tile (pass position)")
    ax.plot(sx, sy, ls="none", marker="D", ms=4.5, color=AQUA, mec="white", mew=0.6, zorder=5,
            label="Back-projected source (model estimate)")
    ax.plot([], [], ls="--", color=ORANGE, lw=1.0, label=f"4 h drift envelope, r = {radius_km:.2f} km")
    ax.plot([], [], color=BLUE, label="Top-3 ranked AIS tracks"); ax.plot([], [], color=GRID, label="Other fleet tracks")
    ax.set_aspect("equal"); ax.set_xlim(-22, 12); ax.set_ylim(-8, 14)
    ax.set_xlabel("East of detection (km)"); ax.set_ylabel("North of detection (km)")
    ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=2, fontsize=5.9,
              handlelength=1.8, columnspacing=1.0)
    save(fig, "fig_scenario")

    rows = []
    for g in det["evidence"]["candidates"][:5]:
        c = next(c for c in det["candidates"] if c["mmsi"] == g["mmsi"])
        cf = g["streams"]["counterfactual"]
        rows.append({"rank": c["rank"], "name": c["name"], "score": c["final_suspect_score"],
                     "miss_km": cf["miss_km"], "margin_km": cf["margin_km"],
                     "robustness": cf["robustness"], "grade": cf["grade"]})
    second = scan["spills"][1]["evidence"]["assessment"]
    return {"scenario_detection_1": {"ship": spill["ship_name"], "envelope_radius_km": radius_km,
                                     "assessment": det["evidence"]["assessment"]["outcome"],
                                     "reasons": det["evidence"]["assessment"]["reasons"][:2],
                                     "candidates": rows},
            "scenario_detection_2": {"assessment": second["outcome"],
                                     "consistent": second["consistent_count"],
                                     "candidates": second["candidate_count"]}}


def main():
    metrics = json.loads((HANDOFF / "cnn_test_metrics.json").read_text())
    preds = pd.read_csv(PREDICTIONS)
    history = pd.read_csv(HANDOFF / "cnn_training_history.csv")
    data_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else None

    numbers = {}
    confusion(metrics)
    numbers.update(roc_pr(preds))
    numbers.update(training(history))
    numbers.update(reliability(preds, validation_probabilities(data_dir) if data_dir else None))
    gradcam()
    numbers.update(scenario())
    NUMBERS.parent.mkdir(parents=True, exist_ok=True)
    NUMBERS.write_text(json.dumps(numbers, indent=2, default=str) + "\n")
    print(json.dumps(numbers, indent=2, default=str))


if __name__ == "__main__":
    main()
