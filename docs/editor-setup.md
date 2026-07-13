# Course Studio editor

Course Studio is the supported production authoring surface. It is bundled in
this repository under `apps/scorm_editor`, renders the actual generated course
player, and does not require authors to edit `course.json`.

## Run locally

```powershell
python -m apps.scorm_editor.server
```

Open `http://localhost:8788`. In Docker, the editor is the isolated
`scorm-editor` service and is published through the production reverse proxy at
`/editor/`.

## Authoring workflow

1. Create a course or import an existing SCORM ZIP.
2. Add and inspect source material and citations.
3. Approve the outline before generation.
4. Edit lessons, media, interactions, assessments, theme, and brand settings in
   the visual player surface.
5. Use revision comparison, comments, review roles, and approval gates.
6. Resolve accessibility blockers and translation review states.
7. Export SCORM 1.2 or SCORM 2004 and run validation before LMS delivery.

Course Studio preserves local recovery state, handles expired sessions and
multi-tab conflicts, reports offline/save/export failures, and supports keyboard
and responsive workflows. The release evidence and tests are documented in
`docs/course-studio-release-evidence.md`.

## Export formats

- **SCORM 1.2 and SCORM 2004** are the primary LMS packages and retain the
  actual Course Studio player experience.
- **H5P** is available for compatible interaction portability.
- **Adapt source export is not part of the public MCP contract.** A legacy
  internal converter may remain for compatibility tests, but production clients
  cannot request it through `build_export_package`.

The older machine-local Adapt Authoring installation is independent of this
product and is not required to build, edit, deploy, or sell courses.
