from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

# Matches docs/authoring-platform-plan.md section 3.2's provider contract:
#   VideoProvider.submit(brief)  -> job_id
#   VideoProvider.poll(job_id)   -> status
#   VideoProvider.fetch(job_id)  -> asset bytes
#
# See section "3.3.1 Correction" in that doc: this codebase has no real async job/worker
# infrastructure anywhere, so the interface is shaped to accommodate a genuinely slow future
# provider (HeyGen, Veo) without requiring every adapter to actually be async. A fast
# synchronous provider like ElevenLabs text-to-speech implements submit() as a real blocking
# HTTP call that returns an already-"completed" job, and poll()/fetch() are thin formalities
# over that cached result -- there is no queue or worker involved.
#
# GenerationStatus is genuinely three-state, not two: "processing" was added alongside the
# HeyGen presenter-video adapter, whose submit() call kicks off generation that takes minutes
# and returns before it's done. submit() may return "processing" (job started, not yet
# complete) or, for a fast synchronous provider like ElevenLabs, "completed" directly. poll()
# reports "processing" while a slow provider is still working and transitions to "completed"
# or "failed" once the remote job reaches a terminal state. fetch() is only meaningful once a
# job is "completed". This widening is additive: ElevenLabsNarrationProvider only ever
# produces "completed" or raises, so it never observes "processing".
GenerationStatus = Literal["processing", "completed", "failed"]


class VideoProviderError(RuntimeError):
    """Raised when a video/audio provider call fails safely (not configured, HTTP failure, etc.)."""


@dataclass(frozen=True)
class ProviderResult:
    """The outcome of a submit() call. For synchronous providers this is already terminal."""

    job_id: str
    status: GenerationStatus
    content_type: str = "application/octet-stream"
    metadata: dict[str, Any] = field(default_factory=dict)


class VideoProvider(Protocol):
    """Common shape for any narration/video generation provider (see module docstring)."""

    def submit(self, brief: dict[str, Any]) -> ProviderResult:
        """Kick off generation for one brief. May block for genuinely synchronous providers."""
        ...

    def poll(self, job_id: str) -> ProviderResult:
        """Return the current status of a previously submitted job."""
        ...

    def fetch(self, job_id: str) -> bytes:
        """Return the generated asset bytes for a completed job."""
        ...
