"use strict";
/*
 * Lightweight DOM-simulation harness for exercising renderFillBlankActivity()
 * from the exported SCORM player.js (see src/course_mcp_server/exporters/scorm.py
 * -> _player_js()). This is deliberately NOT a full browser/jsdom harness --
 * jsdom is not a dependency of this repo and the fill-blank renderer only touches
 * a small, well-known slice of the DOM API (innerHTML assignment producing
 * <input>/<button>/<p> tags, querySelector/querySelectorAll by tag or single
 * class, classList add/toggle/contains, addEventListener("click", ...),
 * textContent). We hand-roll just that slice so the test exercises the ACTUAL
 * renderer function -- inputs get created, the click handler runs for real,
 * completion state is read back off fake classList/textContent -- rather than
 * just grepping the JS source string.
 *
 * Usage: node fill_blank_harness.js <path-to-player.js>
 * Exits 0 and prints "OK" on success. Throws (non-zero exit) on any failed
 * assertion, with node's default stack trace pointing at the failing check.
 */

const fs = require("fs");
const assert = require("assert");
const vm = require("vm");

const playerJsPath = process.argv[2];
if (!playerJsPath) {
  console.error("usage: node fill_blank_harness.js <path-to-player.js>");
  process.exit(2);
}
const playerJsSource = fs.readFileSync(playerJsPath, "utf-8");

// ---- minimal fake DOM ---------------------------------------------------

function makeClassList(initial) {
  const set = new Set((initial || "").split(/\s+/).filter(Boolean));
  return {
    add(c) { set.add(c); },
    remove(c) { set.delete(c); },
    toggle(c, force) {
      if (force === undefined) {
        if (set.has(c)) { set.delete(c); return false; }
        set.add(c);
        return true;
      }
      if (force) set.add(c); else set.delete(c);
      return force;
    },
    contains(c) { return set.has(c); },
  };
}

function parseAttrs(attrString) {
  const attrs = {};
  const attrRe = /([\w-]+)(?:\s*=\s*"([^"]*)")?/g;
  let m;
  while ((m = attrRe.exec(attrString || ""))) {
    attrs[m[1]] = m[2] === undefined ? "" : m[2];
  }
  return attrs;
}

function makeElement(tag, attrString, textContent) {
  const attrs = parseAttrs(attrString);
  return {
    tag,
    attrs,
    className: attrs.class || "",
    classList: makeClassList(attrs.class),
    value: "",
    textContent: textContent === undefined ? "" : textContent,
    _listeners: {},
    addEventListener(type, handler) {
      (this._listeners[type] = this._listeners[type] || []).push(handler);
    },
    click() {
      (this._listeners.click || []).forEach((handler) => handler());
    },
  };
}

// Flat (non-hierarchical) scan for the handful of tags the fill-blank
// renderer's templates ever emit. Flat is sufficient here: every query the
// renderer makes (body.querySelector("button"), body.querySelectorAll(".fill-blank-input"))
// is issued directly against `body`, never against an intermediate parent, so
// we don't need real parent/child structure -- just "does this tag/class
// appear anywhere in the innerHTML string".
function parseHtml(html) {
  const elements = [];
  const inputRe = /<input\b([^>]*?)\/?>/gi;
  let m;
  while ((m = inputRe.exec(html))) {
    elements.push(makeElement("input", m[1]));
  }
  const containerRe = /<(button|p|div|span|h3)\b([^>]*?)>([\s\S]*?)<\/\1>/gi;
  while ((m = containerRe.exec(html))) {
    const inner = m[3].replace(/<[^>]*>/g, "").trim();
    elements.push(makeElement(m[1], m[2], inner));
  }
  return elements;
}

function makeBody() {
  return {
    _html: "",
    _elements: [],
    get innerHTML() { return this._html; },
    set innerHTML(v) {
      this._html = v;
      this._elements = parseHtml(v);
    },
    _match(sel) {
      if (sel.startsWith(".")) {
        const cls = sel.slice(1);
        return this._elements.filter((e) => e.classList.contains(cls));
      }
      return this._elements.filter((e) => e.tag === sel);
    },
    querySelector(sel) { return this._match(sel)[0] || null; },
    querySelectorAll(sel) { return this._match(sel); },
  };
}

function makeCard() {
  const statusEl = makeElement("span", 'class="activity-status"', "");
  return {
    classList: makeClassList("activity-card"),
    querySelector(sel) { return sel === ".activity-status" ? statusEl : null; },
    _statusEl: statusEl,
  };
}

// ---- fake globals the eval'd player.js needs at parse/boot time ---------

const sandbox = {
  console,
  document: {
    getElementById() { return null; },
    querySelector() { return null; },
    querySelectorAll() { return []; },
    addEventListener() {},
    body: { dataset: {} },
  },
  localStorage: {
    _store: {},
    setItem(k, v) { this._store[k] = v; },
    getItem(k) { return Object.prototype.hasOwnProperty.call(this._store, k) ? this._store[k] : null; },
  },
  window: {},
  fetch: undefined,
  CourseScorm: {
    setSuspendData() {},
    setLocation() {},
    recordInteraction() {},
  },
};
sandbox.window = sandbox;
sandbox.globalThis = sandbox;
vm.createContext(sandbox);

// bootCoursePlayer() runs at the bottom of player.js as a top-level call; with
// document.querySelector("[data-course-player], [data-module-page]") stubbed
// to return null it exits immediately (see the `if (!root) return;` guard),
// so evaluating the whole file here has no other side effects.
vm.runInContext(playerJsSource, sandbox, { filename: "player.js" });

