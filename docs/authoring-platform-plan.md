# Best-in-Class AI Authoring Tool — Analysis and Plan

Created: 2026-08-19
Scope: what is actually broken, the drag-and-drop editor decision, the video pipeline, and the execution loop.

This document supersedes nothing. It is the working plan that the orchestrator loop
(`.orchestrator/state.json`) executes against. Every finding below was verified against the
code in this repository, not inferred from documentation.

---

## 1. Verified findings

Baseline: `python -m pytest -q` → **222 passed, 19 skipped**. The Python core is healthy.
Everything broken is at the seams: the editor service, the MCP↔editor handoff, video, and
the gap between claimed status and provable status.

### F1 — Course Studio has no authentication at all `CRITICAL`

`apps/scorm_editor/server.py` contains zero authorization checks (`grep -c` for
`EDITOR_AUTH|check_auth|_authorize|Bearer` → **0**), yet it is published two ways:

- `docker-compose.yml:86` — `ports: - "8788:8788"` binds `0.0.0.0`
- `Caddyfile:39` — `handle /editor* { reverse_proxy scorm-editor:8788 }` on the public TLS host

Anyone who can reach the host can create sessions, upload 60 MB zips (300 MB extracted),
and read any session whose id they can guess or obtain. The only control on an existing
session is that its id is a UUID. There is no tenant, no license check, no rate limit.

### F2 — Unauthenticated endpoint spends our own LLM key `CRITICAL`

`apps/scorm_editor/server.py:596` (`_default_module_generator`) constructs an
`OpenRouterClient` using the **server's** credentials, reachable via `POST /api/generation/<sid>`
with no auth. Two consequences:

1. Direct, unmetered cost and abuse exposure on a public endpoint.
2. It contradicts the product's founding constraint. PRD §3b states the server performs only
   cheap deterministic work and "retains a small internal LLM hook (OpenRouter) strictly for
   minor helper tasks, **never full authoring**." This path *is* full authoring — it writes
   lessons, content blocks, activities, and quiz questions.

### F3 — The editor is a different, weaker product than the MCP `HIGH`

| | MCP server | Course Studio |
|---|---|---|
| Runtime | FastMCP / ASGI | stdlib `ThreadingHTTPServer` |
| State | PostgreSQL | JSON files in a local workspace dir |
| Binaries | S3 object store (`object_store.py`) | local disk, lost on container restart |
| Identity | tenant + license + rate limit | none |
| Tests | 222 Python tests | 333-line Python test, **zero** JS tests |

The editor is `read_only: true` with a `tmpfs` in compose — so on a production restart,
in-flight author work is destroyed. This is the highest-severity *data* risk after F1.

### F4 — There is no handoff between the MCP and the editor `HIGH`

The canonical flow ends at a zip on disk. To edit, a user downloads that zip and re-uploads it
through the browser. Nothing carries `course_id`, tenant, or license across the boundary, and
nothing carries edits back. The two halves of the product never speak.

### F5 — Inline text editing silently destroys formatting `HIGH`

`apps/scorm_editor/static/editor.js:1096` — the inline editor sets `contentEditable`, then on
blur reduces the result to `textContent`:

```js
var text = Array.prototype.map
  .call(host.querySelectorAll("p"), function (p) { return p.textContent.trim(); })
  .filter(Boolean).join(" ") || host.textContent.trim();
```

Any bold, italic, link, or list in an authored block is destroyed the moment an author
double-clicks it. There is no rich text editor in the product.

### F6 — No keyboard path for reordering `HIGH` (accessibility gate contradiction)

`editor.js:333` binds `keydown` for select (Enter/Space) and delete (Delete/Backspace), but
reordering is exclusively HTML5 mouse drag (`dragstart`/`drop`, `editor.js:344-358`). A core
authoring operation is unreachable by keyboard — a WCAG 2.1.1 failure — in a product that ships
`docs/course-studio-localization-accessibility.md` and blocks export on accessibility findings.
We enforce AA on the *output* and fail it in the *tool*.

### F7 — No real video generation exists `HIGH`

