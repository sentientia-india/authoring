# WYSIWYG Editor: Adapt Authoring (running instance)

Decision (see roadmap B1): we adopt the pre-made, production-grade **Adapt Authoring Tool** (GPL-3.0) as the WYSIWYG editor rather than building one, and upgrade the integration when needed. It runs **at arm's length** — a separate install outside this repository, never embedded in the product code — which keeps the GPL boundary clean.

## Where it lives (this machine)

```
C:\Aicoding\adapt-editor\
├── adapt_authoring\    # Adapt Authoring Tool 0.11.5 (framework 5.56.2), npm-installed
├── mongodb\            # Portable MongoDB 4.4.29 (data + logs inside; no Windows service)
├── start-editor.cmd    # One-click start (Mongo + server), opens http://localhost:5050
├── stop-editor.cmd     # Stops both processes
├── install.log         # Install transcript
└── server.log          # Server output
```

- **URL**: http://localhost:5050
- **Login**: `admin@example.com` — change the password after first login (Adapt UI → user settings).
- **Node**: 18.20.4 via nvm-windows (`C:\Users\Sams PC\AppData\Local\nvm\v18.20.4`). Adapt supports Node 16/18 only — do not run it with the system Node 24.
- **MongoDB**: must be 4.x — Adapt's bundled mongo driver (3.6) cannot talk to MongoDB 6+. Bound to `127.0.0.1:27018` (use the IP, not `localhost`, which resolves to `::1` on this machine).

## Daily use

1. Double-click `C:\Aicoding\adapt-editor\start-editor.cmd` (or run it from a terminal).
2. Author/edit in the browser: Dashboard → **Add new course** (or edit existing), full drag-and-drop page/component editing, then **Publish/Download** produces a SCORM zip.
3. `stop-editor.cmd` when done.

## Editing MCP-generated courses in Adapt (converter shipped)

`build_export_package` with `export_format: "adapt"` produces `<slug>-adapt.zip` — an Adapt framework source package (`src/course/en/*.json` + assets + theme/menu stubs) that the dashboard's **Import source** accepts directly. Verified end-to-end: a full MCP demo course imported as 4 pages / 7 articles / 52 blocks with text, graphic (packaged images), accordion, matching, and MCQ components, all editable, previewable, and re-publishable from Adapt.

Mapping (in `src/course_mcp_server/exporters/adapt_source.py`, tests in `tests/test_adapt_export.py`):

| MCP | Adapt |
|---|---|
| module | page |
| lesson | article |
| content block | block + text component (media → graphic/media component) |
| matching activity | matching component |
| flashcards / accordion / tabs | accordion component |
| quiz + final assessment questions | mcq components |
| other interactive types (branching, decision tree, roleplay...) | editable rich-text fallback describing the interaction |

Note: the Level-4 game mechanics (HUD, streaks, slide player) live in the MCP's own SCORM export, not in Adapt's output — Adapt is for hand-polishing content, its Publish produces a standard Adapt course. The two editing paths remain:
- **Adapt** — import the `-adapt.zip`, polish visually, publish.
- **`apps/scorm_editor`** (this repo, port 8788) — direct edits to the MCP game-player zip itself.

## Rebuild-from-scratch notes (if the install is ever lost)

1. Install nvm-windows, `nvm install 18.20.4` (activation via symlink may fail — call the versioned node.exe directly on PATH).
2. Download portable MongoDB **4.4.x** zip, run `mongod --dbpath ... --port 27018 --bind_ip 127.0.0.1` (no service install needed).
3. `git clone https://github.com/adaptlearning/adapt_authoring.git`; `npm install --production` with Node 18.
4. Non-interactive install (all prompts must be passed as CLI flags or it hangs; `--dbHost=127.0.0.1`):
   `node install --useJSON=false --install=true --serverPort=5050 --serverName=localhost --dataRoot=data --frameworkRepository=https://github.com/adaptlearning/adapt_framework.git --frameworkRevision=master --dbName=adaptmaster --useConnectionUri=false --dbHost=127.0.0.1 --dbPort=27018 --useSmtp=false --masterTenantName=master --masterTenantDisplayName=Master --suEmail=<email> --suPassword=<pw> --suRetypePassword=<pw>`
5. `node server` → http://localhost:5050.
