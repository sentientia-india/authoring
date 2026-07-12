import json
import stat
import sys
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile, ZipInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from apps.scorm_editor import server as editor
from course_mcp_server.exporters.scorm import build_scorm_package, validate_scorm_package
from course_mcp_server.schemas import ScormPackageRequest


def _demo_zip(tmp_path) -> bytes:
    fixture = json.loads(
        (Path(__file__).parent / "fixtures" / "agile_course_content.json").read_text(encoding="utf-8")
    )
    modules = [
        {
            "title": module["title"],
            "lessons": module["lessons"],
            "activities": module.get("activities", []),
            "course_payload": {
                "course_title": "Agile Sprint Playbook",
                "course_slug": "agile-sprint-playbook",
                "modules": fixture["modules"],
                "final_assessment": fixture["final_assessment"],
                "learning_objectives": fixture["learning_objectives"],
                "game_options": fixture["game_options"],
            },
        }
        for module in fixture["modules"]
    ]
    result = build_scorm_package(
        ScormPackageRequest(course_title="Agile Sprint Playbook", course_slug="agile-sprint-playbook", modules=modules),
        str(tmp_path / "build"),
    )
    return Path(result["package_path"]).read_bytes()


def test_editor_full_roundtrip_preserves_scorm_validity(tmp_path, monkeypatch):
    monkeypatch.setenv("EDITOR_WORKSPACE_DIR", str(tmp_path / "workspaces"))

    imported = editor.import_package(_demo_zip(tmp_path))
    sid = imported["session"]
    course = imported["course"]

    # The workspace serves the REAL player with editor stamps.
    workspace = editor._workspace(sid)
    player_js = (workspace / "assets" / "player.js").read_text(encoding="utf-8")
    assert "data-cb-id" in player_js
    assert "dataset.activityId = activityId" in player_js

    # Simulate editor actions: rename, edit text, insert a template activity.
    course["modules"][0]["lessons"][0]["title"] = "Edited lesson title"
    course["modules"][0]["lessons"][0]["content_blocks"][0]["text"] = "EDITED IN STUDIO."
    course["modules"][0]["lessons"][0].setdefault("activities", []).append(
        {
            "activity_id": "act_inserted",
            "activity_type": "flashcards",
            "title": "Inserted cards",
            "objective": "Flip each card.",
            "items": [{"front": "A", "back": "B"}],
        }
    )
    editor.save_course(sid, course)

    # The embedded course-data (what the canvas iframe renders) reflects the edit.
    index_html = (workspace / "index.html").read_text(encoding="utf-8")
    assert "EDITED IN STUDIO." in index_html
    assert "Inserted cards" in index_html

    # Media added in the editor lands in the workspace and, on export, the manifest.
    editor.add_media(sid, "studio.svg", b"<svg xmlns='http://www.w3.org/2000/svg'/>")

    blob = editor.export_package(sid)
    exported = tmp_path / "edited.zip"
    exported.write_bytes(blob)
    with ZipFile(BytesIO(blob)) as package:
        names = package.namelist()
        manifest = package.read("imsmanifest.xml").decode("utf-8")
        course_json = package.read("data/course.json").decode("utf-8")
    assert "assets/media/studio.svg" in names
    assert 'href="assets/media/studio.svg"' in manifest
    assert "EDITED IN STUDIO." in course_json

    report = validate_scorm_package(exported, ["imsmanifest.xml", "index.html", "assets/scorm_api.js", "data/course.json"])
    assert report["valid"] is True, report["errors"]


def test_editor_rejects_non_mcp_packages(tmp_path, monkeypatch):
    monkeypatch.setenv("EDITOR_WORKSPACE_DIR", str(tmp_path / "workspaces"))
    buffer = BytesIO()
    with ZipFile(buffer, "w") as package:
        package.writestr("index.html", "<html></html>")
    try:
        editor.import_package(buffer.getvalue())
        raised = False
    except ValueError:
        raised = True
    assert raised


def test_editor_rejects_path_traversal_and_cleans_workspace(tmp_path, monkeypatch):
    root = tmp_path / "workspaces"
    monkeypatch.setenv("EDITOR_WORKSPACE_DIR", str(root))
    buffer = BytesIO()
    with ZipFile(buffer, "w") as package:
        package.writestr("imsmanifest.xml", "<manifest/>")
        package.writestr("data/course.json", "{}")
        package.writestr("../escape.txt", "blocked")
    try:
        editor.import_package(buffer.getvalue())
        raised = False
    except ValueError:
        raised = True
    assert raised
    assert not (tmp_path / "escape.txt").exists()
    assert list(root.iterdir()) == []


def test_editor_rejects_symlink_zip_entry(tmp_path, monkeypatch):
    monkeypatch.setenv("EDITOR_WORKSPACE_DIR", str(tmp_path / "workspaces"))
    buffer = BytesIO()
    with ZipFile(buffer, "w") as package:
        package.writestr("imsmanifest.xml", "<manifest/>")
        package.writestr("data/course.json", "{}")
        entry = ZipInfo("assets/media/link")
        entry.create_system = 3
        entry.external_attr = (stat.S_IFLNK | 0o777) << 16
        package.writestr(entry, "../../outside")
    try:
        editor.import_package(buffer.getvalue())
        raised = False
    except ValueError:
        raised = True
    assert raised
