"""Sanity check for the OBS layer, independent of Whatnot/voice.

Run: python scripts/test_obs.py path/to/some_image.jpg
Confirms the WebSocket connection works, the image source swaps, and the
configured audio source exists.
"""

import sys

from config.settings import load_settings
from obs_control.obs_client import ObsController


def main() -> None:
    if len(sys.argv) != 2:
        print("usage: python scripts/test_obs.py <image_path>")
        sys.exit(1)

    settings = load_settings()
    obs = ObsController(settings)

    obs.show_item(sys.argv[1])
    print(f"Swapped {settings.obs_image_source_name} to {sys.argv[1]}")

    if obs.audio_source_exists():
        print(f"Found audio source '{settings.obs_audio_source_name}' — good.")
    else:
        print(
            f"WARNING: no OBS source named '{settings.obs_audio_source_name}' found. "
            "Add an Audio Input Capture source pointed at your BlackHole device."
        )

    obs.close()


if __name__ == "__main__":
    main()
