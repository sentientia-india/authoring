import { describe, expect, it } from "vitest";
import {
  LESSON_SKELETONS,
  LESSON_SKELETON_IDS,
  buildLessonFromSkeleton,
} from "../src/lesson-skeletons.js";

function counterIdFactory() {
  var counts = {};
  return function (prefix) {
    counts[prefix] = (counts[prefix] || 0) + 1;
    return prefix + "_" + counts[prefix];
  };
}

describe("LESSON_SKELETON_IDS", () => {
  it("lists exactly the registered skeletons, in registry order", () => {
    expect(LESSON_SKELETON_IDS).toEqual(Object.keys(LESSON_SKELETONS));
    expect(LESSON_SKELETON_IDS).toEqual(
      expect.arrayContaining(["standard_onboarding", "compliance_training", "quick_reference"])
    );
    expect(LESSON_SKELETON_IDS.length).toBe(3);
  });
});

describe("buildLessonFromSkeleton", () => {
  it("throws on an unknown skeleton id", () => {
    expect(() => buildLessonFromSkeleton("nope", counterIdFactory())).toThrow("Unknown lesson skeleton");
  });

  it("throws when idFactory is not a function", () => {
    expect(() => buildLessonFromSkeleton("standard_onboarding", null)).toThrow("requires an idFactory");
  });

  it("builds every skeleton into a lesson with the exact shape editor.js's blank-lesson push uses", () => {
    LESSON_SKELETON_IDS.forEach((skeletonId) => {
      var lesson = buildLessonFromSkeleton(skeletonId, counterIdFactory(), ["obj_1"]);
      expect(typeof lesson.id).toBe("string");
      expect(lesson.id).toMatch(/^lesson_/);
      expect(typeof lesson.title).toBe("string");
      expect(lesson.title.length).toBeGreaterThan(0);
      expect(typeof lesson.duration_minutes).toBe("number");
      expect(lesson.objective_ids).toEqual(["obj_1"]);
      expect(typeof lesson.objective).toBe("string");
      expect(Array.isArray(lesson.content_blocks)).toBe(true);
      expect(lesson.content_blocks.length).toBeGreaterThan(0);
      expect(Array.isArray(lesson.activities)).toBe(true);
      expect(Array.isArray(lesson.quiz_questions)).toBe(true);
    });
  });

  it("defaults objective_ids to an empty array when none are passed", () => {
    var lesson = buildLessonFromSkeleton("quick_reference", counterIdFactory());
    expect(lesson.objective_ids).toEqual([]);
  });

  it("mints a fresh, distinct id for every block/activity/question via the injected idFactory", () => {
    var lesson = buildLessonFromSkeleton("compliance_training", counterIdFactory(), []);
    var allIds = []
      .concat(lesson.content_blocks.map((b) => b.id))
      .concat(lesson.activities.map((a) => a.activity_id))
      .concat(lesson.quiz_questions.map((q) => q.id));
    var uniqueIds = new Set(allIds);
    expect(uniqueIds.size).toBe(allIds.length);
    expect(allIds.length).toBeGreaterThan(0);
  });

  describe("standard_onboarding", () => {
    it("is intro + 2 explanation blocks + summary, with a 2-question knowledge-check quiz and no activities", () => {
      var lesson = buildLessonFromSkeleton("standard_onboarding", counterIdFactory(), []);
      expect(lesson.content_blocks.map((b) => b.type)).toEqual([
        "intro",
        "explanation",
        "explanation",
        "summary",
      ]);
      expect(lesson.activities).toEqual([]);
      expect(lesson.quiz_questions.length).toBe(2);
      lesson.quiz_questions.forEach((q) => {
        expect(q.type).toBe("mcq");
        expect(q.correct_answers.length).toBe(1);
        expect(q.options).toContain(q.correct_answers[0]);
      });
    });
  });

  describe("compliance_training", () => {
    it("is intro + 2 policy explanation blocks + summary, one decision activity, and a mandatory quiz question", () => {
      var lesson = buildLessonFromSkeleton("compliance_training", counterIdFactory(), []);
      expect(lesson.content_blocks.map((b) => b.type)).toEqual([
        "intro",
        "explanation",
        "explanation",
        "summary",
      ]);
      expect(lesson.activities.length).toBe(1);
      expect(lesson.activities[0].activity_type).toBe("scenario_decision_tree");
      expect(lesson.activities[0].items[0].choices.length).toBe(2);
      expect(lesson.quiz_questions.length).toBe(1);
      expect(lesson.quiz_questions[0].type).toBe("mcq");
    });
  });

  describe("quick_reference", () => {
    it("is a single dense explanation block plus a checklist block, no activities or quiz", () => {
      var lesson = buildLessonFromSkeleton("quick_reference", counterIdFactory(), []);
      expect(lesson.content_blocks.map((b) => b.type)).toEqual(["explanation", "checklist"]);
      expect(lesson.activities).toEqual([]);
      expect(lesson.quiz_questions).toEqual([]);
    });
  });

  it("keeps every generated block/question/activity's text clearly labeled as placeholder", () => {
    LESSON_SKELETON_IDS.forEach((skeletonId) => {
      var lesson = buildLessonFromSkeleton(skeletonId, counterIdFactory(), []);
      lesson.content_blocks.forEach((block) => {
        expect(block.text.toLowerCase()).toContain("placeholder");
      });
      lesson.quiz_questions.forEach((question) => {
        expect(question.question.toLowerCase()).toContain("placeholder");
      });
    });
  });
});
