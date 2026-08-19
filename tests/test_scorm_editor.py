from io import BytesIO
import time
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from apps.scorm_editor.server import (
    EditConflictError,
    _build_zip,
    _import_package,
    accessibility_report,
    cancel_generation_job,
    collaboration_state,
    compare_revisions,
    create_course,
    export_package,
    get_revision,
    generation_job_state,
    import_package,
    ingest_source,
    list_revisions,
    list_sources,
    localization_state,
    save_course,
    start_generation_job,
    update_collaboration,
    update_localization,
    upload_source,
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
    assert 'id="tab-sources"' in index
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
    assert "@media (max-width: 900px)" in css
    assert "@media (max-width: 600px)" in css
    assert "prefers-reduced-motion" in css
    assert 'role="tablist"' in index
    assert 'node.setAttribute("role", "button")' in app_js
    assert 'event.key === "Enter"' in app_js
    assert "BroadcastChannel" in app_js
    assert "course-studio-recovery:" in app_js
    assert "/api/collaboration/" in app_js
    assert "Approve revision" in app_js
    assert 'fetch("/api/new"' in app_js
    assert "Citation inspector" in app_js
    assert "Outline approved" in app_js
    assert "Certificate footer" in app_js
    assert "/api/sources/" in app_js
    assert "/api/accessibility/" in app_js
    assert "Accessibility report" in app_js
    assert "/api/localization/" in app_js
    assert "Save translation" in app_js
    assert "/api/generation/" in app_js
    assert "Cancel generation" in app_js


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


def test_editor_source_intake_is_digest_verified_and_excluded_from_export(tmp_path, monkeypatch):
    monkeypatch.setenv("EDITOR_WORKSPACE_DIR", str(tmp_path / "workspaces"))
    created = create_course("Evidence-led onboarding")
    source = ingest_source(
        created["session"],
        "Customer handbook",
        "Page 1: Always verify the account owner before changing administrative access.",
    )
    assert source["source_id"].startswith("source_")
    assert len(source["sha256"]) == 64
    assert list_sources(created["session"])[0]["title"] == "Customer handbook"
    with ZipFile(BytesIO(export_package(created["session"]))) as package:
        assert not any("sources" in name for name in package.namelist())


def _real_pdf_bytes(page_texts):
    from reportlab.pdfgen import canvas

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)
    for text in page_texts:
        pdf.drawString(72, 720, text)
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def test_editor_source_upload_extracts_pdf_text_and_page_references(tmp_path, monkeypatch):
    monkeypatch.setenv("EDITOR_WORKSPACE_DIR", str(tmp_path / "workspaces"))
    created = create_course("Evidence-led onboarding")
    blob = _real_pdf_bytes(["Always verify the account owner first.", "Escalate unresolved disputes to a lead."])
    source = upload_source(created["session"], "Customer Handbook.pdf", blob)
    assert source["source_id"].startswith("source_")
    assert source["title"] == "Customer Handbook"
    assert source["references"] == ["page:1", "page:2"]
    stored = list_sources(created["session"])[0]
    assert stored["references"] == ["page:1", "page:2"]


def test_editor_source_upload_rejects_unsupported_extension(tmp_path, monkeypatch):
    monkeypatch.setenv("EDITOR_WORKSPACE_DIR", str(tmp_path / "workspaces"))
    created = create_course("Evidence-led onboarding")
    with pytest.raises(ValueError, match="Unsupported source file type"):
        upload_source(created["session"], "notes.txt", b"plain text notes")


def test_editor_source_upload_rejects_pdf_with_no_extractable_text(tmp_path, monkeypatch):
    monkeypatch.setenv("EDITOR_WORKSPACE_DIR", str(tmp_path / "workspaces"))
    created = create_course("Evidence-led onboarding")
    # A malformed PDF still falls back to a regex text scrape (see ingestion._extract_pdf)
    # rather than raising; this payload survives that fallback with under 20 chars of text,
    # which is upload_source's own no-extractable-content rejection, not extract_source's.
    with pytest.raises(ValueError, match="No extractable text"):
        upload_source(created["session"], "broken.pdf", b"\x00\x01\x02garbage%%\x03")


def test_editor_source_upload_rejects_malformed_docx_cleanly(tmp_path, monkeypatch):
    monkeypatch.setenv("EDITOR_WORKSPACE_DIR", str(tmp_path / "workspaces"))
    created = create_course("Evidence-led onboarding")
    with pytest.raises(ValueError, match="Could not extract text from"):
        upload_source(created["session"], "broken.docx", b"not a real docx zip file at all")


def test_editor_text_source_ingest_stays_backward_compatible_without_references(tmp_path, monkeypatch):
    monkeypatch.setenv("EDITOR_WORKSPACE_DIR", str(tmp_path / "workspaces"))
    created = create_course("Evidence-led onboarding")
    source = ingest_source(created["session"], "Pasted notes", "Pasted text with no page anchors at all here.")
    assert "references" not in source


