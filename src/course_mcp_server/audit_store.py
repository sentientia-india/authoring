from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def _path() -> Path:
    default_dir = Path(os.getenv("OUTPUT_DIR", "course_mcp_output"))
    return Path(os.getenv("AUDIT_STORE_PATH", str(default_dir / "audit.json"))).resolve()


def _read() -> list[dict[str, Any]]:
    path = _path()
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def record_audit_event(event: dict[str, Any]) -> dict[str, Any]:
    events = _read()
    events.append(event)
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(events, indent=2, sort_keys=True), encoding="utf-8")
    return event


def list_audit_events(tenant_id: str) -> list[dict[str, Any]]:
    return [event for event in _read() if event.get("tenant_id") == tenant_id]
