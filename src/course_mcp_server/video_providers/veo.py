from __future__ import annotations

import base64
import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..security import read_secret
from .base import ProviderResult, VideoProviderError

DEFAULT_VEO_BASE_URL = "https://generativelanguage.googleapis.com"
# UNVERIFIED ASSUMPTION (no live Gemini/Veo API key available to confirm end-to-end, flagged
# here and in the final report exactly as elevenlabs.py/heygen.py flag their own assumed
# shapes): Veo model names/versions are documented to change over time. "veo-3.0-generate-001"
# is a reasonable current-as-of-this-writing default; override via GEMINI_VEO_MODEL if it has
# moved on by the time this is run against a real account.
DEFAULT_VEO_MODEL = "veo-3.0-generate-001"
DEFAULT_VEO_API_VERSION = "v1beta"


class VeoError(VideoProviderError):
    """Raised when the Veo/Gemini video-clip provider call fails safely."""


@dataclass(frozen=True)
class VeoConfig:
    api_key: str | None = None
    model: str = DEFAULT_VEO_MODEL
    base_url: str = DEFAULT_VEO_BASE_URL
    api_version: str = DEFAULT_VEO_API_VERSION
    timeout_seconds: float = 60.0
    max_retries: int = 2
    retry_backoff_seconds: float = 0.5

    @classmethod
    def from_env(cls) -> "VeoConfig":
        return cls(
            api_key=read_secret("GEMINI_API_KEY"),
            model=os.getenv("GEMINI_VEO_MODEL", DEFAULT_VEO_MODEL),
            base_url=os.getenv("GEMINI_VEO_BASE_URL", DEFAULT_VEO_BASE_URL),
            api_version=os.getenv("GEMINI_VEO_API_VERSION", DEFAULT_VEO_API_VERSION),
            timeout_seconds=float(os.getenv("GEMINI_VEO_TIMEOUT_SECONDS", "60")),
            max_retries=int(os.getenv("GEMINI_VEO_MAX_RETRIES", "2")),
            retry_backoff_seconds=float(os.getenv("GEMINI_VEO_RETRY_BACKOFF_SECONDS", "0.5")),
        )

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)


