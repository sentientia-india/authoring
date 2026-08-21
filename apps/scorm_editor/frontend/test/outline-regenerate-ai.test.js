import { describe, expect, it } from "vitest";
import {
  OUTLINE_REGENERATE_MIN_ITEMS,
  OUTLINE_REGENERATE_MAX_ITEMS,
  OUTLINE_BLOCK_ROLES,
  OUTLINE_REGENERATE_MODULE_SYSTEM_PROMPT,
  OUTLINE_REGENERATE_LESSON_SYSTEM_PROMPT,
  buildOutlineRegenerateRequest,
  extractRegeneratedModuleOutline,
  extractRegeneratedLessonOutline,
} from "../src/outline-regenerate-ai.js";
import { createUndoStack, pushEntry, undoEntry } from "../src/undo-stack.js";

function counterIdFactory() {
  var counts = {};
  return function (prefix) {
    counts[prefix] = (counts[prefix] || 0) + 1;
    return prefix + "_" + counts[prefix];
  };
}

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

describe("OUTLINE_REGENERATE system prompts", () => {
  it("are non-trivial, structure-only prompts naming the JSON contract and block role enum", () => {
    expect(OUTLINE_REGENERATE_MODULE_SYSTEM_PROMPT.length).toBeGreaterThan(100);
    expect(OUTLINE_REGENERATE_MODULE_SYSTEM_PROMPT).toContain("lessons");
    expect(OUTLINE_REGENERATE_MODULE_SYSTEM_PROMPT).toContain("structure only");
    expect(OUTLINE_REGENERATE_MODULE_SYSTEM_PROMPT).toContain("role");
    OUTLINE_BLOCK_ROLES.forEach((role) => expect(OUTLINE_REGENERATE_MODULE_SYSTEM_PROMPT).toContain(role));

    expect(OUTLINE_REGENERATE_LESSON_SYSTEM_PROMPT.length).toBeGreaterThan(100);
    expect(OUTLINE_REGENERATE_LESSON_SYSTEM_PROMPT).toContain("blocks");
    expect(OUTLINE_REGENERATE_LESSON_SYSTEM_PROMPT).toContain("structure only");
    OUTLINE_BLOCK_ROLES.forEach((role) => expect(OUTLINE_REGENERATE_LESSON_SYSTEM_PROMPT).toContain(role));
  });

  it("neither prompt asks for full lesson/block prose (structure-only decision)", () => {
    expect(OUTLINE_REGENERATE_MODULE_SYSTEM_PROMPT).toContain("Do NOT write full lesson");
    expect(OUTLINE_REGENERATE_LESSON_SYSTEM_PROMPT).toContain("Do NOT write full block");
  });

  it("declares min/max item bounds consistently", () => {
    expect(OUTLINE_REGENERATE_MIN_ITEMS).toBe(1);
    expect(OUTLINE_REGENERATE_MAX_ITEMS).toBeGreaterThan(OUTLINE_REGENERATE_MIN_ITEMS);
  });
});

describe("buildOutlineRegenerateRequest", () => {
  it("throws on an unknown scope", () => {
    expect(() => buildOutlineRegenerateRequest("course", {}, "guidance", {})).toThrow("Unknown outline regeneration scope");
  });

  it("throws when guidance is blank", () => {
    expect(() => buildOutlineRegenerateRequest("module", { title: "M" }, "   ", {})).toThrow("reshaped first");
    expect(() => buildOutlineRegenerateRequest("lesson", { title: "L" }, "", {})).toThrow("reshaped first");
  });

  it("builds a module-scope request with the module system prompt and schema_name", () => {
    var target = { title: "Onboarding", lessons: [{ title: "Welcome" }] };
    var body = buildOutlineRegenerateRequest("module", target, "make it shorter", {});
    expect(body.system_prompt).toBe(OUTLINE_REGENERATE_MODULE_SYSTEM_PROMPT);
    expect(body.schema_name).toBe("outline_regenerate_module");
    expect(body.user_payload.scope).toBe("module");
    expect(body.user_payload.guidance).toBe("make it shorter");
    expect(body.user_payload.current).toEqual(target);
  });

  it("builds a lesson-scope request with the lesson system prompt and schema_name", () => {
    var target = { title: "Lesson 1", objective: "Do X", blocks: [{ role: "intro" }] };
    var body = buildOutlineRegenerateRequest("lesson", target, "add examples", {});
    expect(body.system_prompt).toBe(OUTLINE_REGENERATE_LESSON_SYSTEM_PROMPT);
    expect(body.schema_name).toBe("outline_regenerate_lesson");
    expect(body.user_payload.guidance).toBe("add examples");
    expect(body.user_payload.current).toEqual(target);
  });

  it("trims guidance and spreads in buildAiRequestFields()-style fields untouched", () => {
    var aiFields = { text_provider: "openrouter", text_provider_api_key: "sk-live-1" };
    var body = buildOutlineRegenerateRequest("module", { title: "M", lessons: [] }, "  add a refund section  ", aiFields);
    expect(body.user_payload.guidance).toBe("add a refund section");
    expect(body.text_provider).toBe("openrouter");
    expect(body.text_provider_api_key).toBe("sk-live-1");
  });
});

