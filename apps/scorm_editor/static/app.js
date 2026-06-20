let importedZip = null;
let course = null;
let selection = { type: null, moduleIndex: null, lessonIndex: null };
let mode = "outline";
let viewport = "desktop";

const $ = (id) => document.getElementById(id);

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[ch]));
}

function flatten() {
  const items = [];
  (course?.modules || []).forEach((module, moduleIndex) => {
    items.push({ type: "module", moduleIndex, title: module.title || `Module ${moduleIndex + 1}`, module });
    (module.lessons || []).forEach((lesson, lessonIndex) => {
      items.push({ type: "lesson", moduleIndex, lessonIndex, title: lesson.title || `Lesson ${lessonIndex + 1}`, lesson });
    });
  });
  return items;
}

function ensureBlocks(lesson) {
  if (!Array.isArray(lesson.content_blocks)) {
    lesson.content_blocks = [
      { type: "intro", text: `Start with the real work context for: ${lesson.objective || "this lesson"}` },
      { type: "concept", text: lesson.objective || "Explain the key idea learners need." },
      { type: "example", text: "Add one practical example." },
      { type: "scenario", text: "Add one realistic decision scenario." },
      { type: "practice", text: "Ask learners to apply the idea." },
      { type: "takeaway", text: "Summarize the safest next action." },
    ];
  }
  return lesson.content_blocks;
}

function renderOutline() {
  const outline = $("outline");
  if (!course) {
    outline.innerHTML = "<p class='muted'>Load a package to edit the outline.</p>";
    return;
  }
  outline.innerHTML = (course.modules || []).map((module, moduleIndex) => `
    <div class="node ${selection.type === "module" && selection.moduleIndex === moduleIndex ? "active" : ""}" draggable="true" data-type="module" data-module-index="${moduleIndex}">
      <strong>${esc(module.title || `Module ${moduleIndex + 1}`)}</strong>
      <small>${(module.lessons || []).length} lessons</small>
      <div class="pill-row">
        <span class="pill">Drag to reorder</span>
      </div>
      <div class="node-list">
        ${(module.lessons || []).map((lesson, lessonIndex) => `
          <div class="node ${selection.type === "lesson" && selection.moduleIndex === moduleIndex && selection.lessonIndex === lessonIndex ? "active" : ""}"
               draggable="true" data-type="lesson" data-module-index="${moduleIndex}" data-lesson-index="${lessonIndex}">
            <strong>${esc(lesson.title || `Lesson ${lessonIndex + 1}`)}</strong>
            <small>${esc(lesson.objective || "No objective yet")}</small>
          </div>
        `).join("")}
      </div>
    </div>
  `).join("");
  [...outline.querySelectorAll("[data-type]")].forEach((node) => {
    node.addEventListener("click", () => selectNode(node.dataset.type, Number(node.dataset.moduleIndex), Number(node.dataset.lessonIndex)));
    node.addEventListener("dragstart", onDragStart);
    node.addEventListener("dragover", onDragOver);
    node.addEventListener("drop", onDrop);
  });
}

function selectNode(type, moduleIndex, lessonIndex = null) {
  selection = { type, moduleIndex, lessonIndex };
  if (type === "lesson") mode = "lesson";
  if (type === "module") mode = "outline";
  renderOutline();
  renderModes();
  renderEditor();
  renderPreview();
}

let dragState = null;
function onDragStart(event) {
  dragState = {
    type: event.currentTarget.dataset.type,
    moduleIndex: Number(event.currentTarget.dataset.moduleIndex),
    lessonIndex: event.currentTarget.dataset.lessonIndex === undefined ? null : Number(event.currentTarget.dataset.lessonIndex),
  };
}
function onDragOver(event) {
  if (dragState) event.preventDefault();
}
function onDrop(event) {
  event.preventDefault();
  const target = {
    type: event.currentTarget.dataset.type,
    moduleIndex: Number(event.currentTarget.dataset.moduleIndex),
    lessonIndex: event.currentTarget.dataset.lessonIndex === undefined ? null : Number(event.currentTarget.dataset.lessonIndex),
  };
  if (!dragState || dragState.type !== target.type) return;
  if (dragState.type === "module") {
    const [module] = course.modules.splice(dragState.moduleIndex, 1);
    course.modules.splice(target.moduleIndex, 0, module);
  } else if (dragState.type === "lesson" && dragState.moduleIndex === target.moduleIndex) {
    const lessons = course.modules[target.moduleIndex].lessons;
    const [lesson] = lessons.splice(dragState.lessonIndex, 1);
    lessons.splice(target.lessonIndex, 0, lesson);
  }
  dragState = null;
  renderAll();
}

