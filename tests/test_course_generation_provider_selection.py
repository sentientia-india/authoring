"""End-to-end coverage for P5-2: provider-selection + per-request BYO-key plumbing through
real course-plan (outline/blueprint) generation.

Exercises the actual call site (tools.generate_course_blueprint -> course_generator.generate_outline
-> text_providers.registry.get_text_provider), not just the registry/schema in isolation, and
proves the per-request API key never reaches disk.
"""

import json
from contextlib import contextmanager

from course_mcp_server.security import RequestContext
from course_mcp_server.tools import create_course_project, generate_course_blueprint


def _fake_urlopen_factory(captured: dict, content: str):
    """Build a urlopen replacement that captures the outgoing Request and returns `content`
    as the chat-completion message content, in the {"choices": [...]} shape every OpenAI-style
    adapter in text_providers/ expects.

    Patching the module-level `default_transport` (as done for OpenRouterTextProvider in
    test_openrouter_text_provider.py) does not work here because DeepSeekTextProvider /
    OpenAITextProvider / etc. bind `transport: Transport = default_transport` as a function
    default at import time -- reassigning the module attribute afterward does not change an
    already-constructed default. Patching `urlopen` itself (what the shared
    `text_providers.base.default_transport` calls) works regardless of when/how the provider
    was constructed, which matters here since these providers are built inside
    course_generator.py/registry.py, not directly by the test. All adapters share the same
    `default_transport` implementation (text_providers/base.py) now, so `urlopen` is patched
    there rather than on each individual adapter module.
    """

    @contextmanager
    def _fake_urlopen(request, timeout=None):  # noqa: ARG001 - timeout unused, matches urlopen signature
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["body"] = json.loads(request.data.decode("utf-8"))

        class _Response:
            def read(self_inner):
                return json.dumps({"choices": [{"message": {"content": content}}]}).encode("utf-8")

        yield _Response()

    return _fake_urlopen


def _ctx() -> RequestContext:
    return RequestContext(tenant_id="tenant-a", user_id="user-a", token="token", request_id="req1")


def _make_project(tmp_path, monkeypatch):
    monkeypatch.setenv("COURSE_PROJECT_STORE_PATH", str(tmp_path / "projects.json"))
    context = _ctx()
    project = create_course_project(
        {"course_title": "Ramp Safety", "audience": "ramp agents", "language": "English"},
        context,
    )
    return project["data"]["project_id"], context


def test_default_openrouter_path_uses_openrouter_request_shape(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "env-openrouter-key")
    project_id, context = _make_project(tmp_path, monkeypatch)

    captured = {}
    content = json.dumps(
        {
            "course_title": "Ramp Safety for ramp agents",
            "audience": "ramp agents",
            "difficulty": "beginner",
            "language": "English",
            "learning_objectives": ["Understand ramp safety basics."],
            "modules": [{"title": "Foundations", "lessons": []}],
            "assessment_plan": "MCQ quiz.",
        }
    )

    import course_mcp_server.text_providers.base as text_providers_base_module

    monkeypatch.setattr(text_providers_base_module, "urlopen", _fake_urlopen_factory(captured, content))

    blueprint = generate_course_blueprint({"project_id": project_id, "duration_minutes": 30}, context)

    assert blueprint["ok"] is True
    # OpenRouter's request shape: Bearer auth header, /chat/completions path.
    assert captured["headers"]["Authorization"] == "Bearer env-openrouter-key"
    assert "/chat/completions" in captured["url"]
    assert captured["body"]["messages"][0]["role"] == "system"
    assert blueprint["data"]["generation_provider"] == "openrouter"
    assert blueprint["data"]["generation_provider_error"] is None
    # The key that authenticated this call came from the environment, not the request.
    assert blueprint["data"]["generation_key_source"] == "env"

    # Persisted project JSON must never contain the OpenRouter key (or any BYO-key material).
    stored = json.loads((tmp_path / "projects.json").read_text(encoding="utf-8"))
    dumped = json.dumps(stored)
    assert "env-openrouter-key" not in dumped


def test_deepseek_with_request_api_key_override_and_no_leak_to_disk(tmp_path, monkeypatch):
    # Deliberately do NOT set DEEPSEEK_API_KEY in the environment -- the per-request key must be
    # the only thing that makes this call succeed, proving request_key genuinely overrides env.
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    # Make sure OpenRouter is not accidentally selected/enabled either.
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    project_id, context = _make_project(tmp_path, monkeypatch)

    secret_key = "sk-deepseek-super-secret-value"
    captured = {}
    content = json.dumps(
        {
            "course_title": "Ramp Safety for ramp agents",
            "audience": "ramp agents",
            "difficulty": "beginner",
            "language": "English",
            "learning_objectives": ["Understand ramp safety basics."],
            "modules": [{"title": "Foundations", "lessons": []}],
            "assessment_plan": "MCQ quiz.",
        }
    )

    import course_mcp_server.text_providers.base as text_providers_base_module

    monkeypatch.setattr(text_providers_base_module, "urlopen", _fake_urlopen_factory(captured, content))

    blueprint = generate_course_blueprint(
        {
            "project_id": project_id,
            "duration_minutes": 30,
            "text_provider": "deepseek",
            "text_provider_api_key": secret_key,
        },
        context,
    )

    assert blueprint["ok"] is True
    # DeepSeek's request shape: Bearer auth header, DeepSeek base_url/chat/completions path.
    assert captured["headers"]["Authorization"] == f"Bearer {secret_key}"
    assert "api.deepseek.com" in captured["url"]
    # The BYO-key/provider-routing fields must never reach the LLM's own user_payload.
    sent_payload = captured["body"]["messages"][1]["content"]
    assert "text_provider_api_key" not in sent_payload
    assert secret_key not in sent_payload

    # generation_provider on the resulting outline/blueprint reflects the REAL provider used.
    assert blueprint["data"]["generation_provider"] == "deepseek"
    assert blueprint["data"]["generation_provider_error"] is None
    # The key that authenticated this call was the per-request BYO key, not an env var.
    assert blueprint["data"]["generation_key_source"] == "request"

    # The per-request key must be genuinely absent from the persisted project JSON on disk --
    # read the file back (not the in-memory object) and assert its absence.
    stored_text = (tmp_path / "projects.json").read_text(encoding="utf-8")
    assert secret_key not in stored_text
    stored = json.loads(stored_text)
    for project in stored:
        assert "text_provider_api_key" not in json.dumps(project)