`grep -i` across the repo for `heygen|synthesia|veo|gemini|runway|d-id|elevenlabs|sora` returns
**nothing**. What exists is `html_video_engine.py`: a scene/caption model that renders an
*HTML slideshow* (`export_mode: interactive_html | recordable_html | scorm_slide_video`). It is
a good interactive format and worth keeping — but it is not video, and the product cannot
currently produce, ingest, or transcode one.

### F8 — No video decision point in discovery `MEDIUM`

`discovery/question_flow.py` asks `media_plan_mode` (`agent_images | user_uploads | text_only`)
and an optional `video_links` free-text field. There is no branch that asks whether the course
*needs* video and routes to generate / link / upload / skip. Video is an afterthought in the
interview, which is why it is an afterthought in the output.

### F9 — `source_ingestion.py` is dead code `MEDIUM`

191 lines, imported by nothing except `tests/test_source_ingestion.py`. The live path is
`ingestion.py::_extract_pdf` (which does now use pypdf with a regex fallback). Two PDF
extractors, one of them unreachable, both tested — so the test suite reports green on code
that never runs in production.

### F10 — Status is over-claimed `HIGH` (process defect)

`docs/task-board.md` marks T-001…T-035 and B-001…B-014 as **Done**. But
`docs/roadmap-next-layer.md` and `roadmap-production-best-in-class.md` §2.2 list gates that are
explicitly *not* met: tracked Moodle conformance, SCORM Cloud cross-check, three designer
sign-offs, a live Stripe purchase, a hosted paying-tier demo, and 30 days of measured SLOs.

"Done" currently means "code exists," which principle §3.7 of the production roadmap explicitly
forbids. Until this is corrected, the board cannot be used to decide what to work on — which is
exactly what an autonomous loop needs it for. **This is the first thing the loop must fix**,
otherwise it will iterate confidently over a false picture.

---

## 2. The drag-and-drop editor decision

### 2.1 The constraint that determines the answer

The product's real differentiator is stated in the production roadmap §3.1: *"Course Studio
remains WYSIWYG: authors edit the actual learner player output."* The canvas is an iframe
running the genuine exported SCORM player. Competitors edit a facsimile; we edit the artifact.

