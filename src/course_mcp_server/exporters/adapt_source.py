from __future__ import annotations

"""Convert an MCP course payload into an Adapt Authoring import zip.

Produces an Adapt *framework source* package that the Adapt Authoring Tool's
"Import source" accepts, so courses generated through the MCP can be polished
in the pre-made WYSIWYG editor. Structure (validated against the authoring
tool's importsourcecheck.js):

    package.json                     # framework version
    src/course/config.json
    src/course/en/course.json
    src/course/en/contentObjects.json
    src/course/en/articles.json
    src/course/en/blocks.json
    src/course/en/components.json
    src/course/en/assets/...        # packaged images / local video

Mapping: module -> page, lesson -> article, content block -> block with one
component. Uses only core bundled components (text, graphic, media, mcq,
matching, accordion) so imports never require plugin installs.
"""

import json
import os
import re
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ADAPT_FRAMEWORK_VERSION = "5.56.2"

# Theme/menu plugin stubs must be present in the zip (the importer dereferences
# them unconditionally). Versions match the authoring tool's bundled plugins so
# the import categorises them as already-installed and installs nothing.
ADAPT_THEME = {"name": "adapt-contrib-vanilla", "theme": "vanilla", "version": "9.37.1", "displayName": "Vanilla", "framework": ">=5.19.1"}
ADAPT_MENU = {"name": "adapt-contrib-boxMenu", "menu": "boxMenu", "version": "7.7.0", "displayName": "Box menu", "framework": ">=5.19.1"}
_EMBED_FALLBACK = re.compile(r"^https://", re.IGNORECASE)


def _ids() -> "_IdFactory":
    return _IdFactory()


class _IdFactory:
    def __init__(self) -> None:
        self._counter = 0

    def next(self, prefix: str) -> str:
        self._counter += 1
        return f"{prefix}-{self._counter:04d}"


def _text_component(ids: _IdFactory, block_id: str, title: str, body_parts: list[str]) -> dict:
    body = "".join(f"<p>{part}</p>" for part in body_parts if part)
    return {
        "_id": ids.next("c"),
        "_parentId": block_id,
        "_type": "component",
        "_component": "text",
        "_layout": "full",
        "title": title,
        "displayTitle": title,
        "body": body,
    }


def _graphic_component(ids: _IdFactory, block_id: str, title: str, media: dict) -> dict:
    src = f"course/en/assets/{Path(str(media.get('src', ''))).name}"
    return {
        "_id": ids.next("c"),
        "_parentId": block_id,
        "_type": "component",
        "_component": "graphic",
        "_layout": "full",
        "title": title,
        "displayTitle": title,
        "body": f"<p>{media.get('caption', '')}</p>" if media.get("caption") else "",
        "_graphic": {"large": src, "small": src, "alt": media.get("alt", "")},
    }


def _media_component(ids: _IdFactory, block_id: str, title: str, media: dict) -> dict:
    src = f"course/en/assets/{Path(str(media.get('src', ''))).name}"
    return {
        "_id": ids.next("c"),
        "_parentId": block_id,
        "_type": "component",
        "_component": "media",
        "_layout": "full",
        "title": title,
        "displayTitle": title,
        "body": f"<p>{media.get('caption', '')}</p>" if media.get("caption") else "",
        "_media": {"mp4": src},
        "_useClosedCaptions": False,
        "_setCompletionOn": "play",
    }


def _mcq_component(ids: _IdFactory, block_id: str, question: dict) -> dict:
    correct = set(question.get("correct_answers", []))
    return {
        "_id": ids.next("c"),
        "_parentId": block_id,
        "_type": "component",
        "_component": "mcq",
        "_layout": "full",
        "title": question.get("id", "Question"),
        "displayTitle": "Knowledge check",
        "body": f"<p>{question.get('question', '')}</p>",
        "instruction": "Choose the best answer.",
        "_attempts": 2,
        "_shouldDisplayAttempts": False,
        "_isRandom": False,
        "_selectable": 1,
        "_items": [
            {"text": option, "_shouldBeSelected": option in correct}
            for option in question.get("options", [])
        ],
        "_feedback": {
            "correct": question.get("explanation", "Correct."),
            "_incorrect": {"final": question.get("explanation", "Review the lesson and try again.")},
        },
    }


