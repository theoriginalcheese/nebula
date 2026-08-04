/* The drag maths in customise mode, run without a window.
 *
 *     node tests/test_v4_drag.js
 *
 * Why this file exists
 * --------------------
 * The four blockers in the code audit were all in `app.js`, and all four were
 * invisible to every gate the project had: `lint_tokens.py` reads stylesheets,
 * `test_v4_customise.py` checks the Python normalisation contract, and
 * `tools/shoot.py` photographs a *resting* dashboard. Nothing looked at what
 * happens between pressing on a handle strip and letting go, which is exactly
 * where the mode felt wrong.
 *
 * The geometry is pure arithmetic now (that was the fix), so it is testable
 * with nothing but a stub `getComputedStyle` and a map of block heights. The
 * audit's own acceptance test - "drag Session stats between two half-width
 * modules and watch the placeholder" - is `monotonic in cursor position`
 * below, expressed as a property rather than a screenshot.
 */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const APP = path.join(__dirname, "..", "spike", "web", "app.js");

const results = [];
function check(name, passed, detail = "") {
  results.push([name, !!passed, String(detail)]);
}

/* ---- the smallest DOM that lets app.js finish loading ------------------ */

const GRID = { left: 100, top: 60, width: 1000 };
const GAP = 16;

function stubEl(extra = {}) {
  return Object.assign({
    style: { setProperty() {}, removeProperty() {} },
    classList: { add() {}, remove() {}, toggle() {}, contains: () => false },
    addEventListener() {},
    removeEventListener() {},
    querySelector: () => null,
    querySelectorAll: () => [],
    appendChild() {},
    getBoundingClientRect: () => ({ left: 0, top: 0, width: 0, height: 0 }),
  }, extra);
}

const elements = {
  "dash-grid": stubEl({
    getBoundingClientRect: () => ({
      left: GRID.left, top: GRID.top, width: GRID.width, height: 800,
    }),
  }),
  "pane-dashboard": stubEl({
    getBoundingClientRect: () => ({ left: 0, top: 0, width: 1200, height: 900 }),
  }),
};

const sandbox = {
  console,
  setTimeout,
  clearTimeout,
  setInterval,
  clearInterval,
  Promise,
  Math,
  Map,
  Set,
  JSON,
  performance: { now: () => 0 },
  requestAnimationFrame() {},
  getComputedStyle: () => ({ columnGap: `${GAP}px`, rowGap: `${GAP}px` }),
  document: {
    documentElement: stubEl(),
    addEventListener() {},
    getElementById: (id) => elements[id] || null,
    querySelector: () => null,
    querySelectorAll: () => [],
    createElement: () => stubEl(),
  },
  window: { addEventListener() {}, location: { search: "" } },
};
sandbox.window.window = sandbox.window;
sandbox.globalThis = sandbox;

vm.createContext(sandbox);
// `function` declarations land on the context object, but app.js's state is
// `let` - a lexical binding the sandbox cannot see or write. Appending the
// accessors inside the same script is what puts them in scope; the alternative
// is exporting the module's internals purely so a test can reach them.
vm.runInContext(
  fs.readFileSync(APP, "utf8") + `
  globalThis.__set = (o) => {
    if ("dashMeta" in o) dashMeta = o.dashMeta;
    if ("dashLayout" in o) dashLayout = o.dashLayout;
    if ("dashDrag" in o) dashDrag = o.dashDrag;
    if ("dashEditing" in o) dashEditing = o.dashEditing;
    if ("dashKbdHeld" in o) dashKbdHeld = o.dashKbdHeld;
  };
  globalThis.__get = () => ({ dashLayout, dashDrag, dashKbdHeld });
  `,
  sandbox, { filename: APP });

const set = sandbox.__set;
const get = sandbox.__get;

/* ---- a dashboard to drag things around in ------------------------------ */
// Three modules, the middle row a pair of half-width ones - the exact shape
// the old one-dimensional hit test could not order correctly.
const HEIGHTS = { hero: 300, stats: 180, activity: 260, extra: 200 };

set({ dashMeta: {
  cols: 12,
  spans: [6, 8, 12],
  span_labels: { 6: "½", 8: "⅔", 12: "Full" },
  labels: { hero: "Live session", stats: "Session stats", activity: "Activity", extra: "Extra" },
  blocks: ["hero", "stats", "activity", "extra"],
} });

