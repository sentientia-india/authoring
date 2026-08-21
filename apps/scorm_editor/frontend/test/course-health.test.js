import { describe, expect, it } from "vitest";
import {
  CATEGORY_MISSING_ALT_TEXT,
  CATEGORY_EMPTY_BLOCK,
  CATEGORY_QUIZ_NO_CORRECT_ANSWER,
  CATEGORY_BRANCHING_GRAPH,
  CATEGORY_UNCOVERED_OBJECTIVE,
  CATEGORY_UNCONFIGURED_BLANK,
  CATEGORY_BLANK_TOKEN_MISMATCH,
  EMPTY_BLOCK_MIN_CHARS,
  findMissingAltText,
  findEmptyBlocks,
  findUnansweredQuizQuestions,
  findOrphanedBranchingNodes,
  checkBranchingGraph,
  findUncoveredObjectives,
  findUnconfiguredBlanks,
  findBlankTokenMismatch,
  runCourseHealthCheck,
} from "../src/course-health.js";

// A course with one issue seeded in every category, plus one clean lesson/objective so each
// finder has to actually discriminate rather than flag everything.
function buildSeededCourse() {
  return {
    learning_objectives: [
      { id: "lo_covered", text: "Covered objective" },
      { id: "lo_uncovered", text: "Uncovered objective" },
    ],
    final_assessment: {
      questions: [
        { id: "fq1", question: "Final question", options: ["A", "B"], correct_answers: ["A"], objective_ids: ["lo_covered"] },
      ],
    },
    modules: [
      {
        title: "Module 1",
        lessons: [
          {
            title: "Lesson 1",
            content_blocks: [
              { id: "cb1", type: "example", text: "This is plenty of real content.", media: { kind: "image", src: "a.png", alt: "" } },
              { id: "cb2", type: "explanation", text: "short" },
              { id: "cb3", type: "example", text: "Also fine content here, no issues at all." },
            ],
            quiz_questions: [
              { id: "q1", type: "mcq", question: "Unanswered?", options: ["A", "B"], correct_answers: [], objective_ids: ["lo_covered"] },
              { id: "q2", type: "mcq", question: "Answered fine", options: ["A", "B"], correct_answers: ["A"], objective_ids: ["lo_covered"] },
            ],
            activities: [
              {
                activity_id: "act1",
                activity_type: "branching_scenario",
                title: "Broken scene",
                items: [
                  { id: "n1", scenario: "Start", choices: [{ label: "Go", next_node_id: "missing" }] },
                  { id: "n1", scenario: "Duplicate id", choices: [{ label: "End" }] },
                ],
              },
              {
                activity_id: "act2",
                activity_type: "fill_blank",
                title: "Unconfigured blank",
                text: "The capital of France is {{blank}} and Germany's is {{blank}}.",
                blanks: [{ answers: "" }, { answers: "Berlin" }],
              },
            ],
          },
        ],
      },
    ],
  };
}

// A course engineered to trip zero findings across every category.
function buildCleanCourse() {
  return {
    learning_objectives: [{ id: "lo1", text: "Clean objective" }],
    modules: [
      {
        title: "Module 1",
        lessons: [
          {
            title: "Lesson 1",
            content_blocks: [
              { id: "cb1", type: "example", text: "Plenty of real substantive content here.", media: { kind: "image", src: "a.png", alt: "A diagram of the process" } },
            ],
            quiz_questions: [
              { id: "q1", type: "mcq", question: "Fine question", options: ["A", "B"], correct_answers: ["A"], objective_ids: ["lo1"] },
            ],
            activities: [
              {
                activity_id: "act1",
                activity_type: "branching_scenario",
                title: "Clean scene",
                items: [
                  { id: "n1", scenario: "Start", choices: [{ label: "Go", next_node_id: "n2" }] },
                  { id: "n2", scenario: "End", choices: [{ label: "Done" }] },
                ],
              },
              {
                activity_id: "act2",
                activity_type: "fill_blank",
                title: "Configured blank",
                text: "The capital of France is {{blank}}.",
                blanks: [{ answers: "Paris, France's capital" }],
              },
            ],
          },
        ],
      },
    ],
  };
}

