from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections import defaultdict
from typing import Any

from .database import connection, database_url


STARTED_AT = time.time()
_LOCK = threading.Lock()
_COUNTERS: dict[tuple[str, tuple[tuple[str, str], ...]], float] = defaultdict(float)


def structured_log(level: int, event: str, **fields: Any) -> None:
    blocked = {"token", "secret", "password", "authorization", "prompt", "source_content"}
    clean = {key: value for key, value in fields.items() if key.lower() not in blocked}
    logging.getLogger("course_mcp").log(level, json.dumps({"event": event, **clean}, default=str))


def increment(metric: str, value: float = 1, **labels: str) -> None:
    safe_metric = "".join(character if character.isalnum() or character in "_:" else "_" for character in metric)
    safe_labels = tuple(sorted((str(key), str(label)) for key, label in labels.items()))
    with _LOCK:
        _COUNTERS[(safe_metric, safe_labels)] += value


def dependency_health() -> dict[str, Any]:
    result: dict[str, Any] = {"database": "not_configured", "redis": "not_configured"}
    if database_url():
        try:
            with connection() as active:
                active.execute("SELECT 1").fetchone()
            result["database"] = "ready"
        except Exception:  # noqa: BLE001
            result["database"] = "unavailable"
    redis_url = os.getenv("REDIS_URL", "").strip()
    if redis_url:
        try:
            import redis

            client = redis.Redis.from_url(redis_url, socket_connect_timeout=1, socket_timeout=1)
            result["redis"] = "ready" if client.ping() else "unavailable"
        except Exception:  # noqa: BLE001
            result["redis"] = "unavailable"
    result["ready"] = all(value in {"ready", "not_configured"} for value in result.values())
    return result


def prometheus_metrics() -> str:
    lines = [
        "# HELP course_mcp_uptime_seconds Process uptime.",
        "# TYPE course_mcp_uptime_seconds gauge",
        f"course_mcp_uptime_seconds {time.time() - STARTED_AT:.3f}",
    ]
    with _LOCK:
        items = sorted(_COUNTERS.items())
    for (metric, labels), value in items:
        label_text = ""
        if labels:
            escaped = [f'{key}="{label.replace(chr(34), chr(92) + chr(34))}"' for key, label in labels]
            label_text = "{" + ",".join(escaped) + "}"
        lines.append(f"{metric}{label_text} {value:g}")
    health = dependency_health()
    for dependency in ("database", "redis"):
        lines.append(
            f'course_mcp_dependency_ready{{dependency="{dependency}"}} '
            f'{1 if health[dependency] in {"ready", "not_configured"} else 0}'
        )
    return "\n".join(lines) + "\n"
