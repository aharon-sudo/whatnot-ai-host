import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    xai_api_key: str
    obs_host: str
    obs_port: int
    obs_password: str
    obs_scene_name: str
    obs_image_source_name: str
    obs_audio_source_name: str
    whatnot_storage_state_path: str
    whatnot_dashboard_url: str
    alert_webhook_url: str
    inventory_path: str


def load_settings() -> Settings:
    return Settings(
        xai_api_key=os.environ["XAI_API_KEY"],
        obs_host=os.environ.get("OBS_HOST", "localhost"),
        obs_port=int(os.environ.get("OBS_PORT", "4455")),
        obs_password=os.environ.get("OBS_PASSWORD", ""),
        obs_scene_name=os.environ.get("OBS_SCENE_NAME", "Auction"),
        obs_image_source_name=os.environ.get("OBS_IMAGE_SOURCE_NAME", "ProductImage"),
        obs_audio_source_name=os.environ.get("OBS_AUDIO_SOURCE_NAME", "AIHostVoice"),
        whatnot_storage_state_path=os.environ.get(
            "WHATNOT_STORAGE_STATE_PATH", "./whatnot_storage_state.json"
        ),
        whatnot_dashboard_url=os.environ["WHATNOT_DASHBOARD_URL"],
        alert_webhook_url=os.environ.get("ALERT_WEBHOOK_URL", ""),
        inventory_path=os.environ.get("INVENTORY_PATH", "./inventory/example_inventory.json"),
    )
