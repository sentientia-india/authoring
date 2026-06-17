from __future__ import annotations

from html import escape
from pathlib import Path
from urllib.parse import urlparse
from zipfile import ZIP_DEFLATED, ZipFile

from ..schemas import ScormPackageRequest, ScormPackageResult


def _ensure_inside(parent: Path, child: Path) -> None:
    child.resolve().relative_to(parent.resolve())


def _module_page_name(index: int) -> str:
    return f"module-{index}.html"


def _write_zip(package_path: Path, base: Path, files: list[str]) -> None:
    with ZipFile(package_path, "w", ZIP_DEFLATED) as package:
        for file_name in files:
            package.write(base / file_name, file_name)


def _safe_video_url(module: dict) -> str | None:
    raw = module.get("video_url")
    if not isinstance(raw, str) or not raw:
        return None
    parsed = urlparse(raw)
    if parsed.scheme != "https":
        return None
    if parsed.netloc not in {"www.youtube-nocookie.com", "www.youtube.com", "youtube.com"}:
        return None
    return raw


def _styles_css() -> str:
    return """:root {
  --ink: #172033;
  --muted: #5b6475;
  --bg: #f5f7fb;
  --panel: #ffffff;
  --blue: #2563eb;
  --green: #12805c;
  --orange: #d97706;
  --line: #d8deea;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  color: var(--ink);
  background: var(--bg);
  font-family: Arial, Helvetica, sans-serif;
  line-height: 1.5;
}
.hero {
  min-height: 72vh;
  display: grid;
  grid-template-columns: minmax(280px, 1fr) minmax(260px, 460px);
  gap: 32px;
  align-items: center;
  padding: 40px min(6vw, 72px);
  background: linear-gradient(120deg, #eef6ff, #f8fbff 48%, #fff7ed);
  border-bottom: 1px solid var(--line);
}
.hero h1 { margin: 0; max-width: 760px; font-size: 54px; line-height: 1.02; }
.eyebrow { margin: 0 0 12px; color: var(--blue); font-weight: 700; text-transform: uppercase; font-size: 13px; }
.lede { max-width: 680px; color: var(--muted); font-size: 20px; }
.hero img, .module img { width: 100%; max-height: 360px; }
main { max-width: 1120px; margin: 0 auto; padding: 28px 20px 48px; }
.module, .interactive, .quiz {
  margin: 24px 0;
  padding: 24px;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
}
.module { display: grid; grid-template-columns: 1fr 420px; gap: 24px; align-items: center; }
.module.alt { grid-template-columns: 360px 1fr; }
h2 { margin-top: 0; font-size: 28px; }
.checks { padding-left: 20px; }
.video-card iframe { width: 100%; aspect-ratio: 16 / 9; border: 0; border-radius: 6px; background: #111827; }
.method-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
.method-grid div { padding: 14px; border: 1px solid var(--line); border-radius: 6px; background: #f8fafc; }
.method-grid span { display: block; color: var(--green); font-weight: 700; }
.activity-list { display: grid; gap: 12px; margin: 16px 0; }
.habit { display: grid; grid-template-columns: 1fr auto auto; gap: 10px; align-items: center; padding: 12px; border: 1px solid var(--line); border-radius: 6px; }
.habit button, .primary, .complete { min-height: 40px; border: 0; border-radius: 6px; padding: 10px 14px; font-weight: 700; cursor: pointer; }
.habit button { background: #e8eefc; color: var(--blue); }
.habit button.selected { background: var(--blue); color: white; }
.primary { background: var(--blue); color: white; }
.complete { background: var(--green); color: white; }
.prompt-builder { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
.prompt-builder label { display: grid; gap: 6px; color: var(--muted); font-weight: 700; }
input { width: 100%; border: 1px solid var(--line); border-radius: 6px; padding: 10px; font-size: 16px; }
.prompt-output { margin-top: 16px; min-height: 56px; padding: 14px; border-left: 4px solid var(--orange); background: #fff7ed; }
fieldset { margin: 14px 0; border: 1px solid var(--line); border-radius: 6px; padding: 14px; }
fieldset label { display: block; margin: 8px 0; }
.feedback { min-height: 28px; font-weight: 700; }
footer { padding: 24px min(6vw, 72px); background: #172033; color: #e5e7eb; }
@media (max-width: 820px) {
  .hero, .module, .module.alt, .prompt-builder { grid-template-columns: 1fr; }
  .hero h1 { font-size: 40px; }
  .method-grid { grid-template-columns: 1fr; }
  .habit { grid-template-columns: 1fr; }
}
"""


