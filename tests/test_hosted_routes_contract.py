from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_hosted_selling_routes_are_rest_only_and_authenticated_where_required():
    server = (ROOT / "src" / "course_mcp_server" / "server.py").read_text(encoding="utf-8")
    tools = (ROOT / "src" / "course_mcp_server" / "tools.py").read_text(encoding="utf-8")

    assert '"/api/hosted/releases"' in server
    assert '"/api/hosted/{token}/dashboard"' in server
    assert '"/api/hosted/{token}/entitlements"' in server
    assert '"/learn/{token}/lead"' in server
    assert "_context_from_request(request)" in server
    assert "publish_hosted_release" not in tools
    assert "grant_paid_access" not in tools
