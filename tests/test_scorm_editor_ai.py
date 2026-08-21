"""HTTP-level tests for Course Studio's AI transport route (P5-3): POST /api/ai/<sid>/generate.

Mirrors tests/test_scorm_editor_auth.py's pattern of driving the real ThreadingHTTPServer over a
socket, so these tests exercise the actual Handler.do_POST() route dispatch, _require_auth(), and
error translation -- not just the internal generate_ai_content() function in isolation.
"""

from __future__ import annotations

import base64
import json
import threading
import urllib.error
import urllib.request
import zipfile
from http.server import ThreadingHTTPServer
from io import BytesIO

import pytest

import apps.scorm_editor.server as server_module
from apps.scorm_editor.server import Handler, generate_ai_content, workspace_root

TOKEN = "test-editor-token-ai"


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

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        httpd.shutdown()
        thread.join(timeout=5)


def _post(url: str, token: str | None, payload: dict):
    body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
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


class _FakeProvider:
    def __init__(self, payload: dict | None = None, error: Exception | None = None) -> None:
        self._payload = payload
        self._error = error
        self.calls: list[dict] = []

    def generate_json(self, system_prompt, user_payload, schema_name, *, model=None):
        self.calls.append(
            {"system_prompt": system_prompt, "user_payload": user_payload, "schema_name": schema_name, "model": model}
        )
        if self._error is not None:
            raise self._error
        return self._payload


def test_route_denies_without_token(running_server):
    status, body = _post(running_server + "/api/ai/000000000000/generate", None, {})
    assert status == 401
    assert body["error"] == "unauthorized"


def test_route_accepts_session_scoped_open_token(running_server, monkeypatch):
    imported = _import(running_server)
    sid = imported["session"]
    open_token = imported["open_token"]
    fake = _FakeProvider(payload={"title": "Hello"})
    monkeypatch.setattr(
        server_module,
        "_text_provider_factory",
        lambda provider_id, *, api_key, base_url, model: fake,
    )

    status, body = _post(
        running_server + f"/api/ai/{sid}/generate",
        open_token,
        {"system_prompt": "sp", "user_payload": {"x": 1}, "schema_name": "Thing"},
    )
    assert status == 200, body
    assert body == {"ok": True, "provider": "openrouter", "result": {"title": "Hello"}}
    assert fake.calls == [{"system_prompt": "sp", "user_payload": {"x": 1}, "schema_name": "Thing", "model": None}]


def test_route_returns_mocked_transport_success_with_standing_token(running_server, monkeypatch):
    imported = _import(running_server)
    sid = imported["session"]
    fake = _FakeProvider(payload={"lessons": []})
    captured = {}

    def factory(provider_id, *, api_key, base_url, model):
        captured.update({"provider_id": provider_id, "api_key": api_key, "base_url": base_url, "model": model})
        return fake

    monkeypatch.setattr(server_module, "_text_provider_factory", factory)

    status, body = _post(
        running_server + f"/api/ai/{sid}/generate",
        TOKEN,
        {
            "system_prompt": "Rewrite this block",
            "user_payload": {"block": "text"},
            "schema_name": "RewriteBlock",
            "text_provider": "anthropic",
            "text_provider_api_key": "sk-user-supplied",
            "text_provider_model": "claude-x",
        },
    )
    assert status == 200, body
    assert body["ok"] is True
    assert body["provider"] == "anthropic"
    assert body["result"] == {"lessons": []}
    assert captured == {
        "provider_id": "anthropic",
        "api_key": "sk-user-supplied",
        "base_url": None,
        "model": "claude-x",
    }
    # The BYO key must never be echoed back in the response.
    assert "sk-user-supplied" not in json.dumps(body)


