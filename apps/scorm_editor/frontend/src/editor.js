/* Course Studio — WYSIWYG editor whose canvas IS the real course player.
   Same-origin iframe: the editor reads and decorates the player DOM directly. */
import { escapeHtml } from "./escape-html.js";
import { moveItem } from "./move-item.js";
import { moveBetweenLists } from "./move-between-lists.js";
import { sanitizeRichTextHtml, richTextToPlainText } from "./rich-text.js";
import { routeDroppedFile } from "./upload-route.js";
import { KNOWN_TEXT_PROVIDERS, buildAiRequestFields, getAiSettings, requiresCustomEndpointFields, setAiSettings } from "./ai-settings.js";
import { createUndoStack, pushEntry as pushUndoEntry, canUndo, canRedo, undoEntry, redoEntry } from "./undo-stack.js";
import { initialSaveStatus, saveStatusReducer, formatSaveStatus } from "./save-status.js";
import { CONTENT_BLOCK_TRANSFORMS, CONTENT_BLOCK_TRANSFORM_IDS, buildContentBlockAiRequest, extractRewrittenText } from "./content-block-ai.js";
import { buildQuizFromContentRequest, extractQuizQuestions } from "./quiz-from-content-ai.js";
import { buildBranchingScenarioFromPremiseRequest, extractBranchingScenarioActivity } from "./branching-scenario-ai.js";
import { buildTranslateBlockRequest, extractTranslatedText } from "./translate-block-ai.js";
import { ALT_TEXT_CONTEXT_ONLY_NOTE, buildAltTextRequest, extractAltText } from "./alt-text-ai.js";
import { countBlankTokens } from "./fill-blank.js";
import { computeRegionPercentages, isRegionSizeUsable, rectFromPoints } from "./hotspot-geometry.js";
import { CATEGORY_LABELS as COURSE_HEALTH_CATEGORY_LABELS, runCourseHealthCheck } from "./course-health.js";
import { LESSON_SKELETONS, LESSON_SKELETON_IDS, buildLessonFromSkeleton } from "./lesson-skeletons.js";
import {
  buildOutlineRegenerateRequest,
  extractRegeneratedModuleOutline,
  extractRegeneratedLessonOutline,
} from "./outline-regenerate-ai.js";

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
    undoStack: createUndoStack(50),
    selected: { kind: "course" },
    saveStatus: initialSaveStatus(),
    lastSaveArgs: null,
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

  /* Reflects the real, current save() lifecycle -- not a fake timer. Every
     mutation in this file already routes through save() (see the many
     save(true)/save(false) call sites below), which fires the PUT
     immediately; this only renders what that call is doing right now:
     in-flight, succeeded (with a relative-time hint that stays honest via
     the 30s refresh timer below), or failed (with a visible retry
     affordance, never a silent failure). */
  function renderSaveIndicator() {
    var display = formatSaveStatus(state.saveStatus, Date.now());
    $("save-status").textContent = display.text;
    var retryBtn = $("btn-save-retry");
    if (retryBtn) retryBtn.hidden = !display.showRetry;
  }

  function dispatchSaveStatus(event) {
    state.saveStatus = saveStatusReducer(state.saveStatus, event);
    renderSaveIndicator();
  }

  function retrySave() {
    if (!state.lastSaveArgs) return;
    save(state.lastSaveArgs.structural, true);
  }

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
    pushUndoEntry(state.undoStack, clone(state.course));
    updateUndoButtons();
  }

  function updateUndoButtons() {
    $("btn-undo").disabled = !canUndo(state.undoStack);
    $("btn-redo").disabled = !canRedo(state.undoStack);
  }

  function undo() {
    var entry = undoEntry(state.undoStack);
    if (entry === null) return;
    state.course = clone(entry);
    updateUndoButtons();
    save(true, true);
  }

  function redo() {
    var entry = redoEntry(state.undoStack);
    if (entry === null) return;
    state.course = clone(entry);
    updateUndoButtons();
    save(true, true);
  }

  // P5-5c note on the `structural` flag and preview refresh timing: `structural` really means
  // "does this change need to be visible in the inline canvas preview" -- when true (the default
  // for anything that adds/edits rendered content: text, media, quiz questions, activities,
  // branding, etc.) a successful save reloads the <iframe id="canvas"> in place, so the preview
  // updates automatically without the user navigating anywhere or clicking "Refresh preview"
  // manually. It's false only for authoring metadata that never renders in the course itself
  // (e.g. the "Outline approved" workflow toggle, citation source_refs) or for edits made
  // directly on the canvas DOM (startInlineEdit()'s finish(), which patches host.innerHTML
  // itself -- reloading there would just be wasted work).
  //
  // No extra debounce was added for this refresh: every save() call site here is already gated
  // by a discrete user action -- a text/number/select input's "change" event (which fires on
  // blur, not per keystroke), a button click, or an AI action's fetch response -- not by
  // continuous typing. So each edit already produces at most one save(), and therefore at most
  // one canvas reload; no keystroke-storm exists to coalesce.
  function save(structural, recorded) {
    state.lastSaveArgs = { structural: structural };
    if (state.conflicted) { toast("Reload the newer revision before saving."); return Promise.resolve(); }
    if (!recorded) pushHistory();
    persistRecovery();
    state.saving = true;
    var blockedThisAttempt = false;
    if (!navigator.onLine) { setSaveStatus("Offline · recovery saved"); }
    else { dispatchSaveStatus({ type: "saving" }); }
    return fetch("/api/course/" + state.session, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ course: state.course, version: state.version }),
    })
      .then(function (res) { return res.json().then(function (data) { data.httpStatus = res.status; return data; }); })
      .then(function (data) {
        if (data.httpStatus === 409) {
          state.conflicted = true;
          blockedThisAttempt = true;
          $("conflict-banner").hidden = false;
          dispatchSaveStatus({ type: "blocked", reason: "Conflict · reload required" });
          throw new Error("Another tab saved a newer revision");
        }
        if (data.httpStatus === 410) {
          blockedThisAttempt = true;
          dispatchSaveStatus({ type: "blocked", reason: "Session expired · recovery available" });
          throw new Error("Session expired");
        }
        if (!data.ok) throw new Error(data.error || "Save failed");
        state.version = data.version;
        state.saving = false;
        clearRecovery();
        dispatchSaveStatus({ type: "success", version: data.version, at: Date.now() });
        if (state.channel) state.channel.postMessage({ session: state.session, version: state.version });
        if (structural) reloadCanvas();
        renderTree();
        $("course-name").textContent = state.course.course_title || "Untitled course";
      })
      .catch(function (error) {
        state.saving = false;
        persistRecovery();
        if (!state.conflicted && !blockedThisAttempt) dispatchSaveStatus({ type: "failure", reason: error.message });
        toast("Save failed: " + error.message);
      });
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

  // P5-5d: results of the last "Run course health check" click, kept outside state.course (it's
  // a derived, ephemeral report, not authored course data -- never written through save()) so it
  // survives renderReview() re-renders (e.g. the generation-status polling in this function) until
  // the author re-runs the check. null means "not run yet this session".
  var lastCourseHealthResults = null;

  function renderCourseHealthSection(box) {
    var section = document.createElement("div");
    section.className = "course-health";
    var heading = document.createElement("h4");
    heading.textContent = "Course health";
    section.appendChild(heading);
    var hint = document.createElement("p");
    hint.className = "hint";
    hint.textContent = "Advisory scan for missing alt text, thin content, unanswered quiz questions, broken branching links, and objectives with no assessment coverage. This never blocks export.";
    section.appendChild(hint);
    var button = document.createElement("button");
    button.type = "button";
    button.className = "ghost";
    button.textContent = "Run course health check";
    button.addEventListener("click", function () {
      lastCourseHealthResults = runCourseHealthCheck(state.course);
      paint();
    });
    section.appendChild(button);
    var results = document.createElement("div");
    results.className = "course-health-results";
    results.setAttribute("role", "status");
    section.appendChild(results);

    function paint() {
      results.innerHTML = "";
      if (!lastCourseHealthResults) return;
      if (!lastCourseHealthResults.length) {
        var pass = document.createElement("p");
        pass.className = "review-row";
        pass.textContent = "All checks passed — no issues found.";
        results.appendChild(pass);
        return;
      }
      var byCategory = {};
      lastCourseHealthResults.forEach(function (finding) {
        (byCategory[finding.category] = byCategory[finding.category] || []).push(finding);
      });
      Object.keys(byCategory).forEach(function (category) {
        var group = byCategory[category];
        var groupTitle = document.createElement("p");
        groupTitle.className = "review-row";
        groupTitle.style.fontWeight = "700";
        groupTitle.textContent = (COURSE_HEALTH_CATEGORY_LABELS[category] || category) + " (" + group.length + ")";
        results.appendChild(groupTitle);
        var list = document.createElement("ul");
        list.className = "course-health-list";
        group.forEach(function (finding) {
          var li = document.createElement("li");
          li.textContent = finding.location + " — " + finding.message;
          list.appendChild(li);
        });
        results.appendChild(list);
      });
    }

    paint();
    box.appendChild(section);
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
      renderCourseHealthSection(box);
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

  /* ================= AI settings (P5-3: transport + key-entry UI only) =================
     No AI action (rewrite/quiz/translate) is wired up here yet -- that is explicit future
     work. This panel only lets the author pick a text_providers/ adapter and enter their own
     API key for THIS browser tab. See ai-settings.js's header comment for the storage
     contract: the key lives in that module's in-memory variable only, is never written to
     localStorage/sessionStorage, never touches state.course, and is resent per-request rather
     than remembered by the server. */
  function renderAiSettings() {
    var box = $("tab-ai");
    if (!box) return;
    box.replaceChildren();
    var heading = document.createElement("h3");
    heading.textContent = "AI settings";
    box.appendChild(heading);
    var hint = document.createElement("p");
    hint.className = "hint";
    hint.textContent =
      "Your API key is kept only in this browser tab's memory for this session. It is never " +
      "saved to the course, written to disk, or sent anywhere except your chosen provider's " +
      "own request.";
    box.appendChild(hint);

    var current = getAiSettings();
    var form = document.createElement("form");
    form.className = "review-form";

    var providerLabel = document.createElement("label");
    providerLabel.textContent = "Provider";
    var providerSelect = document.createElement("select");
    providerSelect.setAttribute("aria-label", "AI text provider");
    KNOWN_TEXT_PROVIDERS.forEach(function (entry) {
      var option = document.createElement("option");
      option.value = entry.id;
      option.textContent = entry.label;
      option.selected = entry.id === current.provider;
      providerSelect.appendChild(option);
    });
    providerLabel.appendChild(providerSelect);
    form.appendChild(providerLabel);

    var keyLabel = document.createElement("label");
    keyLabel.textContent = "API key";
    var keyInput = document.createElement("input");
    keyInput.type = "password";
    keyInput.autocomplete = "off";
    keyInput.placeholder = "sk-...";
    keyInput.value = current.apiKey;
    keyInput.setAttribute("aria-label", "AI provider API key");
    keyLabel.appendChild(keyInput);
    form.appendChild(keyLabel);

    var customFields = document.createElement("div");
    customFields.hidden = !requiresCustomEndpointFields(current.provider);
    var baseUrlLabel = document.createElement("label");
    baseUrlLabel.textContent = "Base URL";
    var baseUrlInput = document.createElement("input");
    baseUrlInput.placeholder = "https://api.example.com/v1";
    baseUrlInput.value = current.baseUrl;
    baseUrlInput.setAttribute("aria-label", "Custom endpoint base URL");
    baseUrlLabel.appendChild(baseUrlInput);
    var modelLabel = document.createElement("label");
    modelLabel.textContent = "Model";
    var modelInput = document.createElement("input");
    modelInput.placeholder = "model-name";
    modelInput.value = current.model;
    modelInput.setAttribute("aria-label", "Custom endpoint model");
    modelLabel.appendChild(modelInput);
    customFields.append(baseUrlLabel, modelLabel);
    form.appendChild(customFields);

    providerSelect.addEventListener("change", function () {
      customFields.hidden = !requiresCustomEndpointFields(providerSelect.value);
    });

    var saveButton = document.createElement("button");
    saveButton.className = "primary";
    saveButton.type = "submit";
    saveButton.textContent = "Save for this session";
    form.appendChild(saveButton);

    var status = document.createElement("p");
    status.className = "hint";
    status.setAttribute("role", "status");
    box.appendChild(form);
    box.appendChild(status);

    form.addEventListener("submit", function (event) {
      event.preventDefault();
      try {
        setAiSettings({
          provider: providerSelect.value,
          apiKey: keyInput.value,
          baseUrl: baseUrlInput.value,
          model: modelInput.value,
        });
        status.textContent = "Saved for this browser tab only.";
      } catch (error) {
        status.textContent = error.message;
      }
    });
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

  // Single source of truth for every "activity" template (the interaction
  // types also rendered server-side by renderNativeActivity() in
  // exporters/scorm.py). Previously the palette metadata (icon/name/note)
  // lived in the TEMPLATES array below while each type's default value shape
  // lived in a parallel switch statement in templatePayload() -- adding a
  // type meant editing both in lockstep. Now each type is one entry here;
  // TEMPLATES and templatePayload() both derive from it. Non-activity
  // templates (text/image/video block inserts, and the mcq question insert)
  // aren't part of this registry: they don't go through renderNativeActivity
  // or activityEditor's activity_type dispatch, so folding them in here
  // would not be consolidating an actual split -- see activityEditor() below
  // for why the *inspector* dispatch stays a separate ordered table instead
  // of also living in this by-id registry.
  var ACTIVITY_TEMPLATE_REGISTRY = {
    flashcards: {
      icon: "🃏",
      name: "Flashcards",
      note: "Flip cards for terms and definitions.",
      build: function () {
        return { activity_id: uid("act"), activity_type: "flashcards", title: "Key terms", objective: "Flip each card and say the answer first.", items: [{ front: "Term", back: "Definition" }] };
      },
    },
    matching: {
      icon: "🔗",
      name: "Matching",
      note: "Match prompts to their answers.",
      build: function () {
        return { activity_id: uid("act"), activity_type: "matching", title: "Match the pairs", objective: "Match each prompt to its answer.", items: [{ prompt: "Prompt", match: "Answer" }] };
      },
    },
    accordion: {
      icon: "📂",
      name: "Accordion",
      note: "Expandable review sections.",
      build: function () {
        return { activity_id: uid("act"), activity_type: "accordion", title: "Review points", objective: "Open each section.", items: [{ title: "Point one", detail: "Detail for point one." }] };
      },
    },
    decision: {
      icon: "🌿",
      name: "Decision scenario",
      note: "One scene with best/risk choices.",
      build: function () {
        return { activity_id: uid("act"), activity_type: "scenario_decision_tree", title: "Choose the best response", objective: "Pick the strongest action.", items: [{ scenario: "Describe the situation…", choices: [{ label: "Best action", result: "best", feedback: "Why this is right." }, { label: "Risky action", result: "risk", feedback: "Why this backfires." }] }] };
      },
    },
    branching: {
      icon: "🎭",
      name: "Branching character scene",
      note: "Persona-driven multi-scene dialogue.",
      build: function () {
        return { activity_id: uid("act"), activity_type: "branching_scenario", title: "Conversation scene", objective: "Lead the conversation.", persona: { name: "Alex", role: "Stakeholder" }, items: [{ scenario: "Alex opens with…", choices: [{ label: "Strong reply", result: "best", feedback: "Great choice." }, { label: "Weak reply", result: "risk", feedback: "This loses trust." }] }] };
      },
    },
    timeline: {
      icon: "📅",
      name: "Timeline",
      note: "Ordered steps with detail.",
      build: function () {
        return { activity_id: uid("act"), activity_type: "timeline", title: "The steps", objective: "Walk the steps in order.", items: [{ label: "Step 1", detail: "What happens first." }] };
      },
    },
    fill_blank: {
      icon: "✏️",
      name: "Fill in the blank",
      note: "Text with {{blank}} tokens the learner fills in.",
      build: function () {
        return { activity_id: uid("act"), activity_type: "fill_blank", title: "Fill in the blank", objective: "Type the missing word for each blank.", text: "The capital of France is {{blank}}.", blanks: [{ answers: "Paris" }] };
      },
    },
    hotspot: {
      icon: "🎯",
      name: "Image hotspot",
      note: "Click regions on an image to find the right spot.",
      build: function () {
        return { activity_id: uid("act"), activity_type: "image_hotspot", title: "Find the right spot", objective: "Click the correct area on the image.", image: { src: "", alt: "" }, regions: [] };
      },
    },
    sorting: {
      icon: "🔢",
      name: "Sorting / ranking",
      note: "Learner reorders items back into the correct sequence.",
      build: function () {
        return {
          activity_id: uid("act"),
          activity_type: "sorting",
          title: "Put the steps in order",
          objective: "Reorder the items into the correct sequence.",
          items: [{ text: "First step" }, { text: "Second step" }, { text: "Third step" }],
        };
      },
    },
  };

  var TEMPLATES = [
    { id: "text", icon: "📝", name: "Text block", note: "A paragraph of learner-facing content." },
    { id: "image", icon: "🖼️", name: "Image block", note: "Text with an image (upload or URL)." },
    { id: "video", icon: "🎬", name: "Video block", note: "Text with a YouTube/Vimeo/Loom or mp4 video." },
  ].concat(Object.keys(ACTIVITY_TEMPLATE_REGISTRY).map(function (id) {
    var entry = ACTIVITY_TEMPLATE_REGISTRY[id];
    return { id: id, icon: entry.icon, name: entry.name, note: entry.note };
  })).concat([
    { id: "mcq", icon: "❓", name: "Quiz question", note: "MCQ with feedback (lesson or final)." },
  ]);

  function templatePayload(templateId) {
    switch (templateId) {
      case "text":
        return { target: "block", value: { id: uid("cb"), type: "explanation", text: "Write the learner-facing explanation here." } };
      case "image":
        return { target: "block", value: { id: uid("cb"), type: "example", text: "Describe what the image shows.", media: { kind: "image", src: "", alt: "", caption: "" } } };
      case "video":
        return { target: "block", value: { id: uid("cb"), type: "example", text: "Introduce the video.", media: { kind: "video", src: "", caption: "Watch the walkthrough" } } };
      case "mcq":
        return { target: "question", value: { id: uid("q"), type: "mcq", objective_ids: [], question: "Write the question here?", options: ["Correct answer", "Distractor"], correct_answers: ["Correct answer"], explanation: "Explain why the correct answer is right." } };
      default: {
        var entry = ACTIVITY_TEMPLATE_REGISTRY[templateId];
        return entry ? { target: "activity", value: entry.build() } : null;
      }
    }
  }

  // P5-5e: builds the "start from a template" picker shown in the module inspector, next to the
  // existing "+ Add lesson" blank-lesson button. A plain <select> (not a button-per-skeleton
  // palette like TEMPLATES/insertTemplate above) because there are only a handful of skeletons
  // and the module inspector already reads top-to-bottom as a form -- a select keeps the default
  // "Start from scratch" placeholder explicit and one extra click away from accidentally firing,
  // unlike a bare list of buttons. Picking a real option builds the lesson via
  // buildLessonFromSkeleton() (lesson-skeletons.js), pushes it into module.lessons, saves through
  // the same save(true) call the blank-lesson button uses (so it's undoable in one Ctrl+Z step,
  // and P5-5c's live preview refreshes), then resets back to the placeholder so the control is
  // ready to use again without implying a skeleton is "selected" as ongoing state.
  function lessonSkeletonPicker(module) {
    var select = document.createElement("select");
    var placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = "Start from scratch (choose a template instead)…";
    select.appendChild(placeholder);
    LESSON_SKELETON_IDS.forEach(function (skeletonId) {
      var skeleton = LESSON_SKELETONS[skeletonId];
      var option = document.createElement("option");
      option.value = skeletonId;
      option.textContent = (skeleton.icon ? skeleton.icon + " " : "") + skeleton.name + " — " + skeleton.note;
      select.appendChild(option);
    });
    select.addEventListener("change", function () {
      var skeletonId = select.value;
      select.value = "";
      if (!skeletonId) return;
      var lesson = buildLessonFromSkeleton(skeletonId, uid, module.objective_ids || []);
      (module.lessons = module.lessons || []).push(lesson);
      save(true);
      toast("Inserted “" + LESSON_SKELETONS[skeletonId].name + "” — now edit the placeholder text.");
    });
    return field("Or start a new lesson from a template", select);
  }

  // P5-5f: "AI-assisted inline outline regeneration" -- lets an author select the current module
  // OR lesson, type brief guidance, and ask AI to produce a NEW outline (lesson titles +
  // block-role skeleton at module scope; a block-role skeleton at lesson scope) without leaving
  // the editor or restarting the pre-generation discovery flow. STRUCTURE ONLY -- see
  // outline-regenerate-ai.js's module docstring for why full-content regeneration was rejected.
  // Keyed by "module:<mi>" / "lesson:<lessonKey>" -- same per-target in-flight guard shape as
  // aiQuizRequestInFlight/aiBranchingRequestInFlight above. `aiOutlineGuidanceDraft` holds the
  // author's in-progress guidance text per target key across renderInspector() re-renders,
  // deliberately NOT part of state.course (ephemeral input, never saved/undoable on its own),
  // mirroring aiBranchingPremiseDraft above.
  var aiOutlineRequestInFlight = {};
  var aiOutlineGuidanceDraft = {};

  // Shared guard/fetch/parse/finally scaffolding for the six "AI action" flows in this file
  // (outline regenerate, content-block transform, quiz-from-content, branching scenario,
  // translate, alt text). Each flow differs in real ways -- whether it needs a confirm() gate
  // before sending anything, whether it fires one request or a batch (runTranslateAiAction),
  // how a successful result is applied to state.course, and whether the trailing re-render is
  // unconditional or scoped to "only if this target is still selected" -- so those stay as
  // parameters/callbacks supplied by each call site rather than being unified away. What IS
  // identical across all six: the in-flight double-fire guard, the optional confirm()-before-
  // request gate, wrapping request.build() in try/catch so a validation error becomes a toast
  // and sends no request, setting the in-flight flag before the request (immediately followed by
  // a renderInspector() to show the loading state), and clearing the flag + re-rendering in
  // .finally() regardless of outcome.
  //
  // config: the 9 fields below group into 4 sub-objects/values by concern -- in-flight state,
  // an optional confirm gate, network I/O, and result application -- plus the standalone
  // `rerender` override.
  //   flight
  //     .map           - the target's `aiXxxRequestInFlight` map
  //     .key            - key into flight.map for this target
  //     .value          - value stored at flight.map[flight.key] while running (default: true;
  //                       runContentBlockAiTransform stores the transformId instead, so its
  //                       busy-state UI can show which of the three transforms is running)
  //   confirm          - optional message; if truthy, confirm() must be accepted (checked right
  //                       after the in-flight guard, before request.build -- a decline sends no
  //                       request and mutates nothing)
  //   request
  //     .build          - () -> body for request.send; may throw, caught and toasted as
  //                       error.message
  //     .send           - (body) -> Promise resolving to whatever result.onSuccess needs (the
  //                       parsed postAiGenerate() response for every single-request action, or an
  //                       already-extracted array for runTranslateAiAction's batch)
  //   result
  //     .onSuccess      - (result) -> apply the mutation, save(), toast() on success
  //     .failureMessage - (error) -> string toasted on any rejection (network error, non-ok
  //                       response, or onSuccess itself throwing)
  //   rerender         - optional; called in .finally() instead of the default unconditional
  //                       renderInspector() (runContentBlockAiTransform/runAltTextAiAction use
  //                       this to only re-render if their block is still the selected one)
  function runAiAction(config) {
    if (config.flight.map[config.flight.key]) return; // already running for this target -- ignore double-fire
    if (config.confirm && !confirm(config.confirm)) return; // declined -- no request sent, nothing mutated

    var body;
    try {
      body = config.request.build();
    } catch (error) {
      toast(error.message);
      return;
    }

    config.flight.map[config.flight.key] = config.flight.value === undefined ? true : config.flight.value;
    renderInspector(); // shows the disabled/loading state immediately

    config.request.send(body)
      .then(function (result) { config.result.onSuccess(result); })
      .catch(function (error) { toast(config.result.failureMessage(error)); })
      .finally(function () {
        delete config.flight.map[config.flight.key];
        if (config.rerender) config.rerender();
        else renderInspector();
      });
  }

  // Single-request POST to the session's AI endpoint, shared by every AI action below that fires
  // one request per invocation (all but runTranslateAiAction, which batches one call per block --
  // see its own comment). Resolves with the parsed response (httpStatus attached) once data.ok is
  // true, otherwise rejects with an Error carrying the server's message.
  function postAiGenerate(body) {
    return fetch("/api/ai/" + state.session + "/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
      .then(function (res) { return res.json().then(function (data) { data.httpStatus = res.status; return data; }); })
      .then(function (data) {
        if (!data.ok) throw new Error(data.error || "AI request failed.");
        return data;
      });
  }

  function outlineRegenerateActionsSection(scope, flightKey, label, run) {
    var wrap = document.createElement("div");
    wrap.className = "ai-outline-actions";
    wrap.appendChild(sectionLabel("AI actions"));

    var hint = document.createElement("p");
    hint.className = "hint";
    hint.textContent = "Regenerate this " + scope + "'s outline with AI (titles/roles only -- you fill in the real content afterward). This REPLACES the current structure.";
    wrap.appendChild(hint);

    var busy = Boolean(aiOutlineRequestInFlight[flightKey]);
    var textarea = textInput(aiOutlineGuidanceDraft[flightKey] || "", function (value) {
      aiOutlineGuidanceDraft[flightKey] = value;
    }, "area");
    textarea.placeholder = "e.g. \"make this more example-heavy\" or \"add a section on refunds\"";
    textarea.disabled = busy;
    wrap.appendChild(textarea);

    var button = document.createElement("button");
    button.type = "button";
    button.className = "ghost";
    button.textContent = busy ? "Regenerating outline…" : label;
    button.disabled = busy;
    button.setAttribute("aria-label", label);
    button.addEventListener("click", run);
    wrap.appendChild(button);

    if (busy) {
      var status = document.createElement("p");
      status.className = "hint";
      status.setAttribute("role", "status");
      status.textContent = "Regenerating outline — this can take a few seconds…";
      wrap.appendChild(status);
    }
    return wrap;
  }

  // Shared confirm/request/apply/undo path for both scopes. `scope` is "module" or "lesson";
  // `flightKey` is this target's aiOutlineRequestInFlight key; `buildTarget` returns the plain
  // current-structure context to send (module: {title, lessons:[{title}]}; lesson: {title,
  // objective, blocks:[{role}]}); `apply(regenerated)` performs the actual structural replacement
  // and MUST be the only place that mutates state.course for this action, called only after both
  // the confirm() gate below AND a successful, validated response.
  //
  // The confirm() fires FIRST -- before the AI request is even sent -- same
  // confirm()-before-destructive-action pattern as runAltTextAiAction's existing-alt-text
  // overwrite confirm above, and asked up front (rather than after a successful generation)
  // because this action is destructive-by-definition regardless of what the model returns: there
  // is no "confirm only if there's something to overwrite" branch here the way alt text has, so
  // asking first also avoids spending an AI call the author was always going to decline. Declining
  // sends no request at all and mutates nothing.
  function runOutlineRegenerateAiAction(scope, flightKey, confirmMessage, buildTarget, apply) {
    runAiAction({
      flight: { map: aiOutlineRequestInFlight, key: flightKey },
      confirm: confirmMessage,
      request: {
        build: function () {
          var guidance = aiOutlineGuidanceDraft[flightKey] || "";
          return buildOutlineRegenerateRequest(scope, buildTarget(), guidance, buildAiRequestFields());
        },
        send: postAiGenerate,
      },
      result: {
        onSuccess: function (data) {
          // extractRegeneratedModuleOutline()/extractRegeneratedLessonOutline() are this module's
          // own validation of the AI response shape -- see outline-regenerate-ai.js's module
          // docstring. On a throw here nothing is applied, same as any other rejection path below --
          // apply() is only ever called with a fully-validated regenerated structure.
          var summary = apply(data.result); // e.g. "4 lessons" or "3 blocks" -- see call sites below
          delete aiOutlineGuidanceDraft[flightKey];
          // P5-5c: save(true) -- the regenerated outline is rendered structural content, so the
          // inline preview needs to refresh to show it. Also the sole undo mechanism beyond the
          // confirm() gate above: Ctrl+Z restores the pre-regeneration structure in one step.
          save(true);
          toast("Regenerated " + summary + " — now fill in the placeholder content.");
        },
        failureMessage: function (error) {
          // Nothing is mutated above apply() succeeding, so a rejection at any point (network
          // error, malformed/invalid AI response, no provider key) leaves the module/lesson's
          // structure exactly as it was.
          return "Outline regeneration failed: " + error.message;
        },
      },
    });
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

  // P5-3b: per-block AI actions (Rewrite/Expand/Simplify). Keyed by content block id so the
  // "disable while in flight" state survives renderInspector() rebuilding the DOM (the block's
  // own inspector panel is rebuilt from scratch once the request settles, to show the updated
  // text and clear the busy state) and so a second click on the SAME block while a request is
  // still running is a no-op -- see the guard at the top of runContentBlockAiTransform. This is
  // deliberately keyed per-block, not global, so acting on a different block is still allowed.
  var aiBlockRequestInFlight = {};

  function aiBlockActionsSection(block) {
    var wrap = document.createElement("div");
    wrap.className = "ai-block-actions";
    wrap.appendChild(sectionLabel("AI actions"));
    var buttonRow = document.createElement("div");
    buttonRow.style.display = "flex";
    buttonRow.style.gap = "8px";
    buttonRow.style.flexWrap = "wrap";
    var busyTransform = aiBlockRequestInFlight[block.id] || null;

    CONTENT_BLOCK_TRANSFORM_IDS.forEach(function (transformId) {
      var transform = CONTENT_BLOCK_TRANSFORMS[transformId];
      var button = document.createElement("button");
      button.type = "button";
      button.className = "ghost";
      button.textContent = busyTransform === transformId ? transform.label + "…" : transform.label;
      button.disabled = Boolean(busyTransform); // any transform running on THIS block disables all three
      button.setAttribute("aria-label", transform.label + " this content block with AI");
      button.addEventListener("click", function () { runContentBlockAiTransform(transformId, block.id); });
      buttonRow.appendChild(button);
    });
    wrap.appendChild(buttonRow);

    if (busyTransform) {
      var status = document.createElement("p");
      status.className = "hint";
      status.setAttribute("role", "status");
      status.textContent = "Running " + CONTENT_BLOCK_TRANSFORMS[busyTransform].label.toLowerCase() + "…";
      wrap.appendChild(status);
    }
    return wrap;
  }

  function runContentBlockAiTransform(transformId, cbId) {
    // Checked here too (ahead of runAiAction's own in-flight guard) so findBlock() below never
    // runs while a request for this block is already in flight -- matches this function's
    // pre-refactor order exactly; runAiAction's internal check is then a harmless no-op re-check.
    if (aiBlockRequestInFlight[cbId]) return; // already running for this block -- ignore double-fire
    var found = findBlock(cbId);
    if (!found) return;

    runAiAction({
      flight: { map: aiBlockRequestInFlight, key: cbId, value: transformId },
      request: {
        build: function () {
          return buildContentBlockAiRequest(
            transformId,
            found.block,
            found.row.lesson.title,
            found.row.lesson.content_blocks || [],
            buildAiRequestFields()
          );
        },
        send: postAiGenerate,
      },
      result: {
        onSuccess: function (data) {
          var text = extractRewrittenText(data.result);
          var stillThere = findBlock(cbId);
          if (!stillThere) return; // block was removed while the request was in flight -- nothing to apply
          // Same save()/pushHistory() path every other block edit uses (see the "Text" field's
          // textInput() onChange above) -- so Ctrl+Z genuinely undoes an AI transform exactly like
          // a manual edit. P5-5c: save(true) (not false) because the rewritten text is rendered
          // content -- the inline preview must pick it up, same as a manual text edit does.
          stillThere.block.text = text;
          stillThere.block.text_html = sanitizeRichTextHtml("<p>" + escapeHtml(text) + "</p>");
          save(true);
          toast(CONTENT_BLOCK_TRANSFORMS[transformId].label + " applied.");
        },
        failureMessage: function (error) {
          // Original block text is untouched -- we only ever write to `stillThere.block` inside
          // the success branch above, never here.
          return CONTENT_BLOCK_TRANSFORMS[transformId].label + " failed: " + error.message;
        },
      },
      rerender: function () {
        if (state.selected.kind === "block" && state.selected.cbId === cbId) renderInspector();
      },
    });
  }

  // P5-3c: "Generate quiz from content" AI action. Keyed by a scope key ("block:<cbId>" or
  // "lesson:<lessonKey>") so it's a per-target in-flight guard, same shape/reasoning as
  // aiBlockRequestInFlight above -- a second click on the SAME target while a request is running
  // is a no-op, but a different block/lesson can still run its own request concurrently.
  var aiQuizRequestInFlight = {};

  // Renders the trigger + status for one scope. `scope` is "block" or "lesson"; `flightKey` is
  // this target's aiQuizRequestInFlight key; `label` is the button copy; `run` performs the
  // request (bound to the right block/lesson by the caller).
  function quizFromContentActionsSection(flightKey, label, run) {
    var wrap = document.createElement("div");
    wrap.className = "ai-quiz-actions";
    wrap.appendChild(sectionLabel("AI actions"));
    var busy = Boolean(aiQuizRequestInFlight[flightKey]);
    var button = document.createElement("button");
    button.type = "button";
    button.className = "ghost";
    button.textContent = busy ? "Generating quiz…" : label;
    button.disabled = busy;
    button.setAttribute("aria-label", label);
    button.addEventListener("click", run);
    wrap.appendChild(button);
    if (busy) {
      var status = document.createElement("p");
      status.className = "hint";
      status.setAttribute("role", "status");
      status.textContent = "Generating a quiz — this can take a few seconds…";
      wrap.appendChild(status);
    }
    return wrap;
  }

  // Shared request/apply/undo path for both scopes (block and lesson) -- see
  // quiz-from-content-ai.js's module docstring for the wire-format and mapping decisions.
  // `scopedBlocks` is the array of content blocks to draw the quiz from; `lesson` is the owning
  // lesson the generated questions get appended to (lesson.quiz_questions, NEVER overwriting any
  // existing quiz questions already there -- always append, same as insertTemplate("mcq", ...)
  // does for a manually-inserted question). Routed through save(false)/pushHistory() so Ctrl+Z
  // undoes the whole generated batch in one step, exactly like a manual "+ Add question" click
  // would undo in one step.
  function runQuizFromContentAiAction(scope, flightKey, lesson, scopedBlocks) {
    runAiAction({
      flight: { map: aiQuizRequestInFlight, key: flightKey },
      request: {
        build: function () {
          return buildQuizFromContentRequest(scope, lesson.title, scopedBlocks, buildAiRequestFields());
        },
        send: postAiGenerate,
      },
      result: {
        onSuccess: function (data) {
          // extractQuizQuestions() is a lighter-weight second check on top of the server's real
          // Pydantic QuizBank/QuizQuestion validation (server.py's _validate_ai_result_schema) --
          // see quiz-from-content-ai.js's module docstring. On failure here nothing is inserted,
          // same as any other rejection path below.
          var questions = extractQuizQuestions(data.result);
          lesson.quiz_questions = lesson.quiz_questions || [];
          questions.forEach(function (question) {
            lesson.quiz_questions.push({
              id: uid("q"),
              type: "mcq",
              objective_ids: [],
              question: question.question,
              options: question.options,
              correct_answers: question.correct_answers,
              explanation: question.explanation,
            });
          });
          // P5-5c: save(true) -- new quiz questions are rendered lesson content, so the inline
          // preview needs to refresh to show them.
          save(true);
          toast("Generated " + questions.length + " quiz question" + (questions.length === 1 ? "" : "s") + ".");
        },
        failureMessage: function (error) {
          // Nothing is mutated above the extractQuizQuestions() call succeeding, so a rejection at
          // any point (network error, server-side schema rejection, no provider key) inserts
          // nothing -- lesson.quiz_questions is left exactly as it was.
          return "Quiz generation failed: " + error.message;
        },
      },
    });
  }

  // P5-3f: "Generate branching scenario from premise" AI action. Keyed by lesson key -- one
  // in-flight guard per lesson (this action always creates a brand-new activity in that lesson's
  // lesson.activities, so there's no per-activity target the way the quiz action has a per-block
  // one). `aiBranchingPremiseDraft` holds the author's in-progress premise text per lesson key
  // across renderInspector() re-renders (e.g. triggered by an unrelated edit while the textarea is
  // focused); it is deliberately NOT part of state.course (it's ephemeral input, not saved course
  // data) so it is never written through save()/pushHistory().
  var aiBranchingRequestInFlight = {};
  var aiBranchingPremiseDraft = {};

  function branchingScenarioActionsSection(lessonKey, lesson) {
    var wrap = document.createElement("div");
    wrap.className = "ai-branching-actions";
    wrap.appendChild(sectionLabel("AI actions"));
    var busy = Boolean(aiBranchingRequestInFlight[lessonKey]);

    var hint = document.createElement("p");
    hint.className = "hint";
    hint.textContent = "Generate a new branching character scene from a short premise.";
    wrap.appendChild(hint);

    var textarea = textInput(aiBranchingPremiseDraft[lessonKey] || "", function (value) {
      aiBranchingPremiseDraft[lessonKey] = value;
    }, "area");
    textarea.placeholder = "e.g. \"A customer calls in angry about a billing error.\"";
    textarea.disabled = busy;
    wrap.appendChild(textarea);

    var button = document.createElement("button");
    button.type = "button";
    button.className = "ghost";
    button.textContent = busy ? "Generating scenario…" : "Generate branching scenario";
    button.disabled = busy;
    button.setAttribute("aria-label", "Generate branching scenario");
    button.addEventListener("click", function () { runBranchingScenarioAiAction(lessonKey, lesson); });
    wrap.appendChild(button);

    if (busy) {
      var status = document.createElement("p");
      status.className = "hint";
      status.setAttribute("role", "status");
      status.textContent = "Generating a branching scenario — this can take a few seconds…";
      wrap.appendChild(status);
    }
    return wrap;
  }

  // Builds the request from the lesson's own draft premise, sends it, and on success inserts a
  // brand-new "branching_scenario" activity into lesson.activities -- the exact data shape
  // ACTIVITY_TEMPLATE_REGISTRY.branching's build() produces, so it renders in the existing shared
  // "scenes" ACTIVITY_INSPECTORS entry and exports through the existing renderNativeActivity/
  // ACTIVITY_RENDERERS with no special-casing. Routed through save(false)/pushHistory() so Ctrl+Z
  // undoes the whole generated activity in one step, exactly like insertTemplate("branching", ...)
  // would undo in one step. On any failure -- network error, server-side schema/graph-validity
  // rejection, no provider key -- nothing is mutated: lesson.activities is left exactly as it was.
  function runBranchingScenarioAiAction(lessonKey, lesson) {
    runAiAction({
      flight: { map: aiBranchingRequestInFlight, key: lessonKey },
      request: {
        build: function () {
          var premise = aiBranchingPremiseDraft[lessonKey] || "";
          return buildBranchingScenarioFromPremiseRequest(premise, lesson.title, lesson.objective, buildAiRequestFields());
        },
        send: postAiGenerate,
      },
      result: {
        onSuccess: function (data) {
          // extractBranchingScenarioActivity() is a lighter-weight second check on top of the
          // server's real Pydantic BranchingScenario validation (server.py's
          // _validate_ai_result_schema), which already ran the schema's own graph-integrity check
          // (duplicate node ids / dangling next_node_id) -- see branching-scenario-ai.js's module
          // docstring. On failure here nothing is inserted, same as any other rejection path below.
          var activity = extractBranchingScenarioActivity(data.result, lesson.objective);
          activity.activity_id = uid("act");
          lesson.activities = lesson.activities || [];
          lesson.activities.push(activity);
          // P5-5c: save(true) -- a new branching scenario activity is rendered lesson content, so
          // the inline preview needs to refresh to show it.
          save(true);
          delete aiBranchingPremiseDraft[lessonKey];
          toast("Generated a branching scenario with " + activity.items.length + " scene" + (activity.items.length === 1 ? "" : "s") + ".");
        },
        failureMessage: function (error) {
          return "Branching scenario generation failed: " + error.message;
        },
      },
    });
  }

  // P5-3d: "Translate" AI action. Keyed by a scope key ("block:<cbId>" / "lesson:<lessonKey>" /
  // "course") -- same per-target in-flight guard shape as aiBlockRequestInFlight/
  // aiQuizRequestInFlight above. See translate-block-ai.js's module docstring for the full scope
  // and data-model decision (new locale-tagged sibling block appended after the original, never an
  // in-place overwrite; one AI call per block at every scope).
  var aiTranslateRequestInFlight = {};
  // Free-text target language the author last typed, shared across the block/lesson/course
  // pickers purely as a UI convenience (so switching between scopes doesn't lose what was typed) --
  // it plays no role in undo/save and is never persisted with the course.
  var aiTranslateTargetLanguage = "";

  // Renders the trigger + language input + status for one scope. `flightKey` is this target's
  // aiTranslateRequestInFlight key; `label` is the button copy; `run(language)` performs the
  // request (bound to the right block/lesson/course by the caller).
  function translateActionsSection(flightKey, label, run) {
    var wrap = document.createElement("div");
    wrap.className = "ai-translate-actions";
    wrap.appendChild(sectionLabel("AI actions"));
    var busy = Boolean(aiTranslateRequestInFlight[flightKey]);

    var langInput = document.createElement("input");
    langInput.type = "text";
    langInput.placeholder = "Target language (e.g. Spanish)";
    langInput.value = aiTranslateTargetLanguage;
    langInput.disabled = busy;
    langInput.setAttribute("aria-label", "Target language");
    langInput.addEventListener("change", function () { aiTranslateTargetLanguage = langInput.value; });
    wrap.appendChild(langInput);

    var button = document.createElement("button");
    button.type = "button";
    button.className = "ghost";
    button.textContent = busy ? "Translating…" : label;
    button.disabled = busy;
    button.setAttribute("aria-label", label);
    button.addEventListener("click", function () {
      aiTranslateTargetLanguage = langInput.value;
      run(aiTranslateTargetLanguage);
    });
    wrap.appendChild(button);

    if (busy) {
      var status = document.createElement("p");
      status.className = "hint";
      status.setAttribute("role", "status");
      status.textContent = "Translating — this can take a few seconds…";
      wrap.appendChild(status);
    }
    return wrap;
  }

  // Every content block (in document order) across the whole course that has a non-empty
  // block.text, as {lesson, block} pairs -- used to build the "lesson"/"course" scope's list of
  // per-block AI calls. Blocks with no text are silently skipped (nothing to translate), the same
  // way quiz-from-content-ai.js's buildQuizFromContentRequest skips blank blocks.
  function translatableBlocksOf(lesson) {
    return (lesson.content_blocks || [])
      .filter(function (block) { return block && String(block.text || "").trim(); })
      .map(function (block) { return { lesson: lesson, block: block }; });
  }

  // Shared request/apply/undo path for every scope (block/lesson/course). `targets` is an array of
  // {lesson, block} pairs to translate, one AI call per pair. Nothing is written to any
  // lesson.content_blocks until EVERY request in the batch has resolved successfully -- so a
  // failure anywhere in a multi-block lesson/course translation aborts before any insertion, same
  // as a single failed block translation inserts nothing. On success, translated blocks are
  // inserted immediately after the block they came from (descending original index within each
  // lesson, so earlier insertions in the same lesson don't shift indices still to be used), then
  // committed through save(false)/pushHistory() in one step -- so Ctrl+Z undoes the whole batch at
  // once, exactly like runQuizFromContentAiAction's batch does for generated questions.
  function runTranslateAiAction(scope, flightKey, targets) {
    // Captured by request.build, reused by result.onSuccess -- same single-closure-variable shape as
    // the pre-refactor version (computed once per invocation; the language input is disabled
    // while busy, so it cannot change between the two reads).
    var language;

    runAiAction({
      flight: { map: aiTranslateRequestInFlight, key: flightKey },
      request: {
        build: function () {
          language = String(aiTranslateTargetLanguage || "").trim();
          if (!language) throw new Error("Choose a target language first.");
          if (!targets.length) throw new Error("There is no text here to translate.");
          return targets.map(function (target) {
            return buildTranslateBlockRequest(
              target.block,
              target.lesson.title,
              language,
              target.lesson.content_blocks || [],
              buildAiRequestFields()
            );
          });
        },
        // One AI call per block, batched via Promise.all rather than postAiGenerate's single
        // fetch -- see the module comment above this function's original declaration for why
        // (nothing is written to any lesson.content_blocks until every request in the batch has
        // resolved successfully).
        send: function (bodies) {
          return Promise.all(bodies.map(postAiGenerate)).then(function (dataList) {
            return dataList.map(function (data) { return extractTranslatedText(data.result); });
          });
        },
      },
      result: {
        onSuccess: function (translatedTexts) {
          // Every request in the batch succeeded -- nothing above this line ever touched
          // lesson.content_blocks. Group the (target, translatedText) pairs by lesson so each
          // lesson's array is spliced into once, from the highest original block index down.
          var lessonGroups = [];
          targets.forEach(function (target, i) {
            var group = null;
            for (var g = 0; g < lessonGroups.length; g++) {
              if (lessonGroups[g].lesson === target.lesson) { group = lessonGroups[g]; break; }
            }
            if (!group) { group = { lesson: target.lesson, items: [] }; lessonGroups.push(group); }
            group.items.push({ block: target.block, text: translatedTexts[i] });
          });

          lessonGroups.forEach(function (group) {
            var blocks = group.lesson.content_blocks || (group.lesson.content_blocks = []);
            group.items
              .map(function (entryItem) { return { entryItem: entryItem, index: blocks.indexOf(entryItem.block) }; })
              .filter(function (entry) { return entry.index !== -1; })
              .sort(function (a, b) { return b.index - a.index; }) // highest index first
              .forEach(function (entry) {
                var text = entry.entryItem.text;
                // A brand-new block, tagged with `language`/`translated_from` -- the ORIGINAL block
                // object (entry.entryItem.block) is never written to here or anywhere above.
                blocks.splice(entry.index + 1, 0, {
                  id: uid("cb"),
                  type: entry.entryItem.block.type,
                  text: text,
                  text_html: sanitizeRichTextHtml("<p>" + escapeHtml(text) + "</p>"),
                  language: language,
                  translated_from: entry.entryItem.block.id,
                });
              });
          });

          // P5-5c: save(true) -- the newly-inserted translated blocks are rendered lesson content,
          // so the inline preview needs to refresh to show them.
          save(true);
          toast(
            "Translated " + targets.length + " block" + (targets.length === 1 ? "" : "s") +
            " into " + language + "."
          );
        },
        failureMessage: function (error) {
          // No lesson.content_blocks array is mutated above unless every request in the batch
          // resolved successfully, so a rejection here (network error, missing provider key, a
          // malformed response for any ONE block) leaves every original and every other in-flight
          // block's content exactly as it was -- nothing partial is ever inserted.
          return "Translation failed: " + error.message;
        },
      },
    });
  }

  // P5-3e: "Generate alt text" AI action on an image block's media.alt field. Keyed by content
  // block id, same per-target in-flight guard shape as aiBlockRequestInFlight/
  // aiQuizRequestInFlight/aiTranslateRequestInFlight above. See alt-text-ai.js's module docstring
  // for the text-only (context-based, not real vision) scope decision.
  var aiAltTextRequestInFlight = {};

  // `block` is the owning content block; `lessonTitle` is the owning lesson's title, threaded
  // through from the block inspector's mediaEditor(block, lessonTitle) call so the request has
  // the same lesson-title context every other per-block AI action gets.
  function altTextActionsSection(block, lessonTitle) {
    var wrap = document.createElement("div");
    wrap.className = "ai-alt-text-actions";
    var busy = Boolean(aiAltTextRequestInFlight[block.id]);
    var button = document.createElement("button");
    button.type = "button";
    button.className = "ghost";
    var media = block.media || {};
    var hasExisting = Boolean(String(media.alt || "").trim());
    var label = hasExisting ? "Regenerate alt text" : "Generate alt text";
    button.textContent = busy ? "Generating…" : label;
    button.disabled = busy;
    button.setAttribute("aria-label", label + " for this image with AI");
    button.addEventListener("click", function () { runAltTextAiAction(block, lessonTitle); });
    wrap.appendChild(button);
    var note = document.createElement("p");
    note.className = "hint";
    note.textContent = busy ? "Generating alt text…" : ALT_TEXT_CONTEXT_ONLY_NOTE;
    if (busy) note.setAttribute("role", "status");
    wrap.appendChild(note);
    return wrap;
  }

  function runAltTextAiAction(block, lessonTitle) {
    var existingAlt = String((block.media && block.media.alt) || "").trim();
    // Never silently overwrite a non-empty existing alt text -- confirm first, same
    // confirm()-before-destructive-action pattern used elsewhere in this file (e.g. the
    // Delete '<label>'? confirms above). Unlike runOutlineRegenerateAiAction's always-on confirm
    // gate, this one only fires when there's actually something to overwrite.
    var confirmMessage = existingAlt
      ? "This will replace the existing alt text:\n\n\"" + existingAlt + "\"\n\nContinue?"
      : null;

    runAiAction({
      flight: { map: aiAltTextRequestInFlight, key: block.id },
      confirm: confirmMessage,
      request: {
        build: function () {
          return buildAltTextRequest(block, lessonTitle, buildAiRequestFields());
        },
        send: postAiGenerate,
      },
      result: {
        onSuccess: function (data) {
          var text = extractAltText(data.result);
          var stillThere = findBlock(block.id);
          if (!stillThere || !stillThere.block.media || stillThere.block.media.kind !== "image") return; // block/media removed while in flight
          // Same save()/pushHistory() path every other block/media edit uses (see mediaEditor's
          // set(), which also passes true) -- so Ctrl+Z genuinely undoes an AI-generated alt text
          // exactly like a manual edit, and the inline preview's rendered <img alt> stays in sync.
          stillThere.block.media.alt = text;
          save(true);
          toast("Alt text generated.");
        },
        failureMessage: function (error) {
          // Original media.alt is untouched -- we only ever write to it inside the success branch
          // above, never here.
          return "Alt text generation failed: " + error.message;
        },
      },
      rerender: function () {
        if (state.selected.kind === "block" && state.selected.cbId === block.id) renderInspector();
      },
    });
  }

  function mediaEditor(owner, lessonTitle) {
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
        wrap.appendChild(altTextActionsSection(owner, lessonTitle));
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

  // Ordered dispatch table for activityEditor()'s type-specific fields,
  // mirroring the pattern used server-side by renderNativeActivity() in
  // exporters/scorm.py (an ordered array of {match, render} tested in
  // order, first match wins). This is intentionally a *separate* table from
  // ACTIVITY_TEMPLATE_REGISTRY above rather than folded into it: the
  // registry above is keyed by template id (one id -> one default shape),
  // while this dispatch is keyed by activity_type substring matching against
  // whatever is already saved on the activity, and one entry here
  // ("scenes") is deliberately shared by two different template ids
  // (decision -> scenario_decision_tree, branching -> branching_scenario) --
  // collapsing that into a by-template-id map would either duplicate the
  // scenes editor or change which fields render for a given saved
  // activity_type, so the two tables stay independent lookups over
  // different keyspaces, same as the original code (which already had this
  // split between TEMPLATES/templatePayload's switch-by-id and this
  // function's if/else-if-by-substring -- confirmed while doing this
  // refactor, not assumed).
  var ACTIVITY_INSPECTORS = [
    {
      key: "flashcard",
      match: function (type) { return type.indexOf("flashcard") >= 0; },
      render: function (activity, box, refresh) {
        box.appendChild(sectionLabel("Cards"));
        box.appendChild(itemListEditor(activity.items = activity.items || [], [
          { key: "front", label: "Front (term)" },
          { key: "back", label: "Back (answer)", area: true },
        ], refresh, "+ Add card", { front: "", back: "" }));
      },
    },
    {
      key: "matching",
      match: function (type) { return type.indexOf("matching") >= 0; },
      render: function (activity, box, refresh) {
        box.appendChild(sectionLabel("Pairs"));
        box.appendChild(itemListEditor(activity.items = activity.items || [], [
          { key: "prompt", label: "Prompt" },
          { key: "match", label: "Match" },
        ], refresh, "+ Add pair", { prompt: "", match: "" }));
      },
    },
    {
      key: "accordion",
      match: function (type) { return type.indexOf("accordion") >= 0 || type.indexOf("tabs") >= 0; },
      render: function (activity, box, refresh) {
        box.appendChild(sectionLabel("Sections"));
        box.appendChild(itemListEditor(activity.items = activity.items || [], [
          { key: "title", label: "Title" },
          { key: "detail", label: "Detail", area: true },
        ], refresh, "+ Add section", { title: "", detail: "" }));
      },
    },
    {
      key: "timeline",
      match: function (type) { return type.indexOf("timeline") >= 0; },
      render: function (activity, box, refresh) {
        box.appendChild(sectionLabel("Steps"));
        box.appendChild(itemListEditor(activity.items = activity.items || [], [
          { key: "label", label: "Step label" },
          { key: "detail", label: "Detail", area: true },
        ], refresh, "+ Add step", { label: "", detail: "" }));
      },
    },
    {
      key: "fill_blank",
      match: function (type) { return type.indexOf("fill_blank") >= 0; },
      render: function (activity, box, refresh) {
        var text = textInput(activity.text || "", function (value) { activity.text = value; save(true); }, "area");
        text.placeholder = "Passage text -- mark each blank with {{blank}}";
        box.appendChild(field("Text (use {{blank}} for each blank)", text));
        box.appendChild(sectionLabel("Blanks (one row per {{blank}}, in order)"));
        var blanks = activity.blanks = activity.blanks || [];
        var blankCount = countBlankTokens(activity.text);
        if (blankCount !== blanks.length) {
          var hint = document.createElement("p");
          hint.className = "hint";
          hint.textContent = "Text has " + blankCount + " {{blank}} token" + (blankCount === 1 ? "" : "s") + " but " + blanks.length + " answer row" + (blanks.length === 1 ? "" : "s") + " -- add or remove rows to match.";
          box.appendChild(hint);
        }
        box.appendChild(itemListEditor(blanks, [
          { key: "answers", label: "Accepted answer(s), comma-separated" },
        ], refresh, "+ Add blank", { answers: "" }));
      },
    },
    {
      key: "scenes",
      match: function (type) { return type.indexOf("branching") >= 0 || type.indexOf("scenario") >= 0 || type.indexOf("decision") >= 0; },
      render: function (activity, box) {
        var type = String(activity.activity_type || activity.type || "");
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
      },
    },
    {
      key: "hotspot",
      match: function (type) { return type.indexOf("hotspot") >= 0; },
      // Region-drawing UI (P5-4c). Author uploads/URLs an image, then click-drags directly on
      // it to draw a rectangle; on mouseup the drawn pixel rectangle is converted to PERCENTAGES
      // of the rendered <img>'s own displayed box via computeRegionPercentages() (hotspot-
      // geometry.js) -- not the inspector panel's box -- so a region survives the image being
      // shown at any size, matching the responsive contract renderHotspotActivity() relies on
      // server-side. Deliberately out of scope for this first version: drag-to-move/resize an
      // EXISTING region. Draw-new + delete covers the common authoring flow; the four number
      // inputs per region below are the documented fallback for nudging an existing region's
      // exact coordinates instead of building resize handles.
      render: function (activity, box, refresh) {
        activity.image = activity.image || { src: "", alt: "" };
        activity.regions = activity.regions || [];
        var image = activity.image;

        box.appendChild(sectionLabel("Image"));
        box.appendChild(field("Alt text", textInput(image.alt || "", function (value) { image.alt = value; save(true); })));

        function setImageSrc(src) {
          image.src = src;
          save(true);
          refresh();
        }

        function uploadHotspotImage(file) {
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
                setImageSrc(data.src);
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
          uploadHotspotImage(event.target.files[0]);
        });
        wireFileDropZone(upload, "drag-active", uploadHotspotImage);
        box.appendChild(upload);

        box.appendChild(field("Image URL (https… or assets/media/…)", textInput(image.src || "", function (value) { setImageSrc(value); }, "url")));

        if (!image.src) {
          var hint = document.createElement("p");
          hint.className = "hint";
          hint.textContent = "Upload or set an image URL to start drawing hotspot regions.";
          box.appendChild(hint);
          return;
        }

        box.appendChild(sectionLabel("Draw a region — click and drag on the image"));
        var drawWrap = document.createElement("div");
        drawWrap.className = "hotspot-draw-wrap";
        drawWrap.style.position = "relative";
        drawWrap.style.display = "inline-block";
        drawWrap.style.maxWidth = "100%";
        drawWrap.style.cursor = "crosshair";
        drawWrap.style.userSelect = "none";
        var img = document.createElement("img");
        img.src = withToken("/course/" + state.session + "/" + image.src);
        img.alt = "";
        img.draggable = false;
        img.style.display = "block";
        img.style.width = "420px";
        img.style.maxWidth = "100%";
        img.style.height = "auto";
        drawWrap.appendChild(img);

        // Existing regions rendered as read-only overlays for visual reference while drawing.
        activity.regions.forEach(function (region) {
          var marker = document.createElement("div");
          marker.style.position = "absolute";
          marker.style.left = (region.x_pct || 0) + "%";
          marker.style.top = (region.y_pct || 0) + "%";
          marker.style.width = (region.width_pct || 0) + "%";
          marker.style.height = (region.height_pct || 0) + "%";
          marker.style.border = "2px solid " + (region.tag === "correct" ? "#16a34a" : region.tag === "incorrect" ? "#dc2626" : "#2563eb");
          marker.style.background = "rgba(37, 99, 235, .12)";
          marker.style.boxSizing = "border-box";
          marker.style.pointerEvents = "none";
          drawWrap.appendChild(marker);
        });

        function updateDragBox(dragBox, startRect, start, current) {
          var left = Math.min(start.x, current.x) - startRect.left;
          var top = Math.min(start.y, current.y) - startRect.top;
          dragBox.style.left = left + "px";
          dragBox.style.top = top + "px";
          dragBox.style.width = Math.abs(current.x - start.x) + "px";
          dragBox.style.height = Math.abs(current.y - start.y) + "px";
        }

        drawWrap.addEventListener("mousedown", function (event) {
          if (event.target !== img) return;
          event.preventDefault();
          var startRect = img.getBoundingClientRect();
          var start = { x: event.clientX, y: event.clientY };
          var dragBox = document.createElement("div");
          dragBox.style.position = "absolute";
          dragBox.style.border = "2px dashed #2563eb";
          dragBox.style.background = "rgba(37, 99, 235, .15)";
          dragBox.style.boxSizing = "border-box";
          dragBox.style.pointerEvents = "none";
          drawWrap.appendChild(dragBox);
          updateDragBox(dragBox, startRect, start, start);

          function onMove(moveEvent) {
            updateDragBox(dragBox, startRect, start, { x: moveEvent.clientX, y: moveEvent.clientY });
          }
          function onUp(upEvent) {
            document.removeEventListener("mousemove", onMove);
            document.removeEventListener("mouseup", onUp);
            var end = { x: upEvent.clientX, y: upEvent.clientY };
            dragBox.remove();
            var drawnRect = rectFromPoints(
              { x: start.x - startRect.left, y: start.y - startRect.top },
              { x: end.x - startRect.left, y: end.y - startRect.top }
            );
            if (!isRegionSizeUsable(drawnRect)) return; // treat as a stray click, not a drawn region
            var displayedRect = { left: 0, top: 0, width: startRect.width, height: startRect.height };
            var pct = computeRegionPercentages(displayedRect, drawnRect);
            activity.regions.push(Object.assign({ tag: "correct", feedback: "", label: "" }, pct));
            save(true);
            refresh();
          }
          document.addEventListener("mousemove", onMove);
          document.addEventListener("mouseup", onUp);
        });

        box.appendChild(drawWrap);

        box.appendChild(sectionLabel("Regions (" + activity.regions.length + ")"));
        activity.regions.forEach(function (region, index) {
          var row = document.createElement("div");
          row.className = "item-row";
          var head = document.createElement("div");
          head.className = "item-row-head";
          head.innerHTML = "<span>Region " + (index + 1) + "</span><button type=\"button\" title=\"Remove\">✕</button>";
          head.querySelector("button").addEventListener("click", function () {
            activity.regions.splice(index, 1);
            save(true);
            refresh();
          });
          row.appendChild(head);

          var labelInput = textInput(region.label || "", function (value) { region.label = value; save(true); });
          labelInput.placeholder = "Label (for screen readers / interaction log)";
          row.appendChild(labelInput);

          row.appendChild(selectInput(region.tag || "correct", ["correct", "incorrect", "informational"], function (value) { region.tag = value; save(true); }));

          var feedbackInput = textInput(region.feedback || "", function (value) { region.feedback = value; save(true); }, "area");
          feedbackInput.placeholder = "Feedback shown when this region is clicked";
          row.appendChild(feedbackInput);

          var coordsWrap = document.createElement("div");
          coordsWrap.style.display = "grid";
          coordsWrap.style.gridTemplateColumns = "repeat(4, 1fr)";
          coordsWrap.style.gap = "6px";
          [["x_pct", "X %"], ["y_pct", "Y %"], ["width_pct", "W %"], ["height_pct", "H %"]].forEach(function (pair) {
            var key = pair[0];
            var input = document.createElement("input");
            input.type = "number";
            input.min = "0";
            input.max = "100";
            input.step = "0.1";
            input.title = pair[1];
            input.value = Number(region[key] || 0).toFixed(1);
            input.addEventListener("change", function () {
              region[key] = Math.min(100, Math.max(0, Number(input.value) || 0));
              save(true);
            });
            coordsWrap.appendChild(input);
          });
          row.appendChild(coordsWrap);

          box.appendChild(row);
        });
      },
    },
    {
      key: "sorting",
      match: function (type) { return type.indexOf("sorting") >= 0 || type.indexOf("ranking") >= 0; },
      // The list order here IS the answer key (no separate "correct order" field), so unlike
      // itemListEditor()'s add/remove-only rows, each row needs its own move-up/move-down
      // control -- reusing moveItem() (already used above for tree drag/keyboard reordering)
      // rather than inventing a new reorder primitive. The row/head markup mirrors the "scenes"
      // and "hotspot" entries' custom item-row layout above rather than itemListEditor's, since
      // itemListEditor has no move affordance.
      render: function (activity, box, refresh) {
        box.appendChild(sectionLabel("Items, in correct order (the learner sees them shuffled)"));
        var items = activity.items = activity.items || [];
        items.forEach(function (item, index) {
          var row = document.createElement("div");
          row.className = "item-row";
          var head = document.createElement("div");
          head.className = "item-row-head";
          head.innerHTML = "<span>#" + (index + 1) + "</span>";
          var moveUp = document.createElement("button");
          moveUp.type = "button";
          moveUp.title = "Move up";
          moveUp.textContent = "↑";
          moveUp.disabled = index === 0;
          moveUp.addEventListener("click", function () { moveItem(items, index, index - 1); save(true); refresh(); });
          var moveDown = document.createElement("button");
          moveDown.type = "button";
          moveDown.title = "Move down";
          moveDown.textContent = "↓";
          moveDown.disabled = index === items.length - 1;
          moveDown.addEventListener("click", function () { moveItem(items, index, index + 1); save(true); refresh(); });
          var remove = document.createElement("button");
          remove.type = "button";
          remove.title = "Remove";
          remove.textContent = "✕";
          remove.addEventListener("click", function () { items.splice(index, 1); save(true); refresh(); });
          head.appendChild(moveUp);
          head.appendChild(moveDown);
          head.appendChild(remove);
          row.appendChild(head);
          var text = textInput(item.text || "", function (value) { item.text = value; save(true); });
          text.placeholder = "Item text";
          row.appendChild(text);
          box.appendChild(row);
        });
        var add = document.createElement("button");
        add.className = "add-item";
        add.type = "button";
        add.textContent = "+ Add item";
        add.addEventListener("click", function () {
          items.push({ text: "" });
          save(true);
          refresh();
        });
        box.appendChild(add);
      },
    },
  ];

  function renderGenericActivityInspector(activity, box, refresh) {
    box.appendChild(sectionLabel("Items (generic)"));
    box.appendChild(itemListEditor(activity.items = activity.items || [], [
      { key: "prompt", label: "Prompt" },
      { key: "detail", label: "Detail", area: true },
    ], refresh, "+ Add item", { prompt: "", detail: "" }));
  }

  function activityEditor(activity) {
    var box = document.createElement("div");
    box.style.display = "grid";
    box.style.gap = "12px";
    var type = String(activity.activity_type || activity.type || "");
    box.appendChild(field("Title", textInput(activity.title, function (value) { activity.title = value; save(true); })));
    box.appendChild(field("Instructions / objective", textInput(activity.objective || activity.instructions, function (value) { activity.objective = value; save(true); }, "area")));

    var refresh = function () { save(true); };
    var entry = ACTIVITY_INSPECTORS.find(function (candidate) { return candidate.match(type); });
    (entry ? entry.render : renderGenericActivityInspector)(activity, box, refresh);
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
      // P5-3d, "whole course" scope: translates every content block in every lesson of the
      // course, one AI call per block (see translate-block-ai.js's module docstring for why this
      // is a deliberate scope-down from a duplicated locale-tagged course entity). Each
      // translated block is appended right after the block it came from, in that block's own
      // lesson -- nothing is committed unless every block's translation succeeds.
      box.appendChild(translateActionsSection(
        "course",
        "Translate whole course",
        function () {
          var targets = [];
          lessonsOf(course).forEach(function (row) {
            targets = targets.concat(translatableBlocksOf(row.lesson));
          });
          runTranslateAiAction("course", "course", targets);
        }
      ));
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
      // P5-5e: an alternative to the blank-lesson button above -- picking a skeleton here builds
      // a fully-formed lesson (blocks/activities/quiz already shaped, generic placeholder text)
      // via lesson-skeletons.js and pushes it into module.lessons exactly like the blank-lesson
      // button does, through the same save(true)/pushHistory() undo-stack path. "+ Add lesson"
      // above is completely untouched and stays the default -- this is purely additive.
      box.appendChild(lessonSkeletonPicker(module));
      // P5-5f, module scope: lets the author ask AI to regenerate this module's WHOLE `lessons`
      // array (titles + block-role skeletons) from brief guidance -- see
      // outline-regenerate-ai.js's module docstring for the structure-only decision and
      // runOutlineRegenerateAiAction's own comment for why the confirm() gate fires before the
      // AI request is even sent. Lives in the module inspector, next to the other
      // module-structure actions above (blank lesson / skeleton picker).
      box.appendChild(outlineRegenerateActionsSection(
        "module",
        "module:" + sel.mi,
        "Regenerate this module's outline",
        function () {
          var lessonCount = (module.lessons || []).length;
          var confirmMessage = "This will REPLACE all " + lessonCount + " lesson" + (lessonCount === 1 ? "" : "s") +
            " in \"" + module.title + "\" with a newly-generated outline (titles + block skeletons only). " +
            "This cannot be undone except with Ctrl+Z. Continue?";
          runOutlineRegenerateAiAction(
            "module",
            "module:" + sel.mi,
            confirmMessage,
            function () { return { title: module.title, lessons: (module.lessons || []).map(function (l) { return { title: l.title }; }) }; },
            function (result) {
              var lessons = extractRegeneratedModuleOutline(result, uid, module.objective_ids || []);
              module.lessons = lessons;
              return lessons.length + " lesson" + (lessons.length === 1 ? "" : "s");
            }
          );
        }
      ));
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
      // P5-3c, "whole lesson" scope: generates a quiz from every content block in this lesson
      // (in document order) and appends the results to lesson.quiz_questions. Lives in the lesson
      // inspector (rather than e.g. the Structure tab) because that's where every other
      // lesson-level action already is (title/objective/duration fields above).
      box.appendChild(quizFromContentActionsSection(
        "lesson:" + sel.key,
        "Generate quiz from this lesson",
        function () { runQuizFromContentAiAction("lesson", "lesson:" + sel.key, lesson, lesson.content_blocks || []); }
      ));
      // P5-3f: generates a brand-new branching character scene activity from an author-supplied
      // premise and appends it to lesson.activities. Lives in the lesson inspector for the same
      // reason the quiz action above does -- every other lesson-level AI action is already here.
      box.appendChild(branchingScenarioActionsSection(sel.key, lesson));
      // P5-3d, "current lesson" scope: translates every content block in this lesson, one AI
      // call per block, each translated block appended right after the block it came from.
      box.appendChild(translateActionsSection(
        "lesson:" + sel.key,
        "Translate this lesson",
        function () { runTranslateAiAction("lesson", "lesson:" + sel.key, translatableBlocksOf(lesson)); }
      ));
      // P5-5f, lesson scope: lets the author ask AI to regenerate this lesson's block-role
      // skeleton from brief guidance -- see outline-regenerate-ai.js's module docstring for the
      // structure-only decision. Replaces lesson.content_blocks wholesale and resets
      // lesson.activities/lesson.quiz_questions to empty (both were authored against the OLD
      // block outline and have no meaningful mapping onto a freshly-regenerated one -- see this
      // module's own header comment and outline-regenerate-ai.js's for the reasoning).
      box.appendChild(outlineRegenerateActionsSection(
        "lesson",
        "lesson:" + sel.key,
        "Regenerate this lesson's outline",
        function () {
          var blockCount = (lesson.content_blocks || []).length;
          var activityCount = (lesson.activities || []).length;
          var questionCount = (lesson.quiz_questions || []).length;
          var confirmMessage = "This will REPLACE all " + blockCount + " content block" + (blockCount === 1 ? "" : "s") +
            " in \"" + lesson.title + "\" with a newly-generated outline (roles only), and CLEAR its " +
            activityCount + " activit" + (activityCount === 1 ? "y" : "ies") + " and " + questionCount +
            " quiz question" + (questionCount === 1 ? "" : "s") + " (they no longer match the new outline). " +
            "This cannot be undone except with Ctrl+Z. Continue?";
          runOutlineRegenerateAiAction(
            "lesson",
            "lesson:" + sel.key,
            confirmMessage,
            function () {
              return {
                title: lesson.title,
                objective: lesson.objective,
                blocks: (lesson.content_blocks || []).map(function (b) { return { role: b.type }; }),
              };
            },
            function (result) {
              var outline = extractRegeneratedLessonOutline(result, uid);
              lesson.objective = outline.objective;
              lesson.content_blocks = outline.content_blocks;
              lesson.activities = [];
              lesson.quiz_questions = [];
              return outline.content_blocks.length + " block" + (outline.content_blocks.length === 1 ? "" : "s");
            }
          );
        }
      ));
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
      box.appendChild(aiBlockActionsSection(block));
      // P5-3c, "single block" scope: generates a quiz from just this block's text and appends the
      // results to the owning lesson's lesson.quiz_questions (not the block itself -- a quiz
      // question is not a content-block-shaped thing in this schema).
      box.appendChild(quizFromContentActionsSection(
        "block:" + block.id,
        "Generate quiz from this block",
        function () { runQuizFromContentAiAction("block", "block:" + block.id, foundBlock.row.lesson, [block]); }
      ));
      // P5-3d, "block" scope: translates just this block, appending the translation as a new
      // sibling block right after it -- the original block above is never overwritten.
      box.appendChild(translateActionsSection(
        "block:" + block.id,
        "Translate this block",
        function () { runTranslateAiAction("block", "block:" + block.id, [{ lesson: foundBlock.row.lesson, block: block }]); }
      ));
      box.appendChild(sectionLabel("Media"));
      box.appendChild(mediaEditor(block, foundBlock.row.lesson.title));
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
      $("tab-ai").hidden = tab.dataset.tab !== "ai";
      if (tab.dataset.tab === "review") renderReview();
      if (tab.dataset.tab === "sources") renderSources();
      if (tab.dataset.tab === "ai") renderAiSettings();
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
    state.saveStatus = initialSaveStatus();
    setSaveStatus("Saved · revision " + state.version);
    var retryBtn = $("btn-save-retry");
    if (retryBtn) retryBtn.hidden = true;
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
    state.undoStack = createUndoStack(50);
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
  $("btn-save-retry").addEventListener("click", retrySave);
  // Coarse refresh so "Saved just now" ages into "Saved 2 minutes ago" etc.
  // without a live-ticking clock -- accurate enough, no need for anything finer.
  setInterval(function () { if (state.saveStatus.phase === "saved") renderSaveIndicator(); }, 30000);
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
