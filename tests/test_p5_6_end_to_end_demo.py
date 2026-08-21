"""P5-6: end-to-end demo/acceptance test.

Drives the REAL code paths for the full authoring lifecycle in one run:

    PDF ingestion -> discovery -> non-OpenRouter (DeepSeek) blueprint generation
    -> agent-authored content submission -> media fulfillment -> open_in_studio
    (a REAL scorm_editor HTTP server booted in-process) -> two in-editor AI
    actions against the real POST /api/ai/<sid>/generate route -> a real PUT
    to /api/course/<sid> landing those mutations plus one new interaction type
    (hotspot) in course.json on disk -> course-health check (via a Node
    subprocess against the real course-health.js) -> import_studio_edits back
    into the MCP project -> build_export_package to a real SCORM zip.

Only the LLM HTTP transport is mocked (urlopen inside the deepseek adapter,
and the scorm_editor _text_provider_factory indirection point that tests in
tests/test_scorm_editor_ai.py already use for the same purpose) -- every tool
call, HTTP request, and file write here is real.

Run directly for a human-readable transcript:
    python -m pytest tests/test_p5_6_end_to_end_demo.py -q -s
"""

from __future__ import annotations

import base64
import json
import subprocess
import sys
import threading
import urllib.error
import urllib.request
import zipfile
from http.server import ThreadingHTTPServer
from io import BytesIO
from pathlib import Path

import pytest

from course_mcp_server.security import RequestContext
from course_mcp_server.tools import (
    approve_course_plan,
    attach_media,
    build_export_package,
    create_course_project,
    generate_course_blueprint,
    import_studio_edits,
    ingest_course_source,
    open_in_studio,
    propose_course_plan,
    save_course_discovery_answer,
    start_course_discovery,
    submit_course_content,
    upload_media_asset,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _log(title: str, payload=None) -> None:
    print(f"\n=== {title} ===")
    if payload is not None:
        print(json.dumps(payload, indent=2, default=str)[:3000])


def _ctx() -> RequestContext:
    return RequestContext(tenant_id="tenant-demo", user_id="demo-agent", token="tok", request_id="req-p5-6")


def _make_fixture_pdf() -> bytes:
    """Build a real, extractable PDF with reportlab -- not a stub -- so
    ingest_course_source's real pypdf extraction path is genuinely exercised."""
    from reportlab.lib.pagesizes import LETTER
    from reportlab.pdfgen import canvas

    buffer = BytesIO()
    doc = canvas.Canvas(buffer, pagesize=LETTER)
    lines = [
        "Ramp Safety Ground Operations Briefing",
        "",
        "Cones and wheel chocks must be verified in place before any pushback",
        "operation begins, per the IATA Ground Operations Manual chapter 4.",
        "Wing walkers guide all aircraft movement in congested ramp areas and",
        "must use standard IATA hand signals at all times during marshalling.",
        "Foreign Object Debris (FOD) walks are mandatory before every departure",
        "push, and jet blast zones must be clearly marked and enforced by staff.",
        "Ground crew must wear high-visibility clothing and hearing protection",
        "whenever operating within twenty five meters of an active engine.",
    ]
    y = 740
    for line in lines:
        doc.drawString(72, y, line)
        y -= 20
    doc.showPage()
    doc.save()
    return buffer.getvalue()


def _minimal_scorm_zip_for_import() -> bytes:
    # Unused placeholder kept for parity with test_scorm_editor_ai.py's helper name if needed later.
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as package:
        package.writestr("imsmanifest.xml", "<manifest/>")
    return buffer.getvalue()


@pytest.fixture()
def studio_server(monkeypatch, tmp_path):
    """Boot the REAL scorm_editor HTTP server (ThreadingHTTPServer + Handler) in-process,
    exactly like tests/test_scorm_editor_ai.py does, and point the MCP's open_in_studio /
    import_studio_edits tools at it via EDITOR_INTERNAL_URL so the whole studio handoff is a
    genuine loopback HTTP round trip, not a stub.
    """
    editor_token = "demo-editor-token-p5-6"
    monkeypatch.setenv("EDITOR_API_TOKEN", editor_token)
    monkeypatch.setenv("EDITOR_WORKSPACE_DIR", str(tmp_path / "editor-workspaces"))
    monkeypatch.delenv("EDITOR_ALLOW_INSECURE_DEV", raising=False)

    import apps.scorm_editor.server as server_module

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server_module.Handler)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()

    monkeypatch.setenv("EDITOR_INTERNAL_URL", f"http://127.0.0.1:{port}")

    yield {
        "base_url": f"http://127.0.0.1:{port}",
        "token": editor_token,
        "module": server_module,
        "workspace_root": tmp_path / "editor-workspaces",
    }

    httpd.shutdown()
    thread.join(timeout=5)


