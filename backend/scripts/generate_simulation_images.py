"""
Generate placeholder satellite snapshot images.

Writes one labelled image per ship into each existing snapshot folder under
backend/data/simulation/snapshots/. Existing files are left alone, so adding a
new t3/ folder and re-running only fills in what is missing.

Run from the backend/ directory:
    python scripts/generate_simulation_images.py
"""
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from services.simulation_service import get_available_snapshots, SNAPSHOTS_DIR, SHIPS_FILE

SIZE = (512, 512)


def _placeholder(text, seed):
    """A flat sea-coloured tile with the ship and snapshot labelled on it."""
    shade = 30 + (seed * 17) % 60
    image = Image.new("RGB", SIZE, (shade, shade + 20, shade + 45))
    draw = ImageDraw.Draw(image)
    draw.rectangle([8, 8, SIZE[0] - 8, SIZE[1] - 8], outline=(120, 160, 200), width=2)
    draw.text((24, 24), text, fill=(230, 240, 255))
    draw.text((24, 44), "PLACEHOLDER - SYNTHETIC", fill=(150, 180, 210))
    return image


def main():
    with open(SHIPS_FILE, encoding="utf-8") as f:
        ships = json.load(f)["ships"]

    snapshots = get_available_snapshots()
    if not snapshots:
        print(f"No snapshot folders found in {SNAPSHOTS_DIR}")
        return

    written = 0
    for snapshot_id in snapshots:
        folder = SNAPSHOTS_DIR / snapshot_id
        for index, ship in enumerate(ships):
            target = folder / ship["image_filename"]
            if target.exists():
                continue
            label = f"{snapshot_id.upper()}  {ship['id']}  {ship['name']}"
            _placeholder(label, index + len(snapshot_id)).save(target, quality=85)
            written += 1
        print(f"{snapshot_id}: {len(list(folder.glob('*.jpg')))} images")

    print(f"Wrote {written} new placeholder image(s).")


if __name__ == "__main__":
    main()
