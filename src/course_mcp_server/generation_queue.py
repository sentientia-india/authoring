from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any


class QueueUnavailableError(RuntimeError):
    pass


def enqueue_generation_job(*, queue_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    raw = json.dumps({"queue": queue_name, "payload": payload}, sort_keys=True)
    job_id = f"queued_{hashlib.sha256(raw.encode()).hexdigest()[:12]}"
    redis_url = os.getenv("REDIS_URL")
    job = {
        "job_id": job_id,
        "queue_name": queue_name,
        "status": "queued",
        "backend": "inline",
        "queued_at": datetime.now(timezone.utc).isoformat(),
    }
    if redis_url:
        try:
            import redis  # type: ignore

            client = redis.Redis.from_url(redis_url)
            marker = f"queue:{queue_name}:job:{job_id}"
            inserted = client.set(marker, "queued", nx=True, ex=7 * 24 * 60 * 60)
            if inserted:
                client.rpush(queue_name, json.dumps({"job_id": job_id, "payload": payload}))
            job["backend"] = "redis"
            job["deduplicated"] = not bool(inserted)
        except Exception as exc:
            if os.getenv("ENVIRONMENT", "development").lower() == "production":
                raise QueueUnavailableError("Durable generation queue is unavailable") from exc
            job["backend"] = "inline"
    return job