function renderEditor() {
  const editor = $("editor");
  const label = $("selection-label");
  if (!course) {
    editor.innerHTML = "<p class='muted'>Import a course package to start editing.</p>";
    label.textContent = "No course loaded";
    return;
  }
  if (mode === "theme") {
    label.textContent = "Theme";
    editor.innerHTML = `
      <form class="editor-form" id="theme-form">
        <label>Course title<input name="course_title" value="${esc(course.course_title || "")}"></label>
        <label>Theme
          <select name="theme">
            ${["studio", "academy", "compliance"].map((item) => `<option value="${item}" ${course.theme === item ? "selected" : ""}>${item}</option>`).join("")}
          </select>
        </label>
        <label>Course summary<textarea name="summary">${esc(course.summary || course.description || "")}</textarea></label>
      </form>
    `;
    $("theme-form").addEventListener("input", updateTheme);
    return;
  }
  if (mode === "assessment") {
    label.textContent = "Assessment";
    renderAssessmentEditor(editor);
    return;
  }
  if (selection.type === null) {
    editor.innerHTML = "<p class='muted'>Select a module or lesson to edit it.</p>";
    label.textContent = "Nothing selected";
    return;
  }
  if (selection.type === "module") {
    const module = course.modules[selection.moduleIndex];
    label.textContent = `Module ${selection.moduleIndex + 1}`;
    editor.innerHTML = `
      <form class="editor-form" id="module-form">
        <label>Module title<input name="title" value="${esc(module.title || "")}"></label>
        <label>Module overview<textarea name="overview">${esc(module.overview || "")}</textarea></label>
        <label>Duration minutes<input name="duration_minutes" type="number" min="0" value="${Number(module.duration_minutes || 0)}"></label>
      </form>
    `;
    $("module-form").addEventListener("input", updateSelectedModule);
    return;
  }
  const module = course.modules[selection.moduleIndex];
  const lesson = module.lessons[selection.lessonIndex];
  label.textContent = `Lesson ${selection.lessonIndex + 1}`;
  editor.innerHTML = `
    <form class="editor-form" id="lesson-form">
      <label>Lesson title<input name="title" value="${esc(lesson.title || "")}"></label>
      <label>Objective<textarea name="objective">${esc(lesson.objective || "")}</textarea></label>
      <label>Duration minutes<input name="duration_minutes" type="number" min="0" value="${Number(lesson.duration_minutes || 0)}"></label>
    </form>
    <div class="panel-head">
      <strong>Reader blocks</strong>
      <button class="mini-action" type="button" id="add-block">Add block</button>
    </div>
    <div class="block-list" id="block-list">
      ${ensureBlocks(lesson).map((block, index) => renderBlockRow(block, index)).join("")}
    </div>
  `;
  $("lesson-form").addEventListener("input", updateSelectedLesson);
  $("add-block").addEventListener("click", addLessonBlock);
  wireBlockEditors();
}

function updateSelectedModule() {
  const form = $("module-form");
  const module = course.modules[selection.moduleIndex];
  module.title = form.title.value;
  module.overview = form.overview.value;
  module.duration_minutes = Number(form.duration_minutes.value || 0);
  renderOutline();
  renderPreview();
}

function updateSelectedLesson() {
  const form = $("lesson-form");
  const lesson = course.modules[selection.moduleIndex].lessons[selection.lessonIndex];
  lesson.title = form.title.value;
  lesson.objective = form.objective.value;
  lesson.duration_minutes = Number(form.duration_minutes.value || 0);
  if (!lesson.content_blocks) ensureBlocks(lesson);
  renderOutline();
  renderPreview();
}

function updateTheme() {
  const form = $("theme-form");
  course.course_title = form.course_title.value;
  course.theme = form.theme.value;
  course.summary = form.summary.value;
  renderPreview();
}

