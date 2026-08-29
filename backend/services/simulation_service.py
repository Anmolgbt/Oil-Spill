"""
Satellite snapshot simulation.

Each snapshot folder (t0, t1, t2, ...) represents one satellite pass and holds
one image per monitored ship. Ship metadata lives in ships.json and stores only
a bare `image_filename`; the full path is constructed here per snapshot so a new
pass can be added by dropping a `t3/` folder into snapshots/ with no code change.

Filesystem paths stay as pathlib.Path objects internally. Anything handed to the
frontend is a browser URL under the /simulation-images mount declared in main.py.
"""
import json
import re

from core.config import SIMULATION_DIR

SNAPSHOTS_DIR = SIMULATION_DIR / "snapshots"
SHIPS_FILE = SIMULATION_DIR / "ships.json"

# Must match the mount point registered in main.py.
IMAGE_URL_PREFIX = "/simulation-images"

_SNAPSHOT_PATTERN = re.compile(r"^t(\d+)$")


def _snapshot_index(name):
    """Return the numeric index of a snapshot folder name, or None if it isn't one."""
    match = _SNAPSHOT_PATTERN.match(name)
    return int(match.group(1)) if match else None


def get_available_snapshots():
    """All snapshot ids present on disk, sorted numerically so t2 < t10."""
    if not SNAPSHOTS_DIR.is_dir():
        return []
    found = []
    for entry in SNAPSHOTS_DIR.iterdir():
        if not entry.is_dir():
            continue
        index = _snapshot_index(entry.name)
        if index is not None:
            found.append((index, entry.name))
    return [name for _, name in sorted(found)]


def get_latest_snapshot():
    """The highest-numbered snapshot, or None when none exist yet."""
    snapshots = get_available_snapshots()
    return snapshots[-1] if snapshots else None


def get_ships():
    """Raw ship metadata from ships.json."""
    with open(SHIPS_FILE, encoding="utf-8") as f:
        return json.load(f)["ships"]


def _image_url(snapshot_id, filename):
    """Browser URL for one ship image — forward slashes regardless of platform."""
    return f"{IMAGE_URL_PREFIX}/{snapshot_id}/{filename}"


def get_snapshot_data(snapshot_id):
    """
    Ship records for one satellite pass, each with its image resolved.

    A ship whose image is missing from this snapshot is still returned, with
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
            **ship,
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


def get_latest_snapshot_data():
    """Convenience wrapper: snapshot data for the most recent pass."""
    latest = get_latest_snapshot()
    return get_snapshot_data(latest) if latest else None
