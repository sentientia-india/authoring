import { describe, expect, it } from "vitest";
import { computeRegionPercentages, isRegionSizeUsable, rectFromPoints } from "../src/hotspot-geometry.js";

describe("computeRegionPercentages", () => {
  it("converts a rectangle in the top-left quadrant to percentages", () => {
    const displayed = { left: 100, top: 50, width: 400, height: 200 };
    const drawn = { left: 200, top: 100, width: 40, height: 20 };
    expect(computeRegionPercentages(displayed, drawn)).toEqual({
      x_pct: 25,
      y_pct: 25,
      width_pct: 10,
      height_pct: 10,
    });
  });

  it("normalizes a drag that moved up and to the left (negative width/height)", () => {
    const displayed = { left: 0, top: 0, width: 200, height: 100 };
    // Drag started at (100, 50) and ended at (50, 25): rectFromPoints would produce
    // width/height of -50/-25.
    const drawn = { left: 100, top: 50, width: -50, height: -25 };
    const result = computeRegionPercentages(displayed, drawn);
    expect(result.x_pct).toBe(25);
    expect(result.y_pct).toBe(25);
    expect(result.width_pct).toBe(25);
    expect(result.height_pct).toBe(25);
  });

  it("clamps a region that would extend past the image's right/bottom edge", () => {
    const displayed = { left: 0, top: 0, width: 100, height: 100 };
    const drawn = { left: 80, top: 90, width: 50, height: 50 };
    const result = computeRegionPercentages(displayed, drawn);
    expect(result.x_pct).toBe(80);
    expect(result.y_pct).toBe(90);
    expect(result.width_pct).toBe(20);
    expect(result.height_pct).toBe(10);
  });

  it("clamps a drawn rectangle that starts before the image's own bounds", () => {
    const displayed = { left: 100, top: 100, width: 200, height: 200 };
    const drawn = { left: 50, top: 60, width: 40, height: 40 };
    const result = computeRegionPercentages(displayed, drawn);
    expect(result.x_pct).toBe(0);
    expect(result.y_pct).toBe(0);
  });

  it("guards against a zero-width displayed image (division by zero)", () => {
    const displayed = { left: 0, top: 0, width: 0, height: 0 };
    const drawn = { left: 0, top: 0, width: 10, height: 10 };
    const result = computeRegionPercentages(displayed, drawn);
    expect(Number.isFinite(result.x_pct)).toBe(true);
    expect(Number.isFinite(result.width_pct)).toBe(true);
  });
});

describe("rectFromPoints", () => {
  it("builds a rectangle from a start and end point dragged down-right", () => {
    expect(rectFromPoints({ x: 10, y: 20 }, { x: 60, y: 45 })).toEqual({
      left: 10,
      top: 20,
      width: 50,
      height: 25,
    });
  });

  it("produces negative width/height for a drag up-and-left", () => {
    expect(rectFromPoints({ x: 60, y: 45 }, { x: 10, y: 20 })).toEqual({
      left: 60,
      top: 45,
      width: -50,
      height: -25,
    });
  });
});

describe("isRegionSizeUsable", () => {
  it("rejects a near-zero-size drag (accidental click)", () => {
    expect(isRegionSizeUsable({ width: 1, height: 1 })).toBe(false);
  });

  it("accepts a rectangle at least the default 4px threshold in both dimensions", () => {
    expect(isRegionSizeUsable({ width: 4, height: 4 })).toBe(true);
    expect(isRegionSizeUsable({ width: 20, height: 3 })).toBe(false);
  });

  it("treats negative width/height (up-left drags) the same as positive", () => {
    expect(isRegionSizeUsable({ width: -20, height: -20 })).toBe(true);
  });

  it("respects a custom minimum size threshold", () => {
    expect(isRegionSizeUsable({ width: 8, height: 8 }, 10)).toBe(false);
    expect(isRegionSizeUsable({ width: 12, height: 12 }, 10)).toBe(true);
  });
});
