// Pure request/response helpers for P5-5f's "AI-assisted inline outline regeneration" action.
// Follows the exact structural pattern quiz-from-content-ai.js / branching-scenario-ai.js
// established: a pure module with a system prompt, a request builder targeting
// POST /api/ai/<sid>/generate, and a response extractor -- no DOM access, unit-testable on its
// own. editor.js owns the DOM (the module/lesson inspector action, the guidance textarea, the
// confirm()-before-apply gate, in-flight/disabled state) and applying the result via the same
// save(true)/pushHistory() undo-stack path every other structural AI action this cycle uses
// (see quiz-from-content-ai.js / branching-scenario-ai.js's own module docstrings for why
// save(true) -- not save(false) -- is correct whenever the mutation is rendered/structural
// content, per this cycle's P5-5c fix).
//
// STRUCTURE-ONLY DECISION (see the P5-5f task notes): this module regenerates OUTLINE ONLY --
// lesson titles + a block-role skeleton at module scope, or a block-role skeleton at lesson scope
// -- never full lesson/block prose. Full-content regeneration was explicitly considered and
// rejected: this codebase has already established (content-block-ai.js, quiz-from-content-ai.js,
// branching-scenario-ai.js) that AI output must be grounded in author-supplied source text/
// premise/content, specifically to avoid low-quality invented filler; a "regenerate this whole
// module's content" action has no such grounding text to draw from (the author is asking for
// NEW structure, not a rewrite of existing prose), so honest structure-only output -- titles and
// roles the author fills in afterward, exactly like lesson-skeletons.js's existing placeholder
// lesson skeletons -- is the safer and more honest choice. Each generated block's placeholder
// text is built from the model's own short "direction" string in the same
// "<direction> (placeholder -- edit me)" style lesson-skeletons.js already uses for its
// placeholder bodies, so a regenerated outline is visually and behaviorally indistinguishable
// from an author picking a lesson-skeletons.js skeleton -- just guided by their own free-text
// guidance instead of a fixed named skeleton.
//
// DESTRUCTIVE-REPLACE DECISION: regenerating a module/lesson's outline is, by definition, a
// full-scope in-place replacement of its current structure -- module scope replaces the whole
// `lessons` array, lesson scope replaces `content_blocks` (and resets `activities`/
// `quiz_questions` to empty, since both were authored against the OLD outline and have no
// meaningful mapping onto a newly-regenerated block skeleton; keeping them would silently orphan
// activities/questions the author can no longer see referenced from the visible outline). This is
// a different, larger-blast-radius action than any single-block AI edit elsewhere in this
// codebase (P5-3b/d's "never silently overwrite" principle governs a single block's TEXT, not an
// entire structure), so editor.js is required to gate applying this module's output behind an
// explicit confirm() naming exactly what will be replaced -- see editor.js's
// runOutlineRegenerateAiAction() -- with save(true)/the undo stack as the sole additional safety
// net (Ctrl+Z fully restores the prior structure in one step, same as every other AI action here).

export var OUTLINE_REGENERATE_MIN_ITEMS = 1;
export var OUTLINE_REGENERATE_MAX_ITEMS = 8;

// Matches editor.js's own content block "Type" <select> options exactly (see the block inspector
// section of editor.js) so a regenerated block role is always something the editor already knows
// how to render/edit -- no new block types are introduced by this module.
export var OUTLINE_BLOCK_ROLES = [
  "intro", "explanation", "example", "scenario", "practice",
  "summary", "callout", "warning", "checklist", "reflection",
];

function blockSkeletonShape() {
  return (
    "{\"role\": one of \"" + OUTLINE_BLOCK_ROLES.join("\", \"") + "\", " +
    "\"direction\": a short one-sentence string describing what this block should eventually cover}"
  );
}