def test_route_translates_text_provider_error_to_clean_400(running_server, monkeypatch):
    imported = _import(running_server)
    sid = imported["session"]
    from course_mcp_server.text_providers.base import TextProviderError

    fake = _FakeProvider(error=TextProviderError("upstream provider rejected the request"))
    monkeypatch.setattr(server_module, "_text_provider_factory", lambda *a, **k: fake)

    status, body = _post(
        running_server + f"/api/ai/{sid}/generate",
        TOKEN,
        {"system_prompt": "sp", "user_payload": {}, "schema_name": "Thing"},
    )
    assert status == 400
    assert body["ok"] is False
    assert body["error"] == "upstream provider rejected the request"
    # No stack trace / exception type name leaked into the response.
    assert "Traceback" not in json.dumps(body)
    assert "TextProviderError" not in json.dumps(body)


def test_route_redacts_secret_shaped_text_in_a_provider_error(running_server, monkeypatch):
    """Defense-in-depth: even though no current adapter is known to embed a raw secret in its
    error text, do_POST's catch-all exception handler must run every error message through
    course_mcp_server.security.redact_text before it reaches the browser -- mirroring the
    MCP-side audit path. Forces a fake provider to raise an error containing both an sk-prefixed
    API key and a `?key=` query-string credential, then asserts the ACTUAL HTTP response body
    (not a direct function call) has them redacted."""
    imported = _import(running_server)
    sid = imported["session"]
    from course_mcp_server.text_providers.base import TextProviderError

    leaked = (
        "upstream call failed: Authorization: Bearer sk-abcdefghijklmnopqrstuvwx "
        "and https://example.com/v1/generate?key=AIzaSyDABCDEFGHIJKLMNOPQRSTUVWXYZ012 rejected"
    )
    fake = _FakeProvider(error=TextProviderError(leaked))
    monkeypatch.setattr(server_module, "_text_provider_factory", lambda *a, **k: fake)

    status, body = _post(
        running_server + f"/api/ai/{sid}/generate",
        TOKEN,
        {"system_prompt": "sp", "user_payload": {}, "schema_name": "Thing"},
    )
    assert status == 400
    assert body["ok"] is False
    raw_response = json.dumps(body)
    assert "sk-abcdefghijklmnopqrstuvwx" not in raw_response
    assert "AIzaSyDABCDEFGHIJKLMNOPQRSTUVWXYZ012" not in raw_response
    assert "[REDACTED]" in body["error"]


def test_route_rejects_unknown_provider_cleanly(running_server):
    imported = _import(running_server)
    sid = imported["session"]

    status, body = _post(
        running_server + f"/api/ai/{sid}/generate",
        TOKEN,
        {"system_prompt": "sp", "user_payload": {}, "schema_name": "Thing", "text_provider": "not-a-provider"},
    )
    assert status == 400
    assert "Unknown text provider_id" in body["error"]


def test_route_rejects_missing_required_fields(running_server):
    imported = _import(running_server)
    sid = imported["session"]

    status, body = _post(running_server + f"/api/ai/{sid}/generate", TOKEN, {"system_prompt": "", "schema_name": "X"})
    assert status == 400
    assert "system_prompt" in body["error"]


def test_route_unknown_session_returns_clean_400_not_500(running_server):
    status, body = _post(
        running_server + "/api/ai/000000000000/generate",
        TOKEN,
        {"system_prompt": "sp", "user_payload": {}, "schema_name": "Thing"},
    )
    assert status == 400
    assert "Unknown session" in body["error"]


def test_scoped_open_token_does_not_authenticate_a_different_sessions_ai_route(running_server):
    imported_a = _import(running_server)
    imported_b = _import(running_server)
    sid_b = imported_b["session"]
    token_a = imported_a["open_token"]

    status, body = _post(
        running_server + f"/api/ai/{sid_b}/generate",
        token_a,
        {"system_prompt": "sp", "user_payload": {}, "schema_name": "Thing"},
    )
    assert status == 401
    assert body["error"] == "unauthorized"