def _matching_component(ids: _IdFactory, block_id: str, activity: dict) -> dict:
    items = []
    for item in activity.get("items", []):
        prompt = item.get("prompt") or item.get("left") or item.get("front") or ""
        match = item.get("match") or item.get("right") or item.get("back") or ""
        if not prompt or not match:
            continue
        items.append({"text": prompt, "_options": [{"text": match, "_isCorrect": True}]})
    return {
        "_id": ids.next("c"),
        "_parentId": block_id,
        "_type": "component",
        "_component": "matching",
        "_layout": "full",
        "title": activity.get("title", "Matching"),
        "displayTitle": activity.get("title", "Matching"),
        "body": f"<p>{activity.get('objective') or activity.get('instructions') or ''}</p>",
        "instruction": "Match each item to the correct answer.",
        "_attempts": 2,
        "_items": items,
        "_feedback": {"correct": "Well matched.", "_incorrect": {"final": "Check the pairs and try again."}},
    }


def _accordion_component(ids: _IdFactory, block_id: str, activity: dict) -> dict:
    items = []
    for item in activity.get("items", []):
        title = item.get("title") or item.get("front") or item.get("label") or "Item"
        body = item.get("detail") or item.get("back") or item.get("text") or ""
        items.append({"title": title, "body": f"<p>{body}</p>"})
    return {
        "_id": ids.next("c"),
        "_parentId": block_id,
        "_type": "component",
        "_component": "accordion",
        "_layout": "full",
        "title": activity.get("title", "Review"),
        "displayTitle": activity.get("title", "Review"),
        "body": f"<p>{activity.get('objective') or activity.get('instructions') or ''}</p>",
        "_items": items,
    }


def _activity_fallback_component(ids: _IdFactory, block_id: str, activity: dict) -> dict:
    """Interactive types with no core Adapt equivalent become editable rich text."""
    parts = [activity.get("objective") or activity.get("instructions") or ""]
    for item in activity.get("items", []):
        scenario = item.get("scenario") or item.get("prompt") or ""
        if scenario:
            parts.append(f"<b>Scenario:</b> {scenario}")
        for choice in item.get("choices", []) or item.get("options", []) or []:
            label = choice.get("label") or choice.get("text") or ""
            marker = "✓ " if (choice.get("result") == "best") else ""
            parts.append(f"&bull; {marker}{label}")
    activity_type = str(activity.get("activity_type") or activity.get("type") or "activity").replace("_", " ")
    return _text_component(ids, block_id, f"{activity.get('title', 'Activity')} ({activity_type})", parts)


def _component_for_activity(ids: _IdFactory, block_id: str, activity: dict) -> dict:
    activity_type = str(activity.get("activity_type") or activity.get("type") or "").lower()
    if "matching" in activity_type:
        component = _matching_component(ids, block_id, activity)
        if component["_items"]:
            return component
    if "flashcard" in activity_type or "accordion" in activity_type or "tabs" in activity_type:
        component = _accordion_component(ids, block_id, activity)
        if component["_items"]:
            return component
    return _activity_fallback_component(ids, block_id, activity)


def _segment(text: str, limit: int = 1200) -> list[str]:
    clean = re.sub(r"\s+", " ", str(text or "")).strip()
    return [clean[i : i + limit] for i in range(0, len(clean), limit)] or [""]


