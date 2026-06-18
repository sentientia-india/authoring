from course_mcp_server.html_video_engine import (
    HtmlVideoRenderer,
    build_video_project_from_course,
    render_webvtt,
    split_narration_to_captions,
)


def sample_course():
    return {
        "course_id": "course_airline_demo",
        "course_title": "Emergency Evacuation for Cabin Crew",
        "modules": [
            {
                "title": "Evacuation Decisions",
                "lessons": [
                    {
                        "id": "lesson_cabin_evacuate",
                        "title": "Assess the Cabin Before Evacuation",
                        "content_blocks": [
                            {"type": "intro", "text": "The cabin crew must assess smoke, passenger panic, and exit usability before movement."},
                            {"type": "scenario", "text": "A passenger is blocking the aisle while smoke is visible near the rear galley."},
                            {"type": "summary", "text": "Use clear commands and follow the captain's instruction."},
                        ],
                    }
                ],
            }
        ],
    }


def test_captions_are_generated():
    cues = split_narration_to_captions("First sentence. Second sentence.", 10)
    assert len(cues) == 2
    assert cues[0].start == 0
    assert cues[1].end <= 10


def test_video_project_and_html_render(tmp_path):
    project = build_video_project_from_course(sample_course())
    assert project.total_duration_seconds > 20
    assert any(scene.type == "decision_pause" for scene in project.scenes)
    written = HtmlVideoRenderer().write_package(project, tmp_path)
    assert (tmp_path / "interactive-video.html").exists()
    assert (tmp_path / "captions.vtt").exists()
    assert (tmp_path / "video-project.json").exists()
    html = (tmp_path / "interactive-video.html").read_text(encoding="utf-8")
    assert "data-video-project" in html
    assert "sentientia_video_engine.js" in html
    assert "Transcript" in html
    assert written["html"].endswith("interactive-video.html")


def test_vtt_output():
    project = build_video_project_from_course(sample_course())
    vtt = render_webvtt(project)
    assert vtt.startswith("WEBVTT")
    assert "-->" in vtt