def test_generate_ai_content_function_directly_never_persists_the_key(monkeypatch, tmp_path):
    monkeypatch.setenv("EDITOR_WORKSPACE_DIR", str(tmp_path / "workspaces"))
    workspace_root()
    from apps.scorm_editor.server import import_package

    imported = import_package(_minimal_scorm_zip())
    sid = imported["session"]
    fake = _FakeProvider(payload={"ok": True})
    monkeypatch.setattr(server_module, "_text_provider_factory", lambda *a, **k: fake)

    result = generate_ai_content(
        sid,
        {
            "system_prompt": "sp",
            "user_payload": {},
            "schema_name": "Thing",
            "text_provider_api_key": "super-secret-key",
        },
    )
    assert result == {"provider": "openrouter", "result": {"ok": True}}

    workspace = workspace_root() / sid
    for path in workspace.rglob("*"):
        if path.is_file():
            assert "super-secret-key" not in path.read_text(encoding="utf-8", errors="ignore")


# ---------------------------------------------------------------------------
# P5-3c: server-side schema-validation gate for schema_name == "quiz_from_content". The route
# must reject a model response that doesn't validate against the real
# course_mcp_server.schemas.QuizBank/QuizQuestion Pydantic models with a clean 400 (never a raw
# pydantic.ValidationError/stack trace), and must accept and pass through a genuinely valid one.

_VALID_QUIZ_QUESTION = {
    "id": "q1",
    "type": "mcq",
    "difficulty": "beginner",
    "objective": "Recall the widget-socket relationship.",
    "question": "How do widgets connect to gadgets?",
    "options": ["Via a socket", "Via glue", "Via magnets"],
    "answer": "Via a socket",
    "explanation": "The text says widgets connect via a socket.",
}


def test_quiz_from_content_accepts_a_genuinely_valid_quiz_response(running_server, monkeypatch):
    imported = _import(running_server)
    sid = imported["session"]
    payload = {"course_title": "T", "questions": [_VALID_QUIZ_QUESTION]}
    fake = _FakeProvider(payload=payload)
    monkeypatch.setattr(server_module, "_text_provider_factory", lambda *a, **k: fake)

    status, body = _post(
        running_server + f"/api/ai/{sid}/generate",
        TOKEN,
        {"system_prompt": "sp", "user_payload": {"content": "x"}, "schema_name": "quiz_from_content"},
    )
    assert status == 200, body
    assert body["ok"] is True
    assert body["result"]["questions"][0]["id"] == "q1"
    assert body["result"]["questions"][0]["answer"] == "Via a socket"


def test_quiz_from_content_rejects_a_question_missing_required_fields(running_server, monkeypatch):
    imported = _import(running_server)
    sid = imported["session"]
    # Missing "explanation" and "difficulty" -- required fields on QuizQuestion.
    malformed_question = {
        "id": "q1",
        "type": "mcq",
        "objective": "x",
        "question": "Q?",
        "options": ["A", "B"],
        "answer": "A",
    }
    payload = {"course_title": "T", "questions": [malformed_question]}
    fake = _FakeProvider(payload=payload)
    monkeypatch.setattr(server_module, "_text_provider_factory", lambda *a, **k: fake)

    status, body = _post(
        running_server + f"/api/ai/{sid}/generate",
        TOKEN,
        {"system_prompt": "sp", "user_payload": {"content": "x"}, "schema_name": "quiz_from_content"},
    )
    assert status == 400
    assert body["ok"] is False
    assert "required schema" in body["error"]
    assert "Traceback" not in json.dumps(body)
    assert "ValidationError" not in json.dumps(body)


def test_quiz_from_content_rejects_a_question_with_zero_correct_answers(running_server, monkeypatch):
    """A question whose `answer` is not one of its own `options` has zero correct answers among
    the choices offered -- Pydantic's field types alone can't express this cross-field
    constraint, so generate_ai_content() must check it explicitly (see
    _validate_ai_result_schema()'s docstring) and reject cleanly rather than silently accepting
    an unanswerable question."""
    imported = _import(running_server)
    sid = imported["session"]
    malformed_question = dict(_VALID_QUIZ_QUESTION, answer="Not one of the options")
    payload = {"course_title": "T", "questions": [malformed_question]}
    fake = _FakeProvider(payload=payload)
    monkeypatch.setattr(server_module, "_text_provider_factory", lambda *a, **k: fake)

    status, body = _post(
        running_server + f"/api/ai/{sid}/generate",
        TOKEN,
        {"system_prompt": "sp", "user_payload": {"content": "x"}, "schema_name": "quiz_from_content"},
    )
    assert status == 400
    assert body["ok"] is False
    assert "not one of its own options" in body["error"]


