"""
Pseudonymise the committed fleet in place, without rebuilding it.

build_fleet.py now writes pseudonyms itself, but rebuilding re-draws tracks and
snapshots. This applies the same build_fleet.pseudonym() identities to the
existing data/simulation/fleet.json so every position, track, score and seeded
image assignment stays exactly as tested — only `name` and `mmsi` change.

    cd backend
    python scripts/anonymise_fleet.py
"""
import json
import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "scripts"))

from build_fleet import FLEET_FILE, pseudonym  # noqa: E402


def main():
    fleet = json.loads(FLEET_FILE.read_text())
    for ship in fleet["ships"]:
        index = int(re.fullmatch(r"ship(\d+)", ship["id"]).group(1))
        ship.update(pseudonym(index))
    # Same note the builder now writes, so a rebuild and this script agree.
    fleet["note"] = _builder_note()
    FLEET_FILE.write_text(json.dumps(fleet, indent=1))
    for ship in fleet["ships"]:
        print(f"  {ship['id']:7} {ship['name']:9} MMSI {ship['mmsi']}")


def _builder_note():
    source = (BACKEND / "scripts" / "build_fleet.py").read_text()
    block = re.search(r'"note": \((.*?)\),\n', source, re.S).group(1)
    return "".join(re.findall(r'"((?:[^"\\]|\\.)*)"', block))


if __name__ == "__main__":
    main()
