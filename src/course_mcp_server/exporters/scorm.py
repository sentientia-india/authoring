from __future__ import annotations

import copy
import json
from html import escape
from pathlib import Path
from urllib.parse import urlparse
from zipfile import ZIP_DEFLATED, ZipFile

from ..html_video_engine import build_video_project_from_course
from ..schemas import ScormPackageRequest, ScormPackageResult


TECHNICAL_UI_REPLACEMENTS = {
    "SCORM course player": "Course overview",
    "SCORM": "course",
    "LMS": "learning platform",
    "source-aware": "course-based",
    "generated lessons": "lessons",
    "generated activities": "practice activities",
    "suspend/resume data": "saved progress",
    "suspend data": "saved progress",
    "course package": "course",
    "completion tracking": "progress tracking",
    "objective aligned": "Learning goal",
    "source aligned": "Based on course material",
    "expected learner decisions": "what to do in realistic situations",
    "LMS can capture": "Your progress saves",
}


def _learner_safe_text(value: object) -> str:
    text = "" if value is None else str(value)
    for technical, learner_copy in TECHNICAL_UI_REPLACEMENTS.items():
        text = text.replace(technical, learner_copy)
    return text


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
  --ink: #111827;
  --muted: #5b6475;
  --bg: #eef2f8;
  --panel: #ffffff;
  --blue: #2563eb;
  --green: #0f766e;
  --orange: #d97706;
  --line: #d7ddea;
  --soft-line: #e8edf5;
  --sidebar: #0f172a;
  --sidebar-top: #1e293b;
  --hero-start: #f4f8ff;
  --hero-mid: #ffffff;
  --hero-end: #fff7ed;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  color: var(--ink);
  background: var(--bg);
  font-family: "Segoe UI", "Aptos", "Helvetica Neue", Arial, sans-serif;
  line-height: 1.5;
}
body[data-theme="compliance"] {
  --blue: #1d4ed8;
  --green: #0f766e;
  --orange: #d97706;
  --bg: #f5f7fb;
  --panel: #ffffff;
  --sidebar: #0f172a;
  --sidebar-top: #1f2937;
  --hero-start: #e8f1ff;
  --hero-mid: #f8fbff;
  --hero-end: #fff6ea;
}
body[data-theme="academy"] {
  --blue: #7c3aed;
  --green: #0f766e;
  --orange: #ca8a04;
  --bg: #fbf7ff;
  --panel: #ffffff;
  --sidebar: #24153f;
  --sidebar-top: #372357;
  --hero-start: #f2ebff;
  --hero-mid: #faf8ff;
  --hero-end: #fff4e9;
}
body[data-theme="studio"] {
  --blue: #0f766e;
  --green: #2563eb;
  --orange: #ea580c;
  --bg: #f3faf8;
  --panel: #ffffff;
  --sidebar: #072329;
  --sidebar-top: #0f3a3d;
  --hero-start: #e3faf4;
  --hero-mid: #f7fffc;
  --hero-end: #fff4e8;
}
.course-shell {
  min-height: 100vh;
  display: grid;
  grid-template-columns: 320px 1fr;
}
.course-sidebar {
  position: sticky;
  top: 0;
  height: 100vh;
  padding: 22px 18px;
  color: #e5e7eb;
  background:
    radial-gradient(circle at top, rgba(255,255,255,.08), transparent 30%),
    linear-gradient(180deg, var(--sidebar-top), var(--sidebar));
  overflow: auto;
  border-right: 1px solid rgba(255,255,255,.08);
}
.course-sidebar h1 { margin: 0 0 14px; font-size: 26px; line-height: 1.08; letter-spacing: -.03em; }
.course-sidebar a { color: #dbeafe; text-decoration: none; }
.progress-ring {
  display: grid;
  place-items: center;
  width: 112px;
  height: 112px;
  margin: 22px 0;
  border-radius: 999px;
  background: conic-gradient(#38bdf8 0 35%, #334155 35% 100%);
  box-shadow: inset 0 0 0 1px rgba(255,255,255,.08);
}
.progress-ring span {
  display: grid;
  place-items: center;
  width: 82px;
  height: 82px;
  border-radius: 999px;
  background: #0f172a;
  font-size: 24px;
  font-weight: 700;
}
.module-nav { display: grid; gap: 8px; padding: 0; list-style: none; }
.module-nav li { padding: 10px 12px; border: 1px solid rgba(255,255,255,.08); border-radius: 12px; background: rgba(255,255,255,.04); }
.module-nav-button {
  width: 100%;
  border: 0;
  padding: 0;
  color: inherit;
  background: transparent;
  text-align: left;
  font: inherit;
  cursor: pointer;
}
.lesson-workspace { min-width: 0; }
.hero {
  min-height: 54vh;
  display: grid;
  grid-template-columns: minmax(0, 1.08fr) minmax(260px, .92fr);
  gap: 28px;
  align-items: center;
  padding: 44px min(6vw, 72px);
  background: linear-gradient(120deg, var(--hero-start), var(--hero-mid) 48%, var(--hero-end));
  border-bottom: 1px solid var(--line);
}
.hero h1 { margin: 0; max-width: 760px; font-size: clamp(42px, 4.2vw, 60px); line-height: 1.02; letter-spacing: -.04em; }
.eyebrow { margin: 0 0 12px; color: var(--blue); font-weight: 700; text-transform: uppercase; font-size: 13px; }
.lede { max-width: 680px; color: #3f4755; font-size: 18px; }
.hero img, .module img { width: 100%; max-height: 360px; object-fit: cover; }
.course-stats { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin: 22px 0; }
.course-stats div {
  padding: 15px 14px;
  border: 1px solid rgba(215,221,234,.9);
  border-radius: 14px;
  background: rgba(255,255,255,.84);
  box-shadow: 0 12px 30px rgba(15, 23, 42, .04);
}
.course-stats strong { display: block; font-size: 24px; line-height: 1; }
.course-stats span { display: block; margin-top: 6px; color: var(--muted); font-size: 13px; font-weight: 700; }
.hero-actions { display: flex; gap: 10px; flex-wrap: wrap; }
.game-card { margin: 18px 0; padding: 14px; border: 1px solid rgba(255,255,255,.14); border-radius: 8px; background: rgba(255,255,255,.06); }
.game-card strong { display: block; color: #fff; font-size: 22px; }
.game-card span { color: #cbd5e1; font-size: 13px; }
.badge-row { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 10px; }
.badge-pill { padding: 5px 9px; border: 1px solid #334155; border-radius: 999px; color: #cbd5e1; background: rgba(255,255,255,.04); font-size: 12px; font-weight: 700; }
.badge-pill.earned { border-color: #86efac; color: #dcfce7; background: rgba(18,128,92,.28); }
main { max-width: 1180px; margin: 0 auto; padding: 28px 20px 56px; }
.course-panel {
  display: grid;
  gap: 16px;
}
.course-panel-header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
}
.course-panel-title { margin: 0; font-size: 24px; }
.course-panel-subtitle { margin: 4px 0 0; color: var(--muted); }
.lesson-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
.lesson-card {
  display: grid;
  gap: 12px;
  padding: 18px;
  border: 1px solid var(--line);
  border-radius: 14px;
  background: linear-gradient(180deg, #fff, #fafcff);
  transition: border-color .18s ease, background .18s ease, box-shadow .18s ease, transform .18s ease;
}
.lesson-card h3 { margin: 0 0 8px; }
.lesson-card .lesson-meta { display: flex; gap: 12px; flex-wrap: wrap; color: var(--muted); font-size: 13px; }
.lesson-card.active { border-color: rgba(37,99,235,.5); box-shadow: 0 12px 32px rgba(37, 99, 235, .14); transform: translateY(-1px); }
.lesson-card.completed { border-color: rgba(15,118,110,.35); background: linear-gradient(180deg, #f4fbf8, #fff); }
.lesson-reader {
  display: grid;
  gap: 18px;
  margin-top: 18px;
  padding: 26px;
  border: 1px solid #d5ddea;
  border-radius: 18px;
  background:
    radial-gradient(circle at top right, rgba(37,99,235,.06), transparent 28%),
    linear-gradient(180deg, #ffffff 0%, #f8fbff 100%);
  box-shadow: 0 18px 48px rgba(23, 32, 51, .08);
}
.lesson-reader-header { display: grid; gap: 10px; padding-bottom: 16px; border-bottom: 1px solid var(--line); }
.lesson-reader-kicker { color: var(--green); font-size: 12px; font-weight: 800; letter-spacing: .08em; text-transform: uppercase; }
.lesson-reader-title { margin: 0; font-size: 30px; line-height: 1.12; letter-spacing: -.03em; }
.lesson-reader-objective { margin: 0; color: #374151; font-size: 17px; }
.lesson-reader-meta { display: flex; gap: 10px; flex-wrap: wrap; color: var(--muted); font-size: 13px; }
.lesson-reader-meta span {
  padding: 6px 10px;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: #fff;
}
.lesson-block-grid { display: grid; grid-template-columns: minmax(0, 1fr) minmax(280px, .82fr); gap: 18px; align-items: start; }
.lesson-block-main { display: grid; gap: 12px; }
.lesson-block {
  display: grid;
  gap: 8px;
  padding: 16px 16px 15px;
  border: 1px solid var(--soft-line);
  border-radius: 14px;
  background: linear-gradient(180deg, #fff, #fbfcfe);
}
.lesson-block strong { color: var(--green); font-size: 12px; letter-spacing: .08em; text-transform: uppercase; }
.lesson-block p { margin: 0; color: #293548; }
.lesson-practice-card {
  display: grid;
  gap: 12px;
  padding: 18px;
  border-radius: 16px;
  background: linear-gradient(180deg, #fff7ed, #fffaf4);
  border: 1px solid #fed7aa;
  align-self: start;
}
.lesson-practice-card strong { color: #9a3412; font-size: 13px; letter-spacing: .04em; text-transform: uppercase; }
.lesson-practice-card p { margin: 0; color: #3b2b1b; }
.lesson-reader-actions { display: flex; gap: 10px; flex-wrap: wrap; padding-top: 4px; }
.reader-side-panel { display: grid; gap: 12px; }
.reader-side-panel .lesson-practice-card + .lesson-practice-card { background: linear-gradient(180deg, #eef6ff, #ffffff); border-color: #bfdbfe; }
.reader-side-panel .lesson-practice-card + .lesson-practice-card strong { color: var(--blue); }
.lesson-source-note { margin: 0; color: var(--muted); font-size: 13px; }
.lesson-card button { align-self: start; }
.lesson-actions { display: flex; gap: 10px; flex-wrap: wrap; }
.secondary {
  min-height: 40px;
  border: 1px solid var(--line);
  border-radius: 999px;
  padding: 10px 14px;
  font-weight: 700;
  cursor: pointer;
  background: #edf2f7;
  color: var(--ink);
}
.module, .interactive, .quiz {
  margin: 24px 0;
  padding: 24px;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 18px;
  box-shadow: 0 14px 34px rgba(15, 23, 42, .04);
}
.module { display: grid; grid-template-columns: 1fr 420px; gap: 24px; align-items: center; }
.module-full { grid-template-columns: 1fr; }
.module.alt { grid-template-columns: 360px 1fr; }
h2 { margin-top: 0; font-size: 28px; letter-spacing: -.02em; }
.checks { padding-left: 20px; }
.video-card iframe { width: 100%; aspect-ratio: 16 / 9; border: 0; border-radius: 6px; background: #111827; }
.method-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
.method-grid div {
  padding: 14px;
  border: 1px solid var(--line);
  border-radius: 14px;
  background: linear-gradient(180deg, #f8fafc, #ffffff);
}
.method-grid span { display: block; color: var(--green); font-weight: 700; }
.activity-list { display: grid; gap: 12px; margin: 16px 0; }
.embedded-activity { margin: 12px 0; padding: 14px; border: 1px solid var(--line); border-radius: 14px; background: #f8fafc; }
.embedded-activity h3 { margin: 0 0 6px; }
.embedded-activity span { display: inline-block; color: var(--green); font-weight: 700; }
.activity-shell { display: grid; gap: 12px; }
.activity-card { padding: 18px; border: 1px solid var(--line); border-radius: 18px; background: linear-gradient(180deg, #fff, #fcfdff); display: grid; gap: 10px; }
.activity-card.completed { border-color: #b7dfd2; background: linear-gradient(180deg, #f3fbf8, #fff); }
.activity-status { display: inline-flex; width: max-content; align-items: center; padding: 5px 9px; border-radius: 999px; color: var(--muted); background: #f8fafc; border: 1px solid var(--line); font-size: 12px; font-weight: 800; }
.activity-card.completed .activity-status { color: var(--green); background: #ecfdf3; border-color: #bbf7d0; }
.activity-card h3 { margin: 0; }
.activity-card .activity-type { color: var(--green); font-weight: 700; text-transform: uppercase; font-size: 12px; }
.activity-card .activity-feedback { min-height: 24px; color: var(--muted); }
.flashcard-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.flashcard { min-height: 116px; padding: 14px; border: 1px solid var(--line); border-radius: 8px; background: #f8fafc; text-align: left; cursor: pointer; }
.flashcard strong { display: block; margin-bottom: 8px; color: var(--ink); }
.flashcard .flashcard-back { display: none; color: var(--green); font-weight: 700; }
.flashcard.is-flipped { background: #f3fbf8; border-color: #b7dfd2; }
.flashcard.is-flipped .flashcard-back { display: block; }
.accordion-list { display: grid; gap: 10px; }
.accordion-item { border: 1px solid var(--line); border-radius: 8px; background: #fff; overflow: hidden; }
.accordion-item button { width: 100%; border: 0; padding: 12px 14px; background: #f8fafc; color: var(--ink); font: inherit; font-weight: 700; text-align: left; cursor: pointer; }
.accordion-panel { display: none; padding: 12px 14px; color: var(--muted); border-top: 1px solid var(--line); }
.accordion-item.is-open .accordion-panel { display: block; }
.timeline-list { display: grid; gap: 0; border-left: 3px solid #b7dfd2; margin-left: 10px; padding-left: 18px; }
.timeline-item { position: relative; padding: 0 0 16px; }
.timeline-item::before { content: ""; position: absolute; left: -27px; top: 4px; width: 14px; height: 14px; border-radius: 999px; background: var(--green); }
.timeline-item strong { display: block; color: var(--ink); }
.fill-blank-row { display: grid; gap: 8px; max-width: 520px; }
.fill-blank-row label { display: grid; gap: 6px; font-weight: 700; color: var(--muted); }
.reflection-box { display: grid; gap: 8px; color: var(--muted); font-weight: 700; }
textarea { width: 100%; border: 1px solid var(--line); border-radius: 6px; padding: 10px; font: inherit; resize: vertical; }
.roleplay-grid { display: grid; grid-template-columns: minmax(0, .72fr) minmax(260px, 1fr); gap: 14px; align-items: start; }
.roleplay-persona, .roleplay-rubric, .roleplay-response { display: grid; gap: 10px; padding: 14px; border: 1px solid var(--line); border-radius: 8px; background: #f8fafc; }
.roleplay-persona strong, .roleplay-rubric strong, .roleplay-response strong { color: var(--ink); }
.roleplay-rubric ul { margin: 0; padding-left: 20px; }
.roleplay-response textarea { min-height: 118px; background: #fff; }
.scenario-options { display: grid; gap: 10px; }
.scenario-options button.is-selected { outline: 3px solid rgba(18, 128, 92, .18); transform: translateY(-1px); }
.scenario-consequence { margin-top: 8px; padding: 12px; border: 1px solid #fed7aa; border-radius: 12px; background: #fff7ed; color: #3b2b1b; }
.scenario-prompt { margin: 0; padding: 12px; border-left: 4px solid var(--orange); background: #fff7ed; }
.match-row { display: grid; grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr); gap: 10px; align-items: center; padding: 12px; border: 1px solid var(--line); border-radius: 8px; background: #f8fafc; }
.match-result { color: var(--green); font-weight: 700; }
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
.quiz-question-card { display: grid; gap: 12px; margin-top: 16px; padding: 18px; border: 1px solid var(--line); border-radius: 8px; background: #fff; }
.quiz-question-card { border-radius: 16px; }
.quiz-question-card label { display: flex; gap: 10px; align-items: flex-start; padding: 12px; border: 1px solid var(--line); border-radius: 12px; background: #f8fafc; cursor: pointer; }
.quiz-question-card label.is-selected { border-color: var(--blue); background: #eff6ff; }
.quiz-question-card.is-hidden { display: none; }
.assessment-nav { display: flex; gap: 10px; flex-wrap: wrap; align-items: center; margin-top: 14px; }
.assessment-nav .secondary[disabled] { opacity: .48; cursor: not-allowed; }
.quiz-progress-text { color: var(--muted); font-size: 13px; font-weight: 800; text-transform: uppercase; }
.quiz-result-card, .completion-screen { display: grid; gap: 14px; padding: 24px; border: 1px solid var(--line); border-radius: 18px; background: #fff; text-align: center; }
.quiz-score, .completion-score { font-size: 48px; line-height: 1; font-weight: 900; color: var(--green); }
.completion-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
.completion-grid div { padding: 14px; border: 1px solid var(--line); border-radius: 14px; background: #f8fafc; }
.completion-grid strong { display: block; font-size: 22px; }
.feedback { min-height: 28px; font-weight: 700; }
footer {
  padding: 24px min(6vw, 72px);
  background: linear-gradient(180deg, #111827, #0f172a);
  color: #e5e7eb;
}
@media (max-width: 820px) {
  .course-shell { grid-template-columns: 1fr; }
  .course-sidebar { position: static; height: auto; }
  .hero, .module, .module.alt, .prompt-builder { grid-template-columns: 1fr; }
  .course-stats { grid-template-columns: 1fr; }
  .lesson-grid { grid-template-columns: 1fr; }
  .lesson-block-grid { grid-template-columns: 1fr; }
  .roleplay-grid { grid-template-columns: 1fr; }
  .match-row { grid-template-columns: 1fr; }
  .hero h1 { font-size: 40px; }
  .method-grid { grid-template-columns: 1fr; }
  .completion-grid { grid-template-columns: 1fr; }
  .habit { grid-template-columns: 1fr; }
  .lesson-reader { padding: 20px; }
  .lesson-block-grid { gap: 12px; }
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
      <button type="button" data-choice="smart">Smart use</button>
      <button type="button" data-choice="risky">Risky use</button>
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
  const footerMessage = document.querySelector("footer p");
  if (footerMessage) footerMessage.textContent = "Course marked complete. You can close this lesson.";
}
function bindStaticCourseControls() {
  renderHabits();
  const promptButton = document.getElementById("prompt-build");
  if (promptButton) promptButton.addEventListener("click", buildPrompt);
  const completeButton = document.getElementById("course-complete");
  if (completeButton) completeButton.addEventListener("click", markCourseComplete);
  const moduleCompleteButton = document.getElementById("module-complete");
  if (moduleCompleteButton) moduleCompleteButton.addEventListener("click", markCourseComplete);
  const sortActivity = document.getElementById("sort-activity");
  if (sortActivity && !sortActivity.dataset.bound) {
    sortActivity.dataset.bound = "true";
    sortActivity.addEventListener("click", (event) => {
      const button = event.target.closest("button[data-choice]");
      if (!button) return;
      const habit = button.closest("[data-index]");
      if (!habit) return;
      chooseHabit(Number(habit.dataset.index), button.dataset.choice);
    });
  }
}
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", bindStaticCourseControls);
} else {
  bindStaticCourseControls();
}
"""


def _theme_for_course(course_title: str, audience: str) -> str:
    text = f"{course_title} {audience}".lower()
    if any(keyword in text for keyword in ("safety", "sop", "evac", "crew", "compliance", "policy", "airline")):
        return "compliance"
    if any(keyword in text for keyword in ("student", "academy", "study", "training", "learn")):
        return "academy"
    return "studio"


def _course_payload(req: ScormPackageRequest) -> dict:
    for module in req.modules:
        payload = module.get("course_payload")
        if isinstance(payload, dict):
            return payload
    return {
        "course_title": req.course_title,
        "course_slug": req.course_slug,
        "modules": req.modules,
    }


def _remove_h5p_markers(value):
    if isinstance(value, dict):
        return {
            key: _remove_h5p_markers(item)
            for key, item in value.items()
            if key.lower() not in {"h5p_style", "h5p", "h5p_package"}
        }
    if isinstance(value, list):
        return [_remove_h5p_markers(item) for item in value]
    return value


def _sanitize_learner_strings(value):
    if isinstance(value, dict):
        return {key: _sanitize_learner_strings(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_learner_strings(item) for item in value]
    if isinstance(value, str):
        return _learner_safe_text(value)
    return value


def _activity_key(activity: dict) -> str:
    return json.dumps(
        {
            "type": activity.get("activity_type") or activity.get("type"),
            "title": activity.get("title"),
            "objective": activity.get("objective"),
            "items": activity.get("items", []),
        },
        sort_keys=True,
        default=str,
    )


def _dedupe_activities(activities: list[dict]) -> list[dict]:
    seen: set[str] = set()
    output: list[dict] = []
    for activity in activities:
        if not isinstance(activity, dict):
            continue
        key = _activity_key(activity)
        if key in seen:
            continue
        seen.add(key)
        output.append(activity)
    return output


def _fallback_assessment(course: dict) -> dict:
    lessons = [
        lesson
        for module in course.get("modules", [])
        for lesson in module.get("lessons", [])
        if isinstance(lesson, dict)
    ]
    questions = []
    for index, lesson in enumerate(lessons[:4], start=1):
        objective = lesson.get("objective") or "Apply the lesson objective."
        title = lesson.get("title") or f"Lesson {index}"
        questions.append(
            {
                "id": f"q_{index}",
                "type": "mcq",
                "objective_ids": lesson.get("objective_ids", ["lo_apply"]),
                "question": f"Which action best supports: {objective}",
                "options": [
                    f"Apply the guidance from {title}",
                    "Skip the check to save time",
                    "Wait without making a decision",
                ],
                "correct_answers": [f"Apply the guidance from {title}"],
                "explanation": "The best answer applies the lesson objective in a realistic work situation.",
            }
        )
    return {
        "id": "assessment_final",
        "title": "Final Check",
        "passing_score": 80,
        "questions": questions,
    }


def _fallback_module_activity(module: dict, module_index: int) -> dict:
    lesson = next((item for item in module.get("lessons", []) if isinstance(item, dict)), {})
    title = lesson.get("title") or module.get("title") or f"Module {module_index + 1}"
    objective = lesson.get("objective") or "Apply the module objective in a realistic situation."
    return {
        "activity_id": f"module_{module_index + 1}_scenario",
        "activity_type": "scenario_decision_tree",
        "title": f"Apply: {title}",
        "objective": objective,
        "items": [
            {
                "scenario": f"You need to apply '{title}' during real work. Which action best supports the objective?",
                "choices": [
                    {"label": "Use the lesson guidance and check the result", "result": "best"},
                    {"label": "Skip the check and move faster", "result": "risk"},
                    {"label": "Wait for someone else to decide", "result": "delay"},
                ],
            }
        ],
    }


def _normalize_scorm_payload(payload: dict) -> dict:
    normalized = _sanitize_learner_strings(_remove_h5p_markers(copy.deepcopy(payload)))
    modules = normalized.get("modules", [])
    global_seen: set[str] = set()
    for module_index, module in enumerate(modules):
        if not isinstance(module, dict):
            continue
        unique_module_activities = []
        for activity in _dedupe_activities(module.get("activities", [])):
            key = _activity_key(activity)
            if key in global_seen:
                continue
            global_seen.add(key)
            unique_module_activities.append(activity)
        if not unique_module_activities and module.get("lessons"):
            unique_module_activities.append(_fallback_module_activity(module, module_index))
        module["activities"] = unique_module_activities
        for lesson in module.get("lessons", []):
            if isinstance(lesson, dict):
                lesson["activities"] = _dedupe_activities(lesson.get("activities", []))
    assessment = normalized.get("final_assessment") or {}
    if not assessment.get("questions"):
        normalized["final_assessment"] = _fallback_assessment(normalized)
    return normalized


def _player_js() -> str:
    return r"""const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (ch) => ({
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
  "'": "&#39;"
}[ch]));

const TECHNICAL_UI_REPLACEMENTS = [
  ["SCORM course player", "Course overview"],
  ["SCORM", "course"],
  ["LMS", "learning platform"],
  ["source-aware", "course-based"],
  ["generated lessons", "lessons"],
  ["generated activities", "practice activities"],
  ["suspend/resume data", "saved progress"],
  ["suspend data", "saved progress"],
  ["course package", "course"],
  ["completion tracking", "progress tracking"],
  ["objective aligned", "Learning goal"],
  ["source aligned", "Based on course material"],
  ["expected learner decisions", "what to do in realistic situations"],
  ["LMS can capture", "Your progress saves"],
];

function learnerSafeText(value) {
  return TECHNICAL_UI_REPLACEMENTS.reduce(
    (text, pair) => text.replaceAll(pair[0], pair[1]),
    String(value ?? "")
  );
}

function flattenActivities(course) {
  return (course.modules || []).flatMap((module, moduleIndex) =>
    (module.activities || []).map((activity, activityIndex) => ({
      ...activity,
      moduleIndex,
      activityIndex,
      moduleTitle: module.title || `Module ${moduleIndex + 1}`,
    }))
  );
}

function flattenLessons(course) {
  return (course.modules || []).flatMap((module, moduleIndex) =>
    (module.lessons || []).map((lesson, lessonIndex) => ({
      ...lesson,
      moduleIndex,
      lessonIndex,
      moduleTitle: module.title || `Module ${moduleIndex + 1}`,
    }))
  );
}

function displayType(value) {
  return String(value || "interactive")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function lessonIdFor(moduleIndex, lessonIndex) {
  return `module-${moduleIndex + 1}-lesson-${lessonIndex + 1}`;
}

function findLessonById(course, lessonId) {
  for (const [moduleIndex, module] of (course.modules || []).entries()) {
    for (const [lessonIndex, lesson] of (module.lessons || []).entries()) {
      const id = lessonIdFor(moduleIndex, lessonIndex);
      if (id === lessonId) return { lesson, module, moduleIndex, lessonIndex, lessonId: id };
    }
  }
  return null;
}

function nextLessonId(course, activeLessonId) {
  const lessons = flattenLessons(course);
  const index = lessons.findIndex((lesson) => lessonIdFor(lesson.moduleIndex, lesson.lessonIndex) === activeLessonId);
  if (index < 0 || index >= lessons.length - 1) return null;
  const next = lessons[index + 1];
  return lessonIdFor(next.moduleIndex, next.lessonIndex);
}

function blockText(lesson, type) {
  return (lesson.content_blocks || []).find((block) => String(block.type || "").toLowerCase() === type)?.text || "";
}

function segmentText(value, maxLength = 360) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  if (text.length <= maxLength) return text ? [text] : [];
  const sentences = text.split(/(?<=[.!?])\s+/);
  const segments = [];
  let current = "";
  sentences.forEach((sentence) => {
    if ((current + " " + sentence).trim().length > maxLength && current) {
      segments.push(current.trim());
      current = sentence;
    } else {
      current = `${current} ${sentence}`.trim();
    }
  });
  if (current) segments.push(current.trim());
  return segments.length ? segments : [text.slice(0, maxLength)];
}

function blockTitle(type) {
  const labels = {
    explanation: "Concept",
    concept: "Concept",
    example: "Workplace example",
    scenario: "Scenario",
    intro: "Context",
    practice: "Practice",
    summary: "Takeaway",
    takeaway: "Takeaway",
    checklist: "Checklist",
    source_note: "Source note",
  };
  return labels[String(type || "").toLowerCase()] || displayType(type || "lesson block");
}

function normalizeLessonDisplay(lesson) {
  const blocks = (lesson.content_blocks || []).filter((block) => block && block.text);
  const byType = {};
  blocks.forEach((block) => {
    const key = String(block.type || "concept").toLowerCase();
    if (!byType[key]) byType[key] = block;
  });
  const objective = lesson.objective || "Complete the lesson objective.";
  const sourceBlock = blocks.find((block) => (block.source_refs || []).length);
  return {
    hook: byType.intro || { type: "intro", text: `Start with the work situation this lesson prepares you for: ${objective}` },
    concept: byType.concept || byType.explanation || { type: "concept", text: objective },
    example: byType.example || { type: "example", text: "Use one real work example and decide what a good response would look like." },
    scenario: byType.scenario || { type: "scenario", text: "Imagine this issue appears during real work. Choose the next action before continuing." },
    practice: byType.practice || { type: "practice", text: "Write the action you would take, then compare it with the course standard." },
    takeaway: byType.takeaway || byType.summary || { type: "takeaway", text: "State the safest next step in one sentence." },
    sourceRefs: sourceBlock?.source_refs || [],
  };
}

function renderTextBlock(block, label) {
  const parts = segmentText(block.text);
  return `
    <section class="lesson-block">
      <strong>${escapeHtml(label || blockTitle(block.type))}</strong>
      ${parts.map((part) => `<p>${escapeHtml(part)}</p>`).join("")}
    </section>
  `;
}

function lessonBlocks(lesson) {
  const blocks = (lesson.content_blocks || []).filter((block) => block && block.text);
  if (blocks.length) return blocks;
  return [
    { type: "explanation", text: lesson.objective || "Review the lesson objective before completing this item." },
    { type: "example", text: "Use a realistic workplace example to connect this concept to a decision." },
    { type: "scenario", text: "Place the learner in a realistic situation and ask what should happen next." },
    { type: "practice", text: "Write the action you would take, then compare it with the course standard." },
    { type: "summary", text: "Finish by stating the safest next step in one sentence." },
  ];
}

function sourceLabel(lesson) {
  const refs = (lesson.content_blocks || []).flatMap((block) => block.source_refs || []);
  if (!refs.length) return "Based on course material";
  const ref = refs[0];
  return [ref.source_id, ref.reference].filter(Boolean).join(" / ") || "Based on course material";
}

function renderLessonReader(course, state, module, moduleIndex) {
  const active = state.activeLesson ? findLessonById(course, state.activeLesson) : null;
  if (!active || active.moduleIndex !== moduleIndex) return "";
  const lesson = active.lesson;
  const display = normalizeLessonDisplay(lesson);
  const blocks = [
    [display.hook, "Context"],
    [display.concept, "Key idea"],
    [display.example, "Worked example"],
    [display.scenario, "Guided scenario"],
    [display.takeaway, "Takeaway"],
  ];
  const practice = display.practice.text || blockText(lesson, "practice") || "Write the action you would take, then compare it with the course standard.";
  const completed = (state.completedLessons || []).includes(active.lessonId);
  const nextId = nextLessonId(course, active.lessonId);
  return `
    <article class="lesson-reader" data-reader-lesson-id="${active.lessonId}">
      <div class="lesson-reader-header">
        <span class="lesson-reader-kicker">${escapeHtml(module.title || `Module ${moduleIndex + 1}`)} lesson</span>
        <h3 class="lesson-reader-title">${escapeHtml(lesson.title || "Lesson")}</h3>
        <p class="lesson-reader-objective">${escapeHtml(lesson.objective || "Complete the lesson objective.")}</p>
        <div class="lesson-reader-meta">
          <span>${lesson.duration_minutes || 8} min</span>
          <span>${escapeHtml((lesson.objective_ids || []).length ? "Learning goal" : "Learning goal")}</span>
          <span>${escapeHtml(sourceLabel(lesson))}</span>
        </div>
      </div>
      <div class="lesson-block-grid">
        <div class="lesson-block-main">
          ${blocks.map(([block, label]) => renderTextBlock(block, label)).join("")}
        </div>
        <aside class="reader-side-panel">
          <div class="lesson-practice-card">
            <strong>Try it now</strong>
            ${segmentText(practice, 220).map((part) => `<p>${escapeHtml(part)}</p>`).join("")}
          </div>
          <div class="lesson-practice-card">
            <strong>Evidence note</strong>
            <p>${escapeHtml(sourceLabel(lesson))}</p>
          </div>
        </aside>
      </div>
      <div class="lesson-reader-actions">
        <button class="complete" type="button" data-reader-action="done">${completed ? "Completed" : "Mark done"}</button>
        ${nextId ? `<button class="secondary" type="button" data-reader-action="next" data-next-lesson-id="${nextId}">Next lesson</button>` : ""}
      </div>
    </article>
  `;
}

function loadState(course) {
  let scormState = {};
  try {
    const raw = CourseScorm.getSuspendData();
    if (raw && typeof raw === "object") scormState = raw;
  } catch (_error) {}
  const fallback = localStorage.getItem(`course-state:${course.course_slug}`);
  try {
    const localState = fallback ? JSON.parse(fallback) : {};
    return { ...scormState, ...localState };
  } catch (_error) {
    return scormState;
  }
}

function getEmbeddedCourseData() {
  const node = document.getElementById("course-data");
  if (!node || !node.textContent.trim()) return null;
  try {
    return JSON.parse(node.textContent);
  } catch (_error) {
    return null;
  }
}

function saveState(course, state) {
  try { CourseScorm.setSuspendData(state); } catch (_error) {}
  localStorage.setItem(`course-state:${course.course_slug}`, JSON.stringify(state));
}

function gameDefaults(state) {
  return {
    xp: Number(state.xp || 0),
    badges: Array.isArray(state.badges) ? state.badges : [],
    completedActivities: Array.isArray(state.completedActivities) ? state.completedActivities : [],
    quizScore: Number(state.quizScore || 0),
    quizPassed: Boolean(state.quizPassed),
  };
}

function awardBadge(game, badge) {
  if (!game.badges.includes(badge)) game.badges.push(badge);
}

function awardProgress(course, state, eventType, amount, badge) {
  const game = gameDefaults(state);
  game.xp += amount;
  if (badge) awardBadge(game, badge);
  if (game.xp >= 120) awardBadge(game, "Momentum Builder");
  const nextState = { ...state, ...game };
  saveState(course, nextState);
  renderGameCard(course, nextState);
  return nextState;
}

function renderGameCard(course, state) {
  const xp = document.getElementById("game-xp");
  const level = document.getElementById("game-level");
  const badges = document.getElementById("badge-row");
  const game = gameDefaults(state);
  if (xp) xp.textContent = `${game.xp} XP`;
  if (level) level.textContent = `Level ${Math.max(1, Math.floor(game.xp / 100) + 1)}`;
  if (badges) {
    const badgeNames = ["Course Starter", "Practice Pro", "Quiz Passed", "Course Complete"];
    badges.innerHTML = badgeNames.map((name) => `<span class="badge-pill ${game.badges.includes(name) ? "earned" : ""}">${escapeHtml(name)}</span>`).join("");
  }
}

function renderModuleNav(course, state) {
  const nav = document.getElementById("module-nav");
  if (!nav) return;
  nav.innerHTML = (course.modules || []).map((module, index) => `
    <li>
      <button class="module-nav-button" type="button" data-target="module-${index + 1}">
        ${escapeHtml(module.title || `Module ${index + 1}`)}
      </button>
    </li>
  `).join("");
  nav.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => {
      const target = document.getElementById(button.dataset.target);
      if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
      CourseScorm.setLocation(button.dataset.target);
      saveState(course, { ...state, activeModule: button.dataset.target });
    });
  });
}

function renderHero(course, state) {
  const title = document.getElementById("course-title");
  const lede = document.getElementById("course-lede");
  const progress = document.getElementById("progress-value");
  const duration = document.getElementById("stat-duration");
  const modules = document.getElementById("stat-modules");
  const lessons = document.getElementById("stat-lessons");
  if (title) title.textContent = course.course_title || "Course";
  if (lede) {
    lede.textContent = learnerSafeText(`Build practical skill in ${course.course_title || "this topic"} through ${course.modules.length} modules, ${flattenLessons(course).length} short lessons, practice activities, and a final check.`);
  }
  if (progress) progress.textContent = "0%";
  renderGameCard(course, state || {});
  if (duration) {
    const minutes = (course.modules || []).reduce((total, module) => total + Number(module.duration_minutes || 0), 0)
      || flattenLessons(course).reduce((total, lesson) => total + Number(lesson.duration_minutes || 0), 0);
    duration.textContent = minutes || "Short";
  }
  if (modules) modules.textContent = String((course.modules || []).length);
  if (lessons) lessons.textContent = String(flattenLessons(course).length);
}

function openLesson(course, state, lessonId) {
  const nextState = { ...state, activeLesson: lessonId };
  CourseScorm.setLocation(lessonId);
  saveState(course, nextState);
  renderCoursePlayer(course, nextState);
  const active = document.querySelector(`[data-reader-lesson-id="${lessonId}"]`) || document.querySelector(`[data-lesson-id="${lessonId}"]`);
  if (active) active.scrollIntoView({ behavior: "smooth", block: "start" });
}

function bindIntroControls(course, state) {
  const start = document.getElementById("start-course");
  const outline = document.getElementById("view-outline");
  if (start) {
    start.textContent = state.activeLesson ? "Continue learning" : "Start course";
    start.onclick = () => {
      const first = flattenLessons(course)[0];
      const lessonId = state.activeLesson || (first ? lessonIdFor(first.moduleIndex, first.lessonIndex) : null);
      if (lessonId) openLesson(course, state, lessonId);
    };
  }
  if (outline) {
    outline.onclick = () => {
      const deck = document.getElementById("lesson-deck");
      if (deck) deck.scrollIntoView({ behavior: "smooth", block: "start" });
    };
  }
}

function renderLessonCards(course, state, module, moduleIndex) {
  return `
    <div class="lesson-grid">
      ${(module.lessons || []).map((lesson, lessonIndex) => {
        const lessonId = lessonIdFor(moduleIndex, lessonIndex);
        const completed = (state.completedLessons || []).includes(lessonId);
        const current = state.activeLesson === lessonId;
        return `
          <article class="lesson-card ${completed ? "completed" : ""} ${current ? "active" : ""}" data-lesson-id="${lessonId}">
            <h3>${escapeHtml(lesson.title || `Lesson ${lessonIndex + 1}`)}</h3>
            <p>${escapeHtml(lesson.objective || "Complete the lesson objective.")}</p>
            <div class="lesson-meta">
              <span>${lesson.duration_minutes || 8} min</span>
              <span>${escapeHtml((lesson.objective_ids || []).length ? "Learning goal" : "Learning goal")}</span>
            </div>
            <div class="lesson-actions">
              <button class="primary" type="button" data-action="open">${current ? "Close" : "Open"}</button>
              <button class="secondary" type="button" data-action="done">${completed ? "Completed" : "Mark done"}</button>
            </div>
          </article>`;
      }).join("")}
    </div>
  `;
}

function renderModuleSection(course, state, module, moduleIndex) {
  return `
    <section class="course-panel" id="module-${moduleIndex + 1}">
      <div class="course-panel-header">
        <div>
          <h2 class="course-panel-title">${escapeHtml(module.title || `Module ${moduleIndex + 1}`)}</h2>
          <p class="course-panel-subtitle">${escapeHtml(`Module ${moduleIndex + 1} of ${course.modules.length}`)}</p>
        </div>
        <span class="lesson-meta">${(module.lessons || []).length} lessons</span>
      </div>
      ${renderLessonCards(course, state, module, moduleIndex)}
      ${renderLessonReader(course, state, module, moduleIndex)}
    </section>
  `;
}

function markLessonDone(course, state, lessonId) {
  const completedLessons = new Set(state.completedLessons || []);
  const wasNew = !completedLessons.has(lessonId);
  completedLessons.add(lessonId);
  const nextState = { ...state, activeLesson: lessonId, completedLessons: Array.from(completedLessons) };
  const awardedState = wasNew ? awardProgress(course, nextState, "lesson", 25, "Course Starter") : nextState;
  saveState(course, awardedState);
  CourseScorm.setLocation(lessonId);
  renderCoursePlayer(course, awardedState);
}

function markActivityComplete(course, state, activityId, points = 35) {
  const game = gameDefaults(state);
  if (!game.completedActivities.includes(activityId)) {
    game.completedActivities.push(activityId);
    game.xp += points;
    awardBadge(game, "Practice Pro");
    if (game.xp >= 120) awardBadge(game, "Momentum Builder");
  }
  const nextState = { ...state, ...game };
  saveState(course, nextState);
  renderGameCard(course, nextState);
  return nextState;
}

function renderLessonDeck(course, state) {
  const deck = document.getElementById("lesson-deck");
  if (!deck) return;
  const lessons = flattenLessons(course);
  deck.innerHTML = (course.modules || []).map((module, moduleIndex) => renderModuleSection(course, state, module, moduleIndex)).join("");

  deck.querySelectorAll("[data-lesson-id]").forEach((card) => {
    const lessonId = card.dataset.lessonId;
    const open = card.querySelector('[data-action="open"]');
    const done = card.querySelector('[data-action="done"]');
    if (open) {
      open.addEventListener("click", () => {
        const nextActiveLesson = state.activeLesson === lessonId ? null : lessonId;
        if (nextActiveLesson) {
          openLesson(course, state, nextActiveLesson);
        } else {
          const nextState = { ...state, activeLesson: null };
          CourseScorm.setLocation(lessonId);
          saveState(course, nextState);
          renderCoursePlayer(course, nextState);
        }
      });
    }
    if (done) {
      done.addEventListener("click", () => markLessonDone(course, state, lessonId));
    }
  });

  deck.querySelectorAll("[data-reader-action]").forEach((button) => {
    button.addEventListener("click", () => {
      const reader = button.closest("[data-reader-lesson-id]");
      const lessonId = reader?.dataset.readerLessonId;
      if (button.dataset.readerAction === "done" && lessonId) {
        markLessonDone(course, state, lessonId);
      }
      if (button.dataset.readerAction === "next" && button.dataset.nextLessonId) {
        const nextState = { ...state, activeLesson: button.dataset.nextLessonId };
        saveState(course, nextState);
        CourseScorm.setLocation(button.dataset.nextLessonId);
        renderCoursePlayer(course, nextState);
      }
    });
  });

  const completedCount = (state.completedLessons || []).length;
  const percent = lessons.length ? Math.round((completedCount / lessons.length) * 100) : 0;
  const progress = document.getElementById("progress-value");
  if (progress) progress.textContent = `${percent}%`;
}

function renderNativeActivity(activity, course, index, state) {
  const card = document.createElement("article");
  const activityId = activity.activity_id || `activity-${index}`;
  const completedActivity = gameDefaults(state).completedActivities.includes(activityId);
  card.className = `activity-card ${completedActivity ? "completed" : ""}`;
  const type = String(activity.activity_type || activity.type || "").toLowerCase();
  const items = activity.items || activity.cards || activity.steps || [];
  card.innerHTML = `
    <div class="activity-type">${escapeHtml(displayType(activity.activity_type || activity.type || "interactive"))}</div>
    <span class="activity-status">${completedActivity ? "Completed" : "+35 XP"}</span>
    <h3>${escapeHtml(activity.title || `Activity ${index + 1}`)}</h3>
    <p>${escapeHtml(activity.objective || activity.instructions || "Complete the interactive practice item.")}</p>
    <div class="activity-body"></div>
    <div class="activity-feedback" role="status"></div>
  `;
  const body = card.querySelector(".activity-body");
  const feedback = card.querySelector(".activity-feedback");
  if (type.includes("flashcard")) {
    const cards = items.length ? items : [
      { front: activity.objective || "Key idea", back: activity.instructions || "Explain it in your own words." },
    ];
    body.innerHTML = `<div class="flashcard-grid">
      ${cards.map((item, itemIndex) => `
        <button type="button" class="flashcard" data-card="${itemIndex}">
          <strong>${escapeHtml(item.front || item.term || item.prompt || `Card ${itemIndex + 1}`)}</strong>
          <span class="flashcard-back">${escapeHtml(item.back || item.definition || item.answer || "Review the course explanation.")}</span>
        </button>
      `).join("")}
    </div>`;
    body.querySelectorAll(".flashcard").forEach((button) => {
      button.addEventListener("click", () => {
        button.classList.toggle("is-flipped");
        feedback.textContent = "Flashcard flipped. Say the answer before revealing it.";
        card.classList.add("completed");
        card.querySelector(".activity-status").textContent = "Completed";
        state = markActivityComplete(course, state, activityId, 20);
        CourseScorm.recordInteraction?.(`activity-${index}`, "flashcard", button.textContent, "neutral", activity.title || "Flashcard");
      });
    });
  } else if (type.includes("accordion") || type.includes("tabs")) {
    const rows = items.length ? items : [
      { title: activity.objective || "Review point", detail: activity.instructions || "Open each item and connect it to the lesson." },
    ];
    body.innerHTML = `<div class="accordion-list">
      ${rows.map((item, itemIndex) => `
        <div class="accordion-item" data-accordion="${itemIndex}">
          <button type="button">${escapeHtml(item.title || item.label || item.front || `Item ${itemIndex + 1}`)}</button>
          <div class="accordion-panel">${escapeHtml(item.detail || item.text || item.back || "Review this point before continuing.")}</div>
        </div>
      `).join("")}
    </div>`;
    body.querySelectorAll(".accordion-item button").forEach((button) => {
      button.addEventListener("click", () => {
        const item = button.closest(".accordion-item");
        item.classList.toggle("is-open");
        feedback.textContent = "Section opened. Compare the detail with the lesson objective.";
        card.classList.add("completed");
        card.querySelector(".activity-status").textContent = "Completed";
        state = markActivityComplete(course, state, activityId, 20);
        CourseScorm.recordInteraction?.(`activity-${index}`, "accordion", button.textContent, "neutral", activity.title || "Accordion");
      });
    });
  } else if (type.includes("timeline")) {
    const rows = items.length ? items : [
      { label: "Learn", detail: "Read the core idea." },
      { label: "Practice", detail: "Apply it in a scenario." },
      { label: "Prove", detail: "Answer the assessment item." },
    ];
    body.innerHTML = `<div class="timeline-list">
      ${rows.map((item, itemIndex) => `
        <div class="timeline-item">
          <strong>${escapeHtml(item.label || item.title || `Step ${item.step || itemIndex + 1}`)}</strong>
          <span>${escapeHtml(item.detail || item.text || item.description || "Complete this step.")}</span>
        </div>
      `).join("")}
    </div>`;
    feedback.textContent = "Timeline ready. Move through the steps in order.";
  } else if (type.includes("roleplay") || type.includes("role-play")) {
    const persona = activity.persona || {};
    const roleName = persona.name || activity.persona_name || activity.role || "Scenario stakeholder";
    const roleTitle = persona.role || activity.persona_role || activity.counterpart_role || "Stakeholder";
    const goals = persona.goals || activity.goals || activity.objective || "Get a clear, safe, and useful response from the learner.";
    const constraints = persona.constraints || activity.constraints || "Push back when the learner is vague or skips the process.";
    const scenario = activity.situation || activity.scenario || activity.setup || "Practice the conversation using the lesson standard.";
    const objectives = activity.objectives || activity.expected_behaviors || [
      activity.objective || "Clarify the situation before acting.",
      "Use the documented process.",
      "Communicate the next step clearly.",
    ];
    const rubric = activity.rubric || objectives.map((objective, rubricIndex) => ({
      criterion: objective,
      points: rubricIndex === 0 ? 40 : 30,
    }));
    body.innerHTML = `
      <div class="roleplay-grid">
        <div class="roleplay-persona">
          <strong>${escapeHtml(roleName)} · ${escapeHtml(roleTitle)}</strong>
          <p>${escapeHtml(scenario)}</p>
          <p><b>Goal:</b> ${escapeHtml(goals)}</p>
          <p><b>Constraint:</b> ${escapeHtml(constraints)}</p>
        </div>
        <div class="roleplay-rubric">
          <strong>Success rubric</strong>
          <ul>
            ${rubric.map((item) => `<li>${escapeHtml(item.criterion || item.objective || item)} (${escapeHtml(item.points || item.weight || 1)} pts)</li>`).join("")}
          </ul>
        </div>
      </div>
      <label class="roleplay-response">
        <strong>Your response</strong>
        <span>${escapeHtml(objectives.join(" "))}</span>
        <textarea placeholder="Write what you would say or do in this role-play"></textarea>
      </label>
      <button type="button" class="primary">Score response</button>
    `;
    body.querySelector("button").addEventListener("click", () => {
      const response = body.querySelector("textarea").value.trim();
      const lower = response.toLowerCase();
      const hits = objectives.filter((objective) => {
        const terms = String(objective).toLowerCase().split(/\W+/).filter((term) => term.length > 5);
        return terms.some((term) => lower.includes(term));
      }).length;
      const score = objectives.length ? Math.max(25, Math.round((hits / objectives.length) * 100)) : 50;
      feedback.textContent = response
        ? `Debrief score: ${score}%. Check your answer against the rubric before continuing.`
        : "Write a response first, then score it against the rubric.";
      if (response) {
        card.classList.add("completed");
        card.querySelector(".activity-status").textContent = "Completed";
        state = markActivityComplete(course, state, activityId, 45);
      }
      CourseScorm.recordInteraction?.(`activity-${index}`, "roleplay", response, score >= 70 ? "correct" : "neutral", activity.title || "Role-play");
    });
  } else if (type.includes("fill")) {
    const prompt = activity.prompt || activity.objective || "Complete the missing term.";
    const answer = String(activity.answer || activity.correct_answer || activity.correct || "").trim().toLowerCase();
    body.innerHTML = `
      <div class="fill-blank-row">
        <label>${escapeHtml(prompt)}<input type="text" autocomplete="off"></label>
        <button type="button" class="primary">Check answer</button>
      </div>
    `;
    body.querySelector("button").addEventListener("click", () => {
      const value = body.querySelector("input").value.trim().toLowerCase();
      const correct = answer ? value === answer : value.length > 2;
      feedback.textContent = correct ? "Accepted. Continue to the next item." : "Not yet. Recheck the lesson wording and try again.";
      if (correct) {
        card.classList.add("completed");
        card.querySelector(".activity-status").textContent = "Completed";
        state = markActivityComplete(course, state, activityId, 35);
      }
      CourseScorm.recordInteraction?.(`activity-${index}`, "fill-in", value, correct ? "correct" : "wrong", activity.title || "Fill in the blank");
    });
  } else if (type.includes("matching")) {
    body.innerHTML = (items || []).map((item, itemIndex) => `
      <div class="match-row" data-item="${itemIndex}">
        <span>${escapeHtml(item.left || item.front || item.prompt || `Item ${itemIndex + 1}`)}</span>
        <button type="button" class="secondary">Reveal</button>
        <span class="match-result"></span>
      </div>
    `).join("");
    body.querySelectorAll(".match-row button").forEach((button) => {
      button.addEventListener("click", () => {
        const row = button.closest(".match-row");
        const result = row.querySelector(".match-result");
        const itemIndex = Number(row.dataset.item);
        const item = items?.[itemIndex] || {};
        result.textContent = item.right || item.back || item.match || "Matched";
        button.textContent = "Revealed";
        feedback.textContent = "Match revealed. Compare the pair before moving on.";
        card.classList.add("completed");
        card.querySelector(".activity-status").textContent = "Completed";
        state = markActivityComplete(course, state, activityId, 30);
        CourseScorm.recordInteraction?.(`activity-${index}`, "matching", item.left || item.front || item.prompt || "", "correct", activity.title || "Matching");
      });
    });
  } else if (type.includes("scenario") || type.includes("decision")) {
    const scenarioItem = items.find((item) => item && (item.choices || item.options)) || {};
    const choices = activity.choices || activity.options || scenarioItem.choices || scenarioItem.options || ["Choose the safest action", "Choose the fastest action", "Skip the check"];
    body.innerHTML = `
      <p class="scenario-prompt">${escapeHtml(scenarioItem.scenario || activity.scenario || "Choose the best response for this workplace situation.")}</p>
      <div class="scenario-options">
        ${choices.map((choice, choiceIndex) => `<button type="button" class="primary" data-choice="${choiceIndex}">${escapeHtml(choice.label || choice.text || choice)}</button>`).join("")}
      </div>
      <div class="scenario-consequence" hidden></div>
    `;
    body.querySelectorAll("button").forEach((button) => {
      button.addEventListener("click", () => {
        body.querySelectorAll("button").forEach((item) => item.classList.remove("is-selected"));
        button.classList.add("is-selected");
        const choice = choices[Number(button.dataset.choice)] || {};
        const result = choice.feedback || choice.consequence || choice.result || "Compare this decision with the lesson standard before continuing.";
        const consequence = body.querySelector(".scenario-consequence");
        consequence.hidden = false;
        consequence.textContent = result;
        feedback.textContent = `Decision saved: ${button.textContent}.`;
        card.classList.add("completed");
        card.querySelector(".activity-status").textContent = "Completed";
        state = markActivityComplete(course, state, activityId, 35);
        CourseScorm.recordInteraction?.(`activity-${index}`, "choice", button.textContent, choice.result === "risk" ? "wrong" : "neutral", activity.title || "Scenario");
      });
    });
  } else if (type.includes("reflection")) {
    body.innerHTML = `
      <label class="reflection-box">
        <span>Your reflection</span>
        <textarea rows="4" placeholder="Write your answer here"></textarea>
      </label>
      <button type="button" class="primary">Save reflection</button>
    `;
    body.querySelector("button").addEventListener("click", () => {
      feedback.textContent = "Reflection saved in this session.";
      card.classList.add("completed");
      card.querySelector(".activity-status").textContent = "Completed";
      state = markActivityComplete(course, state, activityId, 25);
      CourseScorm.setSuspendData({ ...state, [`reflection-${index}`]: body.querySelector("textarea").value });
    });
  } else {
    body.innerHTML = `
      <label class="reflection-box">
        <span>Action commitment</span>
        <textarea rows="3" placeholder="Write the action you would take after this lesson"></textarea>
      </label>
      <button type="button" class="primary">Save action</button>
    `;
    body.querySelector("button").addEventListener("click", () => {
      feedback.textContent = "Action saved. Use it as your next workplace practice step.";
      card.classList.add("completed");
      card.querySelector(".activity-status").textContent = "Completed";
      state = markActivityComplete(course, state, activityId, 25);
      CourseScorm.setSuspendData({ ...state, [`activity-action-${index}`]: body.querySelector("textarea").value });
    });
  }
  return card;
}

function renderActivityDeck(course, state) {
  const deck = document.getElementById("activity-deck");
  if (!deck) return;
  const activities = flattenActivities(course);
  deck.innerHTML = "";
  const shell = document.createElement("div");
  shell.className = "activity-shell";
  activities.forEach((activity, index) => {
    shell.appendChild(renderNativeActivity(activity, course, index, state));
  });
  if (!activities.length) {
    shell.innerHTML = "<p>No interactive activities were generated for this course.</p>";
  }
  deck.appendChild(shell);
}

function renderAssessmentOrEmptyState(course) {
  const deck = document.getElementById("assessment-deck");
  if (!deck) return;
  const questions = course.final_assessment?.questions || [];
  if (!questions.length) {
    deck.innerHTML = "";
    return;
  }
  const stored = loadState(course);
  if (stored.quizSubmitted) {
    renderQuizResult(course, deck, stored);
    return;
  }
  const activeQuestion = Number(stored.activeQuestion || 0);
  deck.innerHTML = `
    <div class="course-panel">
      <div class="course-panel-header">
        <div>
          <h2 class="course-panel-title">${escapeHtml(course.final_assessment?.title || "Final Check")}</h2>
          <p class="course-panel-subtitle">Check your understanding before completing the course.</p>
        </div>
      </div>
      <form id="quiz-form">
        ${questions.map((question, index) => `
          <fieldset class="quiz-question-card ${index === activeQuestion ? "" : "is-hidden"}" data-question-index="${index}">
            <div class="quiz-progress-text">Question ${index + 1} of ${questions.length}</div>
            <legend>${escapeHtml(question.question || "Question")}</legend>
            ${(question.options || []).map((option, optionIndex) => `
              <label>
                <input type="radio" name="q${index}" value="${escapeHtml(option)}">
                ${escapeHtml(option)}
              </label>
            `).join("")}
          </fieldset>
        `).join("")}
      </form>
      <div class="assessment-nav">
        <button class="secondary" type="button" id="quiz-prev" ${activeQuestion <= 0 ? "disabled" : ""}>Previous</button>
        <button class="secondary" type="button" id="quiz-next" ${activeQuestion >= questions.length - 1 ? "disabled" : ""}>Next question</button>
      </div>
      <div class="assessment-actions">
        <button class="primary" type="button" id="quiz-submit">Submit final check</button>
        <p id="quiz-feedback" class="feedback" role="status"></p>
      </div>
    </div>
  `;
  deck.querySelectorAll("fieldset label").forEach((label) => {
    label.addEventListener("click", () => {
      label.closest("fieldset").querySelectorAll("label").forEach((item) => item.classList.remove("is-selected"));
      label.classList.add("is-selected");
    });
  });
  const submit = deck.querySelector("#quiz-submit");
  const feedback = deck.querySelector("#quiz-feedback");
  const setQuestion = (nextIndex) => {
    const safeIndex = Math.max(0, Math.min(questions.length - 1, nextIndex));
    const nextState = { ...loadState(course), activeQuestion: safeIndex };
    saveState(course, nextState);
    renderAssessmentOrEmptyState(course);
  };
  deck.querySelector("#quiz-prev")?.addEventListener("click", () => setQuestion(activeQuestion - 1));
  deck.querySelector("#quiz-next")?.addEventListener("click", () => setQuestion(activeQuestion + 1));
  if (!submit) return;
  submit.addEventListener("click", () => {
    const form = deck.querySelector("#quiz-form");
    let score = 0;
    questions.forEach((question, index) => {
      const selected = form.querySelector(`input[name="q${index}"]:checked`);
      if (selected && (question.correct_answers || []).includes(selected.value)) score += 1;
      CourseScorm.recordInteraction?.(`quiz-${index}`, question.type || "mcq", selected ? selected.value : "", selected && (question.correct_answers || []).includes(selected.value) ? "correct" : "wrong", question.question || "");
    });
    const percent = questions.length ? Math.round((score / questions.length) * 100) : 0;
    const game = gameDefaults(loadState(course));
    game.quizScore = percent;
    game.quizPassed = percent >= 80;
    game.quizSubmitted = true;
    game.xp += score * 20;
    if (game.quizPassed) awardBadge(game, "Quiz Passed");
    const nextState = { ...loadState(course), ...game };
    saveState(course, nextState);
    CourseScorm.setScore(percent);
    if (percent >= 80) CourseScorm.markComplete();
    feedback.textContent = `Score: ${score}/${questions.length} (${percent}%).`;
    renderGameCard(course, nextState);
    renderQuizResult(course, deck, nextState);
  });
}

function renderQuizResult(course, deck, state) {
  const score = Number(state.quizScore || 0);
  const passed = score >= 80;
  deck.innerHTML = `
    <div class="quiz-result-card">
      <p class="eyebrow">${passed ? "Final check passed" : "Review and try again"}</p>
      <h2>${passed ? "You passed the final check" : "You can improve this score"}</h2>
      <div class="quiz-score">${score}%</div>
      <p>${passed ? "Your completion is ready. Review your badges or finish the course." : "Review the lesson cards, then retry the final check."}</p>
      <div class="hero-actions">
        <button class="secondary" type="button" id="quiz-retry">Try again</button>
        ${passed ? '<button class="complete" type="button" id="show-completion">Complete course</button>' : ""}
      </div>
    </div>
  `;
  const retry = deck.querySelector("#quiz-retry");
  if (retry) {
    retry.addEventListener("click", () => {
      const nextState = { ...state, quizSubmitted: false };
      saveState(course, nextState);
      renderAssessmentOrEmptyState(course);
    });
  }
  const completion = deck.querySelector("#show-completion");
  if (completion) {
    completion.addEventListener("click", () => renderCompletionScreen(course, state));
  }
}

function renderCompletionScreen(course, state) {
  const deck = document.getElementById("assessment-deck");
  if (!deck) return;
  const lessons = flattenLessons(course);
  const completed = (state.completedLessons || []).length;
  const game = gameDefaults(state);
  awardBadge(game, "Course Complete");
  const nextState = { ...state, ...game, courseCompleted: true };
  saveState(course, nextState);
  CourseScorm.markComplete();
  renderGameCard(course, nextState);
  deck.innerHTML = `
    <section class="completion-screen">
      <p class="eyebrow">Course complete</p>
      <h2>${escapeHtml(course.course_title || "Course")}</h2>
      <div class="completion-score">${Number(nextState.quizScore || 0)}%</div>
      <div class="completion-grid">
        <div><strong>${completed}/${lessons.length}</strong><span>Lessons complete</span></div>
        <div><strong>${nextState.xp}</strong><span>XP earned</span></div>
        <div><strong>Ready</strong><span>Certificate status</span></div>
      </div>
      <p>Your completion is saved. You can close this course or review any lesson again.</p>
      <button class="secondary" type="button" id="return-outline">Return to course outline</button>
    </section>
  `;
  deck.querySelector("#return-outline").addEventListener("click", () => {
    document.getElementById("lesson-deck")?.scrollIntoView({ behavior: "smooth", block: "start" });
  });
}

function renderModulePage(course) {
  const moduleIndex = Math.max(0, Number(document.body.dataset.modulePage || "1") - 1);
  const module = course.modules[moduleIndex] || course.modules[0];
  const deck = document.getElementById("module-activity-deck");
  if (!deck || !module) return;
  const activities = module.activities || [];
  deck.innerHTML = `
    <div class="course-panel">
      <div class="course-panel-header">
        <div>
          <h2 class="course-panel-title">${escapeHtml(module.title || `Module ${moduleIndex + 1}`)}</h2>
          <p class="course-panel-subtitle">${activities.length} module activities</p>
        </div>
        <a class="primary" href="index.html" style="text-decoration:none; display:inline-flex; align-items:center;">Back to course</a>
      </div>
      <div class="activity-shell">
        ${activities.map((activity, index) => `
          <article class="activity-card">
            <div class="activity-type">${escapeHtml(activity.activity_type || activity.type || "interactive")}</div>
            <h3>${escapeHtml(activity.title || `Activity ${index + 1}`)}</h3>
            <p>${escapeHtml(activity.objective || activity.instructions || "Complete the module activity.")}</p>
          </article>
        `).join("")}
      </div>
    </div>
  `;
}

function renderCoursePlayer(course, providedState) {
  const state = providedState || loadState(course);
  renderHero(course, state);
  renderModuleNav(course, state);
  renderLessonDeck(course, state);
  bindIntroControls(course, state);
  renderActivityDeck(course, state);
  renderAssessmentOrEmptyState(course);
  if (state.activeLesson) {
    const active = document.querySelector(`[data-lesson-id="${state.activeLesson}"]`);
    if (active) active.classList.add("active");
  }
}

async function bootCoursePlayer() {
  const root = document.querySelector("[data-course-player], [data-module-page]");
  if (!root) return;
  let course = getEmbeddedCourseData();
  if (!course) {
    const response = await fetch("data/course.json");
    course = await response.json();
  }
  document.body.dataset.theme = course.theme || "studio";
  if (document.body.dataset.coursePlayer !== undefined) {
    renderCoursePlayer(course);
    return;
  }
  if (document.body.dataset.modulePage) {
    renderModulePage(course);
  }
}

bootCoursePlayer();
"""


def _runtime_js() -> str:
    runtime_path = Path(__file__).with_name("scorm_runtime_v2.js")
    return runtime_path.read_text(encoding="utf-8")


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
            runtime = package.read("assets/scorm_api.js").decode("utf-8") if "assets/scorm_api.js" in names else ""
            if runtime and "recordInteraction" not in runtime:
                errors.append("SCORM runtime does not record interactions.")
            if runtime and "cmi.core.lesson_status" not in runtime:
                errors.append("SCORM runtime does not set SCORM 1.2 completion status.")
            if runtime and "cmi.success_status" not in runtime:
                errors.append("SCORM runtime does not set SCORM 2004 success status.")
    except Exception:
        errors.append("Package is not a readable zip archive.")

    return {"valid": not errors, "errors": errors}


def build_scorm_package(req: ScormPackageRequest, output_dir: str) -> dict:
    root = Path(output_dir).resolve()
    base = root / req.course_slug
    _ensure_inside(root, base)
    base.mkdir(parents=True, exist_ok=True)
    assets = base / "assets"
    assets.mkdir(exist_ok=True)
    data_dir = base / "data"
    data_dir.mkdir(exist_ok=True)
    module_files = [_module_page_name(i) for i, _module in enumerate(req.modules, start=1)]
    course_payload = _normalize_scorm_payload(_course_payload(req))
    course_payload["theme"] = _theme_for_course(req.course_title, " ".join(str(module.get("title", "")) for module in req.modules))
    course_payload_json = json.dumps(course_payload, indent=2).replace("</", "<\\/")
    video_dir = base / "interactive-video"
    video_dir.mkdir(exist_ok=True)
    asset_files = [
        "assets/styles.css",
        "assets/course.js",
        "assets/player.js",
        "assets/gamification_engine.js",
        "assets/sentientia_video_engine.js",
        "assets/sentientia_video_engine.css",
        "assets/scorm_api.js",
        "assets/study-map.svg",
        "assets/prompt-lab.svg",
    ]
    data_files = ["data/course.json"]
    video_files = [
        "interactive-video/index.html",
        "interactive-video/video_project.json",
        "interactive-video/sentientia_video_engine.js",
        "interactive-video/sentientia_video_engine.css",
    ]
    files = ["imsmanifest.xml", "index.html", *module_files, *asset_files, *video_files, *data_files]

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
{chr(10).join(f'      <file href="{escape(file_name)}" />' for file_name in video_files)}
{chr(10).join(f'      <file href="{escape(file_name)}" />' for file_name in data_files)}
    </resource>
  </resources>
</manifest>
'''
    navigation = "\n".join(
        f'<li><a href="{escape(file_name)}">{escape(module.get("title", f"Module {i}"))}</a></li>'
        for i, (file_name, module) in enumerate(zip(module_files, req.modules, strict=True), start=1)
    )
    first_video = next((_safe_video_url(module) for module in req.modules if _safe_video_url(module)), None)
    has_video = first_video is not None
    safe_course_title = _learner_safe_text(req.course_title)
    total_duration = sum(int(module.get("duration_minutes", 0) or 0) for module in req.modules)
    if not total_duration:
        total_duration = sum(
            int(lesson.get("duration_minutes", 0) or 0)
            for module in req.modules
            for lesson in module.get("lessons", [])
            if isinstance(lesson, dict)
        )
    total_lessons = sum(len(module.get("lessons", [])) for module in req.modules)
    intro_module_class = "module" if has_video else "module module-full"
    video_block = (
        f'''<div class="video-card">
        <iframe src="{escape(first_video)}" title="{escape(req.course_title)} video" allowfullscreen></iframe>
      </div>'''
        if first_video
        else ""
    )
    index = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(safe_course_title)}</title>
  <link rel="icon" href="data:,">
  <link rel="stylesheet" href="assets/styles.css">
  <script src="assets/scorm_api.js"></script>
</head>
<body data-course-player data-theme="{escape(course_payload["theme"])}">
  <script id="course-data" type="application/json">{course_payload_json}</script>
  <div class="course-shell">
    <aside class="course-sidebar">
      <p class="eyebrow">Course overview</p>
      <h1 id="course-title">{escape(safe_course_title)}</h1>
      <div class="progress-ring" aria-label="Your progress"><span id="progress-value">0%</span></div>
      <div class="game-card" aria-label="Points and badges">
        <span id="game-level">Level 1</span>
        <strong id="game-xp">0 XP</strong>
        <div class="badge-row" id="badge-row"></div>
      </div>
      <ul class="module-nav" id="module-nav">{navigation}</ul>
    </aside>
    <div class="lesson-workspace">
      <header class="hero">
        <div id="hero-copy">
          <p class="eyebrow">Your learning path</p>
          <h1>{escape(safe_course_title)}</h1>
          <p class="lede" id="course-lede">Build practical skill in {escape(safe_course_title)} through short lessons, examples, practice activities, and a final check.</p>
          <div class="course-stats" aria-label="Course summary">
            <div><strong id="stat-duration">{total_duration or "Short"}</strong><span>Minutes</span></div>
            <div><strong id="stat-modules">{len(req.modules)}</strong><span>Modules</span></div>
            <div><strong id="stat-lessons">{total_lessons}</strong><span>Lessons</span></div>
          </div>
          <div class="hero-actions">
            <button class="primary" type="button" id="start-course">Start course</button>
            <button class="secondary" type="button" id="view-outline">View outline</button>
          </div>
        </div>
        <img src="assets/study-map.svg" alt="Course study map">
      </header>
      <main>
        <section class="{intro_module_class}">
          <div class="module-text">
            <h2>How to use this course</h2>
            <p>Move through each lesson, save progress, complete the practice activities, and submit the final check. Your progress is saved as you move through the course.</p>
            <div id="lesson-deck" class="course-panel"></div>
          </div>
          {video_block}
        </section>
        <section class="module alt">
          <img src="assets/prompt-lab.svg" alt="Interactive prompt lab">
          <div class="module-text">
            <h2>Practice method</h2>
            <p>Each generated course should combine explanation, example, learner practice, scenario feedback, and assessment evidence.</p>
            <div class="method-grid">
              <div><span>Learn</span><p>Read the module objective.</p></div>
              <div><span>Practice</span><p>Try an interactive activity.</p></div>
              <div><span>Prove</span><p>Submit the quiz and mark complete.</p></div>
            </div>
          </div>
        </section>
        <section class="interactive">
          <h2>Interactive practice</h2>
          <p>Activities are rendered directly inside the SCORM player so learners do not need a separate activity runtime.</p>
          <div id="activity-deck"></div>
        </section>
        <section class="interactive">
          <h2>Interactive video</h2>
          <p>The interactive video project and runtime assets are packaged inside this SCORM file.</p>
          <p><a class="primary" href="interactive-video/index.html">Open interactive video</a></p>
        </section>
        <section class="interactive">
          <h2>Interactive 2: Prompt builder</h2>
          <p>Fill the boxes, then generate a stronger learning prompt.</p>
          <div class="prompt-builder">
            <label>Topic <input id="topic" value="{escape(req.course_title)}"></label>
            <label>Level <input id="level" value="beginner"></label>
            <label>Task <input id="task" value="explain simply with examples"></label>
          </div>
          <button class="primary" type="button" id="prompt-build">Build prompt</button>
          <div id="prompt-output" class="prompt-output"></div>
        </section>
        <section class="quiz" id="assessment-deck"></section>
      </main>
      <footer>
        <button class="complete" type="button" id="course-complete">Mark course complete</button>
        <p>Generated by Samrat Course MCP.</p>
      </footer>
    </div>
  </div>
  <script src="assets/course.js"></script>
  <script src="assets/player.js"></script>
</body>
</html>
"""

    (base / "imsmanifest.xml").write_text(manifest, encoding="utf-8")
    (base / "index.html").write_text(index, encoding="utf-8")
    (assets / "styles.css").write_text(_styles_css(), encoding="utf-8")
    (assets / "course.js").write_text(_course_js(), encoding="utf-8")
    (assets / "player.js").write_text(_player_js(), encoding="utf-8")
    static_dir = Path(__file__).with_name("static")
    for asset_name in ("gamification_engine.js", "sentientia_video_engine.js", "sentientia_video_engine.css"):
        source = static_dir / asset_name
        if source.exists():
            (assets / asset_name).write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    (assets / "scorm_api.js").write_text(_runtime_js(), encoding="utf-8")
    (assets / "study-map.svg").write_text(_study_map_svg(), encoding="utf-8")
    (assets / "prompt-lab.svg").write_text(_prompt_lab_svg(), encoding="utf-8")
    video_project = build_video_project_from_course(course_payload)
    video_project_payload = video_project.model_dump(mode="json")
    video_project_json = json.dumps(video_project_payload, indent=2)
    video_project_attribute = escape(json.dumps(video_project_payload), quote=True)
    (video_dir / "video_project.json").write_text(video_project_json, encoding="utf-8")
    for asset_name in ("sentientia_video_engine.js", "sentientia_video_engine.css"):
        source = static_dir / asset_name
        if source.exists():
            (video_dir / asset_name).write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    (video_dir / "index.html").write_text(
        f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(req.course_title)} Interactive Video</title>
  <link rel="icon" href="data:,">
  <link rel="stylesheet" href="sentientia_video_engine.css">
  <script src="../assets/scorm_api.js"></script>
</head>
<body>
  <main class="sv-shell" data-video-project="{video_project_attribute}">
    <section class="sv-player aspect-16-9" aria-label="Interactive training video">
      <div class="sv-stage" id="sv-stage"></div>
      <div class="sv-caption" id="sv-caption" aria-live="polite"></div>
      <div class="sv-controls">
        <button id="sv-play" type="button">Play</button>
        <button id="sv-pause" type="button">Pause</button>
        <button id="sv-prev" type="button">Back</button>
        <button id="sv-next" type="button">Next</button>
        <progress id="sv-progress" max="100" value="0" aria-label="Video progress"></progress>
      </div>
    </section>
    <aside class="sv-transcript">
      <h2>Transcript</h2>
      <pre>{escape(video_project.transcript or "")}</pre>
    </aside>
  </main>
  <script src="sentientia_video_engine.js"></script>
</body>
</html>
""",
        encoding="utf-8",
    )
    (data_dir / "course.json").write_text(json.dumps(course_payload, indent=2), encoding="utf-8")
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
  <link rel="icon" href="data:,">
  <link rel="stylesheet" href="assets/styles.css">
  <script src="assets/scorm_api.js"></script>
</head>
<body data-module-page="{i}" data-theme="{escape(course_payload["theme"])}">
  <script id="course-data" type="application/json">{course_payload_json}</script>
  <div class="course-shell">
    <aside class="course-sidebar">
      <p class="eyebrow">Module view</p>
      <h1>{escape(str(module.get("title", f"Module {i}")))}</h1>
      <div class="progress-ring" aria-label="Module progress"><span>0%</span></div>
      <ul class="module-nav"><li><a href="index.html">Course index</a></li></ul>
    </aside>
    <div class="lesson-workspace">
      <header class="hero">
        <div>
          <p class="eyebrow">Module {i}</p>
          <h1>{escape(str(module.get("title", f"Module {i}")))}</h1>
          <p class="lede">Lesson list, module activities, and completion controls for this section of the course.</p>
        </div>
        <img src="assets/study-map.svg" alt="Module study map">
      </header>
      <main>
        <section class="module">
          <div class="module-text">
            <h2>Lessons</h2>
            <div class="lesson-grid">{lesson_items}</div>
          </div>
          <div class="video-card"><p>Module pages reuse the same course JSON and player logic as the main course view.</p></div>
        </section>
        <section class="interactive" id="module-activity-deck"></section>
      </main>
      <footer>
        <button class="complete" type="button" id="module-complete">Mark complete</button>
        <p>Generated by Samrat Course MCP.</p>
      </footer>
    </div>
  </div>
  <script src="assets/course.js"></script>
  <script src="assets/player.js"></script>
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
            "SCORM package created and internally validated."
            if validation["valid"]
            else "SCORM package created but validation reported issues."
        ),
    ).model_dump(mode="json")
