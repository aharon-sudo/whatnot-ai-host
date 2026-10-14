"""Streams PCM16 audio from the voice agent out to a virtual audio device
(e.g. BlackHole 2ch on macOS) so OBS's audio-input-capture source picks it
up as the AI host's "microphone."

Uses a small jitter buffer: network/generation delivery of audio deltas is
bursty, not a smooth constant stream, so playing back the instant any byte
arrives means every gap between bursts becomes an audible silence-glitch
mid-word. Instead we "prime" — buffer silently until PRIME_MS of audio has
queued up — before letting the callback start consuming, then only re-prime
once the buffer fully drains (i.e. the utterance actually ended), rather
than glitching on every small gap.
"""

import threading

import sounddevice as sd

SAMPLE_RATE = 24000  # matches the audio/pcm format requested in session.update
CHANNELS = 1
BYTES_PER_MS = SAMPLE_RATE * 2 // 1000  # int16 mono
PRIME_MS = 250
PRIME_BYTES = BYTES_PER_MS * PRIME_MS


class AudioPlayer:
    def __init__(self, output_device_name: str | None = None):
        self._device_index = self._resolve_device(output_device_name)
        self._stream = sd.RawOutputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
            device=self._device_index,
            callback=self._callback,
        )
        self._lock = threading.Lock()
        self._buffer = bytearray()
        self._priming = True

    @staticmethod
    def _resolve_device(name: str | None) -> int | None:
        if not name:
            return None
        for idx, dev in enumerate(sd.query_devices()):
            if name.lower() in dev["name"].lower() and dev["max_output_channels"] > 0:
                return idx
        raise RuntimeError(
            f"Audio output device matching '{name}' not found. "
            f"Available: {[d['name'] for d in sd.query_devices()]}"
        )

    def _callback(self, outdata, frames, time, status):
        needed = frames * 2  # int16 mono -> 2 bytes/frame
        with self._lock:
            if self._priming and len(self._buffer) < PRIME_BYTES:
                outdata[:] = b"\x00" * needed
                return
            self._priming = False
            chunk = bytes(self._buffer[:needed])
            del self._buffer[: len(chunk)]
            if len(chunk) < needed:
                chunk += b"\x00" * (needed - len(chunk))
                self._priming = True  # buffer ran dry: re-prime before next utterance
        outdata[: len(chunk)] = chunk

    def start(self) -> None:
        self._stream.start()

    def stop(self) -> None:
        self._stream.stop()
        self._stream.close()

    def push_pcm16(self, data: bytes) -> None:
        with self._lock:
            self._buffer.extend(data)
