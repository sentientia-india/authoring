from __future__ import annotations

import json
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
  --sidebar: #172033;
  --hero-start: #eef6ff;
  --hero-mid: #f8fbff;
  --hero-end: #fff7ed;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  color: var(--ink);
  background: var(--bg);
  font-family: Arial, Helvetica, sans-serif;
  line-height: 1.5;
}
body[data-theme="compliance"] {
  --blue: #1d4ed8;
  --green: #0f766e;
  --orange: #d97706;
  --bg: #f4f7fb;
  --panel: #ffffff;
  --sidebar: #0f172a;
  --hero-start: #e8f1ff;
  --hero-mid: #f7fbff;
  --hero-end: #fff6ea;
}
body[data-theme="academy"] {
  --blue: #7c3aed;
  --green: #0f766e;
  --orange: #ca8a04;
  --bg: #fbf7ff;
  --panel: #ffffff;
  --sidebar: #24153f;
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
  --hero-start: #e3faf4;
  --hero-mid: #f7fffc;
  --hero-end: #fff4e8;
}
.course-shell {
  min-height: 100vh;
  display: grid;
  grid-template-columns: 300px 1fr;
}
.course-sidebar {
  position: sticky;
  top: 0;
  height: 100vh;
  padding: 24px 20px;
  color: #e5e7eb;
  background: var(--sidebar);
  overflow: auto;
}
.course-sidebar h1 { margin: 0 0 14px; font-size: 26px; line-height: 1.1; }
.course-sidebar a { color: #dbeafe; text-decoration: none; }
.progress-ring {
  display: grid;
  place-items: center;
  width: 112px;
  height: 112px;
  margin: 22px 0;
  border-radius: 999px;
  background: conic-gradient(#38bdf8 0 35%, #334155 35% 100%);
}
.progress-ring span {
  display: grid;
  place-items: center;
  width: 82px;
  height: 82px;
  border-radius: 999px;
  background: #172033;
  font-size: 24px;
  font-weight: 700;
}
.module-nav { display: grid; gap: 8px; padding: 0; list-style: none; }
.module-nav li { padding: 10px 12px; border: 1px solid #334155; border-radius: 8px; background: rgba(255,255,255,.04); }
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
  min-height: 58vh;
  display: grid;
  grid-template-columns: minmax(280px, 1fr) minmax(260px, 460px);
  gap: 32px;
  align-items: center;
  padding: 40px min(6vw, 72px);
  background: linear-gradient(120deg, var(--hero-start), var(--hero-mid) 48%, var(--hero-end));
  border-bottom: 1px solid var(--line);
}
.hero h1 { margin: 0; max-width: 760px; font-size: 54px; line-height: 1.02; }
.eyebrow { margin: 0 0 12px; color: var(--blue); font-weight: 700; text-transform: uppercase; font-size: 13px; }
.lede { max-width: 680px; color: var(--muted); font-size: 20px; }
.hero img, .module img { width: 100%; max-height: 360px; }
main { max-width: 1120px; margin: 0 auto; padding: 28px 20px 48px; }
.course-panel {
  display: grid;
  gap: 18px;
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
.lesson-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.lesson-card { display: grid; gap: 12px; padding: 18px; border: 1px solid var(--line); border-radius: 8px; background: #fff; }
.lesson-card h3 { margin: 0 0 8px; }
.lesson-card .lesson-meta { display: flex; gap: 12px; flex-wrap: wrap; color: var(--muted); font-size: 14px; }
.lesson-card.active { border-color: var(--blue); box-shadow: 0 10px 30px rgba(37, 99, 235, .12); }
.lesson-card button { align-self: start; }
.lesson-actions { display: flex; gap: 10px; flex-wrap: wrap; }
.secondary { min-height: 40px; border: 1px solid var(--line); border-radius: 6px; padding: 10px 14px; font-weight: 700; cursor: pointer; background: #edf2f7; color: var(--ink); }
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
.embedded-activity { margin: 12px 0; padding: 14px; border: 1px solid var(--line); border-radius: 6px; background: #f8fafc; }
.embedded-activity h3 { margin: 0 0 6px; }
.embedded-activity span { display: inline-block; color: var(--green); font-weight: 700; }
.activity-shell { display: grid; gap: 12px; }
.activity-card { padding: 16px; border: 1px solid var(--line); border-radius: 8px; background: #fff; display: grid; gap: 10px; }
.activity-card h3 { margin: 0; }
.activity-card .activity-type { color: var(--green); font-weight: 700; text-transform: uppercase; font-size: 12px; }
.activity-card .activity-feedback { min-height: 24px; color: var(--muted); }
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
  .course-shell { grid-template-columns: 1fr; }
  .course-sidebar { position: static; height: auto; }
  .hero, .module, .module.alt, .prompt-builder { grid-template-columns: 1fr; }
  .lesson-grid { grid-template-columns: 1fr; }
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


def _h5p_bridge_js() -> str:
    return """async function renderEmbeddedActivities() {
  const container = document.getElementById("embedded-activities");
  if (!container) return;
  try {
    const response = await fetch("activities/content.json");
    const data = await response.json();
    if (!data.activities || data.activities.length === 0) return;
    container.innerHTML = data.activities.map((activity, index) => `
      <article class="embedded-activity">
        <h3>${activity.title || `Activity ${index + 1}`}</h3>
        <p>${activity.objective || "Complete this interactive practice item."}</p>
        <span>${activity.activity_type || "interactive"}</span>
      </article>`).join("");
  } catch (_error) {
    container.innerHTML = "<p>Interactive activity data is included in this package.</p>";
  }
}
renderEmbeddedActivities();
"""


def _embedded_activities(modules: list[dict]) -> list[dict]:
    activities: list[dict] = []
    for module in modules:
        for activity in module.get("activities", []):
            if isinstance(activity, dict):
                activities.append(activity)
    return activities


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


def _player_js() -> str:
    return r"""const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (ch) => ({
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
  "'": "&#39;"
}[ch]));

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

function loadState(course) {
  try {
    const raw = CourseScorm.getSuspendData();
    if (raw && typeof raw === "object") return raw;
  } catch (_error) {}
  const fallback = localStorage.getItem(`course-state:${course.course_slug}`);
  try { return fallback ? JSON.parse(fallback) : {}; } catch (_error) { return {}; }
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

function renderHero(course) {
  const title = document.getElementById("course-title");
  const lede = document.getElementById("course-lede");
  const progress = document.getElementById("progress-value");
  if (title) title.textContent = course.course_title || "Course";
  if (lede) {
    lede.textContent = `A structured course package with ${course.modules.length} modules, ${flattenLessons(course).length} lessons, generated activities, and LMS completion tracking.`;
  }
  if (progress) progress.textContent = "0%";
}

function renderLessonDeck(course, state) {
  const deck = document.getElementById("lesson-deck");
  if (!deck) return;
  const lessons = flattenLessons(course);
  deck.innerHTML = (course.modules || []).map((module, moduleIndex) => `
    <section class="course-panel" id="module-${moduleIndex + 1}">
      <div class="course-panel-header">
        <div>
          <h2 class="course-panel-title">${escapeHtml(module.title || `Module ${moduleIndex + 1}`)}</h2>
          <p class="course-panel-subtitle">${escapeHtml(`Module ${moduleIndex + 1} of ${course.modules.length}`)}</p>
        </div>
        <span class="lesson-meta">${(module.lessons || []).length} lessons</span>
      </div>
      <div class="lesson-grid">
        ${(module.lessons || []).map((lesson, lessonIndex) => {
          const lessonId = `module-${moduleIndex + 1}-lesson-${lessonIndex + 1}`;
          const completed = (state.completedLessons || []).includes(lessonId);
          const current = state.activeLesson === lessonId;
          return `
            <article class="lesson-card ${completed ? "completed" : ""} ${current ? "active" : ""}" data-lesson-id="${lessonId}">
              <h3>${escapeHtml(lesson.title || `Lesson ${lessonIndex + 1}`)}</h3>
              <p>${escapeHtml(lesson.objective || "Complete the lesson objective.")}</p>
              <div class="lesson-meta">
                <span>${lesson.duration_minutes || 8} min</span>
                <span>${escapeHtml((lesson.objective_ids || []).join(", ") || "objective aligned")}</span>
              </div>
              <div class="lesson-actions">
                <button class="primary" type="button" data-action="open">Open</button>
                <button class="secondary" type="button" data-action="done">${completed ? "Completed" : "Mark done"}</button>
              </div>
            </article>`;
        }).join("")}
      </div>
    </section>
  `).join("");

  deck.querySelectorAll("[data-lesson-id]").forEach((card) => {
    const lessonId = card.dataset.lessonId;
    const open = card.querySelector('[data-action="open"]');
    const done = card.querySelector('[data-action="done"]');
    if (open) {
      open.addEventListener("click", () => {
        CourseScorm.setLocation(lessonId);
        saveState(course, { ...state, activeLesson: lessonId });
        card.scrollIntoView({ behavior: "smooth", block: "center" });
      });
    }
    if (done) {
      done.addEventListener("click", () => {
        const completedLessons = new Set(state.completedLessons || []);
        completedLessons.add(lessonId);
        const nextState = { ...state, activeLesson: lessonId, completedLessons: Array.from(completedLessons) };
        saveState(course, nextState);
        CourseScorm.setLocation(lessonId);
        renderCoursePlayer(course, nextState);
      });
    }
  });

  const completedCount = (state.completedLessons || []).length;
  const percent = lessons.length ? Math.round((completedCount / lessons.length) * 100) : 0;
  const progress = document.getElementById("progress-value");
  if (progress) progress.textContent = `${percent}%`;
}

function renderActivityCard(activity, course, index, state) {
  const card = document.createElement("article");
  card.className = "activity-card";
  card.innerHTML = `
    <div class="activity-type">${escapeHtml(activity.activity_type || activity.type || "interactive")}</div>
    <h3>${escapeHtml(activity.title || `Activity ${index + 1}`)}</h3>
    <p>${escapeHtml(activity.objective || activity.instructions || "Complete the interactive practice item.")}</p>
    <div class="activity-body"></div>
    <div class="activity-feedback" role="status"></div>
  `;
  const body = card.querySelector(".activity-body");
  const feedback = card.querySelector(".activity-feedback");
  const type = String(activity.activity_type || activity.type || "").toLowerCase();
  if (type.includes("matching")) {
    body.innerHTML = (activity.items || []).map((item, itemIndex) => `
      <div class="habit" data-item="${itemIndex}">
        <span>${escapeHtml(item.left || item.front || `Item ${itemIndex + 1}`)}</span>
        <button type="button">View match</button>
        <span class="match-result"></span>
      </div>
    `).join("");
    body.querySelectorAll(".habit button").forEach((button) => {
      button.addEventListener("click", () => {
        const row = button.closest(".habit");
        const result = row.querySelector(".match-result");
        const itemIndex = Number(row.dataset.item);
        const item = activity.items?.[itemIndex] || {};
        result.textContent = item.right || item.back || "Matched";
        feedback.textContent = "Matching interaction revealed.";
        CourseScorm.recordInteraction?.(`activity-${index}`, "matching", item.left || item.front || "", "correct", activity.title || "Matching");
      });
    });
  } else if (type.includes("scenario") || type.includes("decision")) {
    const choices = activity.choices || activity.options || ["Choose the safest action", "Choose the fastest action", "Skip the check"];
    body.innerHTML = `
      <div class="scenario-options">
        ${choices.map((choice, choiceIndex) => `<button type="button" class="primary" data-choice="${choiceIndex}">${escapeHtml(choice)}</button>`).join("")}
      </div>
    `;
    body.querySelectorAll("button").forEach((button) => {
      button.addEventListener("click", () => {
        feedback.textContent = `Selected: ${button.textContent}`;
        CourseScorm.recordInteraction?.(`activity-${index}`, "choice", button.textContent, "neutral", activity.title || "Scenario");
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
      CourseScorm.setSuspendData({ ...state, [`reflection-${index}`]: body.querySelector("textarea").value });
    });
  } else {
    body.innerHTML = `<p>This interactive item is included in the course package and can be extended into a richer renderer later.</p>`;
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
    shell.appendChild(renderActivityCard(activity, course, index, state));
  });
  if (!activities.length) {
    shell.innerHTML = "<p>No interactive activities were generated for this course.</p>";
  }
  deck.appendChild(shell);
}

function renderAssessment(course) {
  const deck = document.getElementById("assessment-deck");
  if (!deck) return;
  const questions = course.final_assessment?.questions || [];
  deck.innerHTML = `
    <div class="course-panel">
      <div class="course-panel-header">
        <div>
          <h2 class="course-panel-title">${escapeHtml(course.final_assessment?.title || "Final Assessment")}</h2>
          <p class="course-panel-subtitle">${questions.length} questions</p>
        </div>
      </div>
      <form id="quiz-form">
        ${questions.map((question, index) => `
          <fieldset data-question-index="${index}">
            <legend>${index + 1}. ${escapeHtml(question.question || "Question")}</legend>
            ${(question.options || []).map((option, optionIndex) => `
              <label>
                <input type="radio" name="q${index}" value="${escapeHtml(option)}">
                ${escapeHtml(option)}
              </label>
            `).join("")}
          </fieldset>
        `).join("")}
      </form>
      <div class="assessment-actions">
        <button class="primary" type="button" id="quiz-submit">Submit quiz</button>
        <p id="quiz-feedback" class="feedback" role="status"></p>
      </div>
    </div>
  `;
  const submit = deck.querySelector("#quiz-submit");
  const feedback = deck.querySelector("#quiz-feedback");
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
    feedback.textContent = `Score: ${score}/${questions.length} (${percent}%).`;
    CourseScorm.setScore(percent);
    if (percent >= 80) CourseScorm.markComplete();
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

function renderCoursePlayer(course) {
  const state = loadState(course);
  renderHero(course);
  renderModuleNav(course, state);
  renderLessonDeck(course, state);
  renderActivityDeck(course, state);
  renderAssessment(course);
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
    activities_dir = base / "activities"
    activities_dir.mkdir(exist_ok=True)
    data_dir = base / "data"
    data_dir.mkdir(exist_ok=True)
    module_files = [_module_page_name(i) for i, _module in enumerate(req.modules, start=1)]
    activities = _embedded_activities(req.modules)
    course_payload = _course_payload(req)
    course_payload["theme"] = _theme_for_course(req.course_title, " ".join(str(module.get("title", "")) for module in req.modules))
    course_payload_json = json.dumps(course_payload, indent=2).replace("</", "<\\/")
    asset_files = [
        "assets/styles.css",
        "assets/course.js",
        "assets/player.js",
        "assets/h5p_bridge.js",
        "assets/scorm_api.js",
        "assets/study-map.svg",
        "assets/prompt-lab.svg",
    ]
    activity_files = ["activities/content.json"] if activities else []
    data_files = ["data/course.json"]
    files = ["imsmanifest.xml", "index.html", *module_files, *asset_files, *activity_files, *data_files]

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
{chr(10).join(f'      <file href="{escape(file_name)}" />' for file_name in activity_files)}
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
<body data-course-player data-theme="{escape(course_payload["theme"])}">
  <script id="course-data" type="application/json">{course_payload_json}</script>
  <div class="course-shell">
    <aside class="course-sidebar">
      <p class="eyebrow">SCORM course player</p>
      <h1 id="course-title">{escape(req.course_title)}</h1>
      <div class="progress-ring" aria-label="Course progress"><span id="progress-value">0%</span></div>
      <ul class="module-nav" id="module-nav">{navigation}</ul>
    </aside>
    <div class="lesson-workspace">
      <header class="hero">
        <div id="hero-copy">
          <p class="eyebrow">Interactive lesson path</p>
          <h1>{escape(req.course_title)}</h1>
          <p class="lede" id="course-lede">A structured course package with generated lessons, source-aware activity data, quiz scoring, suspend/resume data, and LMS completion tracking.</p>
        </div>
        <img src="assets/study-map.svg" alt="Course study map">
      </header>
      <main>
        <section class="module">
          <div class="module-text">
            <h2>How to use this course</h2>
            <p>Move through each lesson, save progress, complete the interactions, and submit the final quiz. The LMS can capture score, location, suspend data, interactions, and completion.</p>
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
          <h2>Embedded interactive content</h2>
          <p>H5P-style activity data is packaged inside this SCORM file so the course can be delivered as one download.</p>
          <div id="activity-deck"></div>
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
        <section class="quiz" id="assessment-deck"></section>
      </main>
      <footer>
        <button class="complete" type="button" onclick="markCourseComplete()">Mark course complete</button>
        <p>Generated by Samrat Course MCP.</p>
      </footer>
    </div>
  </div>
  <script src="assets/course.js"></script>
  <script src="assets/player.js"></script>
  <script src="assets/h5p_bridge.js"></script>
</body>
</html>
"""

    (base / "imsmanifest.xml").write_text(manifest, encoding="utf-8")
    (base / "index.html").write_text(index, encoding="utf-8")
    (assets / "styles.css").write_text(_styles_css(), encoding="utf-8")
    (assets / "course.js").write_text(_course_js(), encoding="utf-8")
    (assets / "player.js").write_text(_player_js(), encoding="utf-8")
    (assets / "h5p_bridge.js").write_text(_h5p_bridge_js(), encoding="utf-8")
    (assets / "scorm_api.js").write_text(_runtime_js(), encoding="utf-8")
    (assets / "study-map.svg").write_text(_study_map_svg(), encoding="utf-8")
    (assets / "prompt-lab.svg").write_text(_prompt_lab_svg(), encoding="utf-8")
    if activities:
        (activities_dir / "content.json").write_text(
            json.dumps({"format": "h5p-style", "activities": activities}, indent=2),
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
        <button class="complete" type="button" onclick="CourseScorm.markComplete()">Mark complete</button>
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
