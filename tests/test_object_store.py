from io import BytesIO

import pytest

from course_mcp_server.object_store import LocalObjectStore, ObjectStoreError, object_key, object_store


def test_local_object_store_uses_tenant_key_and_integrity_digest(tmp_path):
    key = object_key(tenant_id="tenant-a", kind="exports", object_id="artifact_1", filename="course.zip")
    result = LocalObjectStore(tmp_path).put(key, BytesIO(b"course"))

    assert key == "tenants/tenant-a/exports/artifact_1/course.zip"
    assert result["size_bytes"] == 6
    assert len(result["sha256"]) == 64
    assert (tmp_path / key).read_bytes() == b"course"


@pytest.mark.parametrize("filename", ("../secret", "/absolute", "nested/file.zip", "..\\secret"))
def test_object_key_rejects_unsafe_filenames(filename):
    with pytest.raises(ObjectStoreError):
        object_key(tenant_id="tenant-a", kind="exports", object_id="artifact_1", filename=filename)


def test_production_requires_external_object_store(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("OBJECT_STORE_BUCKET", raising=False)
    with pytest.raises(ObjectStoreError, match="OBJECT_STORE_BUCKET"):
        object_store()
