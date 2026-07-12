# Moodle SCORM conformance

The Moodle acceptance environment is reproducible through
`.github/workflows/moodle-conformance.yml`.

## Pinned environment

- Moodle: 4.5 LTS, commit `da7446c6c7b786f7f7588537f1cd48b3709c5439`
- Moodle Docker: commit `81a20665c2d2322469dc491c1f972ebde90ec014`
- PostgreSQL through the official Moodle Docker configuration
- PHP 8.3
- Chrome/Selenium capability enabled for tracked learner scenarios

The workflow is manual because the full LMS environment is expensive and is a release-conformance gate, not a unit-test dependency. It builds fresh SCORM 1.2 and 2004 packages, validates them before import, boots and installs Moodle, verifies the login endpoint, and archives the exact packages, hashes, validation reports, and container diagnostics.

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

The environment bootstrap is complete when its workflow is green. Moodle acceptance is complete only after both packages also pass every tracked learner scenario above and the resulting evidence is attached to this document.
