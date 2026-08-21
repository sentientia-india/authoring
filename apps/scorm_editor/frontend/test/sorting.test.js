import { describe, expect, it } from "vitest";
import { isOrderCorrect, shuffleItems } from "../src/sorting.js";

describe("shuffleItems", () => {
  it("returns a permutation of the same indices", () => {
    const result = shuffleItems([0, 1, 2, 3], () => 0.4);
    expect(result.slice().sort()).toEqual([0, 1, 2, 3]);
  });

  it("is deterministic for an injected random source", () => {
    const random = () => 0.9;
    expect(shuffleItems([0, 1, 2, 3], random)).toEqual(shuffleItems([0, 1, 2, 3], random));
  });

  it("does not mutate the input list", () => {
    const input = [0, 1, 2, 3];
    shuffleItems(input, () => 0.5);
    expect(input).toEqual([0, 1, 2, 3]);
  });

  it("never returns the original order when more than one arrangement is possible", () => {
    // A random source that always returns 0 drives Fisher-Yates to pick index 0 at every step,
    // which (for this algorithm) reproduces the original order -- exactly the case the
    // reverse-fallback in shuffleItems exists to catch.
    const result = shuffleItems([0, 1, 2, 3], () => 0);
    expect(result).not.toEqual([0, 1, 2, 3]);
  });

  it("is a no-op for a single-item list (nothing to shuffle)", () => {
    expect(shuffleItems([0], () => 0.5)).toEqual([0]);
  });

  it("is a no-op for an empty list", () => {
    expect(shuffleItems([], () => 0.5)).toEqual([]);
  });

  it("returns an empty array for non-array input", () => {
    expect(shuffleItems(null, () => 0.5)).toEqual([]);
  });

  it("defaults to Math.random when no random source is given", () => {
    const result = shuffleItems([0, 1, 2, 3]);
    expect(result.slice().sort()).toEqual([0, 1, 2, 3]);
  });
});

describe("isOrderCorrect", () => {
  it("is true when every position matches", () => {
    expect(isOrderCorrect([0, 1, 2, 3], [0, 1, 2, 3])).toBe(true);
  });

  it("is false when any position differs", () => {
    expect(isOrderCorrect([0, 2, 1, 3], [0, 1, 2, 3])).toBe(false);
  });

  it("is false for mismatched lengths", () => {
    expect(isOrderCorrect([0, 1], [0, 1, 2])).toBe(false);
  });

  it("is false for non-array inputs", () => {
    expect(isOrderCorrect(null, [0, 1, 2])).toBe(false);
    expect(isOrderCorrect([0, 1, 2], undefined)).toBe(false);
  });

  it("is true for two empty arrays", () => {
    expect(isOrderCorrect([], [])).toBe(true);
  });
});
