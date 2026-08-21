// Pure request/response helpers for P5-3e's "Generate alt text" AI action on image blocks.
// Follows the exact structural pattern content-block-ai.js (P5-3b), quiz-from-content-ai.js
// (P5-3c), and translate-block-ai.js (P5-3d) established: a pure module with a system prompt, a
// request builder targeting POST /api/ai/<sid>/generate, and a response extractor -- no DOM
// access, unit-testable on its own. editor.js owns the DOM (the trigger button, disabled/
// in-flight state, the overwrite-confirmation prompt) and applying the result via the same
// save()/pushHistory() undo-stack path every other edit uses.
//
// REAL MULTIMODAL VS. TEXT-ONLY APPROXIMATION (P5-3e task decision, read before changing this
// file): TextProvider.generate_json(system_prompt, user_payload, schema_name, *, model=None) --
// see src/course_mcp_server/text_providers/base.py -- takes a plain `user_payload: dict`. Every
// current adapter builds a TEXT-ONLY message from it: openai.py's generate_json() JSON-encodes
// `{"schema": schema_name, "payload": user_payload}` straight into a single chat "user" message
// string (see its `body["messages"][1]["content"] = json.dumps(...)`), and anthropic.py/
// gemini.py do the equivalent for their own wire formats -- none of the three builds a
// provider-specific multimodal content array (image_url / inline_data / etc.) from anything in
// user_payload today. Wiring real vision input would mean, at minimum: (1) inventing an
// image-payload convention (e.g. `user_payload.image_base64`/`image_mime_type`), (2) extending
// THREE separate adapters (openai.py, anthropic.py, gemini.py) to detect that convention and
// build their own real multimodal message shape (each provider's image content block is
// differently shaped), (3) a provider-capability registry so the UI can tell a vision-capable
// provider (openai/anthropic/gemini) from a text-only one (deepseek/openrouter's routed model/
// openai_compatible's unknown endpoint) *before* firing a request, since sending an image to a
// provider that silently ignores it would be worse than not offering the feature, and (4) an
// image-fetch/base64-encode step for a `media.src` that can be a same-origin uploaded file OR an
// arbitrary external https URL. That is real, adapter-by-adapter backend work spanning three
// provider modules plus a new capability-detection concept, not a small addition to this task's
// scope of "one inspector action + one wire-format module + editor.js wiring" (the same size of
// change P5-3b/3c/3d each made). So this module ships the TEXT-ONLY, context-based
// approximation (option b from the task notes): the alt-text request goes through the exact same
// transport every other AI action here uses, but the "content" it describes to the model is the
// image's surrounding authored context -- the lesson title, the content block's role and text,
// the media caption, and the image filename parsed from its src/URL -- never the image's actual
// pixels. The system prompt below says this explicitly so the model doesn't invent visual detail
// it cannot possibly know, and editor.js's button label/hint says the same to the author (see
// ALT_TEXT_CONTEXT_ONLY_NOTE below, surfaced in the inspector). Because no real image bytes are
// ever sent, there is no vision-capability gap to guard against: every provider in
// KNOWN_TEXT_PROVIDERS (ai-settings.js) can answer a plain-text prompt, so this module
// deliberately has NO provider-capability guard/allowlist -- unlike a real-multimodal
// implementation would need (see task note 4). If real image analysis is added later, that is
// the point to introduce the adapter work and the capability guard described above; this module
// should not be treated as a stepping stone that already secretly sends image bytes.
export var ALT_TEXT_CONTEXT_ONLY_NOTE =
  "Written from the surrounding lesson text and caption, not from the image itself.";

export var ALT_TEXT_SYSTEM_PROMPT =
  "You are writing accessible alt text for one image in an e-learning lesson. You cannot see the " +
  "image itself -- you are given only the lesson title, the content block's role and text, and the " +
  "image's caption and filename (if any). Write a concise alt text (roughly 5 to 20 words) that " +
  "describes what the image most likely shows, inferred solely from that surrounding context. Do " +
  "not describe visual details (colors, exact composition, specific people) you cannot know from " +
  "text alone -- describe the image's likely subject and purpose in this lesson instead. Do not " +
  "start with \"Image of\" or \"Picture of\". Return plain text only -- no markdown, no quotation " +
  "marks, no HTML tags.";

function filenameFromSrc(src) {
  var value = String(src || "").trim();
  if (!value) return "";
  var withoutQuery = value.split(/[?#]/)[0];
  var parts = withoutQuery.split("/");
  return parts[parts.length - 1] || "";
}

// `block` is the owning content block ({id, type, text, media: {kind: "image", src, caption,
// alt}, ...}). `lessonTitle` is the owning lesson's title. `aiRequestFields` is the output of
// ai-settings.js's buildAiRequestFields() -- spread in as-is, same as every other AI request this
// cycle.
export function buildAltTextRequest(block, lessonTitle, aiRequestFields) {
  if (!block || !block.media || block.media.kind !== "image") {
    throw new Error("This block has no image to describe.");
  }
  var media = block.media;
  var blockText = String(block.text || "").trim();
  var caption = String(media.caption || "").trim();
  var filename = filenameFromSrc(media.src);
  if (!blockText && !caption && !filename) {
    throw new Error("Add a caption or some block text describing the image first.");
  }

  var payload = {
    role: block.type || "example",
    lesson_title: lessonTitle || "",
    block_text: blockText,
    caption: caption,
    filename: filename,
  };
  var existingAlt = String(media.alt || "").trim();
  if (existingAlt) payload.current_alt_text = existingAlt;

  var body = {
    system_prompt: ALT_TEXT_SYSTEM_PROMPT,
    user_payload: payload,
    schema_name: "image_alt_text",
  };
  Object.keys(aiRequestFields || {}).forEach(function (key) { body[key] = aiRequestFields[key]; });
  return body;
}

// Validates/normalizes the `result` field of a successful POST /api/ai/<sid>/generate response
// into the plain alt text, or throws a clear, user-facing message if the shape is unusable. Never
// returns an empty/whitespace-only string.
export function extractAltText(result) {
  if (!result || typeof result !== "object") throw new Error("The AI response was empty.");
  var text = typeof result.alt_text === "string" ? result.alt_text.trim() : "";
  if (!text) throw new Error("The AI response did not include alt text.");
  return text;
}
