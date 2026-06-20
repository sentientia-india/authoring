# SCORM Reference Output Formats

The local `scorm reference/` folder contains two client/reference SCORM 2004 packages. Keep those ZIPs as local reference material; do not delete them and do not deploy the raw vendor packages.

The generator exposes two matching output targets without copying the third-party runtime:

| Reference style | Use when | Generator value |
| --- | --- | --- |
| Format 1: interaction game | Game-like interactions, fast activities, badges, compact lesson flow | `interaction_game` |
| Format 2: course example | Larger course-style package with structured lessons, evaluation, and stronger course hierarchy | `course_example` |

Both styles still produce a normal editable Samrat SCORM ZIP with:

- `imsmanifest.xml`
- `index.html`
- `data/course.json`
- native activities
- final assessment
- progress/completion tracking
- no H5P package embedded inside SCORM

The server SCORM editor shows two small generated samples under "Reference output formats" so users can load either style from the browser before uploading their own generated package.
