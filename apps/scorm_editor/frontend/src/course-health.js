// P5-5d: pure, client-side "course health" checklist that scans the in-memory course document
// (state.course in editor.js) for common authoring gaps before export. This is deliberately
// advisory only -- nothing here blocks export.py's /api/export/<sid> flow; editor.js's
// "Course health" panel (Review tab) surfaces these findings alongside the existing export
// button, it never disables it.
//
// No DOM access here, following the same pure-module pattern as move-between-lists.js,
// quiz-from-content-ai.js, etc: editor.js owns rendering the results, this module only computes
// them from a plain course object so it is unit-testable on its own.

import { countBlankTokens, normalizeAnswers } from "./fill-blank.js";

export var CATEGORY_MISSING_ALT_TEXT = "missing_alt_text";
export var CATEGORY_EMPTY_BLOCK = "empty_content_block";
export var CATEGORY_QUIZ_NO_CORRECT_ANSWER = "quiz_no_correct_answer";
export var CATEGORY_BRANCHING_GRAPH = "branching_graph_issue";
export var CATEGORY_UNCOVERED_OBJECTIVE = "objective_no_assessment";
export var CATEGORY_UNCONFIGURED_BLANK = "fill_blank_no_accepted_answers";
export var CATEGORY_BLANK_TOKEN_MISMATCH = "fill_blank_token_row_mismatch";

export var CATEGORY_LABELS = {};
CATEGORY_LABELS[CATEGORY_MISSING_ALT_TEXT] = "Missing alt text";
CATEGORY_LABELS[CATEGORY_EMPTY_BLOCK] = "Empty or placeholder content blocks";
CATEGORY_LABELS[CATEGORY_QUIZ_NO_CORRECT_ANSWER] = "Quiz questions with no correct answer marked";
CATEGORY_LABELS[CATEGORY_BRANCHING_GRAPH] = "Orphaned branching-scenario nodes";
CATEGORY_LABELS[CATEGORY_UNCOVERED_OBJECTIVE] = "Objectives with no assessment coverage";
CATEGORY_LABELS[CATEGORY_UNCONFIGURED_BLANK] = "Fill-in-the-blank items with no accepted answer";
CATEGORY_LABELS[CATEGORY_BLANK_TOKEN_MISMATCH] = "Fill-in-the-blank items with mismatched blank counts";

// Prose content blocks shorter than this (after trim) are flagged as "suspiciously short" --
// long enough to rule out real single-word/short-phrase content authors might legitimately write,
// short enough to catch obvious "TODO"/"..."/placeholder-style stubs. Zero-length text is always
// flagged as "empty" regardless of this threshold.
export var EMPTY_BLOCK_MIN_CHARS = 10;

function iterateLessons(course) {
  var rows = [];
  ((course && course.modules) || []).forEach(function (module) {
    (module.lessons || []).forEach(function (lesson) {
      rows.push({ module: module, lesson: lesson });
    });
  });
  return rows;
}

function locationLabel(moduleTitle, lessonTitle, detail) {
  var parts = [];
  if (moduleTitle) parts.push(moduleTitle);
  if (lessonTitle) parts.push(lessonTitle);
  if (detail) parts.push(detail);
  return parts.length ? parts.join(" > ") : "Course";
}

// ---- Missing alt-text on images -------------------------------------------------------------
// Content blocks store their image/video attachment on `block.media` (`{kind, src, alt,
// caption}` -- see templatePayload()'s "image"/"video" cases and the alt-text field editor.js
// renders at block.media.alt, wired up for the P5-3e AI alt-text action). Only `kind: "image"`
// media carries a meaningful alt text requirement -- video blocks use `caption` instead.
export function findMissingAltText(course) {
  var findings = [];
  iterateLessons(course).forEach(function (row) {
    (row.lesson.content_blocks || []).forEach(function (block, index) {
      var media = block && block.media;
      if (!media || media.kind !== "image") return;
      var alt = String(media.alt || "").trim();
      if (alt) return;
      findings.push({
        category: CATEGORY_MISSING_ALT_TEXT,
        location: locationLabel(row.module.title, row.lesson.title, "Block " + (index + 1) + " (" + (block.type || "image") + ")"),
        message: "Image block has no alt text.",
      });
    });
  });
  return findings;
}

