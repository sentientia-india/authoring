import { describe, expect, it } from "vitest";
import { moveBetweenLists } from "../src/move-between-lists.js";

describe("moveBetweenLists", () => {
  it("moves an item from one list into another at the given index", () => {
    const source = ["a", "b", "c"];
    const dest = ["x", "y"];
    moveBetweenLists(source, 1, dest, 1);
    expect(source).toEqual(["a", "c"]);
    expect(dest).toEqual(["x", "b", "y"]);
  });

  it("appends to the end of the destination list when destIndex equals its length", () => {
    const source = ["a", "b"];
    const dest = ["x", "y"];
    moveBetweenLists(source, 0, dest, dest.length);
    expect(source).toEqual(["b"]);
    expect(dest).toEqual(["x", "y", "a"]);
  });

  it("inserts at the front of the destination list", () => {
    const source = ["a", "b"];
    const dest = ["x", "y"];
    moveBetweenLists(source, 0, dest, 0);
    expect(source).toEqual(["b"]);
    expect(dest).toEqual(["a", "x", "y"]);
  });

  it("does not duplicate or lose items across two lists", () => {
    const source = ["a", "b", "c"];
    const dest = ["x", "y"];
    moveBetweenLists(source, 2, dest, 1);
    const all = [...source, ...dest].sort();
    expect(all).toEqual(["a", "b", "x", "y", "c"].sort());
    expect(source.length + dest.length).toBe(5);
  });

  it("handles source and dest being the same array reference (moving later)", () => {
    const list = ["a", "b", "c", "d"];
    moveBetweenLists(list, 0, list, 3);
    // Removing "a" shifts everything left; inserting "before original index 3"
    // (which was "d") lands it just before "d".
    expect(list).toEqual(["b", "c", "a", "d"]);
  });

  it("handles source and dest being the same array reference (moving earlier)", () => {
    const list = ["a", "b", "c", "d"];
    moveBetweenLists(list, 3, list, 1);
    expect(list).toEqual(["a", "d", "b", "c"]);
  });

  it("is a no-op when dropped back onto its own original position (same list, same index)", () => {
    const list = ["a", "b", "c"];
    moveBetweenLists(list, 1, list, 1);
    expect(list).toEqual(["a", "b", "c"]);
  });

  it("treats an undefined destIndex as append", () => {
    const source = ["a", "b"];
    const dest = ["x"];
    moveBetweenLists(source, 1, dest, undefined);
    expect(dest).toEqual(["x", "b"]);
  });

  it("clamps a destIndex beyond the destination length to an append", () => {
    const source = ["a"];
    const dest = ["x", "y"];
    moveBetweenLists(source, 0, dest, 99);
    expect(dest).toEqual(["x", "y", "a"]);
  });

  it("ignores an out-of-range source index and leaves both lists untouched", () => {
    const source = ["a", "b"];
    const dest = ["x"];
    moveBetweenLists(source, 10, dest, 0);
    expect(source).toEqual(["a", "b"]);
    expect(dest).toEqual(["x"]);
  });

  it("preserves object identity of the moved element", () => {
    const item = { id: "block-1" };
    const source = [{ id: "a" }, item];
    const dest = [{ id: "b" }];
    moveBetweenLists(source, 1, dest, 0);
    expect(dest[0]).toBe(item);
  });

  it("returns the moved item", () => {
    const source = ["a", "b"];
    const dest = [];
    expect(moveBetweenLists(source, 0, dest, 0)).toBe("a");
  });

  it("returns undefined and no-ops on non-array inputs", () => {
    expect(moveBetweenLists(null, 0, [], 0)).toBeUndefined();
    expect(moveBetweenLists([], 0, null, 0)).toBeUndefined();
  });
});
