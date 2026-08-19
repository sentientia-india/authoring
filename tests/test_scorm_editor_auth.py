"""HTTP-level acceptance tests for Course Studio auth (docs/authoring-platform-plan.md F1, F2).

Prior editor tests only exercised internal functions (import_package, save_course, ...) and
never went through the HTTP Handler, so the service shipped with zero authorization checks
undetected. These tests drive the real ThreadingHTTPServer over a socket.
"""

from __future__ import annotations

import base64
import json
import os
import threading
import time
import urllib.error
import urllib.request
import zipfile
from http.server import ThreadingHTTPServer
from io import BytesIO

import pytest

from apps.scorm_editor.server import Handler, workspace_root


TOKEN = "test-editor-token-12345"


def _minimal_scorm_zip() -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as package:
        package.writestr(
            "imsmanifest.xml",
            '<?xml version="1.0"?>'
            '<manifest xmlns="http://www.imsproject.org/xsd/imscp_rootv1p1p2">'
            '<organizations><organization><item><title>T</title></item></organization></organizations>'
            '<resources><resource href="index.html"></resource></resources>'
            "</manifest>",
        )
        package.writestr("data/course.json", json.dumps({"course_title": "T", "modules": []}))
        package.writestr("index.html", "<html></html>")
    return buffer.getvalue()


@pytest.fixture()
def running_server(monkeypatch, tmp_path):
    monkeypatch.setenv("EDITOR_API_TOKEN", TOKEN)
    monkeypatch.setenv("EDITOR_WORKSPACE_DIR", str(tmp_path / "workspaces"))
    monkeypatch.delenv("EDITOR_ALLOW_INSECURE_DEV", raising=False)
    monkeypatch.delenv("EDITOR_ALLOW_SERVER_AUTHORING", raising=False)
    workspace_root.cache_clear() if hasattr(workspace_root, "cache_clear") else None

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        httpd.shutdown()
        thread.join(timeout=5)


