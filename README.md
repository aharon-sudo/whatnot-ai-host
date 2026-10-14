# Whatnot AI Host

An experiment in running a fully autonomous, AI-hosted live auction on [Whatnot](https://www.whatnot.com).
OBS shows the product, an AI voice host talks to viewers and reacts to chat and the auction timer, and a
Playwright control layer drives the real Whatnot seller dashboard (start auctions, click Next, read chat),
because Whatnot has no public seller API.

## Why I built it

I sell on Whatnot and wanted to see how far I could automate a live show end to end. It also turned
into a good exercise in integrating several real-time systems safely: a WebSocket voice API, OBS's
WebSocket control protocol, and browser automation against a site with active bot detection.
I chose to drive the dashboard only the way a human would (clicks and typing) and not to bypass that
protection.

## Architecture

```
 inventory/*.json ──► orchestrator/main.py ──► obs_control   (OBS WebSocket v5: switch scene / swap image)
                           │          │
                           │          └──────► voice_agent   (xAI realtime voice over WebSocket ──► BlackHole ──► OBS audio)
                           │
                           └─────────────────► whatnot_control (Playwright: dashboard actions + chat scraping)
                                                      │
                                       on failed verification ──► orchestrator/alerts.py (webhook alert, show pauses)
```

- **orchestrator/** runs the show loop item by item and owns the failsafe. Each action is verified, and if
  verification fails the show pauses and an alert goes to `ALERT_WEBHOOK_URL`. It doesn't continue on stale state.
- **obs_control/** is a thin obs-websocket wrapper. It supports both setups: one scene per item (`obs_scene` in
  the inventory file, via `show_scene`) or one scene with a swappable image source (`show_item`).
- **voice_agent/** is the realtime voice client plus audio I/O through a virtual audio device.
- **whatnot_control/** is the Playwright driver. Every selector lives in one `SELECTORS` dict, so a Whatnot
  UI change is a one-place edit.
- **inventory/** holds the ordered product list. v1 matches items by position in the Whatnot queue.
- **scripts/** contains the one-time login, per-layer tests (`test_obs.py`, `test_voice.py`), and `autonomous_show.py` / `live_relay.py` runners.

## Tech stack

Python 3 (asyncio), Playwright, obsws-python (OBS WebSocket v5), websockets, httpx, sounddevice + numpy,
python-dotenv, OBS Studio, BlackHole 2ch (macOS virtual audio), xAI realtime voice API.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
cp .env.example .env   # fill in XAI_API_KEY, OBS_PASSWORD, WHATNOT_DASHBOARD_URL, ...
```

Then install a virtual audio device (on macOS, **BlackHole 2ch**) so the host's voice reaches OBS separately from your speakers.

In OBS:
1. Go to Tools → WebSocket Server Settings, enable the server, and put the port and password in `.env`.
2. Either create one scene per product and set `obs_scene` for each inventory item, or create a single
   scene (`OBS_SCENE_NAME`) with an Image source (`OBS_IMAGE_SOURCE_NAME`).
3. Add an Audio Input Capture source named `OBS_AUDIO_SOURCE_NAME` that points at BlackHole.

## Usage

```bash
python scripts/login_whatnot.py          # one-time: log in by hand (2FA ok), session is saved locally
python scripts/test_obs.py inventory/photos/chain_01_gold.png   # check OBS wiring
python scripts/test_voice.py             # check the voice agent alone
python -m orchestrator.main              # run the show
```

Inventory: copy `inventory/example_inventory.json`, list the items **in the same order you queue them on Whatnot**,
and point `INVENTORY_PATH` at the file.

## Status

- Done: OBS control, the voice agent, the orchestrator with verify-then-alert failsafe, and the inventory loader.
- Done: OBS is set up with two real scenes (Gold Chain / Silver Chain) plus a voice audio source. Wiring was checked with `test_obs.py`.
- Done: the orchestrator switches scenes per item when the inventory item has an `obs_scene`.
- In progress: the Next button, timer, current item and price selectors in `whatnot_control/driver.py` are still
  `TODO_RECON`. They only render while a show is live, so they need a supervised rehearsal. The chat composer and chat
  row structure are confirmed. Whatnot has no `data-testid` attributes, so locators are text/role-based.
- In progress: the voice layer has not been tested end to end with a valid API key yet.

## Roadmap

- Confirm the live-only dashboard selectors during a supervised rehearsal.
- Let `test_obs.py` test scene switching too (right now it only tests image swapping).
- Match images by title instead of strict queue order.
- Add an AI avatar or visual character (currently voice + product image only).
- Smarter self-recovery (v1 deliberately pauses and alerts).

## Disclaimer

This is a personal project and isn't affiliated with Whatnot. Use automation in line with Whatnot's terms of service.
