import { describe, expect, it } from "vitest";
import { createUndoStack, pushEntry, canUndo, canRedo, undoEntry, redoEntry } from "../src/undo-stack.js";

describe("undo-stack", () => {
  it("starts empty with nothing to undo or redo", () => {
    const stack = createUndoStack(50);
    expect(stack.entries).toEqual([]);
    expect(stack.index).toBe(-1);
    expect(canUndo(stack)).toBe(false);
    expect(canRedo(stack)).toBe(false);
  });

  it("cannot undo past the first pushed entry", () => {
    const stack = createUndoStack(50);
    pushEntry(stack, "initial");
    expect(canUndo(stack)).toBe(false);
    expect(undoEntry(stack)).toBeNull();
  });

  it("undoes back to the previous entry", () => {
    const stack = createUndoStack(50);
    pushEntry(stack, "a");
    pushEntry(stack, "b");
    pushEntry(stack, "c");
    expect(canUndo(stack)).toBe(true);
    expect(undoEntry(stack)).toBe("b");
    expect(undoEntry(stack)).toBe("a");
    expect(canUndo(stack)).toBe(false);
    expect(undoEntry(stack)).toBeNull();
  });

  it("redoes forward after undoing", () => {
    const stack = createUndoStack(50);
    pushEntry(stack, "a");
    pushEntry(stack, "b");
    pushEntry(stack, "c");
    undoEntry(stack);
    undoEntry(stack);
    expect(canRedo(stack)).toBe(true);
    expect(redoEntry(stack)).toBe("b");
    expect(redoEntry(stack)).toBe("c");
    expect(canRedo(stack)).toBe(false);
    expect(redoEntry(stack)).toBeNull();
  });

  it("clears the redo branch when a new action is pushed after an undo", () => {
    const stack = createUndoStack(50);
    pushEntry(stack, "a");
    pushEntry(stack, "b");
    pushEntry(stack, "c");
    undoEntry(stack); // now at "b", "c" is a pending redo
    expect(canRedo(stack)).toBe(true);
    pushEntry(stack, "d"); // new action from "b" should drop "c"
    expect(canRedo(stack)).toBe(false);
    expect(stack.entries).toEqual(["a", "b", "d"]);
    expect(undoEntry(stack)).toBe("b");
  });

  it("caps the stack at maxDepth, dropping the oldest entries first", () => {
    const stack = createUndoStack(3);
    pushEntry(stack, "a");
    pushEntry(stack, "b");
    pushEntry(stack, "c");
    pushEntry(stack, "d"); // exceeds cap of 3, "a" should be dropped
    expect(stack.entries).toEqual(["b", "c", "d"]);
    expect(stack.index).toBe(2);
    expect(undoEntry(stack)).toBe("c");
    expect(undoEntry(stack)).toBe("b");
    expect(canUndo(stack)).toBe(false);
  });

  it("defaults maxDepth to 50 when not provided or invalid", () => {
    expect(createUndoStack().maxDepth).toBe(50);
    expect(createUndoStack(0).maxDepth).toBe(50);
    expect(createUndoStack(-5).maxDepth).toBe(50);
  });

  it("respects a custom maxDepth", () => {
    expect(createUndoStack(10).maxDepth).toBe(10);
  });

  it("does not mutate the stack when undo/redo have nothing to do", () => {
    const stack = createUndoStack(50);
    pushEntry(stack, "only");
    const before = { entries: [...stack.entries], index: stack.index };
    undoEntry(stack);
    redoEntry(stack);
    expect(stack.entries).toEqual(before.entries);
    expect(stack.index).toBe(before.index);
  });
});
