from course_mcp_server.smoke import openrouter_smoke_status


def test_openrouter_smoke_skips_without_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    assert openrouter_smoke_status() == "openrouter skipped: OPENROUTER_API_KEY not set"

