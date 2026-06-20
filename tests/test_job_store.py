from course_mcp_server.job_store import record_job, reset_job_store
from course_mcp_server.security import RequestContext
from course_mcp_server.tools import get_course_generation_status


def test_record_job_recovers_from_corrupted_store(tmp_path, monkeypatch):
    store_path = tmp_path / "jobs.json"
    store_path.write_text("[]]\n", encoding="utf-8")
    monkeypatch.setenv("JOB_STORE_PATH", str(store_path))

    job = record_job(
        job_id="job_123456",
        tenant_id="tenant-a",
        user_id="user-a",
        tool_name="generate_course_blueprint",
        status="completed",
        message="Course outline generated.",
    )

    assert job["job_id"] == "job_123456"
    assert store_path.read_text(encoding="utf-8").startswith("[\n  {")


def test_status_returns_only_matching_tenant_job(tmp_path, monkeypatch):
    monkeypatch.setenv("JOB_STORE_PATH", str(tmp_path / "jobs.json"))
    reset_job_store()
    record_job(
        job_id="job_123456",
        tenant_id="tenant-a",
        user_id="user-a",
        tool_name="generate_course_blueprint",
        status="completed",
        message="Course outline generated.",
    )

    allowed = get_course_generation_status(
        {"job_id": "job_123456"},
        RequestContext(tenant_id="tenant-a", user_id="user-a", token="x"),
    )
    denied = get_course_generation_status(
        {"job_id": "job_123456"},
        RequestContext(tenant_id="tenant-b", user_id="user-b", token="x"),
    )

    assert allowed["data"]["status"] == "completed"
    assert allowed["data"]["tool_name"] == "generate_course_blueprint"
    assert denied["data"]["status"] == "not_found"
    assert "tenant-a" not in str(denied["data"])
