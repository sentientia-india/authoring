"use strict";
/*
 * Loads the real ACTIVITY_RENDERERS dispatch table out of the exported
 * player.js (see src/course_mcp_server/exporters/scorm.py -> _player_js())
 * and asserts that no entry's `match` predicate steals another (later)
 * entry's own canonical type string.
 *
 * This is the regression guard for the exact bug class that already
 * happened once this session: "fill_blank" vs "fill" are both substring
 * matches on "fill", so a broader entry placed before a narrower one would
 * silently swallow it (first-match-wins). This harness generates each
 * entry's own `key` as its canonical type string (e.g. "fill_blank" for the
 * fill_blank entry, "hotspot" for the hotspot entry, ...) and asserts that,
 * scanning the array in its real declared order, the FIRST entry whose
 * `match` returns true for that canonical string is the entry itself -- not
 * an earlier, broader entry.
 *
 * Usage: node activity_renderers_collision_harness.js <path-to-player.js>
 * Exits 0 and prints "OK" (plus the checked keys) on success. Exits 1 with a
 * descriptive message identifying the colliding pair on failure.
 */

const fs = require("fs");
const vm = require("vm");

const playerJsPath = process.argv[2];
if (!playerJsPath) {
  console.error("usage: node activity_renderers_collision_harness.js <path-to-player.js>");
  process.exit(2);
}
const playerJsSource = fs.readFileSync(playerJsPath, "utf-8");

const sandbox = {
  console,
  document: {
    getElementById() { return null; },
    querySelector() { return null; },
    querySelectorAll() { return []; },
    addEventListener() {},
    body: { dataset: {} },
  },
  localStorage: { setItem() {}, getItem() { return null; } },
  window: {},
  CourseScorm: { setSuspendData() {}, setLocation() {}, recordInteraction() {} },
};
sandbox.window = sandbox;
sandbox.globalThis = sandbox;
vm.createContext(sandbox);

// ACTIVITY_RENDERERS is declared with `const` at the top level of player.js, so
// (unlike `function`/`var` declarations) it is not automatically exposed as a
// property of the vm context. Appending an exposure statement to the SAME
// script keeps it in the same lexical scope as the `const` declaration, so
// this works without modifying scorm.py's actual exported source at all.
const instrumented = `${playerJsSource}\nglobalThis.__ACTIVITY_RENDERERS__ = ACTIVITY_RENDERERS;\n`;
vm.runInContext(instrumented, sandbox, { filename: "player.js" });

const renderers = sandbox.__ACTIVITY_RENDERERS__;
if (!Array.isArray(renderers) || renderers.length === 0) {
  console.error("ACTIVITY_RENDERERS was not found (or empty) in the exported player.js");
  process.exit(1);
}

let failures = [];
renderers.forEach((entry, ownIndex) => {
  const canonical = entry.key;
  const firstMatchIndex = renderers.findIndex((candidate) => candidate.match(canonical));
  if (firstMatchIndex !== ownIndex) {
    failures.push(
      `entry #${ownIndex} ("${entry.key}")'s canonical type string "${canonical}" is captured by an earlier ` +
      `entry #${firstMatchIndex} ("${renderers[firstMatchIndex].key}") before reaching its own renderer -- ` +
      `first-match-wins dispatch would silently route "${canonical}" activities to the wrong renderer.`
    );
  }
});

if (failures.length) {
  console.error(failures.join("\n"));
  process.exit(1);
}

console.log(`OK: no collisions among ${renderers.length} ACTIVITY_RENDERERS entries (${renderers.map((e) => e.key).join(", ")})`);
