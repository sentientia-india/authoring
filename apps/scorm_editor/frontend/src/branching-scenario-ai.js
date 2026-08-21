// Pure request/response helpers for P5-3f's "Generate branching scenario from premise" AI action.
// Follows the exact structural pattern quiz-from-content-ai.js established for P5-3c: a pure
// module with a system prompt, a request builder targeting POST /api/ai/<sid>/generate, and a
// response extractor -- no DOM access, unit-testable on its own. editor.js owns the DOM (the
// premise textarea, the trigger button, in-flight/disabled state) and applying the result via the
// same save()/pushHistory() undo-stack path every other AI action uses.
//
// SCOPE DECISION (see the P5-3f task notes): this ships the "create a brand-new activity from a
// premise" flow, not "regenerate an existing tree" -- a fresh multi-node tree from a short premise
// is the simpler and more valuable first version, and nothing here prevents a later regenerate
// flow from reusing this exact module (buildBranchingScenarioFromPremiseRequest/
// extractBranchingScenarioActivity don't care whether the target activity already existed).
//
// SCHEMA DECISION: the wire schema for schema_name "branching_scenario_from_premise" matches
// course_mcp_server.schemas.BranchingScenario/BranchingNode/BranchingChoice field for field
// (persona{name,role}, items[].{id,scenario,choices[].{label,result,feedback,next_node_id}})
// because the server validates the model's raw JSON against that real Pydantic model in
// server.py's generate_ai_content() (via _validate_ai_result_schema) before ever returning it as a
// success -- BranchingScenario's own `_validate_graph` model_validator (P5-4e) is what actually
// enforces "no dangling next_node_id, no duplicate node id" server-side; nothing here
// re-implements that graph check, this module's extractor is deliberately a second, lighter-weight
// defense-in-depth pass over just the fields it reads (same relationship extractQuizQuestions()
// has to QuizBank/QuizQuestion -- see that module's docstring).
//
// The shape this module hands back to editor.js matches ACTIVITY_TEMPLATE_REGISTRY.branching's
// build() output (activity_type "branching_scenario", optional persona, items[].{scenario,
// choices[].{label,result,feedback}}) plus the graph's node ids/next_node_id preserved on each
// item/choice, so it slots straight into lesson.activities and renders in the existing shared
// "scenes" ACTIVITY_INSPECTORS entry and exports via the existing renderNativeActivity/
// ACTIVITY_RENDERERS -- editor.js is responsible for stamping a fresh activity_id (uid("act")) at
// insertion time, exactly like insertTemplate does for a manually-inserted activity.
export var BRANCHING_SCENARIO_MIN_NODES = 3;
export var BRANCHING_SCENARIO_MAX_NODES = 6;

export var BRANCHING_SCENARIO_SYSTEM_PROMPT =
  "You are creating a short branching dialogue scenario for one lesson of an e-learning course, " +
  "from a short premise the author supplies. Produce between " +
  String(BRANCHING_SCENARIO_MIN_NODES) + " and " + String(BRANCHING_SCENARIO_MAX_NODES) +
  " scenario nodes (scenes) in total -- no more than " + String(BRANCHING_SCENARIO_MAX_NODES) +
  " and no fewer than " + String(BRANCHING_SCENARIO_MIN_NODES) + ". Return JSON with this exact " +
  "shape: {\"title\": string, \"persona\": {\"name\": string, \"role\": string} or null, " +
  "\"items\": [{\"id\": \"node_1\", \"scenario\": string, \"choices\": [{\"label\": string, " +
  "\"result\": \"best\" or \"risk\", \"feedback\": string, \"next_node_id\": string or null}]}]}. " +
  "Every node's \"id\" must be unique within items. Every choice must either be terminal " +
  "(\"next_node_id\": null, ending the scene right there with \"feedback\" as the outcome the " +
  "learner sees) or continue the scenario by setting \"next_node_id\" to the EXACT \"id\" of one " +
  "of the OTHER nodes you are defining in this SAME \"items\" array -- never invent, reuse a " +
  "deleted, or reference a node id that is not present in \"items\", and never leave a dangling " +
  "reference. Each node must have 2 to 4 choices, with at least one choice marked " +
  "\"result\": \"best\" and at least one marked \"result\": \"risk\". Ground every scene strictly " +
  "in the supplied premise and lesson context; do not introduce unrelated topics or invent facts " +
  "not implied by the premise. Return plain JSON only -- no markdown, no text outside the JSON " +
  "object.";