function renderBlockRow(block, index) {
  return `
    <section class="block-row" data-block-index="${index}">
      <header>
        <strong>Block ${index + 1}</strong>
        <div>
          <button class="mini-action" type="button" data-block-action="up">Up</button>
          <button class="mini-action" type="button" data-block-action="down">Down</button>
          <button class="mini-action" type="button" data-block-action="remove">Remove</button>
        </div>
      </header>
      <label>Type
        <select data-block-field="type">
          ${["intro", "concept", "example", "scenario", "practice", "takeaway"].map((type) => `<option value="${type}" ${block.type === type ? "selected" : ""}>${type}</option>`).join("")}
        </select>
      </label>
      <label>Text<textarea data-block-field="text">${esc(block.text || "")}</textarea></label>
    </section>
  `;
}

function selectedLesson() {
  if (selection.type !== "lesson") return null;
  return course.modules?.[selection.moduleIndex]?.lessons?.[selection.lessonIndex] || null;
}

function wireBlockEditors() {
  const lesson = selectedLesson();
  if (!lesson) return;
  ensureBlocks(lesson);
  document.querySelectorAll("[data-block-index]").forEach((row) => {
    const index = Number(row.dataset.blockIndex);
    row.querySelectorAll("[data-block-field]").forEach((field) => {
      field.addEventListener("input", () => {
        lesson.content_blocks[index][field.dataset.blockField] = field.value;
        renderPreview();
      });
    });
    row.querySelectorAll("[data-block-action]").forEach((button) => {
      button.addEventListener("click", () => mutateBlock(index, button.dataset.blockAction));
    });
  });
}

function mutateBlock(index, action) {
  const lesson = selectedLesson();
  if (!lesson) return;
  const blocks = ensureBlocks(lesson);
  if (action === "remove") blocks.splice(index, 1);
  if (action === "up" && index > 0) blocks.splice(index - 1, 0, blocks.splice(index, 1)[0]);
  if (action === "down" && index < blocks.length - 1) blocks.splice(index + 1, 0, blocks.splice(index, 1)[0]);
  renderEditor();
  renderPreview();
}

function addLessonBlock() {
  const lesson = selectedLesson();
  if (!lesson) return;
  ensureBlocks(lesson).push({ type: "practice", text: "Add learner practice here." });
  renderEditor();
  renderPreview();
}

function renderAssessmentEditor(editor) {
  const assessment = course.final_assessment || { title: "Final Check", questions: [] };
  course.final_assessment = assessment;
  editor.innerHTML = `
    <form class="editor-form" id="assessment-form">
      <label>Assessment title<input name="title" value="${esc(assessment.title || "Final Check")}"></label>
      <label>Passing score<input name="passing_score" type="number" min="0" max="100" value="${Number(assessment.passing_score || 80)}"></label>
    </form>
    <div class="panel-head">
      <strong>Questions</strong>
      <button class="mini-action" type="button" id="add-question">Add question</button>
    </div>
    <div class="question-list">
      ${(assessment.questions || []).map((question, index) => renderQuestionRow(question, index)).join("") || "<p class='muted'>No questions yet.</p>"}
    </div>
  `;
  $("assessment-form").addEventListener("input", () => {
    assessment.title = $("assessment-form").title.value;
    assessment.passing_score = Number($("assessment-form").passing_score.value || 80);
    renderPreview();
  });
  $("add-question").addEventListener("click", () => {
    assessment.questions.push({ type: "mcq", question: "New question", options: ["Correct answer", "Distractor"], correct_answers: ["Correct answer"], explanation: "" });
    renderEditor();
    renderPreview();
  });
  document.querySelectorAll("[data-question-index]").forEach((row) => wireQuestionRow(row, assessment));
}

function renderQuestionRow(question, index) {
  return `
    <section class="question-row" data-question-index="${index}">
      <header>
        <strong>Question ${index + 1}</strong>
        <button class="mini-action" type="button" data-question-action="remove">Remove</button>
      </header>
      <label>Question<textarea data-question-field="question">${esc(question.question || "")}</textarea></label>
      <label>Options, one per line<textarea data-question-field="options">${esc((question.options || []).join("\n"))}</textarea></label>
      <label>Correct answer<input data-question-field="correct" value="${esc((question.correct_answers || [])[0] || "")}"></label>
      <label>Feedback<textarea data-question-field="explanation">${esc(question.explanation || "")}</textarea></label>
    </section>
  `;
}

