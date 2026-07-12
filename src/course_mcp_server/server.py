from __future__ import annotations

import os
import base64
import tempfile
from pathlib import Path
from typing import Any

try:
    from fastmcp import FastMCP
    from starlette.responses import FileResponse, JSONResponse
except Exception:  # pragma: no cover - fallback for environments without fastmcp installed
    FastMCP = None  # type: ignore
    JSONResponse = None  # type: ignore
    FileResponse = None  # type: ignore

from .licensing import lifecycle_warning, resolve_license
from .billing import (
    BillingError,
    create_checkout_session,
    create_customer_portal_session,
    handle_stripe_webhook,
)
from .hosted_learning import (
    HostedLearningError,
    capture_lead,
    course_dashboard,
    create_share,
    grant_paid_access,
    record_learner_event,
    resolve_share_file,
    tutor_reply,
)
from .hosted_repository import resolve_grant
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
        license_warning=lifecycle_warning(license_),
    )
    if not check_rate_limit(tenant_id=context.tenant_id, user_id=context.user_id):
        raise PermissionError("Rate limit exceeded")
    return context


def _context_from_request(request) -> RequestContext:  # noqa: ANN001
    authorization = request.headers.get("authorization", "")
    token = authorization[7:].strip() if authorization.lower().startswith("bearer ") else None
    if not token:
        raise PermissionError("Bearer token required")
    return _context_from_payload(
        {
            "mcp_api_token": token,
            "user_id": request.headers.get("x-user-id", "hosted-admin"),
            "request_id": request.headers.get("x-request-id"),
        }
    )