def _course_js() -> str:
    return """const habits = [
  { text: "Ask for a simple explanation before writing your answer.", answer: "smart" },
  { text: "Copy generated text without checking it.", answer: "risky" },
  { text: "Create practice questions for revision.", answer: "smart" },
  { text: "Share private passwords or IDs with an AI tool.", answer: "risky" },
  { text: "Compare AI answers with trusted course material.", answer: "smart" }
];
const choices = {};
function renderHabits() {
  const container = document.getElementById("sort-activity");
  if (!container) return;
  container.innerHTML = habits.map((habit, index) => `
    <div class="habit" data-index="${index}">
      <span>${habit.text}</span>
      <button type="button" onclick="chooseHabit(${index}, 'smart')">Smart use</button>
      <button type="button" onclick="chooseHabit(${index}, 'risky')">Risky use</button>
    </div>`).join("");
}
function chooseHabit(index, value) {
  choices[index] = value;
  document.querySelectorAll(`[data-index="${index}"] button`).forEach(button => {
    button.classList.toggle("selected", button.textContent.toLowerCase().startsWith(value));
  });
}
function checkSort() {
  let score = 0;
  habits.forEach((habit, index) => { if (choices[index] === habit.answer) score += 1; });
  document.getElementById("sort-feedback").textContent = `You sorted ${score} of ${habits.length} habits correctly.`;
  if (score === habits.length) CourseScorm.setScore(40);
}
function buildPrompt() {
  const topic = document.getElementById("topic").value.trim() || "my topic";
  const level = document.getElementById("level").value.trim() || "my level";
  const task = document.getElementById("task").value.trim() || "explain clearly";
  document.getElementById("prompt-output").textContent =
    `Explain ${topic} in simple words for a ${level} learner. Please ${task}. Include 3 examples and one practice question.`;
}
function gradeQuiz() {
  const form = document.getElementById("quiz-form");
  const questions = ["q1", "q2", "q3"];
  const score = questions.reduce((total, name) => {
    const selected = form.querySelector(`input[name="${name}"]:checked`);
    return total + (selected && selected.value === "correct" ? 1 : 0);
  }, 0);
  const percent = Math.round((score / questions.length) * 100);
  document.getElementById("quiz-feedback").textContent = `Score: ${score}/${questions.length} (${percent}%).`;
  CourseScorm.setScore(percent);
  if (percent >= 67) CourseScorm.markComplete();
}
function markCourseComplete() {
  CourseScorm.markComplete();
  document.querySelector("footer p").textContent = "Course marked complete. You can close this lesson.";
}
renderHabits();
"""


def _runtime_js() -> str:
    return """window.CourseScorm = {
  api: function () { return window.API || window.API_1484_11 || null; },
  setScore: function (score) {
    var api = this.api();
    if (!api) return false;
    if (api.LMSSetValue) {
      api.LMSSetValue("cmi.core.score.raw", String(score));
      api.LMSCommit && api.LMSCommit("");
      return true;
    }
    if (api.SetValue) {
      api.SetValue("cmi.score.raw", String(score));
      api.Commit && api.Commit("");
      return true;
    }
    return false;
  },
  markComplete: function () {
    var api = this.api();
    if (!api) return false;
    if (api.LMSSetValue) {
      api.LMSSetValue("cmi.core.lesson_status", "completed");
      api.LMSCommit && api.LMSCommit("");
      return true;
    }
    if (api.SetValue) {
      api.SetValue("cmi.completion_status", "completed");
      api.Commit && api.Commit("");
      return true;
    }
    return false;
  }
};
"""