// `premise` is the free-text scenario premise the author typed; `lessonTitle`/`lessonObjective`
// are carried through as context only (they do not change how premise is used). Throws a clear,
// user-facing message when there is no premise to generate from.
export function buildBranchingScenarioFromPremiseRequest(premise, lessonTitle, lessonObjective, aiRequestFields) {
  var trimmedPremise = String(premise || "").trim();
  if (!trimmedPremise) throw new Error("Describe a scenario premise first.");

  var body = {
    system_prompt: BRANCHING_SCENARIO_SYSTEM_PROMPT,
    user_payload: {
      premise: trimmedPremise,
      lesson_title: lessonTitle || "",
      lesson_objective: lessonObjective || "",
      min_nodes: BRANCHING_SCENARIO_MIN_NODES,
      max_nodes: BRANCHING_SCENARIO_MAX_NODES,
    },
    schema_name: "branching_scenario_from_premise",
  };
  Object.keys(aiRequestFields || {}).forEach(function (key) { body[key] = aiRequestFields[key]; });
  return body;
}

// Validates/normalizes the `result` field of a successful POST /api/ai/<sid>/generate response
// (schema_name "branching_scenario_from_premise") into a plain activity object ready for editor.js
// to stamp an activity_id onto and push into lesson.activities -- or throws a clear, user-facing
// message if the shape is unusable. The server has already validated this same JSON against
// BranchingScenario (including its graph-integrity model_validator) before this ever runs (see
// server.py's generate_ai_content()); this is a lighter-weight second check on just the fields
// this module reads, not a re-implementation of that Pydantic/graph validation.
export function extractBranchingScenarioActivity(result, lessonObjective) {
  if (!result || typeof result !== "object") throw new Error("The AI response was empty.");

  var rawItems = Array.isArray(result.items) ? result.items : (Array.isArray(result.nodes) ? result.nodes : []);
  if (!rawItems.length) throw new Error("The AI response did not include any scenario nodes.");

  var items = rawItems.map(function (node, index) {
    var scenario = typeof (node && node.scenario) === "string" ? node.scenario.trim() : "";
    if (!scenario) throw new Error("The AI response contained a scene with no scenario text (#" + (index + 1) + ").");

    var rawChoices = Array.isArray(node && node.choices) ? node.choices : [];
    if (!rawChoices.length) throw new Error("The AI response contained a scene with no choices (#" + (index + 1) + ").");

    var choices = rawChoices.map(function (choice, choiceIndex) {
      var label = typeof (choice && choice.label) === "string" ? choice.label.trim() : "";
      if (!label) {
        throw new Error("The AI response contained a choice with no label (scene #" + (index + 1) + ", choice #" + (choiceIndex + 1) + ").");
      }
      var out = {
        label: label,
        result: (choice && choice.result === "best") ? "best" : "risk",
        feedback: typeof (choice && choice.feedback) === "string" ? choice.feedback.trim() : "",
      };
      if (choice && typeof choice.next_node_id === "string" && choice.next_node_id.trim()) {
        out.next_node_id = choice.next_node_id.trim();
      }
      return out;
    });

    var id = (node && typeof node.id === "string" && node.id.trim()) ? node.id.trim() : ("node_" + index);
    return { id: id, scenario: scenario, choices: choices };
  });

  var persona = null;
  if (result.persona && typeof result.persona === "object") {
    var name = typeof result.persona.name === "string" ? result.persona.name.trim() : "";
    var role = typeof result.persona.role === "string" ? result.persona.role.trim() : "";
    if (name && role) persona = { name: name, role: role };
  }

  var title = (typeof result.title === "string" && result.title.trim()) ? result.title.trim() : "Branching scenario";

  var activity = {
    activity_type: "branching_scenario",
    title: title,
    objective: lessonObjective || "Lead the conversation.",
    items: items,
  };
  if (persona) activity.persona = persona;
  return activity;
}