describe("findMissingAltText", () => {
  it("flags an image block whose alt text is empty/whitespace-only", () => {
    const findings = findMissingAltText(buildSeededCourse());
    expect(findings).toHaveLength(1);
    expect(findings[0].category).toBe(CATEGORY_MISSING_ALT_TEXT);
    expect(findings[0].location).toContain("Module 1");
    expect(findings[0].location).toContain("Lesson 1");
  });

  it("ignores video media (alt text is image-only) and non-empty alt text", () => {
    const course = {
      modules: [{ title: "M", lessons: [{ title: "L", content_blocks: [
        { type: "example", media: { kind: "video", src: "v.mp4" } },
        { type: "example", media: { kind: "image", src: "a.png", alt: "  present  " } },
      ] }] }],
    };
    expect(findMissingAltText(course)).toHaveLength(0);
  });

  it("finds zero issues on a clean course", () => {
    expect(findMissingAltText(buildCleanCourse())).toHaveLength(0);
  });
});

describe("findEmptyBlocks", () => {
  it("flags a block under the documented character threshold and reports the threshold", () => {
    const findings = findEmptyBlocks(buildSeededCourse());
    expect(findings).toHaveLength(1);
    expect(findings[0].category).toBe(CATEGORY_EMPTY_BLOCK);
    expect(EMPTY_BLOCK_MIN_CHARS).toBe(10);
    expect(findings[0].message).toContain("10-character threshold");
  });

  it("flags a fully empty block with an 'empty' message, not a length message", () => {
    const course = { modules: [{ title: "M", lessons: [{ title: "L", content_blocks: [{ type: "intro", text: "   " }] }] }] };
    const findings = findEmptyBlocks(course);
    expect(findings).toHaveLength(1);
    expect(findings[0].message).toBe("Content block is empty.");
  });

  it("finds zero issues on a clean course", () => {
    expect(findEmptyBlocks(buildCleanCourse())).toHaveLength(0);
  });
});

describe("findUnansweredQuizQuestions", () => {
  it("flags a question with an empty correct_answers array", () => {
    const findings = findUnansweredQuizQuestions(buildSeededCourse());
    expect(findings).toHaveLength(1);
    expect(findings[0].category).toBe(CATEGORY_QUIZ_NO_CORRECT_ANSWER);
    expect(findings[0].message).toContain("no correct answer marked");
  });

  it("flags a question whose correct answer is not among its own options", () => {
    const course = { modules: [{ title: "M", lessons: [{ title: "L", quiz_questions: [
      { id: "q1", question: "Bad", options: ["A", "B"], correct_answers: ["C"] },
    ] }] }] };
    const findings = findUnansweredQuizQuestions(course);
    expect(findings).toHaveLength(1);
    expect(findings[0].message).toContain("not one of its listed options");
  });

  it("checks final_assessment.questions in addition to lesson quiz_questions", () => {
    const course = {
      modules: [],
      final_assessment: { questions: [{ id: "fq1", question: "Q", options: ["A"], correct_answers: [] }] },
    };
    const findings = findUnansweredQuizQuestions(course);
    expect(findings).toHaveLength(1);
    expect(findings[0].location).toContain("Final assessment");
  });

  it("finds zero issues on a clean course", () => {
    expect(findUnansweredQuizQuestions(buildCleanCourse())).toHaveLength(0);
  });
});

