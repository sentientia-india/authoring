# Ten-minute first course

## 1. Connect

```bash
claude mcp add --transport http samrat-course https://YOUR_DOMAIN/mcp --header "Authorization: Bearer YOUR_LICENSE_KEY"
```

## 2. Start with one sentence

Ask the connected client: `Create a course about <topic> for <learner>, using my attached source.`

Answer the three short prompts: the course brief, duration preset, and media plan. Review the proposed plan and say `go`.

## 3. Review and export

The agent authors the modules, runs the quality gate, asks for any missing media, then produces a SCORM ZIP. Upload that ZIP to SCORM Cloud or your LMS. The editor at `/editor/` can revise the course without breaking its tracking package.

Expected elapsed time for the included demo source: under ten minutes, excluding human review and media generation.
