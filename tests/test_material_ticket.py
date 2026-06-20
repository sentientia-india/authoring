from course_mcp_server.intake import create_ticket, generate_layout
from course_mcp_server.security import ALLOWED_TOOLS, RequestContext
from course_mcp_server.tools import create_material_ticket, generate_chapter_layout


def _ctx() -> RequestContext:
    return RequestContext(tenant_id="tenant-a", user_id="user-a", token="token", request_id="req-ticket")


def test_create_ticket_asks_for_missing_course_inputs():
    result = create_ticket({"course_title": "AI for Students"})

    assert result["status"] == "needs_information"
    assert "audience" in result["missing_fields"]
    assert "goal" in result["missing_fields"]
    assert result["questions"]
    assert result["question_flow"][0]["id"] == "course_brief"
    assert result["question_flow"][2]["proposed_topics"]
    assert any("quiz" in item["prompt"].lower() for item in result["question_flow"])
    assert result["normalized_ticket"]["course_title"] == "AI for Students"


def test_create_ticket_accepts_safe_youtube_and_https_mp4_media():
    result = create_ticket(
        {
            "course_title": "AI for Students",
            "audience": "college students",
            "goal": "Use AI safely for study",
            "duration_minutes": 5,
            "materials": [{"upload_id": "study-notes.txt", "source_type": "raw_text"}],
            "media": [
                {"type": "youtube", "url": "https://www.youtube.com/watch?v=abc123", "title": "AI basics"},
                {"type": "mp4", "url": "https://cdn.example.com/lesson.mp4", "title": "Local explainer"},
            ],
            "interactive_preferences": ["matching", "reflection_prompt"],
        }
    )

    assert result["status"] == "ready_for_layout"
    assert result["warnings"] == []


def test_create_ticket_rejects_unsafe_media_paths():
    result = create_ticket(
        {
            "course_title": "AI for Students",
            "audience": "college students",
            "goal": "Use AI safely for study",
            "duration_minutes": 5,
            "materials": [{"upload_id": "study-notes.txt", "source_type": "raw_text"}],
            "media": [{"type": "mp4", "url": "C:/Users/Sams PC/private.mp4"}],
        }
    )

    assert result["status"] == "needs_information"
    assert result["warnings"]
    assert "https MP4 URL" in result["warnings"][0]


def test_generate_layout_returns_chapters_and_confirmation_prompt():
    result = generate_layout(
        {
            "course_title": "AI for Students",
            "audience": "college students",
            "goal": "Use AI safely for study",
            "duration_minutes": 5,
            "materials": [{"upload_id": "study-notes.txt", "source_type": "raw_text"}],
            "media": [{"type": "youtube", "url": "https://youtu.be/abc123"}],
            "interactive_preferences": ["matching", "reflection_prompt"],
            "answers": {"module_topics_review": "yes", "quiz_decision": "mixed"},
        }
    )

    assert result["status"] == "ready_for_generation"
    assert len(result["chapters"]) >= 3
    assert result["media_plan"]
    assert result["interactive_plan"]
    assert result["proposed_topics"]
    assert "confirm" in result["confirmation_prompt"].lower()


def test_generate_layout_prompts_for_topic_and_quiz_confirmation():
    result = generate_layout(
        {
            "course_title": "AI for Students",
            "audience": "college students",
            "goal": "Use AI safely for study",
            "duration_minutes": 5,
            "materials": [{"upload_id": "study-notes.txt", "source_type": "raw_text"}],
            "media": [{"type": "youtube", "url": "https://youtu.be/abc123"}],
            "interactive_preferences": ["matching", "reflection_prompt"],
        }
    )

    assert result["status"] == "needs_more_information"
    assert result["missing_fields"] == ["module_topics_review"]
    assert "proposed_topics" in result
    assert any("topics" in item.lower() for item in result["next_questions"])


def test_material_ticket_tools_are_allowlisted_and_structured():
    assert "create_material_ticket" in ALLOWED_TOOLS
    assert "generate_chapter_layout" in ALLOWED_TOOLS

    ticket = create_material_ticket({"course_title": "AI for Students"}, _ctx())
    assert ticket["ok"] is True
    assert ticket["data"]["status"] == "needs_information"

    layout = generate_chapter_layout(
        {
            "course_title": "AI for Students",
            "audience": "students",
            "goal": "Use AI safely",
            "duration_minutes": 5,
            "materials": [{"upload_id": "notes.txt"}],
            "answers": {"module_topics_review": "yes", "quiz_decision": "mixed"},
        },
        _ctx(),
    )
    assert layout["ok"] is True
    assert layout["data"]["status"] == "ready_for_generation"