def _get(url: str, token: str | None = None, as_header: bool = True):
    headers = {}
    target = url
    if token is not None:
        if as_header:
            headers["Authorization"] = f"Bearer {token}"
        else:
            target = url + ("&" if "?" in url else "?") + f"token={token}"
    request = urllib.request.Request(target, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def test_static_shell_is_public(running_server):
    status, _ = _get(running_server + "/")
    assert status == 200
    status, _ = _get(running_server + "/static/editor.js")
    assert status == 200


def test_api_route_denies_without_token(running_server):
    status, body = _get(running_server + "/api/course/000000000000")
    assert status == 401
    assert json.loads(body)["error"] == "unauthorized"


def test_api_route_denies_wrong_token(running_server):
    status, _ = _get(running_server + "/api/course/000000000000", token="wrong-token")
    assert status == 401


def test_api_route_accepts_bearer_header(running_server):
    # Unknown session still 400s past auth — proves the auth check ran and passed.
    status, body = _get(running_server + "/api/course/000000000000", token=TOKEN)
    assert status == 400
    assert "Unknown session" in json.loads(body).get("error", "")


def test_course_iframe_route_accepts_query_token(running_server):
    # Iframe navigations can't set an Authorization header, so /course/* must accept ?token=.
    status, body = _get(running_server + "/api/course/000000000000", token=TOKEN, as_header=False)
    assert status == 400
    assert "Unknown session" in json.loads(body).get("error", "")


def test_missing_token_fails_closed_even_with_no_env_configured(monkeypatch, tmp_path):
    monkeypatch.delenv("EDITOR_API_TOKEN", raising=False)
    monkeypatch.delenv("EDITOR_API_TOKEN_FILE", raising=False)
    monkeypatch.delenv("EDITOR_ALLOW_INSECURE_DEV", raising=False)
    monkeypatch.setenv("EDITOR_WORKSPACE_DIR", str(tmp_path / "workspaces"))

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        status, body = _get(f"http://127.0.0.1:{port}/api/course/000000000000")
        assert status == 401
        assert "EDITOR_API_TOKEN is not configured" in json.loads(body)["message"]
    finally:
        httpd.shutdown()
        thread.join(timeout=5)


def test_server_side_authoring_disabled_by_default():
    from apps.scorm_editor.server import _default_module_generator

    os.environ.pop("EDITOR_ALLOW_SERVER_AUTHORING", None)
    with pytest.raises(PermissionError, match="disabled by default"):
        _default_module_generator({"course_title": "x"}, {"title": "m"}, [])


def _post(url: str, token: str, payload: dict):
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def _put(url: str, token: str, payload: dict):
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="PUT",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def _import(base_url: str, token: str = TOKEN) -> dict:
    zip_b64 = base64.b64encode(_minimal_scorm_zip()).decode("ascii")
    status, body = _post(base_url + "/api/import", token, {"zip": zip_b64})
    assert status == 200, body
    return body


class TestScopedOpenToken:
    """HTTP-level coverage of the session-scoped open_token minted by import_package
    (see apps/scorm_editor/server.py _route_session_id / _check_open_token). This is a
    SECOND accepted credential form -- the standing EDITOR_API_TOKEN must keep working
    unchanged throughout (asserted directly in each test below)."""

    def test_scoped_token_authenticates_its_own_session(self, running_server):
        imported = _import(running_server)
        sid = imported["session"]
        open_token = imported["open_token"]
        assert open_token and open_token != TOKEN

        status, body = _get(running_server + f"/api/course/{sid}", token=open_token)
        assert status == 200
        assert json.loads(body)["session"] == sid

        status, body = _put(
            running_server + f"/api/course/{sid}",
            open_token,
            {"course": {"course_title": "Edited", "modules": []}, "actor": "reviewer"},
        )
        assert status == 200, body
        assert body["ok"] is True

    def test_scoped_token_does_not_authenticate_a_different_session(self, running_server):
        imported_a = _import(running_server)
        imported_b = _import(running_server)
        sid_b = imported_b["session"]
        token_a = imported_a["open_token"]

        status, body = _get(running_server + f"/api/course/{sid_b}", token=token_a)
        assert status == 401
        assert json.loads(body)["error"] == "unauthorized"

    def test_scoped_token_does_not_authenticate_new_or_import_routes(self, running_server):
        imported = _import(running_server)
        open_token = imported["open_token"]

        status, body = _post(running_server + "/api/new", open_token, {"title": "Another course"})
        assert status == 401
        assert body["error"] == "unauthorized"

        status, body = _post(running_server + "/api/import", open_token, {"zip": ""})
        assert status == 401
        assert body["error"] == "unauthorized"

    def test_scoped_token_expires_after_ttl(self, monkeypatch, running_server):
        # EDITOR_OPEN_TOKEN_TTL_SECONDS is read once at module import time into a module
        # constant, so patch the constant directly rather than relying on env re-evaluation.
        import apps.scorm_editor.server as server_module

        monkeypatch.setattr(server_module, "EDITOR_OPEN_TOKEN_TTL_SECONDS", 1)

        imported = _import(running_server)
        sid = imported["session"]
        open_token = imported["open_token"]

        status, _ = _get(running_server + f"/api/course/{sid}", token=open_token)
        assert status == 200

        time.sleep(1.2)

        status, body = _get(running_server + f"/api/course/{sid}", token=open_token)
        assert status == 401
        assert json.loads(body)["error"] == "unauthorized"

    def test_standing_token_still_works_alongside_scoped_tokens(self, running_server):
        imported = _import(running_server)
        sid = imported["session"]

        status, body = _get(running_server + f"/api/course/{sid}", token=TOKEN)
        assert status == 200
        assert json.loads(body)["session"] == sid


def _real_pdf_base64(page_texts) -> str:
    from io import BytesIO

    from reportlab.pdfgen import canvas

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)
    for text in page_texts:
        pdf.drawString(72, 720, text)
        pdf.showPage()
    pdf.save()
    return base64.b64encode(buffer.getvalue()).decode("ascii")


