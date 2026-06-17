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
create_course_project
-> ingest_course_source
-> generate_course_blueprint
-> generate_module_pack
-> generate_lesson_pack
-> generate_interactive_activity
-> generate_assessment_bank
-> validate_instructional_quality
-> build_export_package
-> request_publish_approval
```

## Exposed Tools

## 1. `create_course_project`

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

## 2. `ingest_course_source`

Imports a controlled uploaded source by `upload_id`. This must never accept arbitrary filesystem paths.

Supported source types: `pdf`, `pptx`, `ppt`, `docx`, `youtube`, `website`, `raw_text`.

## 3. `generate_course_blueprint`

Creates learning objectives, module plan, assessment strategy, and source citation policy.

## 4. `generate_module_pack`

Creates generated module metadata for a course project.

## 5. `generate_lesson_pack`

Creates lesson content for a module and includes source citation placeholders.

## 6. `generate_interactive_activity`

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

## 7. `generate_assessment_bank`

Creates MCQ, true/false, scenario, matching, fill-blank, case-study, and rubric-capable assessment items.

## 8. `generate_roleplay_simulation`

Creates a role-play simulation using the internal role-play generator.

## 9. `validate_instructional_quality`

Runs instructional quality checks.

Output shape:

```json
{
  "score": 84,
  "status": "needs_review",
  "issues": [],
  "recommendations": []
}
```

Checks should cover objective quality, Bloom level, lesson alignment, quiz alignment, source grounding, tone, accessibility, compliance, repetition, and completeness.

## 10. `build_export_package`

Builds an export package from generated project artifacts.

Supported export formats: `scorm`, `h5p`.

Supported SCORM versions: `1.2`, `2004`.

H5P export returns a bounded `.h5p` package generated from internal activity JSON. It does not accept arbitrary H5P files or filesystem paths.

Default SaaS delivery mode is `download_only`: return package metadata so the customer can download the SCORM/H5P file and upload it to their own LMS. This avoids hosting learner delivery/storage in the first SaaS version.

## 11. `get_course_generation_status`

Returns tenant-scoped job status only. Unknown jobs and jobs from another tenant return `not_found`.

## 12. `list_course_artifacts`

Lists generated artifact metadata for a course project without exposing raw server paths or source files.

## 13. `request_publish_approval`

Moves the project into `needs_review`. It does not publish to an LMS.

Publishing adapters must stay internal until a separate approved `publish_approved_course` tool is deliberately designed and tested.