const renderFillBlankActivity = sandbox.renderFillBlankActivity;
assert.strictEqual(typeof renderFillBlankActivity, "function", "renderFillBlankActivity must be defined by player.js");

function baseCtx(activity, overrides) {
  const card = makeCard();
  const body = makeBody();
  const feedback = makeElement("div", "", "");
  return Object.assign({
    activity,
    card,
    body,
    feedback,
    course: { course_slug: "test-course" },
    index: 0,
    activityId: "activity-1",
    state: {},
  }, overrides || {});
}

// ---- Fix 1: zero {{blank}} tokens must not produce a permanently-stuck
//      "incorrect" state ----------------------------------------------------
{
  const activity = {
    text: "This text used to have a blank but the token got removed by an edit.",
    blanks: [{ answers: ["something"] }],
  };
  const ctx = baseCtx(activity);
  renderFillBlankActivity(ctx);

  const inputs = ctx.body.querySelectorAll(".fill-blank-input");
  assert.strictEqual(inputs.length, 0, "expected zero inputs when text has zero {{blank}} tokens");

  const button = ctx.body.querySelector("button");
  assert.strictEqual(button, null, "expected no Check-answers button when there is nothing to check");

  assert.strictEqual(ctx.card.classList.contains("completed"), true,
    "a zero-blank activity must not be permanently uncompletable -- it should be treated as informational and marked complete");
  assert.notStrictEqual(ctx.feedback.textContent, "Some blanks are incorrect. Review the highlighted inputs and try again.",
    "must not show the broken always-incorrect message when there is nothing to check");
}

// ---- Fix 2: an unconfigured (empty accepted-answers) blank must NEVER be
//      markable correct, no matter what the learner types --------------------
{
  const activity = {
    text: "Fill in: {{blank}}.",
    blanks: [{ answers: [] }], // no accepted answers configured for this blank
  };
  const ctx = baseCtx(activity);
  renderFillBlankActivity(ctx);

  const input = ctx.body.querySelector(".fill-blank-input") || ctx.body.querySelectorAll("input")[0];
  assert.ok(input, "expected one input to be rendered for the single {{blank}} token");
  input.value = "literally anything the learner types";

  const button = ctx.body.querySelector("button");
  assert.ok(button, "expected a Check-answers button when there is a real blank to check");
  button.click();

  assert.strictEqual(input.classList.contains("is-correct"), false,
    "an unconfigured blank must never be flagged is-correct");
  assert.strictEqual(input.classList.contains("is-incorrect"), true,
    "an unconfigured blank must be flagged is-incorrect regardless of input");
  assert.strictEqual(ctx.card.classList.contains("completed"), false,
    "the activity must not auto-complete when a blank has no configured accepted answers");
}

// ---- Regression: a normal, well-configured blank still behaves correctly --
{
  const activity = {
    text: "The capital of France is {{blank}}.",
    blanks: [{ answers: ["Paris"] }],
  };
  const ctx = baseCtx(activity);
  renderFillBlankActivity(ctx);

  const input = ctx.body.querySelector(".fill-blank-input");
  assert.ok(input, "expected one input for the configured blank");
  input.value = "paris"; // case-insensitive match

  ctx.body.querySelector("button").click();

  assert.strictEqual(input.classList.contains("is-correct"), true, "correctly-answered configured blank should be marked correct");
  assert.strictEqual(ctx.card.classList.contains("completed"), true, "activity should complete once every blank is answered correctly");
  assert.strictEqual(ctx.feedback.textContent, "All blanks correct. Nice work.");
}

// ---- Fix 3: zero-{{blank}}-token auto-completion must NOT award the
//      "Practice Pro" badge (no genuine learner interaction happened), while a
//      normal, well-answered fill-blank activity still DOES award it -------
function readSavedState(courseSlug) {
  const raw = sandbox.localStorage.getItem(`course-state:${courseSlug}`);
  return raw ? JSON.parse(raw) : null;
}

{
  // zero-blank case: no badge should be awarded.
  const activity = {
    text: "This text used to have a blank but the token got removed by an edit.",
    blanks: [{ answers: ["something"] }],
  };
  const course = { course_slug: "zero-blank-course" };
  const ctx = baseCtx(activity, { course, state: {} });
  renderFillBlankActivity(ctx);

  const saved = readSavedState("zero-blank-course");
  assert.ok(saved, "expected state to be saved even for the zero-blank informational auto-completion");
  assert.deepStrictEqual(saved.badges || [], [],
    "zero-blank auto-completion must NOT award the Practice Pro badge -- no genuine learner interaction occurred");
  assert.ok(Array.isArray(saved.completedActivities) && saved.completedActivities.includes(ctx.activityId),
    "the activity should still be tracked as completed/addressed for progress-bar purposes");
}

{
  // regression: a normal, well-answered fill-blank activity still awards the badge.
  const activity = {
    text: "The capital of France is {{blank}}.",
    blanks: [{ answers: ["Paris"] }],
  };
  const course = { course_slug: "normal-blank-course" };
  const ctx = baseCtx(activity, { course, state: {} });
  renderFillBlankActivity(ctx);

  let saved = readSavedState("normal-blank-course");
  assert.strictEqual(saved, null, "no state should be saved until the learner actually checks their answer");

  const input = ctx.body.querySelector(".fill-blank-input");
  input.value = "Paris";
  ctx.body.querySelector("button").click();

  saved = readSavedState("normal-blank-course");
  assert.ok(saved, "expected state to be saved once the activity is genuinely completed");
  assert.ok((saved.badges || []).includes("Practice Pro"),
    "a genuinely completed (correctly-answered) fill-blank activity must still award the Practice Pro badge");
}

console.log("OK");