def _study_map_svg() -> str:
    return """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 460" role="img" aria-label="Course study map">
  <rect width="640" height="460" rx="28" fill="#eff6ff"/>
  <circle cx="510" cy="92" r="54" fill="#f97316" opacity=".16"/>
  <rect x="70" y="94" width="330" height="230" rx="18" fill="#fff" stroke="#cbd5e1" stroke-width="3"/>
  <rect x="96" y="124" width="140" height="18" rx="9" fill="#2563eb"/>
  <rect x="96" y="162" width="250" height="14" rx="7" fill="#cbd5e1"/>
  <rect x="96" y="192" width="220" height="14" rx="7" fill="#cbd5e1"/>
  <rect x="96" y="222" width="190" height="14" rx="7" fill="#cbd5e1"/>
  <rect x="96" y="262" width="108" height="34" rx="10" fill="#12805c"/>
  <circle cx="454" cy="244" r="86" fill="#172033"/>
  <circle cx="426" cy="226" r="10" fill="#fff"/>
  <circle cx="482" cy="226" r="10" fill="#fff"/>
  <path d="M418 270c26 22 52 22 78 0" fill="none" stroke="#fff" stroke-width="8" stroke-linecap="round"/>
  <rect x="120" y="352" width="420" height="42" rx="21" fill="#dbeafe"/>
  <rect x="148" y="365" width="180" height="16" rx="8" fill="#2563eb" opacity=".8"/>
</svg>"""


def _prompt_lab_svg() -> str:
    return """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 560 420" role="img" aria-label="Prompt lab cards">
  <rect width="560" height="420" rx="24" fill="#fff7ed"/>
  <rect x="52" y="58" width="456" height="304" rx="20" fill="#ffffff" stroke="#fed7aa" stroke-width="4"/>
  <rect x="82" y="90" width="190" height="20" rx="10" fill="#d97706"/>
  <rect x="82" y="138" width="396" height="48" rx="12" fill="#f8fafc" stroke="#cbd5e1"/>
  <rect x="82" y="206" width="396" height="48" rx="12" fill="#ecfeff" stroke="#67e8f9"/>
  <rect x="82" y="274" width="174" height="54" rx="14" fill="#2563eb"/>
  <circle cx="406" cy="302" r="52" fill="#12805c" opacity=".14"/>
  <path d="M374 302l22 22 46-54" fill="none" stroke="#12805c" stroke-width="12" stroke-linecap="round" stroke-linejoin="round"/>
</svg>"""


def validate_scorm_package(package_path: Path | str, expected_files: list[str]) -> dict:
    errors: list[str] = []
    path = Path(package_path)
    if not path.exists():
        return {"valid": False, "errors": [f"Package does not exist: {path.name}"]}
    if path.suffix.lower() != ".zip":
        errors.append("Package must be a .zip file.")

    try:
        with ZipFile(path) as package:
            names = set(package.namelist())
            for file_name in expected_files:
                if file_name not in names:
                    errors.append(f"Missing package file: {file_name}")
            manifest = package.read("imsmanifest.xml").decode("utf-8") if "imsmanifest.xml" in names else ""
            if manifest and "<manifest" not in manifest:
                errors.append("imsmanifest.xml does not contain a manifest root.")
            if manifest and "adlcp:scormtype=\"sco\"" not in manifest:
                errors.append("Manifest does not declare a SCO resource.")
    except Exception:
        errors.append("Package is not a readable zip archive.")

    return {"valid": not errors, "errors": errors}


