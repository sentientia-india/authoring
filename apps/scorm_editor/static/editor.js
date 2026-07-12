/* Course Studio — WYSIWYG editor whose canvas IS the real course player.
   Same-origin iframe: the editor reads and decorates the player DOM directly. */
(function () {
  "use strict";

  var state = {
    session: null,
    course: null,
    version: null,
    saving: false,
    conflicted: false,
    history: [],
    historyIndex: -1,
    selected: { kind: "course" },
  };

  var $ = function (id) { return document.getElementById(id); };
  var canvas = $("canvas");

  /* ================= utilities ================= */

  function uid(prefix) {
    return prefix + "_" + Math.random().toString(36).slice(2, 8);
  }

  function toast(message) {
    var el = $("toast");
    el.textContent = message;
    el.hidden = false;
    clearTimeout(el._t);
    el._t = setTimeout(function () { el.hidden = true; }, 2200);
  }

  function clone(value) { return JSON.parse(JSON.stringify(value)); }

  function setSaveStatus(message) { $("save-status").textContent = message; }

  function recoveryKey() { return state.session ? "course-studio-recovery:" + state.session : null; }

  function persistRecovery() {
    if (recoveryKey()) localStorage.setItem(recoveryKey(), JSON.stringify({ course: state.course, version: state.version, savedAt: Date.now() }));
  }

  function clearRecovery() { if (recoveryKey()) localStorage.removeItem(recoveryKey()); }

  function escapeHtml(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (ch) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch];
    });
  }

  /* ================= course model helpers ================= */

  function lessonsOf(course) {
    var rows = [];
    (course.modules || []).forEach(function (module, mi) {
      (module.lessons || []).forEach(function (lesson, li) {
        rows.push({ module: module, lesson: lesson, mi: mi, li: li });
      });
    });
    return rows;
  }

  function findLesson(lessonKey) {
    var parts = lessonKey.split(":");
    var module = state.course.modules[Number(parts[0])];
    return module ? { module: module, lesson: module.lessons[Number(parts[1])], mi: Number(parts[0]), li: Number(parts[1]) } : null;
  }

  function findBlock(cbId) {
    var hit = null;
    lessonsOf(state.course).forEach(function (row) {
      (row.lesson.content_blocks || []).forEach(function (block) {
        if (block.id === cbId) hit = { block: block, row: row };
      });
    });
    return hit;
  }

  function findActivity(activityId) {
    var hit = null;
    lessonsOf(state.course).forEach(function (row) {
      (row.lesson.activities || []).forEach(function (activity) {
        if ((activity.activity_id || activity.id) === activityId) hit = { activity: activity, row: row };
      });
    });
    (state.course.modules || []).forEach(function (module) {
      (module.activities || []).forEach(function (activity) {
        if ((activity.activity_id || activity.id) === activityId) hit = { activity: activity, row: null };
      });
    });
    return hit;
  }

  function findQuestion(questionId) {
    var hit = null;
    var final = state.course.final_assessment || {};
    (final.questions || []).forEach(function (question) {
      if (question.id === questionId) hit = { question: question, home: final.questions };
    });
    lessonsOf(state.course).forEach(function (row) {
      (row.lesson.quiz_questions || []).forEach(function (question) {
        if (question.id === questionId) hit = { question: question, home: row.lesson.quiz_questions };
      });
    });
    return hit;
  }

  /* ================= persistence + history ================= */

  function pushHistory() {
    state.history = state.history.slice(0, state.historyIndex + 1);
    state.history.push(clone(state.course));
    if (state.history.length > 60) state.history.shift();
    state.historyIndex = state.history.length - 1;
    updateUndoButtons();
  }

  function updateUndoButtons() {
    $("btn-undo").disabled = state.historyIndex <= 0;
    $("btn-redo").disabled = state.historyIndex >= state.history.length - 1;
  }

  function undo() {
    if (state.historyIndex <= 0) return;
    state.historyIndex -= 1;
    state.course = clone(state.history[state.historyIndex]);
    updateUndoButtons();
    save(true, true);
  }

  function redo() {
    if (state.historyIndex >= state.history.length - 1) return;
    state.historyIndex += 1;
    state.course = clone(state.history[state.historyIndex]);
    updateUndoButtons();
    save(true, true);
  }

  function save(structural, recorded) {
    if (state.conflicted) { toast("Reload the newer revision before saving."); return Promise.resolve(); }
    if (!recorded) pushHistory();
    persistRecovery();
    state.saving = true;
    setSaveStatus(navigator.onLine ? "Saving…" : "Offline · recovery saved");
    return fetch("/api/course/" + state.session, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ course: state.course, version: state.version }),
    })
      .then(function (res) { return res.json().then(function (data) { data.httpStatus = res.status; return data; }); })
      .then(function (data) {
        if (data.httpStatus === 409) {
          state.conflicted = true;
          $("conflict-banner").hidden = false;
          setSaveStatus("Conflict · reload required");
          throw new Error("Another tab saved a newer revision");
        }
        if (data.httpStatus === 410) {
          setSaveStatus("Session expired · recovery available");
          throw new Error("Session expired");
        }
        if (!data.ok) throw new Error(data.error || "Save failed");
        state.version = data.version;
        state.saving = false;
        clearRecovery();
        setSaveStatus("Saved · revision " + data.version);
        if (state.channel) state.channel.postMessage({ session: state.session, version: state.version });
        if (structural) reloadCanvas();
        renderTree();
        $("course-name").textContent = state.course.course_title || "Untitled course";
      })
      .catch(function (error) { state.saving = false; persistRecovery(); if (!state.conflicted) setSaveStatus("Recovery saved locally"); toast("Save failed: " + error.message); });
  }

  function reloadCanvas() {
    canvas.contentWindow.location.reload();
  }

  function postCollaboration(action, payload) {
    payload = payload || {};
    payload.action = action;
    payload.actor = payload.actor || "author";
    return fetch("/api/collaboration/" + state.session, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
    }).then(function (res) { return res.json(); }).then(function (data) {
      if (!data.ok) throw new Error(data.error || "Review update failed");
      renderReview();
      return data;
    });
  }

  function renderReview() {
    var box = $("tab-review");
    if (!state.session || !box) return;
    Promise.all([
      fetch("/api/revisions/" + state.session).then(function (res) { return res.json(); }),
      fetch("/api/collaboration/" + state.session).then(function (res) { return res.json(); }),
    ]).then(function (rows) {
      var revisions = rows[0].revisions || [];
      var collaboration = rows[1].collaboration || { comments: [], approvals: [], roles: {} };
      box.replaceChildren();
      var heading = document.createElement("h3"); heading.textContent = "Review & approval"; box.appendChild(heading);
      var form = document.createElement("form"); form.className = "review-form";
      var input = document.createElement("textarea"); input.setAttribute("aria-label", "New review comment"); input.placeholder = "Add a review comment";
      var submit = document.createElement("button"); submit.className = "primary"; submit.type = "submit"; submit.textContent = "Comment";
      form.append(input, submit); form.addEventListener("submit", function (event) { event.preventDefault(); postCollaboration("comment", { message: input.value, target: state.selected.kind || "course" }).catch(function (error) { toast(error.message); }); }); box.appendChild(form);
      var actions = document.createElement("div"); actions.className = "review-actions";
      [["approved", "Approve revision"], ["changes_requested", "Request changes"]].forEach(function (choice) { var button=document.createElement("button"); button.className="ghost"; button.textContent=choice[1]; button.addEventListener("click", function () { postCollaboration("approval", { decision: choice[0] }).catch(function (error) { toast(error.message); }); }); actions.appendChild(button); }); box.appendChild(actions);
      var revisionTitle=document.createElement("h4"); revisionTitle.textContent="Revision history"; box.appendChild(revisionTitle);
      revisions.forEach(function (revision) { var row=document.createElement("p"); row.className="review-row"; row.textContent="Revision "+revision.version+" · "+revision.reason+" · "+revision.actor; box.appendChild(row); });
      var commentTitle=document.createElement("h4"); commentTitle.textContent="Comments"; box.appendChild(commentTitle);
      collaboration.comments.forEach(function (comment) { var row=document.createElement("p"); row.className="review-row"; row.textContent=(comment.resolved?"Resolved · ":"")+comment.actor+": "+comment.message; box.appendChild(row); });
    }).catch(function (error) { box.textContent = "Review data unavailable: " + error.message; });
  }

  /* ================= import / export ================= */

  function importZip(file) {
    var reader = new FileReader();
    reader.onload = function () {
      fetch("/api/import", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ zip: reader.result }),
      })
        .then(function (res) { return res.json(); })
        .then(function (data) {
          if (!data.ok) throw new Error(data.error || "Import failed");
          openSession(data.session, data.course, data.version);
          toast("Course imported — the canvas is the real player.");
        })
        .catch(function (error) {
          $("import-error").textContent = error.message;
          toast(error.message);
        });
    };
    reader.readAsDataURL(file);
  }

  function exportZip() {
    fetch("/api/export/" + state.session, { method: "POST" })
      .then(function (res) {
        if (!res.ok) throw new Error("Export failed");
        return res.blob();
      })
      .then(function (blob) {
        var link = document.createElement("a");
        link.href = URL.createObjectURL(blob);
        link.download = (state.course.course_slug || "course") + "-edited.zip";
        link.click();
        URL.revokeObjectURL(link.href);
        toast("SCORM zip exported.");
      })
      .catch(function (error) { toast(error.message); });
  }

  function createNewCourse(event) {
    event.preventDefault();
    setSaveStatus("Creating course…");
    fetch("/api/new", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: $("new-course-title").value, audience: $("new-course-audience").value, template: $("new-course-template").value }),
    }).then(function (res) { return res.json(); }).then(function (data) {
      if (!data.ok) throw new Error(data.error || "Course creation failed");
      openSession(data.session, data.course, data.version);
      history.replaceState(null, "", "?session=" + encodeURIComponent(data.session));
      toast("New course ready to author.");
    }).catch(function (error) { setSaveStatus("Course creation failed"); $("import-error").textContent = error.message; });
  }

  /* ================= selection ================= */

  function select(sel) {
    state.selected = sel;
    renderInspector();
    renderTree();
  }

  /* ================= structure tree ================= */

  function treeNode(options) {
    var node = document.createElement("div");
    node.className = "tree-node" + (options.indent ? " tree-indent-" + options.indent : "") + (options.selected ? " selected" : "");
    node.innerHTML =
      (options.draggable ? '<span class="grip" title="Drag to reorder">⋮⋮</span>' : "") +
      '<span class="kind">' + options.kind + "</span>" +
      '<span class="label">' + escapeHtml(options.label) + "</span>" +
      (options.onDelete ? '<button class="del" title="Delete">✕</button>' : "");
    node.addEventListener("click", function (event) {
      if (event.target.classList.contains("del")) return;
      options.onSelect();
    });
    if (options.onDelete) {
      node.querySelector(".del").addEventListener("click", function () {
        if (confirm("Delete '" + options.label + "'?")) options.onDelete();
      });
    }
    if (options.draggable) {
      node.draggable = true;
      node.addEventListener("dragstart", function (event) {
        event.dataTransfer.setData("text/plain", JSON.stringify(options.drag));
        event.dataTransfer.effectAllowed = "move";
      });
      node.addEventListener("dragover", function (event) {
        event.preventDefault();
        node.classList.add("drag-over");
      });
      node.addEventListener("dragleave", function () { node.classList.remove("drag-over"); });
      node.addEventListener("drop", function (event) {
        event.preventDefault();
        node.classList.remove("drag-over");
        var payload;
        try { payload = JSON.parse(event.dataTransfer.getData("text/plain")); } catch (e) { return; }
        handleDrop(payload, options.drag);
      });
    }
    return node;
  }

  function moveItem(list, from, to) {
    var item = list.splice(from, 1)[0];
    list.splice(to, 0, item);
  }

  function handleDrop(source, target) {
    if (!source || !target) return;
    if (source.type === "template") { insertTemplate(source.template, target); return; }
    if (source.type !== target.type) return;
    var c = state.course;
    if (source.type === "module") {
      moveItem(c.modules, source.mi, target.mi);
    } else if (source.type === "lesson") {
      var item = c.modules[source.mi].lessons.splice(source.li, 1)[0];
      c.modules[target.mi].lessons.splice(target.li, 0, item);
    } else if (source.type === "block") {
      if (source.key !== target.key) return;
      var lesson = findLesson(source.key).lesson;
      moveItem(lesson.content_blocks, source.bi, target.bi);
    } else if (source.type === "activity") {
      if (source.key !== target.key) return;
      var lesson2 = findLesson(source.key).lesson;
      moveItem(lesson2.activities, source.ai, target.ai);
    } else if (source.type === "question") {
      if (source.home !== target.home) return;
      var home = target.home === "final" ? state.course.final_assessment.questions : findLesson(target.home).lesson.quiz_questions;
      moveItem(home, source.qi, target.qi);
    } else {
      return;
    }
    save(true);
    toast("Reordered.");
  }

  function renderTree() {
    var box = $("tab-structure");
    if (!state.course) return;
    box.innerHTML = "";
    var tree = document.createElement("div");
    tree.className = "tree";
    var sel = state.selected;

    tree.appendChild(treeNode({
      kind: "course",
      label: state.course.course_title || "Course",
      selected: sel.kind === "course",
      onSelect: function () { select({ kind: "course" }); },
    }));

    (state.course.modules || []).forEach(function (module, mi) {
      tree.appendChild(treeNode({
        kind: "module",
        label: module.title || "Module " + (mi + 1),
        indent: 1,
        selected: sel.kind === "module" && sel.mi === mi,
        draggable: true,
        drag: { type: "module", mi: mi },
        onSelect: function () { select({ kind: "module", mi: mi }); },
        onDelete: function () { state.course.modules.splice(mi, 1); save(true); },
      }));
      (module.lessons || []).forEach(function (lesson, li) {
        var key = mi + ":" + li;
        tree.appendChild(treeNode({
          kind: "lesson",
          label: lesson.title || "Lesson " + (li + 1),
          indent: 2,
          selected: sel.kind === "lesson" && sel.key === key,
          draggable: true,
          drag: { type: "lesson", mi: mi, li: li },
          onSelect: function () { select({ kind: "lesson", key: key }); },
          onDelete: function () { module.lessons.splice(li, 1); save(true); },
        }));
      });
    });

    var finalQuestions = (state.course.final_assessment || {}).questions || [];
    tree.appendChild(treeNode({
      kind: "final",
      label: (state.course.final_assessment || {}).title || "Final assessment (" + finalQuestions.length + " questions)",
      indent: 1,
      selected: sel.kind === "final",
      onSelect: function () { select({ kind: "final" }); },
    }));

    box.appendChild(tree);

    if (sel.kind === "lesson" && findLesson(sel.key)) {
      var found = findLesson(sel.key);
      var lesson = found.lesson;
      var label = document.createElement("div");
      label.className = "tree-group-label";
      label.textContent = "Inside: " + (lesson.title || "lesson");
      box.appendChild(label);
      var sub = document.createElement("div");
      sub.className = "tree";
      (lesson.content_blocks || []).forEach(function (block, bi) {
        sub.appendChild(treeNode({
          kind: block.type || "block",
          label: (block.text || "").slice(0, 46) || "(empty)",
          indent: 1,
          selected: sel.kind === "block" && sel.cbId === block.id,
          draggable: true,
          drag: { type: "block", key: sel.key, bi: bi },
          onSelect: function () { select({ kind: "block", cbId: block.id, key: sel.key }); },
          onDelete: function () { lesson.content_blocks.splice(bi, 1); save(true); },
        }));
      });
      (lesson.activities || []).forEach(function (activity, ai) {
        sub.appendChild(treeNode({
          kind: "activity",
          label: activity.title || activity.activity_type || "Activity",
          indent: 1,
          selected: sel.kind === "activity" && sel.activityId === (activity.activity_id || activity.id),
          draggable: true,
          drag: { type: "activity", key: sel.key, ai: ai },
          onSelect: function () { select({ kind: "activity", activityId: activity.activity_id || activity.id, key: sel.key }); },
          onDelete: function () { lesson.activities.splice(ai, 1); save(true); },
        }));
      });
      (lesson.quiz_questions || []).forEach(function (question, qi) {
        sub.appendChild(treeNode({
          kind: "quiz",
          label: (question.question || "Question").slice(0, 46),
          indent: 1,
          selected: sel.kind === "question" && sel.questionId === question.id,
          draggable: true,
          drag: { type: "question", home: sel.key, qi: qi },
          onSelect: function () { select({ kind: "question", questionId: question.id }); },
          onDelete: function () { lesson.quiz_questions.splice(qi, 1); save(true); },
        }));
      });
      box.appendChild(sub);
    }

    if (sel.kind === "final") {
      var subF = document.createElement("div");
      subF.className = "tree";
      finalQuestions.forEach(function (question, qi) {
        subF.appendChild(treeNode({
          kind: "quiz",
          label: (question.question || "Question").slice(0, 46),
          indent: 1,
          selected: sel.kind === "question" && sel.questionId === question.id,
          draggable: true,
          drag: { type: "question", home: "final", qi: qi },
          onSelect: function () { select({ kind: "question", questionId: question.id }); },
          onDelete: function () { finalQuestions.splice(qi, 1); save(true); },
        }));
      });
      box.appendChild(subF);
    }
  }

  /* ================= template palette ================= */

  var TEMPLATES = [
    { id: "text", icon: "📝", name: "Text block", note: "A paragraph of learner-facing content." },
    { id: "image", icon: "🖼️", name: "Image block", note: "Text with an image (upload or URL)." },
    { id: "video", icon: "🎬", name: "Video block", note: "Text with a YouTube/Vimeo/Loom or mp4 video." },
    { id: "flashcards", icon: "🃏", name: "Flashcards", note: "Flip cards for terms and definitions." },
    { id: "matching", icon: "🔗", name: "Matching", note: "Match prompts to their answers." },
    { id: "accordion", icon: "📂", name: "Accordion", note: "Expandable review sections." },
    { id: "decision", icon: "🌿", name: "Decision scenario", note: "One scene with best/risk choices." },
    { id: "branching", icon: "🎭", name: "Branching character scene", note: "Persona-driven multi-scene dialogue." },
    { id: "timeline", icon: "📅", name: "Timeline", note: "Ordered steps with detail." },
    { id: "mcq", icon: "❓", name: "Quiz question", note: "MCQ with feedback (lesson or final)." },
  ];

  function templatePayload(templateId) {
    switch (templateId) {
      case "text":
        return { target: "block", value: { id: uid("cb"), type: "explanation", text: "Write the learner-facing explanation here." } };
      case "image":
        return { target: "block", value: { id: uid("cb"), type: "example", text: "Describe what the image shows.", media: { kind: "image", src: "", alt: "", caption: "" } } };
      case "video":
        return { target: "block", value: { id: uid("cb"), type: "example", text: "Introduce the video.", media: { kind: "video", src: "", caption: "Watch the walkthrough" } } };
      case "flashcards":
        return { target: "activity", value: { activity_id: uid("act"), activity_type: "flashcards", title: "Key terms", objective: "Flip each card and say the answer first.", items: [{ front: "Term", back: "Definition" }] } };
      case "matching":
        return { target: "activity", value: { activity_id: uid("act"), activity_type: "matching", title: "Match the pairs", objective: "Match each prompt to its answer.", items: [{ prompt: "Prompt", match: "Answer" }] } };
      case "accordion":
        return { target: "activity", value: { activity_id: uid("act"), activity_type: "accordion", title: "Review points", objective: "Open each section.", items: [{ title: "Point one", detail: "Detail for point one." }] } };
      case "decision":
        return { target: "activity", value: { activity_id: uid("act"), activity_type: "scenario_decision_tree", title: "Choose the best response", objective: "Pick the strongest action.", items: [{ scenario: "Describe the situation…", choices: [{ label: "Best action", result: "best", feedback: "Why this is right." }, { label: "Risky action", result: "risk", feedback: "Why this backfires." }] }] } };
      case "branching":
        return { target: "activity", value: { activity_id: uid("act"), activity_type: "branching_scenario", title: "Conversation scene", objective: "Lead the conversation.", persona: { name: "Alex", role: "Stakeholder" }, items: [{ scenario: "Alex opens with…", choices: [{ label: "Strong reply", result: "best", feedback: "Great choice." }, { label: "Weak reply", result: "risk", feedback: "This loses trust." }] }] } };
      case "timeline":
        return { target: "activity", value: { activity_id: uid("act"), activity_type: "timeline", title: "The steps", objective: "Walk the steps in order.", items: [{ label: "Step 1", detail: "What happens first." }] } };
      case "mcq":
        return { target: "question", value: { id: uid("q"), type: "mcq", objective_ids: [], question: "Write the question here?", options: ["Correct answer", "Distractor"], correct_answers: ["Correct answer"], explanation: "Explain why the correct answer is right." } };
      default:
        return null;
    }
  }

  function insertTemplate(templateId, target) {
    var payload = templatePayload(templateId);
    if (!payload) return;
    var key = (target && target.key) || (state.selected.kind === "lesson" ? state.selected.key : state.selected.key);
    if (payload.target === "question" && state.selected.kind === "final") {
      state.course.final_assessment = state.course.final_assessment || { id: "assessment_final", title: "Final Check", passing_score: 80, questions: [] };
      state.course.final_assessment.questions.push(payload.value);
    } else {
      if (!key) { toast("Select a lesson first (Structure tab), then insert."); return; }
      var found = findLesson(key);
      if (!found) { toast("Select a lesson first."); return; }
      if (payload.target === "block") (found.lesson.content_blocks = found.lesson.content_blocks || []).push(payload.value);
      if (payload.target === "activity") (found.lesson.activities = found.lesson.activities || []).push(payload.value);
      if (payload.target === "question") (found.lesson.quiz_questions = found.lesson.quiz_questions || []).push(payload.value);
    }
    save(true);
    toast("Inserted — now edit it in the inspector or on the canvas.");
  }

  function renderPalette() {
    var box = $("tab-templates");
    box.innerHTML = '<p class="palette-note">Select a lesson in the Structure tab, then insert — or drag a card onto a lesson.</p>';
    var palette = document.createElement("div");
    palette.className = "palette";
    TEMPLATES.forEach(function (template) {
      var card = document.createElement("div");
      card.className = "palette-card";
      card.draggable = true;
      card.innerHTML =
        '<span class="palette-icon">' + template.icon + "</span>" +
        "<div><strong>" + template.name + "</strong><span>" + template.note + "</span></div>" +
        "<button type=\"button\">Insert</button>";
      card.querySelector("button").addEventListener("click", function () { insertTemplate(template.id, null); });
      card.addEventListener("dragstart", function (event) {
        event.dataTransfer.setData("text/plain", JSON.stringify({ type: "template", template: template.id }));
      });
      palette.appendChild(card);
    });
    box.appendChild(palette);
  }

  /* ================= inspector ================= */

  function field(labelText, inputEl) {
    var wrap = document.createElement("div");
    wrap.className = "field";
    var label = document.createElement("label");
    label.textContent = labelText;
    wrap.appendChild(label);
    wrap.appendChild(inputEl);
    return wrap;
  }

  function textInput(value, onChange, type) {
    var input = document.createElement(type === "area" ? "textarea" : "input");
    if (type !== "area") input.type = type || "text";
    input.value = value == null ? "" : value;
    input.addEventListener("change", function () { onChange(type === "number" ? Number(input.value) : input.value); });
    return input;
  }

  function selectInput(value, options, onChange) {
    var input = document.createElement("select");
    options.forEach(function (option) {
      var el = document.createElement("option");
      el.value = option;
      el.textContent = option;
      if (option === value) el.selected = true;
      input.appendChild(el);
    });
    input.addEventListener("change", function () { onChange(input.value); });
    return input;
  }

  function switchRow(labelText, value, onChange) {
    var row = document.createElement("div");
    row.className = "switch-row";
    row.innerHTML = "<span>" + labelText + "</span>";
    var wrap = document.createElement("label");
    wrap.className = "switch";
    var input = document.createElement("input");
    input.type = "checkbox";
    input.checked = Boolean(value);
    input.addEventListener("change", function () { onChange(input.checked); });
    wrap.appendChild(input);
    wrap.appendChild(document.createElement("i"));
    row.appendChild(wrap);
    return row;
  }

  function sectionLabel(text) {
    var el = document.createElement("div");
    el.className = "section-label";
    el.textContent = text;
    return el;
  }

  function itemListEditor(items, fields, onChanged, addLabel, blank) {
    var wrap = document.createElement("div");
    wrap.style.display = "grid";
    wrap.style.gap = "8px";
    items.forEach(function (item, index) {
      var row = document.createElement("div");
      row.className = "item-row";
      var head = document.createElement("div");
      head.className = "item-row-head";
      head.innerHTML = "<span>#" + (index + 1) + "</span><button type=\"button\" title=\"Remove\">✕</button>";
      head.querySelector("button").addEventListener("click", function () {
        items.splice(index, 1);
        onChanged();
      });
      row.appendChild(head);
      fields.forEach(function (fieldDef) {
        var input = textInput(item[fieldDef.key], function (value) {
          item[fieldDef.key] = value;
          onChanged(false);
        }, fieldDef.area ? "area" : "text");
        input.placeholder = fieldDef.label;
        row.appendChild(input);
      });
      wrap.appendChild(row);
    });
    var add = document.createElement("button");
    add.className = "add-item";
    add.type = "button";
    add.textContent = addLabel || "+ Add item";
    add.addEventListener("click", function () {
      items.push(clone(blank));
      onChanged();
    });
    wrap.appendChild(add);
    return wrap;
  }

  function mediaEditor(owner) {
    var wrap = document.createElement("div");
    wrap.style.display = "grid";
    wrap.style.gap = "10px";
    var media = owner.media || null;

    function set(prop, value) {
      owner.media = owner.media || { kind: "image", src: "" };
      owner.media[prop] = value;
      save(true);
    }

    wrap.appendChild(field("Media type", selectInput(media ? media.kind : "none", ["none", "image", "video", "link"], function (value) {
      if (value === "none") { delete owner.media; save(true); return; }
      set("kind", value);
    })));
    if (media && media.kind) {
      wrap.appendChild(field("URL (https… or assets/media/…)", textInput(media.src || "", function (value) { set("src", value); }, "url")));
      wrap.appendChild(field("Caption", textInput(media.caption || "", function (value) { set("caption", value); })));
      wrap.appendChild(field("Alt text", textInput(media.alt || "", function (value) { set("alt", value); })));
      if (media.kind === "image") {
        if (media.src) {
          var preview = document.createElement("div");
          preview.className = "media-preview";
          preview.innerHTML = '<img src="/course/' + state.session + "/" + escapeHtml(media.src) + '" alt="">';
          wrap.appendChild(preview);
        }
        var upload = document.createElement("label");
        upload.className = "ghost file-button";
        upload.innerHTML = 'Upload image<input type="file" accept="image/*">';
        upload.querySelector("input").addEventListener("change", function (event) {
          var file = event.target.files[0];
          if (!file) return;
          var reader = new FileReader();
          reader.onload = function () {
            fetch("/api/media/" + state.session, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ filename: file.name, content_base64: reader.result }),
            })
              .then(function (res) { return res.json(); })
              .then(function (data) {
                if (!data.ok) throw new Error(data.error || "Upload failed");
                set("src", data.src);
                toast("Image uploaded and attached.");
              })
              .catch(function (error) { toast(error.message); });
          };
          reader.readAsDataURL(file);
        });
        wrap.appendChild(upload);
      }
    }
    return wrap;
  }

  function questionEditor(question) {
    var box = document.createElement("div");
    box.style.display = "grid";
    box.style.gap = "12px";
    box.appendChild(field("Question", textInput(question.question, function (value) { question.question = value; save(true); }, "area")));
    box.appendChild(sectionLabel("Options — tick the correct one"));
    var list = document.createElement("div");
    list.style.display = "grid";
    list.style.gap = "8px";
    (question.options || []).forEach(function (option, index) {
      var row = document.createElement("div");
      row.className = "option-row";
      var radio = document.createElement("input");
      radio.type = "radio";
      radio.name = "correct-" + question.id;
      radio.checked = (question.correct_answers || []).indexOf(option) >= 0;
      radio.addEventListener("change", function () {
        question.correct_answers = [question.options[index]];
        save(true);
      });
      var text = textInput(option, function (value) {
        var wasCorrect = (question.correct_answers || []).indexOf(question.options[index]) >= 0;
        question.options[index] = value;
        if (wasCorrect) question.correct_answers = [value];
        save(true);
      });
      var del = document.createElement("button");
      del.className = "del";
      del.type = "button";
      del.textContent = "✕";
      del.style.background = "none";
      del.style.border = "0";
      del.style.color = "var(--muted)";
      del.style.cursor = "pointer";
      del.addEventListener("click", function () {
        question.options.splice(index, 1);
        question.correct_answers = (question.correct_answers || []).filter(function (a) { return question.options.indexOf(a) >= 0; });
        save(true);
      });
      row.appendChild(radio);
      row.appendChild(text);
      row.appendChild(del);
      list.appendChild(row);
    });
    var add = document.createElement("button");
    add.className = "add-item";
    add.type = "button";
    add.textContent = "+ Add option";
    add.addEventListener("click", function () {
      (question.options = question.options || []).push("New option");
      save(true);
    });
    list.appendChild(add);
    box.appendChild(list);
    box.appendChild(field("Explanation / feedback", textInput(question.explanation, function (value) { question.explanation = value; save(true); }, "area")));
    return box;
  }

  function activityEditor(activity) {
    var box = document.createElement("div");
    box.style.display = "grid";
    box.style.gap = "12px";
    var type = String(activity.activity_type || activity.type || "");
    box.appendChild(field("Title", textInput(activity.title, function (value) { activity.title = value; save(true); })));
    box.appendChild(field("Instructions / objective", textInput(activity.objective || activity.instructions, function (value) { activity.objective = value; save(true); }, "area")));

    var refresh = function () { save(true); };
    if (type.indexOf("flashcard") >= 0) {
      box.appendChild(sectionLabel("Cards"));
      box.appendChild(itemListEditor(activity.items = activity.items || [], [
        { key: "front", label: "Front (term)" },
        { key: "back", label: "Back (answer)", area: true },
      ], refresh, "+ Add card", { front: "", back: "" }));
    } else if (type.indexOf("matching") >= 0) {
      box.appendChild(sectionLabel("Pairs"));
      box.appendChild(itemListEditor(activity.items = activity.items || [], [
        { key: "prompt", label: "Prompt" },
        { key: "match", label: "Match" },
      ], refresh, "+ Add pair", { prompt: "", match: "" }));
    } else if (type.indexOf("accordion") >= 0 || type.indexOf("tabs") >= 0) {
      box.appendChild(sectionLabel("Sections"));
      box.appendChild(itemListEditor(activity.items = activity.items || [], [
        { key: "title", label: "Title" },
        { key: "detail", label: "Detail", area: true },
      ], refresh, "+ Add section", { title: "", detail: "" }));
    } else if (type.indexOf("timeline") >= 0) {
      box.appendChild(sectionLabel("Steps"));
      box.appendChild(itemListEditor(activity.items = activity.items || [], [
        { key: "label", label: "Step label" },
        { key: "detail", label: "Detail", area: true },
      ], refresh, "+ Add step", { label: "", detail: "" }));
    } else if (type.indexOf("branching") >= 0 || type.indexOf("scenario") >= 0 || type.indexOf("decision") >= 0) {
      if (type.indexOf("branching") >= 0) {
        activity.persona = activity.persona || { name: "Alex", role: "Stakeholder" };
        box.appendChild(sectionLabel("Character"));
        box.appendChild(field("Name", textInput(activity.persona.name, function (value) { activity.persona.name = value; save(true); })));
        box.appendChild(field("Role", textInput(activity.persona.role, function (value) { activity.persona.role = value; save(true); })));
      }
      box.appendChild(sectionLabel("Scenes"));
      (activity.items = activity.items || []).forEach(function (item, index) {
        var scene = document.createElement("div");
        scene.className = "item-row";
        var head = document.createElement("div");
        head.className = "item-row-head";
        head.innerHTML = "<span>Scene " + (index + 1) + "</span><button type=\"button\">✕</button>";
        head.querySelector("button").addEventListener("click", function () { activity.items.splice(index, 1); save(true); });
        scene.appendChild(head);
        var scenario = textInput(item.scenario, function (value) { item.scenario = value; save(true); }, "area");
        scenario.placeholder = "Scenario text";
        scene.appendChild(scenario);
        (item.choices = item.choices || []).forEach(function (choice, choiceIndex) {
          var row = document.createElement("div");
          row.className = "option-row";
          var best = document.createElement("input");
          best.type = "radio";
          best.name = "best-" + (activity.activity_id || "a") + "-" + index;
          best.title = "Best choice";
          best.checked = choice.result === "best";
          best.addEventListener("change", function () {
            item.choices.forEach(function (c) { c.result = "risk"; });
            choice.result = "best";
            save(true);
          });
          var label = textInput(choice.label, function (value) { choice.label = value; save(true); });
          label.placeholder = "Choice label";
          var del = document.createElement("button");
          del.type = "button";
          del.textContent = "✕";
          del.style.cssText = "background:none;border:0;color:var(--muted);cursor:pointer";
          del.addEventListener("click", function () { item.choices.splice(choiceIndex, 1); save(true); });
          row.appendChild(best);
          row.appendChild(label);
          row.appendChild(del);
          scene.appendChild(row);
          var feedback = textInput(choice.feedback, function (value) { choice.feedback = value; save(true); });
          feedback.placeholder = "Feedback for this choice";
          scene.appendChild(feedback);
        });
        var addChoice = document.createElement("button");
        addChoice.className = "add-item";
        addChoice.type = "button";
        addChoice.textContent = "+ Add choice";
        addChoice.addEventListener("click", function () {
          item.choices.push({ label: "New choice", result: "risk", feedback: "" });
          save(true);
        });
        scene.appendChild(addChoice);
        box.appendChild(scene);
      });
      var addScene = document.createElement("button");
      addScene.className = "add-item";
      addScene.type = "button";
      addScene.textContent = "+ Add scene";
      addScene.addEventListener("click", function () {
        activity.items.push({ scenario: "New scene…", choices: [{ label: "Best", result: "best", feedback: "" }, { label: "Risky", result: "risk", feedback: "" }] });
        save(true);
      });
      box.appendChild(addScene);
    } else {
      box.appendChild(sectionLabel("Items (generic)"));
      box.appendChild(itemListEditor(activity.items = activity.items || [], [
        { key: "prompt", label: "Prompt" },
        { key: "detail", label: "Detail", area: true },
      ], refresh, "+ Add item", { prompt: "", detail: "" }));
    }
    return box;
  }

  function renderInspector() {
    var box = $("inspector");
    var title = $("inspector-title");
    if (!state.course) return;
    box.innerHTML = "";
    var sel = state.selected;
    var course = state.course;

    if (sel.kind === "course") {
      title.textContent = "Course";
      box.appendChild(field("Title", textInput(course.course_title, function (value) { course.course_title = value; save(true); })));
      box.appendChild(field("Theme", selectInput(course.theme || "studio", ["studio", "compliance", "academy"], function (value) { course.theme = value; save(true); })));
      box.appendChild(sectionLabel("Game options"));
      var options = course.game_options = course.game_options || {};
      [
        ["locked_progression", "Locked lesson progression"],
        ["streaks", "Streak multipliers"],
        ["timed_challenges", "Timed quiz questions"],
        ["branching_scenarios", "Branching character scenes"],
        ["celebration", "Confetti celebration"],
        ["certificate", "Completion certificate"],
      ].forEach(function (pair) {
        box.appendChild(switchRow(pair[1], options[pair[0]] !== false && (pair[0] !== "timed_challenges" || options[pair[0]] === true), function (value) {
          options[pair[0]] = value;
          save(true);
        }));
      });
      box.appendChild(field("Timer seconds", textInput(options.timer_seconds || 20, function (value) { options.timer_seconds = Number(value) || 20; save(true); }, "number")));
      return;
    }

    if (sel.kind === "module") {
      var module = course.modules[sel.mi];
      if (!module) return;
      title.textContent = "Module";
      box.appendChild(field("Title", textInput(module.title, function (value) { module.title = value; save(true); })));
      box.appendChild(field("Duration (minutes)", textInput(module.duration_minutes, function (value) { module.duration_minutes = Number(value) || 10; save(true); }, "number")));
      var addLesson = document.createElement("button");
      addLesson.className = "add-item";
      addLesson.textContent = "+ Add lesson";
      addLesson.addEventListener("click", function () {
        (module.lessons = module.lessons || []).push({
          id: uid("lesson"),
          title: "New lesson",
          duration_minutes: 8,
          objective_ids: module.objective_ids || [],
          objective: "Describe what the learner will be able to do.",
          content_blocks: [{ id: uid("cb"), type: "intro", text: "Open with why this lesson matters." }],
          activities: [],
          quiz_questions: [],
        });
        save(true);
      });
      box.appendChild(addLesson);
      return;
    }

    if (sel.kind === "lesson") {
      var foundLesson = findLesson(sel.key);
      if (!foundLesson) return;
      title.textContent = "Lesson";
      var lesson = foundLesson.lesson;
      box.appendChild(field("Title", textInput(lesson.title, function (value) { lesson.title = value; save(true); })));
      box.appendChild(field("Objective", textInput(lesson.objective, function (value) { lesson.objective = value; save(true); }, "area")));
      box.appendChild(field("Duration (minutes)", textInput(lesson.duration_minutes, function (value) { lesson.duration_minutes = Number(value) || 8; save(true); }, "number")));
      var note = document.createElement("p");
      note.className = "palette-note";
      note.textContent = "Blocks, activities, and questions inside this lesson are listed in the Structure tab. Use the Insert tab to add more.";
      box.appendChild(note);
      return;
    }

    if (sel.kind === "block") {
      var foundBlock = findBlock(sel.cbId);
      if (!foundBlock) { box.innerHTML = '<p class="inspector-empty">Block not found.</p>'; return; }
      title.textContent = "Content block";
      var block = foundBlock.block;
      box.appendChild(field("Type", selectInput(block.type || "explanation",
        ["intro", "explanation", "example", "scenario", "practice", "summary", "callout", "warning", "checklist", "reflection"],
        function (value) { block.type = value; save(true); })));
      box.appendChild(field("Text", textInput(block.text, function (value) { block.text = value; save(true); }, "area")));
      box.appendChild(sectionLabel("Media"));
      box.appendChild(mediaEditor(block));
      return;
    }

    if (sel.kind === "activity") {
      var foundActivity = findActivity(sel.activityId);
      if (!foundActivity) { box.innerHTML = '<p class="inspector-empty">Activity not found.</p>'; return; }
      title.textContent = "Activity — " + String(foundActivity.activity.activity_type || "").replace(/_/g, " ");
      box.appendChild(activityEditor(foundActivity.activity));
      return;
    }

    if (sel.kind === "question") {
      var foundQuestion = findQuestion(sel.questionId);
      if (!foundQuestion) { box.innerHTML = '<p class="inspector-empty">Question not found.</p>'; return; }
      title.textContent = "Quiz question";
      box.appendChild(questionEditor(foundQuestion.question));
      return;
    }

    if (sel.kind === "final") {
      title.textContent = "Final assessment";
      var final = course.final_assessment = course.final_assessment || { id: "assessment_final", title: "Final Check", passing_score: 80, questions: [] };
      box.appendChild(field("Title", textInput(final.title, function (value) { final.title = value; save(true); })));
      box.appendChild(field("Passing score (%)", textInput(final.passing_score, function (value) { final.passing_score = Number(value) || 80; save(true); }, "number")));
      var addQ = document.createElement("button");
      addQ.className = "add-item";
      addQ.textContent = "+ Add question";
      addQ.addEventListener("click", function () { insertTemplate("mcq", null); });
      box.appendChild(addQ);
      return;
    }

    box.innerHTML = '<p class="inspector-empty">Select something in the structure tree or click it on the canvas.</p>';
  }

  /* ================= canvas bridge (same-origin) ================= */

  var HIGHLIGHT_CSS =
    "[data-cb-id], [data-activity-id], [data-question-id], [data-lesson-id] { transition: outline-color .15s ease; outline: 2px solid transparent; outline-offset: 3px; }" +
    ".studio-hover { outline-color: rgba(56,189,248,.8) !important; cursor: pointer; }" +
    ".studio-selected { outline-color: rgba(45,212,191,.95) !important; }" +
    ".studio-editing { outline-color: #f59e0b !important; background: rgba(245,158,11,.06); }";

  function canvasDoc() {
    try { return canvas.contentDocument; } catch (e) { return null; }
  }

  function editableTargetOf(node) {
    if (!node || !node.closest) return null;
    return node.closest("[data-cb-id], [data-activity-id], [data-question-id], [data-lesson-id]");
  }

  function selectFromCanvas(target) {
    if (target.dataset.cbId) {
      var foundBlock = findBlock(target.dataset.cbId);
      if (foundBlock) select({ kind: "block", cbId: target.dataset.cbId, key: foundBlock.row.mi + ":" + foundBlock.row.li });
    } else if (target.dataset.activityId) {
      select({ kind: "activity", activityId: target.dataset.activityId });
    } else if (target.dataset.questionId) {
      select({ kind: "question", questionId: target.dataset.questionId });
    } else if (target.dataset.lessonId) {
      var parts = target.dataset.lessonId.match(/module-(\d+)-lesson-(\d+)/);
      if (parts) select({ kind: "lesson", key: (Number(parts[1]) - 1) + ":" + (Number(parts[2]) - 1) });
    }
  }

  function startInlineEdit(target) {
    var doc = canvasDoc();
    if (!doc) return;
    var cbId = target.dataset.cbId;
    var textHost = target.querySelector(".sp-body") || target;
    var paragraphs = textHost.querySelectorAll("p");
    var host = paragraphs.length ? textHost : target;
    if (!cbId) return;
    var found = findBlock(cbId);
    if (!found) return;
    target.classList.add("studio-editing");
    host.contentEditable = "true";
    host.focus();
    var finish = function () {
      host.contentEditable = "false";
      target.classList.remove("studio-editing");
      var text = Array.prototype.map
        .call(host.querySelectorAll("p"), function (p) { return p.textContent.trim(); })
        .filter(Boolean)
        .join(" ") || host.textContent.trim();
      if (text && text !== found.block.text) {
        found.block.text = text;
        save(false); // DOM already shows the edit — no reload needed
        toast("Text updated.");
      }
      host.removeEventListener("blur", finish);
    };
    host.addEventListener("blur", finish);
  }

  function bindCanvas() {
    var doc = canvasDoc();
    if (!doc || !doc.body) return;
    if (doc.getElementById("studio-css")) return;
    var style = doc.createElement("style");
    style.id = "studio-css";
    style.textContent = HIGHLIGHT_CSS;
    doc.head.appendChild(style);

    var hovered = null;
    doc.addEventListener("mousemove", function (event) {
      var target = editableTargetOf(event.target);
      if (hovered && hovered !== target) hovered.classList.remove("studio-hover");
      if (target) target.classList.add("studio-hover");
      hovered = target;
    });
    doc.addEventListener("click", function (event) {
      var target = editableTargetOf(event.target);
      if (!target) return;
      doc.querySelectorAll(".studio-selected").forEach(function (el) { el.classList.remove("studio-selected"); });
      target.classList.add("studio-selected");
      selectFromCanvas(target);
    }, true);
    doc.addEventListener("dblclick", function (event) {
      var target = editableTargetOf(event.target);
      if (target && target.dataset.cbId) {
        event.preventDefault();
        event.stopPropagation();
        startInlineEdit(target);
      }
    }, true);
  }

  canvas.addEventListener("load", function () {
    bindCanvas();
    // The slide player re-renders its stage; re-bind cheaply on DOM changes.
    var doc = canvasDoc();
    if (doc && doc.body && window.MutationObserver) {
      new MutationObserver(function () { bindCanvas(); }).observe(doc.body, { childList: true, subtree: false });
    }
  });

  /* ================= wiring ================= */

  document.querySelectorAll(".tab").forEach(function (tab) {
    tab.addEventListener("click", function () {
      document.querySelectorAll(".tab").forEach(function (t) { t.classList.remove("active"); });
      tab.classList.add("active");
      $("tab-structure").hidden = tab.dataset.tab !== "structure";
      $("tab-templates").hidden = tab.dataset.tab !== "templates";
      $("tab-review").hidden = tab.dataset.tab !== "review";
      if (tab.dataset.tab === "review") renderReview();
    });
  });

  ["zip-input", "zip-input-empty"].forEach(function (id) {
    var input = $(id);
    if (input) input.addEventListener("change", function (event) {
      if (event.target.files[0]) importZip(event.target.files[0]);
      event.target.value = "";
    });
  });

  function openSession(sid, course, version) {
    state.session = sid;
    state.course = course;
    state.version = version || 1;
    state.conflicted = false;
    $("conflict-banner").hidden = true;
    setSaveStatus("Saved · revision " + state.version);
    if (window.BroadcastChannel) {
      if (state.channel) state.channel.close();
      state.channel = new BroadcastChannel("course-studio:" + sid);
      state.channel.onmessage = function (event) {
        if (event.data && event.data.version > state.version) {
          state.conflicted = true;
          $("conflict-banner").hidden = false;
          setSaveStatus("Newer revision in another tab");
        }
      };
    }
    state.history = [];
    state.historyIndex = -1;
    pushHistory();
    $("empty-state").hidden = true;
    $("layout").hidden = false;
    $("btn-export").disabled = false;
    $("course-name").textContent = course.course_title || "Untitled course";
    canvas.src = "/course/" + sid + "/index.html";
    renderTree();
    renderPalette();
    renderReview();
    select({ kind: "course" });
  }

  // Deep link: /?session=<id> re-opens an existing workspace (used by the MCP flow).
  var params = new URLSearchParams(location.search);
  if (params.get("session")) {
    fetch("/api/course/" + params.get("session"))
      .then(function (res) { return res.json(); })
      .then(function (data) {
        if (data.course) openSession(data.session, data.course, data.version);
        else if (data.error === "session_expired") setSaveStatus("Session expired");
      })
      .catch(function () {});
  }

  $("btn-export").addEventListener("click", exportZip);
  $("new-course-form").addEventListener("submit", createNewCourse);
  $("btn-reload").addEventListener("click", reloadCanvas);
  $("btn-undo").addEventListener("click", undo);
  $("btn-redo").addEventListener("click", redo);
  document.addEventListener("keydown", function (event) {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "z" && !event.shiftKey) { event.preventDefault(); undo(); }
    if ((event.ctrlKey || event.metaKey) && (event.key.toLowerCase() === "y" || (event.shiftKey && event.key.toLowerCase() === "z"))) { event.preventDefault(); redo(); }
  });
  window.addEventListener("offline", function () { persistRecovery(); setSaveStatus("Offline · recovery saved"); });
  window.addEventListener("online", function () { setSaveStatus(state.conflicted ? "Conflict · reload required" : "Online · ready to save"); });
  window.addEventListener("beforeunload", function (event) { if (state.saving) { persistRecovery(); event.preventDefault(); event.returnValue = ""; } });
})();