export var OUTLINE_REGENERATE_MODULE_SYSTEM_PROMPT =
  "You are restructuring one module of an e-learning course. The author will give you the " +
  "module's current lesson titles and short guidance describing how they want the module " +
  "reshaped. Produce a NEW outline for this module ONLY -- a list of between " +
  String(OUTLINE_REGENERATE_MIN_ITEMS) + " and " + String(OUTLINE_REGENERATE_MAX_ITEMS) +
  " lessons, each with a title, a one-sentence objective, and a skeleton of between " +
  String(OUTLINE_REGENERATE_MIN_ITEMS) + " and " + String(OUTLINE_REGENERATE_MAX_ITEMS) +
  " content block roles that lesson should eventually contain. Do NOT write full lesson " +
  "content, prose, or examples -- structure only. Return JSON with this exact shape: " +
  "{\"lessons\": [{\"title\": string, \"objective\": string, \"blocks\": [" + blockSkeletonShape() + "]}]}. " +
  "Ground the new outline strictly in the author's guidance and the module's existing lesson " +
  "titles; do not invent unrelated topics. Return plain JSON only -- no markdown, no text " +
  "outside the JSON object.";

export var OUTLINE_REGENERATE_LESSON_SYSTEM_PROMPT =
  "You are restructuring one lesson of an e-learning course. The author will give you the " +
  "lesson's current title/objective and current content block roles, plus short guidance " +
  "describing how they want the lesson reshaped. Produce a NEW outline for this lesson ONLY -- " +
  "a one-sentence objective and a skeleton of between " + String(OUTLINE_REGENERATE_MIN_ITEMS) +
  " and " + String(OUTLINE_REGENERATE_MAX_ITEMS) + " content block roles this lesson should " +
  "eventually contain. Do NOT write full block content, prose, or examples -- structure only. " +
  "Return JSON with this exact shape: {\"objective\": string, \"blocks\": [" + blockSkeletonShape() + "]}. " +
  "Ground the new outline strictly in the author's guidance and the lesson's current title/" +
  "objective/blocks; do not invent unrelated topics. Return plain JSON only -- no markdown, no " +
  "text outside the JSON object.";

// `scope` is "module" or "lesson". `target` is the plain-data context handed to the model:
//   - scope "module": { title, lessons: [{ title }, ...] } (the module's own title + its current
//     lesson titles only -- never full lesson content, keeping the request small and honest about
//     what this action draws from).
//   - scope "lesson": { title, objective, blocks: [{ role }, ...] } (the lesson's own title/
//     objective + its current block roles only, never block text).
// `guidance` is the author's required free-text steer (e.g. "make this more example-heavy");
// throws a clear, user-facing message when it's blank, same as branching-scenario-ai.js requiring
// a premise. `aiRequestFields` is ai-settings.js's buildAiRequestFields() output, spread in as-is.
export function buildOutlineRegenerateRequest(scope, target, guidance, aiRequestFields) {
  if (scope !== "module" && scope !== "lesson") throw new Error("Unknown outline regeneration scope: " + scope);

  var trimmedGuidance = String(guidance || "").trim();
  if (!trimmedGuidance) throw new Error("Describe how you'd like this " + scope + " reshaped first.");

  var systemPrompt = scope === "module" ? OUTLINE_REGENERATE_MODULE_SYSTEM_PROMPT : OUTLINE_REGENERATE_LESSON_SYSTEM_PROMPT;
  var schemaName = scope === "module" ? "outline_regenerate_module" : "outline_regenerate_lesson";

  var body = {
    system_prompt: systemPrompt,
    user_payload: {
      scope: scope,
      guidance: trimmedGuidance,
      current: target || {},
    },
    schema_name: schemaName,
  };
  Object.keys(aiRequestFields || {}).forEach(function (key) { body[key] = aiRequestFields[key]; });
  return body;
}

function normalizeRole(role) {
  var value = typeof role === "string" ? role.trim() : "";
  return OUTLINE_BLOCK_ROLES.indexOf(value) === -1 ? "explanation" : value;
}

function normalizeDirection(direction) {
  return typeof direction === "string" ? direction.trim() : "";
}

