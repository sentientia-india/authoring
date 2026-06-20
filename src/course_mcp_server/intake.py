from __future__ import annotations

import hashlib
from urllib.parse import urlparse

from .schemas import ChapterLayoutRequest, MaterialTicketRequest

REQUIRED_FIELDS = ("course_title", "audience", "goal", "duration_minutes")
YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "youtu.be", "www.youtube-nocookie.com"}


def _ticket_id(ticket: dict) -> str:
    raw = repr(
        (
            ticket.get("course_title"),
            ticket.get("audience"),
            ticket.get("goal"),
            ticket.get("duration_minutes"),
        )
    ).encode("utf-8", errors="ignore")
    return f"ticket_{hashlib.sha256(raw).hexdigest()[:12]}"


def _media_warning(media: dict) -> str | None:
    parsed = urlparse(media.get("url", ""))
    media_type = media.get("type")
    if parsed.scheme != "https":
        if media_type == "mp4":
            return "MP4 media must use an https MP4 URL."
        return f"{media_type} media must use an https URL, not a local path or insecure URL."
    host = parsed.netloc.lower()
    if media_type == "youtube" and host not in YOUTUBE_HOSTS:
        return "YouTube media must use youtube.com, youtu.be, or youtube-nocookie.com."
    if media_type == "mp4" and not parsed.path.lower().endswith(".mp4"):
        return "MP4 media must use an https MP4 URL."
    return None


def _missing_fields(ticket: dict, warnings: list[str]) -> list[str]:
    missing = [field for field in REQUIRED_FIELDS if not ticket.get(field)]
    if not ticket.get("materials"):
        missing.append("materials")
    if warnings:
        missing.append("media")
    return missing


def _questions(missing: list[str]) -> list[str]:
    prompts = {
        "course_title": "What is the exact course title?",
        "audience": "Who are the learners and what is their current level?",
        "goal": "What should learners be able to do after the course?",
        "duration_minutes": "How many minutes should the full course take?",
        "materials": "Which uploaded source, notes, SOP, PDF, PPT, DOCX, transcript, or raw text should be used?",
        "media": "Please provide only approved YouTube URLs or HTTPS MP4 URLs for course videos.",
    }
    return [prompts[field] for field in missing if field in prompts]


def _proposed_topics(ticket: dict) -> list[str]:
    course_title = ticket.get("course_title") or "the course"
    audience = ticket.get("audience") or "the learners"
    goal = ticket.get("goal") or "the learning goal"
    topic_root = str(course_title).strip()
    return [
        f"What {topic_root} is trying to achieve for {audience}",
        f"Core ideas, terms, and rules behind {goal}",
        f"Worked examples and common mistakes in {topic_root}",
        f"Practice, quiz, and reflection for {topic_root}",
    ]


def _question_flow(ticket: dict) -> list[dict]:
    topics = _proposed_topics(ticket)
    return [
        {
            "step": 1,
            "id": "course_brief",
            "prompt": "What course are we building, and who is it for?",
        },
        {
            "step": 2,
            "id": "course_goal",
            "prompt": "What should learners be able to do after the course?",
        },
        {
            "step": 3,
            "id": "module_topics_review",
            "prompt": "I propose these module topics: "
            + "; ".join(topics)
            + ". Are these topics good, or should I revise them?",
            "proposed_topics": topics,
        },
        {
            "step": 4,
            "id": "quiz_decision",
            "prompt": "Should the course include a quiz? If yes, choose the quiz model: MCQ, scenario, mixed, or no quiz.",
            "options": ["mcq", "scenario", "mixed", "no_quiz"],
        },
    ]


def create_ticket(payload: dict) -> dict:
    req = MaterialTicketRequest.model_validate(payload)
    ticket = req.model_dump(mode="json")
    warnings = [warning for item in ticket["media"] if (warning := _media_warning(item))]
    missing = _missing_fields(ticket, warnings)
    questions = _questions(missing)
    if not questions:
        questions = [item["prompt"] for item in _question_flow(ticket)]
    return {
        "ticket_id": _ticket_id(ticket),
        "status": "needs_information" if missing else "ready_for_layout",
        "missing_fields": missing,
        "questions": questions,
        "question_flow": _question_flow(ticket),
        "proposed_topics": _proposed_topics(ticket),
        "warnings": warnings,
        "normalized_ticket": ticket,
    }


