"""Grok Voice Agent (xAI realtime speech-to-speech) session wrapper.

Protocol reference: https://docs.x.ai/developers/model-capabilities/audio/voice-agent
Connects once per stream, keeps a live conversation going, and exposes the
handful of operations the orchestrator actually needs:

  - inject_cue(text)   -> a state/timer event (new item, 30s left, sold, ...)
  - inject_chat(text)  -> a batched digest of new viewer chat messages
  - register_tool(...) -> lets the model pull get_current_state / get_recent_chat
                           on its own instead of only reacting to pushed cues
  - nudge()            -> heartbeat call so the host doesn't go dead-air silent

Cues and chat digests are both sent as role="user" text items, but the system
prompt (instructions) tells the model how to tell them apart via their
[CUE]/[CHAT] prefixes, since the API doesn't have a distinct "environment"
role. This keeps the model from mistaking a state update for something a
person said to it directly.
"""

import asyncio
import base64
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

import websockets

from voice_agent.audio_io import AudioPlayer

logger = logging.getLogger(__name__)

REALTIME_URL = "wss://api.x.ai/v1/realtime?model=grok-voice-latest"

ToolHandler = Callable[[dict], Awaitable[dict]]


@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: dict
    handler: ToolHandler


@dataclass
class _ReconnectState:
    attempt: int = 0
    max_backoff_s: float = 30.0


class GrokVoiceAgent:
    def __init__(
        self,
        api_key: str,
        instructions: str,
        voice: str = "eve",
        audio_output_device: str | None = None,
    ):
        self._api_key = api_key
        self._instructions = instructions
        self._voice = voice
        self._tools: dict[str, ToolDefinition] = {}
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._player = AudioPlayer(output_device_name=audio_output_device)
        self._closing = False

    def register_tool(self, tool: ToolDefinition) -> None:
        self._tools[tool.name] = tool

    async def run_forever(self) -> None:
        """Keeps the session alive across drops with exponential backoff.

        A dropped realtime websocket must not silently end the show — this
        reconnects and re-sends session config, but callers should watch
        `connected` and pause/alert via the orchestrator's failsafe if
        reconnection keeps failing rather than trusting it blindly forever.
        """
        state = _ReconnectState()
        self._player.start()
        try:
            while not self._closing:
                try:
                    await self._connect_and_serve()
                    state.attempt = 0
                except (websockets.ConnectionClosed, OSError) as exc:
                    state.attempt += 1
                    backoff = min(2**state.attempt, state.max_backoff_s)
                    logger.warning("voice session dropped (%s), reconnecting in %.1fs", exc, backoff)
                    await asyncio.sleep(backoff)
        finally:
            self._player.stop()

    async def _connect_and_serve(self) -> None:
        headers = {"Authorization": f"Bearer {self._api_key}"}
        async with websockets.connect(REALTIME_URL, additional_headers=headers) as ws:
            self._ws = ws
            await self._send_session_update()
            async for raw in ws:
                await self._handle_event(json.loads(raw))

    async def _send_session_update(self) -> None:
        await self._send(
            {
                "type": "session.update",
                "session": {
                    "voice": self._voice,
                    "instructions": self._instructions,
                    "turn_detection": {"type": "server_vad"},
                    "tools": [
                        {
                            "type": "function",
                            "name": t.name,
                            "description": t.description,
                            "parameters": t.parameters,
                        }
                        for t in self._tools.values()
                    ],
                    "audio": {
                        "output": {"format": {"type": "audio/pcm", "rate": 24000}},
                    },
                },
            }
        )

    async def inject_cue(self, text: str) -> None:
        await self._inject_text(f"[CUE] {text}")

    async def inject_chat(self, text: str) -> None:
        await self._inject_text(f"[CHAT] {text}")

    async def nudge(self) -> None:
        """Dead-air heartbeat: prompts the host to keep the show alive when
        nothing material has happened in a while."""
        await self._inject_text(
            "[CUE] No new activity for a bit. Keep the energy up, "
            "talk about the current item, or hype bidding."
        )

    async def _inject_text(self, text: str) -> None:
        await self._send(
            {
                "type": "conversation.item.create",
                "item": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": text}],
                },
            }
        )
        await self._send({"type": "response.create"})

    async def _handle_event(self, event: dict) -> None:
        etype = event.get("type")

        if etype == "response.output_audio.delta":
            audio_bytes = base64.b64decode(event["delta"])
            self._player.push_pcm16(audio_bytes)

        elif etype == "response.function_call_arguments.done":
            await self._dispatch_tool_call(event)

        elif etype == "error":
            logger.error("voice agent error event: %s", event)

    async def _dispatch_tool_call(self, event: dict) -> None:
        name = event["name"]
        call_id = event["call_id"]
        args = json.loads(event.get("arguments") or "{}")

        tool = self._tools.get(name)
        if tool is None:
            logger.warning("model called unknown tool %s", name)
            result: dict = {"error": f"unknown tool {name}"}
        else:
            try:
                result = await tool.handler(args)
            except Exception as exc:  # tool failures shouldn't kill the session
                logger.exception("tool %s failed", name)
                result = {"error": str(exc)}

        await self._send(
            {
                "type": "conversation.item.create",
                "item": {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": json.dumps(result),
                },
            }
        )
        await self._send({"type": "response.create"})

    async def _send(self, payload: dict) -> None:
        if self._ws is None:
            logger.warning("dropped outgoing event, no active connection: %s", payload.get("type"))
            return
        await self._ws.send(json.dumps(payload))

    async def close(self) -> None:
        self._closing = True
        if self._ws is not None:
            await self._ws.close()