def test_editor_accessibility_report_blocks_missing_media_alternatives(tmp_path, monkeypatch):
    monkeypatch.setenv("EDITOR_WORKSPACE_DIR", str(tmp_path / "workspaces"))
    created = create_course("Accessible onboarding")
    course = created["course"]
    lesson = course["modules"][0]["lessons"][0]
    lesson["media"] = [
        {"type": "image", "src": "assets/media/diagram.png"},
        {"type": "video", "src": "assets/media/demo.mp4"},
    ]
    report = accessibility_report(course)
    assert report["status"] == "fail"
    assert {item["code"] for item in report["issues"] if item["severity"] == "blocker"} == {
        "image_alt_missing",
        "video_text_alternative_missing",
    }
    save_course(created["session"], course, expected_version=1)
    with pytest.raises(ValueError, match="Accessibility gate failed with 2 blocker"):
        export_package(created["session"])
    lesson["media"][0]["alt_text"] = "Account owner verification flow"
    lesson["media"][1]["transcript"] = "The presenter demonstrates the verification flow."
    save_course(created["session"], course, expected_version=2)
    assert accessibility_report(course)["status"] == "pass"
    assert export_package(created["session"])


def test_editor_localization_inherits_source_and_tracks_translation_status(tmp_path, monkeypatch):
    monkeypatch.setenv("EDITOR_WORKSPACE_DIR", str(tmp_path / "workspaces"))
    created = create_course("Localized onboarding")
    state = localization_state(created["session"])
    assert state["base_locale"] == "en"
    assert state["locales"]["en"]["status"] == "source"
    state = update_localization(created["session"], "add_locale", {"locale": "es-MX"})
    assert state["locales"]["es-mx"]["overrides"] == {}
    state = update_localization(
        created["session"],
        "set_override",
        {"locale": "es-mx", "path": "course_title", "value": "Incorporacion localizada"},
    )
    assert state["locales"]["es-mx"]["status"] == "draft"
    assert state["locales"]["es-mx"]["overrides"]["course_title"] == "Incorporacion localizada"
    state = update_localization(
        created["session"], "set_status", {"locale": "es-mx", "status": "approved"}
    )
    assert state["locales"]["es-mx"]["status"] == "approved"
    with ZipFile(BytesIO(export_package(created["session"]))) as package:
        assert not any("localization" in name for name in package.namelist())


def test_editor_generation_preserves_partial_work_and_retries_failed_modules(tmp_path, monkeypatch):
    monkeypatch.setenv("EDITOR_WORKSPACE_DIR", str(tmp_path / "workspaces"))
    created = create_course("Background generation course")
    course = created["course"]
    course["workflow"] = {"outline_approved": True}
    course["modules"].append({"title": "Advanced practice", "lessons": []})
    save_course(created["session"], course, expected_version=1)

    def first_generator(_course, module, _sources):
        if module["title"] == "Advanced practice":
            raise RuntimeError("provider unavailable")
        return {"title": module["title"], "lessons": [{"title": "Generated foundation"}]}

    start_generation_job(created["session"], generator=first_generator)
    deadline = time.time() + 10
    while generation_job_state(created["session"])["status"] not in {"failed", "succeeded"}:
        assert time.time() < deadline
        time.sleep(0.01)
    failed = generation_job_state(created["session"])
    assert failed["status"] == "failed"
    assert [item["status"] for item in failed["modules"]] == ["succeeded", "failed"]
    first_version = failed["modules"][0]["version"]

    def retry_generator(_course, module, _sources):
        return {"title": module["title"], "lessons": [{"title": "Recovered lesson"}]}

    start_generation_job(created["session"], generator=retry_generator)
    deadline = time.time() + 10
    while generation_job_state(created["session"])["status"] != "succeeded":
        assert time.time() < deadline
        time.sleep(0.01)
    recovered = generation_job_state(created["session"])
    assert recovered["progress"] == 100
    assert recovered["modules"][0]["version"] == first_version
    assert recovered["modules"][0]["attempts"] == 1
    assert recovered["modules"][1]["attempts"] == 2


def test_editor_generation_cancellation_is_cooperative(tmp_path, monkeypatch):
    monkeypatch.setenv("EDITOR_WORKSPACE_DIR", str(tmp_path / "workspaces"))
    created = create_course("Cancellable generation course")
    course = created["course"]
    course["workflow"] = {"outline_approved": True}
    save_course(created["session"], course, expected_version=1)

    def slow_generator(_course, module, _sources):
        time.sleep(0.15)
        return {"title": module["title"], "lessons": [{"title": "Late result"}]}

    start_generation_job(created["session"], generator=slow_generator)
    deadline = time.time() + 10
    while generation_job_state(created["session"])["status"] != "running":
        assert time.time() < deadline
        time.sleep(0.01)
    cancel_generation_job(created["session"])
    while generation_job_state(created["session"])["status"] != "cancelled":
        assert time.time() < deadline
        time.sleep(0.01)
    cancelled = generation_job_state(created["session"])
    assert cancelled["progress"] == 0
    assert cancelled["modules"][0]["status"] == "cancelled"
