"""The real standalone show runner: alternates auctions between items,
switches the OBS scene to match, scrapes live chat, and feeds it all to the
Grok Voice relay (scripts/live_relay.py, must already be running on
localhost:8765) — all independent of any chat session driving it.

Built from live recon of the actual controls (no data-testid on the site,
so everything is text/role-based, per the driver.py recon notes):
  - "Shop" opens the seller product panel (Auction tab is default)
  - each item card has a "Product Actions" button -> menu -> "Start Auction"
  - the settings flyout that opens has its OWN "Start Auction" button to confirm
  - default auction length is 30s unless bids extend it

Run: python scripts/autonomous_show.py
Requires: scripts/login_whatnot.py already run once (saved session), and
scripts/live_relay.py already running.
"""

import asyncio
import urllib.request

from playwright.async_api import Page, async_playwright

from config.settings import load_settings
from inventory.loader import load_inventory
from obs_control.obs_client import ObsController

RELAY_URL = "http://127.0.0.1:8765"
LIVE_SHOW_URL = "https://www.whatnot.com/live/4fd1a0b4-4fa3-4ae4-a9c9-0988eb7f9fed"
ROUND_SECONDS = 30
CHAT_POLL_INTERVAL = 4


def relay_post(path: str, text: str) -> None:
    try:
        req = urllib.request.Request(
            f"{RELAY_URL}{path}", data=text.encode("utf-8"), method="POST"
        )
        urllib.request.urlopen(req, timeout=5).read()
    except Exception as exc:
        print(f"relay post failed ({path}): {exc}")


async def open_shop_panel(page: Page) -> None:
    await page.get_by_text("Shop", exact=True).first.click()
    await page.wait_for_timeout(600)


async def close_shop_panel(page: Page) -> None:
    # the panel's close control is an "x" icon button near the top-right
    close_buttons = page.locator("button svg").locator("..")
    try:
        await page.get_by_role("button", name="Close").click(timeout=1500)
    except Exception:
        pass  # non-fatal: next open_shop_panel click still works over it


async def start_auction_for(page: Page, item_title: str) -> bool:
    """Returns True if we believe the auction actually started."""
    await open_shop_panel(page)
    card = page.locator("div").filter(has_text=item_title).filter(
        has=page.get_by_role("button", name="Product Actions")
    ).last
    try:
        await card.get_by_role("button", name="Product Actions").click(timeout=3000)
        await page.get_by_role("button", name="Start Auction").click(timeout=3000)
        await page.wait_for_timeout(400)
        await page.get_by_role("button", name="Start Auction").click(timeout=3000)
        started = True
    except Exception as exc:
        print(f"start_auction_for({item_title!r}) failed: {exc}")
        started = False
    await close_shop_panel(page)
    return started


async def scrape_new_chat(page: Page, seen: set[str]) -> list[str]:
    rows = await page.locator("text=joined").all()  # cheap presence check, ignored below
    messages: list[str] = []
    # chat rows: containers with an author line + message text; grab all leaf text
    all_text_nodes = await page.locator("div.pb-2").all_inner_texts()
    for raw in all_text_nodes:
        if raw not in seen:
            seen.add(raw)
            messages.append(raw.replace("\n", ": "))
    return messages


async def run_round(page: Page, obs: ObsController, item, seen_chat: set[str]) -> None:
    print(f"--- starting round: {item.name} ({item.obs_scene}) ---")
    if item.obs_scene:
        obs.show_scene(item.obs_scene)
    ok = await start_auction_for(page, item.name)
    relay_post(
        "/cue",
        f"New item up: {item.name}, starting at {item.starting_price}. {item.blurb}"
        + ("" if ok else " (heads up, could not confirm the auction actually started)"),
    )

    elapsed = 0
    while elapsed < ROUND_SECONDS:
        await asyncio.sleep(CHAT_POLL_INTERVAL)
        elapsed += CHAT_POLL_INTERVAL
        try:
            new_msgs = await scrape_new_chat(page, seen_chat)
        except Exception as exc:
            print(f"chat scrape failed: {exc}")
            new_msgs = []
        if new_msgs:
            relay_post("/chat", "; ".join(new_msgs[-8:]))


async def main() -> None:
    settings = load_settings()
    inventory = load_inventory(settings.inventory_path)
    obs = ObsController(settings)
    seen_chat: set[str] = set()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(storage_state=settings.whatnot_storage_state_path)
        page = await context.new_page()
        await page.goto(LIVE_SHOW_URL)
        await page.wait_for_timeout(3000)
        print(f"Loaded live show: {LIVE_SHOW_URL}")

        round_num = 0
        while True:
            item = inventory[round_num % len(inventory)]
            await run_round(page, obs, item, seen_chat)
            round_num += 1


if __name__ == "__main__":
    asyncio.run(main())
