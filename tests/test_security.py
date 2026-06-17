from course_mcp_server.security import RequestContext, redact_output
from course_mcp_server.tools import generate_course_outline


def test_redacts_common_secret_patterns():
    payload = {"message": "api_key=abc123 token:secretvalue sk-abcdefghijklmnop"}
    redacted = redact_output(payload)
    assert "abc123" not in redacted["message"]
    assert "secretvalue" not in redacted["message"]
    assert "sk-abcdefghijklmnop" not in redacted["message"]


def test_generate_outline_safe_shape():
    context = RequestContext(tenant_id="t1", user_id="u1", token="x")
    result = generate_course_outline(
        {
            "topic": "Airline safety onboarding",
            "audience": "cabin crew",
            "duration_minutes": 60,
            "difficulty": "beginner",
        },
        context,
    )
    assert result["ok"] is True
    assert "course_title" in result["data"]
    assert result["audit"]["tool_name"] == "generate_course_outline"
