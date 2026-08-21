import { describe, expect, it } from "vitest";
import { checkBranchingGraph } from "../src/course-health.js";

// Cross-check between checkBranchingGraph() (pure client-side JS) and
// course_mcp_server.schemas.BranchingScenario._validate_graph (server-side Pydantic
// model_validator, see src/course_mcp_server/schemas.py lines ~880-903). There is no way to
// literally invoke the Python validator from a Vitest run, so this file hand-constructs the same
// fixture data the Python model would receive as its `nodes` list (after BranchingScenario's
// `items`/`nodes` alias resolves) and documents, fixture by fixture, exactly what
// BranchingScenario._validate_graph does with it -- quoting the relevant lines -- so the JS
// verdict can be read against that documented behavior.
//
// The two checks _validate_graph performs, in order:
//   1. Back-fill: `for index, node in enumerate(self.nodes): if not node.id: node.id = f"node_{index}"`
//      -- any falsy/missing id becomes "node_<list position>" BEFORE duplicates are checked.
//   2. Duplicate ids: `duplicate_ids = sorted({node_id for node_id in ids if ids.count(node_id) > 1})`
//      -- raises ValueError if non-empty.
//   3. Dangling refs: any `choice.next_node_id` that is not None and not in the (post-backfill) id
//      set raises ValueError, formatted as "`<node.id> -> <next_node_id>`" per choice.
// checkBranchingGraph() below reimplements exactly these three steps.

describe("checkBranchingGraph vs. BranchingScenario._validate_graph (Python)", () => {
  it("fixture 1: a valid 3-node tree with only forward references -- Python raises nothing (valid model)", () => {
    // Matches BranchingScenario._validate_graph's happy path: ids are unique, every
    // next_node_id resolves inside id_set, so neither `if duplicate_ids:` nor `if dangling:`
    // fires and the model validates successfully.
    const nodes = [
      { id: "start", scenario: "Customer calls in angry.", choices: [
        { label: "Apologize", next_node_id: "resolve" },
        { label: "Argue", next_node_id: "escalate" },
      ] },
      { id: "resolve", scenario: "Customer calms down.", choices: [{ label: "Close ticket" }] },
      { id: "escalate", scenario: "Customer demands a manager.", choices: [{ label: "Transfer" }] },
    ];
    const result = checkBranchingGraph(nodes);
    expect(result.ok).toBe(true);
    expect(result.duplicateIds).toEqual([]);
    expect(result.dangling).toEqual([]);
  });

  it("fixture 2: two nodes sharing an explicit id -- Python raises 'BranchingScenario has duplicate node id(s): n1'", () => {
    // Both nodes already have a truthy `id`, so the `if not node.id` back-fill never fires for
    // either -- `ids = ["n1", "n1"]`, `ids.count("n1") == 2`, so duplicate_ids == {"n1"} and
    // Python raises before ever reaching the dangling-reference check.
    const nodes = [
      { id: "n1", scenario: "First scene", choices: [{ label: "Go" }] },
      { id: "n1", scenario: "Second scene (id collision)", choices: [{ label: "Go" }] },
    ];
    const result = checkBranchingGraph(nodes);
    expect(result.ok).toBe(false);
    expect(result.duplicateIds).toEqual(["n1"]);
  });

  it("fixture 3: a choice references a node id that doesn't exist -- Python raises '...references a node that does not exist in nodes: n1 -> ghost'", () => {
    // ids == ["n1"], id_set == {"n1"}; the choice's next_node_id "ghost" is not None and not in
    // id_set, so dangling == ["n1 -> ghost"] and Python raises with that exact "n1 -> ghost" pair.
    const nodes = [
      { id: "n1", scenario: "Only scene", choices: [{ label: "Continue", next_node_id: "ghost" }] },
    ];
    const result = checkBranchingGraph(nodes);
    expect(result.ok).toBe(false);
    expect(result.dangling).toEqual(["n1 -> ghost"]);
  });

  it("fixture 4: missing ids are back-filled by list position, and a back-filled id can itself collide with an explicit one", () => {
    // node[0] has no id -> back-filled to "node_0" (its list index). node[1] explicitly sets
    // id "node_0", which now collides with node[0]'s back-filled id. Python's back-fill loop
    // runs first (`for index, node in enumerate(self.nodes): if not node.id: ...`), so by the
    // time duplicate_ids is computed, ids == ["node_0", "node_0"] and Python raises exactly the
    // same "duplicate node id(s): node_0" it would for two explicit collisions.
    const nodes = [
      { scenario: "Unlabeled first scene", choices: [{ label: "Go" }] },
      { id: "node_0", scenario: "Explicitly claims the backfilled id", choices: [{ label: "Go" }] },
    ];
    const result = checkBranchingGraph(nodes);
    expect(result.ok).toBe(false);
    expect(result.duplicateIds).toEqual(["node_0"]);
  });

  it("fixture 5: missing ids that do NOT collide back-fill cleanly and validate -- Python raises nothing", () => {
    // Neither node sets an id, so back-fill assigns "node_0" and "node_1" respectively -- no
    // collision, and the one next_node_id reference ("node_1") resolves inside the post-backfill
    // id set, so this is a valid model just like fixture 1.
    const nodes = [
      { scenario: "First", choices: [{ label: "Next", next_node_id: "node_1" }] },
      { scenario: "Second", choices: [{ label: "Done" }] },
    ];
    const result = checkBranchingGraph(nodes);
    expect(result.ok).toBe(true);
    expect(result.duplicateIds).toEqual([]);
    expect(result.dangling).toEqual([]);
  });
});
