// Pure request/response helpers for P5-3b's per-content-block AI actions (Rewrite / Expand /
// Simplify). Extracted so the request-shaping and response-validation logic is unit testable
// without the DOM, matching the pattern already established by ai-settings.js / undo-stack.js /
// move-item.js. editor.js is responsible for the DOM (buttons, disabled state, applying the
// result via the same save()/pushHistory() path as every other edit) -- this module only builds
// the request body and validates the response shape.
//
// WIRE FORMAT DECISION (see docs/authoring-platform-plan.md P5-3b task notes): plain TEXT only,
// both directions. `user_payload.text` is always block.text (never block.text_html), and the
// expected `result` shape is `{ text: "..." }`, also plain text. Any existing text_html
// formatting (bold/italic/links/lists) is intentionally NOT round-tripped through the model --
// asking a general text_provider to reliably emit exactly our restricted-HTML allowlist
// (html_sanitizer.py's ALLOWED_TAGS) is more failure-prone than just re-deriving text_html from
// the returned plain text the same way editor.js's startInlineEdit() already derives an initial
// value for a block that has no text_html yet: `"<p>" + escapeHtml(block.text) + "</p>"`, run
// through the same sanitizeRichTextHtml() a manual edit uses. Any formatting the block had is
// therefore reset to an unformatted paragraph by an AI transform -- documented, not a bug.
//
// CONTEXT DECISION: kept deliberately small -- the lesson title plus a short excerpt of the
// immediately adjacent (previous/next) blocks in the same lesson, not the whole lesson/course.

export var CONTENT_BLOCK_TRANSFORMS = {
  rewrite: {
    id: "rewrite",
    label: "Rewrite",
    systemPrompt:
      "You are editing one content block of an e-learning lesson. Rewrite the given text to " +
      "improve clarity and flow. Do not change its meaning and do not materially change its " +
      "length, and do not introduce new facts, examples, or claims that are not already present " +
      "in the text. Preserve its content block role (e.g. intro, explanation, example, summary). " +
      "Return plain text only -- no markdown, no HTML tags.",
  },
  expand: {
    id: "expand",
    label: "Expand",
    systemPrompt:
      "You are editing one content block of an e-learning lesson. Expand the given text with " +
      "more detail, explanation, or a concrete example, while preserving its original meaning " +
      "and its content block role. Do not contradict or remove anything already stated in the " +
      "original text. Return plain text only -- no markdown, no HTML tags.",
  },
  simplify: {
    id: "simplify",
    label: "Simplify",
    systemPrompt:
      "You are editing one content block of an e-learning lesson. Rewrite the given text at a " +
      "lower reading level: shorter sentences, plainer vocabulary, one idea per sentence. " +
      "Preserve its original meaning, its content block role, and every piece of information a " +
      "learner needs -- simplify the language, not the substance. Return plain text only -- no " +
      "markdown, no HTML tags.",
  },
};

export var CONTENT_BLOCK_TRANSFORM_IDS = Object.keys(CONTENT_BLOCK_TRANSFORMS);

var CONTEXT_EXCERPT_LENGTH = 160;

function excerpt(text) {
  text = String(text || "").trim();
  if (text.length <= CONTEXT_EXCERPT_LENGTH) return text;
  return text.slice(0, CONTEXT_EXCERPT_LENGTH).trim() + "…";
}

// `block` is the target content block ({id, type, text, ...}). `siblingBlocks` is the full
// content_blocks array the target block lives in (used only to find its immediate neighbors for
// continuity context); `lessonTitle` is the owning lesson's title. `aiRequestFields` is the
// output of ai-settings.js's buildAiRequestFields() -- spread in as-is so this request carries
// the same text_provider/text_provider_api_key/... fields as every other AI call.
export function buildContentBlockAiRequest(transformId, block, lessonTitle, siblingBlocks, aiRequestFields) {
  var transform = CONTENT_BLOCK_TRANSFORMS[transformId];
  if (!transform) throw new Error("Unknown content block AI transform: " + transformId);
  if (!block || !String(block.text || "").trim()) throw new Error("This block has no text to transform.");

  var blocks = siblingBlocks || [];
  var index = blocks.indexOf(block);
  var before = index > 0 ? blocks[index - 1] : null;
  var after = index >= 0 && index < blocks.length - 1 ? blocks[index + 1] : null;

  var payload = {
    role: block.type || "explanation",
    text: block.text,
    lesson_title: lessonTitle || "",
  };
  if (before) payload.previous_block = { role: before.type || "explanation", excerpt: excerpt(before.text) };
  if (after) payload.next_block = { role: after.type || "explanation", excerpt: excerpt(after.text) };

  var body = {
    system_prompt: transform.systemPrompt,
    user_payload: payload,
    schema_name: "content_block_rewrite",
  };
  Object.keys(aiRequestFields || {}).forEach(function (key) { body[key] = aiRequestFields[key]; });
  return body;
}

// Validates/normalizes the `result` field of a successful POST /api/ai/<sid>/generate response
// into the plain rewritten text, or throws a clear, user-facing message if the shape is
// unusable. Never returns an empty/whitespace-only string.
export function extractRewrittenText(result) {
  if (!result || typeof result !== "object") throw new Error("The AI response was empty.");
  var text = typeof result.text === "string" ? result.text.trim() : "";
  if (!text) throw new Error("The AI response did not include rewritten text.");
  return text;
}