def generate_layout(payload: dict) -> dict:
    req = ChapterLayoutRequest.model_validate(payload)
    ticket = req.model_dump(mode="json")
    ticket_result = create_ticket(ticket)
    missing = ticket_result["missing_fields"]
    answers = {str(key).lower(): str(value).strip().lower() for key, value in (ticket.get("answers") or {}).items()}
    topics_ok = answers.get("module_topics_review") in {"yes", "y", "approved", "ok", "good", "confirm", "confirmed"}
    quiz_choice = answers.get("quiz_decision") or answers.get("quiz_model")
    if not missing and not topics_ok:
        return {
            "status": "needs_more_information",
            "missing_fields": ["module_topics_review"],
            "next_questions": [
                "Are these proposed module topics good, or should I revise them?",
                "I can also adjust the topic order if you want a different flow.",
            ],
            "chapters": [],
            "media_plan": [],
            "interactive_plan": [],
            "confirmation_prompt": "Review the proposed module topics before chapter layout generation.",
            "proposed_topics": ticket_result["proposed_topics"],
        }
    if not missing and topics_ok and not quiz_choice:
        return {
            "status": "needs_more_information",
            "missing_fields": ["quiz_decision"],
            "next_questions": [
                "Should the course include a quiz?",
                "If yes, choose the quiz model: MCQ, scenario, mixed, or no quiz.",
            ],
            "chapters": [],
            "media_plan": [],
            "interactive_plan": [],
            "confirmation_prompt": "Confirm whether the course should include a quiz before chapter layout generation.",
            "proposed_topics": ticket_result["proposed_topics"],
        }
    if missing:
        return {
            "status": "needs_more_information",
            "missing_fields": missing,
            "next_questions": ticket_result["questions"],
            "chapters": [],
            "media_plan": [],
            "interactive_plan": [],
            "confirmation_prompt": "Answer the missing material-ticket questions before chapter layout generation.",
            "proposed_topics": ticket_result["proposed_topics"],
        }

    minutes = ticket["duration_minutes"] or 5
    chapter_minutes = max(1, minutes // 4)
    proposed_topics = ticket_result["proposed_topics"]
    chapters = [
        {
            "chapter_id": "chapter_1",
            "title": proposed_topics[0],
            "objective": f"Explain why {ticket['goal']} matters for {ticket['audience']}.",
            "duration_minutes": chapter_minutes,
        },
        {
            "chapter_id": "chapter_2",
            "title": proposed_topics[1],
            "objective": "Extract the main ideas from the supplied material.",
            "duration_minutes": chapter_minutes,
        },
        {
            "chapter_id": "chapter_3",
            "title": proposed_topics[2],
            "objective": "Apply the ideas through interactive practice.",
            "duration_minutes": chapter_minutes,
        },
        {
            "chapter_id": "chapter_4",
            "title": proposed_topics[3],
            "objective": "Complete a short assessment and identify next steps.",
            "duration_minutes": max(1, minutes - (chapter_minutes * 3)),
        },
    ]
    media_plan = [
        {
            "chapter_id": f"chapter_{min(index + 1, len(chapters))}",
            "type": media["type"],
            "url": media["url"],
            "title": media.get("title") or "Course media",
        }
        for index, media in enumerate(ticket["media"])
    ]
    preferences = ticket["interactive_preferences"] or ["matching", "reflection_prompt"]
    interactive_plan = [
        {
            "chapter_id": f"chapter_{min(index + 2, len(chapters))}",
            "activity_type": preference,
            "purpose": "Turn the material into learner action before assessment.",
        }
        for index, preference in enumerate(preferences)
    ]
    return {
        "status": "ready_for_generation",
        "missing_fields": [],
        "next_questions": [
            "Do you want to add more source material, videos, or activity preferences before generation?"
        ],
        "chapters": chapters,
        "media_plan": media_plan,
        "interactive_plan": interactive_plan,
        "proposed_topics": proposed_topics,
        "quiz_decision": quiz_choice or "mixed",
        "confirmation_prompt": "Review this chapter layout. Add more material or confirm to generate modules, lessons, activities, assessment, and one SCORM package.",
    }