def build_scorm_scaffold(req: ScormPackageRequest, output_dir: str) -> dict:
    root = Path(output_dir).resolve()
    base = root / req.course_slug
    _ensure_inside(root, base)
    base.mkdir(parents=True, exist_ok=True)
    assets = base / "assets"
    assets.mkdir(exist_ok=True)
    module_files = [_module_page_name(i) for i, _module in enumerate(req.modules, start=1)]
    asset_files = [
        "assets/styles.css",
        "assets/course.js",
        "assets/scorm_api.js",
        "assets/study-map.svg",
        "assets/prompt-lab.svg",
    ]
    files = ["imsmanifest.xml", "index.html", *module_files, *asset_files]

    manifest = f'''<?xml version="1.0" encoding="UTF-8"?>
<manifest identifier="{escape(req.course_slug)}" version="1.0"
  xmlns="http://www.imsproject.org/xsd/imscp_rootv1p1p2"
  xmlns:adlcp="http://www.adlnet.org/xsd/adlcp_rootv1p2">
  <metadata>
    <schema>ADL SCORM</schema>
    <schemaversion>{escape(req.scorm_version)}</schemaversion>
  </metadata>
  <organizations default="org1">
    <organization identifier="org1">
      <title>{escape(req.course_title)}</title>
      <item identifier="item1" identifierref="res1">
        <title>{escape(req.course_title)}</title>
      </item>
    </organization>
  </organizations>
  <resources>
    <resource identifier="res1" type="webcontent" adlcp:scormtype="sco" href="index.html">
      <file href="index.html" />
{chr(10).join(f'      <file href="{escape(file_name)}" />' for file_name in module_files)}
{chr(10).join(f'      <file href="{escape(file_name)}" />' for file_name in asset_files)}
    </resource>
  </resources>
</manifest>
'''
    navigation = "\n".join(
        f'<li><a href="{escape(file_name)}">{escape(module.get("title", f"Module {i}"))}</a></li>'
        for i, (file_name, module) in enumerate(zip(module_files, req.modules, strict=True), start=1)
    )
    first_video = next((_safe_video_url(module) for module in req.modules if _safe_video_url(module)), None)
    video_block = (
        f'''<div class="video-card">
        <iframe src="{escape(first_video)}" title="{escape(req.course_title)} video" allowfullscreen></iframe>
      </div>'''
        if first_video
        else """<div class="video-card"><p>Video block ready. Add an approved YouTube embed URL to the module JSON to show media here.</p></div>"""
    )
    index = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(req.course_title)}</title>
  <link rel="stylesheet" href="assets/styles.css">
  <script src="assets/scorm_api.js"></script>
</head>
<body>
  <header class="hero">
    <div>
      <p class="eyebrow">Interactive SCORM course</p>
      <h1>{escape(req.course_title)}</h1>
      <p class="lede">A guided micro-course with lesson content, media, interactive practice, quiz scoring, and SCORM completion tracking.</p>
    </div>
    <img src="assets/study-map.svg" alt="Course study map">
  </header>
  <main>
    <section class="module">
      <div class="module-text">
        <h2>How to use this course</h2>
        <p>Move through each module, complete the interactive checks, and submit the final quiz. Your LMS can capture score and completion when SCORM APIs are available.</p>
        <ul class="checks">{navigation}</ul>
      </div>
      {video_block}
    </section>
    <section class="module alt">
      <img src="assets/prompt-lab.svg" alt="Interactive prompt lab">
      <div class="module-text">
        <h2>Practice method</h2>
        <p>Use the activity below to classify habits, build a useful prompt, and complete a short knowledge check.</p>
        <div class="method-grid">
          <div><span>Learn</span><p>Read the module objective.</p></div>
          <div><span>Practice</span><p>Try an interactive activity.</p></div>
          <div><span>Prove</span><p>Submit the quiz and mark complete.</p></div>
        </div>
      </div>
    </section>
    <section class="interactive">
      <h2>Interactive 1: Sort the habits</h2>
      <p>Choose whether each behavior is a smart use or risky use.</p>
      <div id="sort-activity" class="activity-list"></div>
      <button class="primary" type="button" onclick="checkSort()">Check habits</button>
      <p id="sort-feedback" class="feedback" role="status"></p>
    </section>
    <section class="interactive">
      <h2>Interactive 2: Prompt builder</h2>
      <p>Fill the boxes, then generate a stronger learning prompt.</p>
      <div class="prompt-builder">
        <label>Topic <input id="topic" value="{escape(req.course_title)}"></label>
        <label>Level <input id="level" value="beginner"></label>
        <label>Task <input id="task" value="explain simply with examples"></label>
      </div>
      <button class="primary" type="button" onclick="buildPrompt()">Build prompt</button>
      <div id="prompt-output" class="prompt-output"></div>
    </section>
    <section class="quiz">
      <h2>Final quiz</h2>
      <form id="quiz-form">
        <fieldset>
          <legend>1. What is the best way to use learning content?</legend>
          <label><input type="radio" name="q1" value="correct"> Read, practice, and check understanding</label>
          <label><input type="radio" name="q1" value="wrong"> Skip directly to completion</label>
        </fieldset>
        <fieldset>
          <legend>2. What should you do after an AI-generated answer?</legend>
          <label><input type="radio" name="q2" value="correct"> Check it and explain it in your own words</label>
          <label><input type="radio" name="q2" value="wrong"> Submit it without reading</label>
        </fieldset>
        <fieldset>
          <legend>3. What makes a good prompt?</legend>
          <label><input type="radio" name="q3" value="correct"> Topic, level, task, and examples requested</label>
          <label><input type="radio" name="q3" value="wrong"> A vague instruction with no context</label>
        </fieldset>
      </form>
      <button class="primary" type="button" onclick="gradeQuiz()">Submit quiz</button>
      <p id="quiz-feedback" class="feedback" role="status"></p>
    </section>
  </main>
  <footer>
    <button class="complete" type="button" onclick="markCourseComplete()">Mark course complete</button>
    <p>Generated by Samrat Course MCP.</p>
  </footer>
  <script src="assets/course.js"></script>
