# MCP Tool Contracts

## Tool Exposure Rule

Only the tools below are exposed to Codex. Do not expose shell, exec, raw file read/write, environment, database query, Docker, prompt dump, or raw log tools.

Every MCP tool must:

- have a Pydantic request/response schema in `src/course_mcp_server/schemas.py`
- be explicitly allowlisted in `src/course_mcp_server/security.py`
- be registered in `src/course_mcp_server/tools.py`
- return structured JSON
- redact secrets and internal paths
- have tests for exposure and security behavior

## Production Course Workflow

```text
create_material_ticket
-> generate_chapter_layout
-> create_course_project
-> ingest_course_source
-> generate_course_blueprint
-> generate_module_pack
-> generate_lesson_pack
-> generate_interactive_activity
-> generate_assessment_bank
-> validate_instructional_quality
-> build_export_package
-> build_storyline_handoff_package
-> request_publish_approval
```

## Exposed Tools

## 1. `create_material_ticket`

Collects the user's initial course brief without touching raw server files. It returns missing fields and questions that the UI/GPT layer should ask before generation continues.

Input:

```json
{
  "course_title": "AI for Students",
  "audience": "college students",
  "goal": "Use AI safely for study",
  "duration_minutes": 5,
  "materials": [{"upload_id": "study-notes.txt", "source_type": "raw_text"}],
  "media": [{"type": "youtube", "url": "https://www.youtube.com/watch?v=abc123"}],
  "interactive_preferences": ["matching", "reflection_prompt"]
}
```

It accepts controlled upload IDs, approved YouTube URLs, and HTTPS MP4 URLs. It must not accept local paths or arbitrary file browsing.

## 2. `generate_chapter_layout`

Turns a complete material ticket into a confirmable chapter plan. If required information is still missing, it returns `needs_more_information` with follow-up questions instead of generating content.

Output includes:

- `chapters`
- `media_plan`
- `interactive_plan`
- `confirmation_prompt`

The next step should ask the user to add more materials/media or confirm before generating modules, lessons, activities, assessments, and export.

## 3. `create_course_project`

Creates a tenant-scoped course project with `draft` status.

Input:

```json
{
  "course_title": "Ramp Safety",
  "audience": "ramp agents",
  "language": "English",
  "compliance_domain": "airline"
}
```

## 4. `ingest_course_source`

Imports a controlled uploaded source by `upload_id`. This must never accept arbitrary filesystem paths.

Supported source types: `pdf`, `pptx`, `ppt`, `docx`, `youtube`, `website`, `raw_text`.

## 5. `generate_course_blueprint`

Creates learning objectives, module plan, assessment strategy, and source citation policy.

## 6. `generate_module_pack`

Creates generated module metadata for a course project.

## 7. `generate_lesson_pack`

Creates lesson content for a module and includes source citation placeholders.

## 8. `generate_interactive_activity`

Creates H5P-style activity JSON.

Allowed activity types:

- `flashcards`
- `accordion`
- `interactive_video`
- `drag_and_drop`
- `matching`
- `scenario_decision_tree`
- `hotspot_image`
- `branching_scenario`
- `timeline`
- `fill_in_blanks`
- `reflection_prompt`

## 9. `generate_assessment_bank`

Creates MCQ, true/false, scenario, matching, fill-blank, case-study, and rubric-capable assessment items.

## 10. `generate_roleplay_simulation`

Creates a role-play simulation using the internal role-play generator.

## 11. `validate_instructional_quality`

Runs instructional quality checks.

Output shape:

```json
{
  "score": 84,
  "status": "needs_review",
  "issues": [],
  "recommendations": [],
  "metrics": {}
}
```

Checks should cover objective quality, Bloom level, lesson alignment, quiz alignment, source grounding, tone, accessibility, compliance, repetition, and completeness.

## 12. `build_export_package`

Builds an export package from generated project artifacts.

Supported export formats: `scorm`, `h5p`.

Supported SCORM versions: `1.2`, `2004`.

SCORM export returns one downloadable zip that contains lesson pages, media references, SCORM runtime files, and embedded H5P-style activity JSON when generated activities exist.

H5P export remains available as an optional separate bounded `.h5p` package generated from internal activity JSON. It does not accept arbitrary H5P files or filesystem paths.

Default SaaS delivery mode is `download_only`: return package metadata so the customer can download the SCORM/H5P file and upload it to their own LMS. This avoids hosting learner delivery/storage in the first SaaS version.

## 13. `build_storyline_handoff_package`

Builds a Storyline developer handoff ZIP. It does not generate native `.story` files.

Package contents:

- `storyboard.md`
- `storyline_build_spec.json`
- `quiz_import.csv`
- `interaction_blueprint.json`
- `voiceover_script.md`
- `assets/README.md`

## 14. `get_course_generation_status`

Returns tenant-scoped job status only. Unknown jobs and jobs from another tenant return `not_found`.

## 15. `list_course_artifacts`

Lists generated artifact metadata for a course project without exposing raw server paths or source files.

## 16. `request_publish_approval`

Moves the project into `needs_review`. It does not publish to an LMS.

Publishing adapters must stay internal until a separate approved `publish_approved_course` tool is deliberately designed and tested.
