from __future__ import annotations

import json
import os
from uuid import uuid4
from pathlib import Path
from typing import Any

from psycopg.types.json import Jsonb

from .database import connection, database_url, ensure_tenant


def _path() -> Path:
    default_dir = Path(os.getenv("OUTPUT_DIR", "course_mcp_output"))
    return Path(os.getenv("AUDIT_STORE_PATH", str(default_dir / "audit.json"))).resolve()


def _read() -> list[dict[str, Any]]:
    path = _path()
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def record_audit_event(event: dict[str, Any]) -> dict[str, Any]:
    if database_url():
        tenant_id = str(event.get("tenant_id") or "")
        if not tenant_id:
            raise ValueError("Audit events require tenant_id")
        audit_id = str(event.get("audit_id") or f"audit_{uuid4().hex}")
        actor_id = str(event.get("user_id") or event.get("actor_id") or "system")
        action = str(event.get("tool_name") or event.get("action") or "unknown")
        with connection() as active:
            ensure_tenant(active, tenant_id)
            active.execute(
                """
                INSERT INTO audit_events
                    (tenant_id, audit_id, actor_id, action, target_type, target_id, result, request_id, metadata)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    tenant_id,
                    audit_id,
                    actor_id,
                    action,
                    event.get("target_type"),
                    event.get("target_id"),
                    str(event.get("result") or "recorded"),
                    event.get("request_id"),
                    Jsonb(event),
                ),
            )
        return event
    events = _read()
    events.append(event)
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(events, indent=2, sort_keys=True), encoding="utf-8")
    return event


def list_audit_events(tenant_id: str) -> list[dict[str, Any]]:
    if database_url():
        with connection() as active:
            rows = active.execute(
                "SELECT metadata FROM audit_events WHERE tenant_id = %s ORDER BY occurred_at",
                (tenant_id,),
            ).fetchall()
            return [dict(row["metadata"]) for row in rows]
    return [event for event in _read() if event.get("tenant_id") == tenant_id]
