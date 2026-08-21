// Pure helper extracted from editor.js so the undo/redo stack's push/pop
// semantics, depth cap, and redo-cleared-on-new-action rule can be unit
// tested in isolation from the DOM and from state.course (same pattern as
// move-item.js / move-between-lists.js / ai-settings.js).
//
// This module is deliberately snapshot-agnostic: it stores whatever value
// the caller hands to pushEntry() (editor.js pushes a deep clone of
// state.course) and never inspects, clones, or mutates that value itself.
// The undo/redo *mechanism* (index bookkeeping, cap, clearing redo on a new
// action) lives here; deciding *when* to snapshot, actually restoring
// state.course, re-rendering, and persisting the restored state stays in
// editor.js, which already wires a snapshot into every mutation entry point
// via save()'s pushHistory() call.

var DEFAULT_MAX_DEPTH = 50;

// Creates a fresh, empty stack. `maxDepth` caps how many entries are kept
// (oldest entries are dropped once the cap is exceeded) so a long editing
// session doesn't grow memory unboundedly.
export function createUndoStack(maxDepth) {
  return { entries: [], index: -1, maxDepth: maxDepth > 0 ? maxDepth : DEFAULT_MAX_DEPTH };
}

// Records `entry` as the new current position. Any entries beyond the
// current index (i.e. the redo history) are discarded first -- the
// standard "a new action clears redo" rule. Returns the stack for
// convenience.
export function pushEntry(stack, entry) {
  stack.entries = stack.entries.slice(0, stack.index + 1);
  stack.entries.push(entry);
  if (stack.entries.length > stack.maxDepth) stack.entries.shift();
  stack.index = stack.entries.length - 1;
  return stack;
}

export function canUndo(stack) {
  return stack.index > 0;
}

export function canRedo(stack) {
  return stack.index < stack.entries.length - 1;
}

// Moves the stack pointer one step back and returns the entry that is now
// current, or null if there is nothing to undo to (already at the oldest
// entry / stack empty). Does not mutate the stack when there is nothing to
// undo.
export function undoEntry(stack) {
  if (!canUndo(stack)) return null;
  stack.index -= 1;
  return stack.entries[stack.index];
}

// Moves the stack pointer one step forward and returns the entry that is
// now current, or null if there is nothing to redo (already at the newest
// entry). Does not mutate the stack when there is nothing to redo.
export function redoEntry(stack) {
  if (!canRedo(stack)) return null;
  stack.index += 1;
  return stack.entries[stack.index];
}
