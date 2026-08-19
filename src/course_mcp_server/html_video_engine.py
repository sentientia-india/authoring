from __future__ import annotations

import html
import json
import re
import uuid
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


SceneType = Literal[
    "title",
    "narration",
    "animated_explanation",
    "process_stepper",
    "hotspot",
    "decision_pause",
    "quiz_checkpoint",
    "summary",
]


class CaptionCue(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    text: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def end_after_start(self) -> "CaptionCue":
        if self.end <= self.start:
            raise ValueError("caption end must be greater than start")
        return self


class VideoScene(BaseModel):
    id: str = Field(pattern=r"^scene_[a-zA-Z0-9_\-]{1,60}$")
    type: SceneType
    title: str = Field(min_length=3, max_length=180)
    duration_seconds: int = Field(ge=3, le=600)
    narration: str = Field(min_length=1, max_length=2000)
    visual_prompt: str = Field(min_length=1, max_length=1000)
    on_screen_text: list[str] = Field(default_factory=list, max_length=8)
    interactions: list[dict[str, Any]] = Field(default_factory=list, max_length=8)
    checkpoint_question_id: str | None = Field(default=None, max_length=80)
    source_refs: list[dict[str, Any]] = Field(default_factory=list, max_length=10)
    captions: list[CaptionCue] = Field(default_factory=list, max_length=60)
    narration_audio_src: str | None = Field(default=None, max_length=300)


class HtmlVideoProject(BaseModel):
    video_id: str = Field(pattern=r"^video_[a-zA-Z0-9_\-]{1,80}$")
    title: str = Field(min_length=3, max_length=220)
    course_id: str = Field(min_length=3, max_length=120)
    language: str = Field(default="English", max_length=80)
    aspect_ratio: Literal["16:9", "9:16", "4:3"] = "16:9"
    poster_title: str | None = Field(default=None, max_length=220)
    scenes: list[VideoScene] = Field(min_length=1, max_length=80)
    global_captions: list[CaptionCue] = Field(default_factory=list, max_length=1000)
    transcript: str | None = Field(default=None, max_length=50000)
    export_mode: Literal["interactive_html", "recordable_html", "scorm_slide_video"] = "interactive_html"

    @property
    def total_duration_seconds(self) -> int:
        return sum(scene.duration_seconds for scene in self.scenes)


def _slug(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return value[:80] or uuid.uuid4().hex[:8]


def split_narration_to_captions(narration: str, total_seconds: int) -> list[CaptionCue]:
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", narration.strip()) if s.strip()]
    if not sentences:
        return []
    segment = max(1.5, total_seconds / len(sentences))
    cues = []
    for index, sentence in enumerate(sentences):
        start = round(index * segment, 2)
        end = round(min(total_seconds, (index + 1) * segment), 2)
        if end <= start:
            end = start + 1.0
        cues.append(CaptionCue(start=start, end=end, text=sentence[:500]))
    return cues


def build_video_project_from_course(course: dict[str, Any], *, max_scenes: int = 12) -> HtmlVideoProject:
    course_id = course.get("course_id") or f"course_{_slug(course.get('course_title', 'course'))}"
    title = course.get("course_title", "Generated Course Video")
    scenes: list[VideoScene] = [
        VideoScene(
            id="scene_intro",
            type="title",
            title=title,
            duration_seconds=8,
            narration=f"Welcome to {title}. This interactive video will guide you through the core decisions, examples, and checks.",
            visual_prompt="Clean training title screen with progress path and professional icons.",
            on_screen_text=[title, "Interactive training video"],
        )
    ]
    scene_count = 1
    for module in course.get("modules", []):
        for lesson in module.get("lessons", []):
            if scene_count >= max_scenes:
                break
            blocks = lesson.get("content_blocks", [])
            text_parts = [b.get("text", "") for b in blocks if b.get("type") in {"intro", "explanation", "example", "scenario", "summary"}]
            narration = " ".join(text_parts).strip() or f"This lesson explains {lesson.get('title', 'the topic')}."
            has_scenario = any(b.get("type") == "scenario" for b in blocks)
            scene_type: SceneType = "decision_pause" if has_scenario else "animated_explanation"
            duration = max(20, min(90, len(narration.split()) // 2))
            scenes.append(
                VideoScene(
                    id=f"scene_{_slug(lesson.get('id', lesson.get('title', str(scene_count))))}",
                    type=scene_type,
                    title=lesson.get("title", "Lesson Scene"),
                    duration_seconds=duration,
                    narration=narration[:1800],
                    visual_prompt=f"Visualize the lesson '{lesson.get('title', '')}' as a clean animated e-learning scene with icons, process arrows, and realistic workplace context.",
                    on_screen_text=[lesson.get("title", "Lesson"), module.get("title", "Module")],
                    interactions=[
                        {
                            "type": "pause_and_choose",
                            "prompt": "What should the learner do first in this situation?",
                            "choices": ["Follow the documented procedure", "Skip to the quickest action", "Wait without communicating"],
                            "correct_index": 0,
                        }
                    ] if has_scenario else [],
                    captions=split_narration_to_captions(narration, duration),
                )
            )
            scene_count += 1
        if scene_count >= max_scenes:
            break
    scenes.append(
        VideoScene(
            id="scene_summary",
            type="summary",
            title="Key Takeaways",
            duration_seconds=20,
            narration="You have completed this interactive video. Review the key decisions, complete the checkpoint, and continue to the practice activity.",
            visual_prompt="Summary screen with three key takeaways and completion badge animation.",
            on_screen_text=["Key Takeaways", "Complete the checkpoint to continue"],
        )
    )
    for s in scenes:
        if not s.captions:
            s.captions = split_narration_to_captions(s.narration, s.duration_seconds)
    return HtmlVideoProject(
        video_id=f"video_{_slug(title)}",
        title=title,
        course_id=course_id,
        poster_title=title,
        scenes=scenes,
        transcript="\n\n".join(scene.narration for scene in scenes),
    )


def _format_vtt_time(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


def render_webvtt(project: HtmlVideoProject) -> str:
    lines = ["WEBVTT", ""]
    offset = 0.0
    cue_index = 1
    for scene in project.scenes:
        cues = scene.captions or split_narration_to_captions(scene.narration, scene.duration_seconds)
        for cue in cues:
            lines.append(str(cue_index))
            lines.append(f"{_format_vtt_time(offset + cue.start)} --> {_format_vtt_time(offset + cue.end)}")
            lines.append(cue.text)
            lines.append("")
            cue_index += 1
        offset += scene.duration_seconds
    return "\n".join(lines)


class HtmlVideoRenderer:
    def __init__(self, static_js_name: str = "sentientia_video_engine.js", static_css_name: str = "sentientia_video_engine.css") -> None:
        self.static_js_name = static_js_name
        self.static_css_name = static_css_name

    def render(self, project: HtmlVideoProject) -> str:
        payload = html.escape(json.dumps(project.model_dump(mode="json"), ensure_ascii=False), quote=True)
        title = html.escape(project.title)
        aspect_class = {"16:9": "aspect-16-9", "9:16": "aspect-9-16", "4:3": "aspect-4-3"}[project.aspect_ratio]
        return f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>{title}</title>
  <link rel=\"stylesheet\" href=\"assets/{self.static_css_name}\" />
</head>
<body>
  <main class=\"sv-shell\" data-video-project=\"{payload}\">
    <section class=\"sv-player {aspect_class}\" aria-label=\"Interactive training video\">
      <div class=\"sv-stage\" id=\"sv-stage\"></div>
      <div class=\"sv-caption\" id=\"sv-caption\" aria-live=\"polite\"></div>
      <div class=\"sv-controls\">
        <button id=\"sv-play\" type=\"button\">Play</button>
        <button id=\"sv-pause\" type=\"button\">Pause</button>
        <button id=\"sv-prev\" type=\"button\">Back</button>
        <button id=\"sv-next\" type=\"button\">Next</button>
        <progress id=\"sv-progress\" max=\"100\" value=\"0\" aria-label=\"Video progress\"></progress>
      </div>
    </section>
    <aside class=\"sv-transcript\">
      <h2>Transcript</h2>
      <pre>{html.escape(project.transcript or '')}</pre>
    </aside>
  </main>
  <script src=\"assets/{self.static_js_name}\"></script>
</body>
</html>"""

    def write_package(self, project: HtmlVideoProject, output_dir: str | Path) -> dict[str, str]:
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        (output / "assets").mkdir(exist_ok=True)
        html_path = output / "interactive-video.html"
        vtt_path = output / "captions.vtt"
        json_path = output / "video-project.json"
        html_path.write_text(self.render(project), encoding="utf-8")
        vtt_path.write_text(render_webvtt(project), encoding="utf-8")
        json_path.write_text(project.model_dump_json(indent=2), encoding="utf-8")
        return {"html": str(html_path), "vtt": str(vtt_path), "json": str(json_path)}


__all__ = [
    "CaptionCue",
    "HtmlVideoProject",
    "HtmlVideoRenderer",
    "VideoScene",
    "build_video_project_from_course",
    "render_webvtt",
    "split_narration_to_captions",
]
