# Course Studio release evidence

The user-authored Course Studio redesign is preserved as the product surface;
production work was applied around that surface rather than replacing it. Its
static assets, real-player canvas, editor server, workspace format, and export
path are versioned together under `apps/scorm_editor`.

Release coverage includes:

- create/import, source intake, structure editing, typed interactions,
  assessments, media, brand kit, review, localization, and export;
- loading/empty/import-error, saving/saved, offline recovery, expired session,
  optimistic conflict, export-blocked, generation partial-failure/retry, and
  cooperative cancellation states;
- responsive layout, keyboard/focus behavior, semantic labels/live status,
  accessibility blocking, local recovery, immutable revisions, roles,
  approvals, and conflict-safe saves;
- bounded ZIP upload/extraction, path and symlink rejection, compression/file
  limits, manifest/resource preservation, media replacement, protected
  branding, learner-source exclusion, SCORM 1.2/2004 runtime preservation, and
  import-edit-export-reimport equivalence.

The focused suites are `tests/test_scorm_editor.py` and
`tests/test_editor_roundtrip.py`. They run inside the release-blocking test job;
the resulting validation packages then pass pinned Moodle import, launch,
completion, suspend/resume, relaunch, and score verification before deployment.
