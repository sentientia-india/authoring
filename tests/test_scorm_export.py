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
        "assets/gamification_engine.js",
        "assets/sentientia_video_engine.js",
        "assets/sentientia_video_engine.css",
        "assets/scorm_api.js",
        "assets/study-map.svg",
        "assets/prompt-lab.svg",
        "interactive-video/index.html",
        "interactive-video/video_project.json",
        "interactive-video/sentientia_video_engine.js",
        "interactive-video/sentientia_video_engine.css",
        "data/course.json",
    ]

    with ZipFile(package_path) as package:
        names = sorted(package.namelist())
        assert names == sorted(result["files"])
        assert "module-1.html" in package.read("imsmanifest.xml").decode("utf-8")
        assert "Ramp Safety" in package.read("data/course.json").decode("utf-8")
        assert "theme" in package.read("data/course.json").decode("utf-8")


def test_scorm_package_renders_activities_natively_without_h5p_runtime(tmp_path):
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

    assert "activities/content.json" not in result["files"]
    assert "assets/h5p_bridge.js" not in result["files"]
    assert "h5p/course.h5p" not in result["files"]

    with ZipFile(result["package_path"]) as package:
        manifest = package.read("imsmanifest.xml").decode("utf-8")
        index = package.read("index.html").decode("utf-8")
        names = package.namelist()
        player_js = package.read("assets/player.js").decode("utf-8")
        course_json = package.read("data/course.json").decode("utf-8")

    assert "activities/content.json" not in manifest
    assert "h5p_bridge.js" not in index
    assert "h5p/" not in "\n".join(names)
    assert "h5p_style" not in course_json
    assert "Interactive practice" in index
    assert "renderActivityDeck" in player_js


def test_scorm_learner_ui_hides_technical_copy_and_shows_intro_controls(tmp_path):
    result = build_scorm_package(
        ScormPackageRequest(
            course_title="Agile for Project Managers",
            course_slug="agile-for-project-managers",
            modules=[
                {
                    "title": "Foundation",
                    "duration_minutes": 6,
                    "lessons": [
                        {
                            "title": "Agile basics",
                            "objective": "Understand expected learner decisions without source-aware wording.",
                            "duration_minutes": 3,
                        },
                        {"title": "Startup delivery", "objective": "Choose a practical delivery action.", "duration_minutes": 3},
                    ],
                }
            ],
        ),
        str(tmp_path),
    )

    with ZipFile(result["package_path"]) as package:
        index = package.read("index.html").decode("utf-8")
        player_js = package.read("assets/player.js").decode("utf-8")
        course_json = package.read("data/course.json").decode("utf-8")

    forbidden = [
        "SCORM course player",
        "Interactive lesson path",
        "A structured course package",
        "source-aware",
        "generated lessons",
        "suspend data",
        "completion tracking",
        "objective aligned",
        "source aligned",
        "expected learner decisions",
        "The LMS can capture",
    ]
    for text in forbidden:
        assert text not in index
        assert text not in course_json

    assert "Course overview" in index
    assert "Your learning path" in index
    assert "Build practical skill" in index
    assert 'id="stat-duration"' in index
    assert 'id="stat-modules"' in index
    assert 'id="stat-lessons"' in index
    assert 'id="start-course"' in index
    assert 'id="view-outline"' in index
    assert "learnerSafeText" in player_js
    assert "Continue learning" in player_js