describe("findOrphanedBranchingNodes", () => {
  it("flags both a duplicate node id and a dangling next_node_id reference", () => {
    const findings = findOrphanedBranchingNodes(buildSeededCourse());
    expect(findings).toHaveLength(2);
    expect(findings.map((f) => f.category)).toEqual([CATEGORY_BRANCHING_GRAPH, CATEGORY_BRANCHING_GRAPH]);
    expect(findings.some((f) => f.message.includes("Duplicate branching node id"))).toBe(true);
    expect(findings.some((f) => f.message.includes("does not exist"))).toBe(true);
  });

  it("ignores non-branching activity types", () => {
    const course = { modules: [{ title: "M", lessons: [{ title: "L", activities: [
      { activity_type: "flashcards", items: [{ id: "n1", scenario: "x", choices: [{ label: "y", next_node_id: "missing" }] }] },
    ] }] }] };
    expect(findOrphanedBranchingNodes(course)).toHaveLength(0);
  });

  it("finds zero issues on a clean course", () => {
    expect(findOrphanedBranchingNodes(buildCleanCourse())).toHaveLength(0);
  });
});

describe("findUncoveredObjectives", () => {
  it("flags an objective with zero linked quiz questions across lessons and final assessment", () => {
    const findings = findUncoveredObjectives(buildSeededCourse());
    expect(findings).toHaveLength(1);
    expect(findings[0].category).toBe(CATEGORY_UNCOVERED_OBJECTIVE);
    expect(findings[0].location).toContain("Uncovered objective");
  });

  it("finds zero issues on a clean course", () => {
    expect(findUncoveredObjectives(buildCleanCourse())).toHaveLength(0);
  });
});

describe("findUnconfiguredBlanks", () => {
  it("flags a fill_blank activity where at least one blank has no accepted answers", () => {
    const findings = findUnconfiguredBlanks(buildSeededCourse());
    expect(findings).toHaveLength(1);
    expect(findings[0].category).toBe(CATEGORY_UNCONFIGURED_BLANK);
    expect(findings[0].location).toContain("Unconfigured blank");
    expect(findings[0].message).toContain("1 of 2 blanks");
  });

  it("treats an empty array, empty string, and whitespace-only answers as unconfigured", () => {
    const course = { modules: [{ title: "M", lessons: [{ title: "L", activities: [
      {
        activity_type: "fill_blank",
        title: "All bad",
        blanks: [{ answers: [] }, { answers: "   " }, { answer: "" }, {}],
      },
    ] }] }] };
    const findings = findUnconfiguredBlanks(course);
    expect(findings).toHaveLength(1);
    expect(findings[0].message).toContain("4 of 4 blanks");
  });

  it("ignores non-fill_blank activity types", () => {
    const course = { modules: [{ title: "M", lessons: [{ title: "L", activities: [
      { activity_type: "flashcards", blanks: [{ answers: "" }] },
    ] }] }] };
    expect(findUnconfiguredBlanks(course)).toHaveLength(0);
  });

  it("finds zero issues on a clean course", () => {
    expect(findUnconfiguredBlanks(buildCleanCourse())).toHaveLength(0);
  });
});

describe("findBlankTokenMismatch", () => {
  it("flags a fill_blank activity where the text has MORE {{blank}} tokens than configured answer rows", () => {
    const course = { modules: [{ title: "M", lessons: [{ title: "L", activities: [
      {
        activity_type: "fill_blank",
        title: "Missing a row",
        text: "{{blank}} {{blank}} {{blank}}",
        blanks: [{ answers: "one" }, { answers: "two" }],
      },
    ] }] }] };
    const findings = findBlankTokenMismatch(course);
    expect(findings).toHaveLength(1);
    expect(findings[0].category).toBe(CATEGORY_BLANK_TOKEN_MISMATCH);
    expect(findings[0].location).toContain("Missing a row");
    expect(findings[0].message).toContain("3 {{blank}} tokens in the text but 2 answer rows configured");
    expect(findings[0].message).toContain("learners cannot complete the missing blank");
  });

  it("also flags the reverse mismatch (fewer tokens than configured rows)", () => {
    const course = { modules: [{ title: "M", lessons: [{ title: "L", activities: [
      {
        activity_type: "fill_blank",
        title: "Extra row",
        text: "Only {{blank}} here.",
        blanks: [{ answers: "one" }, { answers: "two" }],
      },
    ] }] }] };
    const findings = findBlankTokenMismatch(course);
    expect(findings).toHaveLength(1);
    expect(findings[0].message).toContain("1 {{blank}} token in the text but 2 answer rows configured");
    expect(findings[0].message).toContain("extra unused answer row");
  });

  it("produces zero findings when token count and row count match, even with unconfigured answers", () => {
    // This check is orthogonal to findUnconfiguredBlanks -- it only cares about counts lining up.
    const findings = findBlankTokenMismatch(buildSeededCourse());
    expect(findings).toHaveLength(0);
  });

  it("ignores non-fill_blank activity types", () => {
    const course = { modules: [{ title: "M", lessons: [{ title: "L", activities: [
      { activity_type: "flashcards", text: "{{blank}} {{blank}}", blanks: [] },
    ] }] }] };
    expect(findBlankTokenMismatch(course)).toHaveLength(0);
  });

  it("finds zero issues on a clean course", () => {
    expect(findBlankTokenMismatch(buildCleanCourse())).toHaveLength(0);
  });
});

