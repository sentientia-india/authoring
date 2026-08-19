// Pure helper extracted from editor.js so it can be unit tested in isolation.
// Moves the element at index `from` to index `to` within `list`, in place.
// Used by both mouse/pointer drag-and-drop (handleDrop) and keyboard reordering
// (Ctrl+ArrowUp / Ctrl+ArrowDown in treeNode's keydown handler).
export function moveItem(list, from, to) {
  if (!Array.isArray(list)) return list;
  var len = list.length;
  if (from < 0 || from >= len) return list;
  var clampedTo = Math.max(0, Math.min(to, len - 1));
  if (from === clampedTo) return list;
  var item = list.splice(from, 1)[0];
  list.splice(clampedTo, 0, item);
  return list;
}
