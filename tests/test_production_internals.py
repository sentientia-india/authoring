from course_mcp_server.artifacts import store_artifact_metadata
from course_mcp_server.audit_store import list_audit_events, record_audit_event
from course_mcp_server.certificate_renderer import render_certificate_html
from course_mcp_server.generation_queue import enqueue_generation_job
from course_mcp_server.rate_limit import check_rate_limit
from course_mcp_server.storage import JsonStorageBackend


def test_json_storage_backend_persists_projects_jobs_and_audit(tmp_path):
    backend = JsonStorageBackend(tmp_path / "store.json")
    project = {"project_id": "course_abc12345", "tenant_id": "t1", "course_title": "Safety"}
    job = {"job_id": "job_1", "tenant_id": "t1", "status": "completed"}
    audit = {"tenant_id": "t1", "tool_name": "create_course_project"}

    backend.upsert_project(project)
    backend.upsert_job(job)
    backend.append_audit(audit)

    assert backend.get_project("t1", "course_abc12345")["course_title"] == "Safety"
    assert backend.get_job("t1", "job_1")["status"] == "completed"
    assert backend.list_audit("t1")[0]["tool_name"] == "create_course_project"


def test_rate_limit_blocks_after_configured_limit(tmp_path, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_STORE_PATH", str(tmp_path / "rate.json"))
    monkeypatch.setenv("RATE_LIMIT_REQUESTS", "2")
    monkeypatch.setenv("RATE_LIMIT_WINDOW_SECONDS", "60")

    assert check_rate_limit(tenant_id="t1", user_id="u1") is True
    assert check_rate_limit(tenant_id="t1", user_id="u1") is True
    assert check_rate_limit(tenant_id="t1", user_id="u1") is False


def test_audit_store_records_without_exposing_payload(tmp_path, monkeypatch):
    monkeypatch.setenv("AUDIT_STORE_PATH", str(tmp_path / "audit.json"))
    event = {"tenant_id": "t1", "tool_name": "build_export_package", "input_hash": "abc"}

    record_audit_event(event)

    assert list_audit_events("t1")[0]["input_hash"] == "abc"


def test_queue_fallback_runs_inline_without_redis(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)

    job = enqueue_generation_job(
        queue_name="generation",
        payload={"project_id": "course_abc12345", "task": "blueprint"},
    )

    assert job["status"] == "queued"
    assert job["backend"] == "inline"


def test_artifact_metadata_and_certificate_rendering(tmp_path):
    metadata = store_artifact_metadata(
        project_id="course_abc12345",
        artifact_type="certificate",
        package_path=str(tmp_path / "cert.html"),
    )
    html = render_certificate_html(
        {
            "certificate_id": "cert_123",
            "learner_name": "Learner One",
            "course_title": "Safety",
            "score": 92,
            "issued_date": "2026-06-17",
            "recertification_due_date": "2027-06-17",
        }
    )

    assert metadata["artifact_uri"].startswith("artifact://course_abc12345/")
    assert "Learner One" in html
    assert "cert_123" in html