describe("checkBranchingGraph prototype pollution guard", () => {
  it("flags a dangling next_node_id of \"__proto__\" as missing, instead of silently resolving via the prototype chain", () => {
    // Regression test for the plain-object hash set bug: `{}["__proto__"] = true` is a silent
    // no-op (it reassigns the prototype rather than setting an own property), yet
    // `{}["__proto__"]` still reads back truthy afterwards (it resolves to Object.prototype via
    // the prototype chain) -- so a node id/next_node_id of "__proto__" would previously bypass
    // the dangling-reference check entirely, even though no node with that id exists.
    const nodes = [
      { id: "n1", choices: [{ label: "Go", next_node_id: "__proto__" }] },
    ];
    const result = checkBranchingGraph(nodes);
    expect(result.ok).toBe(false);
    expect(result.dangling).toEqual(["n1 -> __proto__"]);
  });

  it("flags \"__proto__\" as a duplicate id when it appears twice, instead of silently no-op'ing the count", () => {
    const nodes = [
      { id: "__proto__", choices: [] },
      { id: "__proto__", choices: [] },
    ];
    const result = checkBranchingGraph(nodes);
    expect(result.ok).toBe(false);
    expect(result.duplicateIds).toEqual(["__proto__"]);
  });

  it("does not flag a valid reference to a real node named \"constructor\"", () => {
    const nodes = [
      { id: "constructor", choices: [] },
      { id: "n1", choices: [{ label: "Go", next_node_id: "constructor" }] },
    ];
    const result = checkBranchingGraph(nodes);
    expect(result.ok).toBe(true);
    expect(result.dangling).toEqual([]);
  });
});

describe("runCourseHealthCheck", () => {
  it("produces exactly one finding per seeded category (6 categories, one issue each except branching's 2)", () => {
    const findings = runCourseHealthCheck(buildSeededCourse());
    // 1 alt-text + 1 empty-block + 1 quiz + 2 branching (dup + dangling) + 1 objective + 1 fill-blank = 7
    expect(findings).toHaveLength(7);
    const categories = new Set(findings.map((f) => f.category));
    expect(categories).toEqual(new Set([
      CATEGORY_MISSING_ALT_TEXT,
      CATEGORY_EMPTY_BLOCK,
      CATEGORY_QUIZ_NO_CORRECT_ANSWER,
      CATEGORY_BRANCHING_GRAPH,
      CATEGORY_UNCOVERED_OBJECTIVE,
      CATEGORY_UNCONFIGURED_BLANK,
    ]));
  });

  it("produces zero findings across all categories for a clean course", () => {
    expect(runCourseHealthCheck(buildCleanCourse())).toEqual([]);
  });

  it("returns an empty array (not a throw) when there is no course yet", () => {
    expect(runCourseHealthCheck(null)).toEqual([]);
    expect(runCourseHealthCheck(undefined)).toEqual([]);
  });
});