function wireQuestionRow(row, assessment) {
  const index = Number(row.dataset.questionIndex);
  row.querySelector("[data-question-action]")?.addEventListener("click", () => {
    assessment.questions.splice(index, 1);
    renderEditor();
    renderPreview();
  });
  row.querySelectorAll("[data-question-field]").forEach((field) => {
    field.addEventListener("input", () => {
      const question = assessment.questions[index];
      if (field.dataset.questionField === "options") question.options = field.value.split("\n").map((item) => item.trim()).filter(Boolean);
      if (field.dataset.questionField === "correct") question.correct_answers = [field.value.trim()].filter(Boolean);
      if (field.dataset.questionField === "question") question.question = field.value;
      if (field.dataset.questionField === "explanation") question.explanation = field.value;
      renderPreview();
    });
  });
}

function renderAll() {
  renderOutline();
  renderModes();
  renderEditor();
  renderPreview();
  $("export-btn").disabled = !importedZip || !course;
  $("import-status").textContent = course
    ? `${course.course_title || "Course"} loaded with ${(course.modules || []).length} modules.`
    : "No package loaded.";
}

function renderModes() {
  document.querySelectorAll(".mode-tab").forEach((button) => {
    button.classList.toggle("active", button.dataset.mode === mode);
  });
  document.querySelectorAll(".viewport-tab").forEach((button) => {
    button.classList.toggle("active", button.dataset.viewport === viewport);
  });
}

function renderPreview() {
  const preview = $("preview");
  if (!preview) return;
  preview.dataset.viewport = viewport;
  if (!course) {
    preview.innerHTML = "<div class='preview-course'><p class='muted'>Import a package to preview the course.</p></div>";
    return;
  }
  const modules = course.modules || [];
  const selected = selectedLesson() || modules[0]?.lessons?.[0] || null;
  const blocks = selected ? ensureBlocks(selected) : [];
  preview.innerHTML = `
    <div class="preview-course">
      <p class="eyebrow">${esc(course.theme || "studio")}</p>
      <h2>${esc(course.course_title || "Course")}</h2>
      ${modules.slice(0, 3).map((module) => `<div class="preview-module"><strong>${esc(module.title || "Module")}</strong><p class="muted">${(module.lessons || []).length} lessons</p></div>`).join("")}
      ${selected ? `<div class="preview-lesson"><strong>${esc(selected.title || "Lesson")}</strong><p>${esc(selected.objective || "")}</p></div>` : ""}
      ${blocks.map((block) => `<div class="preview-block"><strong>${esc(block.type || "block")}</strong><p>${esc(block.text || "")}</p></div>`).join("")}
    </div>
  `;
}

async function importZip(file) {
  const zip = await fileToDataUrl(file);
  const response = await fetch("/api/import", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ zip }),
  });
  const payload = await response.json();
  if (!response.ok || !payload.ok) throw new Error(payload.error || "Failed to import package.");
  importedZip = file;
  course = payload.data.course;
  selection = { type: null, moduleIndex: null, lessonIndex: null };
  renderAll();
}

async function exportZip() {
  if (!importedZip || !course) return;
  const response = await fetch("/api/export", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ zip: await fileToDataUrl(importedZip), course }),
  });
  if (!response.ok) throw new Error("Export failed.");
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = (course.course_slug || "scorm-course") + "-edited.zip";
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1500);
}

function fileToDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(reader.error || new Error("Could not read file."));
    reader.readAsDataURL(file);
  });
}

function wire() {
  $("zip-input").addEventListener("change", (event) => importZip(event.target.files[0]).catch((error) => $("import-status").textContent = error.message));
  $("export-btn").addEventListener("click", () => exportZip().catch((error) => $("import-status").textContent = error.message));
  document.querySelectorAll(".mode-tab").forEach((button) => {
    button.addEventListener("click", () => {
      mode = button.dataset.mode;
      renderAll();
    });
  });
  document.querySelectorAll(".viewport-tab").forEach((button) => {
    button.addEventListener("click", () => {
      viewport = button.dataset.viewport;
      renderAll();
    });
  });
  const dropzone = $("dropzone");
  dropzone.addEventListener("dragover", (event) => {
    event.preventDefault();
    dropzone.classList.add("is-active");
  });
  dropzone.addEventListener("dragleave", () => dropzone.classList.remove("is-active"));
  dropzone.addEventListener("drop", (event) => {
    event.preventDefault();
    dropzone.classList.remove("is-active");
    const file = event.dataTransfer.files[0];
    if (file) importZip(file).catch((error) => $("import-status").textContent = error.message);
  });
}

wire();
renderAll();
