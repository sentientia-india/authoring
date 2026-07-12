from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from apps.scorm_editor.server import (
    EditConflictError,
    _build_zip,
    _import_package,
    collaboration_state,
    compare_revisions,
    create_course,
    export_package,
    get_revision,
    import_package,
    list_revisions,
    save_course,
    update_collaboration,
)


def _sample_zip_bytes() -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as package:
        package.writestr("imsmanifest.xml", """<?xml version="1.0" encoding="UTF-8"?>
<manifest identifier="demo" version="1.0"
  xmlns="http://www.imsproject.org/xsd/imscp_rootv1p1p2"
  xmlns:adlcp="http://www.adlnet.org/xsd/adlcp_rootv1p2">
  <organizations default="org1">
    <organization identifier="org1">
      <item identifier="item1" identifierref="res1">
        <title>Demo Course</title>
      </item>
    </organization>
  </organizations>
  <resources>
    <resource identifier="res1" type="webcontent" adlcp:scormtype="sco" href="index.html">
      <file href="index.html" />
      <file href="data/course.json" />
    </resource>
  </resources>
</manifest>
""")
        package.writestr(
            "data/course.json",
            """{"course_title":"Demo Course","course_slug":"demo-course","modules":[{"title":"A","lessons":[{"title":"L1"}]}]}""",
        )
        package.writestr("index.html", "<html><body>demo</body></html>")
    return buffer.getvalue()


def test_import_package_reads_manifest_and_course_json():
    payload = _import_package(_sample_zip_bytes())
    assert payload["manifest"]["course_title"] == "Demo Course"
    assert payload["course"]["course_title"] == "Demo Course"
    assert payload["course"]["modules"][0]["title"] == "A"


def test_build_zip_replaces_course_json_without_touching_manifest():
    rebuilt = _build_zip(
        _sample_zip_bytes(),
        {"course_title": "Demo Course", "course_slug": "demo-course", "modules": [{"title": "B", "lessons": []}]},
    )
    with ZipFile(BytesIO(rebuilt)) as package:
        assert "imsmanifest.xml" in package.namelist()
        assert "data/course.json" in package.namelist()
        assert '"title": "B"' in package.read("data/course.json").decode("utf-8")


def test_build_zip_replaces_media_and_preserves_protected_branding():
    original = _sample_zip_bytes()
    buffer = BytesIO()
    with ZipFile(BytesIO(original)) as source, ZipFile(buffer, "w", ZIP_DEFLATED) as target:
        for name in source.namelist():
            if name == "data/course.json":
                target.writestr(
                    name,
                    '{"course_title":"Demo Course","course_slug":"demo-course","modules":[],"branding":{"footer_text":"Licensed customer"},"export_stamp":"signed"}',
                )
            else:
                target.writestr(name, source.read(name))
        target.writestr("assets/scorm_api.js", "tracking")
        target.writestr("assets/media/hero.png", b"old")

    rebuilt = _build_zip(
        buffer.getvalue(),
        {"course_title": "Edited", "course_slug": "demo-course", "modules": [], "branding": {}},
        {"hero.png": b"new"},
    )
    with ZipFile(BytesIO(rebuilt)) as package:
        course = package.read("data/course.json").decode("utf-8")
        assert '"footer_text": "Licensed customer"' in course
        assert '"export_stamp": "signed"' in course
        assert package.read("assets/media/hero.png") == b"new"
        assert package.read("assets/scorm_api.js") == b"tracking"


