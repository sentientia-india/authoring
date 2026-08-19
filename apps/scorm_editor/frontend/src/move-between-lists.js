// Pure helper extracted from editor.js so it can be unit tested in isolation,
// alongside moveItem (move-item.js). Where moveItem only reorders within a
// single array, moveBetweenLists removes an item from one array and inserts
// it into another — the general case that also covers "same array" (moveItem
// could be reimplemented in terms of this, but is left alone since it's
// already tested and used by the keyboard-reorder path, which never crosses
// lists).
//
// `destIndex` is interpreted as "insert before this index of destList, as it
// stood before the removal from sourceList" — i.e. callers compute it from
// the pre-drag/pre-drop list, not from a list they've already mutated. When
// sourceList and destList are the *same* array reference (a cross-list drop
// can still resolve to the same list — e.g. dropping a lesson on a module
// node that happens to already be its own module), removing the source item
// shifts every later index down by one, so this function adjusts destIndex
// itself rather than requiring the caller to.
export function moveBetweenLists(sourceList, sourceIndex, destList, destIndex) {
  if (!Array.isArray(sourceList) || !Array.isArray(destList)) return undefined;
  if (sourceIndex < 0 || sourceIndex >= sourceList.length) return undefined;

  var item = sourceList.splice(sourceIndex, 1)[0];

  var insertAt = destIndex;
  if (typeof insertAt !== "number" || isNaN(insertAt)) insertAt = destList.length;
  if (sourceList === destList && sourceIndex < insertAt) insertAt -= 1;
  insertAt = Math.max(0, Math.min(insertAt, destList.length));

  destList.splice(insertAt, 0, item);
  return item;
}