// ---- Empty / placeholder content blocks ------------------------------------------------------
export function findEmptyBlocks(course) {
  var findings = [];
  iterateLessons(course).forEach(function (row) {
    (row.lesson.content_blocks || []).forEach(function (block, index) {
      var text = String((block && block.text) || "").trim();
      if (text.length >= EMPTY_BLOCK_MIN_CHARS) return;
      findings.push({
        category: CATEGORY_EMPTY_BLOCK,
        location: locationLabel(row.module.title, row.lesson.title, "Block " + (index + 1) + " (" + (block.type || "content") + ")"),
        message: text.length === 0
          ? "Content block is empty."
          : "Content block is suspiciously short (" + text.length + " character" + (text.length === 1 ? "" : "s") +
            ", under the " + EMPTY_BLOCK_MIN_CHARS + "-character threshold).",
      });
    });
  });
  return findings;
}

// ---- Quiz questions with no correct answer marked ---------------------------------------------
// Course Studio's quiz question shape is {id, type, objective_ids, question, options,
// correct_answers, explanation} (see templatePayload()'s "mcq" case and
// quiz-from-content-ai.js's extractQuizQuestions() -- both write `correct_answers` as an array).
// A question is "answered" only if correct_answers is non-empty AND every listed correct answer
// is actually one of the question's own options -- the same class of check
// course_mcp_server.schemas.QuizQuestion / QuizBank enforce server-side for AI-generated content
// (see QuizQuestion.answer must be a listed option), applied here as a pure client-side scan of
// already-authored content rather than a validation of an AI response.
function questionAnswerIssue(question) {
  var correct = Array.isArray(question && question.correct_answers)
    ? question.correct_answers.filter(function (value) { return String(value || "").trim(); })
    : [];
  if (!correct.length) return "no_answer";
  var options = Array.isArray(question.options) ? question.options : [];
  var allListed = correct.every(function (value) { return options.indexOf(value) !== -1; });
  if (!allListed) return "not_in_options";
  return null;
}

function questionLabel(question, index) {
  var prefix = "Question " + (index + 1);
  var text = String((question && question.question) || "").trim();
  if (!text) return prefix;
  return prefix + ": \"" + (text.length > 60 ? text.slice(0, 60) + "…" : text) + "\"";
}

function questionFinding(location, issue) {
  return {
    category: CATEGORY_QUIZ_NO_CORRECT_ANSWER,
    location: location,
    message: issue === "no_answer"
      ? "Quiz question has no correct answer marked."
      : "Quiz question's marked correct answer is not one of its listed options.",
  };
}

export function findUnansweredQuizQuestions(course) {
  var findings = [];
  iterateLessons(course).forEach(function (row) {
    (row.lesson.quiz_questions || []).forEach(function (question, index) {
      var issue = questionAnswerIssue(question);
      if (!issue) return;
      findings.push(questionFinding(
        locationLabel(row.module.title, row.lesson.title, questionLabel(question, index)),
        issue
      ));
    });
  });
  var finalQuestions = (course && course.final_assessment && course.final_assessment.questions) || [];
  finalQuestions.forEach(function (question, index) {
    var issue = questionAnswerIssue(question);
    if (!issue) return;
    findings.push(questionFinding("Final assessment > " + questionLabel(question, index), issue));
  });
  return findings;
}

