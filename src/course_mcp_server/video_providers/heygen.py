from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..security import read_secret
from .base import ProviderResult, VideoProviderError

DEFAULT_HEYGEN_BASE_URL = "https://api.heygen.com"
# UNVERIFIED ASSUMPTION (no live HeyGen account/key available to confirm end-to-end, mirroring
# the caveat elevenlabs.py flags for its own API shape): HeyGen's public API is documented as
# having a v2 "generate" endpoint for kicking off an avatar video and a v1 "status" endpoint for
# polling it -- the two live under different version prefixes on their own API, which is
# unusual but is what their public docs describe as of this writing. If this has changed,
# update DEFAULT_HEYGEN_*_PATH below; the rest of the adapter does not depend on the exact path.
DEFAULT_HEYGEN_GENERATE_PATH = "/v2/video/generate"
DEFAULT_HEYGEN_STATUS_PATH = "/v1/video_status.get"


class HeyGenError(VideoProviderError):
    """Raised when the HeyGen presenter-video provider call fails safely."""


@dataclass(frozen=True)
class HeyGenConfig:
    api_key: str | None = None
    avatar_id: str | None = None
    voice_id: str | None = None
    base_url: str = DEFAULT_HEYGEN_BASE_URL
    timeout_seconds: float = 60.0
    max_retries: int = 2
    retry_backoff_seconds: float = 0.5

    @classmethod
    def from_env(cls) -> "HeyGenConfig":
        return cls(
            api_key=read_secret("HEYGEN_API_KEY"),
            avatar_id=os.getenv("HEYGEN_AVATAR_ID"),
            voice_id=os.getenv("HEYGEN_VOICE_ID"),
            base_url=os.getenv("HEYGEN_BASE_URL", DEFAULT_HEYGEN_BASE_URL),
            timeout_seconds=float(os.getenv("HEYGEN_TIMEOUT_SECONDS", "60")),
            max_retries=int(os.getenv("HEYGEN_MAX_RETRIES", "2")),
            retry_backoff_seconds=float(os.getenv("HEYGEN_RETRY_BACKOFF_SECONDS", "0.5")),
        )

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)


# HeyGen's generate/status endpoints return JSON (unlike ElevenLabs' TTS endpoint, which
# returns raw audio bytes directly) -- so this adapter needs two transport shapes: one for the
# JSON submit/poll calls, and a separate one for downloading the finished MP4 from its result
# URL once poll() reports "completed".
JsonTransport = Callable[[Request, float], dict[str, Any]]
BytesTransport = Callable[[Request, float], bytes]


def _default_json_transport(request: Request, timeout: float) -> dict[str, Any]:
    with urlopen(request, timeout=timeout) as response:  # nosec B310 - fixed HTTPS provider URL
        return json.loads(response.read().decode("utf-8"))


def _default_bytes_transport(request: Request, timeout: float) -> bytes:
    with urlopen(request, timeout=timeout) as response:  # nosec B310 - fixed HTTPS provider URL
        return response.read()