def test_quiz_from_content_rejects_a_non_object_response(running_server, monkeypatch):
    imported = _import(running_server)
    sid = imported["session"]
    fake = _FakeProvider(payload=["not", "an", "object"])
    monkeypatch.setattr(server_module, "_text_provider_factory", lambda *a, **k: fake)

    status, body = _post(
        running_server + f"/api/ai/{sid}/generate",
        TOKEN,
        {"system_prompt": "sp", "user_payload": {"content": "x"}, "schema_name": "quiz_from_content"},
    )
    assert status == 400
    assert body["ok"] is False
    assert "required schema" in body["error"]


def test_other_schema_names_are_not_gated_by_quiz_validation(running_server, monkeypatch):
    """schema_name values other than "quiz_from_content" (e.g. P5-3b's "content_block_rewrite")
    must pass through _validate_ai_result_schema() unchanged -- confirms the gate is scoped to
    exactly the one schema_name that needs it, not applied globally."""
    imported = _import(running_server)
    sid = imported["session"]
    fake = _FakeProvider(payload={"text": "not a quiz at all"})
    monkeypatch.setattr(server_module, "_text_provider_factory", lambda *a, **k: fake)

    status, body = _post(
        running_server + f"/api/ai/{sid}/generate",
        TOKEN,
        {"system_prompt": "sp", "user_payload": {"text": "x"}, "schema_name": "content_block_rewrite"},
    )
    assert status == 200, body
    assert body["result"] == {"text": "not a quiz at all"}


def test_validate_ai_result_schema_dispatch_table_covers_known_and_unknown_names():
    """Unit-level proof that _validate_ai_result_schema()'s dispatch table -- not a leftover
    if-chain -- is what drives this gate: a schema_name present in the table (here,
    "quiz_from_content") still validates and returns the model_dump()'d result, while a
    schema_name absent from the table returns the input completely unchanged (the same
    pass-through behavior asserted at the HTTP layer above), confirming the dispatch mechanism
    itself works for both known and unknown names."""
    valid_quiz = {"course_title": "Widgets 101", "questions": [_VALID_QUIZ_QUESTION]}
    validated = server_module._validate_ai_result_schema("quiz_from_content", valid_quiz)
    assert validated["questions"][0]["answer"] == "Via a socket"

    sentinel = {"anything": "goes", "not": ["a", "registered", "schema"]}
    passthrough = server_module._validate_ai_result_schema("some_unregistered_schema_name", sentinel)
    assert passthrough is sentinel


# P5-3f: server-side schema-validation gate for schema_name == "branching_scenario_from_premise".
# The route must reject a model response that doesn't validate against the real
# course_mcp_server.schemas.BranchingScenario Pydantic model -- INCLUDING a response that is
# field-shape valid but graph-invalid (duplicate node id, or a choice's next_node_id dangling to a
# node id outside the response's own nodes) -- with a clean 400 (never a raw
# pydantic.ValidationError/stack trace), and must accept and pass through a genuinely valid
# multi-node tree.

_VALID_BRANCHING_SCENARIO = {
    "title": "Angry customer call",
    "persona": {"name": "Jordan", "role": "Customer"},
    "items": [
        {
            "id": "node_1",
            "scenario": "Jordan calls in furious about a billing error.",
            "choices": [
                {"label": "Apologize and investigate", "result": "best", "feedback": "Great start.", "next_node_id": "node_2"},
                {"label": "Argue with Jordan", "result": "risk", "feedback": "This escalates the call.", "next_node_id": None},
            ],
        },
        {
            "id": "node_2",
            "scenario": "You confirm the billing error and offer a refund.",
            "choices": [
                {"label": "Offer a full refund", "result": "best", "feedback": "Jordan is satisfied.", "next_node_id": None},
                {"label": "Offer nothing", "result": "risk", "feedback": "Jordan hangs up angry.", "next_node_id": None},
            ],
        },
    ],
}