class TestSourceUploadRoute:
    """HTTP-level coverage of POST /api/sources/<sid>/upload (docs/authoring-platform-plan.md
    3.4 -- dropping a PDF/DOCX/PPTX creates a real, page-anchored source instead of inert
    media). Distinct from the pre-existing text-only POST /api/sources/<sid>."""

    def test_upload_route_denies_without_token(self, running_server):
        imported = _import(running_server)
        sid = imported["session"]
        status, body = _post(running_server + f"/api/sources/{sid}/upload", "", {"filename": "a.pdf", "content_base64": ""})
        assert status == 401
        assert body["error"] == "unauthorized"

    def test_upload_route_accepts_scoped_open_token_for_its_own_session(self, running_server):
        imported = _import(running_server)
        sid = imported["session"]
        open_token = imported["open_token"]
        payload_b64 = _real_pdf_base64(["Verify the account owner before any change."])

        status, body = _post(
            running_server + f"/api/sources/{sid}/upload",
            open_token,
            {"filename": "handbook.pdf", "content_base64": payload_b64},
        )
        assert status == 201, body
        assert body["ok"] is True
        assert body["source"]["references"] == ["page:1"]

    def test_upload_route_extracts_real_pdf_text_and_page_references(self, running_server):
        imported = _import(running_server)
        sid = imported["session"]
        payload_b64 = _real_pdf_base64(["Always verify the account owner first.", "Escalate disputes to a lead."])

        status, body = _post(
            running_server + f"/api/sources/{sid}/upload",
            TOKEN,
            {"filename": "Customer Handbook.pdf", "content_base64": payload_b64},
        )
        assert status == 201, body
        source = body["source"]
        assert source["title"] == "Customer Handbook"
        assert source["references"] == ["page:1", "page:2"]
        assert "text" not in source  # public record never returns full source text over the list/upload APIs

        status, body = _get(running_server + f"/api/sources/{sid}", token=TOKEN)
        assert status == 200
        listed = json.loads(body)["sources"]
        assert any(item["source_id"] == source["source_id"] and item["references"] == ["page:1", "page:2"] for item in listed)

    def test_upload_route_rejects_unsupported_extension(self, running_server):
        imported = _import(running_server)
        sid = imported["session"]
        payload_b64 = base64.b64encode(b"plain text notes").decode("ascii")

        status, body = _post(
            running_server + f"/api/sources/{sid}/upload",
            TOKEN,
            {"filename": "notes.txt", "content_base64": payload_b64},
        )
        assert status == 400
        assert "Unsupported source file type" in body["error"]

    def test_upload_route_rejects_extraction_failure_cleanly(self, running_server):
        imported = _import(running_server)
        sid = imported["session"]
        payload_b64 = base64.b64encode(b"not a real docx zip file at all").decode("ascii")

        status, body = _post(
            running_server + f"/api/sources/{sid}/upload",
            TOKEN,
            {"filename": "broken.docx", "content_base64": payload_b64},
        )
        assert status == 400
        assert "Could not extract text from" in body["error"]

    def test_upload_route_enforces_size_limit(self, monkeypatch, running_server):
        import apps.scorm_editor.server as server_module

        imported = _import(running_server)
        sid = imported["session"]
        monkeypatch.setattr(server_module, "MAX_UPLOAD_BYTES", 100)
        payload_b64 = base64.b64encode(b"x" * 200).decode("ascii")

        status, body = _post(
            running_server + f"/api/sources/{sid}/upload",
            TOKEN,
            {"filename": "big.pdf", "content_base64": payload_b64},
        )
        assert status == 400
        assert "too large" in body["error"].lower()

    def test_existing_text_paste_route_still_works_unchanged(self, running_server):
        imported = _import(running_server)
        sid = imported["session"]

        status, body = _post(
            running_server + f"/api/sources/{sid}",
            TOKEN,
            {"title": "Pasted notes", "text": "Pasted text with no page anchors at all here."},
        )
        assert status == 201, body
        assert "references" not in body["source"]
