import json
import logging
from pathlib import Path

from course_mcp_server.observability import increment, prometheus_metrics, structured_log


def test_metrics_render_prometheus_counters_and_dependency_state():
    increment("course_mcp_test_total", tool="safe", outcome="success")
    metrics = prometheus_metrics()
    assert "course_mcp_uptime_seconds" in metrics
    assert 'course_mcp_test_total{outcome="success",tool="safe"}' in metrics
    assert 'course_mcp_dependency_ready{dependency="database"}' in metrics


def test_structured_logs_redact_blocked_fields(caplog):
    with caplog.at_level(logging.INFO, logger="course_mcp"):
        structured_log(logging.INFO, "request", request_id="r1", token="secret", password="secret")
    payload = json.loads(caplog.records[-1].message)
    assert payload == {"event": "request", "request_id": "r1"}


def test_public_proxy_exposes_status_and_authenticated_product_apis():
    caddy = (Path(__file__).resolve().parents[1] / "Caddyfile").read_text(encoding="utf-8")
    assert "handle /status" in caddy
    assert "handle /api/*" in caddy
    assert "handle /email/*" in caddy
