from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_analytics_routes_are_authenticated_tenant_scoped_and_exportable():
    server = (ROOT / "src" / "course_mcp_server" / "server.py").read_text(encoding="utf-8")
    assert '"/api/analytics/account"' in server
    assert '"/api/analytics/releases/{release_id}"' in server
    assert '"/api/analytics/schedules"' in server
    assert '"/api/analytics/learners/{learner_id}"' in server
    assert '"/api/analytics/quality"' in server
    assert '"/api/analytics/report-runs/{run_id}"' in server
    assert "context.tenant_id" in server
    assert 'media_type="text/csv"' in server
