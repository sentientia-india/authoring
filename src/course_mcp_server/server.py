from __future__ import annotations

import os
from typing import Any

try:
    from fastmcp import FastMCP
except Exception:  # pragma: no cover - fallback for environments without fastmcp installed
    FastMCP = None  # type: ignore

from .security import RequestContext, validate_token
from .tools import TOOL_REGISTRY, safe_error

SERVER_INSTRUCTIONS = """
Samrat Course MCP exposes only safe, allowlisted course-generation tools.
Do not request shell, filesystem, environment, database, Docker, or prompt-dump access.
Use tools only for course outline, lesson, quiz, role-play, schema validation, SCORM scaffold,
and generation status workflows. High-risk publish actions require human approval and are not in MVP.
""".strip()


def _context_from_payload(payload: dict[str, Any] | None) -> RequestContext:
    payload = payload or {}
    token = payload.pop("mcp_api_token", None) or os.getenv("MCP_API_TOKEN")
    validate_token(token)
    return RequestContext(
        tenant_id=payload.pop("tenant_id", "default"),
        user_id=payload.pop("user_id", "codex"),
        token=token,
        request_id=payload.pop("request_id", None),
    )


def create_mcp_server():
    if FastMCP is None:
        raise RuntimeError("fastmcp package is not installed")
    mcp = FastMCP(name="samrat-course-mcp", instructions=SERVER_INSTRUCTIONS)

    for tool_name, handler in TOOL_REGISTRY.items():
        def make_tool(name: str, fn):
            @mcp.tool(name=name)
            def tool(payload: dict[str, Any]) -> dict[str, Any]:
                try:
                    context = _context_from_payload(dict(payload or {}))
                    clean_payload = dict(payload or {})
                    clean_payload.pop("mcp_api_token", None)
                    clean_payload.pop("tenant_id", None)
                    clean_payload.pop("user_id", None)
                    clean_payload.pop("request_id", None)
                    return fn(clean_payload, context)
                except Exception as exc:  # return safe error to client
                    return safe_error(exc)
            return tool

        make_tool(tool_name, handler)

    return mcp


def main() -> None:
    mcp = create_mcp_server()
    host = os.getenv("MCP_HOST", "127.0.0.1")
    port = int(os.getenv("MCP_PORT", "8777"))
    # FastMCP transport names vary by version. For production, pin and verify fastmcp version.
    # The default here targets HTTP-style deployment for Docker/Codex.
    mcp.run(transport="http", host=host, port=port, path="/mcp")


if __name__ == "__main__":
    main()
