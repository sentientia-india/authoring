from course_mcp_server.security import RequestContext, read_secret, redact_output, validate_token
from course_mcp_server.tools import create_course_project


def test_redacts_common_secret_patterns():
    payload = {"message": "api_key=abc123 token:secretvalue sk-abcdefghijklmnop"}
    redacted = redact_output(payload)
    assert "abc123" not in redacted["message"]
    assert "secretvalue" not in redacted["message"]
    assert "sk-abcdefghijklmnop" not in redacted["message"]


def test_create_project_safe_shape(tmp_path, monkeypatch):
    monkeypatch.setenv("COURSE_PROJECT_STORE_PATH", str(tmp_path / "projects.json"))
    context = RequestContext(tenant_id="t1", user_id="u1", token="x")
    result = create_course_project(
        {
            "course_title": "Airline safety onboarding",
            "audience": "cabin crew",
        },
        context,
    )
    assert result["ok"] is True
    assert result["data"]["course_title"] == "Airline safety onboarding"
    assert result["audit"]["tool_name"] == "create_course_project"


def test_secret_file_is_supported_for_mcp_token(tmp_path, monkeypatch):
    secret_file = tmp_path / "mcp_token"
    secret_file.write_text("from-file\n", encoding="utf-8")
    monkeypatch.delenv("MCP_API_TOKEN", raising=False)
    monkeypatch.setenv("MCP_API_TOKEN_FILE", str(secret_file))

    assert read_secret("MCP_API_TOKEN") == "from-file"
    validate_token("from-file")
