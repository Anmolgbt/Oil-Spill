"""
t3 satellite-pass image simulation.

t1 and t2 are always all-clean. t3 is the only pass where a vessel's tile may
show oil, and which vessels get one is decided here, by a seeded random draw
over a small pool of real SAR tiles this project already has (the t1/t2 clean
tiles plus the two real oil tiles the original demo shipped, and the handoff
sample scenes).

The draw happens BEFORE any classification: this module only picks which real
image file lands at snapshots/t3/<ship_id>.jpg. It never runs the CNN and the
CNN (backend/ml/cnn_inference.py) never sees this module's ground truth — it
only ever receives image bytes. That separation is what keeps the simulation
and the model independent: the model's oil/no-oil call on a t3 tile is a real
prediction, checkable afterwards against `t3_ground_truth.json`, never an input
to it.

Same SIMULATION_SEED -> same vessels flagged oil-positive -> same demo replay.
"""
import json
import random
import shutil

from core.config import SIMULATION_DIR, SIMULATION_SEED, T3_OIL_MAX, T3_OIL_MIN

POOL_DIR = SIMULATION_DIR / "image_pool"
CLEAN_POOL_DIR = POOL_DIR / "clean"
OIL_POOL_DIR = POOL_DIR / "oil"

SNAPSHOTS_DIR = SIMULATION_DIR / "snapshots"
GROUND_TRUTH_FILE = SIMULATION_DIR / "t3_ground_truth.json"


def _pool(directory):
    return sorted(directory.glob("*.jpg")) if directory.is_dir() else []


def assign_t3_images(ship_ids, seed=SIMULATION_SEED, oil_min=T3_OIL_MIN, oil_max=T3_OIL_MAX):
    """
    Deterministic oil/clean source-tile assignment for one t3 pass.

    Returns one record per ship. `ground_truth_for_simulation` is
    internal/debug information for verifying the demo — it is not part of the
    image itself and must never be handed to the oil model as an input.
    """
    clean_pool = _pool(CLEAN_POOL_DIR)
    oil_pool = _pool(OIL_POOL_DIR)
    if not clean_pool or not oil_pool:
        raise FileNotFoundError(f"t3 image pool missing clean/oil tiles under {POOL_DIR}")

    ship_ids = list(ship_ids)
    rng = random.Random(seed)
    oil_count = rng.randint(oil_min, min(oil_max, len(ship_ids)))
    oil_ships = set(rng.sample(ship_ids, oil_count))

    assignments = []
    for ship_id in ship_ids:
        is_oil = ship_id in oil_ships
        pool = oil_pool if is_oil else clean_pool
        source = pool[rng.randrange(len(pool))]
        assignments.append({
            "snapshot_id": "t3",
            "ship_id": ship_id,
            "source_image": str(source),
            "ground_truth_for_simulation": "oil" if is_oil else "no_oil",
        })
    return assignments


def write_t3_snapshot(fleet_ships, seed=SIMULATION_SEED):
    """
    Populate data/simulation/snapshots/t3/ from the seeded assignment and record
    the ground truth to a side file. The oil model is never called from here.
    """
    ship_ids = [s["id"] for s in fleet_ships]
    assignments = assign_t3_images(ship_ids, seed=seed)
    by_ship = {a["ship_id"]: a for a in assignments}

    t3_dir = SNAPSHOTS_DIR / "t3"
    t3_dir.mkdir(parents=True, exist_ok=True)
    for ship in fleet_ships:
        assignment = by_ship[ship["id"]]
        shutil.copyfile(assignment["source_image"], t3_dir / ship["image_filename"])

    GROUND_TRUTH_FILE.write_text(json.dumps({
        "seed": seed,
        "snapshot_id": "t3",
        "note": ("Internal/debug only. Assigned BEFORE any model ran and never "
                 "passed to the CNN. Use only to verify the demo replays "
                 "identically for a given seed."),
        "oil_positive_ships": sorted(a["ship_id"] for a in assignments
                                     if a["ground_truth_for_simulation"] == "oil"),
        "assignments": assignments,
    }, indent=1))
    return assignments
