"""
Satellite passes.

Each folder under data/simulation/snapshots/ (t0, t1, t2, ...) is one pass and
holds one SAR tile per monitored vessel, named after the vessel's `id`. Folders
are discovered and sorted numerically, so dropping in a `t3/` needs no code
change.

The vessel roster comes from fleet.json — this module owns only the passes and
where each tile lives.

Filesystem paths stay as pathlib.Path objects internally; anything handed to the
frontend is a browser URL under the /simulation-images mount declared in main.py.
"""
import json
import re

from core.config import SIMULATION_DIR

SNAPSHOTS_DIR = SIMULATION_DIR / "snapshots"
FLEET_FILE = SIMULATION_DIR / "fleet.json"

# Must match the mount point registered in main.py.
IMAGE_URL_PREFIX = "/simulation-images"

_SNAPSHOT_PATTERN = re.compile(r"^t(\d+)$")


def _snapshot_index(name):
    """The numeric index of a snapshot folder name, or None if it isn't one."""
    match = _SNAPSHOT_PATTERN.match(name)
    return int(match.group(1)) if match else None


def get_available_snapshots():
    """All passes present on disk, sorted numerically so t2 comes before t10."""
    if not SNAPSHOTS_DIR.is_dir():
        return []
    found = []
    for entry in SNAPSHOTS_DIR.iterdir():
        if entry.is_dir():
            index = _snapshot_index(entry.name)
            if index is not None:
                found.append((index, entry.name))
    return [name for _, name in sorted(found)]


def get_latest_snapshot():
    """The highest-numbered pass, or None when none exist yet."""
    snapshots = get_available_snapshots()
    return snapshots[-1] if snapshots else None


def get_ships():
    """The monitored vessel roster."""
    with open(FLEET_FILE, encoding="utf-8") as f:
        return json.load(f)["ships"]


def _image_url(snapshot_id, filename):
    """Browser URL for one tile — forward slashes regardless of platform."""
    return f"{IMAGE_URL_PREFIX}/{snapshot_id}/{filename}"


def get_snapshot_data(snapshot_id):
    """
    Per-vessel tile locations for one pass.

    A vessel whose tile is missing from this pass is still listed, with
    image_available False, so one absent file never breaks the whole pass.
    """
    if snapshot_id not in get_available_snapshots():
        return None

    snapshot_dir = SNAPSHOTS_DIR / snapshot_id
    ships = []
    for ship in get_ships():
        filename = ship["image_filename"]
        exists = (snapshot_dir / filename).is_file()
        ships.append({
            "id": ship["id"],
            "name": ship["name"],
            "snapshot_id": snapshot_id,
            "image_available": exists,
            "image_url": _image_url(snapshot_id, filename) if exists else None,
        })

    return {
        "snapshot_id": snapshot_id,
        "ship_count": len(ships),
        "images_available": sum(1 for s in ships if s["image_available"]),
        "ships": ships,
    }