def test_editor_ui_has_authoring_modes_and_preview():
    index = open("apps/scorm_editor/static/index.html", encoding="utf-8").read()
    app_js = open("apps/scorm_editor/static/editor.js", encoding="utf-8").read()
    css = open("apps/scorm_editor/static/editor.css", encoding="utf-8").read()

    assert 'id="tab-structure"' in index
    assert 'id="tab-templates"' in index
    assert 'id="tab-review"' in index
    assert 'id="inspector"' in index
    assert 'id="canvas"' in index
    assert 'id="btn-export"' in index
    assert 'id="new-course-form"' in index
    assert "/api/import" in app_js
    assert "/api/export/" in app_js
    assert "renderInspector" in app_js
    assert "renderTree" in app_js
    assert "game_options" in app_js
    assert ".media-preview" in css
    assert "BroadcastChannel" in app_js
    assert "course-studio-recovery:" in app_js
    assert "/api/collaboration/" in app_js
    assert "Approve revision" in app_js
    assert 'fetch("/api/new"' in app_js


def test_editor_versions_saves_and_preserves_revision_history(tmp_path, monkeypatch):
    monkeypatch.setenv("EDITOR_WORKSPACE_DIR", str(tmp_path / "workspaces"))
    imported = import_package(_sample_zip_bytes())
    assert imported["version"] == 1
    course = imported["course"]
    course["course_title"] = "Revision two"
    saved = save_course(imported["session"], course, expected_version=1, actor="reviewer", reason="Review edit")
    assert saved["version"] == 2
    revisions = list_revisions(imported["session"])
    assert [item["version"] for item in revisions] == [2, 1]
    assert get_revision(imported["session"], 2)["course"]["course_title"] == "Revision two"
    with pytest.raises(EditConflictError) as conflict:
        save_course(imported["session"], course, expected_version=1)
    assert conflict.value.current_version == 2


def test_editor_export_excludes_internal_revision_metadata(tmp_path, monkeypatch):
    monkeypatch.setenv("EDITOR_WORKSPACE_DIR", str(tmp_path / "workspaces"))
    imported = import_package(_sample_zip_bytes())
    exported = export_package(imported["session"])
    with ZipFile(BytesIO(exported)) as package:
        assert not any(part.startswith(".") for name in package.namelist() for part in name.split("/"))


def test_editor_revision_comparison_comments_roles_and_approvals(tmp_path, monkeypatch):
    monkeypatch.setenv("EDITOR_WORKSPACE_DIR", str(tmp_path / "workspaces"))
    imported = import_package(_sample_zip_bytes())
    course = imported["course"]
    course["course_title"] = "Reviewed title"
    save_course(imported["session"], course, expected_version=1, actor="ari")
    comparison = compare_revisions(imported["session"], 1, 2)
    assert comparison["changes"] == [
        {"path": "course_title", "before": "Demo Course", "after": "Reviewed title"}
    ]
    state = update_collaboration(
        imported["session"], "comment", {"actor": "ari", "target": "course_title", "message": "Use customer wording"}
    )
    comment_id = state["comments"][0]["id"]
    update_collaboration(imported["session"], "resolve_comment", {"actor": "lee", "comment_id": comment_id})
    update_collaboration(imported["session"], "role", {"actor": "ari", "user": "lee", "role": "reviewer"})
    state = update_collaboration(
        imported["session"], "approval", {"actor": "lee", "decision": "approved"}
    )
    assert state["comments"][0]["resolved"] is True
    assert state["roles"]["lee"] == "reviewer"
    assert state["approvals"][0]["version"] == 2
    assert collaboration_state(imported["session"])["approvals"][0]["decision"] == "approved"


def test_editor_creates_new_scenario_course_without_json_or_import(tmp_path, monkeypatch):
    monkeypatch.setenv("EDITOR_WORKSPACE_DIR", str(tmp_path / "workspaces"))
    created = create_course("Customer Escalation Practice", "Support specialists", "scenario")
    assert created["version"] == 1
    assert created["course"]["course_title"] == "Customer Escalation Practice"
    activity = created["course"]["modules"][0]["lessons"][0]["activities"][0]
    assert activity["activity_type"] == "scenario_decision_tree"
    with ZipFile(BytesIO(export_package(created["session"]))) as package:
        assert "imsmanifest.xml" in package.namelist()
        assert "assets/scorm_api.js" in package.namelist()
