# SCORM Cloud validation record

Validated on 2026-07-12 in the `samrat D` SCORM Cloud trial realm.

## Imported packages

| Package | SCORM Cloud course ID | Result |
|---|---|---|
| SCORM 1.2 | `samrat-scorm12-validation3af4112c-37eb-4ed4-b951-828b81c56f5c` | Imported; SCORM Cloud reported `Congratulations, your manifest looks great!`; Sandbox launch history recorded a 28-second launch. |
| SCORM 2004 4th Edition | `samrat-scorm2004-validation629ff92b-8af7-4639-83f3-913679403b6d` | Imported; SCORM Cloud reported `Congratulations, your manifest looks great!`; learner player rendered, the final check scored 100%, and the course completion UI rendered. |

## Open acceptance item

SCORM Cloud launches the SCO in a popup. In browser-controlled validation, the popup route can run with `tracking=false`, so the course UI can complete while the Sandbox registration remains `Attempts: 0`, `Completed: unknown`, and `Score: unknown`.

To finish the authoritative completion/score/resume assertion, run the course from the **Course Sandbox** with popups allowed for `cloud.scorm.com`, then inspect **View Registration State**. Required outcome:

- `Attempts: 1`
- `Completed: true`
- `Success: passed`
- `Score: 100`
- saved suspend/resume state after closing and relaunching mid-course

This is a SCORM Cloud browser-launch configuration issue, not a manifest parser failure. The repository's local SCORM validation and runtime tests remain green.
