from datetime import datetime

from course_mcp_server.delivery import build_delivery_metadata


def test_download_only_delivery_metadata_does_not_require_storage(monkeypatch):
    monkeypatch.setenv("EXPORT_DELIVERY_MODE", "download_only")
    monkeypatch.setenv("EXPORT_RETENTION_SECONDS", "3600")

    metadata = build_delivery_metadata(
        project_id="course_abc12345",
        artifact_type="scorm",
        package_path="/app/output/course.zip",
    )

    assert metadata["delivery_mode"] == "download_only"
    assert metadata["storage_required"] is False
    assert metadata["customer_action"] == "download_and_upload_to_lms"
    assert metadata["expires_at"]
    datetime.fromisoformat(metadata["expires_at"])