// Builds one placeholder content block from a {role, direction} pair -- same
// "<text> (placeholder -- edit me)" convention lesson-skeletons.js's introBlock/explanationBlock/
// etc. use, so a regenerated block is indistinguishable in style from a skeleton-built one.
// `idFactory` is injected the same way lesson-skeletons.js's buildLessonFromSkeleton() takes one,
// so this module stays deterministic/testable without depending on editor.js's uid().
function placeholderBlock(idFactory, raw) {
  var role = normalizeRole(raw && raw.role);
  var direction = normalizeDirection(raw && raw.direction);
  var text = direction
    ? direction + " (placeholder -- edit me)"
    : "Write the " + role + " content here. (placeholder -- edit me)";
  return { id: idFactory("cb"), type: role, text: text };
}

function extractBlocks(rawBlocks, idFactory, label) {
  var list = Array.isArray(rawBlocks) ? rawBlocks : [];
  if (!list.length) throw new Error("The AI response did not include any blocks for " + label + ".");
  return list.map(function (raw) { return placeholderBlock(idFactory, raw); });
}

// Validates/normalizes the `result` field of a successful POST /api/ai/<sid>/generate response
// (schema_name "outline_regenerate_module") into a plain array of full lesson objects -- the same
// shape lesson-skeletons.js's buildLessonFromSkeleton() returns and editor.js's "+ Add lesson"
// button already pushes into module.lessons -- ready for editor.js to splice in as the WHOLE
// replacement for module.lessons (never appended; see this module's header comment on the
// destructive-replace decision). Throws a clear, user-facing message if the shape is unusable; on
// a throw, editor.js applies nothing and module.lessons is left exactly as it was.
export function extractRegeneratedModuleOutline(result, idFactory, objectiveIds) {
  if (!result || typeof result !== "object") throw new Error("The AI response was empty.");
  if (typeof idFactory !== "function") throw new Error("extractRegeneratedModuleOutline requires an idFactory function.");

  var rawLessons = Array.isArray(result.lessons) ? result.lessons : [];
  if (!rawLessons.length) throw new Error("The AI response did not include any lessons.");

  return rawLessons.map(function (raw, index) {
    var title = (raw && typeof raw.title === "string" && raw.title.trim()) ? raw.title.trim() : "New lesson";
    var objective = (raw && typeof raw.objective === "string" && raw.objective.trim())
      ? raw.objective.trim()
      : "Describe what the learner will be able to do after this lesson. (placeholder -- edit me)";
    return {
      id: idFactory("lesson"),
      title: title,
      duration_minutes: 8,
      objective_ids: objectiveIds || [],
      objective: objective,
      content_blocks: extractBlocks(raw && raw.blocks, idFactory, "lesson #" + (index + 1) + " (\"" + title + "\")"),
      activities: [],
      quiz_questions: [],
    };
  });
}

// Validates/normalizes the `result` field of a successful POST /api/ai/<sid>/generate response
// (schema_name "outline_regenerate_lesson") into a plain {objective, content_blocks} pair -- ready
// for editor.js to assign onto the target lesson (lesson.objective = ..., lesson.content_blocks =
// ..., plus resetting lesson.activities/lesson.quiz_questions to [] -- see this module's header
// comment for why). Throws a clear, user-facing message if the shape is unusable; on a throw,
// editor.js applies nothing and the lesson is left exactly as it was.
export function extractRegeneratedLessonOutline(result, idFactory) {
  if (!result || typeof result !== "object") throw new Error("The AI response was empty.");
  if (typeof idFactory !== "function") throw new Error("extractRegeneratedLessonOutline requires an idFactory function.");

  var objective = (typeof result.objective === "string" && result.objective.trim())
    ? result.objective.trim()
    : "Describe what the learner will be able to do after this lesson. (placeholder -- edit me)";

  return {
    objective: objective,
    content_blocks: extractBlocks(result.blocks, idFactory, "this lesson"),
  };
}
