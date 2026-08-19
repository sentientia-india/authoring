import { describe, expect, it } from "vitest";
import { moveItem } from "../src/move-item.js";

describe("moveItem", () => {
  it("moves an item later in the list", () => {
    const list = ["a", "b", "c", "d"];
    moveItem(list, 0, 2);
    expect(list).toEqual(["b", "c", "a", "d"]);
  });

  it("moves an item earlier in the list", () => {
    const list = ["a", "b", "c", "d"];
    moveItem(list, 3, 1);
    expect(list).toEqual(["a", "d", "b", "c"]);
  });

  it("moves an item up by one position (Ctrl+ArrowUp)", () => {
    const list = ["a", "b", "c"];
    moveItem(list, 2, 1);
    expect(list).toEqual(["a", "c", "b"]);
  });

  it("moves an item down by one position (Ctrl+ArrowDown)", () => {
    const list = ["a", "b", "c"];
    moveItem(list, 0, 1);
    expect(list).toEqual(["b", "a", "c"]);
  });

  it("is a no-op when from equals to", () => {
    const list = ["a", "b", "c"];
    moveItem(list, 1, 1);
    expect(list).toEqual(["a", "b", "c"]);
  });

  it("clamps an out-of-range target index instead of dropping the item", () => {
    const list = ["a", "b", "c"];
    moveItem(list, 0, 99);
    expect(list).toEqual(["b", "c", "a"]);
  });

  it("clamps a negative target index to the start of the list", () => {
    const list = ["a", "b", "c"];
    moveItem(list, 2, -5);
    expect(list).toEqual(["c", "a", "b"]);
  });

  it("ignores an out-of-range source index and leaves the list untouched", () => {
    const list = ["a", "b", "c"];
    moveItem(list, 10, 0);
    expect(list).toEqual(["a", "b", "c"]);
  });

  it("preserves object identity of the moved element", () => {
    const item = { id: "x" };
    const list = [{ id: "a" }, item, { id: "c" }];
    moveItem(list, 1, 0);
    expect(list[0]).toBe(item);
  });

  it("returns the mutated list", () => {
    const list = ["a", "b"];
    expect(moveItem(list, 0, 1)).toBe(list);
  });

  it("is a no-op on a non-array input", () => {
    expect(moveItem(null, 0, 1)).toBeNull();
  });
});
