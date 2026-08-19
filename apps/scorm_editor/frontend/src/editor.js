/* Course Studio — WYSIWYG editor whose canvas IS the real course player.
   Same-origin iframe: the editor reads and decorates the player DOM directly. */
import { escapeHtml } from "./escape-html.js";
import { moveItem } from "./move-item.js";
import { moveBetweenLists } from "./move-between-lists.js";
import { sanitizeRichTextHtml, richTextToPlainText } from "./rich-text.js";
import { routeDroppedFile } from "./upload-route.js";

import { Editor } from "@tiptap/core";
import Document from "@tiptap/extension-document";
import Paragraph from "@tiptap/extension-paragraph";
import Text from "@tiptap/extension-text";
import Bold from "@tiptap/extension-bold";
import Italic from "@tiptap/extension-italic";
import Underline from "@tiptap/extension-underline";
import Link from "@tiptap/extension-link";
import BulletList from "@tiptap/extension-bullet-list";
import OrderedList from "@tiptap/extension-ordered-list";
import ListItem from "@tiptap/extension-list-item";

// Document/Paragraph/Text are Tiptap's required base nodes (every editor needs
// them). Everything else here is hand-picked to match, tag for tag, the
// server-side rich-text allowlist in src/course_mcp_server/html_sanitizer.py
// (ALLOWED_TAGS = strong/em/u/a/ul/ol/li) — deliberately NOT the full
// @tiptap/starter-kit, so this editor cannot produce formatting (headings,
// code blocks, blockquotes, images, tables, ...) the SCORM exporter doesn't
// know how to render.
var RICH_TEXT_EXTENSIONS = [
  Document,
  Paragraph,
  Text,
  Bold,
  Italic,
  Underline,
  Link.configure({ openOnClick: false, autolink: false, protocols: ["http", "https", "mailto"] }),
  BulletList,
  OrderedList,
  ListItem,
];