describe("extractRegeneratedModuleOutline", () => {
  it("throws when result is missing/not an object", () => {
    expect(() => extractRegeneratedModuleOutline(null, counterIdFactory())).toThrow("empty");
    expect(() => extractRegeneratedModuleOutline(undefined, counterIdFactory())).toThrow("empty");
  });

  it("throws when idFactory is not a function", () => {
    expect(() => extractRegeneratedModuleOutline({ lessons: [] }, null)).toThrow("requires an idFactory");
  });

  it("throws when there are no lessons", () => {
    expect(() => extractRegeneratedModuleOutline({ lessons: [] }, counterIdFactory())).toThrow("did not include any lessons");
    expect(() => extractRegeneratedModuleOutline({}, counterIdFactory())).toThrow("did not include any lessons");
  });

  it("throws when a lesson has no blocks", () => {
    var result = { lessons: [{ title: "L1", objective: "O", blocks: [] }] };
    expect(() => extractRegeneratedModuleOutline(result, counterIdFactory())).toThrow("did not include any blocks");
  });

  it("builds full lesson objects with placeholder blocks, inheriting objectiveIds", () => {
    var result = {
      lessons: [
        {
          title: "Welcome",
          objective: "Greet the learner",
          blocks: [
            { role: "intro", direction: "Say hello" },
            { role: "explanation", direction: "Explain the plan" },
          ],
        },
        {
          title: "Wrap-up",
          objective: "Recap",
          blocks: [{ role: "summary", direction: "Recap key points" }],
        },
      ],
    };
    var lessons = extractRegeneratedModuleOutline(result, counterIdFactory(), ["obj_1"]);
    expect(lessons).toHaveLength(2);
    lessons.forEach((lesson) => {
      expect(lesson.id).toMatch(/^lesson_/);
      expect(lesson.objective_ids).toEqual(["obj_1"]);
      expect(Array.isArray(lesson.content_blocks)).toBe(true);
      expect(lesson.activities).toEqual([]);
      expect(lesson.quiz_questions).toEqual([]);
    });
    expect(lessons[0].title).toBe("Welcome");
    expect(lessons[0].content_blocks.map((b) => b.type)).toEqual(["intro", "explanation"]);
    expect(lessons[0].content_blocks[0].text).toBe("Say hello (placeholder -- edit me)");
    expect(lessons[0].content_blocks[0].id).toMatch(/^cb_/);
  });

  it("falls back an unknown role to explanation and a missing direction to a generic placeholder", () => {
    var result = { lessons: [{ title: "L", blocks: [{ role: "not_a_role" }] }] };
    var lessons = extractRegeneratedModuleOutline(result, counterIdFactory(), []);
    expect(lessons[0].content_blocks[0].type).toBe("explanation");
    expect(lessons[0].content_blocks[0].text).toBe("Write the explanation content here. (placeholder -- edit me)");
  });

  it("defaults objective_ids to an empty array when none are passed", () => {
    var result = { lessons: [{ title: "L", blocks: [{ role: "intro" }] }] };
    var lessons = extractRegeneratedModuleOutline(result, counterIdFactory());
    expect(lessons[0].objective_ids).toEqual([]);
  });

  it("mints distinct ids for every lesson and block via the injected idFactory", () => {
    var result = {
      lessons: [
        { title: "L1", blocks: [{ role: "intro" }, { role: "summary" }] },
        { title: "L2", blocks: [{ role: "intro" }] },
      ],
    };
    var lessons = extractRegeneratedModuleOutline(result, counterIdFactory(), []);
    var allIds = [].concat(lessons.map((l) => l.id), lessons[0].content_blocks.map((b) => b.id), lessons[1].content_blocks.map((b) => b.id));
    expect(new Set(allIds).size).toBe(allIds.length);
  });
});

