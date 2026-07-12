# SCORM Cloud validation record

Validated on 2026-07-12 in the `samrat D` SCORM Cloud trial realm.

## Imported packages

| Package | SCORM Cloud course ID | Result |
|---|---|---|
| SCORM 1.2 | `samrat-scorm12-validation3af4112c-37eb-4ed4-b951-828b81c56f5c` | Passed tracked Sandbox validation: manifest clean, completion `complete`, success `passed`, score `100.00%`, registration `Completed: true`, and `Attempts: 1`. |
| SCORM 2004 4th Edition | `samrat-scorm2004-validation629ff92b-8af7-4639-83f3-913679403b6d` | Passed tracked Sandbox validation: manifest clean, completion `complete`, success `passed`, score `100.00%`, registration `Completed: true`, and `Attempts: 1`. |

## Authoritative tracked results

Both packages were launched through **Course Sandbox** with `tracking=true`. The learner passed the final check, completed the course, and closed the SCO so the runtime could terminate. SCORM Cloud then reported the following for both standards:

- Completion: `complete`
- Success: `passed`
- Score: `100.00%`
- Registration: `Completed: true`, `Satisfied: true`, `Progress Status: true`, `Attempts: 1`, `Suspended: false`
- Total tracked time: SCORM 1.2 `2m 37s`; SCORM 2004 `21m 40s`

## Remaining acceptance items

- Verify saved suspend/resume state by closing a tracked attempt mid-course and relaunching it.