</body>
</html>
"""

    (base / "imsmanifest.xml").write_text(manifest, encoding="utf-8")
    (base / "index.html").write_text(index, encoding="utf-8")
    (assets / "styles.css").write_text(_styles_css(), encoding="utf-8")
    (assets / "course.js").write_text(_course_js(), encoding="utf-8")
    (assets / "scorm_api.js").write_text(_runtime_js(), encoding="utf-8")
    (assets / "study-map.svg").write_text(_study_map_svg(), encoding="utf-8")
    (assets / "prompt-lab.svg").write_text(_prompt_lab_svg(), encoding="utf-8")
    for i, (file_name, module) in enumerate(zip(module_files, req.modules, strict=True), start=1):
        lessons = module.get("lessons", [])
        lesson_items = "\n".join(
            f"<li>{escape(str(lesson.get('title', 'Lesson')))}: "
            f"{escape(str(lesson.get('objective', 'Practice the module objective.')))}</li>"
            for lesson in lessons
        )
        page = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(str(module.get("title", f"Module {i}")))}</title>
  <link rel="stylesheet" href="assets/styles.css">
  <script src="assets/scorm_api.js"></script>
</head>
<body>
  <main>
    <section class="module">
      <div class="module-text">
        <p><a href="index.html">Course index</a></p>
        <h1>{escape(str(module.get("title", f"Module {i}")))}</h1>
        <ul class="checks">{lesson_items}</ul>
      </div>
      <img src="assets/study-map.svg" alt="Module study map">
    </section>
  </main>
  <footer>
    <button class="complete" type="button" onclick="CourseScorm.markComplete()">Mark complete</button>
  </footer>
</body>
</html>
"""
        (base / file_name).write_text(page, encoding="utf-8")

    package_path = root / f"{req.course_slug}.zip"
    _ensure_inside(root, package_path)
    _write_zip(package_path, base, files)
    validation = validate_scorm_package(package_path, files)

    return ScormPackageResult(
        course_title=req.course_title,
        course_slug=req.course_slug,
        scorm_version=req.scorm_version,
        artifact_path=str(base),
        package_path=str(package_path),
        files=files,
        note=(
            "SCORM package scaffold created and internally validated."
            if validation["valid"]
            else "SCORM package scaffold created but validation reported issues."
        ),
    ).model_dump(mode="json")
