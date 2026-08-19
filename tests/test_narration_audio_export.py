from __future__ import annotations

import json
from io import BytesIO
from zipfile import ZipFile

import pytest

from course_mcp_server import tools
from course_mcp_server.html_video_engine import VideoScene
from course_mcp_server.object_store import LocalObjectStore, ObjectStoreError, fetch_object_bytes, object_key
from course_mcp_server.security import RequestContext
from course_mcp_server.tools import (
    build_export_package,
    create_course_project,
    generate_assessment_bank,
    generate_course_blueprint,
    generate_lesson_pack,
    generate_narration_audio,
    ingest_course_source,
)
from course_mcp_server.video_providers import ElevenLabsConfig, ElevenLabsNarrationProvider


def _ctx() -> RequestContext:
    return RequestContext(tenant_id="tenant-a", user_id="user-a", token="token", request_id="req1")


def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("COURSE_PROJECT_STORE_PATH", str(tmp_path / "projects.json"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setenv("OBJECT_STORE_LOCAL_ROOT", str(tmp_path / "objects"))
    monkeypatch.delenv("OBJECT_STORE_BUCKET", raising=False)
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir(exist_ok=True)
    (upload_dir / "source.txt").write_text(
        "Ramp safety source text with procedures, cones, and controls.", encoding="utf-8"
    )
    monkeypatch.setenv("UPLOAD_DIR", str(upload_dir))


def _project_with_content(context: RequestContext) -> str:
    project = create_course_project(
        {"course_title": "Ramp Safety", "audience": "crew", "language": "English"},
        context,
    )
    project_id = project["data"]["project_id"]
    ingest_course_source(
        {"project_id": project_id, "upload_id": "source.txt", "source_type": "raw_text"},
        context,
    )
    generate_course_blueprint({"project_id": project_id, "duration_minutes": 20}, context)
    generate_lesson_pack({"project_id": project_id, "module_id": "module_1"}, context)
    generate_assessment_bank(
        {"project_id": project_id, "question_count": 4, "question_types": ["mcq", "matching"]},
        context,
    )
    return project_id


# ---------------------------------------------------------------------------
# object_store.get_bytes / fetch_object_bytes
# ---------------------------------------------------------------------------


def test_local_object_store_get_bytes_round_trips(tmp_path):
    store = LocalObjectStore(tmp_path)
    key = object_key(tenant_id="tenant-a", kind="narration_audio", object_id="video_1", filename="scene.mp3")
    store.put(key, BytesIO(b"fake-mp3-bytes"))

    assert store.get_bytes(key) == b"fake-mp3-bytes"


def test_local_object_store_get_bytes_missing_raises(tmp_path):
    store = LocalObjectStore(tmp_path)
    with pytest.raises(ObjectStoreError):
        store.get_bytes("tenants/tenant-a/narration_audio/video_1/missing.mp3")


def test_fetch_object_bytes_convenience_uses_local_backend(tmp_path, monkeypatch):
    monkeypatch.setenv("OBJECT_STORE_LOCAL_ROOT", str(tmp_path / "objects"))
    monkeypatch.delenv("OBJECT_STORE_BUCKET", raising=False)
    key = object_key(tenant_id="tenant-a", kind="narration_audio", object_id="video_1", filename="scene.mp3")
    LocalObjectStore(tmp_path / "objects").put(key, BytesIO(b"payload"))

    assert fetch_object_bytes(key) == b"payload"


class _FakeS3Client:
    def __init__(self):
        self.objects: dict[str, bytes] = {}

    def put_object(self, Bucket, Key, Body):  # noqa: N803 - mirrors boto3 signature
        self.objects[Key] = Body

    def get_object(self, Bucket, Key):  # noqa: N803
        return {"Body": BytesIO(self.objects[Key])}


def test_s3_object_store_get_bytes_round_trips(monkeypatch):
    from course_mcp_server.object_store import S3ObjectStore

    fake_client = _FakeS3Client()
    monkeypatch.setattr(S3ObjectStore, "__init__", lambda self, **kwargs: None)
    store = S3ObjectStore(bucket="test-bucket")
    store.bucket = "test-bucket"
    store.client = fake_client

    fake_client.put_object(Bucket="test-bucket", Key="tenants/tenant-a/narration_audio/video_1/scene.mp3", Body=b"s3-bytes")

    assert store.get_bytes("tenants/tenant-a/narration_audio/video_1/scene.mp3") == b"s3-bytes"


# ---------------------------------------------------------------------------
# html_video_engine.VideoScene narration_audio_src field
# ---------------------------------------------------------------------------


def _base_scene_kwargs() -> dict:
    return {
        "id": "scene_intro",
        "type": "title",
        "title": "Intro scene",
        "duration_seconds": 8,
        "narration": "Welcome to the course.",
        "visual_prompt": "Clean title card.",
    }


def test_video_scene_narration_audio_src_defaults_to_none():
    scene = VideoScene(**_base_scene_kwargs())
    assert scene.narration_audio_src is None
    assert scene.model_dump(mode="json")["narration_audio_src"] is None


def test_video_scene_narration_audio_src_accepts_value():
    scene = VideoScene(**_base_scene_kwargs(), narration_audio_src="audio/scene_intro.mp3")
    assert scene.narration_audio_src == "audio/scene_intro.mp3"
    assert scene.model_dump(mode="json")["narration_audio_src"] == "audio/scene_intro.mp3"


# ---------------------------------------------------------------------------
# End-to-end: narration audio actually lands in the exported SCORM zip.
# ---------------------------------------------------------------------------


def test_export_with_narration_audio_bundles_real_audio_into_zip(tmp_path, monkeypatch):
    _env(tmp_path, monkeypatch)
    context = _ctx()
    project_id = _project_with_content(context)

    fake_mp3 = b"ID3fake-mp3-bytes-for-export-testing"

    def fake_transport(request, timeout):
        return fake_mp3

    fake_provider = ElevenLabsNarrationProvider(config=ElevenLabsConfig(api_key="test-key"), transport=fake_transport)
    monkeypatch.setattr(tools, "ElevenLabsNarrationProvider", lambda: fake_provider)

    narration_result = generate_narration_audio({"project_id": project_id}, context)
    assert narration_result["ok"] is True
    assert narration_result["data"]["status"] == "completed"
    completed_scene_ids = [scene["scene_id"] for scene in narration_result["data"]["scenes"]]
    assert completed_scene_ids

    export_result = build_export_package({"project_id": project_id, "export_format": "scorm"}, context)
    assert export_result["ok"] is True
    package_path = export_result["data"]["package_path"]

    with ZipFile(package_path) as package:
        names = set(package.namelist())

        for scene_id in completed_scene_ids:
            audio_name = f"interactive-video/audio/{scene_id}.mp3"
            assert audio_name in names
            assert package.read(audio_name) == fake_mp3

        manifest_text = package.read("imsmanifest.xml").decode("utf-8")
        for scene_id in completed_scene_ids:
            assert f"interactive-video/audio/{scene_id}.mp3" in manifest_text

        index_html = package.read("interactive-video/index.html").decode("utf-8")
        for scene_id in completed_scene_ids:
            assert f'src="audio/{scene_id}.mp3"' in index_html
            assert f'id="sv-narration-{scene_id}"' in index_html
            assert "<audio" in index_html

        video_project_json = json.loads(package.read("interactive-video/video_project.json").decode("utf-8"))
        scenes_by_id = {scene["id"]: scene for scene in video_project_json["scenes"]}
        for scene_id in completed_scene_ids:
            assert scenes_by_id[scene_id]["narration_audio_src"] == f"audio/{scene_id}.mp3"


def test_export_without_narration_audio_artifact_is_unaffected(tmp_path, monkeypatch):
    """The common case today: no narration_audio artifact at all. Export must proceed exactly
    as before -- no audio directory, no audio references anywhere in the package."""
    _env(tmp_path, monkeypatch)
    context = _ctx()
    project_id = _project_with_content(context)

    export_result = build_export_package({"project_id": project_id, "export_format": "scorm"}, context)
    assert export_result["ok"] is True
    package_path = export_result["data"]["package_path"]

    with ZipFile(package_path) as package:
        names = package.namelist()
        assert not any(name.startswith("interactive-video/audio/") for name in names)

        index_html = package.read("interactive-video/index.html").decode("utf-8")
        assert "<audio" not in index_html

        video_project_json = json.loads(package.read("interactive-video/video_project.json").decode("utf-8"))
        for scene in video_project_json["scenes"]:
            assert scene.get("narration_audio_src") is None
