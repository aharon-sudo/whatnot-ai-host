"""Keeps one persistent Grok Voice session alive during the real show, and
exposes a tiny local HTTP relay so cues/chat observed live (by watching the
actual Whatnot page) can be fed to it, without needing the not-yet-finished
whatnot_control selectors. This is the deliberate fallback for today's show:
a human (well, an AI) in the loop reading the real page and calling these
endpoints, instead of untested automation against a real live broadcast.

Run: python scripts/live_relay.py
Then: curl -s localhost:8765/cue  --data "New item: ..."
      curl -s localhost:8765/chat --data "alice: is this real gold?; bob: fire"
"""

import asyncio
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from config.settings import load_settings
from orchestrator.main import HOST_INSTRUCTIONS
from voice_agent.realtime_client import GrokVoiceAgent

loop: asyncio.AbstractEventLoop
voice: GrokVoiceAgent


class RelayHandler(BaseHTTPRequestHandler):
    def _handle(self, coro_fn):
        length = int(self.headers.get("Content-Length", 0))
        text = self.rfile.read(length).decode("utf-8")
        asyncio.run_coroutine_threadsafe(coro_fn(text), loop)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def do_POST(self):
        if self.path == "/cue":
            self._handle(voice.inject_cue)
        elif self.path == "/chat":
            self._handle(voice.inject_chat)
        elif self.path == "/nudge":
            asyncio.run_coroutine_threadsafe(voice.nudge(), loop)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # keep stdout clean


def run_event_loop():
    global loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.create_task(voice.run_forever())
    loop.run_forever()


def main():
    global voice
    settings = load_settings()
    voice = GrokVoiceAgent(
        api_key=settings.xai_api_key,
        instructions=HOST_INSTRUCTIONS,
        audio_output_device="BlackHole",
    )

    thread = threading.Thread(target=run_event_loop, daemon=True)
    thread.start()

    server = HTTPServer(("127.0.0.1", 8765), RelayHandler)
    print("Live relay up on http://127.0.0.1:8765 (POST /cue, /chat, /nudge)")
    server.serve_forever()


if __name__ == "__main__":
    main()
