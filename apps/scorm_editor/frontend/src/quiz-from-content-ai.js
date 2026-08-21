// Pure request/response helpers for P5-3c's "Generate quiz from content" AI action. Follows the
// exact structural pattern content-block-ai.js established for P5-3b (rewrite/expand/simplify):
// a pure module with a system prompt, a request builder targeting POST /api/ai/<sid>/generate,
// and a response extractor -- no DOM access, unit-testable on its own. editor.js owns the DOM
// (the trigger button, scope choice, disabled/in-flight state) and applying the result via the
// same save()/pushHistory() undo-stack path every other edit uses.
//
// SCOPE DECISION: the caller (editor.js) always hands this module an already-resolved array of
// content blocks to draw from -- either the one selected block (scope "block") or every block in
// the current lesson in document order (scope "lesson"). Keeping the scope resolution in
// editor.js (which owns state.selected/findBlock/findLesson) and this module scope-agnostic below
// that point mirrors content-block-ai.js's own split: editor.js resolves "which data", this module
// only shapes "what request"/"what response".
//
// SCHEMA DECISION (see docs/authoring-platform-plan.md P5-3c task notes): the wire schema for
// schema_name "quiz_from_content" matches course_mcp_server.schemas.QuizBank/QuizQuestion field
// for field (course_title, questions[].{id,type,difficulty,objective,question,options,answer,
// explanation}) because the server validates the model's raw JSON against those real Pydantic
// models in server.py's generate_ai_content() before ever returning it as a success -- so the
// system prompt below asks for exactly that shape, and this module's extractor is deliberately a
// second, lighter-weight defense-in-depth check (a malformed response should never reach here,
// since the server already rejected it, but this module doesn't assume that and re-validates the
// fields it actually consumes). What is NOT reused wire-side is the shape this module ultimately
// hands back to editor.js -- that shape matches ACTIVITY_TEMPLATE_REGISTRY-adjacent "mcq" question
// template (templatePayload()'s case "mcq": {id, type: "mcq", objective_ids, question, options,
// correct_answers, explanation}), i.e. Course Studio's own lesson.quiz_questions item shape, which
// editor.js already knows how to render/edit/export. This module's extractQuizQuestions() bridges
// the two: it returns {question, options, correct_answers, explanation} per question (one AI
// QuizQuestion -> one Course Studio question), and editor.js is responsible for stamping a fresh
// id (uid("q")) and objective_ids: [] onto each one at insertion time, exactly like insertTemplate
// does for a manually-inserted "mcq" template. All returned questions are mapped to type "mcq"
// (Course Studio's questionEditor()/exporter only understand the mcq shape today regardless of
// whether the AI called a given question "mcq" or "true_false" -- a true/false question is simply
// an mcq with two options, "True"/"False", so no information or fidelity is lost).
export var QUIZ_FROM_CONTENT_QUESTION_COUNT = 4;

export var QUIZ_FROM_CONTENT_SYSTEM_PROMPT =
  "You are creating a short quiz for one lesson of an e-learning course. Write exactly " +
  String(QUIZ_FROM_CONTENT_QUESTION_COUNT) +
  " questions, each either multiple-choice or true/false, strictly grounded in the given lesson " +
  "content -- every question must test something explicitly stated in the provided text. Do not " +
  "invent facts, numbers, names, or examples that are not present in the text. Each question must " +
  "have exactly one correct answer and 1 to 5 plausible, clearly incorrect distractors (a " +
  "true/false question must use exactly the two options \"True\" and \"False\"). Return JSON with " +
  "this exact shape: {\"course_title\": string, \"questions\": [{\"id\": \"q1\", \"type\": \"mcq\" " +
  "or \"true_false\", \"difficulty\": \"beginner\" or \"intermediate\" or \"advanced\", " +
  "\"objective\": a short string naming what the question checks, \"question\": string, " +
  "\"options\": an array of option strings, \"answer\": the exact text of the single correct " +
  "option copied verbatim from options, \"explanation\": a short string explaining why that " +
  "answer is correct}]}. Number question ids sequentially starting at \"q1\". Return plain JSON " +
  "only -- no markdown, no text outside the JSON object.";

var CONTENT_LENGTH_LIMIT = 6000; // keeps a whole-lesson request well inside provider context limits

function blockLabel(block) {
  return String((block && block.type) || "explanation");
}

// `scopedBlocks` is the array of content blocks to draw the quiz from -- one element for scope
// "block", every block of the current lesson (in order) for scope "lesson". `scope` is carried
// through only as metadata for the model/logging, it does not change how the text is assembled.
export function buildQuizFromContentRequest(scope, lessonTitle, scopedBlocks, aiRequestFields) {
  if (scope !== "block" && scope !== "lesson") throw new Error("Unknown quiz scope: " + scope);

  var blocks = (scopedBlocks || []).filter(function (block) { return block && String(block.text || "").trim(); });
  if (!blocks.length) throw new Error("There is no text here to generate a quiz from.");

  var content = blocks
    .map(function (block) { return "[" + blockLabel(block) + "] " + String(block.text).trim(); })
    .join("\n\n")
    .slice(0, CONTENT_LENGTH_LIMIT);

  var body = {
    system_prompt: QUIZ_FROM_CONTENT_SYSTEM_PROMPT,
    user_payload: {
      scope: scope,
      lesson_title: lessonTitle || "",
      question_count: QUIZ_FROM_CONTENT_QUESTION_COUNT,
      content: content,
    },
    schema_name: "quiz_from_content",
  };
  Object.keys(aiRequestFields || {}).forEach(function (key) { body[key] = aiRequestFields[key]; });
  return body;
}

// Validates/normalizes the `result` field of a successful POST /api/ai/<sid>/generate response
// (schema_name "quiz_from_content") into an array of plain question objects shaped
// {question, options, correct_answers, explanation}, ready for editor.js to stamp an id/type onto
// and push into lesson.quiz_questions -- or throws a clear, user-facing message if the shape is
// unusable. The server has already validated this same JSON against QuizBank/QuizQuestion before
// this ever runs (see server.py's generate_ai_content()); this is a lighter-weight second check on
// just the fields this module reads, not a re-implementation of that Pydantic validation.
export function extractQuizQuestions(result) {
  if (!result || typeof result !== "object") throw new Error("The AI response was empty.");
  var rawQuestions = Array.isArray(result.questions) ? result.questions : [];
  if (!rawQuestions.length) throw new Error("The AI response did not include any quiz questions.");

  return rawQuestions.map(function (raw, index) {
    var question = typeof (raw && raw.question) === "string" ? raw.question.trim() : "";
    var options = Array.isArray(raw && raw.options)
      ? raw.options.map(function (option) { return String(option || "").trim(); }).filter(Boolean)
      : [];
    var answer = typeof (raw && raw.answer) === "string" ? raw.answer.trim() : "";
    var explanation = typeof (raw && raw.explanation) === "string" ? raw.explanation.trim() : "";

    if (!question || options.length < 2 || !answer || options.indexOf(answer) === -1) {
      throw new Error("The AI response contained a malformed quiz question (#" + (index + 1) + ").");
    }

    return {
      question: question,
      options: options,
      correct_answers: [answer],
      explanation: explanation || "Explain why this answer is correct.",
    };
  });
}
