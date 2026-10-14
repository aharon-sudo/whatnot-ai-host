"""Fixed, ordered product list for one stream.

Order here must match the order items are queued on the Whatnot dashboard
(v1 uses strict sequential index matching) — item 0 in this file
is whatever you queue first on Whatnot, item 1 is queued second, etc.
"""

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class InventoryItem:
    image_path: str
    name: str
    starting_price: str
    blurb: str
    obs_scene: str | None = None


def load_inventory(path: str) -> list[InventoryItem]:
    data = json.loads(Path(path).read_text())
    items = [InventoryItem(**entry) for entry in data]
    for item in items:
        if not Path(item.image_path).exists():
            raise FileNotFoundError(f"inventory image not found: {item.image_path}")
    return items