def _http_post(url: str, token: str, payload: dict):
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"}, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def _http_put(url: str, token: str, payload: dict):
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"}, method="PUT"
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def _http_get(url: str, token: str):
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def test_p5_6_end_to_end_demo(tmp_path, monkeypatch, studio_server):
    monkeypatch.setenv("COURSE_PROJECT_STORE_PATH", str(tmp_path / "projects.json"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    (tmp_path / "uploads").mkdir(exist_ok=True)
    context = _ctx()

    # ------------------------------------------------------------------
    # STEP 1: ingest a real, extractable fixture PDF via ingest_course_source.
    # ------------------------------------------------------------------
    pdf_bytes = _make_fixture_pdf()
    upload_path = Path(tmp_path / "uploads" / "ramp_safety_briefing.pdf")
    upload_path.write_bytes(pdf_bytes)
    _log("STEP 1: fixture PDF written", {"path": str(upload_path), "size_bytes": len(pdf_bytes)})

    project = create_course_project(
        {"course_title": "Ramp Safety Briefing", "audience": "new ramp agents", "language": "English"}, context
    )
    assert project["ok"] is True
    project_id = project["data"]["project_id"]

    ingested = ingest_course_source(
        {"project_id": project_id, "upload_id": "ramp_safety_briefing.pdf", "source_type": "pdf"}, context
    )
    _log("STEP 1: ingest_course_source result", ingested)
    assert ingested["ok"] is True
    assert "ramp" in ingested["data"]["extracted_text_preview"].lower() or "cones" in ingested["data"][
        "extracted_text_preview"
    ].lower()
    assert ingested["data"]["source_type"] == "pdf"

    # ------------------------------------------------------------------
    # STEP 2: run discovery (the real question-flow tools) to produce a course plan.
    # ------------------------------------------------------------------
    started = start_course_discovery({"project_id": project_id}, context)
    assert started["ok"] is True
    for question_id, answer in (
        ("course_brief_line", "Ramp safety briefing for new ramp agents"),
        ("source_mode", "upload_document"),
        ("duration_preset", "standard"),
        ("media_plan_mode", "agent_images"),
    ):
        answered = save_course_discovery_answer({"project_id": project_id, "question_id": question_id, "answer": answer}, context)
        assert answered["ok"] is True
    _log("STEP 2: discovery answers saved")

    # ------------------------------------------------------------------
    # STEP 3: generate the course plan with a NON-OpenRouter provider (DeepSeek),
    # BYO key, mocked HTTP transport at the urlopen boundary (not a live call).
    # ------------------------------------------------------------------
    captured_deepseek_request: dict = {}
    blueprint_content = json.dumps(
        {
            "course_title": "Ramp Safety Briefing for new ramp agents",
            "audience": "new ramp agents",
            "difficulty": "beginner",
            "language": "English",
            "learning_objectives": ["Verify cones and chocks before pushback.", "Use standard IATA wing-walker signals."],
            "modules": [{"title": "Ground Operations Fundamentals", "lessons": []}],
            "assessment_plan": "MCQ quiz on ramp safety fundamentals.",
        }
    )

    # Patched on text_providers.base (not text_providers.deepseek) since every adapter now
    # shares one default_transport() implementation there (text_providers/base.py) instead of
    # each adapter module importing its own urlopen name.
    import course_mcp_server.text_providers.base as text_providers_base_module
    from contextlib import contextmanager

    @contextmanager
    def _fake_deepseek_urlopen(request, timeout=None):  # noqa: ARG001
        captured_deepseek_request["url"] = request.full_url
        captured_deepseek_request["headers"] = dict(request.header_items())
        captured_deepseek_request["body"] = json.loads(request.data.decode("utf-8"))

        class _Response:
            def read(self_inner):
                return json.dumps({"choices": [{"message": {"content": blueprint_content}}]}).encode("utf-8")

        yield _Response()

    monkeypatch.setattr(text_providers_base_module, "urlopen", _fake_deepseek_urlopen)

    blueprint = generate_course_blueprint(
        {
            "project_id": project_id,
            "duration_minutes": 45,
            "text_provider": "deepseek",
            "text_provider_api_key": "sk-demo-deepseek-byo-key",
        },
        context,
    )
    _log("STEP 3: DeepSeek blueprint result", blueprint)
    assert blueprint["ok"] is True
    assert blueprint["data"]["generation_provider"] == "deepseek"
    assert captured_deepseek_request["headers"]["Authorization"] == "Bearer sk-demo-deepseek-byo-key"
    assert "api.deepseek.com" in captured_deepseek_request["url"]
    stored_projects_text = (tmp_path / "projects.json").read_text(encoding="utf-8")
    assert "sk-demo-deepseek-byo-key" not in stored_projects_text
    print("CONFIRMED: generation_provider == 'deepseek' (real BYO-key adapter selected + used; key never hit disk).")

    # ------------------------------------------------------------------
    # Discovery -> plan approval (readiness gate).
    # ------------------------------------------------------------------
    plan = propose_course_plan({"project_id": project_id}, context)
    assert plan["ok"] is True
    approval = approve_course_plan({"project_id": project_id}, context)
    _log("STEP 2/3: plan approval", approval)
    assert approval["ok"] is True

    # ------------------------------------------------------------------
    # Agent authors the full course content (server never fabricates lesson prose --
    # see product-direction memory note) via submit_course_content, reusing the
    # already-validated fixture from tests/test_canonical_flow.py.
    # ------------------------------------------------------------------
    fixture = json.loads((FIXTURES / "agile_course_content.json").read_text(encoding="utf-8"))
    fixture["project_id"] = project_id
    submitted = submit_course_content(fixture, context)
    assert submitted["ok"] is True, submitted

    # Mandatory-image gate: discover + fulfill every image brief with a fake but real upload.
    blocked = build_export_package({"project_id": project_id, "export_format": "scorm"}, context)
    if not blocked["ok"]:
        assert blocked["error"] == "media_incomplete"
        for brief in blocked["data"]["image_briefs"]:
            filename = brief["filename"].replace(".png", ".svg")
            upload_media_asset(
                {
                    "project_id": project_id,
                    "filename": filename,
                    "content_base64": base64.b64encode(b"<svg xmlns='http://www.w3.org/2000/svg'/>").decode(),
                },
                context,
            )
            attach_media({"project_id": project_id, "block_id": brief["block_id"], "kind": "image", "upload_id": filename}, context)
        unblocked = build_export_package({"project_id": project_id, "export_format": "scorm"}, context)
        assert unblocked["ok"] is True, unblocked

    # ------------------------------------------------------------------
    # STEP 4: open in Course Studio (real HTTP handoff to the in-process editor server).
    # ------------------------------------------------------------------
    opened = open_in_studio({"project_id": project_id, "scorm_version": "1.2"}, context)
    _log("STEP 4: open_in_studio result", opened)
    assert opened["ok"] is True, opened
    sid = opened["data"]["session"]
    open_token = opened["data"]["editor_url"].split("token=")[-1]

    status, current = _http_get(f"{studio_server['base_url']}/api/course/{sid}", open_token)
    assert status == 200, current
    course_before = current["course"]
    version_before = current["version"]
    target_block = next(
        b for lesson in course_before["modules"][0]["lessons"] for b in lesson["content_blocks"] if b["id"] == "cb_1_intro"
    )
    original_text = target_block["text"]
    target_lesson = course_before["modules"][0]["lessons"][0]

    # --- AI action 1: rewrite a content block, via the REAL POST /api/ai/<sid>/generate route,
    # mocked only at the transport indirection point (matching tests/test_scorm_editor_ai.py).
    server_module = studio_server["module"]
    rewritten_text = (
        "REWRITTEN BY P5-6 DEMO: Cones and wheel chocks are verified before every pushback, "
        "exactly as this briefing's source PDF describes, so risk surfaces before the tug ever moves."
    )

    class _FakeRewriteProvider:
        def generate_json(self, system_prompt, user_payload, schema_name, *, model=None):
            return {"text": rewritten_text}

    monkeypatch.setattr(server_module, "_text_provider_factory", lambda *a, **k: _FakeRewriteProvider())
    status, rewrite_response = _http_post(
        f"{studio_server['base_url']}/api/ai/{sid}/generate",
        open_token,
        {
            "system_prompt": "Rewrite this content block to be punchier.",
            "user_payload": {"text": original_text},
            "schema_name": "content_block_rewrite",
            "text_provider": "openrouter",
        },
    )
    _log("STEP 4: AI action 1 (rewrite) response", rewrite_response)
    assert status == 200, rewrite_response
    assert rewrite_response["ok"] is True
    assert rewrite_response["result"]["text"] == rewritten_text

    # --- AI action 2: generate a quiz from a lesson, via the same real route, gated by the
    # real QuizBank/QuizQuestion pydantic validation inside generate_ai_content.
    ai_quiz_question = {
        "id": "q1",
        "type": "mcq",
        "difficulty": "beginner",
        "objective": "Recall why fixed-length sprints surface risk early.",
        "question": "What does a sprint's fixed timebox force into the open?",
        "options": ["Working output, before optimism can compound", "Extra scope, to fill the schedule", "Nothing new"],
        "answer": "Working output, before optimism can compound",
        "explanation": "A fixed deadline cannot hide slippage the way a moving one can.",
    }

    class _FakeQuizProvider:
        def generate_json(self, system_prompt, user_payload, schema_name, *, model=None):
            return {"course_title": "Ramp Safety Briefing", "questions": [ai_quiz_question]}

    monkeypatch.setattr(server_module, "_text_provider_factory", lambda *a, **k: _FakeQuizProvider())
    status, quiz_response = _http_post(
        f"{studio_server['base_url']}/api/ai/{sid}/generate",
        open_token,
        {
            "system_prompt": "Generate one quiz question from this lesson's content.",
            "user_payload": {"lesson_id": target_lesson["id"], "content": "sprint content"},
            "schema_name": "quiz_from_content",
        },
    )
    _log("STEP 4: AI action 2 (quiz generation) response", quiz_response)
    assert status == 200, quiz_response
    assert quiz_response["ok"] is True
    assert quiz_response["result"]["questions"][0]["id"] == "q1"

    # ------------------------------------------------------------------
    # STEP 5: land both AI mutations + one new interaction type (hotspot) via a real PUT.
    # ------------------------------------------------------------------
    mutated_course = json.loads(json.dumps(course_before))  # deep copy
    for lesson in mutated_course["modules"][0]["lessons"]:
        for block in lesson["content_blocks"]:
            if block["id"] == "cb_1_intro":
                block["text"] = rewritten_text

    # AI-generated quiz question lands on the target lesson.
    for lesson in mutated_course["modules"][0]["lessons"]:
        if lesson["id"] == target_lesson["id"]:
            lesson.setdefault("quiz_questions", []).append(
                {
                    "id": ai_quiz_question["id"],
                    "type": ai_quiz_question["type"],
                    "difficulty": ai_quiz_question["difficulty"],
                    "objective_ids": [],
                    "question": ai_quiz_question["question"],
                    "options": ai_quiz_question["options"],
                    "correct_answers": [ai_quiz_question["answer"]],
                    "explanation": ai_quiz_question["explanation"],
                }
            )

    # New interaction type: hotspot activity (P5-4-adjacent, rendered by
    # exporters/scorm.py's renderHotspotActivity -- see that module's ordered
    # MATCH table for "hotspot").
    # The studio course.json's existing activities went through _player_activity()'s
    # course_schema_v2 Activity -> player-shape mapping, which renames "id" to
    # "activity_id" and "type" to "activity_type" (see tools.py's _player_activity).
    # Match that same on-disk convention for the newly added activity so it is
    # indistinguishable, in shape, from an activity that came through the normal
    # authoring pipeline -- both "id"/"type" are also included since
    # exporters/scorm.py's renderNativeActivity() falls back to them if
    # activity_id/activity_type are absent.
    hotspot_activity = {
        "id": "act_p56_hotspot",
        "activity_id": "act_p56_hotspot",
        "type": "hotspot",
        "activity_type": "hotspot",
        "title": "Find the FOD hazard",
        "instructions": "Click the area of the ramp diagram where FOD risk is highest before pushback.",
        "image": {"src": "assets/media/backlog-labels.svg", "alt": "Ramp diagram"},
        "regions": [
            {"x_pct": 10, "y_pct": 10, "width_pct": 20, "height_pct": 20, "tag": "correct", "label": "Engine intake zone", "feedback": "Correct -- FOD near the intake is the highest-risk area."},
            {"x_pct": 60, "y_pct": 60, "width_pct": 15, "height_pct": 15, "tag": "incorrect", "label": "Parked GPU", "feedback": "Not the highest-risk area."},
        ],
        "objective_ids": [],
    }
    mutated_course["modules"][0]["lessons"][0].setdefault("activities", []).append(hotspot_activity)

    status, put_response = _http_put(
        f"{studio_server['base_url']}/api/course/{sid}", open_token, {"course": mutated_course, "version": version_before}
    )
    _log("STEP 5: PUT /api/course/<sid> response", put_response)
    assert status == 200, put_response
    assert put_response["saved"] is True

    # Confirm on disk, reading the REAL course.json file the server just wrote.
    on_disk_path = studio_server["workspace_root"] / sid / "data" / "course.json"
    on_disk = json.loads(on_disk_path.read_text(encoding="utf-8"))
    on_disk_intro = next(
        b for lesson in on_disk["modules"][0]["lessons"] for b in lesson["content_blocks"] if b["id"] == "cb_1_intro"
    )
    assert on_disk_intro["text"] == rewritten_text
    assert any(q["id"] == "q1" for q in on_disk["modules"][0]["lessons"][0].get("quiz_questions", []))
    assert any(
        a.get("id") == "act_p56_hotspot" and a.get("type") == "hotspot"
        for a in on_disk["modules"][0]["lessons"][0].get("activities", [])
    )
    print(f"CONFIRMED: {on_disk_path} contains the rewritten block, the AI-generated quiz question, and the hotspot activity.")

    # ------------------------------------------------------------------
    # STEP 6: course-health checklist -- real course-health.js via a Node subprocess.
    # ------------------------------------------------------------------
    health_script_dir = tmp_path / "health"
    health_script_dir.mkdir()
    course_json_path = health_script_dir / "course.json"
    course_json_path.write_text(json.dumps(on_disk), encoding="utf-8")
    course_health_js = (
        Path(__file__).resolve().parents[1] / "apps" / "scorm_editor" / "frontend" / "src" / "course-health.js"
    )
    runner_path = health_script_dir / "run_health.mjs"
    runner_path.write_text(
        "import { runCourseHealthCheck } from " + json.dumps(course_health_js.as_uri()) + ";\n"
        "import { readFileSync } from 'node:fs';\n"
        "const course = JSON.parse(readFileSync(" + json.dumps(str(course_json_path)) + ", 'utf-8'));\n"
        "const findings = runCourseHealthCheck(course);\n"
        "console.log(JSON.stringify(findings, null, 2));\n",
        encoding="utf-8",
    )
    node_result = subprocess.run([sys.executable and "node" or "node", str(runner_path)], capture_output=True, text=True, timeout=30)
    _log("STEP 6: course-health stdout", node_result.stdout)
    if node_result.returncode != 0:
        _log("STEP 6: course-health stderr", node_result.stderr)
    assert node_result.returncode == 0, node_result.stderr
    findings = json.loads(node_result.stdout)
    categories = sorted({f["category"] for f in findings})
    print(f"course-health findings: {len(findings)} total, categories: {categories}")
    # cb_2_summary and several other blocks are short single-sentence "summary"/"reflection"
    # blocks by design (this fixture predates course-health and was authored for
    # test_canonical_flow.py, not to be a zero-finding fixture) -- expected findings are
    # short-block / missing-alt-text style content warnings, not structural errors. There must
    # be ZERO branching-graph or quiz-no-correct-answer findings, since every quiz question
    # (including the freshly AI-generated one) has a real correct answer, and this fixture has
    # no branching_scenario activities with dangling nodes.
    unexpected = [f for f in findings if f["category"] in ("branching_graph_issue", "quiz_no_correct_answer")]
    assert unexpected == [], unexpected
    print("CONFIRMED: zero unexpected (branching-graph / quiz-no-correct-answer) findings; remaining findings are expected content-completeness notes.")

    # ------------------------------------------------------------------
    # Pull the studio session's edited course.json back into the MCP project.
    # ------------------------------------------------------------------
    imported_back = import_studio_edits({"project_id": project_id, "session_id": sid}, context)
    _log("STEP 7 prep: import_studio_edits", imported_back)
    assert imported_back["ok"] is True, imported_back

    # ------------------------------------------------------------------
    # STEP 7: export via build_export_package -- confirm the AI-modified content, the new
    # interaction type, and a structurally valid SCORM zip.
    # ------------------------------------------------------------------
    exported = build_export_package({"project_id": project_id, "export_format": "scorm", "scorm_version": "1.2"}, context)
    _log("STEP 7: build_export_package result", exported)
    assert exported["ok"] is True, exported
    package_path = Path(exported["data"]["package_path"])
    assert package_path.is_file()
    package_size = package_path.stat().st_size
    print(f"CONFIRMED: real SCORM package at {package_path} ({package_size} bytes).")

    with zipfile.ZipFile(package_path) as zf:
        names = zf.namelist()
        assert "imsmanifest.xml" in names
        assert any(n.endswith("course.json") for n in names)
        course_json_name = next(n for n in names if n.endswith("course.json"))
        exported_course = json.loads(zf.read(course_json_name))
        bad = zf.testzip()
        assert bad is None, f"corrupt member in zip: {bad}"

    exported_text = json.dumps(exported_course)
    assert rewritten_text in exported_text, "AI-rewritten content block did not make it into the exported package"
    assert "q1" in exported_text, "AI-generated quiz question did not make it into the exported package"
    assert "act_p56_hotspot" in exported_text, "New hotspot interaction type did not make it into the exported package"
    print("CONFIRMED: exported SCORM zip contains the AI-rewritten block, the AI-generated quiz question, and the new hotspot activity.")

    # ------------------------------------------------------------------
    # STEP 8: LMS import -- documented honestly below (see report), NOT executed here.
    # ------------------------------------------------------------------
    print(
        "\nSTEP 8 (LMS import / Moodle conformance): NOT executed in this run. "
        "A real, non-decorative Moodle-conformance harness exists at "
        ".github/workflows/moodle-conformance.yml (clones moodle/moodle-docker, boots MySQL + "
        "PHP, runs a real Behat SCORM 1.2/2004 import-launch-relaunch-verify scenario against "
        "packages built by scripts/build_scorm_conformance_fixtures.py) and P4-1's ledger entry "
        "records it passing in a real GitHub Actions run. It needs no human-provided external "
        "credentials, but it is a multi-service Docker Compose job (full Moodle checkout + MySQL) "
        "that is impractical to stand up inside this sandboxed agent session for THIS specific "
        "package -- that is an infrastructure/CI-runtime constraint of this environment, not a "
        "human-approval gate like P4-1's SCORM Cloud sub-item. See the final report for the exact "
        "distinction and what would be needed to close this out for real."
    )