@dataclass
class _JobState:
    status: str  # "processing" | "completed" | "failed"
    video_url: str | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class HeyGenPresenterProvider:
    """VideoProvider implementation for HeyGen avatar/presenter video generation.

    Unlike ElevenLabsNarrationProvider (whose single HTTP call returns finished audio bytes
    synchronously), HeyGen video generation genuinely takes minutes. This adapter makes three
    separate real HTTP calls across the VideoProvider lifecycle:
      submit() -> POST to start generation, returns immediately with status="processing".
      poll()   -> GET the job's status; returns "processing" until HeyGen reports the job
                  done, then "completed" (with the result video URL in metadata) or "failed".
      fetch()  -> GET the result video URL captured by poll() and return the raw MP4 bytes.
                  Only valid once poll() has reported "completed" -- calling it earlier raises
                  HeyGenError rather than blocking or returning garbage.

    Assumed API shape (UNVERIFIED -- no live HeyGen account/key was available to confirm this
    end-to-end; flagged here and in the final report exactly as elevenlabs.py flags its own
    assumed shape):
      POST {base_url}/v2/video/generate
        Headers: X-Api-Key: <api_key>, Content-Type: application/json
        Body: {"video_inputs": [{"character": {"type": "avatar", "avatar_id": "..."},
                                  "voice": {"type": "text", "input_text": "...", "voice_id": "..."}}]}
        Response: {"data": {"video_id": "..."}}
      GET {base_url}/v1/video_status.get?video_id=<video_id>
        Headers: X-Api-Key: <api_key>
        Response: {"data": {"status": "processing" | "completed" | "failed",
                             "video_url": "https://...mp4" (once completed),
                             "error": {...} (once failed)}}
      GET <video_url>  (no auth header assumed -- HeyGen result URLs are typically pre-signed)
        Response: raw MP4 bytes
    """

    def __init__(
        self,
        config: HeyGenConfig | None = None,
        json_transport: JsonTransport = _default_json_transport,
        bytes_transport: BytesTransport = _default_bytes_transport,
    ) -> None:
        self.config = config or HeyGenConfig.from_env()
        self._json_transport = json_transport
        self._bytes_transport = bytes_transport
        self._jobs: dict[str, _JobState] = {}

    def submit(self, brief: dict[str, Any]) -> ProviderResult:
        if not self.config.api_key:
            raise HeyGenError("HeyGen API key is not configured")

        script = str(brief.get("script") or brief.get("text") or "").strip()
        if not script:
            raise HeyGenError("HeyGen presenter brief is missing script text")
        avatar_id = str(brief.get("avatar_id") or self.config.avatar_id or "")
        if not avatar_id:
            raise HeyGenError("HeyGen presenter brief is missing avatar_id")
        voice_id = brief.get("voice_id") or self.config.voice_id

        voice_payload: dict[str, Any] = {"type": "text", "input_text": script}
        if voice_id:
            voice_payload["voice_id"] = str(voice_id)

        body = {
            "video_inputs": [
                {
                    "character": {"type": "avatar", "avatar_id": avatar_id},
                    "voice": voice_payload,
                }
            ]
        }
        headers = {
            "X-Api-Key": self.config.api_key,
            "Content-Type": "application/json",
        }
        request = Request(
            f"{self.config.base_url.rstrip('/')}{DEFAULT_HEYGEN_GENERATE_PATH}",
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        # This call only starts generation -- it must not block waiting for the video to
        # finish. HeyGen's generate endpoint is documented to return quickly with a video_id;
        # actual rendering happens asynchronously and is observed later via poll().
        payload = self._send_json_with_retries(request)
        video_id = str((payload.get("data") or {}).get("video_id") or "")
        if not video_id:
            raise HeyGenError("HeyGen generate response did not include a video_id")

        self._jobs[video_id] = _JobState(status="processing", metadata={"avatar_id": avatar_id})
        return ProviderResult(
            job_id=video_id,
            status="processing",
            content_type="video/mp4",
            metadata={"avatar_id": avatar_id},
        )

    def poll(self, job_id: str) -> ProviderResult:
        # Get-or-create, not "raise if unseen": a real MCP tool call submits a job in one
        # request and polls it again in a LATER, separate request -- each request constructs
        # a fresh HeyGenPresenterProvider() (the same pattern generate_narration_audio already
        # uses for ElevenLabsNarrationProvider), so self._jobs is empty on that later call even
        # though the job genuinely exists on HeyGen's servers. Polling a video_id this instance
        # has never locally seen before must still work -- HeyGen's status endpoint is stateless
        # from the client's perspective and needs nothing but the job_id to answer.
        job = self._jobs.setdefault(job_id, _JobState(status="processing"))

        headers = {"X-Api-Key": self.config.api_key or ""}
        request = Request(
            f"{self.config.base_url.rstrip('/')}{DEFAULT_HEYGEN_STATUS_PATH}?video_id={job_id}",
            headers=headers,
            method="GET",
        )
        payload = self._send_json_with_retries(request)
        data = payload.get("data") or {}
        status = str(data.get("status") or "processing")

        if status == "completed":
            video_url = data.get("video_url")
            if not video_url:
                raise HeyGenError("HeyGen reported job completed but omitted video_url")
            job.status = "completed"
            job.video_url = str(video_url)
            job.metadata = {**job.metadata, "video_url": job.video_url}
        elif status == "failed":
            job.status = "failed"
            job.error = str(data.get("error") or "HeyGen reported job failed")
        else:
            job.status = "processing"

        return ProviderResult(
            job_id=job_id,
            status=job.status,  # type: ignore[arg-type]
            content_type="video/mp4",
            metadata=dict(job.metadata),
        )

    def fetch(self, job_id: str) -> bytes:
        job = self._jobs.get(job_id)
        # Same cross-call-instance concern as poll() above: a fresh provider instance (e.g. a
        # separate MCP tool call) has no locally cached video_url even for a job that is
        # genuinely complete on HeyGen's side, because THIS instance never called poll() on
        # it. Self-heal with one real poll() rather than requiring the caller to have already
        # polled on this exact instance -- poll() itself get-or-creates the local job state,
        # so this is always safe to call.
        if job is None or job.status != "completed" or not job.video_url:
            self.poll(job_id)
            job = self._jobs[job_id]
        if job.status != "completed" or not job.video_url:
            raise HeyGenError(
                f"HeyGen job {job_id} is not complete yet (status={job.status}); "
                "call poll() until it reports 'completed' before fetch()"
            )

        request = Request(job.video_url, method="GET")
        return self._send_bytes_with_retries(request)

    def _send_json_with_retries(self, request: Request) -> dict[str, Any]:
        attempts = self.config.max_retries + 1
        for attempt in range(attempts):
            try:
                return self._json_transport(request, self.config.timeout_seconds)
            except HTTPError as exc:
                if exc.code < 500 or attempt == attempts - 1:
                    raise HeyGenError(f"HeyGen request failed with status {exc.code}") from exc
            except URLError as exc:
                if attempt == attempts - 1:
                    raise HeyGenError("HeyGen request failed") from exc
            if self.config.retry_backoff_seconds > 0:
                time.sleep(self.config.retry_backoff_seconds * (attempt + 1))
        raise HeyGenError("HeyGen request failed")

    def _send_bytes_with_retries(self, request: Request) -> bytes:
        attempts = self.config.max_retries + 1
        for attempt in range(attempts):
            try:
                return self._bytes_transport(request, self.config.timeout_seconds)
            except HTTPError as exc:
                if exc.code < 500 or attempt == attempts - 1:
                    raise HeyGenError(f"HeyGen video download failed with status {exc.code}") from exc
            except URLError as exc:
                if attempt == attempts - 1:
                    raise HeyGenError("HeyGen video download failed") from exc
            if self.config.retry_backoff_seconds > 0:
                time.sleep(self.config.retry_backoff_seconds * (attempt + 1))
        raise HeyGenError("HeyGen video download failed")
