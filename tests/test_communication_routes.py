from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_email_provider_webhook_requires_constant_time_secret_check():
    server = (ROOT / "src" / "course_mcp_server" / "server.py").read_text(encoding="utf-8")
    assert '"/email/provider-webhook"' in server
    assert "EMAIL_WEBHOOK_SECRET" in server
    assert "hmac.compare_digest" in server
    assert "record_provider_event" in server