(function () {
  "use strict";

  /* ================= auth =================
     Course Studio now requires EDITOR_API_TOKEN on the server (see server.py
     _require_auth). The token is never hardcoded here: it comes from this page's
     own URL (?token=..., set by the MCP's open_in_studio deep link) or from a
     value the operator pastes in for local/manual use, and is then attached to
     every same-origin request this page makes — fetch() via header, iframe/img
     src via query param, since a browser navigation cannot carry a header. */
  var editorToken = (function () {
    var fromUrl = new URLSearchParams(window.location.search).get("token");
    if (fromUrl) {
      try { sessionStorage.setItem("course-studio-token", fromUrl); } catch (e) { /* ignore */ }
      return fromUrl;
    }
    try { return sessionStorage.getItem("course-studio-token") || ""; } catch (e) { return ""; }
  })();

  function withToken(url) {
    if (!editorToken) return url;
    return url + (url.indexOf("?") === -1 ? "?" : "&") + "token=" + encodeURIComponent(editorToken);
  }

  var nativeFetch = window.fetch.bind(window);
  window.fetch = function (input, init) {
    init = init || {};
    if (typeof input === "string" && input.charAt(0) === "/" && editorToken) {
      init = Object.assign({}, init);
      init.headers = Object.assign({}, init.headers, { Authorization: "Bearer " + editorToken });
    }
    return nativeFetch(input, init);
  };

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
      fetch("/api/accessibility/" + state.session).then(function (res) { return res.json(); }),
      fetch("/api/localization/" + state.session).then(function (res) { return res.json(); }),
      fetch("/api/generation/" + state.session).then(function (res) { return res.json(); }),
    ]).then(function (rows) {
      var revisions = rows[0].revisions || [];
      var collaboration = rows[1].collaboration || { comments: [], approvals: [], roles: {} };
      var accessibility = rows[2].report || { status: "pass", summary: { blockers: 0, warnings: 0 }, issues: [] };
      var localization = rows[3].localization || { base_locale: "en", locales: {} };
      var generation = rows[4].generation || { status: "not_started", progress: 0, modules: [] };
      box.replaceChildren();
      var heading = document.createElement("h3"); heading.textContent = "Review & approval"; box.appendChild(heading);
      var form = document.createElement("form"); form.className = "review-form";
      var input = document.createElement("textarea"); input.setAttribute("aria-label", "New review comment"); input.placeholder = "Add a review comment";
      var submit = document.createElement("button"); submit.className = "primary"; submit.type = "submit"; submit.textContent = "Comment";
      form.append(input, submit); form.addEventListener("submit", function (event) { event.preventDefault(); postCollaboration("comment", { message: input.value, target: state.selected.kind || "course" }).catch(function (error) { toast(error.message); }); }); box.appendChild(form);
      var actions = document.createElement("div"); actions.className = "review-actions";
      [["approved", "Approve revision"], ["changes_requested", "Request changes"]].forEach(function (choice) { var button=document.createElement("button"); button.className="ghost"; button.textContent=choice[1]; button.addEventListener("click", function () { postCollaboration("approval", { decision: choice[0] }).catch(function (error) { toast(error.message); }); }); actions.appendChild(button); }); box.appendChild(actions);
      var generationTitle=document.createElement("h4");generationTitle.textContent="Background generation";box.appendChild(generationTitle);
      var generationStatus=document.createElement("p");generationStatus.className="review-row";generationStatus.setAttribute("role","status");generationStatus.textContent=generation.status.replace("_"," ")+" / "+generation.progress+"% / "+(generation.modules||[]).filter(function(item){return item.status==="succeeded";}).length+" of "+(generation.modules||[]).length+" modules";box.appendChild(generationStatus);
      var generationActions=document.createElement("div");generationActions.className="review-actions";
      var generationButton=document.createElement("button");generationButton.className="primary";generationButton.textContent=generation.status==="failed"||generation.status==="cancelled"?"Retry incomplete modules":"Generate approved outline";generationButton.disabled=generation.status==="queued"||generation.status==="running";generationButton.addEventListener("click",function(){fetch("/api/generation/"+state.session,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({action:"start"})}).then(function(res){return res.json();}).then(function(data){if(!data.ok)throw new Error(data.error||"Generation failed to start");renderReview();}).catch(function(error){toast(error.message);});});generationActions.appendChild(generationButton);
      var cancelButton=document.createElement("button");cancelButton.className="ghost";cancelButton.textContent="Cancel generation";cancelButton.disabled=generation.status!=="queued"&&generation.status!=="running";cancelButton.addEventListener("click",function(){fetch("/api/generation/"+state.session,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({action:"cancel"})}).then(function(res){return res.json();}).then(function(data){if(!data.ok)throw new Error(data.error||"Cancellation failed");renderReview();}).catch(function(error){toast(error.message);});});generationActions.appendChild(cancelButton);box.appendChild(generationActions);
      if(generation.status==="queued"||generation.status==="running"){setTimeout(renderReview,1000);}
      var revisionTitle=document.createElement("h4"); revisionTitle.textContent="Revision history"; box.appendChild(revisionTitle);
      revisions.forEach(function (revision) { var row=document.createElement("p"); row.className="review-row"; row.textContent="Revision "+revision.version+" · "+revision.reason+" · "+revision.actor; box.appendChild(row); });
      var commentTitle=document.createElement("h4"); commentTitle.textContent="Comments"; box.appendChild(commentTitle);
      collaboration.comments.forEach(function (comment) { var row=document.createElement("p"); row.className="review-row"; row.textContent=(comment.resolved?"Resolved · ":"")+comment.actor+": "+comment.message; box.appendChild(row); });
      var accessibilityTitle=document.createElement("h4"); accessibilityTitle.textContent="Accessibility report"; box.appendChild(accessibilityTitle);
      var accessibilitySummary=document.createElement("p"); accessibilitySummary.className="review-row"; accessibilitySummary.textContent=(accessibility.status === "pass" ? "Pass" : "Export blocked")+" / "+accessibility.summary.blockers+" blockers / "+accessibility.summary.warnings+" warnings"; box.appendChild(accessibilitySummary);
      accessibility.issues.forEach(function(item){var row=document.createElement("p");row.className="review-row";row.textContent=item.severity.toUpperCase()+" / "+item.path+" / "+item.message;box.appendChild(row);});
      var localizationTitle=document.createElement("h4"); localizationTitle.textContent="Localization"; box.appendChild(localizationTitle);
      var localeForm=document.createElement("form");localeForm.className="review-form";
      var localeInput=document.createElement("input");localeInput.required=true;localeInput.placeholder="Locale, e.g. es-MX";localeInput.setAttribute("aria-label","New locale");
      var localeButton=document.createElement("button");localeButton.className="primary";localeButton.type="submit";localeButton.textContent="Add locale";localeForm.append(localeInput,localeButton);
      localeForm.addEventListener("submit",function(event){event.preventDefault();fetch("/api/localization/"+state.session,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({action:"add_locale",locale:localeInput.value})}).then(function(res){return res.json();}).then(function(data){if(!data.ok)throw new Error(data.error||"Locale update failed");renderReview();}).catch(function(error){toast(error.message);});});box.appendChild(localeForm);
      Object.keys(localization.locales).sort().forEach(function(locale){var item=localization.locales[locale];var row=document.createElement("div");row.className="review-row";var label=document.createElement("span");label.textContent=locale+(locale===localization.base_locale?" / inherited source":" / "+Object.keys(item.overrides||{}).length+" overrides");var status=document.createElement("select");["source","draft","in_review","approved"].forEach(function(value){var option=document.createElement("option");option.value=value;option.textContent=value.replace("_"," ");option.selected=item.status===value;status.appendChild(option);});status.disabled=locale===localization.base_locale;status.setAttribute("aria-label",locale+" translation status");status.addEventListener("change",function(){fetch("/api/localization/"+state.session,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({action:"set_status",locale:locale,status:status.value})}).then(function(res){return res.json();}).then(function(data){if(!data.ok)throw new Error(data.error||"Translation status failed");renderReview();}).catch(function(error){toast(error.message);});});row.append(label,status);box.appendChild(row);if(locale!==localization.base_locale){var translationForm=document.createElement("form");translationForm.className="review-form";var pathInput=document.createElement("input");pathInput.placeholder="Field path, e.g. course_title";pathInput.required=true;pathInput.setAttribute("aria-label",locale+" field path");var valueInput=document.createElement("textarea");valueInput.placeholder="Translated value";valueInput.required=true;valueInput.setAttribute("aria-label",locale+" translated value");var translateButton=document.createElement("button");translateButton.type="submit";translateButton.className="ghost";translateButton.textContent="Save translation";translationForm.append(pathInput,valueInput,translateButton);translationForm.addEventListener("submit",function(event){event.preventDefault();fetch("/api/localization/"+state.session,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({action:"set_override",locale:locale,path:pathInput.value,value:valueInput.value})}).then(function(res){return res.json();}).then(function(data){if(!data.ok)throw new Error(data.error||"Translation save failed");renderReview();}).catch(function(error){toast(error.message);});});box.appendChild(translationForm);}});
    }).catch(function (error) { box.textContent = "Review data unavailable: " + error.message; });
  }

  function renderSources() {
    var box = $("tab-sources");
    if (!state.session || !box) return;
    fetch("/api/sources/" + state.session).then(function (res) { return res.json(); }).then(function (data) {
      box.replaceChildren();
      var heading=document.createElement("h3"); heading.textContent="Source intake"; box.appendChild(heading);
      function uploadSourceFile(file) {
        if (!file) return;
        var route = routeDroppedFile(file.name);
        if (route.kind !== "source") {
          toast("Unsupported file type for a source (" + (route.extension || "no extension") + "). Drop a PDF, DOCX, or PPTX.");
          return;
        }
        var reader = new FileReader();
        reader.onload = function () {
          fetch("/api/sources/" + state.session + "/upload", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ filename: file.name, content_base64: reader.result }),
          })
            .then(function (res) { return res.json(); })
            .then(function (result) {
              if (!result.ok) throw new Error(result.error || "Source upload failed");
              toast("Source extracted from " + file.name + ". Use its ID in lesson citations.");
              renderSources();
            })
            .catch(function (error) { toast(error.message); });
        };
        reader.readAsDataURL(file);
      }
      var dropZone = document.createElement("div");
      dropZone.className = "source-drop-zone";
      dropZone.textContent = "Drop a PDF, DOCX, or PPTX here to extract a page-anchored source automatically.";
      wireFileDropZone(dropZone, "drag-active", uploadSourceFile);
      box.appendChild(dropZone);
      var form=document.createElement("form"); form.className="review-form";
      var title=document.createElement("input"); title.required=true; title.placeholder="Source title"; title.setAttribute("aria-label","Source title");
      var text=document.createElement("textarea"); text.required=true; text.minLength=20; text.placeholder="Paste source text. It remains in the authoring workspace and is not added to the exported course."; text.setAttribute("aria-label","Source text");
      var button=document.createElement("button"); button.className="primary"; button.type="submit"; button.textContent="Add source";
      form.append(title,text,button); form.addEventListener("submit",function(event){event.preventDefault();fetch("/api/sources/"+state.session,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({title:title.value,text:text.value})}).then(function(res){return res.json();}).then(function(result){if(!result.ok)throw new Error(result.error||"Source intake failed");toast("Source added. Use its ID in lesson citations.");renderSources();}).catch(function(error){toast(error.message);});}); box.appendChild(form);
      (data.sources||[]).forEach(function(source){var row=document.createElement("p");row.className="review-row";var refCount=(source.references||[]).length;row.textContent=source.title+" · "+source.source_id+" · "+source.character_count+" characters"+(refCount?" · "+refCount+" reference"+(refCount===1?"":"s"):"");box.appendChild(row);});
    }).catch(function(error){box.textContent="Sources unavailable: "+error.message;});
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

  /* Keyboard reordering: focus a draggable tree node (Tab) and press
     Ctrl+ArrowUp / Ctrl+ArrowDown to move it one position within its own
     list (same-list only, matching mouse drag-and-drop — see handleDrop).
     Chosen over a separate "pick up" step (e.g. Space to grab, Escape to
     cancel) to keep the interaction a single, immediately-applied action:
     there is no pending/uncommitted move to lose track of, and it can't
     collide with Enter/Space (select) or Delete/Backspace (delete) since
     Ctrl is never held for those. Each press applies and autosaves right
     away, consistent with how this app already autosaves every edit
     (see save(true) below and elsewhere in this file). Escape/blur simply
     leaves the node — there is no in-progress state to cancel. */
  var pendingFocus = null; // { scope, index } — set right before a renderTree() triggered by a keyboard move, consumed after render to restore focus.

  function announceMove(text) {
    var region = $("tree-live-region");
    if (!region) return;
    // Clear-then-set on the next tick so the live region fires even when the
    // new text is identical to what's already there (e.g. two consecutive
    // "Already at the top of the list." announcements). setTimeout is used
    // instead of requestAnimationFrame because rAF callbacks are throttled to
    // near-never on a backgrounded/hidden tab, which would silently swallow
    // the announcement for a screen reader user who has switched tabs.
    region.textContent = "";
    window.setTimeout(function () { region.textContent = text; }, 0);
  }

  function treeNode(options) {
    var node = document.createElement("div");
    node.className = "tree-node" + (options.indent ? " tree-indent-" + options.indent : "") + (options.selected ? " selected" : "");
    node.tabIndex = 0;
    node.setAttribute("role", "button");
    node.setAttribute("aria-current", options.selected ? "true" : "false");
    if (options.reorder) {
      node.dataset.moveScope = options.reorder.scope;
      node.dataset.moveIndex = String(options.reorder.index);
    }
    node.innerHTML =
      (options.draggable ? '<span class="grip" title="Drag to reorder (or focus + Ctrl+Arrow keys)">⋮⋮</span>' : "") +
      '<span class="kind">' + options.kind + "</span>" +
      '<span class="label">' + escapeHtml(options.label) + "</span>" +
      (options.onDelete ? '<button class="del" title="Delete">✕</button>' : "");
    node.addEventListener("click", function (event) {
      if (event.target.classList.contains("del")) return;
      options.onSelect();
    });
    node.addEventListener("keydown", function (event) {
      if (event.key === "Enter" || event.key === " ") { event.preventDefault(); options.onSelect(); }
      if ((event.key === "Delete" || event.key === "Backspace") && options.onDelete) { event.preventDefault(); if (confirm("Delete '" + options.label + "'?")) options.onDelete(); }
      if (options.reorder && event.ctrlKey && (event.key === "ArrowUp" || event.key === "ArrowDown")) {
        event.preventDefault();
        var list = options.reorder.list;
        var from = options.reorder.index;
        var to = from + (event.key === "ArrowUp" ? -1 : 1);
        if (to < 0 || to >= list.length) {
          announceMove((event.key === "ArrowUp" ? "Already at the top" : "Already at the bottom") + " of the list.");
          return;
        }
        moveItem(list, from, to);
        // Don't call renderTree() here ourselves: save(true) already re-renders
        // the tree once its fetch resolves (see save()'s .then()), same as the
        // mouse-drag path in handleDrop. Rendering synchronously here too would
        // race a second render in right behind it and reliably lose focus (the
        // freshly-rendered node from this call gets thrown away and replaced
        // by save()'s render, which starts from a null pendingFocus).
        pendingFocus = { scope: options.reorder.scope, index: to };
        announceMove("Moved " + options.kind + " to position " + (to + 1) + " of " + list.length + ".");
        save(true);
      }
    });
    if (options.onDelete) {
      node.querySelector(".del").addEventListener("click", function () {
        if (confirm("Delete '" + options.label + "'?")) options.onDelete();
      });
    }
    if (options.draggable) {
      node.draggable = true;
      // dropPosition tracks which half of this node the pointer is currently
      // over ("before"/"after" the hovered item), so the drop-position
      // indicator (a thin line above or below the node, via the
      // .drop-before/.drop-after CSS classes) and handleDrop's target index
      // both reflect where the item will actually land, not just "on this
      // node somewhere". Kept on the closure (not recomputed from the DOM in
      // drop) so drop doesn't need a second getBoundingClientRect call.
      var dropPosition = null;
      node.addEventListener("dragstart", function (event) {
        node.classList.add("dragging");
        event.dataTransfer.setData("text/plain", JSON.stringify(options.drag));
        event.dataTransfer.effectAllowed = "move";
      });
      node.addEventListener("dragover", function (event) {
        event.preventDefault();
        var rect = node.getBoundingClientRect();
        var isAfter = event.clientY - rect.top > rect.height / 2;
        var next = isAfter ? "after" : "before";
        // Only touch classList when the half actually changes, so a dragover
        // stream (which can fire many times per second) doesn't force a
        // style recalc on every event — just on the rarer half-flip.
        if (next !== dropPosition) {
          dropPosition = next;
          node.classList.toggle("drop-before", next === "before");
          node.classList.toggle("drop-after", next === "after");
        }
      });
      node.addEventListener("dragleave", function () {
        dropPosition = null;
        node.classList.remove("drop-before", "drop-after");
      });
      node.addEventListener("drop", function (event) {
        event.preventDefault();
        var position = dropPosition;
        dropPosition = null;
        node.classList.remove("drop-before", "drop-after");
        var payload;
        try { payload = JSON.parse(event.dataTransfer.getData("text/plain")); } catch (e) { return; }
        handleDrop(payload, Object.assign({ position: position }, options.drag));
      });
      node.addEventListener("dragend", function () {
        // Hardening: dragover/dragleave don't reliably pair up (a drop outside
        // any valid target, or the browser cancelling the drag, can leave a
        // stray highlight behind). Always sweep on dragend so the tree never
        // gets stuck showing a drag-over/dragging state after the gesture ends.
        dropPosition = null;
        node.classList.remove("dragging");
        var tree = node.closest(".tree") ? node.closest(".tree").parentElement : document;
        (tree || document).querySelectorAll(".tree-node.drop-before, .tree-node.drop-after").forEach(function (n) {
          n.classList.remove("drop-before", "drop-after");
        });
      });
    }
    return node;
  }

  // Target-resolution design (P1-4): handleDrop now distinguishes three shapes
  // of drop instead of one:
  //  1. Same type, same list (e.g. lesson dropped on a lesson in its own
  //     module) — precise same-list reorder using the drop-position
  //     indicator (before/after the hovered node).
  //  2. Same type, different list (e.g. lesson dropped on a lesson belonging
  //     to another module; block dropped on a block in another lesson) —
  //     cross-list move to a precise position, via moveBetweenLists.
  //  3. Dropped on the *parent* node one level up (a lesson dropped on a
  //     module node; a block/activity/question dropped on a lesson node) —
  //     always an append to the end of that parent's list. This is how
  //     cross-list moves reach lessons/modules the tree isn't currently
  //     showing the contents of (Course Studio only ever renders one
  //     selected lesson's blocks/activities/questions at a time, so you
  //     can't drag a block directly onto a block that lives in a different,
  //     currently-collapsed lesson — dropping on the lesson row itself is
  //     the reachable equivalent).
  // moveBetweenLists handles both shapes 1 and 2 uniformly (including the
  // case where a "different list" target actually resolves to the same
  // array reference), so both are always routed through it rather than
  // through the old same-list-only moveItem.
  function handleDrop(source, target) {
    if (!source || !target) return;
    if (source.type === "template") { insertTemplate(source.template, target); return; }
    var c = state.course;
    var after = target.position === "after" ? 1 : 0;

    if (source.type === "module" && target.type === "module") {
      moveBetweenLists(c.modules, source.mi, c.modules, target.mi + after);
    } else if (source.type === "lesson" && target.type === "lesson") {
      var srcModule = c.modules[source.mi];
      var dstModule = c.modules[target.mi];
      if (!srcModule || !dstModule) return;
      moveBetweenLists(srcModule.lessons, source.li, dstModule.lessons, target.li + after);
    } else if (source.type === "lesson" && target.type === "module") {
      // Dropped on a module node itself: append to the end of that module's
      // lessons. There's no meaningful before/after half of a module node to
      // read a lesson position from, so this ignores `after`.
      var srcModule2 = c.modules[source.mi];
      var dstModule2 = c.modules[target.mi];
      if (!srcModule2 || !dstModule2) return;
      moveBetweenLists(srcModule2.lessons, source.li, dstModule2.lessons, dstModule2.lessons.length);
    } else if (source.type === "block" && target.type === "block") {
      var srcBlockLesson = findLesson(source.key);
      var dstBlockLesson = findLesson(target.key);
      if (!srcBlockLesson || !dstBlockLesson) return;
      moveBetweenLists(srcBlockLesson.lesson.content_blocks, source.bi, dstBlockLesson.lesson.content_blocks, target.bi + after);
    } else if (source.type === "block" && target.type === "lesson") {
      var srcBlockLesson2 = findLesson(source.key);
      var dstLessonForBlock = findLesson(target.mi + ":" + target.li);
      if (!srcBlockLesson2 || !dstLessonForBlock) return;
      moveBetweenLists(srcBlockLesson2.lesson.content_blocks, source.bi, dstLessonForBlock.lesson.content_blocks, dstLessonForBlock.lesson.content_blocks.length);
    } else if (source.type === "activity" && target.type === "activity") {
      var srcActLesson = findLesson(source.key);
      var dstActLesson = findLesson(target.key);
      if (!srcActLesson || !dstActLesson) return;
      moveBetweenLists(srcActLesson.lesson.activities, source.ai, dstActLesson.lesson.activities, target.ai + after);
    } else if (source.type === "activity" && target.type === "lesson") {
      var srcActLesson2 = findLesson(source.key);
      var dstLessonForAct = findLesson(target.mi + ":" + target.li);
      if (!srcActLesson2 || !dstLessonForAct) return;
      moveBetweenLists(srcActLesson2.lesson.activities, source.ai, dstLessonForAct.lesson.activities, dstLessonForAct.lesson.activities.length);
    } else if (source.type === "question" && target.type === "question") {
      // Final-assessment questions are a deliberately distinct scope from
      // lesson-embedded practice questions (different purpose: a summative
      // gate vs. in-lesson practice), so a drop is only honored when both
      // sides share the same home. This mismatch can't currently happen via
      // the mouse (the tree only ever renders one question list — a lesson's
      // or the final assessment's — at a time, so source and target are
      // always drawn from the same list), but the guard stays explicit
      // rather than relying on that UI accident.
      if (source.home !== target.home) return;
      var qHome = target.home === "final" ? c.final_assessment.questions : findLesson(target.home).lesson.quiz_questions;
      moveBetweenLists(qHome, source.qi, qHome, target.qi + after);
    } else if (source.type === "question" && target.type === "lesson") {
      // Same final-assessment boundary as above: a final-assessment question
      // dropped on a lesson node does NOT migrate into that lesson's quiz
      // questions. Only lesson-to-lesson question moves are allowed here.
      if (source.home === "final") return;
      var srcQuestionHome = findLesson(source.home);
      var dstLessonForQuestion = findLesson(target.mi + ":" + target.li);
      if (!srcQuestionHome || !dstLessonForQuestion) return;
      moveBetweenLists(srcQuestionHome.lesson.quiz_questions, source.qi, dstLessonForQuestion.lesson.quiz_questions, dstLessonForQuestion.lesson.quiz_questions.length);
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
        reorder: { scope: "module", index: mi, list: state.course.modules },
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
          reorder: { scope: "lesson:" + mi, index: li, list: module.lessons },
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
          reorder: { scope: "block:" + sel.key, index: bi, list: lesson.content_blocks },
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
          reorder: { scope: "activity:" + sel.key, index: ai, list: lesson.activities },
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
          reorder: { scope: "question:" + sel.key, index: qi, list: lesson.quiz_questions },
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
          reorder: { scope: "question:final", index: qi, list: finalQuestions },
          onSelect: function () { select({ kind: "question", questionId: question.id }); },
          onDelete: function () { finalQuestions.splice(qi, 1); save(true); },
        }));
      });
      box.appendChild(subF);
    }

    if (pendingFocus) {
      var focusTarget = box.querySelector(
        '[data-move-scope="' + pendingFocus.scope + '"][data-move-index="' + pendingFocus.index + '"]'
      );
      pendingFocus = null;
      if (focusTarget) focusTarget.focus();
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

  // Wires real OS drag-and-drop (as opposed to the app's own internal drag system used for
  // tree reordering and template insertion, which uses dataTransfer.setData("text/plain")
  // with a JSON payload -- see handleDrop/dragstart above) onto `el`. Calls onFile(file) with
  // the single dropped File on drop; toggles activeClass for hover feedback, mirroring the
  // `.drop-before`/`.drop-after` P1-4 indicator style rather than inventing a new visual
  // language (see editor.css).
  function wireFileDropZone(el, activeClass, onFile) {
    el.addEventListener("dragover", function (event) {
      event.preventDefault();
      event.dataTransfer.dropEffect = "copy";
      el.classList.add(activeClass);
    });
    el.addEventListener("dragleave", function () {
      el.classList.remove(activeClass);
    });
    el.addEventListener("drop", function (event) {
      event.preventDefault();
      el.classList.remove(activeClass);
      var file = event.dataTransfer && event.dataTransfer.files && event.dataTransfer.files[0];
      if (file) onFile(file);
    });
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
          preview.innerHTML = '<img src="' + escapeHtml(withToken("/course/" + state.session + "/" + media.src)) + '" alt="">';
          wrap.appendChild(preview);
        }
        function uploadMediaFile(file) {
          if (!file) return;
          var route = routeDroppedFile(file.name);
          if (route.kind && route.kind !== "media") {
            toast("That file looks like a source document (" + route.extension + "). Drop it on the Sources tab instead.");
            return;
          }
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
        }
        var upload = document.createElement("label");
        upload.className = "ghost file-button";
        upload.innerHTML = 'Upload or drop image<input type="file" accept="image/*">';
        upload.querySelector("input").addEventListener("change", function (event) {
          uploadMediaFile(event.target.files[0]);
        });
        wireFileDropZone(upload, "drag-active", uploadMediaFile);
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
      box.appendChild(sectionLabel("Brand kit"));
      var branding = course.branding = course.branding || {};
      box.appendChild(field("Organization", textInput(branding.organization || "", function (value) { branding.organization = value; save(true); })));
      box.appendChild(field("Logo URL", textInput(branding.logo_url || "", function (value) { branding.logo_url = value; save(true); })));
      box.appendChild(field("Primary color", textInput(branding.primary_color || "#1f6f5f", function (value) { branding.primary_color = value; save(true); })));
      box.appendChild(field("Typography", selectInput(branding.typography || "system", ["system", "outfit", "geist", "accessible"], function (value) { branding.typography = value; save(true); })));
      box.appendChild(field("Certificate footer", textInput(branding.certificate_footer || "", function (value) { branding.certificate_footer = value; save(true); })));
      box.appendChild(sectionLabel("Workflow"));
      var workflow = course.authoring_workflow = course.authoring_workflow || {};
      box.appendChild(switchRow("Outline approved", workflow.outline_approved === true, function (value) { workflow.outline_approved = value; save(false); }));
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
      box.appendChild(sectionLabel("Citation inspector"));
      box.appendChild(field("Source references (one per line)", textInput((lesson.source_refs || []).join("\n"), function (value) {
        lesson.source_refs = value.split(/\r?\n/).map(function (item) { return item.trim(); }).filter(Boolean);
        save(false);
      }, "area")));
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

  // Real rich-text editing (bold/italic/underline/links/lists) that survives
  // a save, replacing the old contentEditable-then-collapse-to-textContent
  // approach that silently destroyed any formatting an author added. The
  // Tiptap instance is mounted as an overlay in THIS document (not inside
  // the canvas iframe): ProseMirror assumes it owns the realm it renders
  // into, and instantiating it against nodes from a different `window`
  // (the iframe's) risks subtle cross-realm bugs in selection/instanceof
  // checks. The overlay is positioned over the block's on-canvas position
  // instead, and on finish the sanitized HTML is written into the iframe's
  // DOM directly for instant feedback.
  var activeRichEditor = null;

  function destroyActiveRichEditor() {
    if (!activeRichEditor) return;
    document.removeEventListener("mousedown", activeRichEditor.onDocMouseDown, true);
    if (activeRichEditor.canvasDoc) {
      activeRichEditor.canvasDoc.removeEventListener("mousedown", activeRichEditor.onDocMouseDown, true);
    }
    activeRichEditor.editor.destroy();
    if (activeRichEditor.overlay.parentNode) activeRichEditor.overlay.parentNode.removeChild(activeRichEditor.overlay);
    activeRichEditor.target.classList.remove("studio-editing");
    activeRichEditor = null;
  }

  function startInlineEdit(target) {
    var doc = canvasDoc();
    if (!doc) return;
    var cbId = target.dataset.cbId;
    if (!cbId) return;
    var found = findBlock(cbId);
    if (!found) return;
    destroyActiveRichEditor();

    var host = target.querySelector(".sp-body") || target;
    var hostRect = host.getBoundingClientRect();
    var frameRect = canvas.getBoundingClientRect();

    target.classList.add("studio-editing");

    var overlay = document.createElement("div");
    overlay.className = "studio-rich-text-overlay";
    Object.assign(overlay.style, {
      position: "absolute",
      top: frameRect.top + hostRect.top + window.scrollY + "px",
      left: frameRect.left + hostRect.left + window.scrollX + "px",
      width: Math.max(hostRect.width, 160) + "px",
      minHeight: hostRect.height + "px",
      zIndex: "2147483647",
      background: "#fff",
      color: "#111",
      border: "2px solid #f59e0b",
      borderRadius: "4px",
      padding: "4px 6px",
      boxShadow: "0 4px 16px rgba(0,0,0,.25)",
      font: window.getComputedStyle(host).font || "inherit",
    });
    document.body.appendChild(overlay);

    var initialHtml = found.block.text_html || "<p>" + escapeHtml(found.block.text || "") + "</p>";

    var editor = new Editor({
      element: overlay,
      extensions: RICH_TEXT_EXTENSIONS,
      content: initialHtml,
      autofocus: "end",
    });

    var finish = function () {
      var sanitizedHtml = sanitizeRichTextHtml(editor.getHTML());
      var plainText = richTextToPlainText(sanitizedHtml);
      destroyActiveRichEditor();
      var changed = plainText && (plainText !== found.block.text || sanitizedHtml !== (found.block.text_html || ""));
      if (changed) {
        found.block.text_html = sanitizedHtml;
        found.block.text = plainText;
        host.innerHTML = sanitizedHtml; // DOM already shows the edit — no reload needed
        save(false);
        toast("Text updated.");
      }
    };

    var onDocMouseDown = function (event) {
      if (!overlay.contains(event.target)) finish();
    };
    overlay.addEventListener("keydown", function (event) {
      if (event.key === "Escape") {
        event.preventDefault();
        destroyActiveRichEditor();
        return;
      }
      if (event.key === "Enter" && !event.shiftKey && !editor.isActive("bulletList") && !editor.isActive("orderedList")) {
        // Content blocks are a single run of text, not a multi-paragraph
        // document — Enter commits the edit instead of inserting a paragraph.
        event.preventDefault();
        finish();
        return;
      }
      var mod = event.ctrlKey || event.metaKey;
      if (mod && (event.key === "k" || event.key === "K")) {
        event.preventDefault();
        var current = editor.getAttributes("link").href || "";
        var url = window.prompt("Link URL (https:// or mailto:)", current);
        if (url === null) return;
        if (!url.trim()) {
          editor.chain().focus().extendMarkRange("link").unsetLink().run();
        } else {
          editor.chain().focus().extendMarkRange("link").setLink({ href: url.trim() }).run();
        }
      }
    });
    document.addEventListener("mousedown", onDocMouseDown, true);
    // Clicks inside the iframe don't bubble to this (parent) document, so a
    // click elsewhere on the canvas needs its own listener to close the editor.
    doc.addEventListener("mousedown", onDocMouseDown, true);

    activeRichEditor = { editor: editor, overlay: overlay, target: target, onDocMouseDown: onDocMouseDown, canvasDoc: doc };
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
      document.querySelectorAll(".tab").forEach(function (item) { item.setAttribute("aria-selected", item === tab ? "true" : "false"); });
      $("tab-structure").hidden = tab.dataset.tab !== "structure";
      $("tab-templates").hidden = tab.dataset.tab !== "templates";
      $("tab-review").hidden = tab.dataset.tab !== "review";
      $("tab-sources").hidden = tab.dataset.tab !== "sources";
      if (tab.dataset.tab === "review") renderReview();
      if (tab.dataset.tab === "sources") renderSources();
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
    canvas.src = withToken("/course/" + sid + "/index.html");
    renderTree();
    renderPalette();
    renderReview();
    renderSources();
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

  if (!editorToken) {
    toast("No editor token in this link. Every save/export will fail until you open this page with ?token=...");
  }
})();