def test_scorm_package_contains_interactive_video_payload_without_h5p_package(tmp_path):
    result = build_scorm_package(
        ScormPackageRequest(
            course_title="Agile Micro Course",
            course_slug="agile-micro-course",
            modules=[
                {
                    "title": "Agile in 2026",
                    "lessons": [{"title": "Shift", "objective": "Identify Agile shifts"}],
                    "activities": [
                        {
                            "activity_id": "activity_1",
                            "activity_type": "scenario_decision_tree",
                            "title": "Choose an Agile move",
                            "objective": "Pick a practical action.",
                            "items": [{"scenario": "A startup is stuck in planning.", "choices": [{"label": "Limit WIP"}]}],
                        }
                    ],
                }
            ],
        ),
        str(tmp_path),
    )

    assert "h5p/course.h5p" not in result["files"]
    assert "interactive-video/index.html" in result["files"]
    assert "interactive-video/video_project.json" in result["files"]

    with ZipFile(result["package_path"]) as package:
        names = package.namelist()
        index = package.read("index.html").decode("utf-8")

    assert "h5p/course.h5p" not in names
    assert "interactive-video/video_project.json" in names
    assert "Open interactive video" in index


def test_scorm_player_buttons_are_bound_without_inline_handlers(tmp_path):
    result = build_scorm_package(
        ScormPackageRequest(
            course_title="Agile Micro Course",
            course_slug="agile-micro-course",
            modules=[{"title": "Intro", "lessons": [{"title": "Shift", "objective": "Identify Agile shifts"}]}],
        ),
        str(tmp_path),
    )

    with ZipFile(result["package_path"]) as package:
        index = package.read("index.html").decode("utf-8")
        module = package.read("module-1.html").decode("utf-8")
        course_js = package.read("assets/course.js").decode("utf-8")
        player_js = package.read("assets/player.js").decode("utf-8")

    assert 'onclick="buildPrompt()"' not in index
    assert 'onclick="markCourseComplete()"' not in index
    assert "onclick=" not in module
    assert "onclick=" not in course_js
    assert 'id="prompt-build"' in index
    assert 'id="course-complete"' in index
    assert 'id="module-complete"' in module
    assert 'data-choice="smart"' in course_js
    assert 'data-choice="risky"' in course_js
    assert 'addEventListener("click", buildPrompt)' in course_js
    assert 'addEventListener("click", markCourseComplete)' in course_js
    assert 'addEventListener("click", (event)' in course_js
    assert "renderLessonReader" in player_js
    assert "renderLessonCards" in player_js
    assert "renderModuleSection" in player_js
    assert "Close" in player_js
    assert "lesson-reader" in player_js
    assert "lesson-block-grid" in player_js
    assert "Concept" in player_js
    assert "Workplace example" in player_js
    assert "Try it now" in player_js
    assert "data-reader-action=\"next\"" in player_js
    assert "item.match" in player_js
    assert "item.choices" in player_js


def test_scorm_interactive_video_shell_matches_runtime_contract(tmp_path):
    result = build_scorm_package(
        ScormPackageRequest(
            course_title="Agile Micro Course",
            course_slug="agile-micro-course",
            modules=[
                {
                    "title": "Intro",
                    "lessons": [
                        {
                            "title": "Shift",
                            "objective": "Identify Agile shifts",
                            "content_blocks": [
                                {
                                    "type": "scenario",
                                    "text": "A startup team has too much work in progress and needs a practical Agile reset.",
                                }
                            ],
                        }
                    ],
                }
            ],
        ),
        str(tmp_path),
    )

    with ZipFile(result["package_path"]) as package:
        video_index = package.read("interactive-video/index.html").decode("utf-8")
        video_project = package.read("interactive-video/video_project.json").decode("utf-8")

    assert 'class="sv-shell"' in video_index
    assert "data-video-project=" in video_index
    assert 'id="sv-stage"' in video_index
    assert 'id="sv-play"' in video_index
    assert 'id="sv-pause"' in video_index
    assert 'id="sv-prev"' in video_index
    assert 'id="sv-next"' in video_index
    assert 'id="sv-progress"' in video_index
    assert '"interactions"' in video_project
    assert '"checkpoint"' not in video_project


