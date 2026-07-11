# MCP Tool Contracts

## Recommended generation recipe (agent playbook)

The calling agent (the user's Claude Code / Codex subscription) does all expensive work; the MCP validates, gates, and packages. The friction-free flow:

1. **Interview — three questions only.** `start_course_discovery`, then save answers for `course_brief_line` ("Ramp safety essentials for new ramp agents" — title/audience/goal are auto-derived), `duration_preset` (`micro`/`standard`/`deep`), and `media_plan_mode` (`agent_images`/`user_uploads`/`text_only`, plus optional `video_links`). If the user shared a PDF/PPT/doc/site, `ingest_course_source` it (extraction is deterministic — no LLM cost).
2. **One plan card.** `propose_course_plan` returns the whole plan (modules, length, template, media, gamification). Show it; when the user says "go", call `approve_course_plan` — it collapses every granular approval in one step.
3. **Write in parallel.** Spawn one subagent per module (user's tokens), each authoring full lessons per the content rules below, and `submit_course_module` as each finishes (idempotent by module id; the last one auto-assembles and quality-checks the course). Or use `submit_course_content` for one-shot.
4. **Media.** `get_media_briefs` returns image briefs (ready-to-render prompts + filenames) and video slots (with suggested searches). Generate images with your own tooling, push each via `upload_media_asset` (base64, png/jpg/svg/webp/mp4/webm, ≤8 MB), then `attach_media` to the target block. For video slots, ask the user one crisp question per slot (paste a YouTube/Vimeo/Loom link, upload an mp4, or skip — skipped slots render a clean poster card).
5. **Gate and ship.** `validate_instructional_quality` → `build_export_package` (SCORM zip with everything embedded). Exports are metered per license tier; `white_label` licenses may pass `branding: {product_name, footer_text}`.

Licensing: every call requires a license key (`mcp_api_token`). Customer keys are issued server-side with `scripts/issue_license.py` (tiers: free/pro/white_label with monthly export quotas); the `MCP_API_TOKEN` bootstrap key remains for the operator. Tenant identity comes from the license, not the payload.

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
-> list_course_templates / recommend_course_templates
-> start_course_discovery
-> get_next_course_question / save_course_discovery_answer
-> save_course_brief
-> propose_course_outline
-> approve_course_outline
-> propose_lesson_structure
-> approve_lesson_structure
-> select_assessment_model
-> select_interaction_model
-> check_generation_readiness
-> generate_course_with_codex
-> select_course_template
-> ingest_course_source
-> generate_course_blueprint
-> generate_module_pack
-> generate_lesson_pack
-> generate_interactive_activity
-> generate_interactive_video
-> generate_assessment_bank
-> validate_instructional_quality
-> validate_superior_course_quality
-> build_export_package
-> build_storyline_handoff_package
-> request_publish_approval
```

Discovery rules:

- Ask the course brief first, then module topics, then quiz and interaction decisions.
- The brief includes course title, target learner, learner level, course goal, industry/context, course type, expected duration, source material, module topic mode, and export target.
- Blank answers are allowed and should fall back to AI suggestions or template defaults.
- User answers always override AI suggestions.
- The workflow must not move to generation until the brief, template, outline, lessons, assessment model, interaction model, and source chunks are all present.

The Codex generation contract must use the approved brief, outline, lessons, selected template, source chunks, assessment model, interaction model, quality rules, and export targets. Default export should be a single SCORM package with native interactive activities and interactive video assets instead of producing separate handoff packages.

`start_course_discovery` and `get_next_course_question` return `next_question` for compatibility plus a `questions` array so the UI/GPT layer can ask multiple missing questions in one turn. `save_course_brief` is the brief approval gate. `propose_course_outline` must only run after the brief is approved and source chunks exist. `propose_lesson_structure` must only run after the outline is approved.

## Exposed Tools

## 1. `create_material_ticket`

Collects the user's initial course brief without touching raw server files. It returns missing fields and questions that the UI/GPT layer should ask before generation continues.

The default interview order is:

1. What course are we building, and who is it for?
2. What should learners be able to do after the course?
3. Are these proposed module topics good, or should they be revised?
4. Should the course include a quiz, and which quiz model should be used?

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

If the caller has not confirmed the proposed module topics or quiz decision, the tool should return `needs_more_information` and keep asking in that order instead of generating the layout.

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

## 5. `select_course_template`

Selects the best template for the requested topic, audience, industry, and delivery mode. Returns template metadata only, not file paths.

## 6. `generate_course_blueprint`

Creates learning objectives, module plan, assessment strategy, and source citation policy.

## 6b. `submit_course_content`

**This is the primary content path.** The calling agent (Claude Code / Codex) authors the full course — every lesson's prose, every activity's items, every quiz question — and submits it in one validated payload. The MCP server validates structure against `course_schema_v2`, runs the deterministic instructional-quality gate, stores the content, and uses it for export. The server never writes lesson prose itself.

Input:

```json
{
  "project_id": "course_ab12cd34ef56",
  "difficulty": "beginner",
  "theme": "studio",
  "learning_objectives": [
    {"id": "lo_sprint", "text": "Explain how sprints structure delivery work.", "bloom_level": "understand"}
  ],
  "modules": [
    {
      "id": "module_1",
      "title": "Scrum Foundations",
      "duration_minutes": 20,
      "objective_ids": ["lo_sprint"],
      "lessons": [
        {
          "id": "lesson_1",
          "title": "Why sprints work",
          "duration_minutes": 10,
          "objective_ids": ["lo_sprint"],
          "content_blocks": [
            {"id": "cb_1", "type": "intro", "text": "Learner-facing prose, not writer instructions."}
          ],
          "activities": [
            {"id": "act_1", "type": "flashcards", "title": "Sprint vocabulary", "instructions": "Flip each card.", "data": {"items": [{"front": "...", "back": "..."}]}, "objective_ids": ["lo_sprint"]}
          ],
          "quiz_questions": []
        }
      ],
      "activities": []
    }
  ],
  "final_assessment": {"id": "assessment_final", "title": "Final check", "passing_score": 80, "questions": [/* QuizQuestion objects */]}
}
```

Content rules the validator enforces (submission returns `quality_score`, `quality_status`, `quality_issues` so the agent can immediately fix and resubmit):

- Every lesson needs intro/explanation/example/practice/summary block types and at least ~180 learner-facing words.
- Text must be learner-facing prose. Writer meta-instructions ("Ask the learner to...", "Use the source to explain...") are flagged as placeholder content.
- Lessons, activities, and questions must map to learning objective ids.
- Final assessment needs 5+ questions including at least one scenario question, each with a meaningful explanation.
- Activity `data.items` should differ per lesson; do not reuse one activity everywhere.

Output: `{project_id, module_count, lesson_count, activity_count, quiz_question_count, quality_score, quality_status, quality_issues, media_requests}`.

### Level 3.5/4 mechanics (`game_options`)

Optional per-course switches controlling the packaged player's gamified experience:

```json
"game_options": {
  "branching_scenarios": true,
  "locked_progression": true,
  "streaks": true,
  "timed_challenges": false,
  "timer_seconds": 20,
  "celebration": true,
  "certificate": true
}
```

- `locked_progression`: lessons unlock sequentially on the dashboard.
- `streaks`: consecutive correct answers build an XP multiplier shown in the HUD.
- `timed_challenges`: knowledge-check slides get a countdown ring.
- `celebration` / `certificate`: confetti on completion and a printable certificate.
- Use activity type `branching_scenario` with `data.persona {name, role}` and `data.items` (each `{scenario, choices: [{label, result: "best"|"risk", feedback}]}`) for character-driven dialogue scenes.

### Media on content blocks

Any content block may carry one `media` attachment. Images the user supplies are referenced by controlled `upload_id` and packaged into the SCORM zip; videos and links use https URLs (YouTube embeds allowed):

```json
{"id": "cb_x", "type": "example", "text": "...", "media": {"kind": "video", "url": "https://www.youtube-nocookie.com/embed/VIDEO_ID", "caption": "Watch: ..."}}
{"id": "cb_y", "type": "practice", "text": "...", "media": {"kind": "image", "upload_id": "diagram.svg", "alt": "...", "caption": "..."}}
{"id": "cb_z", "type": "callout", "text": "...", "media": {"kind": "link", "url": "https://example.com", "caption": "Read more"}}
```

If a `media_placeholder` block has no media, or an `upload_id` file is missing, the submission result's `media_requests` lists exactly what to ask the user for — ask, then resubmit.

## 7. `generate_module_pack`

Creates generated module metadata for a course project. Prefer `submit_course_content` for real courses; this remains for scaffolding.

## 8. `generate_lesson_pack`

Creates lesson content for a module and includes source citation placeholders.

## 9. `generate_interactive_activity`

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

## 10. `generate_assessment_bank`

Creates MCQ, true/false, scenario, matching, fill-blank, case-study, and rubric-capable assessment items.

## 11. `generate_roleplay_simulation`

Creates a role-play simulation using the internal role-play generator.

## 12. `validate_instructional_quality`

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

Supported export formats: `scorm`, `h5p`, `adapt` (an Adapt Authoring "Import source" zip so the course can be polished in the WYSIWYG editor — see docs/editor-setup.md).

Supported SCORM versions: `1.2`, `2004`.

SCORM export returns one downloadable zip that contains lesson pages, media references, SCORM runtime files, native interactive activities, and interactive video assets. It must not embed H5P runtime files or `.h5p` packages inside the SCORM zip.

H5P export remains available as an optional separate bounded `.h5p` package generated from internal activity JSON. It does not accept arbitrary H5P files or filesystem paths.

Default SaaS delivery mode is `download_only`: return package metadata so the customer can download the SCORM/H5P file and upload it to their own LMS. This avoids hosting learner delivery/storage in the first SaaS version.

## 13. `validate_superior_course_quality`

Runs the stronger quality gate that checks lesson similarity, source coverage, scenario specificity, assessment alignment, and interaction variety. Export should be blocked if this reports `fail`.

## 14. `generate_interactive_video`

Builds a browser-native interactive training video package from the course project. The package contains HTML, captions, transcript, and the video-engine static assets.

## 15. `build_storyline_handoff_package`

Builds a Storyline developer handoff ZIP. It does not generate native `.story` files.

Package contents:

- `storyboard.md`
- `storyline_build_spec.json`
- `quiz_import.csv`
- `interaction_blueprint.json`
- `voiceover_script.md`
- `assets/README.md`

## 16. `get_course_generation_status`

Returns tenant-scoped job status only. Unknown jobs and jobs from another tenant return `not_found`.

## 17. `list_course_artifacts`

Lists generated artifact metadata for a course project without exposing raw server paths or source files.

## 18. `request_publish_approval`

Moves the project into `needs_review`. It does not publish to an LMS.

Publishing adapters must stay internal until a separate approved `publish_approved_course` tool is deliberately designed and tested.