def build_adapt_source_package(course: dict, output_dir: str, upload_dir: str | None = None) -> dict:
    """Build the Adapt import zip. Returns {package_path, files}."""
    root = Path(output_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    slug = str(course.get("course_slug", "course")).strip("/") or "course"
    package_path = root / f"{slug}-adapt.zip"

    ids = _ids()
    course_id = "adapt-course"
    title = course.get("course_title", "Course")

    course_json = {
        "_id": course_id,
        "_type": "course",
        "title": title,
        "displayTitle": title,
        "description": f"For {course.get('audience', 'learners')}.",
        "body": f"<p>{course.get('audience', '')}</p>",
    }
    config_json = {
        "_type": "config",
        "_defaultLanguage": "en",
        "_theme": "adapt-contrib-vanilla",
        "_menu": "adapt-contrib-boxMenu",
        "_completionCriteria": {"_requireContentCompleted": True, "_requireAssessmentCompleted": False},
    }

    content_objects: list[dict] = []
    articles: list[dict] = []
    blocks: list[dict] = []
    components: list[dict] = []
    asset_files: set[str] = set()

    def collect_media(media: dict | None) -> str | None:
        if not media:
            return None
        # Accept both the player payload shape (src) and the authored shape (upload_id/url).
        src = str(media.get("src") or "")
        if not src and media.get("upload_id"):
            src = f"assets/media/{media['upload_id']}"
            media["src"] = src
        if not src and media.get("url"):
            src = str(media["url"])
            media["src"] = src
        if src.startswith("assets/media/"):
            asset_files.add(Path(src).name)
        return src

    def add_block(article_id: str, order: int, block_title: str, component: dict | None, body_parts: list[str] | None = None) -> None:
        block_id = ids.next("b")
        blocks.append(
            {
                "_id": block_id,
                "_parentId": article_id,
                "_type": "block",
                "_sortOrder": order,
                "title": block_title,
                "displayTitle": "",
                "body": "",
            }
        )
        if component is not None:
            component["_parentId"] = block_id
            components.append(component)
        else:
            components.append(_text_component(ids, block_id, block_title, body_parts or [""]))

    for module_index, module in enumerate(course.get("modules", []), start=1):
        page_id = ids.next("co")
        content_objects.append(
            {
                "_id": page_id,
                "_parentId": course_id,
                "_type": "page",
                "title": module.get("title", f"Module {module_index}"),
                "displayTitle": module.get("title", f"Module {module_index}"),
                "body": "",
            }
        )
        for lesson_index, lesson in enumerate(module.get("lessons", []), start=1):
            article_id = ids.next("a")
            articles.append(
                {
                    "_id": article_id,
                    "_parentId": page_id,
                    "_type": "article",
                    "_sortOrder": lesson_index,
                    "title": lesson.get("title", f"Lesson {lesson_index}"),
                    "displayTitle": lesson.get("title", f"Lesson {lesson_index}"),
                    "body": f"<p>{lesson.get('objective', '')}</p>",
                }
            )
            order = 0
            for block in lesson.get("content_blocks", []):
                if not isinstance(block, dict):
                    continue
                order += 1
                label = str(block.get("type", "content")).replace("_", " ").title()
                media = block.get("media")
                src = collect_media(media)
                kind = media.get("kind") if media else None
                is_packaged = bool(src) and src.startswith("assets/media/")
                text_parts = _segment(block.get("text", ""))

                if kind == "image" and src:
                    # Text and image become adjacent blocks so both stay editable.
                    if block.get("text"):
                        add_block(article_id, order, label, None, text_parts)
                        order += 1
                    add_block(article_id, order, label, _graphic_component(ids, "pending", label, media))
                elif kind == "video" and is_packaged:
                    if block.get("text"):
                        add_block(article_id, order, label, None, text_parts)
                        order += 1
                    add_block(article_id, order, label, _media_component(ids, "pending", label, media))
                else:
                    # External video embeds and links become editable anchors in the text.
                    if kind in {"video", "link"} and src:
                        prefix = "Watch: " if kind == "video" else ""
                        text_parts.append(f'<a href="{src}" target="_blank">{prefix}{media.get("caption") or src}</a>')
                    add_block(article_id, order, label, None, text_parts)
            for activity in lesson.get("activities", []):
                order += 1
                add_block(article_id, order, activity.get("title", "Activity"), _component_for_activity(ids, "pending", activity))
            for question in lesson.get("quiz_questions", []):
                order += 1
                add_block(article_id, order, "Knowledge check", _mcq_component(ids, "pending", question))

    final = course.get("final_assessment") or {}
    if final.get("questions"):
        page_id = ids.next("co")
        content_objects.append(
            {
                "_id": page_id,
                "_parentId": course_id,
                "_type": "page",
                "title": final.get("title", "Final Assessment"),
                "displayTitle": final.get("title", "Final Assessment"),
                "body": "",
            }
        )
        article_id = ids.next("a")
        articles.append(
            {
                "_id": article_id,
                "_parentId": page_id,
                "_type": "article",
                "_sortOrder": 1,
                "title": final.get("title", "Final Assessment"),
                "displayTitle": final.get("title", "Final Assessment"),
                "body": "",
            }
        )
        for order, question in enumerate(final.get("questions", []), start=1):
            add_block(article_id, order, "Assessment question", _mcq_component(ids, "pending", question))

    files: list[str] = []
    with ZipFile(package_path, "w", ZIP_DEFLATED) as package:
        def write(name: str, payload) -> None:
            package.writestr(name, json.dumps(payload, indent=2))
            files.append(name)

        write("package.json", {"name": slug, "version": ADAPT_FRAMEWORK_VERSION})
        write(f"src/theme/{ADAPT_THEME['name']}/bower.json", ADAPT_THEME)
        write(f"src/menu/{ADAPT_MENU['name']}/bower.json", ADAPT_MENU)
        write("src/course/config.json", config_json)
        write("src/course/en/course.json", course_json)
        write("src/course/en/contentObjects.json", content_objects)
        write("src/course/en/articles.json", articles)
        write("src/course/en/blocks.json", blocks)
        write("src/course/en/components.json", components)
        if upload_dir:
            uploads = Path(upload_dir)
            for name in sorted(asset_files):
                source = uploads / name
                if source.is_file():
                    package.write(source, f"src/course/en/assets/{name}")
                    files.append(f"src/course/en/assets/{name}")

    return {"package_path": str(package_path), "files": files}


__all__ = ["build_adapt_source_package", "ADAPT_FRAMEWORK_VERSION"]
