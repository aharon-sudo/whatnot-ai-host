"""Thin wrapper around obs-websocket v5 for the two things the bot needs:
swapping the product image source, and making sure the AI voice's virtual
audio device is wired in as an OBS audio source.

Requires OBS Studio running with Tools -> WebSocket Server Settings enabled,
and a scene (OBS_SCENE_NAME) containing an image source (OBS_IMAGE_SOURCE_NAME)
and an audio input capture source (OBS_AUDIO_SOURCE_NAME) pointed at the
virtual audio device (e.g. BlackHole 2ch) that the voice agent plays into.
"""

from pathlib import Path

import obsws_python as obs

from config.settings import Settings


class ObsController:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._client = obs.ReqClient(
            host=settings.obs_host,
            port=settings.obs_port,
            password=settings.obs_password,
        )

    def show_item(self, image_path: str) -> None:
        """Swap the product-image source to the given local file.

        Used when a single scene has one swappable image source. If your
        scene collection instead has one scene per item (as the two-scene
        Gold/Silver setup does today), use show_scene() per item instead.
        """
        resolved = str(Path(image_path).resolve())
        self._client.set_input_settings(
            self._settings.obs_image_source_name,
            {"file": resolved},
            overlay=True,
        )

    def show_scene(self, scene_name: str) -> None:
        """Switch OBS's current program scene to the given scene by name."""
        self._client.set_current_program_scene(scene_name)

    def audio_source_exists(self) -> bool:
        inputs = self._client.get_input_list().inputs
        return any(i["inputName"] == self._settings.obs_audio_source_name for i in inputs)

    def close(self) -> None:
        self._client.disconnect()
