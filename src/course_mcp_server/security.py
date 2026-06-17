from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .audit_store import record_audit_event

ALLOWED_TOOLS: set[str] = {
    "create_material_ticket",
    "generate_chapter_layout",
    "create_course_project",
    "ingest_course_source",
    "generate_course_blueprint",
    "generate_module_pack",
    "generate_lesson_pack",
    "generate_interactive_activity",
    "generate_assessment_bank",
    "generate_roleplay_simulation",
    "validate_instructional_quality",
    "build_export_package",
    "get_course_generation_status",
    "list_course_artifacts",
    "request_publish_approval",
}

DENIED_TOOL_PATTERNS = (
    "shell",
    "exec",
    "read_file",
    "write_file",
    "env",
    "database",
    "query",
    "docker",
    "prompt_dump",
    "logs_dump",
)

SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*[^\s,;]+"),
    re.compile(r"sk-[A-Za-z0-9_\-]{12,}"),
    re.compile(r"/app/(src|secrets|config)[^\s,;]*"),
]


class SecurityError(PermissionError):
    """Raised when an MCP operation violates security policy."""


@dataclass(frozen=True)
class RequestContext:
    tenant_id: str
    user_id: str
    token: str | None = None
    request_id: str | None = None


def assert_tool_allowed(tool_name: str) -> None:
    lowered = tool_name.lower()
    if tool_name not in ALLOWED_TOOLS:
        raise SecurityError(f"Tool is not allowlisted: {tool_name}")
    if any(pattern in lowered for pattern in DENIED_TOOL_PATTERNS):
        raise SecurityError(f"Tool name violates denied pattern: {tool_name}")


def read_secret(name: str) -> str | None:
    file_path = os.getenv(f"{name}_FILE")
    if file_path:
        try:
            return Path(file_path).read_text(encoding="utf-8").strip() or None
        except OSError as exc:
            raise SecurityError(f"{name}_FILE could not be read") from exc
    return os.getenv(name) or None


def validate_token(token: str | None) -> None:
    expected = read_secret("MCP_API_TOKEN")
    if not expected:
        raise SecurityError("MCP_API_TOKEN is not configured")
    if not token or token != expected:
        raise SecurityError("Invalid MCP token")


def redact_text(value: str) -> str:
    redacted = value
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def redact_output(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, list):
        return [redact_output(item) for item in value]
    if isinstance(value, dict):
        return {key: redact_output(item) for key, item in value.items()}
    return value


def hash_payload(payload: Any) -> str:
    raw = repr(payload).encode("utf-8", errors="ignore")
    return hashlib.sha256(raw).hexdigest()


def audit_event(tool_name: str, context: RequestContext, input_payload: Any, output_payload: Any) -> dict[str, Any]:
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "request_id": context.request_id,
        "tenant_id": context.tenant_id,
        "user_id": context.user_id,
        "tool_name": tool_name,
        "decision": "allowed",
        "input_hash": hash_payload(input_payload),
        "output_hash": hash_payload(output_payload),
    }
    try:
        record_audit_event(event)
    except Exception as exc:
        event["audit_persisted"] = False
        event["audit_persist_error"] = exc.__class__.__name__
    else:
        event["audit_persisted"] = True
    return event
