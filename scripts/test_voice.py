"""Sanity check for the voice agent alone, independent of Whatnot/OBS.

Run: python scripts/test_voice.py
Opens a Grok Voice session, injects one cue, and plays the response through
your default audio output (or BlackHole if the constant below is set) so
you can hear it actually talk before wiring it to the real show.
"""

import asyncio

from config.settings import load_settings
from voice_agent.realtime_client import GrokVoiceAgent

TEST_INSTRUCTIONS = (
    "You are a test voice for an AI Whatnot auction host. Say a short, "
    "energetic hello introducing yourself as an AI auctioneer, then stop."
)


async def main() -> None:
    settings = load_settings()
    voice = GrokVoiceAgent(
        api_key=settings.xai_api_key,
        instructions=TEST_INSTRUCTIONS,
        audio_output_device=None,  # default output speakers for this smoke test
    )

    task = asyncio.create_task(voice.run_forever())
    await asyncio.sleep(1)  # let the session connect
    await voice.inject_cue("Say hello now.")
    await asyncio.sleep(15)  # let it speak

    await voice.close()
    task.cancel()


if __name__ == "__main__":
    asyncio.run(main())