// ---- Orphaned branching-scenario nodes ---------------------------------------------------------
// Reimplements, in pure JS, the exact two checks
// course_mcp_server.schemas.BranchingScenario._validate_graph enforces server-side:
//   1. duplicate node ids (after back-filling any missing id from list position, "node_<index>",
//      exactly like the Python model_validator does before comparing ids)
//   2. dangling choice.next_node_id references that don't name any node in the same list
// See tests/course-health-branching-cross-check.test.js for fixtures whose expected verdict is
// cross-checked against this same Python validator's documented behavior.
export function checkBranchingGraph(rawNodes) {
  var nodes = Array.isArray(rawNodes) ? rawNodes : [];
  var ids = nodes.map(function (node, index) {
    return node && node.id ? node.id : "node_" + index;
  });
  // Use real Map/Set instances rather than plain object literals: a plain `{}` used as a hash set
  // is vulnerable to prototype pollution via keys like "__proto__" -- `obj["__proto__"] = true` is
  // a silent no-op (it reassigns the prototype, not a own-property), yet `obj["__proto__"]` still
  // reads back truthy via the prototype chain (resolving to Object.prototype). That would make a
  // node id or next_node_id of "__proto__" (or "constructor", "hasOwnProperty", etc.) silently
  // bypass both the duplicate-id count and the dangling-reference check below. Map/Set have no
  // such prototype-chain lookup for string keys.
  var counts = new Map();
  ids.forEach(function (id) { counts.set(id, (counts.get(id) || 0) + 1); });
  var duplicateIds = Array.from(counts.keys()).filter(function (id) { return counts.get(id) > 1; }).sort();
  var idSet = new Set(ids);
  var dangling = [];
  nodes.forEach(function (node, index) {
    (node && node.choices ? node.choices : []).forEach(function (choice) {
      var next = choice && choice.next_node_id;
      if (next !== null && next !== undefined && next !== "" && !idSet.has(next)) {
        dangling.push(ids[index] + " -> " + next);
      }
    });
  });
  return { duplicateIds: duplicateIds, dangling: dangling, ok: duplicateIds.length === 0 && dangling.length === 0 };
}

// Mirrors the "scenes" ACTIVITY_INSPECTORS.match() predicate in editor.js -- both
// scenario_decision_tree and branching_scenario activities share this exact node/choices shape.
function isBranchingActivity(activity) {
  var type = String((activity && (activity.activity_type || activity.type)) || "");
  return type.indexOf("branching") >= 0 || type.indexOf("scenario") >= 0 || type.indexOf("decision") >= 0;
}

export function findOrphanedBranchingNodes(course) {
  var findings = [];
  iterateLessons(course).forEach(function (row) {
    (row.lesson.activities || []).forEach(function (activity, index) {
      if (!isBranchingActivity(activity)) return;
      var nodes = activity.items || activity.nodes || [];
      var result = checkBranchingGraph(nodes);
      if (result.ok) return;
      var label = "Activity " + (index + 1) + (activity.title ? " (\"" + activity.title + "\")" : "");
      var location = locationLabel(row.module.title, row.lesson.title, label);
      if (result.duplicateIds.length) {
        findings.push({
          category: CATEGORY_BRANCHING_GRAPH,
          location: location,
          message: "Duplicate branching node id(s): " + result.duplicateIds.join(", ") + ".",
        });
      }
      if (result.dangling.length) {
        findings.push({
          category: CATEGORY_BRANCHING_GRAPH,
          location: location,
          message: "Choice references a node that does not exist: " + result.dangling.join(", ") + ".",
        });
      }
    });
  });
  return findings;
}

// ---- Objectives with no assessment coverage ----------------------------------------------------
// Mirrors course_mcp_server.advanced_quality_gates.assessment_alignment_score()'s coverage set:
// every learning_objectives[].id that never appears in any quiz_questions[].objective_ids
// (lesson-level or final_assessment) is "uncovered".
export function findUncoveredObjectives(course) {
  var objectives = (course && course.learning_objectives) || [];
  if (!objectives.length) return [];
  var assessed = {};
  iterateLessons(course).forEach(function (row) {
    (row.lesson.quiz_questions || []).forEach(function (question) {
      (question.objective_ids || []).forEach(function (id) { assessed[id] = true; });
    });
  });
  var finalQuestions = (course && course.final_assessment && course.final_assessment.questions) || [];
  finalQuestions.forEach(function (question) {
    (question.objective_ids || []).forEach(function (id) { assessed[id] = true; });
  });
  var findings = [];
  objectives.forEach(function (objective, index) {
    var id = objective && objective.id;
    if (!id || assessed[id]) return;
    var text = String((objective && objective.text) || "").trim();
    findings.push({
      category: CATEGORY_UNCOVERED_OBJECTIVE,
      location: "Learning objective " + (index + 1) + (text ? ": \"" + (text.length > 80 ? text.slice(0, 80) + "…" : text) + "\"" : ""),
      message: "No quiz question (lesson or final assessment) references this objective.",
    });
  });
  return findings;
}

