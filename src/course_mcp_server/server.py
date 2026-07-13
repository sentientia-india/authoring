from __future__ import annotations

import os
import base64
import tempfile
import hmac
import logging
import time
from pathlib import Path
from typing import Any

try:
    from fastmcp import FastMCP
    from starlette.responses import FileResponse, JSONResponse, Response
except Exception:  # pragma: no cover - fallback for environments without fastmcp installed
    FastMCP = None  # type: ignore
    JSONResponse = None  # type: ignore
    FileResponse = None  # type: ignore
    Response = None  # type: ignore

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
    embed_document,
    grant_paid_access,
    grant_share_access,
    record_learner_event,
    resolve_domain_file,
    resolve_share_file,
    tutor_reply,
)
from .hosted_repository import (
    add_collection_item,
    create_collection,
    get_collection,
    request_custom_domain,
    remove_custom_domain,
    resolve_grant,
    resolve_verified_domain,
    verify_custom_domain,
)
from .communication import CommunicationError, record_provider_event
from .analytics import (
    account_dashboard,
    analytics_quality_dashboard,
    course_analytics,
    export_csv,
    funnel_analytics,
    learner_timeline,
    question_analytics,
    report_run_access,
    schedule_report,
)
from .observability import dependency_health, increment, prometheus_metrics, structured_log
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
        dependencies = dependency_health()
        return JSONResponse(
            {"ok": dependencies["ready"], "service": "samrat-course-mcp", "dependencies": dependencies},
            status_code=200 if dependencies["ready"] else 503,
        )

    @mcp.custom_route("/metrics", methods=["GET"], include_in_schema=False)
    async def metrics(_request):  # noqa: ANN001
        return Response(prometheus_metrics(), media_type="text/plain; version=0.0.4")

    @mcp.custom_route("/status", methods=["GET"], include_in_schema=False)
    async def public_status(_request):  # noqa: ANN001
        dependencies = dependency_health()
        return JSONResponse(
            {
                "status": "operational" if dependencies["ready"] else "degraded",
                "components": {key: value for key, value in dependencies.items() if key != "ready"},
            }
        )

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
            context = _context_from_request(request)
            payload = await request.json()
            result = create_customer_portal_session(
                tenant_id=context.tenant_id,
                return_url=str(payload.get("return_url") or ""),
            )
        except (BillingError, PermissionError, ValueError, TypeError):
            return JSONResponse({"ok": False, "error": "portal_unavailable"}, status_code=400)
        return JSONResponse({"ok": True, **result}, status_code=201)

    @mcp.custom_route("/email/provider-webhook", methods=["POST"], include_in_schema=False)
    async def email_provider_webhook(request):  # noqa: ANN001
        expected = os.getenv("EMAIL_WEBHOOK_SECRET", "")
        supplied = request.headers.get("x-email-webhook-secret", "")
        if not expected or not hmac.compare_digest(expected, supplied):
            return JSONResponse({"ok": False, "error": "invalid_webhook"}, status_code=401)
        try:
            result = record_provider_event(await request.json())
        except (CommunicationError, ValueError, TypeError):
            return JSONResponse({"ok": False, "error": "invalid_event"}, status_code=400)
        return JSONResponse({"ok": True, **result})

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

    @mcp.custom_route("/api/analytics/account", methods=["GET"], include_in_schema=False)
    async def analytics_account(request):  # noqa: ANN001
        try:
            context = _context_from_request(request)
            result = account_dashboard(tenant_id=context.tenant_id)
        except PermissionError:
            return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
        return JSONResponse({"ok": True, "dashboard": result})

    @mcp.custom_route("/api/analytics/releases/{release_id}", methods=["GET"], include_in_schema=False)
    async def analytics_release(request):  # noqa: ANN001
        try:
            context = _context_from_request(request)
            release_id = request.path_params["release_id"]
            result = {
                "course": course_analytics(tenant_id=context.tenant_id, release_id=release_id),
                "questions": question_analytics(tenant_id=context.tenant_id, release_id=release_id),
                "funnel": funnel_analytics(tenant_id=context.tenant_id, release_id=release_id),
            }
        except PermissionError:
            return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
        if request.query_params.get("format") == "csv":
            return Response(export_csv([result["course"]]), media_type="text/csv")
        return JSONResponse({"ok": True, **result})

    @mcp.custom_route("/api/analytics/schedules", methods=["POST"], include_in_schema=False)
    async def analytics_schedule(request):  # noqa: ANN001
        try:
            context = _context_from_request(request)
            payload = await request.json()
            result = schedule_report(
                tenant_id=context.tenant_id,
                report_type=str(payload.get("report_type") or "course"),
                release_id=str(payload.get("release_id") or "") or None,
                cadence=str(payload.get("cadence") or "weekly"),
                recipients=[str(value) for value in payload.get("recipients") or []],
                parameters={"learner_id": str(payload.get("learner_id") or "")}
                if str(payload.get("report_type") or "course") == "learner"
                else {},
            )
        except (PermissionError, ValueError, TypeError):
            return JSONResponse({"ok": False, "error": "invalid_schedule"}, status_code=400)
        return JSONResponse({"ok": True, "schedule": result}, status_code=201)

    @mcp.custom_route("/api/analytics/learners/{learner_id}", methods=["GET"], include_in_schema=False)
    async def analytics_learner(request):  # noqa: ANN001
        try:
            context = _context_from_request(request)
            result = learner_timeline(
                tenant_id=context.tenant_id, learner_id=request.path_params["learner_id"]
            )
        except PermissionError:
            return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
        return JSONResponse({"ok": True, "timeline": result})

    @mcp.custom_route("/api/analytics/quality", methods=["GET"], include_in_schema=False)
    async def analytics_quality(request):  # noqa: ANN001
        try:
            context = _context_from_request(request)
            result = analytics_quality_dashboard(
                tenant_id=context.tenant_id,
                release_id=request.query_params.get("release_id") or None,
            )
        except PermissionError:
            return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
        return JSONResponse({"ok": True, "quality": result})

    @mcp.custom_route("/api/analytics/report-runs/{run_id}", methods=["GET"], include_in_schema=False)
    async def analytics_report_download(request):  # noqa: ANN001
        try:
            context = _context_from_request(request)
            access = report_run_access(
                tenant_id=context.tenant_id, run_id=request.path_params["run_id"]
            )
        except PermissionError:
            return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
        except LookupError:
            return JSONResponse({"ok": False, "error": "report_not_found"}, status_code=404)
        if access["backend"] == "local":
            return FileResponse(access["path"], media_type="text/csv", filename="learning-report.csv")
        return JSONResponse({"ok": True, "download_url": access["url"], "expires_in": 300})

    @mcp.custom_route("/api/hosted/domains", methods=["POST"], include_in_schema=False)
    async def hosted_domain_request(request):  # noqa: ANN001
        try:
            context = _context_from_request(request)
            payload = await request.json()
            result = request_custom_domain(
                tenant_id=context.tenant_id,
                hostname=str(payload.get("hostname") or ""),
                release_id=str(payload.get("release_id") or "") or None,
            )
        except (PermissionError, ValueError, TypeError):
            return JSONResponse({"ok": False, "error": "invalid_custom_domain"}, status_code=400)
        return JSONResponse({"ok": True, "domain": result}, status_code=201)

    @mcp.custom_route("/api/hosted/access", methods=["POST"], include_in_schema=False)
    async def hosted_access_grant(request):  # noqa: ANN001
        try:
            context = _context_from_request(request)
            payload = await request.json()
            result = grant_share_access(
                str(payload.get("share_token") or ""),
                str(payload.get("subject") or ""),
                str(payload.get("source") or ""),
                expected_tenant_id=context.tenant_id,
            )
        except (PermissionError, HostedLearningError, ValueError, TypeError):
            return JSONResponse({"ok": False, "error": "access_grant_failed"}, status_code=400)
        return JSONResponse({"ok": True, "access": result}, status_code=201)

    @mcp.custom_route("/api/hosted/domains/verify", methods=["POST"], include_in_schema=False)
    async def hosted_domain_verify(request):  # noqa: ANN001
        try:
            context = _context_from_request(request)
            payload = await request.json()
            result = verify_custom_domain(
                tenant_id=context.tenant_id,
                hostname=str(payload.get("hostname") or ""),
                observed_token=str(payload.get("observed_token") or ""),
            )
        except (PermissionError, ValueError, TypeError):
            return JSONResponse({"ok": False, "error": "domain_verification_failed"}, status_code=400)
        return JSONResponse({"ok": True, "domain": result})

    @mcp.custom_route("/api/hosted/domains", methods=["DELETE"], include_in_schema=False)
    async def hosted_domain_remove(request):  # noqa: ANN001
        try:
            context = _context_from_request(request)
            payload = await request.json()
            removed = remove_custom_domain(
                tenant_id=context.tenant_id, hostname=str(payload.get("hostname") or "")
            )
        except (PermissionError, ValueError, TypeError):
            return JSONResponse({"ok": False, "error": "domain_removal_failed"}, status_code=400)
        if not removed:
            return JSONResponse({"ok": False, "error": "domain_not_found"}, status_code=404)
        return JSONResponse({"ok": True, "removed": True})

    @mcp.custom_route("/api/hosted/collections", methods=["POST"], include_in_schema=False)
    async def hosted_collection_create(request):  # noqa: ANN001
        try:
            context = _context_from_request(request)
            payload = await request.json()
            result = create_collection(
                tenant_id=context.tenant_id,
                title=str(payload.get("title") or ""),
                slug=str(payload.get("slug") or ""),
                description=str(payload.get("description") or ""),
            )
        except (PermissionError, ValueError, TypeError):
            return JSONResponse({"ok": False, "error": "invalid_collection"}, status_code=400)
        return JSONResponse({"ok": True, "collection": result}, status_code=201)

    @mcp.custom_route("/api/hosted/collections/{collection_id}", methods=["GET"], include_in_schema=False)
    async def hosted_collection_get(request):  # noqa: ANN001
        try:
            context = _context_from_request(request)
            result = get_collection(tenant_id=context.tenant_id, collection_id=request.path_params["collection_id"])
        except PermissionError:
            return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
        if not result:
            return JSONResponse({"ok": False, "error": "collection_not_found"}, status_code=404)
        return JSONResponse({"ok": True, "collection": result})

    @mcp.custom_route("/api/hosted/collections/{collection_id}/items", methods=["POST"], include_in_schema=False)
    async def hosted_collection_item_create(request):  # noqa: ANN001
        try:
            context = _context_from_request(request)
            payload = await request.json()
            result = add_collection_item(
                tenant_id=context.tenant_id,
                collection_id=request.path_params["collection_id"],
                release_id=str(payload.get("release_id") or ""),
                position=int(payload.get("position") or 0),
                prerequisite_release_id=str(payload.get("prerequisite_release_id") or "") or None,
            )
        except (PermissionError, ValueError, TypeError):
            return JSONResponse({"ok": False, "error": "invalid_collection_item"}, status_code=400)
        return JSONResponse({"ok": True, "item": result}, status_code=201)

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

    @mcp.custom_route("/embed/{token}", methods=["GET"], include_in_schema=False)
    async def hosted_embed(request):  # noqa: ANN001
        try:
            body, headers = embed_document(
                request.path_params["token"], request.query_params.get("access_token")
            )
        except HostedLearningError:
            return JSONResponse({"ok": False, "error": "embed_not_found"}, status_code=404)
        return Response(body, media_type="text/html", headers=headers)

    @mcp.custom_route(
        "/internal/caddy/domain-allowed", methods=["GET"], include_in_schema=False
    )
    async def caddy_domain_allowed(request):  # noqa: ANN001
        domain = resolve_verified_domain(request.query_params.get("domain") or "")
        return Response("allowed" if domain else "denied", status_code=200 if domain else 403)

    @mcp.custom_route(
        "/domain/{hostname}/{asset_path:path}", methods=["GET"], include_in_schema=False
    )
    async def hosted_custom_domain(request):  # noqa: ANN001
        try:
            target = resolve_domain_file(
                request.path_params["hostname"], request.path_params.get("asset_path") or "index.html"
            )
        except HostedLearningError:
            return JSONResponse({"ok": False, "error": "custom_domain_not_found"}, status_code=404)
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
                    started = time.monotonic()
                    context = _context_from_payload(dict(payload or {}))
                    clean_payload = dict(payload or {})
                    clean_payload.pop("mcp_api_token", None)
                    clean_payload.pop("tenant_id", None)
                    clean_payload.pop("user_id", None)
                    clean_payload.pop("request_id", None)
                    result = fn(clean_payload, context)
                    increment("course_mcp_tool_requests_total", tool=name, outcome="success")
                    increment(
                        "course_mcp_tool_duration_seconds_total",
                        time.monotonic() - started,
                        tool=name,
                    )
                    return result
                except Exception as exc:  # return safe error to client
                    increment("course_mcp_tool_requests_total", tool=name, outcome="error")
                    structured_log(logging.ERROR, "tool_failed", tool=name, error_type=exc.__class__.__name__)
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
