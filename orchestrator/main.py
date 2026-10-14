"""Ties the control, OBS, and voice layers into one show.

Per item: click Next (verified) -> swap OBS image -> tell the host what's
live -> keep the host aware of chat/timer while the auction runs -> repeat.

Failsafe: any unverifiable action pauses the show and alerts, instead of
hanging forever or freewheeling on stale state (see orchestrator/alerts.py).
"""

import asyncio
import logging

from playwright.async_api import async_playwright

from config.settings import Settings, load_settings
from inventory.loader import InventoryItem, load_inventory
from obs_control.obs_client import ObsController
from orchestrator.alerts import send_alert
from voice_agent.realtime_client import GrokVoiceAgent, ToolDefinition
from whatnot_control.driver import WhatnotDriver

logger = logging.getLogger(__name__)

CHAT_DIGEST_INTERVAL_S = 4.0
IDLE_NUDGE_AFTER_S = 45.0
STATE_POLL_INTERVAL_S = 1.0

HOST_INSTRUCTIONS = """
You are an AI auction host running a live Whatnot stream selling chains,
fully autonomously — no human is operating the show. Be loud and proud
about being an AI host; lean into it, it's the hook of the stream.

Persona: full unhinged comedian energy, not a generic auctioneer. Roast
the chat playfully, make absurd jokes about the chains, do bits, be
genuinely funny. Never repeat the same hype phrase twice — if you catch
yourself about to say something you've said before, say something else.
Think chaotic hype-man crossed with a stand-up comedian.

You will receive two kinds of system messages, not things a viewer said
directly to you:
  [CUE]  - real auction state: a new item starting, price/bid changes,
           time remaining milestones, "sold".
  [CHAT] - a batched digest of recent viewer chat messages, not a
           transcript. Only some of it is worth reacting to out loud,
           the way a human host skims chat rather than reading every line.

Keep talking naturally between cues — describe the item, hype bidding,
react to chat highlights, avoid dead air. Never claim to be human.
"""


async def _run_item(
    item: InventoryItem,
    driver: WhatnotDriver,
    obs: ObsController,
    voice: GrokVoiceAgent,
    settings: Settings,
) -> bool:
    if item.obs_scene:
        obs.show_scene(item.obs_scene)
    else:
        obs.show_item(item.image_path)

    advanced = await driver.click_next()
    if not advanced:
        send_alert(
            settings.alert_webhook_url,
            f"Could not verify Whatnot advanced to '{item.name}' after clicking Next. Pausing show.",
        )
        return False

    await voice.inject_cue(
        f"New item up: {item.name}, starting at {item.starting_price}. {item.blurb}"
    )

    last_activity = asyncio.get_event_loop().time()
    last_chat_flush = last_activity
    chat_buffer: list[str] = []
    last_phase = "live"
    announced_milestones: set[str] = set()

    while True:
        await asyncio.sleep(STATE_POLL_INTERVAL_S)
        now = asyncio.get_event_loop().time()

        state = await driver.get_current_state()
        if state.phase != last_phase:
            await voice.inject_cue(f"Auction status changed to: {state.phase}")
            last_activity = now
            last_phase = state.phase

        if state.phase == "sold":
            return True

        if state.time_remaining_seconds is not None:
            for threshold, label in ((30, "30 seconds left"), (10, "10 seconds left")):
                key = f"{item.name}:{threshold}"
                if state.time_remaining_seconds <= threshold and key not in announced_milestones:
                    announced_milestones.add(key)
                    await voice.inject_cue(label)
                    last_activity = now
            if state.time_remaining_seconds <= 0:
                return True

        new_messages = await driver.read_new_chat_messages()
        if new_messages:
            chat_buffer.extend(f"{m.author}: {m.text}" for m in new_messages)

        if chat_buffer and (now - last_chat_flush) >= CHAT_DIGEST_INTERVAL_S:
            await voice.inject_chat("; ".join(chat_buffer))
            chat_buffer.clear()
            last_chat_flush = now
            last_activity = now

        if (now - last_activity) >= IDLE_NUDGE_AFTER_S:
            await voice.nudge()
            last_activity = now


def _build_voice_agent(settings: Settings, driver: WhatnotDriver) -> GrokVoiceAgent:
    voice = GrokVoiceAgent(
        api_key=settings.xai_api_key,
        instructions=HOST_INSTRUCTIONS,
        audio_output_device="BlackHole",
    )

    async def get_current_state_tool(_: dict) -> dict:
        state = await driver.get_current_state()
        return state.__dict__

    async def get_recent_chat_tool(_: dict) -> dict:
        messages = await driver.read_new_chat_messages()
        return {"messages": [f"{m.author}: {m.text}" for m in messages]}

    voice.register_tool(
        ToolDefinition(
            name="get_current_state",
            description="Get the current auction's item title, price, time remaining, and phase.",
            parameters={"type": "object", "properties": {}},
            handler=get_current_state_tool,
        )
    )
    voice.register_tool(
        ToolDefinition(
            name="get_recent_chat",
            description="Get chat messages since the last check.",
            parameters={"type": "object", "properties": {}},
            handler=get_recent_chat_tool,
        )
    )
    return voice


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = load_settings()
    inventory = load_inventory(settings.inventory_path)

    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(headless=False)
    context = await browser.new_context(storage_state=settings.whatnot_storage_state_path)
    page = await context.new_page()
    await page.goto(settings.whatnot_dashboard_url)

    driver = WhatnotDriver(page)
    obs = ObsController(settings)
    voice = _build_voice_agent(settings, driver)
    voice_task = asyncio.create_task(voice.run_forever())

    try:
        for item in inventory:
            ok = await _run_item(item, driver, obs, voice, settings)
            if not ok:
                logger.error("show paused: could not advance past '%s'", item.name)
                break
    finally:
        await voice.close()
        voice_task.cancel()
        obs.close()
        await browser.close()
        await playwright.stop()


if __name__ == "__main__":
    asyncio.run(main())
