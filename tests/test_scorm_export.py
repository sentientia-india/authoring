from pathlib import Path
from zipfile import ZipFile

from course_mcp_server.exporters.scorm import build_scorm_package, validate_scorm_package
from course_mcp_server.schemas import ScormPackageRequest


def test_scorm_package_creates_zip_with_manifest_and_module_pages(tmp_path):
    result = build_scorm_package(
        ScormPackageRequest(
            course_title="Ramp Safety",
            course_slug="ramp-safety",
            modules=[
                {
                    "title": "Hazards",
                    "lessons": [
                        {
                            "title": "Spot hazards",
                            "objective": "Identify hazards",
                            "duration_minutes": 15,
                        }
                    ],
                }
            ],
        ),
        str(tmp_path),
    )

    package_path = Path(result["package_path"])
    assert package_path.exists()
    assert package_path.suffix == ".zip"
    assert result["files"] == [
        "imsmanifest.xml",
        "index.html",
        "module-1.html",
        "assets/styles.css",
        "assets/course.js",
        "assets/player.js",
        "assets/h5p_bridge.js",
        "assets/scorm_api.js",
        "assets/study-map.svg",
        "assets/prompt-lab.svg",
        "data/course.json",
    ]

    with ZipFile(package_path) as package:
        names = sorted(package.namelist())
        assert names == sorted(result["files"])
        assert "module-1.html" in package.read("imsmanifest.xml").decode("utf-8")
        assert "Ramp Safety" in package.read("data/course.json").decode("utf-8")
        assert "theme" in package.read("data/course.json").decode("utf-8")


def test_scorm_package_embeds_h5p_style_activity_content(tmp_path):
    result = build_scorm_package(
        ScormPackageRequest(
            course_title="AI for Students",
            course_slug="ai-for-students",
            modules=[
                {
                    "title": "Prompt practice",
                    "lessons": [{"title": "Write a prompt", "objective": "Create clear prompts"}],
                    "activities": [
                        {
                            "activity_id": "activity_1",
                            "activity_type": "matching",
                            "title": "Match prompt parts",
                            "objective": "Match each prompt part to its purpose.",
                            "items": [{"left": "Audience", "right": "Who the answer is for"}],
                        }
                    ],
                }
            ],
        ),
        str(tmp_path),
    )

    assert "activities/content.json" in result["files"]
    assert "assets/h5p_bridge.js" in result["files"]

    with ZipFile(result["package_path"]) as package:
        manifest = package.read("imsmanifest.xml").decode("utf-8")
        index = package.read("index.html").decode("utf-8")
        activities = package.read("activities/content.json").decode("utf-8")

    assert "activities/content.json" in manifest
    assert "h5p_bridge.js" in index
    assert "Match prompt parts" in activities


def test_scorm_package_uses_polished_responsive_template(tmp_path):
    result = build_scorm_package(
        ScormPackageRequest(
            course_title="AI for Students",
            course_slug="ai-for-students",
            modules=[
                {
                    "title": "Use AI responsibly",
                    "lessons": [
                        {
                            "title": "Ask Check Learn",
                            "objective": "Use AI as a study helper",
                            "duration_minutes": 5,
                        }
                    ],
                    "video_url": "https://www.youtube-nocookie.com/embed/128rGos_q9w",
                }
            ],
        ),
        str(tmp_path),
    )

    with ZipFile(result["package_path"]) as package:
        index = package.read("index.html").decode("utf-8")
        css = package.read("assets/styles.css").decode("utf-8")
        js = package.read("assets/course.js").decode("utf-8")
        player_js = package.read("assets/player.js").decode("utf-8")
        scorm_js = package.read("assets/scorm_api.js").decode("utf-8")

    assert "How to use this course" in index
    assert "youtube-nocookie.com/embed/128rGos_q9w" in index
    assert "@media (max-width: 820px)" in css
    assert "function gradeQuiz" in js
    assert "renderCoursePlayer" in player_js
    assert "renderAssessment" in player_js
    assert "setScore" in scorm_js
    assert "findApi(window.opener" in scorm_js
    assert "setSuspendData" in scorm_js
    assert "setLocation" in scorm_js
    assert "recordInteraction" in scorm_js
    assert "cmi.interactions." in scorm_js
    assert "cmi.core.lesson_status" in scorm_js
    assert "cmi.success_status" in scorm_js


def test_scorm_artifact_path_stays_inside_output_dir(tmp_path):
    result = build_scorm_package(
        ScormPackageRequest(
            course_title="Safe Course",
            course_slug="safe-course",
            modules=[{"title": "Intro", "lessons": []}],
        ),
        str(tmp_path),
    )

    artifact_path = Path(result["artifact_path"]).resolve()
    assert artifact_path.is_relative_to(tmp_path.resolve())


def test_validate_scorm_package_reports_missing_manifest(tmp_path):
    package_path = tmp_path / "broken.zip"
    with ZipFile(package_path, "w") as package:
        package.writestr("index.html", "<html></html>")

    result = validate_scorm_package(package_path, ["imsmanifest.xml", "index.html"])

    assert result["valid"] is False
    assert "Missing package file: imsmanifest.xml" in result["errors"]


def test_validate_scorm_package_checks_runtime_tracking_files(tmp_path):
    package_path = tmp_path / "weak.zip"
    with ZipFile(package_path, "w") as package:
        package.writestr(
            "imsmanifest.xml",
            '<manifest><resource adlcp:scormtype="sco" href="index.html"></resource></manifest>',
        )
        package.writestr("index.html", "<html></html>")
        package.writestr("assets/scorm_api.js", "function setScore() {}")

    result = validate_scorm_package(
        package_path,
        ["imsmanifest.xml", "index.html", "assets/scorm_api.js"],
    )

    assert result["valid"] is False
    assert "SCORM runtime does not record interactions." in result["errors"]


def test_scorm_shell_uses_course_player_layout(tmp_path):
    result = build_scorm_package(
        ScormPackageRequest(
            course_title="Emergency Evacuation",
            course_slug="emergency-evacuation",
            modules=[
                {
                    "title": "Assess Conditions",
                    "lessons": [
                        {
                            "title": "Cabin readiness",
                            "objective": "Evaluate passenger readiness.",
                            "duration_minutes": 8,
                        }
                    ],
                }
            ],
        ),
        str(tmp_path),
    )

    with ZipFile(result["package_path"]) as package:
        index = package.read("index.html").decode("utf-8")
        css = package.read("assets/styles.css").decode("utf-8")
        player_js = package.read("assets/player.js").decode("utf-8")

    assert "course-shell" in index
    assert "progress-ring" in index
    assert "lesson-workspace" in index
    assert "data-course-player" in index
    assert 'id="course-data"' in index
    assert ".course-shell" in css
    assert "renderModuleNav" in player_js
    assert "renderLessonDeck" in player_js


def test_scorm_package_assigns_a_themed_player_for_compliance_courses(tmp_path):
    result = build_scorm_package(
        ScormPackageRequest(
            course_title="Emergency Evacuation for Cabin Crew",
            course_slug="emergency-evacuation",
            modules=[
                {
                    "title": "Foundation",
                    "lessons": [{"title": "Readiness", "objective": "Identify readiness", "duration_minutes": 8}],
                }
            ],
        ),
        str(tmp_path),
    )

    with ZipFile(result["package_path"]) as package:
        course_json = package.read("data/course.json").decode("utf-8")
        index = package.read("index.html").decode("utf-8")

    assert '"theme": "compliance"' in course_json
    assert 'data-theme="compliance"' in index
