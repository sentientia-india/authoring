from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .outbox import claim_events, mark_delivered, release_failed

EventHandler = Callable[[dict[str, Any]], None]


def process_outbox_batch(
    handlers: dict[str, EventHandler], *, limit: int = 25, lease_seconds: int = 60, max_attempts: int = 5
) -> dict[str, int]:
    """Process one bounded batch using an explicit event-type handler allowlist."""
    summary = {"claimed": 0, "delivered": 0, "retry_scheduled": 0, "dead_lettered": 0}
    for event in claim_events(limit=limit, lease_seconds=lease_seconds):
        summary["claimed"] += 1
        handler = handlers.get(event["event_type"])
        try:
            if handler is None:
                raise LookupError("unsupported_event_type")
            handler(event)
        except Exception as exc:  # noqa: BLE001 - error class is reduced before persistence
            error_code = type(exc).__name__.lower()[:120]
            result = release_failed(
                tenant_id=event["tenant_id"],
                event_id=event["event_id"],
                error_code=error_code,
                max_attempts=max_attempts,
            )
            summary[result["status"]] += 1
        else:
            mark_delivered(tenant_id=event["tenant_id"], event_id=event["event_id"])
            summary["delivered"] += 1
    return summary
