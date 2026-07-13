# Moodle SCORM conformance

The Moodle acceptance environment is reproducible through
`.github/workflows/moodle-conformance.yml`.

## Pinned environment

- Moodle: 4.5 LTS, commit `da7446c6c7b786f7f7588537f1cd48b3709c5439`
- Moodle Docker: commit `81a20665c2d2322469dc491c1f972ebde90ec014`
- PostgreSQL through the official Moodle Docker configuration
- PHP 8.3
- Chrome/Selenium capability enabled for tracked learner scenarios

The workflow can be run manually for diagnosis and is also called by both production deployment workflows. A production deployment cannot start unless this reusable gate passes. It builds fresh SCORM 1.2 and 2004 packages, validates them before import, boots and installs Moodle, imports both packages through Moodle's SCORM activity generator, and runs the tracked learner scenarios in Moodle's Chrome/Behat environment. The run leaves and relaunches each activity to prove persisted location and suspend data, then archives the exact packages, hashes, validation reports, acceptance summary, and container diagnostics.

## Required tracked scenarios

For each package, the final acceptance run must record:

| Capability | SCORM 1.2 field | SCORM 2004 field | Required outcome |
|---|---|---|---|
| Initialize | `LMSInitialize` | `Initialize` | returns success |
| Location | `cmi.core.lesson_location` | `cmi.location` | restored after relaunch |
| Suspend data | `cmi.suspend_data` | `cmi.suspend_data` | restored after relaunch |
| Score | `cmi.core.score.raw` | `cmi.score.raw` and `cmi.score.scaled` | 100 |
| Completion | `cmi.core.lesson_status` | `cmi.completion_status` | completed |
| Success | `cmi.core.lesson_status` | `cmi.success_status` | passed |
| Interaction | `cmi.interactions.n.*` | `cmi.interactions.n.*` | final check recorded |
| Session time | `cmi.core.session_time` | `cmi.session_time` | greater than zero |
| Commit | `LMSCommit` | `Commit` | returns success |
| Terminate | `LMSFinish` | `Terminate` | returns success |

The environment bootstrap is complete when Moodle becomes healthy. Moodle acceptance is complete only when the `@course_mcp_acceptance` browser scenarios pass for both packages and the resulting workflow artifacts are linked below. A green parser-only run is not acceptance evidence.

## Acceptance evidence

- Result: passed on 2026-07-13 for both SCORM 1.2 and SCORM 2004.
- Source commit: `14442ed2ec374307398ebd4c1f6980315acd3382`.
- GitHub Actions run: [CI 29228239968](https://github.com/ratsam93/course_pack_elearning/actions/runs/29228239968).
- Moodle job: `86746998104`; two Chrome/Behat scenarios passed in the pinned Moodle 4.5 LTS environment.
- Release gate: the same run completed the production deployment job `86747774750` only after Moodle passed.
- SCORM 1.2 SHA-256: `177da7951e357e90484489c0667fa8bf9fb450e368d86a169ae239416e0fe3d6`.
- SCORM 2004 SHA-256: `a026a9e0f54fadb2d1abe0b4f01cb4c859e69efacfe0f2c406d0a16f50a82408`.
- Archived artifacts: `moodle-scorm-conformance-inputs` and `moodle-diagnostics` (GitHub retention applies).
- Repository evidence record: [`evidence/moodle-2026-07-13.json`](evidence/moodle-2026-07-13.json).
