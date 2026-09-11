"""
Pass ingestion — drop images in, get a new satellite pass out.

The demo ships three passes on disk. This lets a presenter add a fourth (then a
fifth, ...) live, by handing the system a folder of SAR tiles the way a real
downlink would: the images arrive, the pass is created, and the pipeline runs
over it without anyone configuring anything.

What this module does NOT do is decide what is in the images. It writes files
and names a pass. The CNN sees the bytes and nothing else — there is no ground
truth for an uploaded pass, and none is invented. Whatever the model says about
these tiles is a real prediction with nothing to check it against, and the API
says so in `ground_truth_available: false`.

Tiles are matched to vessels by position: the first image goes to the first
vessel in the roster, and so on. That is an arbitrary assignment and it is
reported back, because a viewer needs to know the pairing was chosen here rather
than observed.
"""
import re
import shutil

from PIL import Image

from core.config import SIMULATION_DIR
from .snapshots import get_available_snapshots, get_ships

SNAPSHOTS_DIR = SIMULATION_DIR / "snapshots"

# What the CNN can actually open. Anything else is rejected rather than written
# and left to fail later at inference time.
ALLOWED_SUFFIXES = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp"}
MAX_BYTES = 20 * 1024 * 1024


def next_snapshot_id():
    """The pass id after the highest one on disk."""
    existing = get_available_snapshots()
    highest = -1
    for name in existing:
        match = re.match(r"^t(\d+)$", name)
        if match:
            highest = max(highest, int(match.group(1)))
    return f"t{highest + 1}"


def _is_readable_image(data):
    """Whether PIL can actually decode this, checked before anything is written."""
    from io import BytesIO
    try:
        Image.open(BytesIO(data)).verify()
        return True
    except Exception:
        return False


def create_pass(files, snapshot_id=None):
    """
    Write an uploaded set of tiles as a new pass.

    `files` is a list of (filename, bytes). Returns a summary of what was
    created, including which image was paired with which vessel.

    Fewer images than vessels is allowed: the unmatched vessels simply have no
    tile for this pass, which `snapshots.get_snapshot_data()` already reports as
    `image_available: false` rather than treating as an error. Extra images past
    the roster are ignored and reported.
    """
    ships = get_ships()
    if not ships:
        raise ValueError("No vessel roster — fleet.json is missing or empty.")

    usable = []
    rejected = []
    for name, data in files:
        suffix = ("." + name.rsplit(".", 1)[-1].lower()) if "." in name else ""
        if suffix not in ALLOWED_SUFFIXES:
            rejected.append({"filename": name, "reason": "unsupported type"})
        elif len(data) > MAX_BYTES:
            rejected.append({"filename": name, "reason": "larger than 20 MB"})
        elif not _is_readable_image(data):
            rejected.append({"filename": name, "reason": "not a readable image"})
        else:
            usable.append((name, data))

    if not usable:
        raise ValueError("No usable images in the upload.")

    # Stable order, so the same drop produces the same pairing twice running.
    usable.sort(key=lambda pair: pair[0].lower())

    snapshot_id = snapshot_id or next_snapshot_id()
    target = SNAPSHOTS_DIR / snapshot_id
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)

    assignments = []
    for ship, (name, data) in zip(ships, usable):
        # The vessel's tile filename is fixed by the roster; the upload's own
        # name is kept only so the pairing can be reported.
        (target / ship["image_filename"]).write_bytes(data)
        assignments.append({
            "ship_id": ship["id"],
            "ship_name": ship["name"],
            "source_filename": name,
        })

    unmatched_ships = [s["name"] for s in ships[len(usable):]]
    ignored = [name for name, _ in usable[len(ships):]]

    return {
        "snapshot_id": snapshot_id,
        "images_written": len(assignments),
        "assignments": assignments,
        "vessels_without_tile": unmatched_ships,
        "images_ignored": ignored,
        "rejected": rejected,
        "ground_truth_available": False,
        "pairing": ("Images are paired with vessels in filename order — an arbitrary "
                    "assignment made at upload, not an observation."),
        "note": ("No ground truth exists for an uploaded pass. The classifier's call on "
                 "these tiles is a real prediction with nothing to check it against."),
    }


def delete_pass(snapshot_id):
    """Remove an uploaded pass. Refuses to touch the three that ship with the repo."""
    if snapshot_id in {"t1", "t2", "t3"}:
        raise ValueError(f"{snapshot_id} ships with the repo and cannot be deleted.")
    target = SNAPSHOTS_DIR / snapshot_id
    if not re.match(r"^t\d+$", snapshot_id or "") or not target.is_dir():
        raise FileNotFoundError(f"No such pass: {snapshot_id}")
    shutil.rmtree(target)
    return {"deleted": snapshot_id}
