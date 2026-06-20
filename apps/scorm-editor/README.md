# SCORM Editor App

This is the separate drag-and-drop SCORM editor service.

Run it independently from the MCP server:

```bash
python -m apps.scorm_editor.server --host 127.0.0.1 --port 8788
```

Capabilities:
- upload a SCORM zip
- parse `imsmanifest.xml`
- load editable learner content from `data/course.json`
- drag/reorder modules and lessons
- edit module and lesson fields
- export a rebuilt SCORM zip

Runtime rules:
- separate service from `course-mcp`
- separate port, suggested `127.0.0.1:8788`
- no access to MCP secrets
- no unsafe filesystem browsing
- no MCP tool exposure