This rules out the obvious candidates. **GrapesJS** (BSD-3) wants to own an HTML document
model — our model is `data/course.json`, and GrapesJS would either fight it or replace the
player. **Puck** (MIT, [puckeditor/puck](https://github.com/puckeditor/puck)) and **Craft.js**
(MIT) are excellent, but both want to render *your React components* as the canvas. Our canvas
is not React — it is the shipped vanilla player. Adopting either means porting the player to
React first, at which point "WYSIWYG" becomes "WYSIWYG if the React port and the exporter never
drift."

### 2.2 Recommendation

**Compose primitives; do not adopt a page builder.** Keep the real-player iframe, and add:

| Layer | Pick | License | Why this one |
|---|---|---|---|
| Drag & drop | **hand-rolled, dnd-kit-inspired** | — | See correction below (2.2.1) — dnd-kit itself is off the table. |
| Rich text | **Tiptap** (`@tiptap/core`) | MIT | Headless and framework-agnostic at the core-package level (framework bindings like `@tiptap/react` are optional, not required) — it renders inside the player's own styling instead of fighting it, and works directly in this vanilla-DOM codebase. Schema-constrained: we whitelist exactly the marks the SCORM exporter can render, so the editor cannot produce unexportable content. Closes F5. |
| Block palette / slash menu | build on Tiptap | — | ~200 lines against our own block registry, versus adopting BlockNote's opinionated block model and then mapping it to `course.json` anyway. |

#### 2.2.1 Correction (2026-08-19, orchestrator cycle 3): dnd-kit is not usable here

The original pick above assumed dnd-kit was a framework-agnostic primitive. It is not:
`npm view @dnd-kit/core peerDependencies` returns `{ react: '>=16.8.0', 'react-dom': '>=16.8.0' }`,
and `@dnd-kit/sortable` depends on `@dnd-kit/core` the same way. Course Studio
(`apps/scorm_editor/frontend/src/editor.js`) is hand-rolled DOM manipulation with no React
anywhere in the stack. Adopting dnd-kit as specified would mean introducing React solely to
mount the outline tree — a materially larger architectural change than "swap the drag library,"
and not something this plan approved.

Resolution: implement the *behavior* dnd-kit would have given us — pointer drag plus a real
keyboard sensor (Tab to focus a grip, Space/Enter to pick up, Arrow keys to move, Space/Enter to
drop, Escape to cancel, live-region announcements for screen readers) — directly in vanilla JS
against the existing `treeNode`/`handleDrop`/`moveItem` functions. This closes F6 without a new
runtime dependency or a React migration. If a full page-canvas drag-and-drop layer (§2.3 items
1, 4, 5) later needs more machinery than hand-rolled code can reasonably provide, revisit
**Sortable.js** (MIT, framework-agnostic, no React requirement) before reconsidering dnd-kit —
but only as a scoped, separately-evaluated decision, not a default.

Rejected, with reasons recorded per production-roadmap §3.5:

- **BlockNote** — gives drag handles and a slash menu free, but owns the block model. We already
  have one (`course_schema_v2.py`) and it is the portable contract. Also MPL-2.0, a heavier
  license conversation than MIT for a white-label tier.
- **Lexical** — faster ceiling, React-first, Meta-backed. Genuinely a good pick, but our need is
  schema constraint and extension maturity, not typing throughput at millions of concurrent users.
- **Puck / Craft.js** — revisit *only* if we decide to port the player to React. That is a
  strategic bet, not a Phase 1 task.

### 2.3 What "drag-and-drop editor" should mean here

Beyond reordering, which already half-works:

1. Drag a block from the Insert palette onto a *position* in the canvas, with a live drop
   indicator — not just "append to lesson."
2. Drag to move a block between lessons and modules.
3. Keyboard equivalents for all of the above (hand-rolled keyboard sensor — see §2.2.1).
4. Drag a media asset from a media library onto a block.
5. Drag a PDF or a video file onto the canvas to create a source or a media block.

---

## 3. The video pipeline

Design principle, inherited from PRD §3b: **bring-your-own-key.** Generation cost belongs to
the customer. The server orchestrates, validates, packages, and never pays for inference.

### 3.1 Discovery gate (fixes F8)

Insert an `essentials`-stage branch before `media_plan_mode`:

> **Does this course need video?** `no | generate | i_have_links | i_will_upload`

- `generate` → ask provider preference, then require a BYO key
- `i_have_links` → the existing `video_links` path (YouTube/Vimeo/Loom embed blocks)
- `i_will_upload` → media slots + `upload_media_asset`
- `no` → skip the whole branch

### 3.2 Provider adapter

One interface, several implementations, selected by config — never hardcoded:

```
VideoProvider.submit(brief)  -> job_id      # async, returns immediately
VideoProvider.poll(job_id)   -> status|url
VideoProvider.fetch(url)     -> asset bytes -> object_store
```

Candidate adapters, in the order I would build them:

1. **HeyGen** — avatar-presenter video. (I believe this is what "Hixfield" refers to; confirm.)
   Best fit for corporate training talking-head segments, which is our core market.
2. **Google Veo via the Gemini API** — generative B-roll and scene illustration.
3. **ElevenLabs** — narration audio only. Cheapest, highest ROI: it turns the *existing*
   `html_video_engine` slideshow into a genuinely narrated lesson without any video model.
4. **Link ingestion** — YouTube/Vimeo/Loom. Already partly present; needs real embed validation.

Everything degrades to the existing HTML slide-video engine when no key is configured. That
keeps the free tier working and means the video feature can ship before any provider contract.

### 3.3 What must be built regardless of provider

- Async job model with resumable state (the pattern in `generation_queue.py` already exists).
- Assets into `object_store.py`, never local disk (F3).
- Captions/transcript required for every video — accessibility gate, and we already model
  `CaptionCue` in `html_video_engine.py`.
- Packaging into the SCORM zip with manifest entries and a size budget.
- Cost preview before submission. Nobody should discover the bill after the fact.

#### 3.3.1 Correction (2026-08-19, orchestrator cycle 11): the async job model doesn't actually exist

The line above assumed `generation_queue.py`'s `enqueue_generation_job` was an established, in-use
pattern. It isn't: `grep -rln enqueue_generation_job` returns only `generation_queue.py` itself and
its own tests — no MCP tool has ever called it. Every real generation tool in `tools.py`
(`generate_lesson_pack`, `generate_assessment_bank`, etc.) runs synchronously inside the tool call
and logs completion via `_record()`/`job_store.record_job()` purely for audit bookkeeping, not for
genuine async dispatch. There is no worker process consuming a queue anywhere in this codebase.

Resolution, applied to the ElevenLabs narration adapter (P3-2): keep the `VideoProvider` interface
shaped as `submit`/`poll`/`fetch` per §3.2, so a genuinely slow provider (HeyGen, Veo — both can
take minutes) has a real place to implement asynchronous behavior later. But for a provider whose
call actually completes in seconds (ElevenLabs text-to-speech per scene), `submit()` performs the
real HTTP call synchronously and returns an already-`completed` status; `poll()` is a thin
formality that returns that cached result. This avoids inventing async infrastructure this codebase
doesn't otherwise use, while keeping the interface honest for HeyGen/Veo (P3-3/P3-4) when they
actually need to poll a long-running job.

### 3.4 PDF → course, in the editor

`POST /api/sources` currently accepts only a pasted title + text. The editor should accept a
dropped PDF and route it through the *live* extractor (`ingestion.py`), producing page-anchored
`source_refs` — which also gives F9 a resolution: delete `source_ingestion.py`, or promote it and
delete the other. One extractor, reachable, tested.

---

## 4. Execution plan

Ordered by *what breaks the product if left alone*, not by what is fun.

### Phase 0 — Stop the bleeding (blocking; nothing ships past this)

- **P0-1** Authenticate Course Studio; bind it to the tenant/license model. (F1)
- **P0-2** Remove or gate `_default_module_generator`. Server-side authoring contradicts the
  business model — the calling agent authors. (F2)
- **P0-3** Move editor session state off tmpfs into Postgres + object storage. (F3)
- **P0-4** Correct `docs/task-board.md` to separate "code exists" from "evidence stored." (F10)

### Phase 1 — Make the editor genuinely best-in-class

- **P1-1** Replace HTML5 DnD with pointer + keyboard reordering (hand-rolled, no new
  dependency — see §2.2.1). (F6)
- **P1-2** Tiptap with an exporter-constrained schema; stop destroying formatting. (F5)
- **P1-3** Introduce `package.json`, a build, lint, and the first JS tests. (F3)
- **P1-4** Drop-position indicators; cross-lesson and cross-module block moves.

### Phase 2 — Close the loop between the halves

- **P2-1** `open_in_studio` MCP tool → authenticated deep link, no manual zip round-trip. (F4)
- **P2-2** Studio saves back to the course record; MCP export reads it. Round-trip in CI.
- **P2-3** PDF/media drop straight onto the canvas. (F9)

### Phase 3 — Video

- **P3-1** Discovery video gate. (F8)
- **P3-2** `VideoProvider` interface + ElevenLabs narration adapter (highest ROI first).
- **P3-3** HeyGen adapter, BYO-key.
- **P3-4** Veo/Gemini adapter, BYO-key.

### Phase 4 — Earn the claims

The external gates from production-roadmap §2.2. These need accounts and humans, and no amount
of local iteration substitutes for them. The loop's job here is to prepare evidence harnesses
and then **stop and ask**, not to mark them done.

---

## 5. How the loop runs this

State lives in `.orchestrator/state.json`. It is the only durable thing; every agent is
disposable.

- The **orchestrator** reads state, picks the next unblocked task, spawns workers, writes
  results back, and re-schedules itself. If it is killed at any point, the next cycle resumes
  from the ledger with nothing lost.
- **Workers** are spawned per task, do one scoped job, and die.
- **QA** runs after each phase — the full pytest suite plus a real browser pass over the editor.
- A task is `done` only when its acceptance test passes, honouring production-roadmap §3.7.
- **Deploy is a hard stop.** The loop prepares the release and asks for a human go-ahead.
  Phase 4's external gates are hard stops for the same reason.
