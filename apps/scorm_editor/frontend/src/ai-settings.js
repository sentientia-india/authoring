// Pure in-memory state for the Course Studio "AI settings" panel (P5-3: Course Studio <->
// text-provider transport + in-editor key-entry UI). Extracted from editor.js so this state
// machine is unit-testable without a DOM, same pattern as move-item.js/upload-route.js.
//
// CRITICAL storage contract (see docs/authoring-platform-plan.md P5-3 task notes): the API key
// lives ONLY in this module's own module-level `settings` variable -- an in-memory value that
// exists for the lifetime of this page load and is gone on refresh/close. It is NEVER written to
// localStorage (compare editor.js's persistRecovery(), which deliberately DOES use localStorage
// for course-content recovery -- that is a different, non-secret concern), NEVER written to
// sessionStorage, and NEVER touches `state.course` or anything that flows into PUT
// /api/course/<sid>, /api/export/<sid>, or course.json. The only function that lets this state
// leave the module is buildAiRequestFields() below, and its output is meant to be attached
// per-request to a call to POST /api/ai/<sid>/generate -- never stored anywhere itself.
export var KNOWN_TEXT_PROVIDERS = [
  { id: "openrouter", label: "OpenRouter" },
  { id: "deepseek", label: "DeepSeek" },
  { id: "openai", label: "OpenAI" },
  { id: "anthropic", label: "Anthropic" },
  { id: "gemini", label: "Gemini" },
  { id: "openai_compatible", label: "Custom endpoint" },
];

var KNOWN_PROVIDER_IDS = KNOWN_TEXT_PROVIDERS.map(function (entry) { return entry.id; });

function emptySettings() {
  return { provider: "openrouter", apiKey: "", baseUrl: "", model: "" };
}

var settings = emptySettings();

// Only the "openai_compatible" provider needs base_url/model from the user -- every other
// adapter has its own fixed default endpoint/model (see text_providers/registry.py's
// get_text_provider() docstring).
export function requiresCustomEndpointFields(providerId) {
  return providerId === "openai_compatible";
}

export function getAiSettings() {
  return Object.assign({}, settings); // defensive copy: caller can't mutate module state directly
}

export function setAiSettings(partial) {
  partial = partial || {};
  if (partial.provider !== undefined) {
    if (KNOWN_PROVIDER_IDS.indexOf(partial.provider) === -1) {
      throw new Error("Unknown text provider: " + partial.provider);
    }
    settings.provider = partial.provider;
  }
  if (partial.apiKey !== undefined) settings.apiKey = String(partial.apiKey || "");
  if (partial.baseUrl !== undefined) settings.baseUrl = String(partial.baseUrl || "");
  if (partial.model !== undefined) settings.model = String(partial.model || "");
  return getAiSettings();
}

// Used only by tests and by an explicit "forget my key" action, should one ever be added to the
// panel -- not currently wired to any button.
export function resetAiSettings() {
  settings = emptySettings();
  return getAiSettings();
}

// The ONLY function that turns this module's state into request wire fields. Field names
// mirror schemas.py's text_provider/text_provider_api_key/text_provider_base_url/
// text_provider_model exactly, so the same payload shape works against both the MCP's
// generate_course_blueprint and Course Studio's own POST /api/ai/<sid>/generate (see
// server.py's generate_ai_content()). Call this fresh for every request -- nothing here is
// cached server-side, so the key must be resent every time.
export function buildAiRequestFields() {
  var fields = { text_provider: settings.provider };
  if (settings.apiKey) fields.text_provider_api_key = settings.apiKey;
  if (requiresCustomEndpointFields(settings.provider)) {
    fields.text_provider_base_url = settings.baseUrl;
    fields.text_provider_model = settings.model;
  } else if (settings.model) {
    fields.text_provider_model = settings.model;
  }
  return fields;
}