describe("extractRegeneratedLessonOutline", () => {
  it("throws when result is missing/not an object", () => {
    expect(() => extractRegeneratedLessonOutline(null, counterIdFactory())).toThrow("empty");
  });

  it("throws when idFactory is not a function", () => {
    expect(() => extractRegeneratedLessonOutline({ blocks: [{ role: "intro" }] }, null)).toThrow("requires an idFactory");
  });

  it("throws when there are no blocks", () => {
    expect(() => extractRegeneratedLessonOutline({ blocks: [] }, counterIdFactory())).toThrow("did not include any blocks");
    expect(() => extractRegeneratedLessonOutline({}, counterIdFactory())).toThrow("did not include any blocks");
  });

  it("builds {objective, content_blocks} with placeholder text", () => {
    var result = {
      objective: "Handle refund requests",
      blocks: [
        { role: "scenario", direction: "Describe an angry customer" },
        { role: "practice", direction: "Let the learner respond" },
      ],
    };
    var outline = extractRegeneratedLessonOutline(result, counterIdFactory());
    expect(outline.objective).toBe("Handle refund requests");
    expect(outline.content_blocks.map((b) => b.type)).toEqual(["scenario", "practice"]);
    expect(outline.content_blocks[0].text).toBe("Describe an angry customer (placeholder -- edit me)");
    expect(outline.content_blocks[0].id).toMatch(/^cb_/);
  });

  it("defaults a missing objective to a placeholder string rather than throwing", () => {
    var outline = extractRegeneratedLessonOutline({ blocks: [{ role: "intro" }] }, counterIdFactory());
    expect(outline.objective.toLowerCase()).toContain("placeholder");
  });
});

