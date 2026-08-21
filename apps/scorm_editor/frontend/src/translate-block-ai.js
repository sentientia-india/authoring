// Pure request/response helpers for P5-3d's "Translate" AI action. Follows the exact structural
// pattern content-block-ai.js (P5-3b) and quiz-from-content-ai.js (P5-3c) established: a pure
// module with a system-prompt builder, a request builder targeting POST /api/ai/<sid>/generate,
// and a response extractor -- no DOM access, unit-testable on its own. editor.js owns the DOM
// (the language picker, scope selector, disabled/in-flight state) and applying the result via the
// same save()/pushHistory() undo-stack path every other edit uses.
//
// WIRE FORMAT: plain TEXT in, plain TEXT out -- same decision content-block-ai.js made and for the
// same reason (see that module's header comment): asking a general text_provider to reliably
// round-trip our restricted text_html allowlist is more failure-prone than re-deriving text_html
// from the returned plain text the same way editor.js already does for Rewrite/Expand/Simplify.
//
// SCOPE DECISION (see task notes / docs/authoring-platform-plan.md P5-3d): there is no existing
// per-locale-variant concept anywhere in this codebase -- CourseOutline.language / LessonDraft
// etc. (src/course_mcp_server/schemas.py) are a single plain string field per course, describing
// what language the WHOLE course's content is authored in, not a mechanism for holding several
// language variants of the same content side by side. Building a parallel locale-tagged course (or
// lesson) tree to hold translations is a much bigger surface than this task calls for. The task's
// own hard requirement -- never silently overwrite authored content -- is satisfied more simply and
// more safely by producing translated text as a NEW, plainly-tagged sibling content block appended
// immediately after the block it translates, in the SAME content_blocks array as the original:
//   { id: uid("cb"), type: <same as original>, text: <translated text>, text_html: <derived>,
//     language: <target language>, translated_from: <original block id> }
// `language` and `translated_from` are extra fields course_schema_v2.ContentBlock doesn't declare,
// but that model is never used to validate a save (apps/scorm_editor/server.py's save_course()
// persists course.json as a raw dict -- see its own header comment), so they round-trip untouched.
// This is the smallest correct building block: it works identically at every scope --
//   - "block":  translate the one selected block, insert its translation right after it.
//   - "lesson": translate every block in the current lesson, one AI call per block (this module's
//     buildTranslateBlockRequest is intentionally single-block -- no batched/multi-block wire
//     format was introduced), each inserted right after the block it came from.
//   - "course": translate every block in every lesson of the course, same one-call-per-block
//     mechanism as "lesson" repeated across every lesson. This is a real scope-down from "build a
///    duplicated, locale-tagged course entity" -- documented here rather than silently assumed.
// editor.js is responsible for issuing one buildTranslateBlockRequest()/extractTranslatedText()
// round trip per block in scope, collecting every successful translation WITHOUT mutating
// content_blocks, and only committing (splicing every new block into place, then save(false)) once
// every request in the batch has succeeded -- so a failure partway through a multi-block
// lesson/course translation leaves nothing inserted, exactly like a single failed block
// translation. See this module's own header note near extractTranslatedText for why a
// batch-partial-insert would violate the task's "insert nothing partial" requirement.

var CONTEXT_EXCERPT_LENGTH = 160;

function excerpt(text) {
  text = String(text || "").trim();
  if (text.length <= CONTEXT_EXCERPT_LENGTH) return text;
  return text.slice(0, CONTEXT_EXCERPT_LENGTH).trim() + "…";
}

// Builds the system prompt for a given target language. Kept as a function (not a fixed export)
// because -- unlike CONTENT_BLOCK_TRANSFORMS' three fixed transforms -- the target language is
// free text the author picks at request time.
export function buildTranslateSystemPrompt(targetLanguage) {
  var language = String(targetLanguage || "").trim();
  return (
    "You are translating one content block of an e-learning lesson into " + language + ". " +
    "Translate the given text faithfully: preserve its meaning, structure, tone, and any " +
    "formatting markers (such as lists or emphasis) exactly, without adding, omitting, or " +
    "altering any information. Do not summarize, expand, or editorialize -- produce a direct, " +
    "faithful translation only. Return plain text only -- no markdown, no HTML tags, and do not " +
    "include the original text or any language name/label in the output."
  );
}

// `block` is the target content block ({id, type, text, ...}). `siblingBlocks` is the full
// content_blocks array the target block lives in (used only to find its immediate neighbors for
// continuity context, mirroring buildContentBlockAiRequest); `lessonTitle` is the owning lesson's
// title. `targetLanguage` is the free-text language name the author chose. `aiRequestFields` is
// the output of ai-settings.js's buildAiRequestFields() -- spread in as-is, same as every other AI
// request this cycle.
export function buildTranslateBlockRequest(block, lessonTitle, targetLanguage, siblingBlocks, aiRequestFields) {
  var language = String(targetLanguage || "").trim();
  if (!language) throw new Error("Choose a target language first.");
  if (!block || !String(block.text || "").trim()) throw new Error("This block has no text to translate.");

  var blocks = siblingBlocks || [];
  var index = blocks.indexOf(block);
  var before = index > 0 ? blocks[index - 1] : null;
  var after = index >= 0 && index < blocks.length - 1 ? blocks[index + 1] : null;

  var payload = {
    role: block.type || "explanation",
    text: block.text,
    lesson_title: lessonTitle || "",
    target_language: language,
  };
  if (before) payload.previous_block = { role: before.type || "explanation", excerpt: excerpt(before.text) };
  if (after) payload.next_block = { role: after.type || "explanation", excerpt: excerpt(after.text) };

  var body = {
    system_prompt: buildTranslateSystemPrompt(language),
    user_payload: payload,
    schema_name: "content_block_translate",
  };
  Object.keys(aiRequestFields || {}).forEach(function (key) { body[key] = aiRequestFields[key]; });
  return body;
}

// Validates/normalizes the `result` field of a successful POST /api/ai/<sid>/generate response
// into the plain translated text, or throws a clear, user-facing message if the shape is unusable.
// Never returns an empty/whitespace-only string. A throw here (or a rejected fetch, or a
// !data.ok response) is what editor.js's batch orchestration treats as "this block's translation
// failed" -- which, for a multi-block lesson/course translation, aborts the WHOLE batch before
// anything is inserted (see this module's header comment).
export function extractTranslatedText(result) {
  if (!result || typeof result !== "object") throw new Error("The AI response was empty.");
  var text = typeof result.text === "string" ? result.text.trim() : "";
  if (!text) throw new Error("The AI response did not include translated text.");
  return text;
}
