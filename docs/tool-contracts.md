# MCP Tool Contracts

## Tool exposure rule

Only the tools below should be exposed to Codex in MVP. Any new tool must be added to this document, implemented with a Pydantic schema, tested, and explicitly added to the allowlist.

## 1. `generate_course_outline`

### Purpose

Create a structured course outline.

### Input

```json
{
  "topic": "string",
  "audience": "string",
  "duration_minutes": 60,
  "difficulty": "beginner|intermediate|advanced",
  "source_text": "optional string",
  "language": "English"
}
```

### Output

```json
{
  "course_title": "string",
  "audience": "string",
  "difficulty": "beginner|intermediate|advanced",
  "language": "string",
  "learning_objectives": ["string"],
  "modules": [
    {
      "title": "string",
      "lessons": [
        {"title": "string", "objective": "string", "duration_minutes": 10}
      ]
    }
  ],
  "assessment_plan": "string",
  "source_used": true,
  "source_risk_flags": ["instruction_injection"],
  "instructional_design_notes": ["string"]
}
```

## 2. `generate_lesson_draft`

Creates a lesson with explanation, examples, activity, summary, and checks for understanding.

## 3. `generate_quiz_bank`

Creates a quiz with MCQs, answer keys, explanations, and difficulty labels.

## 4. `generate_roleplay_scenario`

Creates a scenario, roles, situation setup, dialogue prompts, expected behaviors, and scoring rubric.

## 5. `validate_course_schema`

Validates a course payload against the expected JSON schema. Does not publish anything.

## 6. `build_scorm_package_scaffold`

Creates a safe package scaffold. Production publishing still requires approval.
The generated zip is internally checked for required files, readable zip structure, manifest root, and SCO resource declaration.

### Output

```json
{
  "course_title": "string",
  "course_slug": "string",
  "scorm_version": "1.2|2004",
  "artifact_path": "string",
  "package_path": "string",
  "files": [
    "imsmanifest.xml",
    "index.html",
    "module-1.html",
    "assets/styles.css",
    "assets/course.js",
    "assets/scorm_api.js",
    "assets/study-map.svg",
    "assets/prompt-lab.svg"
  ],
  "note": "string"
}
```

## 7. `get_course_generation_status`

Returns job status for a known job ID. Must not reveal unrelated jobs.

Status lookup is scoped by tenant. Unknown jobs and jobs owned by another tenant return `not_found`.
