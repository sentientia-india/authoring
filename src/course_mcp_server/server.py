from __future__ import annotations

import os
from typing import Any

try:
    from fastmcp import FastMCP
    from starlette.responses import JSONResponse
except Exception:  # pragma: no cover - fallback for environments without fastmcp installed
    FastMCP = None  # type: ignore
    JSONResponse = None  # type: ignore

from .licensing import resolve_license
from .security import RequestContext
from .rate_limit import check_rate_limit
from .tools import TOOL_REGISTRY, safe_error

SERVER_INSTRUCTIONS = """
Samrat Course MCP exposes only safe, allowlisted course-generation tools.
Do not request shell, filesystem, environment, database, Docker, or prompt-dump access.
Use tools only for project creation, controlled source ingestion, blueprint/module/lesson/activity/
assessment generation, quality validation, export packaging, status, artifact listing, and publish
approval workflows. High-risk publish actions require human approval and are not directly exposed.
""".strip()


def _context_from_payload(payload: dict[str, Any] | None) -> RequestContext:
    payload = payload or {}
    token = payload.pop("mcp_api_token", None) or os.getenv("MCP_API_TOKEN")
    license_ = resolve_license(token)
    # Tenant identity comes from the license, never from the caller's payload
    # (the admin bootstrap key may impersonate tenants for support).
    claimed_tenant = payload.pop("tenant_id", "default")
    tenant_id = claimed_tenant if license_.tier == "admin" else license_.tenant
    context = RequestContext(
        tenant_id=tenant_id,
        user_id=payload.pop("user_id", "codex"),
        token=token,
        request_id=payload.pop("request_id", None),
        tier=license_.tier,
    )
    if not check_rate_limit(tenant_id=context.tenant_id, user_id=context.user_id):
        raise PermissionError("Rate limit exceeded")
    return context


def create_mcp_server():
    if FastMCP is None:
        raise RuntimeError("fastmcp package is not installed")
    mcp = FastMCP(name="samrat-course-mcp", instructions=SERVER_INSTRUCTIONS)

    @mcp.custom_route("/health", methods=["GET"], include_in_schema=False)
    async def health(_request):  # noqa: ANN001
        return JSONResponse({"ok": True, "service": "samrat-course-mcp"})

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