function setLayout(layout) {
  const metrics = {
    left: GRID.left,
    top: GRID.top,
    // The pane sits at the viewport origin in this stub, so client and pane
    // coordinates coincide - but the fields have to exist, because the drag
    // reads them instead of calling getBoundingClientRect() per pointermove.
    paneLeft: 0,
    paneTop: 0,
    colW: (GRID.width - GAP * 11) / 12,
    gap: GAP,
    rowGap: GAP,
    heights: new Map(Object.entries(HEIGHTS)),
  };
  set({
    dashLayout: layout.map((it) => ({ id: it.id, span: it.span })),
    dashDrag: { id: null, metrics },
  });
  return metrics;
}

const LAYOUT = [
  { id: "hero", span: 12 },
  { id: "stats", span: 6 },
  { id: "activity", span: 6 },
];
const m = setLayout(LAYOUT);

/* ---- packing ----------------------------------------------------------- */

const rows = sandbox.dashRowBoxes(LAYOUT, m);
check("hero owns a row of its own, the halves share the next",
      rows.length === 2 && rows[0].items.length === 1 && rows[1].items.length === 2,
      rows.map((r) => r.items.map((i) => i.id).join("+")).join(" / "));
check("row height is the tallest block in it",
      rows[0].height === HEIGHTS.hero && rows[1].height === HEIGHTS.activity,
      `${rows[0].height} / ${rows[1].height}`);
check("the second row starts one row-gap below the first",
      rows[1].top === GRID.top + HEIGHTS.hero + GAP, rows[1].top);

const half = rows[1].items;
check("half-width blocks are half the grid, minus half a gutter",
      Math.abs(half[0].width - (GRID.width - GAP) / 2) < 0.01, half[0].width);
check("the two halves do not overlap",
      half[0].left + half[0].width <= half[1].left + 0.01,
      `${half[0].left + half[0].width} vs ${half[1].left}`);
check("no coordinate is ever negative",
      rows.every((r) => r.items.every((i) => i.left >= 0 && i.width > 0)));

/* ---- the hit test ------------------------------------------------------ */
// The audit's acceptance gesture: pick up Session stats and sweep the cursor
// across the row it used to share. The index must never go backwards.
setLayout(LAYOUT);
get().dashDrag.id = "stats";

const band = sandbox.dashRowBoxes(
  LAYOUT.filter((it) => it.id !== "stats"), m);
const sweepY = band[1].top + band[1].height / 2;

let indices = [];
for (let x = 0; x <= 1200; x += 10) {
  indices.push(sandbox.dropIndexFor("stats", x, sweepY));
}
check("index is monotonic across a horizontal sweep",
      indices.every((v, i) => i === 0 || v >= indices[i - 1]),
      indices.join(""));
check("index never leaves the insertable range",
      indices.every((v) => v >= 0 && v <= 2),
      `${Math.min(...indices)}..${Math.max(...indices)}`);

// Vertical sweep down the whole pane, same rule.
indices = [];
for (let y = 0; y <= 1000; y += 10) {
  indices.push(sandbox.dropIndexFor("stats", GRID.left + 20, y));
}
check("index is monotonic down a vertical sweep",
      indices.every((v, i) => i === 0 || v >= indices[i - 1]),
      `${indices[0]}..${indices[indices.length - 1]}`);

check("above and left of everything drops at the front",
      sandbox.dropIndexFor("stats", GRID.left + 5, 0) === 0);
check("below everything drops at the end",
      sandbox.dropIndexFor("stats", GRID.left + 5, 5000) === 2);

/* The check with teeth.
 *
 * The audit called the old hit test non-monotonic. Brute-forced over every
 * ordering of four blocks it is not - it never goes backwards in x or in y.
 * What it does is *disagree with where the cursor is*, at 19% of the positions
 * in this layout, because `cy > that block's own midpoint` fires at a
 * different height for every block in a row and blocks in a row have
 * different heights.
 *
 * Concretely: two half-width modules share a row, the left one shorter than
 * the right. Put the cursor in the left module's left half, below its
 * midpoint but well inside the row. It is visibly over the first block, and
 * the old test answered "after it" - which is the "drop lands one slot off
 * from where the marker was" symptom, exactly. */
