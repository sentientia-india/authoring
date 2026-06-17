from __future__ import annotations

import csv
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile
from typing import Any


class StorylineHandoffError(RuntimeError):
    pass


def _safe_slug(slug: str) -> str:
    cleaned = ''.join(ch for ch in slug.lower() if ch.isalnum() or ch == '-')
    cleaned = '-'.join(part for part in cleaned.split('-') if part)
    if len(cleaned) < 3:
        raise StorylineHandoffError('course_slug must contain at least 3 safe characters')
    return cleaned[:100]


def _lesson_rows(course: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for module_index, module in enumerate(course.get('modules', []) or [], start=1):
        for lesson_index, lesson in enumerate(module.get('lessons', []) or [], start=1):
            rows.append({
                'module_index': module_index,
                'module_title': module.get('title', f'Module {module_index}'),
                'lesson_index': lesson_index,
                'lesson_title': lesson.get('title', f'Lesson {lesson_index}'),
                'duration_minutes': lesson.get('duration_minutes', ''),
                'objective_ids': lesson.get('objective_ids', []),
                'content_blocks': lesson.get('content_blocks', []),
                'activities': lesson.get('activities', []),
                'quiz_questions': lesson.get('quiz_questions', []),
            })
    return rows


def _write_storyboard(course: dict[str, Any], path: Path) -> None:
    lines: list[str] = []
    lines.append(f"# Storyboard - {course.get('course_title', 'Untitled Course')}")
    lines.append('')
    lines.append(f"Audience: {course.get('audience', '-')}")
    lines.append(f"Difficulty: {course.get('difficulty', '-')}")
    lines.append(f"Duration: {course.get('estimated_duration_minutes', '-')} minutes")
    lines.append('')
    lines.append('## Learning Objectives')
    for obj in course.get('learning_objectives', []) or []:
        if isinstance(obj, dict):
            lines.append(f"- **{obj.get('id', '')}**: {obj.get('text', '')}")
        else:
            lines.append(f"- {obj}")
    lines.append('')

    slide_no = 1
    lines.append('## Slides / Screens')
    for row in _lesson_rows(course):
        lines.append('')
        lines.append(f"### Slide {slide_no}: {row['module_title']} - {row['lesson_title']}")
        lines.append("Type: Lesson screen")
        lines.append(f"Estimated time: {row['duration_minutes']} min")
        lines.append(f"Objectives: {', '.join(row['objective_ids']) if row['objective_ids'] else '-'}")
        lines.append('')
        lines.append('**On-screen content:**')
        for block in row['content_blocks']:
            lines.append(f"- [{block.get('type', 'content')}] {block.get('text', '')}")
        if row['activities']:
            lines.append('')
            lines.append('**Interactions to build in Storyline:**')
            for activity in row['activities']:
                lines.append(f"- {activity.get('type', 'activity')}: {activity.get('title', '')} - {activity.get('instructions', '')}")
        slide_no += 1

    assessment = course.get('final_assessment') or {}
    questions = assessment.get('questions', []) if isinstance(assessment, dict) else []
    if questions:
        lines.append('')
        lines.append('## Assessment Slides')
        for question in questions:
            lines.append('')
            lines.append(f"### Slide {slide_no}: Question {question.get('id', '')}")
            lines.append(f"Question type: {question.get('type', '')}")
            lines.append(f"Question: {question.get('question', '')}")
            if question.get('options'):
                lines.append('Options:')
                for option in question.get('options', []):
                    lines.append(f"- {option}")
            lines.append(f"Correct answer(s): {', '.join(question.get('correct_answers', []))}")
            lines.append(f"Feedback: {question.get('explanation', '')}")
            slide_no += 1

    path.write_text('\n'.join(lines), encoding='utf-8')


def _write_quiz_csv(course: dict[str, Any], path: Path) -> None:
    assessment = course.get('final_assessment') or {}
    questions = assessment.get('questions', []) if isinstance(assessment, dict) else []
    with path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['id', 'type', 'question', 'options', 'correct_answers', 'explanation', 'objective_ids'])
        writer.writeheader()
        for q in questions:
            writer.writerow({
                'id': q.get('id', ''),
                'type': q.get('type', ''),
                'question': q.get('question', ''),
                'options': ' || '.join(q.get('options', []) or []),
                'correct_answers': ' || '.join(q.get('correct_answers', []) or []),
                'explanation': q.get('explanation', ''),
                'objective_ids': ' || '.join(q.get('objective_ids', []) or []),
            })


