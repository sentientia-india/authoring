from __future__ import annotations

import json
import os
import time
from pathlib import Path


def _path() -> Path:
    default_dir = Path(os.getenv("OUTPUT_DIR", "course_mcp_output"))
    return Path(os.getenv("RATE_LIMIT_STORE_PATH", str(default_dir / "rate_limits.json"))).resolve()


def _read() -> dict[str, list[float]]:
    path = _path()
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write(data: dict[str, list[float]]) -> None:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def check_rate_limit(*, tenant_id: str, user_id: str) -> bool:
    limit = int(os.getenv("RATE_LIMIT_REQUESTS", "120"))
    window = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))
    now = time.time()
    key = f"{tenant_id}:{user_id}"
    data = _read()
    hits = [stamp for stamp in data.get(key, []) if now - stamp < window]
    if len(hits) >= limit:
        data[key] = hits
        _write(data)
        return False
    hits.append(now)
    data[key] = hits
    _write(data)
    return True
