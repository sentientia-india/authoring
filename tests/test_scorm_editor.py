from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from apps.scorm_editor.server import _build_zip, _import_package


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


def test_editor_ui_has_authoring_modes_and_preview():
    index = open("apps/scorm_editor/static/index.html", encoding="utf-8").read()
    app_js = open("apps/scorm_editor/static/app.js", encoding="utf-8").read()
    css = open("apps/scorm_editor/static/style.css", encoding="utf-8").read()

    assert 'data-mode="outline"' in index
    assert 'data-mode="lesson"' in index
    assert 'data-mode="theme"' in index
    assert 'data-mode="assessment"' in index
    assert 'id="preview"' in index
    assert "ensureBlocks" in app_js
    assert "renderAssessmentEditor" in app_js
    assert "renderPreview" in app_js
    assert "Edit JSON blocks directly" not in app_js
    assert ".preview-frame" in css
