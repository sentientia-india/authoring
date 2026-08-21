from course_mcp_server.text_providers.openrouter import OpenRouterTextProvider


def test_explicit_api_key_never_reads_env_var(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "env-key-must-not-be-used")

    captured = {}

    def fake_transport(request, _timeout):
        captured["headers"] = dict(request.header_items())
        return {"choices": [{"message": {"content": '{"ok":true}'}}]}

    provider = OpenRouterTextProvider(transport=fake_transport, api_key="explicit-key")

    result = provider.generate_json(
        system_prompt="Return JSON.",
        user_payload={"topic": "Ramp Safety"},
        schema_name="CourseOutline",
    )

    assert result == {"ok": True}
    assert captured["headers"]["Authorization"] == "Bearer explicit-key"
    assert provider.config.api_key == "explicit-key"
    assert provider.key_source == "request"


def test_no_explicit_api_key_falls_back_to_env(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "env-key")

    provider = OpenRouterTextProvider()

    assert provider.config.api_key == "env-key"
    assert provider.key_source == "env"
