import { describe, expect, it } from "vitest";
import {
  BRANCHING_SCENARIO_MIN_NODES,
  BRANCHING_SCENARIO_MAX_NODES,
  BRANCHING_SCENARIO_SYSTEM_PROMPT,
  buildBranchingScenarioFromPremiseRequest,
  extractBranchingScenarioActivity,
} from "../src/branching-scenario-ai.js";

describe("BRANCHING_SCENARIO_SYSTEM_PROMPT", () => {
  it("is a non-trivial prompt that bounds the node count and names the BranchingScenario-shaped JSON contract", () => {
    expect(BRANCHING_SCENARIO_MIN_NODES).toBe(3);
    expect(BRANCHING_SCENARIO_MAX_NODES).toBe(6);
    expect(BRANCHING_SCENARIO_SYSTEM_PROMPT.length).toBeGreaterThan(100);
    expect(BRANCHING_SCENARIO_SYSTEM_PROMPT).toContain("3");
    expect(BRANCHING_SCENARIO_SYSTEM_PROMPT).toContain("6");
    expect(BRANCHING_SCENARIO_SYSTEM_PROMPT).toContain("next_node_id");
    expect(BRANCHING_SCENARIO_SYSTEM_PROMPT).toContain("items");
    expect(BRANCHING_SCENARIO_SYSTEM_PROMPT).toMatch(/same.*items|items.*same/i);
  });
});

describe("buildBranchingScenarioFromPremiseRequest", () => {
  it("throws when there is no premise text", () => {
    expect(() => buildBranchingScenarioFromPremiseRequest("", "Lesson", "Objective", {})).toThrow("premise");
    expect(() => buildBranchingScenarioFromPremiseRequest("   ", "Lesson", "Objective", {})).toThrow("premise");
    expect(() => buildBranchingScenarioFromPremiseRequest(null, "Lesson", "Objective", {})).toThrow("premise");
  });

  it("builds a request carrying the fixed system prompt and schema_name", () => {
    const body = buildBranchingScenarioFromPremiseRequest(
      "A customer calls angry about a billing error.",
      "Handling difficult calls",
      "Resolve billing complaints calmly.",
      {}
    );
    expect(body.system_prompt).toBe(BRANCHING_SCENARIO_SYSTEM_PROMPT);
    expect(body.schema_name).toBe("branching_scenario_from_premise");
    expect(body.user_payload.premise).toBe("A customer calls angry about a billing error.");
    expect(body.user_payload.lesson_title).toBe("Handling difficult calls");
    expect(body.user_payload.lesson_objective).toBe("Resolve billing complaints calmly.");
    expect(body.user_payload.min_nodes).toBe(BRANCHING_SCENARIO_MIN_NODES);
    expect(body.user_payload.max_nodes).toBe(BRANCHING_SCENARIO_MAX_NODES);
  });

  it("trims the premise", () => {
    const body = buildBranchingScenarioFromPremiseRequest("  a premise  ", "L", "O", {});
    expect(body.user_payload.premise).toBe("a premise");
  });

  it("spreads in buildAiRequestFields()-style fields untouched (never nested)", () => {
    const aiFields = { text_provider: "openrouter", text_provider_api_key: "sk-live-1" };
    const body = buildBranchingScenarioFromPremiseRequest("premise", "L", "O", aiFields);
    expect(body.text_provider).toBe("openrouter");
    expect(body.text_provider_api_key).toBe("sk-live-1");
  });
});

describe("extractBranchingScenarioActivity", () => {
  const validResult = {
    title: "Angry customer call",
    persona: { name: "Jordan", role: "Customer" },
    items: [
      {
        id: "node_1",
        scenario: "Jordan calls in furious about a billing error.",
        choices: [
          { label: "Apologize and investigate", result: "best", feedback: "Great start.", next_node_id: "node_2" },
          { label: "Argue with Jordan", result: "risk", feedback: "This escalates the call.", next_node_id: null },
        ],
      },
      {
        id: "node_2",
        scenario: "You confirm the billing error and offer a refund.",
        choices: [
          { label: "Offer a full refund", result: "best", feedback: "Jordan is satisfied.", next_node_id: null },
          { label: "Offer nothing", result: "risk", feedback: "Jordan hangs up angry.", next_node_id: null },
        ],
      },
    ],
  };

  it("returns a branching_scenario activity shape ready for lesson.activities", () => {
    const activity = extractBranchingScenarioActivity(validResult, "Resolve billing complaints calmly.");
    expect(activity.activity_type).toBe("branching_scenario");
    expect(activity.title).toBe("Angry customer call");
    expect(activity.objective).toBe("Resolve billing complaints calmly.");
    expect(activity.persona).toEqual({ name: "Jordan", role: "Customer" });
    expect(activity.items).toHaveLength(2);
    expect(activity.items[0]).toEqual({
      id: "node_1",
      scenario: "Jordan calls in furious about a billing error.",
      choices: [
        { label: "Apologize and investigate", result: "best", feedback: "Great start.", next_node_id: "node_2" },
        { label: "Argue with Jordan", result: "risk", feedback: "This escalates the call." },
      ],
    });
  });

  it("omits next_node_id on a terminal choice rather than writing null", () => {
    const activity = extractBranchingScenarioActivity(validResult, "O");
    expect(activity.items[0].choices[1]).not.toHaveProperty("next_node_id");
  });

  it("omits persona when absent", () => {
    const withoutPersona = { title: validResult.title, items: validResult.items };
    const activity = extractBranchingScenarioActivity(withoutPersona, "O");
    expect(activity).not.toHaveProperty("persona");
  });

  it("falls back to a default title/objective when missing", () => {
    const withoutTitle = { persona: validResult.persona, items: validResult.items };
    const activity = extractBranchingScenarioActivity(withoutTitle, "");
    expect(activity.title).toBe("Branching scenario");
    expect(activity.objective).toBe("Lead the conversation.");
  });

  it("backfills a missing node id from list position", () => {
    const result = { items: [{ scenario: "S", choices: [{ label: "L", result: "best", feedback: "F" }] }] };
    const activity = extractBranchingScenarioActivity(result, "O");
    expect(activity.items[0].id).toBe("node_0");
  });

  it("throws when result is missing/not an object", () => {
    expect(() => extractBranchingScenarioActivity(null)).toThrow("empty");
    expect(() => extractBranchingScenarioActivity(undefined)).toThrow("empty");
    expect(() => extractBranchingScenarioActivity("just a string")).toThrow("empty");
  });

  it("throws when there are no nodes", () => {
    expect(() => extractBranchingScenarioActivity({ items: [] })).toThrow("did not include any scenario nodes");
    expect(() => extractBranchingScenarioActivity({})).toThrow("did not include any scenario nodes");
  });

  it("throws on a node with no scenario text", () => {
    const result = { items: [{ id: "n1", scenario: "  ", choices: [{ label: "L" }] }] };
    expect(() => extractBranchingScenarioActivity(result)).toThrow("no scenario text (#1)");
  });

  it("throws on a node with no choices", () => {
    const result = { items: [{ id: "n1", scenario: "S", choices: [] }] };
    expect(() => extractBranchingScenarioActivity(result)).toThrow("no choices (#1)");
  });

  it("throws on a choice with no label", () => {
    const result = { items: [{ id: "n1", scenario: "S", choices: [{ label: "  " }] }] };
    expect(() => extractBranchingScenarioActivity(result)).toThrow("no label");
  });
});
