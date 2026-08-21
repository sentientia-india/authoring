import { describe, expect, it } from "vitest";
import { countBlankTokens, isAnswerAccepted, normalizeAnswers } from "../src/fill-blank.js";

describe("countBlankTokens", () => {
  it("counts a single {{blank}} token", () => {
    expect(countBlankTokens("The capital of France is {{blank}}.")).toBe(1);
  });

  it("counts multiple {{blank}} tokens", () => {
    expect(countBlankTokens("{{blank}} plus {{blank}} equals {{blank}}.")).toBe(3);
  });

  it("returns 0 for text with no tokens", () => {
    expect(countBlankTokens("No blanks here.")).toBe(0);
  });

  it("returns 0 for empty/null/undefined input", () => {
    expect(countBlankTokens("")).toBe(0);
    expect(countBlankTokens(null)).toBe(0);
    expect(countBlankTokens(undefined)).toBe(0);
  });
});

describe("normalizeAnswers", () => {
  it("splits a comma-separated string into trimmed lowercase answers", () => {
    expect(normalizeAnswers("Paris, capital of France")).toEqual(["paris", "capital of france"]);
  });

  it("passes a real array through, lowercasing and trimming each entry", () => {
    expect(normalizeAnswers([" Paris ", "FRANCE"])).toEqual(["paris", "france"]);
  });

  it("drops empty entries produced by trailing/consecutive commas", () => {
    expect(normalizeAnswers("Paris,, ,France,")).toEqual(["paris", "france"]);
  });

  it("returns an empty array for null/undefined/empty input", () => {
    expect(normalizeAnswers(null)).toEqual([]);
    expect(normalizeAnswers(undefined)).toEqual([]);
    expect(normalizeAnswers("")).toEqual([]);
  });
});

describe("isAnswerAccepted", () => {
  it("accepts a case-insensitive, whitespace-trimmed match", () => {
    expect(isAnswerAccepted("  paris  ", "Paris")).toBe(true);
    expect(isAnswerAccepted("PARIS", "Paris")).toBe(true);
  });

  it("accepts any one of several comma-separated answers", () => {
    expect(isAnswerAccepted("france's capital", "Paris, France's Capital")).toBe(true);
  });

  it("rejects a value not in the accepted list", () => {
    expect(isAnswerAccepted("london", "Paris")).toBe(false);
  });

  it("never marks a blank correct when no accepted answers are configured", () => {
    // Regression test: an author who adds a blank but never fills in its
    // accepted-answer field must not have every learner input marked correct.
    expect(isAnswerAccepted("anything", "")).toBe(false);
    expect(isAnswerAccepted("asdf", "")).toBe(false);
    expect(isAnswerAccepted("", "")).toBe(false);
    expect(isAnswerAccepted("anything", [])).toBe(false);
    expect(isAnswerAccepted("anything", null)).toBe(false);
    expect(isAnswerAccepted("anything", undefined)).toBe(false);
  });

  it("still works exactly as before when answers ARE configured", () => {
    expect(isAnswerAccepted("  paris  ", "Paris")).toBe(true);
    expect(isAnswerAccepted("PARIS", "Paris")).toBe(true);
    expect(isAnswerAccepted("france's capital", "Paris, France's Capital")).toBe(true);
    expect(isAnswerAccepted("london", "Paris")).toBe(false);
    expect(isAnswerAccepted("Paris", ["Paris", "Capital of France"])).toBe(true);
  });
});
