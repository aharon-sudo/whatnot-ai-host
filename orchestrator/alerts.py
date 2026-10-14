"""V1 failsafe alerting: when the orchestrator can't verify an action worked,
it must not hang or silently keep going on stale state. It pauses and pages
a human via a webhook (Slack incoming webhook works out of the box; swap
the payload shape if you wire this to SMS/email instead).
"""

import logging

import httpx

logger = logging.getLogger(__name__)


def send_alert(webhook_url: str, message: str) -> None:
    if not webhook_url:
        logger.error("ALERT (no webhook configured): %s", message)
        return
    try:
        httpx.post(webhook_url, json={"text": f"🚨 Whatnot AI host: {message}"}, timeout=5.0)
    except Exception:
        logger.exception("failed to send alert, falling back to log: %s", message)