def test_scorm_player_uses_full_width_lesson_reader_and_fallback_assessment(tmp_path):
    result = build_scorm_package(
        ScormPackageRequest(
            course_title="Agile Micro Course",
            course_slug="agile-micro-course",
            modules=[
                {
                    "title": "Intro",
                    "lessons": [
                        {
                            "title": "Shift",
                            "objective": "Identify Agile shifts",
                            "duration_minutes": 5,
                            "content_blocks": [
                                {"type": "explanation", "text": "Teams need shorter feedback loops."},
                                {"type": "example", "text": "A startup reviews delivery evidence weekly."},
                                {"type": "practice", "text": "Pick the next Agile action."},
                                {"type": "summary", "text": "Use evidence before changing process."},
                            ],
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
        course_json = package.read("data/course.json").decode("utf-8")

    assert "Video block ready" not in index
    assert "lesson-reader" in css
    assert "renderLessonReader(course, state, module, moduleIndex)" in player_js
    assert "${current ? renderLessonDetail(lesson) : \"\"}" not in player_js
    assert "Final Check" in course_json
    assert '"questions": []' not in course_json


def test_scorm_normalizes_duplicate_activities_for_course_player(tmp_path):
    duplicate = {
        "activity_type": "matching",
        "title": "Match Agile moves",
        "objective": "Match methods to startup situations.",
        "items": [{"prompt": "Safe action", "match": "Verify with evidence"}],
    }
    result = build_scorm_package(
        ScormPackageRequest(
            course_title="Agile Micro Course",
            course_slug="agile-micro-course",
            modules=[
                {"title": "One", "lessons": [{"title": "Alpha lesson", "objective": "Do A"}], "activities": [duplicate]},
                {"title": "Two", "lessons": [{"title": "Beta lesson", "objective": "Do B"}], "activities": [duplicate]},
            ],
        ),
        str(tmp_path),
    )

    with ZipFile(result["package_path"]) as package:
        course_json = package.read("data/course.json").decode("utf-8")
        player_js = package.read("assets/player.js").decode("utf-8")

    assert course_json.count("Match Agile moves") == 1
    assert "displayType(activity.activity_type" in player_js
    assert "scenario-prompt" in player_js
    assert "match-row" in player_js


def test_scorm_renders_native_interaction_library_and_activity_fallbacks(tmp_path):
    result = build_scorm_package(
        ScormPackageRequest(
            course_title="Agile Practice",
            course_slug="agile-practice",
            modules=[
                {
                    "title": "Native interactions",
                    "lessons": [
                        {
                            "title": "Feedback loops",
                            "objective": "Select the right interaction pattern.",
                            "content_blocks": [
                                {"type": "concept", "text": "Use short feedback loops for uncertain startup work."},
                                {"type": "checklist", "text": "Define the test, run it, review evidence."},
                            ],
                        }
                    ],
                    "activities": [
                        {
                            "activity_type": "flashcards",
                            "title": "Terms",
                            "items": [{"front": "WIP", "back": "Work in progress"}],
                        },
                        {
                            "activity_type": "accordion",
                            "title": "Review",
                            "items": [{"title": "Evidence", "detail": "Use delivery data."}],
                        },
                        {
                            "activity_type": "timeline",
                            "title": "Sprint flow",
                            "items": [{"label": "Plan", "detail": "Pick a thin slice."}],
                        },
                        {
                            "activity_type": "fill_in_blanks",
                            "title": "Blank",
                            "prompt": "Agile needs short ____ loops.",
                            "answer": "feedback",
                        },
                    ],
                },
                {
                    "title": "Fallback interaction",
                    "lessons": [{"title": "Retrospectives", "objective": "Run a focused retro."}],
                },
            ],
        ),
        str(tmp_path),
    )

    with ZipFile(result["package_path"]) as package:
        css = package.read("assets/styles.css").decode("utf-8")
        player_js = package.read("assets/player.js").decode("utf-8")
        course_json = package.read("data/course.json").decode("utf-8")

    assert "flashcard-grid" in css
    assert "accordion-list" in css
    assert "timeline-list" in css
    assert "fill-blank-row" in css
    assert "blockTitle(block.type)" in player_js
    assert "type.includes(\"flashcard\")" in player_js
    assert "type.includes(\"accordion\")" in player_js
    assert "type.includes(\"timeline\")" in player_js
    assert "type.includes(\"fill\")" in player_js
    assert "Apply: Retrospectives" in course_json
    assert "Use short feedback loops for uncertain startup work." in course_json
    assert "Define the test, run it, review evidence." in course_json


def test_scorm_renders_roleplay_activity_from_minicourse_reference_pattern(tmp_path):
    result = build_scorm_package(
        ScormPackageRequest(
            course_title="Agile Coaching Role Play",
            course_slug="agile-coaching-role-play",
            modules=[
                {
                    "title": "Stakeholder conversation",
                    "lessons": [{"title": "Coach a founder", "objective": "Handle Agile pushback."}],
                    "activities": [
                        {
                            "activity_type": "roleplay",
                            "title": "Founder pushback",
                            "role": "Agile project manager",
                            "situation": "A founder wants to skip retrospectives because the team is busy.",
                            "objective": "Clarify the risk and agree a lightweight retro format.",
                            "persona": {
                                "name": "Mira Kapoor",
                                "role": "startup founder",
                                "goals": "Ship the investor demo this week.",
                                "constraints": "Will reject anything that sounds like ceremony.",
                            },
                            "expected_behaviors": [
                                "Clarify the delivery risk before prescribing a process.",
                                "Offer a time-boxed retrospective.",
                            ],
                            "rubric": [
                                {"criterion": "Clarifies the founder's risk", "points": 40},
                                {"criterion": "Offers a practical retro format", "points": 60},
                            ],
                        }
                    ],
                }
            ],
        ),
        str(tmp_path),
    )

    with ZipFile(result["package_path"]) as package:
        css = package.read("assets/styles.css").decode("utf-8")
        player_js = package.read("assets/player.js").decode("utf-8")
        course_json = package.read("data/course.json").decode("utf-8")

    assert "roleplay-grid" in css
    assert "type.includes(\"roleplay\")" in player_js
    assert "Success rubric" in player_js
    assert "Debrief score" in player_js
    assert "Mira Kapoor" in course_json
    assert "Clarifies the founder's risk" in course_json


def test_scorm_coursebox_style_gamification_quiz_and_completion_ui(tmp_path):
    result = build_scorm_package(
        ScormPackageRequest(
            course_title="Agile Gamified Course",
            course_slug="agile-gamified-course",
            modules=[
                {
                    "title": "Foundation",
                    "lessons": [{"title": "Sprint basics", "objective": "Apply a short feedback loop."}],
                    "activities": [
                        {
                            "activity_id": "activity_flashcards",
                            "activity_type": "flashcards",
                            "title": "Agile terms",
                            "items": [{"front": "Retro", "back": "A team reflection session"}],
                        }
                    ],
                }
            ],
            final_assessment={
                "title": "Final Check",
                "questions": [
                    {
                        "id": "q1",
                        "type": "mcq",
                        "question": "What should the team inspect?",
                        "options": ["Evidence", "Guesswork"],
                        "correct_answers": ["Evidence"],
                    }
                ],
            },
        ),
        str(tmp_path),
    )

    with ZipFile(result["package_path"]) as package:
        index = package.read("index.html").decode("utf-8")
        css = package.read("assets/styles.css").decode("utf-8")
        player_js = package.read("assets/player.js").decode("utf-8")

    assert 'id="game-xp"' in index
    assert 'id="badge-row"' in index
    assert "badge-pill" in css
    assert "quiz-question-card" in css
    assert "completion-screen" in css
    assert "Question ${index + 1} of ${questions.length}" in player_js
    assert "renderQuizResult" in player_js
    assert "renderCompletionScreen" in player_js
    assert "Quiz Passed" in player_js
    assert "Course Complete" in player_js


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
    assert "renderAssessmentOrEmptyState" in player_js
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