# Google's operation-polling and Files-API-style download calls both return/consume JSON or
# raw bytes over plain HTTPS, same two-transport split as heygen.py -- one for the JSON
# generate/poll calls, one for downloading the finished clip bytes once the operation reports
# "done" with a populated response.
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
    video_uri: str | None = None
    inline_bytes: bytes | None = None
    mime_type: str = "video/mp4"
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class VeoClipProvider:
    """VideoProvider implementation for Google Veo (Gemini API) B-roll/scene clip generation.

    Distinct from HeyGenPresenterProvider (avatar/presenter video) -- this adapter targets
    Veo's video generation for illustrative scene clips, not a talking avatar.

    Google's Gemini API models video generation as a standard Google Long-Running Operation
    (LRO), not a custom job-id-and-status-endpoint pair the way HeyGen does:
      submit() -> POST .../models/{model}:predictLongRunning, returns immediately with
                  {"name": "operations/abc123xyz", "done": false}. That "name" string IS the
                  job_id/reference used for every later poll()/fetch() call -- there is no
                  separate video-id field.
      poll()   -> GET .../{operation_name}?key=<API_KEY> (the operation name, e.g.
                  "operations/abc123xyz", is used directly as part of the URL path, not a
                  query param). Returns {"name": ..., "done": true|false, "response": {...}
                  (once done, success), "error": {...} (once done, failure)}. "done": true
                  alone does NOT mean success -- this adapter checks whether "response" or
                  "error" is populated before deciding completed vs. failed.
      fetch()  -> Once poll() reports "completed", the operation's "response" contains a
                  reference to the generated video: either inline base64-encoded bytes, or a
                  "uri" pointing at Google's Files API. Both shapes are handled: inline bytes
                  are decoded and returned directly; a uri is downloaded via a real HTTP call.
                  CRITICALLY -- unlike HeyGen's adapter, which assumes an unauthenticated
                  pre-signed download URL -- Google's Files API download ALSO requires the API
                  key (an "x-goog-api-key" header here), same as every other call in this
                  family. Only valid once poll() has reported "completed"; calling it earlier
                  raises VeoError rather than blocking or returning garbage.

    UNVERIFIED ASSUMPTIONS (no live Gemini/Veo API key was available to confirm this
    end-to-end; flagged here and in the final report exactly as elevenlabs.py/heygen.py flag
    their own assumed shapes):
      POST {base_url}/v1beta/models/{model}:predictLongRunning?key=<API_KEY>
        Body: {"instances": [{"prompt": "..."}], "parameters": {...optional...}}
        Response: {"name": "operations/abc123xyz", "done": false}
      GET {base_url}/v1beta/{operation_name}?key=<API_KEY>
        Response: {"name": ..., "done": true|false,
                    "response": {"generateVideoResponse": {"generatedSamples": [
                        {"video": {"uri": "https://...", "mimeType": "video/mp4"}}
                        # or {"video": {"bytesBase64Encoded": "...", "mimeType": "video/mp4"}}
                    ]}}, "error": {...}}
        The exact nesting of the completed response (which key holds the sample list, and
        whether it's "generatedSamples", "generatedVideos", or something else) is the least
        certain part of this shape -- _extract_video_ref() below tries a couple of reasonable
        candidate keys and raises a clear VeoError if none match, rather than guessing silently.
      GET <uri>  (WITH auth -- x-goog-api-key header, unlike HeyGen's unauthenticated
                  pre-signed URL assumption)
        Response: raw video bytes
    """

    def __init__(
        self,
        config: VeoConfig | None = None,
        json_transport: JsonTransport = _default_json_transport,
        bytes_transport: BytesTransport = _default_bytes_transport,
    ) -> None:
        self.config = config or VeoConfig.from_env()
        self._json_transport = json_transport
        self._bytes_transport = bytes_transport
        self._jobs: dict[str, _JobState] = {}

    def submit(self, brief: dict[str, Any]) -> ProviderResult:
        if not self.config.api_key:
            raise VeoError("Gemini API key is not configured")

        prompt = str(brief.get("prompt") or brief.get("script") or brief.get("text") or "").strip()
        if not prompt:
            raise VeoError("Veo generation brief is missing a prompt")

        instance: dict[str, Any] = {"prompt": prompt}
        body: dict[str, Any] = {"instances": [instance]}
        parameters: dict[str, Any] = {}
        if brief.get("aspect_ratio"):
            parameters["aspectRatio"] = str(brief["aspect_ratio"])
        if brief.get("duration_seconds"):
            parameters["durationSeconds"] = brief["duration_seconds"]
        if parameters:
            body["parameters"] = parameters

        url = (
            f"{self.config.base_url.rstrip('/')}/{self.config.api_version}/models/"
            f"{self.config.model}:predictLongRunning?key={self.config.api_key}"
        )
        request = Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        # This call only starts generation -- it must not block waiting for the clip to
        # finish. Veo's predictLongRunning endpoint is documented to return quickly with an
        # LRO operation resource; actual rendering happens asynchronously and is observed
        # later via poll().
        payload = self._send_json_with_retries(request)
        operation_name = str(payload.get("name") or "")
        if not operation_name:
            raise VeoError("Veo generate response did not include an operation name")

        self._jobs[operation_name] = _JobState(status="processing")
        return ProviderResult(
            job_id=operation_name,
            status="processing",
            content_type="video/mp4",
            metadata={"model": self.config.model},
        )

    def poll(self, job_id: str) -> ProviderResult:
        # Get-or-create, not "raise if unseen": a real MCP tool call submits a job in one
        # request and polls it again in a LATER, separate request -- each request constructs
        # a fresh VeoClipProvider() (the same pattern generate_presenter_video already uses
        # for HeyGenPresenterProvider), so self._jobs is empty on that later call even though
        # the operation genuinely exists on Google's servers. Polling an operation name this
        # instance has never locally seen before must still work -- the LRO GetOperation call
        # is stateless from the client's perspective and needs nothing but the operation name.
        job = self._jobs.setdefault(job_id, _JobState(status="processing"))

        url = f"{self.config.base_url.rstrip('/')}/{self.config.api_version}/{job_id}?key={self.config.api_key or ''}"
        request = Request(url, method="GET")
        payload = self._send_json_with_retries(request)

        done = bool(payload.get("done"))
        if not done:
            job.status = "processing"
        else:
            error = payload.get("error")
            response = payload.get("response")
            if error:
                job.status = "failed"
                job.error = str(error)
            elif response:
                uri, inline_bytes, mime_type = self._extract_video_ref(response)
                job.status = "completed"
                job.video_uri = uri
                job.inline_bytes = inline_bytes
                job.mime_type = mime_type
                job.metadata = {**job.metadata, "mime_type": mime_type}
                if uri:
                    job.metadata["video_uri"] = uri
            else:
                # done=true but neither "response" nor "error" populated -- an LRO that
                # reports terminal without either field is not a shape this adapter can make
                # sense of, so treat it as a failure rather than silently guessing.
                job.status = "failed"
                job.error = "Veo operation reported done=true with no response or error"

        return ProviderResult(
            job_id=job_id,
            status=job.status,  # type: ignore[arg-type]
            content_type=job.mime_type,
            metadata=dict(job.metadata),
        )

    def fetch(self, job_id: str) -> bytes:
        job = self._jobs.get(job_id)
        # Same cross-call-instance concern as poll() above: a fresh provider instance (e.g. a
        # separate MCP tool call) has no locally cached completion state even for an operation
        # that is genuinely complete on Google's side, because THIS instance never called
        # poll() on it. Self-heal with one real poll() rather than requiring the caller to have
        # already polled on this exact instance -- poll() itself get-or-creates the local job
        # state, so this is always safe to call.
        if job is None or job.status != "completed" or (not job.video_uri and job.inline_bytes is None):
            self.poll(job_id)
            job = self._jobs[job_id]
        if job.status != "completed":
            raise VeoError(
                f"Veo job {job_id} is not complete yet (status={job.status}); "
                "call poll() until it reports 'completed' before fetch()"
            )

        if job.inline_bytes is not None:
            return job.inline_bytes
        if not job.video_uri:
            raise VeoError(f"Veo job {job_id} completed but has no video uri or inline bytes")

        # Unlike HeyGen's assumed unauthenticated pre-signed download URL, Google's Files API
        # download also requires the API key -- sent here as the x-goog-api-key header, same
        # auth mechanism used across the rest of this family of Google APIs.
        request = Request(job.video_uri, headers={"x-goog-api-key": self.config.api_key or ""}, method="GET")
        return self._send_bytes_with_retries(request)

    @staticmethod
    def _extract_video_ref(response: dict[str, Any]) -> tuple[str | None, bytes | None, str]:
        samples = (
            (response.get("generateVideoResponse") or {}).get("generatedSamples")
            or response.get("generatedSamples")
            or response.get("generatedVideos")
            or response.get("videos")
        )
        if not samples:
            raise VeoError("Veo completed response did not include any generated video samples")

        sample = samples[0]
        video = sample.get("video") if isinstance(sample, dict) and "video" in sample else sample
        if not isinstance(video, dict):
            raise VeoError("Veo completed response had an unexpected generated-sample shape")

        mime_type = str(video.get("mimeType") or "video/mp4")
        inline_b64 = video.get("bytesBase64Encoded") or video.get("bytes")
        if inline_b64:
            try:
                return None, base64.b64decode(inline_b64), mime_type
            except (ValueError, TypeError) as exc:
                raise VeoError("Veo completed response had invalid base64 inline video bytes") from exc

        uri = video.get("uri")
        if uri:
            return str(uri), None, mime_type

        raise VeoError("Veo completed response did not include a video uri or inline bytes")

    def _send_json_with_retries(self, request: Request) -> dict[str, Any]:
        attempts = self.config.max_retries + 1
        for attempt in range(attempts):
            try:
                return self._json_transport(request, self.config.timeout_seconds)
            except HTTPError as exc:
                if exc.code < 500 or attempt == attempts - 1:
                    raise VeoError(f"Veo request failed with status {exc.code}") from exc
            except URLError as exc:
                if attempt == attempts - 1:
                    raise VeoError("Veo request failed") from exc
            if self.config.retry_backoff_seconds > 0:
                time.sleep(self.config.retry_backoff_seconds * (attempt + 1))
        raise VeoError("Veo request failed")

    def _send_bytes_with_retries(self, request: Request) -> bytes:
        attempts = self.config.max_retries + 1
        for attempt in range(attempts):
            try:
                return self._bytes_transport(request, self.config.timeout_seconds)
            except HTTPError as exc:
                if exc.code < 500 or attempt == attempts - 1:
                    raise VeoError(f"Veo video download failed with status {exc.code}") from exc
            except URLError as exc:
                if attempt == attempts - 1:
                    raise VeoError("Veo video download failed") from exc
            if self.config.retry_backoff_seconds > 0:
                time.sleep(self.config.retry_backoff_seconds * (attempt + 1))
        raise VeoError("Veo video download failed")