// ---- Fill-in-the-blank activities with no accepted answer configured --------------------------
// Mirrors fill-blank.js's normalizeAnswers(): an entry's accepted answers may be given as a real
// array (`{answers: [...]}`), a comma-separated string (`{answers: "Paris, France"}`), or the
// singular `{answer: "Paris"}` shorthand. If, after normalizing, a blank has zero accepted
// answers, isAnswerAccepted() now (correctly) rejects every learner input for that blank -- which
// means an author who added a blank via "+ Add blank" but never filled in its answer field has
// shipped an unwinnable question. Flag it here so that gap surfaces before export.
function isBlankUnconfigured(blank) {
  var raw = blank && (blank.answers !== undefined ? blank.answers : blank.answer);
  return normalizeAnswers(raw).length === 0;
}

export function findUnconfiguredBlanks(course) {
  var findings = [];
  iterateLessons(course).forEach(function (row) {
    (row.lesson.activities || []).forEach(function (activity, index) {
      var type = String((activity && (activity.activity_type || activity.type)) || "");
      if (type.indexOf("fill_blank") < 0) return;
      var blanks = (activity && activity.blanks) || [];
      var unconfiguredCount = blanks.filter(isBlankUnconfigured).length;
      if (!unconfiguredCount) return;
      var label = "Activity " + (index + 1) + (activity.title ? " (\"" + activity.title + "\")" : "");
      findings.push({
        category: CATEGORY_UNCONFIGURED_BLANK,
        location: locationLabel(row.module.title, row.lesson.title, label),
        message: unconfiguredCount + " of " + blanks.length + " blank" + (blanks.length === 1 ? "" : "s") +
          " has no accepted answer configured -- learners cannot get it right.",
      });
    });
  });
  return findings;
}

// ---- Fill-in-the-blank activities where the text's {{blank}} token count doesn't match the
// configured blank rows -----------------------------------------------------------------------
// findUnconfiguredBlanks (above) only inspects *existing* activity.blanks[] rows for empty
// accepted-answers -- it never cross-checks blanks.length against the actual number of
// "{{blank}}" tokens in activity.text. If the text has MORE tokens than configured rows, the
// exported player's renderFillBlankActivity() (scorm.py) does `blanks[blankIndex] || {}` for the
// missing index(es), producing zero accepted answers -- an unwinnable blank that
// findUnconfiguredBlanks can't see because there's no row there to inspect. (Fewer tokens than
// rows is comparatively harmless -- the extra row is just unused -- but is still flagged here so
// authors notice the mismatch and can decide which side is wrong.)
export function findBlankTokenMismatch(course) {
  var findings = [];
  iterateLessons(course).forEach(function (row) {
    (row.lesson.activities || []).forEach(function (activity, index) {
      var type = String((activity && (activity.activity_type || activity.type)) || "");
      if (type.indexOf("fill_blank") < 0) return;
      var tokenCount = countBlankTokens(activity && activity.text);
      var blanks = (activity && activity.blanks) || [];
      if (tokenCount === blanks.length) return;
      var label = "Activity " + (index + 1) + (activity.title ? " (\"" + activity.title + "\")" : "");
      findings.push({
        category: CATEGORY_BLANK_TOKEN_MISMATCH,
        location: locationLabel(row.module.title, row.lesson.title, label),
        message: tokenCount + " {{blank}} token" + (tokenCount === 1 ? "" : "s") + " in the text but " +
          blanks.length + " answer row" + (blanks.length === 1 ? "" : "s") + " configured -- " +
          (tokenCount > blanks.length
            ? "learners cannot complete the missing blank" + (tokenCount - blanks.length === 1 ? "" : "s") + "."
            : "there " + (blanks.length - tokenCount === 1 ? "is an" : "are") + " extra unused answer row" +
              (blanks.length - tokenCount === 1 ? "" : "s") + "."),
      });
    });
  });
  return findings;
}

// Runs every check and returns a single flat array of findings, in category order. Each finding
// is `{category, location, message}`; grouping by category for display is left to the caller
// (editor.js) since that's a presentation concern, not a checklist concern.
export function runCourseHealthCheck(course) {
  if (!course) return [];
  return []
    .concat(findMissingAltText(course))
    .concat(findEmptyBlocks(course))
    .concat(findUnansweredQuizQuestions(course))
    .concat(findOrphanedBranchingNodes(course))
    .concat(findUncoveredObjectives(course))
    .concat(findUnconfiguredBlanks(course))
    .concat(findBlankTokenMismatch(course));
}
