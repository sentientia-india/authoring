from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any


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
            client.lpush(queue_name, json.dumps({"job_id": job_id, "payload": payload}))
            job["backend"] = "redis"
        except Exception:
            job["backend"] = "inline"
    return job
