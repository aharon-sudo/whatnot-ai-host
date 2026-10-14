"""Playwright driver for the real Whatnot seller dashboard.

SELECTORS below are placeholders until Phase 0 recon confirms the actual
dashboard markup against the live site. Fill them in from DevTools inspection,
preferring data-testid / ARIA role / visible text over
generated CSS class names (those get rewritten on every Whatnot deploy).

Keeping every selector in one dict means a Whatnot UI change is a one-place
edit here, not a hunt through the rest of the codebase.

Uses Playwright's async API so it drops straight into the orchestrator's
asyncio event loop alongside the voice agent and OBS calls.

RECON NOTES (from inspecting the real pre-show seller console,
whatnot.com's live-show page for a scheduled show, without going live):
  - The site has NO data-testid attributes anywhere inspected — build
    locators with Playwright's text/role/placeholder matchers
    (get_by_role, get_by_placeholder, get_by_text), not CSS classes.
    Classes are Tailwind utility strings, not stable hooks, and the whole
    site runs a client-side bot-detection layer ("vice_loader"/sdiapi.com)
    that monkey-patches fetch/iframes — a strong signal not to fight it
    with clever JS, only drive it the way a real user would (clicks/typing).
  - Confirmed: the chat composer is `input[placeholder="Say something..."]`.
  - Confirmed: chat messages render as a stack of `div` rows (system events
    like "<user> joined" use a `<strong>` for the message body); a real
    viewer chat message's exact author/text markup should be re-checked
    live since only a join-event was visible pre-show.
  - NOT captured yet (only render once an auction is actually live):
    the Next button, the timer, current item title/price, sold indicator.
    These need a real rehearsal/show to inspect — deliberately not done by
    going live unattended.
"""

import asyncio
from dataclasses import dataclass
from time import monotonic

from playwright.async_api import Locator, Page

SELECTORS = {
    "next_button": "TODO_RECON",
    "current_item_title": "TODO_RECON",
    "current_price": "TODO_RECON",
    "timer": "TODO_RECON",
    "auction_phase_badge": "TODO_RECON",
    "chat_message_row": "TODO_RECON",  # one row per chat message
    "chat_message_author": "TODO_RECON",  # scoped within a row
    "chat_message_text": "TODO_RECON",  # scoped within a row
}


@dataclass
class AuctionState:
    item_title: str | None
    current_price: str | None
    time_remaining_seconds: int | None
    phase: str  # "queued" | "live" | "ending" | "sold" | "unknown"


@dataclass
class ChatMessage:
    id: str
    author: str
    text: str


class SelectorNotConfigured(RuntimeError):
    """Raised when a SELECTORS entry is still the TODO_RECON placeholder."""


class WhatnotDriver:
    def __init__(self, page: Page):
        self.page = page
        self._seen_chat_ids: set[str] = set()

    def _sel(self, key: str) -> str:
        value = SELECTORS[key]
        if value == "TODO_RECON":
            raise SelectorNotConfigured(
                f"SELECTORS['{key}'] not filled in yet — finish Phase 0 recon first"
            )
        return value

    async def get_current_state(self) -> AuctionState:
        title = await self._text_or_none(self._sel("current_item_title"))
        price = await self._text_or_none(self._sel("current_price"))
        timer_text = await self._text_or_none(self._sel("timer"))
        phase_text = await self._text_or_none(self._sel("auction_phase_badge"))

        return AuctionState(
            item_title=title,
            current_price=price,
            time_remaining_seconds=self._parse_timer(timer_text),
            phase=self._normalize_phase(phase_text),
        )

    async def click_next(self, verify_timeout_s: float = 8.0) -> bool:
        """Click Next and verify the dashboard actually advanced.

        Never assumes the click worked — returns False (does not raise) on
        failure so the orchestrator's failsafe can decide what to do, rather
        than the driver silently retrying forever or crashing the show.
        """
        before = await self.get_current_state()
        await self.page.locator(self._sel("next_button")).click()

        deadline = monotonic() + verify_timeout_s
        while monotonic() < deadline:
            after = await self.get_current_state()
            if after.item_title != before.item_title or after.phase != before.phase:
                return True
            await asyncio.sleep(0.25)
        return False

    async def read_new_chat_messages(self) -> list[ChatMessage]:
        rows = await self.page.locator(self._sel("chat_message_row")).all()
        new_messages: list[ChatMessage] = []
        for row in rows:
            msg_id = await self._row_id(row)
            if msg_id in self._seen_chat_ids:
                continue
            author = (await row.locator(self._sel("chat_message_author")).inner_text()).strip()
            text = (await row.locator(self._sel("chat_message_text")).inner_text()).strip()
            self._seen_chat_ids.add(msg_id)
            new_messages.append(ChatMessage(id=msg_id, author=author, text=text))
        return new_messages

    async def _text_or_none(self, selector: str) -> str | None:
        locator = self.page.locator(selector)
        if await locator.count() == 0:
            return None
        try:
            return (await locator.first.inner_text()).strip()
        except Exception:
            return None

    @staticmethod
    async def _row_id(row: Locator) -> str:
        # Fallback identity when Whatnot doesn't expose a stable message id:
        # author+text is good enough to dedupe consecutive polls, since exact
        # duplicate messages from the same user are rare in a chat feed.
        try:
            return (await row.inner_text()).strip()
        except Exception:
            return str(id(row))

    @staticmethod
    def _parse_timer(timer_text: str | None) -> int | None:
        if not timer_text:
            return None
        parts = timer_text.strip().split(":")
        try:
            if len(parts) == 2:
                minutes, seconds = parts
                return int(minutes) * 60 + int(seconds)
            if len(parts) == 1:
                return int(parts[0])
        except ValueError:
            return None
        return None

    @staticmethod
    def _normalize_phase(phase_text: str | None) -> str:
        if not phase_text:
            return "unknown"
        lowered = phase_text.lower()
        for phase in ("sold", "ending", "live", "queued"):
            if phase in lowered:
                return phase
        return "unknown"