// P5-5f verification requirement: exercise the confirm-before-apply gate, the undo-stack entry a
// successful regeneration produces, and that a failed/errored response leaves the original
// structure untouched. editor.js itself has no exports (it is a single un-modularized IIFE, same
// as every other AI action's wiring in this file -- see quiz-from-content-ai.test.js /
// branching-scenario-ai.test.js, neither of which unit-tests editor.js's DOM wiring either), so
// this harness reproduces runOutlineRegenerateAiAction's actual confirm-first / extract-then-apply
// / snapshot-on-success control flow using this module's real extractors plus undo-stack.js's real
// exported pushEntry/undoEntry -- the same two pieces editor.js's confirm() gate and save(true)
// call site actually wire together -- rather than re-describing that behavior in prose.
describe("module/lesson regeneration applied through editor.js's confirm+undo-stack wiring", () => {
  function makeCourseWithModule() {
    return {
      modules: [
        {
          title: "Onboarding",
          objective_ids: ["obj_1"],
          lessons: [
            { id: "lesson_orig", title: "Old lesson", objective: "Old objective", content_blocks: [{ id: "cb_orig", type: "intro", text: "Old text" }], activities: [], quiz_questions: [] },
          ],
        },
      ],
    };
  }

  // Mirrors runOutlineRegenerateAiAction(scope, flightKey, confirmMessage, buildTarget, apply):
  // confirm() is asked FIRST; only a truthy confirm result goes on to extract + apply + push a new
  // undo-stack entry. A decline, or a throw from apply/extract, must leave `course` bit-for-bit
  // identical to how it started and must NOT push an undo-stack entry.
  function runModuleRegeneration(course, module, aiResult, confirmFn, undoStack) {
    if (!confirmFn()) return { applied: false };
    var lessons = extractRegeneratedModuleOutline(aiResult, counterIdFactory(), module.objective_ids || []);
    module.lessons = lessons;
    pushEntry(undoStack, clone(course));
    return { applied: true, lessons: lessons };
  }

  it("declining the confirm applies nothing -- module.lessons and the undo stack are untouched", () => {
    var course = makeCourseWithModule();
    var before = clone(course);
    var undoStack = createUndoStack(50);
    pushEntry(undoStack, clone(course)); // initial snapshot, same as editor.js's load-time pushHistory()

    var result = runModuleRegeneration(course, course.modules[0], { lessons: [{ title: "New", blocks: [{ role: "intro" }] }] }, () => false, undoStack);

    expect(result.applied).toBe(false);
    expect(course).toEqual(before);
    expect(undoStack.entries.length).toBe(1); // no new entry was pushed
  });

  it("a malformed/errored AI response leaves the module's lessons untouched and pushes no undo entry", () => {
    var course = makeCourseWithModule();
    var before = clone(course);
    var undoStack = createUndoStack(50);
    pushEntry(undoStack, clone(course));

    expect(() => runModuleRegeneration(course, course.modules[0], { lessons: [] }, () => true, undoStack)).toThrow("did not include any lessons");
    expect(course).toEqual(before);
    expect(undoStack.entries.length).toBe(1);
  });

  it("a successful, confirmed regeneration replaces module.lessons and produces a genuine undo-stack entry that restores the original lessons", () => {
    var course = makeCourseWithModule();
    var undoStack = createUndoStack(50);
    pushEntry(undoStack, clone(course));

    var aiResult = {
      lessons: [
        { title: "New lesson A", objective: "Do A", blocks: [{ role: "intro", direction: "Open" }] },
        { title: "New lesson B", objective: "Do B", blocks: [{ role: "summary", direction: "Recap" }] },
      ],
    };
    var result = runModuleRegeneration(course, course.modules[0], aiResult, () => true, undoStack);

    expect(result.applied).toBe(true);
    expect(course.modules[0].lessons.map((l) => l.title)).toEqual(["New lesson A", "New lesson B"]);
    expect(course.modules[0].lessons[0].objective_ids).toEqual(["obj_1"]); // inherited from the module

    expect(undoStack.entries.length).toBe(2);
    var restored = undoEntry(undoStack);
    expect(restored.modules[0].lessons.map((l) => l.id)).toEqual(["lesson_orig"]);
    expect(restored.modules[0].lessons[0].title).toBe("Old lesson");
  });

  // Same contract, exercised at lesson scope: content_blocks is replaced and activities/
  // quiz_questions are cleared (see outline-regenerate-ai.js's module docstring for why), all
  // gated behind the same confirm-first / undo-stack-entry-on-success mechanism.
  function runLessonRegeneration(course, lesson, aiResult, confirmFn, undoStack) {
    if (!confirmFn()) return { applied: false };
    var outline = extractRegeneratedLessonOutline(aiResult, counterIdFactory());
    lesson.objective = outline.objective;
    lesson.content_blocks = outline.content_blocks;
    lesson.activities = [];
    lesson.quiz_questions = [];
    pushEntry(undoStack, clone(course));
    return { applied: true, outline: outline };
  }

  it("lesson scope: declining the confirm leaves content_blocks/activities/quiz_questions untouched", () => {
    var course = makeCourseWithModule();
    course.modules[0].lessons[0].activities = [{ activity_id: "act_1" }];
    course.modules[0].lessons[0].quiz_questions = [{ id: "q_1" }];
    var before = clone(course);
    var undoStack = createUndoStack(50);
    pushEntry(undoStack, clone(course));

    var result = runLessonRegeneration(course, course.modules[0].lessons[0], { objective: "New", blocks: [{ role: "intro" }] }, () => false, undoStack);

    expect(result.applied).toBe(false);
    expect(course).toEqual(before);
    expect(undoStack.entries.length).toBe(1);
  });

  it("lesson scope: a successful, confirmed regeneration replaces blocks and clears activities/quiz_questions, undoable in one step", () => {
    var course = makeCourseWithModule();
    var lesson = course.modules[0].lessons[0];
    lesson.activities = [{ activity_id: "act_1" }];
    lesson.quiz_questions = [{ id: "q_1" }];
    var undoStack = createUndoStack(50);
    pushEntry(undoStack, clone(course));

    var aiResult = { objective: "Handle refunds", blocks: [{ role: "scenario", direction: "Angry customer" }, { role: "practice", direction: "Respond" }] };
    var result = runLessonRegeneration(course, lesson, aiResult, () => true, undoStack);

    expect(result.applied).toBe(true);
    expect(lesson.objective).toBe("Handle refunds");
    expect(lesson.content_blocks.map((b) => b.type)).toEqual(["scenario", "practice"]);
    expect(lesson.activities).toEqual([]);
    expect(lesson.quiz_questions).toEqual([]);

    var restored = undoEntry(undoStack);
    var restoredLesson = restored.modules[0].lessons[0];
    expect(restoredLesson.content_blocks).toEqual([{ id: "cb_orig", type: "intro", text: "Old text" }]);
    expect(restoredLesson.activities).toEqual([{ activity_id: "act_1" }]);
    expect(restoredLesson.quiz_questions).toEqual([{ id: "q_1" }]);
  });
});
