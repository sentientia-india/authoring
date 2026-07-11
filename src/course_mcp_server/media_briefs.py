from __future__ import annotations

"""Deterministic media briefs: no LLM calls, no image generation.

The MCP composes briefs from authored course content; the calling agent
(the user's Claude Code / Codex subscription) renders images with its own
tools and uploads the results via `upload_media_asset`. This keeps all
generation cost on the user's side while the pipeline stays server-gated.
"""

import re
from typing import Any

THEME_STYLE_WORDS = {
    "studio": "teal and cyan accents on deep navy, energetic",
    "compliance": "blue and emerald accents on deep navy, trustworthy",
    "academy": "violet and pink accents on deep navy, scholarly",
}

IMAGE_PROMPT_TEMPLATE = (
    "Flat, modern e-learning illustration, {style_words}, minimal geometric shapes, "
    "soft gradients, high contrast, no text, no letters, 16:9 aspect ratio. "
    "Depict: {subject}."
)


def _first_sentence(text: str, limit: int = 160) -> str:
    clean = re.sub(r"\s+", " ", str(text or "")).strip()
    match = re.match(r"(.+?[.!?])(\s|$)", clean)
    sentence = match.group(1) if match else clean
    return sentence[:limit]


def _slug(value: str, fallback: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-")
    return (slug or fallback)[:40]


def build_media_briefs(content: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Compose image briefs and video slots from authored course content.

    Image briefs: one hero image per lesson (anchored to the intro block),
    plus one for every `media_placeholder` block, skipping anything that
    already carries media. Video slots: one per module (anchored to the
    first example/scenario block without media).
    """
    theme = str(content.get("theme") or "studio")
    style_words = THEME_STYLE_WORDS.get(theme, THEME_STYLE_WORDS["studio"])
    image_briefs: list[dict[str, Any]] = []
    video_slots: list[dict[str, Any]] = []

    for module_index, module in enumerate(content.get("modules", []), start=1):
        module_video_done = False
        for lesson_index, lesson in enumerate(module.get("lessons", []), start=1):
            lesson_id = lesson.get("id") or f"lesson_{module_index}_{lesson_index}"
            lesson_title = lesson.get("title") or f"Lesson {lesson_index}"
            blocks = [block for block in lesson.get("content_blocks", []) if isinstance(block, dict)]
            intro = next((block for block in blocks if block.get("type") == "intro"), None)
            if intro and not intro.get("media"):
                subject = f"{lesson_title} - {_first_sentence(intro.get('text', ''))}"
                image_briefs.append(
                    {
                        "brief_id": f"img_{module_index}_{lesson_index}_hero",
                        "lesson_id": lesson_id,
                        "block_id": intro.get("id"),
                        "filename": f"m{module_index}-l{lesson_index}-{_slug(lesson_title, 'hero')}.png",
                        "purpose": f"Hero illustration for the lesson '{lesson_title}'",
                        "prompt": IMAGE_PROMPT_TEMPLATE.format(style_words=style_words, subject=subject),
                        "style": {"theme": theme, "aspect": "16:9", "format": "png"},
                    }
                )
            for block in blocks:
                if block.get("type") == "media_placeholder" and not block.get("media"):
                    image_briefs.append(
                        {
                            "brief_id": f"img_{module_index}_{lesson_index}_{_slug(block.get('id', ''), 'block')}",
                            "lesson_id": lesson_id,
                            "block_id": block.get("id"),
                            "filename": f"m{module_index}-l{lesson_index}-{_slug(block.get('id', ''), 'media')}.png",
                            "purpose": _first_sentence(block.get("text", "")) or f"Supporting visual for '{lesson_title}'",
                            "prompt": IMAGE_PROMPT_TEMPLATE.format(
                                style_words=style_words,
                                subject=_first_sentence(block.get("text", "")) or lesson_title,
                            ),
                            "style": {"theme": theme, "aspect": "16:9", "format": "png"},
                        }
                    )
            if not module_video_done:
                anchor = next(
                    (
                        block
                        for block in blocks
                        if block.get("type") in {"example", "scenario"} and not block.get("media")
                    ),
                    None,
                )
                if anchor:
                    module_video_done = True
                    video_slots.append(
                        {
                            "slot_id": f"vid_module_{module_index}",
                            "lesson_id": lesson_id,
                            "block_id": anchor.get("id"),
                            "purpose": f"Short video reinforcing '{lesson_title}'",
                            "suggested_search": f"short explainer video about {lesson_title}",
                            "accepted": [
                                "https YouTube / Vimeo / Loom embed URL",
                                "mp4 or webm file via upload_media_asset",
                            ],
                        }
                    )
    return {"image_briefs": image_briefs, "video_slots": video_slots}


__all__ = ["build_media_briefs"]