def test_branching_scenario_from_premise_accepts_a_genuinely_valid_tree(running_server, monkeypatch):
    imported = _import(running_server)
    sid = imported["session"]
    fake = _FakeProvider(payload=_VALID_BRANCHING_SCENARIO)
    monkeypatch.setattr(server_module, "_text_provider_factory", lambda *a, **k: fake)

    status, body = _post(
        running_server + f"/api/ai/{sid}/generate",
        TOKEN,
        {"system_prompt": "sp", "user_payload": {"premise": "x"}, "schema_name": "branching_scenario_from_premise"},
    )
    assert status == 200, body
    assert body["ok"] is True
    items = body["result"]["items"]
    assert [node["id"] for node in items] == ["node_1", "node_2"]
    assert items[0]["choices"][0]["next_node_id"] == "node_2"


def test_branching_scenario_from_premise_rejects_a_dangling_next_node_id(running_server, monkeypatch):
    """Deliberately malformed graph: a choice's next_node_id points at a node id that is NOT
    present in the response's own `items` list. This must be rejected by BranchingScenario's own
    `_validate_graph` model_validator (reused via model_validate, not reimplemented here)."""
    imported = _import(running_server)
    sid = imported["session"]
    dangling_payload = json.loads(json.dumps(_VALID_BRANCHING_SCENARIO))
    dangling_payload["items"][0]["choices"][0]["next_node_id"] = "node_does_not_exist"
    fake = _FakeProvider(payload=dangling_payload)
    monkeypatch.setattr(server_module, "_text_provider_factory", lambda *a, **k: fake)

    status, body = _post(
        running_server + f"/api/ai/{sid}/generate",
        TOKEN,
        {"system_prompt": "sp", "user_payload": {"premise": "x"}, "schema_name": "branching_scenario_from_premise"},
    )
    assert status == 400
    assert body["ok"] is False
    assert "required schema" in body["error"]
    assert "Traceback" not in json.dumps(body)
    assert "ValidationError" not in json.dumps(body)


def test_branching_scenario_from_premise_rejects_a_duplicate_node_id(running_server, monkeypatch):
    """Deliberately malformed graph: two nodes share the same id. Must be rejected the same way as
    a dangling reference, via BranchingScenario's own graph-integrity check."""
    imported = _import(running_server)
    sid = imported["session"]
    duplicate_payload = json.loads(json.dumps(_VALID_BRANCHING_SCENARIO))
    duplicate_payload["items"][1]["id"] = "node_1"
    duplicate_payload["items"][0]["choices"][0]["next_node_id"] = None
    fake = _FakeProvider(payload=duplicate_payload)
    monkeypatch.setattr(server_module, "_text_provider_factory", lambda *a, **k: fake)

    status, body = _post(
        running_server + f"/api/ai/{sid}/generate",
        TOKEN,
        {"system_prompt": "sp", "user_payload": {"premise": "x"}, "schema_name": "branching_scenario_from_premise"},
    )
    assert status == 400
    assert body["ok"] is False
    assert "required schema" in body["error"]


def test_branching_scenario_from_premise_rejects_a_non_object_response(running_server, monkeypatch):
    imported = _import(running_server)
    sid = imported["session"]
    fake = _FakeProvider(payload=["not", "an", "object"])
    monkeypatch.setattr(server_module, "_text_provider_factory", lambda *a, **k: fake)

    status, body = _post(
        running_server + f"/api/ai/{sid}/generate",
        TOKEN,
        {"system_prompt": "sp", "user_payload": {"premise": "x"}, "schema_name": "branching_scenario_from_premise"},
    )
    assert status == 400
    assert body["ok"] is False
    assert "required schema" in body["error"]
