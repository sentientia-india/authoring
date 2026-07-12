from pathlib import Path

from scripts.load_test import run_load


ROOT = Path(__file__).resolve().parents[1]


def test_threat_model_covers_every_production_boundary_and_stop_ship_policy():
    model = (ROOT / "docs" / "security-threat-model.md").read_text(encoding="utf-8")
    for term in (
        "MCP/API",
        "Course Studio upload",
        "Hosted content",
        "PostgreSQL",
        "Redis/jobs",
        "Object storage",
        "Stripe",
        "Email",
        "Analytics",
        "CI/deploy",
        "Support",
        "Dependencies",
        "Stop-ship findings",
        "independent penetration test",
    ):
        assert term in model


def test_load_harness_reports_latency_and_errors(monkeypatch):
    monkeypatch.setattr("scripts.load_test.request_once", lambda _url, _timeout: (0.05, True))
    report = run_load(url="https://example.com/health", requests=20, concurrency=4, timeout=1)
    assert report["successes"] == 20
    assert report["error_rate"] == 0
    assert report["p95_seconds"] == 0.05