def _write_voiceover_script(course: dict[str, Any], path: Path) -> None:
    lines = [f"# Voiceover Script - {course.get('course_title', 'Untitled Course')}", '']
    for row in _lesson_rows(course):
        lines.append(f"## {row['module_title']} - {row['lesson_title']}")
        for block in row['content_blocks']:
            if block.get('type') in {'intro', 'explanation', 'example', 'scenario', 'summary'}:
                lines.append(str(block.get('text', '')).strip())
                lines.append('')
    path.write_text('\n'.join(lines), encoding='utf-8')


def _build_spec(course: dict[str, Any]) -> dict[str, Any]:
    screens = []
    screen_no = 1
    for row in _lesson_rows(course):
        screens.append({
            'screen_number': screen_no,
            'screen_type': 'lesson',
            'module_title': row['module_title'],
            'lesson_title': row['lesson_title'],
            'storyline_layout': 'title_content_activity',
            'estimated_duration_minutes': row['duration_minutes'],
            'objective_ids': row['objective_ids'],
            'recommended_layers': ['base', 'feedback'] if row['activities'] else ['base'],
            'recommended_triggers': ['Next button jumps to next slide', 'Activity submit shows feedback layer'] if row['activities'] else ['Next button jumps to next slide'],
        })
        screen_no += 1
    return {
        'course_title': course.get('course_title'),
        'course_slug': course.get('course_slug'),
        'build_target': 'Articulate Storyline manual rebuild package',
        'native_story_file_generated': False,
        'reason': 'No public reliable SDK is assumed for generating editable .story files. This package is a developer handoff.',
        'screens': screens,
    }


def _interaction_blueprint(course: dict[str, Any]) -> dict[str, Any]:
    interactions = []
    for row in _lesson_rows(course):
        for activity in row['activities']:
            interactions.append({
                'module_title': row['module_title'],
                'lesson_title': row['lesson_title'],
                'activity_id': activity.get('id'),
                'activity_type': activity.get('type'),
                'title': activity.get('title'),
                'instructions': activity.get('instructions'),
                'data': activity.get('data', {}),
                'storyline_suggestion': 'Use layers/states/triggers to simulate this interaction.',
            })
    return {'interactions': interactions}


def build_storyline_handoff_package(course: dict[str, Any], output_dir: Path | str, course_slug: str | None = None) -> dict[str, Any]:
    slug = _safe_slug(course_slug or course.get('course_slug', 'course-handoff'))
    root = Path(output_dir).resolve() / f"{slug}_storyline_handoff"
    root.mkdir(parents=True, exist_ok=True)
    assets_dir = root / 'assets'
    assets_dir.mkdir(exist_ok=True)

    files = {
        'storyboard.md': root / 'storyboard.md',
        'storyline_build_spec.json': root / 'storyline_build_spec.json',
        'quiz_import.csv': root / 'quiz_import.csv',
        'interaction_blueprint.json': root / 'interaction_blueprint.json',
        'voiceover_script.md': root / 'voiceover_script.md',
        'assets/README.md': assets_dir / 'README.md',
    }

    _write_storyboard(course, files['storyboard.md'])
    _write_quiz_csv(course, files['quiz_import.csv'])
    _write_voiceover_script(course, files['voiceover_script.md'])
    files['storyline_build_spec.json'].write_text(json.dumps(_build_spec(course), indent=2), encoding='utf-8')
    files['interaction_blueprint.json'].write_text(json.dumps(_interaction_blueprint(course), indent=2), encoding='utf-8')
    files['assets/README.md'].write_text('Place generated images, icons, voiceover audio, and video files here.\n', encoding='utf-8')

    package_path = root.with_suffix('.zip')
    with ZipFile(package_path, 'w', compression=ZIP_DEFLATED) as zf:
        for arcname, file_path in files.items():
            zf.write(file_path, arcname)

    return {
        'course_slug': slug,
        'artifact_dir': str(root),
        'package_path': str(package_path),
        'files': list(files.keys()),
        'native_story_file_generated': False,
        'note': 'This is a Storyline handoff package, not a native editable .story file.',
    }
