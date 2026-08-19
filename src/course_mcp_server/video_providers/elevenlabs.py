from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..security import read_secret
from .base import ProviderResult, VideoProviderError

DEFAULT_ELEVENLABS_BASE_URL = "https://api.elevenlabs.io"
# Publicly documented "multilingual" model id, chosen as the safe default for narration
# text that may not be English. Confirmed stable in ElevenLabs' public TTS docs as of this
# writing; callers may override via ELEVENLABS_MODEL_ID.
DEFAULT_ELEVENLABS_MODEL_ID = "eleven_multilingual_v2"
# ElevenLabs ships a small set of premade voice ids usable without any per-account setup.
# "Rachel" is the most commonly documented example voice id and is used here only as a
# fallback default -- callers should normally set ELEVENLABS_VOICE_ID (or pass voice_id in
# the brief) to a voice id that actually exists on their account.
DEFAULT_ELEVENLABS_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"


class ElevenLabsError(VideoProviderError):
    """Raised when the ElevenLabs narration provider call fails safely."""


@dataclass(frozen=True)
class ElevenLabsConfig:
    api_key: str | None = None
    voice_id: str = DEFAULT_ELEVENLABS_VOICE_ID
    model_id: str = DEFAULT_ELEVENLABS_MODEL_ID
    base_url: str = DEFAULT_ELEVENLABS_BASE_URL
    timeout_seconds: float = 60.0
    max_retries: int = 2
    retry_backoff_seconds: float = 0.5

    @classmethod
    def from_env(cls) -> "ElevenLabsConfig":
        return cls(
            api_key=read_secret("ELEVENLABS_API_KEY"),
            voice_id=os.getenv("ELEVENLABS_VOICE_ID", DEFAULT_ELEVENLABS_VOICE_ID),
            model_id=os.getenv("ELEVENLABS_MODEL_ID", DEFAULT_ELEVENLABS_MODEL_ID),
            base_url=os.getenv("ELEVENLABS_BASE_URL", DEFAULT_ELEVENLABS_BASE_URL),
            timeout_seconds=float(os.getenv("ELEVENLABS_TIMEOUT_SECONDS", "60")),
            max_retries=int(os.getenv("ELEVENLABS_MAX_RETRIES", "2")),
            retry_backoff_seconds=float(os.getenv("ELEVENLABS_RETRY_BACKOFF_SECONDS", "0.5")),
        )

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)


# Unlike OpenRouter's transport (which returns parsed JSON), ElevenLabs' text-to-speech
# endpoint returns raw audio bytes (audio/mpeg), so the transport signature here returns
# bytes rather than a dict.
Transport = Callable[[Request, float], bytes]


def _default_transport(request: Request, timeout: float) -> bytes:
    with urlopen(request, timeout=timeout) as response:  # nosec B310 - fixed HTTPS provider URL
        return response.read()


class ElevenLabsNarrationProvider:
    """VideoProvider implementation for ElevenLabs text-to-speech narration audio.

    ElevenLabs' TTS call completes in seconds, so submit() performs the real HTTP call
    synchronously and returns an already-"completed" ProviderResult; poll() and fetch() are
    thin formalities over that cached result rather than genuine async dispatch (see
    video_providers/base.py's module docstring and docs/authoring-platform-plan.md
    section 3.3.1).

    Assumed API shape (documented, stable core of ElevenLabs' public API -- flagged as an
    assumption because no live account/key is available to verify it end-to-end):
      POST {base_url}/v1/text-to-speech/{voice_id}
      Headers: xi-api-key: <api_key>, Content-Type: application/json, Accept: audio/mpeg
      Body: {"text": "...", "model_id": "..."}
      Response: raw audio bytes, Content-Type audio/mpeg
    """

    def __init__(
        self,
        config: ElevenLabsConfig | None = None,
        transport: Transport = _default_transport,
    ) -> None:
        self.config = config or ElevenLabsConfig.from_env()
        self._transport = transport
        self._results: dict[str, tuple[ProviderResult, bytes]] = {}

    def submit(self, brief: dict[str, Any]) -> ProviderResult:
        if not self.config.api_key:
            raise ElevenLabsError("ElevenLabs API key is not configured")

        text = str(brief.get("text", "")).strip()
        if not text:
            raise ElevenLabsError("ElevenLabs narration brief is missing text")
        voice_id = str(brief.get("voice_id") or self.config.voice_id)

        body = {
            "text": text,
            "model_id": str(brief.get("model_id") or self.config.model_id),
        }
        headers = {
            "xi-api-key": self.config.api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }
        request = Request(
            f"{self.config.base_url.rstrip('/')}/v1/text-to-speech/{voice_id}",
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        audio_bytes = self._send_with_retries(request)

        job_id = f"el_{uuid.uuid4().hex[:24]}"
        result = ProviderResult(
            job_id=job_id,
            status="completed",
            content_type="audio/mpeg",
            metadata={"voice_id": voice_id, "model_id": body["model_id"], "bytes": len(audio_bytes)},
        )
        self._results[job_id] = (result, audio_bytes)
        return result

    def poll(self, job_id: str) -> ProviderResult:
        cached = self._results.get(job_id)
        if cached is None:
            raise ElevenLabsError(f"Unknown ElevenLabs job id: {job_id}")
        return cached[0]

    def fetch(self, job_id: str) -> bytes:
        cached = self._results.get(job_id)
        if cached is None:
            raise ElevenLabsError(f"Unknown ElevenLabs job id: {job_id}")
        return cached[1]

    def _send_with_retries(self, request: Request) -> bytes:
        attempts = self.config.max_retries + 1
        for attempt in range(attempts):
            try:
                return self._transport(request, self.config.timeout_seconds)
            except HTTPError as exc:
                if exc.code < 500 or attempt == attempts - 1:
                    raise ElevenLabsError(f"ElevenLabs request failed with status {exc.code}") from exc
            except URLError as exc:
                if attempt == attempts - 1:
                    raise ElevenLabsError("ElevenLabs request failed") from exc
            if self.config.retry_backoff_seconds > 0:
                time.sleep(self.config.retry_backoff_seconds * (attempt + 1))
        raise ElevenLabsError("ElevenLabs request failed")