def create_mcp_server():
    if FastMCP is None:
        raise RuntimeError("fastmcp package is not installed")
    mcp = FastMCP(name="samrat-course-mcp", instructions=SERVER_INSTRUCTIONS)

    @mcp.custom_route("/health", methods=["GET"], include_in_schema=False)
    async def health(_request):  # noqa: ANN001
        return JSONResponse({"ok": True, "service": "samrat-course-mcp"})

    @mcp.custom_route("/metrics", methods=["GET"], include_in_schema=False)
    async def metrics(_request):  # noqa: ANN001
        return JSONResponse({"ok": True, "service": "samrat-course-mcp", "status": "ready"})

    @mcp.custom_route("/billing/stripe-webhook", methods=["POST"], include_in_schema=False)
    async def stripe_webhook(request):  # noqa: ANN001
        try:
            result = handle_stripe_webhook(
                await request.body(), request.headers.get("stripe-signature", "")
            )
        except (BillingError, ValueError):
            return JSONResponse({"ok": False, "error": "invalid_webhook"}, status_code=400)
        safe_result = {
            key: value for key, value in result.items() if key not in {"license_key", "access_token"}
        }
        return JSONResponse({"ok": True, **safe_result})

    @mcp.custom_route("/billing/checkout", methods=["POST"], include_in_schema=False)
    async def billing_checkout(request):  # noqa: ANN001
        try:
            context = _context_from_request(request)
            payload = await request.json()
            result = create_checkout_session(
                tenant_id=context.tenant_id,
                price_id=str(payload.get("price_id") or ""),
                tier=str(payload.get("tier") or "pro"),
                success_url=str(payload.get("success_url") or ""),
                cancel_url=str(payload.get("cancel_url") or ""),
                share_token=str(payload.get("share_token") or "") or None,
                mode=str(payload.get("mode") or "subscription"),
            )
        except (BillingError, PermissionError, ValueError, TypeError):
            return JSONResponse({"ok": False, "error": "checkout_unavailable"}, status_code=400)
        return JSONResponse({"ok": True, **result}, status_code=201)

    @mcp.custom_route("/billing/customer-portal", methods=["POST"], include_in_schema=False)
    async def billing_customer_portal(request):  # noqa: ANN001
        try:
            _context_from_request(request)
            payload = await request.json()
            result = create_customer_portal_session(
                customer_id=str(payload.get("customer_id") or ""),
                return_url=str(payload.get("return_url") or ""),
            )
        except (BillingError, PermissionError, ValueError, TypeError):
            return JSONResponse({"ok": False, "error": "portal_unavailable"}, status_code=400)
        return JSONResponse({"ok": True, **result}, status_code=201)

    @mcp.custom_route("/api/hosted/releases", methods=["POST"], include_in_schema=False)
    async def publish_hosted_release(request):  # noqa: ANN001
        temporary: Path | None = None
        try:
            context = _context_from_request(request)
            payload = await request.json()
            encoded = str(payload.get("package_base64") or "")
            package = base64.b64decode(encoded, validate=True)
            if not package or len(package) > 60 * 1024 * 1024:
                raise ValueError("invalid package")
            with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as handle:
                handle.write(package)
                temporary = Path(handle.name)
            result = create_share(
                temporary,
                tenant=context.tenant_id,
                course_id=str(payload.get("course_id") or ""),
                access_mode=str(payload.get("access_mode") or "unlisted"),
            )
        except (HostedLearningError, ValueError, TypeError, PermissionError):
            return JSONResponse({"ok": False, "error": "invalid_release"}, status_code=400)
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)
        return JSONResponse({"ok": True, "release": result}, status_code=201)

    @mcp.custom_route("/api/hosted/{token}/dashboard", methods=["GET"], include_in_schema=False)
    async def hosted_admin_dashboard(request):  # noqa: ANN001
        try:
            context = _context_from_request(request)
            token = request.path_params["token"]
            grant = resolve_grant(token)
            if not grant or grant["tenant_id"] != context.tenant_id:
                raise HostedLearningError("Share not found")
            result = course_dashboard(token)
        except (HostedLearningError, PermissionError):
            return JSONResponse({"ok": False, "error": "share_not_found"}, status_code=404)
        return JSONResponse({"ok": True, "dashboard": result})

    @mcp.custom_route("/api/hosted/{token}/entitlements", methods=["POST"], include_in_schema=False)
    async def hosted_entitlement(request):  # noqa: ANN001
        try:
            context = _context_from_request(request)
            token = request.path_params["token"]
            grant = resolve_grant(token)
            if not grant or grant["tenant_id"] != context.tenant_id:
                raise HostedLearningError("Share not found")
            payload = await request.json()
            result = grant_paid_access(token, str(payload.get("purchaser") or ""))
        except (HostedLearningError, PermissionError, ValueError, TypeError):
            return JSONResponse({"ok": False, "error": "entitlement_failed"}, status_code=400)
        return JSONResponse({"ok": True, **result}, status_code=201)

    @mcp.custom_route("/learn/{token}/{asset_path:path}", methods=["GET"], include_in_schema=False)
    async def hosted_course(request):  # noqa: ANN001
        try:
            target = resolve_share_file(
                request.path_params["token"],
                request.path_params.get("asset_path") or "index.html",
                request.query_params.get("access_token"),
            )
        except HostedLearningError:
            return JSONResponse({"ok": False, "error": "share_not_found"}, status_code=404)
        return FileResponse(target)

    @mcp.custom_route("/learn/{token}/events", methods=["POST"], include_in_schema=False)
    async def hosted_event(request):  # noqa: ANN001
        try:
            result = record_learner_event(request.path_params["token"], await request.json())
        except (HostedLearningError, ValueError, TypeError):
            return JSONResponse({"ok": False, "error": "invalid_event"}, status_code=400)
        return JSONResponse({"ok": True, "event": result})

    @mcp.custom_route("/learn/{token}/lead", methods=["POST"], include_in_schema=False)
    async def hosted_lead(request):  # noqa: ANN001
        try:
            payload = await request.json()
            result = capture_lead(request.path_params["token"], str(payload.get("email") or ""))
        except (HostedLearningError, ValueError, TypeError):
            return JSONResponse({"ok": False, "error": "invalid_lead"}, status_code=400)
        return JSONResponse({"ok": True, "lead": result}, status_code=201)

    @mcp.custom_route("/learn/{token}/tutor", methods=["POST"], include_in_schema=False)
    async def hosted_tutor(request):  # noqa: ANN001
        try:
            resolve_share_file(request.path_params["token"], "index.html", request.query_params.get("access_token"))
            payload = await request.json()
            answer = tutor_reply(
                str(payload.get("question", "")),
                str(payload.get("course_context", "")),
                str(payload.get("api_key", "")),
                str(payload.get("model", "openai/gpt-4.1-mini")),
            )
        except (HostedLearningError, ValueError, TypeError):
            return JSONResponse({"ok": False, "error": "tutor_unavailable"}, status_code=400)
        return JSONResponse({"ok": True, "answer": answer})

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
