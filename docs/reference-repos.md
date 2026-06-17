# Reference Repos

These repos are local research inputs, not product source. They live under `.codex/reference-repos/` and are ignored by git.

## Current Local References

| Repo | Local folder | Use |
|---|---|---|
| `https://github.com/modelcontextprotocol/python-sdk.git` | `.codex/reference-repos/python-sdk` | MCP SDK patterns and structured tool examples. |
| `https://github.com/PrefectHQ/fastmcp.git` | `.codex/reference-repos/fastmcp` | FastMCP registration, auth, testing, and transport examples. |
| `https://github.com/fracabu/scorm-course-generator.git` | `.codex/reference-repos/scorm-course-generator` | SCORM manifest/package workflow ideas. |
| `https://github.com/LiaScript/LiaScript-Exporter.git` | `.codex/reference-repos/LiaScript-Exporter` | Export flow and LMS format research. |
| `https://github.com/sr258/scorm-h5p-wrapper.git` | `.codex/reference-repos/scorm-h5p-wrapper` | H5P-to-SCORM packaging concepts. |
| `https://github.com/jcputney/scorm-again.git` | `.codex/reference-repos/scorm-again` | SCORM runtime and LMS API behavior reference. |
| `https://github.com/minicoursegenerator/edu-role-play.git` | `.codex/reference-repos/edu-role-play` | Role-play training composition ideas. |
| `https://github.com/minicoursegenerator/skills-for-course-creators.git` | `.codex/reference-repos/skills-for-course-creators` | Course-creator workflow and skill taxonomy ideas. |

## Refresh Commands

Use this only when the reference repos need refreshing:

```powershell
Get-ChildItem -Directory .codex\reference-repos | ForEach-Object {
  git -C $_.FullName pull --ff-only
}
```

## Integration Rules

- Do not vendor these repos into `src/`.
- Do not run their lint/test failures as product failures.
- Do not copy unsafe MCP examples that expose files, shell, env, logs, databases, or Docker.
- Convert useful patterns into small, tested code that matches this repository's schemas, allowlist, and security layer.

