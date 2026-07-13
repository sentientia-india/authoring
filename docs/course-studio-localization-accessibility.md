# Course Studio localization and accessibility

Course Studio exposes both controls in the **Review** tab. They are authoring REST workflows and are not MCP tools.

## Accessibility release gate

`GET /api/accessibility/{session}` returns a deterministic report with blocker and warning counts, stable issue codes, field paths, and remediation messages. `POST /api/export/{session}` runs the same report and rejects export while any blocker remains.

Current blockers cover:

- lessons without titles;
- images without meaningful alternative text;
- videos without captions or a transcript;
- links without descriptive labels;
- assessment questions without prompts or enough choices.

A missing authored language is a warning. Warnings remain visible but do not prevent an otherwise accessible export. The report is regenerated from current course state, so stale acknowledgements cannot bypass the gate.

## Localization workflow

`GET /api/localization/{session}` returns the source locale and translation records. The source locale inherits directly from the course and always has `source` status. Each target locale starts with no overrides, which means every untranslated field inherits the source value.

`POST /api/localization/{session}` supports these actions:

- `add_locale` with a normalized BCP 47 language tag;
- `set_override` for a stable course field path and translated value;
- `remove_override` to resume source inheritance for that field;
- `set_status` through `draft`, `in_review`, and `approved`.

Editing an override returns its locale to `draft`. Localization metadata remains private authoring state and is excluded from SCORM ZIPs until a localized-release exporter selects an approved locale explicitly.

## Verification

Run:

```powershell
python -m pytest tests/test_scorm_editor.py tests/test_editor_roundtrip.py -q
```

The tests cover blocker detection, export rejection and recovery, source inheritance, translation overrides, status transitions, UI wiring, and exclusion of private authoring metadata from exported packages.