setLayout([
  { id: "stats", span: 6 },      // 180 tall
  { id: "activity", span: 6 },   // 260 tall - same row, taller
]);
get().dashDrag.id = "hero";
const shortRow = sandbox.dashRowBoxes(
  [{ id: "stats", span: 6 }, { id: "activity", span: 6 }], m)[0];
const leftHalf = shortRow.items[0];
check("a cursor over the first block's left half inserts before it",
      sandbox.dropIndexFor("hero",
                           leftHalf.left + leftHalf.width * 0.25,
                           GRID.top + HEIGHTS.stats - 20) === 0,
      sandbox.dropIndexFor("hero",
                           leftHalf.left + leftHalf.width * 0.25,
                           GRID.top + HEIGHTS.stats - 20));
check("row position, not each block's own midpoint, decides the band",
      sandbox.dropIndexFor("hero", leftHalf.left + 5, GRID.top + 10)
        === sandbox.dropIndexFor("hero", leftHalf.left + 5,
                                 GRID.top + shortRow.height - 10));

setLayout(LAYOUT);
get().dashDrag.id = "stats";

// Left of a block's centre means before it, right of it means after - the
// property the old `||` hit test lost the moment two blocks shared a row.
const target = band[1].items[0];
check("left of a block's centre inserts before it",
      sandbox.dropIndexFor("stats", target.left + target.width * 0.25, sweepY)
        < sandbox.dropIndexFor("stats", target.left + target.width * 0.75, sweepY));

// Hovering over the block's own resting place must be a no-op, or the
// placeholder oscillates while the cursor is still.
setLayout(LAYOUT);
get().dashDrag.id = "activity";
const rest = sandbox.dashRowBoxes(LAYOUT.filter((it) => it.id !== "activity"), m);
const own = rest[1].items[0];
check("the layout round-trips through its own drop index",
      sandbox.dropIndexFor("activity", own.left + own.width + 40,
                           rest[1].top + 10) === 2);

/* ---- what the fix deleted ---------------------------------------------- */

check("the drop marker is gone", typeof sandbox.showDropMarker === "undefined");
check("nothing measures by mutating the live layout",
      typeof sandbox.measureBlockRect === "undefined");
check("packGridRows is reachable", typeof sandbox.packGridRows === "function");
check("moveKbdHeld is reachable", typeof sandbox.moveKbdHeld === "function");
check("keyboard span stepping exists", typeof sandbox.stepKbdSpan === "function");
check("there is a live region writer", typeof sandbox.dashAnnounce === "function");

/* ---- keyboard reordering actually reorders ----------------------------- */

setLayout(LAYOUT);
set({ dashEditing: true, dashKbdHeld: "stats" });
sandbox.moveKbdHeld(1);
check("Space-then-arrow moves the held module one place along",
      get().dashLayout.map((it) => it.id).join(",") === "hero,activity,stats",
      get().dashLayout.map((it) => it.id).join(","));

sandbox.moveKbdHeld(1);
check("it stops at the end rather than falling off it",
      get().dashLayout.map((it) => it.id).join(",") === "hero,activity,stats",
      get().dashLayout.map((it) => it.id).join(","));

setLayout(LAYOUT);
set({ dashEditing: true, dashKbdHeld: "stats" });
sandbox.stepKbdSpan(1);
check("Shift-arrow steps the span through dashMeta.spans",
      get().dashLayout.find((it) => it.id === "stats").span === 8,
      get().dashLayout.find((it) => it.id === "stats").span);

set({ dashKbdHeld: "hero" });
sandbox.stepKbdSpan(-1);
check("the hero's width stays locked from the keyboard too",
      sandbox.spanOf("hero") === 12, sandbox.spanOf("hero"));

/* ---- report ------------------------------------------------------------ */

let failed = 0;
for (const [name, passed, detail] of results) {
  if (!passed) failed++;
  console.log(`${passed ? "PASS" : "FAIL"}  ${name.padEnd(52)} ${detail}`);
}
console.log(failed
  ? `\n${failed} of ${results.length} FAILED`
  : `\nALL PASS (${results.length} checks)`);
process.exit(failed ? 1 : 0);
