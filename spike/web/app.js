/* Nebula spike - front end.
 *
 * Three jobs:
 *   1. build the backdrop from the BACKGROUND spec Python hands over
 *   2. bind real data from the existing obsauto modules
 *   3. measure, because the only reason this spike exists is the numbers
 */

const $ = (id) => document.getElementById(id);

const PANE_META = {
  dashboard: { title: "Dashboard", eyebrow: "Live session",
    actions: [["btn-open-folder", "Open folder"], ["btn-rescan", "Rescan Steam"]] },
  clips:     { title: "Clips", eyebrow: "Recorded this session",
    actions: "clips" },
  games:     { title: "Games", eyebrow: "What the classifier has learned",
    actions: [["btn-rescan", "Rescan library"]] },
  macropad:  { title: "Macropad", eyebrow: "No HID layer",
    actions: [] },
  settings:  { title: "Settings", eyebrow: "Writes config.json on blur",
    actions: [] },
};

let currentPane = "dashboard";
let settingsGroup = "obs";
let bootCfg = null;
let lastSnapshot = null;
let clipState = { game: "", query: "", sort: "Newest" };
let paletteState = { open: false, query: "", index: 0, flat: [], total: 0, groups: [] };
let profileState = { basename: "", name: "", profile: null, summary: "", gb: null };
let pendingGameSelect = "";

/* --- dashboard customise (6.8) ----------------------------------------- */

const HERO_SPAN_LOCK = "Live session is always full width";
const DASH_TOAST_MS = 6000;
// Must match .dash-drag-ghost.is-compact in app.css - the drag needs the
// number before the element has been laid out at it.
const DASH_GHOST_COMPACT = [200, 44];

let dashMeta = null;
let dashLayout = [];
let dashEditing = false;
let dashLayoutBeforeEdit = null;
let dashDrag = null;
let dashKbdHeld = null;
let dashRecentlyRemoved = null;
let dashUndoLayout = null;
let dashToastTimer = null;

function dashBlockEl(id) {
  return document.querySelector(`.dash-block[data-block="${id}"]`);
}

function cloneDashLayout(src) {
  return (src || []).map((it) => ({ id: it.id, span: it.span }));
}

function spanOf(id) {
  const it = dashLayout.find((x) => x.id === id);
  if (!it) return dashMeta ? dashMeta.cols : 12;
  return id === "hero" ? dashMeta.cols : it.span;
}

function packGridRows(layout) {
  const cols = dashMeta.cols;
  const rows = [];
  let row = [];
  let used = 0;
  for (const item of layout) {
    let span = item.id === "hero" ? cols : item.span;
    if (used + span > cols) {
      rows.push(row);
      row = [];
      used = 0;
    }
    row.push({ id: item.id, span });
    used += span;
  }
  if (row.length) rows.push(row);
  return rows;
}

function flipBlocks(ids) {
  const grid = $("dash-grid");
  if (!grid) return;
  const before = new Map();
  for (const id of ids) {
    const el = dashBlockEl(id);
    if (el) before.set(id, el.getBoundingClientRect());
  }
  requestAnimationFrame(() => {
    for (const id of ids) {
      const el = dashBlockEl(id);
      const prev = before.get(id);
      if (!el || !prev) continue;
      const next = el.getBoundingClientRect();
      const dx = prev.left - next.left;
      const dy = prev.top - next.top;
      if (Math.abs(dx) < 0.5 && Math.abs(dy) < 0.5) continue;
      el.style.transform = `translate3d(${dx}px, ${dy}px, 0)`;
      el.style.transition = "none";
      requestAnimationFrame(() => {
        el.style.transition = "";
        el.style.transform = "";
      });
    }
  });
}

function updateSpanControls() {
  for (const item of dashLayout) {
    const el = dashBlockEl(item.id);
    if (!el) continue;
    const locked = item.id === "hero";
    el.style.setProperty("--block-span", String(locked ? dashMeta.cols : item.span));
    el.querySelectorAll(".dash-span").forEach((btn) => {
      const s = parseInt(btn.dataset.span, 10);
      // The hero's full width is a rule, so show it as one. Hiding the segment
      // made a deliberate constraint look like a missing control.
      btn.disabled = locked;
      btn.title = locked ? HERO_SPAN_LOCK : "";
      btn.classList.toggle("is-active", locked ? s === dashMeta.cols : item.span === s);
    });
  }
}

function reorderDashDom() {
  const grid = $("dash-grid");
  if (!grid) return;
  for (const item of dashLayout) {
    const el = dashBlockEl(item.id);
    if (el) grid.appendChild(el);
  }
  // The Add module tile is part of the grid, so it has to stay last.
  const tile = $("dash-add-tile");
  if (tile) grid.appendChild(tile);
}

function syncDashBlockVisibility() {
  if (!dashMeta) return;
  const placed = new Set(dashLayout.map((it) => it.id));
  for (const id of dashMeta.blocks || []) {
    const el = dashBlockEl(id);
    if (el) el.hidden = !placed.has(id);
  }
}

/* Add module belongs in the grid, not the titlebar row.

   It used to be a wrapping chip row inside .pane-header-tools capped at 420px:
   remove enough modules and it wrapped to a second line, grew the 62px pane
   header and shoved the title sideways. The one piece of chrome that must
   never move was the one this reflowed. As a half-width tile in the last grid
   slot it grows into the space the removed modules just freed. */
function paintAddModuleTile() {
  const tile = $("dash-add-tile");
  if (!tile) return;
  const placed = new Set(dashLayout.map((it) => it.id));
  const missing = (dashMeta.blocks || []).filter((id) => !placed.has(id));
  if (!missing.length || !dashEditing || currentPane !== "dashboard") {
    tile.hidden = true;
    tile.dataset.painted = "";
    tile.innerHTML = "";
    return;
  }
  tile.hidden = false;
  tile.style.setProperty("--block-span", String(dashMeta.spans[0] || 6));
  // applyDashLayout runs on every index change during a drag, and rebuilding
  // this markup each time threw away the chip the pointer was on. Repaint only
  // when what it lists actually changes.
  const signature = missing.join(",") + "|" + (dashRecentlyRemoved || "");
  if (tile.dataset.painted === signature) return;
  tile.dataset.painted = signature;
  tile.innerHTML = `<span class="eyebrow">Add module</span>
    <div class="dash-add-chips">` +
    missing.map((id) => {
      const recent = id === dashRecentlyRemoved;
      const label = dashMeta.labels[id] || id;
      return `<button class="dash-add-chip no-drag${recent ? " is-recent" : ""}" type="button"
        data-add="${esc(id)}" title="Drag into place, or click to add">${esc(label)}</button>`;
    }).join("") + `</div>
    <span class="dash-add-hint">Drag one into the grid to place it</span>`;
}

/* One region, one whole sentence at a time. Keyboard reordering is invisible
   without it - the strip had a focus ring and nothing to announce. */
function dashAnnounce(text) {
  const live = $("dash-live");
  if (live) live.textContent = text;
}

function dashPositionText(id) {
  const i = dashLayout.findIndex((it) => it.id === id);
  const label = (dashMeta.labels || {})[id] || id;
  const span = spanOf(id);
  const width = (dashMeta.span_labels || {})[span] || `${span} of ${dashMeta.cols}`;
  return `${label}, position ${i + 1} of ${dashLayout.length}, ${width} width`;
}

/* Where a block lands is arithmetic, not something to discover by mutating the
   live layout and reading it back. The old measureBlockRect() did the latter:
   two full DOM reorders plus two forced synchronous layouts for one marker
   position - the Tk "any change costs a composite" problem, rebuilt in a
   browser. Measure the column width and the block heights once at drag start,
   then answer every later question from packGridRows() and a few adds. */
function dashGridMetrics() {
  const grid = $("dash-grid");
  const pane = $("pane-dashboard");
  if (!grid || !pane || !dashMeta) return null;
  const cols = dashMeta.cols;
  const gr = grid.getBoundingClientRect();
  const pr = pane.getBoundingClientRect();
  const cs = getComputedStyle(grid);
  const gap = parseFloat(cs.columnGap) || 0;
  const rowGap = parseFloat(cs.rowGap) || gap;
  const heights = new Map();
  for (const it of dashLayout) {
    const el = dashBlockEl(it.id);
    if (el) heights.set(it.id, el.getBoundingClientRect().height);
  }
  return {
    left: gr.left - pr.left,
    top: gr.top - pr.top,
    // The pane's own origin, so converting a client point to pane coordinates
    // during the drag is subtraction rather than a getBoundingClientRect() -
    // which, right after a DOM reorder, is a forced synchronous layout on
    // every single pointermove.
    paneLeft: pr.left,
    paneTop: pr.top,
    colW: (gr.width - gap * (cols - 1)) / cols,
    gap,
    rowGap,
    heights,
  };
}

/* An ordered layout -> the row bands and the box of every block in it, in pane
   coordinates. Pure: it reads nothing from the DOM. */
function dashRowBoxes(layout, m) {
  const rows = [];
  let y = 0;
  for (const packed of packGridRows(layout)) {
    let col = 0;
    let rowH = 0;
    const items = [];
    for (const it of packed) {
      const h = m.heights.get(it.id) || 0;
      items.push({
        id: it.id,
        left: m.left + col * (m.colW + m.gap),
        width: it.span * m.colW + (it.span - 1) * m.gap,
        height: h,
      });
      col += it.span;
      if (h > rowH) rowH = h;
    }
    rows.push({ top: m.top + y, height: rowH, items });
    y += rowH + m.rowGap;
  }
  return rows;
}

function applyDashLayout(layout, opts) {
  opts = opts || {};
  const prevIds = dashLayout.map((it) => it.id);
  dashLayout = cloneDashLayout(layout);
  reorderDashDom();
  syncDashBlockVisibility();
  updateSpanControls();
  paintAddModuleTile();
  if (opts.animate !== false) {
    const moved = dashLayout.map((it) => it.id).filter((id) => prevIds.includes(id));
    flipBlocks(moved);
  }
}

function buildGridOverlay() {
  const host = $("dash-grid-overlay");
  if (!host || host.childElementCount) return;
  const cols = dashMeta ? dashMeta.cols : 12;
  host.innerHTML = Array.from({ length: cols }, () => "<span></span>").join("");
}

function setDashEditing(on, commit) {
  const pane = $("pane-dashboard");
  const btn = $("btn-customise");
  if (!pane) return;
  const was = dashEditing;
  dashEditing = on;
  if (on && !was) dashLayoutBeforeEdit = cloneDashLayout(dashLayout);
  pane.classList.toggle("is-editing", on);
  if (btn) {
    btn.textContent = on ? "Done" : "Customise";
    btn.classList.toggle("is-active", on);
  }
  pane.querySelectorAll(".dash-chrome").forEach((el) => {
    if (on) el.removeAttribute("hidden");
    else el.setAttribute("hidden", "");
  });
  const overlay = $("dash-grid-overlay");
  if (overlay) overlay.classList.toggle("is-visible", on);
  if (was === on) return;
  if (!on) {
    const before = cloneDashLayout(dashLayoutBeforeEdit || dashLayout);
    const layout = commit === false ? before : cloneDashLayout(dashLayout);
    dashDragCleanup();
    if (dashKbdHeld) {
      const held = dashBlockEl(dashKbdHeld);
      if (held) held.classList.remove("is-kbd-held");
      dashKbdHeld = null;
    }
    dashRecentlyRemoved = null;
    applyDashLayout(layout, { animate: true });
    if (commit !== false) {
      persistDashLayout();
      // Commit is the only visible exit, so it must be reversible. Without
      // this an accidental change was unrecoverable and nobody explored.
      if (!sameDashLayout(before, layout)) {
        dashUndoLayout = before;
        showDashToast("Layout saved", true);
      }
    } else {
      dashUndoLayout = null;
      hideDashToast();
      dashAnnounce("Customise cancelled, layout restored");
    }
  } else {
    buildGridOverlay();
    hideDashToast();
    applyDashLayout(dashLayout, { animate: false });
    dashAnnounce("Customise mode. Tab to a module, Space to pick it up, "
      + "arrows to move it, Shift and arrows to resize, Delete to remove it.");
  }
  paintAddModuleTile();
}

function sameDashLayout(a, b) {
  if (a.length !== b.length) return false;
  return a.every((it, i) => it.id === b[i].id && it.span === b[i].span);
}

/* Reset is the other half of "the mode stops being scary": a way back to the
   shipped arrangement that does not depend on remembering what you changed. */
function resetDashLayout() {
  if (!dashEditing || !dashMeta) return;
  applyDashLayout(cloneDashLayout(dashMeta.default_grid || []));
  dashRecentlyRemoved = null;
  dashAnnounce("Layout reset to the default arrangement");
}

function showDashToast(text, undo) {
  const host = $("dash-toast");
  if (!host) return;
  host.innerHTML = `<span>${esc(text)}</span>` +
    (undo ? `<button class="dash-toast-undo no-drag" type="button" id="dash-undo">Undo</button>` : "");
  host.hidden = false;
  requestAnimationFrame(() => host.classList.add("is-in"));
  dashAnnounce(undo ? `${text}. Undo is available for six seconds.` : text);
  if (dashToastTimer) clearTimeout(dashToastTimer);
  dashToastTimer = setTimeout(hideDashToast, DASH_TOAST_MS);
}

function hideDashToast() {
  const host = $("dash-toast");
  if (dashToastTimer) { clearTimeout(dashToastTimer); dashToastTimer = null; }
  if (!host || host.hidden) return;
  host.classList.remove("is-in");
  host.hidden = true;
  host.innerHTML = "";
}

function undoDashLayout() {
  if (!dashUndoLayout) return;
  applyDashLayout(cloneDashLayout(dashUndoLayout));
  dashUndoLayout = null;
  persistDashLayout();
  hideDashToast();
  dashAnnounce("Layout change undone");
}

async function persistDashLayout() {
  try {
    await window.pywebview.api.set_dashboard_layout(dashLayout);
  } catch (e) {
    fail("dashboard", e);
  }
}

function toggleCustomise() {
  if (dashEditing) setDashEditing(false, true);
  else setDashEditing(true);
}

function cancelCustomise() {
  if (!dashEditing) return;
  if (dashDrag) {
    dashDragCleanup();
    return;
  }
  setDashEditing(false, false);
}

function setBlockSpan(id, span) {
  if (!dashEditing || id === "hero" || !dashMeta.spans.includes(span)) return;
  const layout = cloneDashLayout(dashLayout);
  const it = layout.find((x) => x.id === id);
  if (!it || it.span === span) return;
  it.span = span;
  applyDashLayout(layout);
}

function removeDashBlock(id) {
  if (!dashEditing || dashLayout.length <= 1) return;
  if (dashKbdHeld === id) setKbdHeld(null);
  dashRecentlyRemoved = id;
  applyDashLayout(dashLayout.filter((it) => it.id !== id));
  dashAnnounce(`${(dashMeta.labels || {})[id] || id} removed. `
    + `Restore it from Add module.`);
}

function addDashBlock(id) {
  if (!dashEditing || dashLayout.some((it) => it.id === id)) return;
  if (dashRecentlyRemoved === id) dashRecentlyRemoved = null;
  applyDashLayout(dashLayout.concat([{ id, span: dashMeta.cols }]));
}

/* Row band first, then column within it.

   The previous test counted a block as "past" if the cursor was below its
   vertical midpoint OR right of its horizontal one, with the second clause
   guarded by `abs(cy - mid) < height / 2` - which is true for any cursor
   inside the block at all, so the guard did nothing and the two clauses ORed
   together. For two half-width modules sharing a row the resulting index was
   not monotonic in cursor position: the placeholder flipped back and forth and
   the drop landed a slot off. */
function dropIndexFor(dragId, cx, cy) {
  const m = (dashDrag && dashDrag.metrics) || dashGridMetrics();
  if (!m) return 0;
  const x = cx - m.paneLeft;
  const y = cy - m.paneTop;
  // The resting blocks are the layout without the one in hand - the index is
  // an insertion point into exactly that list.
  const rest = dashLayout.filter((it) => it.id !== dragId);
  const rows = dashRowBoxes(rest, m);
  let seen = 0;
  for (let r = 0; r < rows.length; r++) {
    const row = rows[r];
    const below = y >= row.top + row.height;
    if (below && r < rows.length - 1) {
      seen += row.items.length;
      continue;          // in the gap, or further down: try the next band
    }
    if (below) return rest.length;                       // past the last row
    let n = 0;
    for (const it of row.items) {
      if (x > it.left + it.width / 2) n += 1;
    }
    return seen + n;
  }
  return rest.length;
}

function layoutWithDraggedAt(dragId, index) {
  const layout = dashLayout.filter((it) => it.id !== dragId);
  layout.splice(index, 0, { id: dragId, span: spanOf(dragId) });
  return layout;
}

function dashDragCleanup() {
  const ghost = $("dash-drag-ghost");
  if (ghost) {
    ghost.hidden = true;
    ghost.innerHTML = "";
    ghost.style.transform = "";
  }
  setDashDragging(false);
  if (dashDrag && dashDrag.id) {
    const el = dashBlockEl(dashDrag.id);
    if (el) el.classList.remove("is-drag-src");
  }
  dashDrag = null;
}

function setDashDragging(on) {
  const pane = $("pane-dashboard");
  if (pane) pane.classList.toggle("is-dragging", on);
}

/* A stand-in, not a copy. The old ghost deep-cloned .dash-body-wrap - clip
   thumbnails, log rows and all - on every grab. What the user is aiming is a
   rectangle with a name on it, so that is what follows the cursor.
   Size goes through custom properties rather than style.width: it is one write
   at grab time either way, but it keeps the layout-property rule honest. */
function paintDragGhost(ghost, id, rect, compact) {
  ghost.innerHTML =
    `<span class="dash-ghost-label">${esc((dashMeta.labels || {})[id] || id)}</span>`;
  // A module dragged out of Add module is full width and as tall as its
  // content, and a 984px slab hanging off the cursor tells you nothing you
  // cannot already see: the dashed slot in the grid is showing you the real
  // footprint. So the thing under the finger stays the size of the chip.
  ghost.classList.toggle("is-compact", !!compact);
  ghost.style.setProperty("--ghost-w", compact ? "" : `${rect.width}px`);
  ghost.style.setProperty("--ghost-h", compact ? "" : `${rect.height}px`);
}

function startDashDrag(id, clientX, clientY, opts) {
  if (!dashEditing) return;
  const el = dashBlockEl(id);
  const ghost = $("dash-drag-ghost");
  if (!el || !ghost) return;
  opts = opts || {};
  dashDragCleanup();
  const r = el.getBoundingClientRect();
  dashDrag = {
    id,
    // A module picked up from the grid keeps the grip under the finger. One
    // dragged out of Add module was never under the finger to begin with, so
    // its compact stand-in rides centred on it instead.
    offsetX: opts.centreGhost ? DASH_GHOST_COMPACT[0] / 2 : clientX - r.left,
    offsetY: opts.centreGhost ? DASH_GHOST_COMPACT[1] / 2 : clientY - r.top,
    index: dashLayout.findIndex((it) => it.id === id),
    metrics: dashGridMetrics(),          // measured once, while nothing has moved
  };
  // The block keeps its box and stays in the grid - it is the placeholder.
  // Removing it (display:none) put the aiming picture and the resulting one in
  // two different layouts, and snapped everything below it with no animation.
  el.classList.add("is-drag-src");
  setDashDragging(true);
  paintDragGhost(ghost, id, r, opts.centreGhost);
  ghost.hidden = false;
  moveDashDrag(clientX, clientY);
}

function moveDashDrag(clientX, clientY) {
  if (!dashDrag) return;
  const ghost = $("dash-drag-ghost");
  if (ghost) {
    ghost.style.transform =
      `translate3d(${clientX - dashDrag.offsetX}px, ${clientY - dashDrag.offsetY}px, 0) rotate(var(--drag-rotate))`;
  }
  const idx = dropIndexFor(dashDrag.id, clientX, clientY);
  if (idx === dashDrag.index) return;
  dashDrag.index = idx;
  // One layout, one truth: the placeholder is the real block moving, so the
  // picture being aimed at and the one that lands are the same array.
  applyDashLayout(layoutWithDraggedAt(dashDrag.id, idx));
}

function finishDashDrag() {
  // dashLayout already holds the block at the drop index - the placeholder was
  // never a separate thing to reconcile.
  if (dashDrag) dashDragCleanup();
}

/* One gesture for both "move this module" and "place this new one".
 *
 * Nothing happens until the pointer has actually travelled, so a tap on an Add
 * module chip still just drops the module in at the end - the quick path - and
 * a drag places it where you let go. Same distinction a home screen makes
 * between tapping an app and dragging it out of the library. */
const DASH_DRAG_SLOP = 4;

function beginDashPointerDrag(e, id, opts) {
  opts = opts || {};
  const host = e.currentTarget === document ? e.target : e.currentTarget;
  const startX = e.clientX;
  const startY = e.clientY;
  let started = false;
  try { host.setPointerCapture(e.pointerId); } catch (_) { /* already gone */ }

  const begin = () => {
    if (opts.insert) {
      const layout = cloneDashLayout(dashLayout);
      layout.splice(dropIndexFor(id, startX, startY), 0,
                    { id, span: dashMeta.cols });
      if (dashRecentlyRemoved === id) dashRecentlyRemoved = null;
      applyDashLayout(layout, { animate: false });
    }
    startDashDrag(id, startX, startY, { centreGhost: !!opts.insert });
    started = !!dashDrag;
  };

  const move = (ev) => {
    if (!started) {
      if (Math.abs(ev.clientX - startX) < DASH_DRAG_SLOP &&
          Math.abs(ev.clientY - startY) < DASH_DRAG_SLOP) return;
      begin();
      if (!started) return;
    }
    moveDashDrag(ev.clientX, ev.clientY);
  };

  const up = (ev) => {
    host.removeEventListener("pointermove", move);
    host.removeEventListener("pointerup", up);
    host.removeEventListener("pointercancel", up);
    try { host.releasePointerCapture(ev.pointerId); } catch (_) { /* fine */ }
    if (started) {
      finishDashDrag();
      dashAnnounce(dashPositionText(id));
    } else if (opts.insert) {
      addDashBlock(id);
    }
  };

  host.addEventListener("pointermove", move);
  host.addEventListener("pointerup", up);
  host.addEventListener("pointercancel", up);
}

function initDashboard(cfg) {
  dashMeta = cfg.dashboard || {};
  dashLayout = cloneDashLayout(dashMeta.layout || dashMeta.default_grid || []);
  applyDashLayout(dashLayout, { animate: false });
}

function moveKbdHeld(delta) {
  if (!dashKbdHeld) return;
  const ids = dashLayout.map((it) => it.id);
  const i = ids.indexOf(dashKbdHeld);
  if (i < 0) return;
  const j = Math.max(0, Math.min(ids.length - 1, i + delta));
  if (j === i) return;
  const layout = cloneDashLayout(dashLayout);
  const [item] = layout.splice(i, 1);
  layout.splice(j, 0, item);
  applyDashLayout(layout);
  dashAnnounce(dashPositionText(dashKbdHeld));
}

/* Shift + arrow steps through dashMeta.spans rather than needing the mouse to
   reach a 30px segment. */
function stepKbdSpan(delta) {
  if (!dashKbdHeld || dashKbdHeld === "hero") {
    if (dashKbdHeld === "hero") dashAnnounce(HERO_SPAN_LOCK);
    return;
  }
  const spans = dashMeta.spans || [];
  const i = spans.indexOf(spanOf(dashKbdHeld));
  const j = Math.max(0, Math.min(spans.length - 1, (i < 0 ? 0 : i) + delta));
  if (j === i) return;
  setBlockSpan(dashKbdHeld, spans[j]);
  dashAnnounce(dashPositionText(dashKbdHeld));
}

function setKbdHeld(id) {
  const prev = dashKbdHeld;
  if (prev) {
    const el = dashBlockEl(prev);
    if (el) el.classList.remove("is-kbd-held");
  }
  dashKbdHeld = id;
  if (id) {
    const el = dashBlockEl(id);
    if (el) el.classList.add("is-kbd-held");
    dashAnnounce(`Picked up ${dashPositionText(id)}`);
  } else if (prev) {
    dashAnnounce(`Dropped ${dashPositionText(prev)}`);
  }
  setDashDragging(!!id);
}

function wireDashCustomise() {
  buildGridOverlay();

  // In customise mode the whole module is the handle, the way an icon is on a
  // home screen in jiggle mode - not a 26px strip you have to find first. The
  // strip stays as the affordance and as the keyboard target, and its grip is
  // a real <button> so it has a role and a name without inventing one. The
  // span and close controls are siblings of that button, not children: a
  // button inside a button is not a thing.
  document.addEventListener("pointerdown", (e) => {
    if (!dashEditing || e.button !== 0) return;

    const chip = e.target.closest(".dash-add-chip");
    if (chip) {
      e.preventDefault();
      beginDashPointerDrag(e, chip.dataset.add, { insert: true });
      return;
    }
    if (e.target.closest(".dash-span, .dash-strip-close")) return;
    const block = e.target.closest(".dash-block");
    if (!block || block.hidden) return;
    e.preventDefault();
    const grip = e.target.closest(".dash-strip-grip");
    if (grip) grip.focus();          // preventDefault would have skipped it
    beginDashPointerDrag(e, block.dataset.block);
  });

  document.addEventListener("click", (e) => {
    if (e.target.closest("#dash-undo")) {
      undoDashLayout();
      return;
    }
    if (!dashEditing) return;
    if (e.target.closest("#btn-reset-layout")) {
      resetDashLayout();
      return;
    }
    const spanBtn = e.target.closest(".dash-span");
    if (spanBtn) {
      if (spanBtn.disabled) return;
      const block = spanBtn.closest(".dash-block");
      if (block) setBlockSpan(block.dataset.block, parseInt(spanBtn.dataset.span, 10));
      return;
    }
    const close = e.target.closest(".dash-strip-close");
    if (close) {
      const block = close.closest(".dash-block");
      if (block) removeDashBlock(block.dataset.block);
      return;
    }
    // Keyboard activation of a chip arrives here as a click with no pointer
    // sequence behind it. The pointer path handles taps itself, and
    // addDashBlock refuses a module that is already placed, so the overlap is
    // a no-op rather than a double insert.
    const add = e.target.closest("[data-add]");
    if (add) addDashBlock(add.dataset.add);
  });
}

const PROFILE_ENCODERS = {
  "obs_x264": "x264 (CPU)",
  "nvenc_h264": "NVENC H.264",
  "nvenc_hevc": "NVENC HEVC",
  "jim_nvenc": "NVENC (new)",
  "amd_amf_h264": "AMD H.264",
  "qsv_h264": "QuickSync H.264",
};
const PROFILE_FPS = [24, 30, 48, 60, 120, 144];
const PROFILE_INHERIT = "Inherit default";

/* --- seeded RNG -------------------------------------------------------- */
function mulberry32(a) {
  return function () {
    a |= 0; a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
let rnd = mulberry32(1);
const rand = (lo, hi) => lo + rnd() * (hi - lo);

/* --- backdrop ---------------------------------------------------------- */

const HUE = { accent: "var(--accent-rgb)", deep: "99 84 214", ember: "var(--ember-rgb)" };

function cssNum(name, fallback) {
  const v = parseFloat(getComputedStyle(document.documentElement).getPropertyValue(name));
  return Number.isFinite(v) ? v : fallback;
}

function cssRgb(kind) {
  if (kind === "deep") return "99, 84, 214";
  const raw = getComputedStyle(document.documentElement)
    .getPropertyValue(`--${kind}-rgb`).trim();
  return raw.replace(/\s+/g, ", ");
}

function bakeAurora(aurora, wisps, W, H, bg) {
  /* Ten live filter:blur() layers measured ~42% integrated GPU. Bake once to a
   * bitmap and drift that single sheet instead — same per-launch seed, one
   * composited layer, transform-only motion after rasterise. */
  aurora.innerHTML = "";
  wisps.innerHTML = "";
  const canvas = document.createElement("canvas");
  canvas.width = W;
  canvas.height = H;
  const ctx = canvas.getContext("2d");
  const fade = cssNum("--blob-fade-at", 68) / 100;
  const kinds = ["accent", "deep", "ember"];

  const paintEllipse = (kind, w, h, left, top, blurPx, alphaPrefix) => {
    const a = cssNum(`--${alphaPrefix}-${kind}`, 0.2);
    const cx = left + w / 2;
    const cy = top + h / 2;
    const r = Math.max(w, h) / 2;
    ctx.save();
    ctx.filter = `blur(${blurPx}px)`;
    const g = ctx.createRadialGradient(cx, cy, 0, cx, cy, r);
    const rgb = cssRgb(kind);
    g.addColorStop(0, `rgba(${rgb}, ${a})`);
    g.addColorStop(fade, `rgba(${rgb}, 0)`);
    g.addColorStop(1, `rgba(${rgb}, 0)`);
    ctx.fillStyle = g;
    ctx.beginPath();
    ctx.ellipse(cx, cy, w / 2, h / 2, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
  };

  for (let i = 0; i < bg.blobs_per_surface; i++) {
    const kind = kinds[i % kinds.length];
    paintEllipse(
      kind,
      W * rand(bg.blob_size_w[0], bg.blob_size_w[1]),
      H * rand(bg.blob_size_h[0], bg.blob_size_h[1]),
      rand(-0.15, 0.85) * W,
      rand(-0.25, 0.6) * H,
      rand(bg.blob_blur_px[0], bg.blob_blur_px[1]),
      "blob-a",
    );
  }

  for (let i = 0; i < bg.wisp_count; i++) {
    const kind = kinds[i % kinds.length];
    const w = W * rand(bg.wisp_size_w[0], bg.wisp_size_w[1]);
    const h = H * rand(bg.wisp_size_h[0], bg.wisp_size_h[1]);
    const left = rand(-0.2, 0.9) * W;
    const top = rand(-0.1, 0.95) * H;
    const blurPx = h * bg.wisp_blur_frac;
    const angle = rand(bg.wisp_angle[0], bg.wisp_angle[1]) * Math.PI / 180;
    ctx.save();
    ctx.translate(left + w / 2, top + h / 2);
    ctx.rotate(angle);
    paintEllipse(kind, w, h, -w / 2, -h / 2, blurPx, "wisp-a");
    ctx.restore();
  }

  const sheet = document.createElement("div");
  sheet.className = "aurora-sheet";
  sheet.style.backgroundImage = `url(${canvas.toDataURL("image/png")})`;
  const travel = bg.motion.blob_travel_pct / 100;
  sheet.style.setProperty("--dx", (rand(-travel, travel) * W).toFixed(1) + "px");
  sheet.style.setProperty("--dy", (rand(-travel, travel) * H).toFixed(1) + "px");
  sheet.style.setProperty("--cycle",
    rand(bg.motion.blob_cycle_s[0], bg.motion.blob_cycle_s[1]).toFixed(0) + "s");
  sheet.style.setProperty("--delay", (-rand(0, 40)).toFixed(0) + "s");
  aurora.appendChild(sheet);
}

function buildBackdrop(bg, seed) {
  /* Measurement switches - see the note in app.css. */
  const q = new URLSearchParams(location.search);
  if (q.get("nowind") === "1") document.documentElement.classList.add("nowind");
  if (q.get("nosheet") === "1") document.documentElement.classList.add("nosheet");

  rnd = mulberry32(seed);
  const core = document.querySelector(".core");
  const W = core.clientWidth || 1268;
  const H = core.clientHeight || 796;

  bakeAurora($("aurora"), $("wisps"), W, H, bg);

  const STAR_RGB = "198 190 255";
  const mkLayer = (el, count, sizeRange, alphaRange, bright) => {
    const shadows = [];
    for (let i = 0; i < count; i++) {
      const x = rand(0, W);
      const y = rand(0, H);
      const s = rand(sizeRange[0], sizeRange[1]);
      const isBright = bright && i % bg.star_bright_every === 0;
      const a = isBright ? bg.star_bright_alpha : rand(alphaRange[0], alphaRange[1]);
      shadows.push(`${x.toFixed(0)}px ${y.toFixed(0)}px 0 ${(s / 2).toFixed(2)}px rgb(${STAR_RGB} / ${a.toFixed(2)})`);
      shadows.push(`${x.toFixed(0)}px ${(y + H).toFixed(0)}px 0 ${(s / 2).toFixed(2)}px rgb(${STAR_RGB} / ${a.toFixed(2)})`);
      if (isBright) {
        const g = bg.star_glint_px, ga = (bg.star_glint_alpha * a).toFixed(3);
        for (const [dx, dy] of [[g, 0], [-g, 0], [0, g], [0, -g]]) {
          shadows.push(`${(x + dx).toFixed(0)}px ${(y + dy).toFixed(0)}px 0 0 rgb(${STAR_RGB} / ${ga})`);
          shadows.push(`${(x + dx).toFixed(0)}px ${(y + dy + H).toFixed(0)}px 0 0 rgb(${STAR_RGB} / ${ga})`);
        }
      }
    }
    const dot = document.createElement("div");
    dot.className = "star";
    // lint-allow: one 1x1 anchor node built once per layer at boot, then never
    // touched. The whole star field is its box-shadow, so there is nothing here
    // to re-lay out - this is construction, not animation.
    dot.style.width = "1px";
    dot.style.height = "1px";
    dot.style.left = "0";
    dot.style.top = "0";
    dot.style.background = "transparent";
    dot.style.boxShadow = shadows.join(", ");
    el.innerHTML = "";
    el.appendChild(dot);
  };

  mkLayer($("stars-near"), bg.star_density,
          bg.star_size_near, bg.star_alpha_near, true);
  mkLayer($("stars-far"), Math.round(bg.star_density * 0.75),
          [0.6, bg.star_size_far_max], [0.14, bg.star_alpha_far_max], false);
}

/* --- pointer spotlight + window lean ----------------------------------- */

function ensureSpots() {
  document.querySelectorAll(".card, .tile").forEach((el) => {
    if (!el.querySelector(":scope > .spot")) {
      const s = document.createElement("div");
      s.className = "spot";
      el.prepend(s);
    }
  });
}

function wirePointer(leanPx) {
  const backdrop = document.querySelector(".backdrop");
  let raf = 0, px = 0, py = 0, lit = null;

  document.addEventListener("pointermove", (e) => {
    px = e.clientX; py = e.clientY;
    const card = e.target.closest(".card, .tile");
    if (card !== lit) {
      if (lit) lit.classList.remove("lit");
      if (card) card.classList.add("lit");
      lit = card;
    }
    if (raf) return;
    raf = requestAnimationFrame(() => {
      raf = 0;
      if (lit) {
        const spot = lit.querySelector(":scope > .spot");
        const r = lit.getBoundingClientRect();
        if (spot) {
          spot.style.transform =
            `translate3d(${(px - r.left).toFixed(1)}px, ${(py - r.top).toFixed(1)}px, 0)`;
        }
      }
      const cx = (px / window.innerWidth - 0.5) * -2;
      const cy = (py / window.innerHeight - 0.5) * -2;
      backdrop.style.transform =
        `translate3d(${(cx * leanPx).toFixed(2)}px, ${(cy * leanPx).toFixed(2)}px, 0)`;
    });
  });

  document.addEventListener("pointerleave", () => {
    if (lit) { lit.classList.remove("lit"); lit = null; }
  });
}

/* --- helpers ----------------------------------------------------------- */

const fmtHMS = (s) => {
  s = Math.max(0, Math.round(s));
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
  return h ? `${h}h ${String(m).padStart(2, "0")}m` : `${m}m ${String(s % 60).padStart(2, "0")}s`;
};

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => (
    {"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));
}

function boldLabel(label, spans) {
  if (!spans || !spans.length) return esc(label);
  const hit = new Set(spans);
  let out = "";
  for (let i = 0; i < label.length; i++) {
    const ch = label[i];
    out += hit.has(i) ? `<b>${esc(ch)}</b>` : esc(ch);
  }
  return out;
}

/* --- custom listbox (replaces native <select> popups) ------------------ */

let listboxPanel = null;
let listboxState = { host: null, index: 0, options: [], revertValue: null };

function ensureListboxPanel() {
  if (listboxPanel) return listboxPanel;
  listboxPanel = document.createElement("div");
  listboxPanel.id = "listbox-panel";
  listboxPanel.className = "listbox-panel is-hidden";
  listboxPanel.hidden = true;
  listboxPanel.setAttribute("role", "listbox");
  document.body.appendChild(listboxPanel);
  window.addEventListener("scroll", () => {
    if (listboxState.host) positionListboxPanel(listboxState.host);
  }, true);
  window.addEventListener("resize", () => {
    if (listboxState.host) positionListboxPanel(listboxState.host);
  });
  return listboxPanel;
}

function listboxOptionsData(host) {
  const raw = host.getAttribute("data-listbox-options");
  if (!raw) return [];
  try { return JSON.parse(raw); } catch (_) { return []; }
}

function listboxLabelFor(host, value) {
  const hit = listboxOptionsData(host).find((o) => o.value === value);
  return hit ? hit.label : value;
}

function listboxHtml({ id, className, ariaLabel, options, value, profile, setting }) {
  const selected = options.find((o) => o.value === value) || options[0];
  const attrs = [`data-listbox-options="${esc(JSON.stringify(options))}"`, `data-value="${esc(value)}"`];
  if (profile) attrs.push(`data-profile="${esc(profile)}"`);
  if (setting) attrs.push(`data-setting="${esc(setting)}"`);
  return `<div class="listbox ${className || ""}" ${id ? `id="${esc(id)}"` : ""}
    ${ariaLabel ? `aria-label="${esc(ariaLabel)}"` : ""} ${attrs.join(" ")}>
    <button type="button" class="listbox-trigger no-drag" aria-haspopup="listbox" aria-expanded="false">
      <span class="listbox-value">${esc(selected ? selected.label : "")}</span>
      <span class="listbox-chevron" aria-hidden="true"></span>
    </button>
  </div>`;
}

function bindListboxValue(host) {
  if (!host) return;
  const val = host.dataset.value ?? "";
  host.value = val;
  const valEl = host.querySelector(".listbox-value");
  if (valEl) valEl.textContent = listboxLabelFor(host, val);
}

function listboxSetValue(host, value, silent) {
  host.dataset.value = value;
  host.value = value;
  const valEl = host.querySelector(".listbox-value");
  if (valEl) valEl.textContent = listboxLabelFor(host, value);
  if (!silent) host.dispatchEvent(new Event("change", { bubbles: true }));
}

function positionListboxPanel(host) {
  const panel = ensureListboxPanel();
  const trigger = host.querySelector(".listbox-trigger");
  if (!trigger) return;
  const rect = trigger.getBoundingClientRect();
  // lint-allow: a fixed-position popover placed once when it opens. It is not
  // in the document flow, so this reflows nothing behind it, and there is no
  // transform spelling of "sit under that trigger".
  panel.style.top = `${rect.bottom + 4}px`;
  panel.style.left = `${rect.left}px`;
  panel.style.minWidth = `${rect.width}px`;
}

function paintListboxPanel() {
  const panel = ensureListboxPanel();
  const { host, index, options } = listboxState;
  if (!host) return;
  const cur = host.dataset.value;
  panel.innerHTML = options.map((o, i) =>
    `<div class="listbox-option palette-row ${i === index ? "is-active" : ""}"
          role="option" id="listbox-opt-${i}" data-listbox-value="${esc(o.value)}"
          aria-selected="${o.value === cur ? "true" : "false"}">${esc(o.label)}</div>`
  ).join("");
  const active = panel.querySelector(".listbox-option.is-active");
  if (active) active.scrollIntoView({ block: "nearest" });
}

function openListbox(host) {
  if (!host) return;
  if (listboxState.host === host) return;
  closeListboxPanel(false);
  const options = listboxOptionsData(host);
  if (!options.length) return;
  const cur = host.dataset.value;
  let index = options.findIndex((o) => o.value === cur);
  if (index < 0) index = 0;
  listboxState = { host, index, options, revertValue: cur };
  const trigger = host.querySelector(".listbox-trigger");
  if (trigger) trigger.setAttribute("aria-expanded", "true");
  positionListboxPanel(host);
  paintListboxPanel();
  const panel = ensureListboxPanel();
  panel.hidden = false;
  panel.classList.remove("is-hidden");
  requestAnimationFrame(() => panel.classList.add("is-open"));
}

function closeListboxPanel(revert) {
  const { host, revertValue } = listboxState;
  if (!host) {
    listboxState = { host: null, index: 0, options: [], revertValue: null };
    return;
  }
  const trigger = host.querySelector(".listbox-trigger");
  if (trigger) trigger.setAttribute("aria-expanded", "false");
  if (revert && revertValue != null) {
    host.dataset.value = revertValue;
    host.value = revertValue;
    const valEl = host.querySelector(".listbox-value");
    if (valEl) valEl.textContent = listboxLabelFor(host, revertValue);
  }
  const panel = listboxPanel;
  if (panel) {
    panel.classList.remove("is-open");
    setTimeout(() => {
      panel.classList.add("is-hidden");
      panel.hidden = true;
      panel.innerHTML = "";
    }, cssNum("--pane-change-ms", 260));
  }
  listboxState = { host: null, index: 0, options: [], revertValue: null };
}

function selectListboxOption(value) {
  const { host } = listboxState;
  if (!host) return;
  closeListboxPanel(false);
  if (host.dataset.value !== value) listboxSetValue(host, value, false);
  host.querySelector(".listbox-trigger")?.focus();
}

function paletteHotkeyLabel() {
  const fields = (lastSnapshot && lastSnapshot.settings && lastSnapshot.settings.fields) || [];
  const f = fields.find((x) => x.key === "palette_hotkey");
  const raw = (f && f.value) || "ctrl+k";
  return raw.replace(/\+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function paletteHotkeyMatch(e) {
  const fields = (lastSnapshot && lastSnapshot.settings && lastSnapshot.settings.fields) || [];
  const f = fields.find((x) => x.key === "palette_hotkey");
  const raw = ((f && f.value) || "ctrl+k").toLowerCase();
  const parts = raw.split("+").map((p) => p.trim());
  const needCtrl = parts.includes("ctrl") || parts.includes("control");
  const needAlt = parts.includes("alt");
  const needShift = parts.includes("shift");
  const keyPart = parts.filter((p) => !["ctrl", "control", "alt", "shift"].includes(p))[0] || "k";
  if (needCtrl !== (e.ctrlKey || e.metaKey)) return false;
  if (needAlt !== e.altKey) return false;
  if (needShift !== e.shiftKey) return false;
  return e.key.toLowerCase() === keyPart;
}

/* --- pane switching ---------------------------------------------------- */

function showPane(name) {
  if (!PANE_META[name]) return;
  closeListboxPanel(false);
  // Leaving the dashboard leaves customise mode. Rebuilding #pane-actions was
  // not enough on its own: .is-editing stayed on the dashboard, the handle
  // strips stayed up and the draft stayed uncommitted while the user was three
  // panes away.
  if (dashEditing && name !== "dashboard") setDashEditing(false, true);
  currentPane = name;
  document.querySelectorAll(".rail-item").forEach((b) => {
    b.classList.toggle("is-active", b.dataset.pane === name);
  });
  document.querySelectorAll(".pane-body").forEach((el) => {
    const on = el.dataset.pane === name;
    el.classList.toggle("is-active", on);
    el.hidden = !on;
  });
  const meta = PANE_META[name];
  $("pane-title").textContent = meta.title;
  let eyebrow = meta.eyebrow;
  if (name === "games" && lastSnapshot && lastSnapshot.games) {
    const n = lastSnapshot.games.pending.length;
    eyebrow = n ? `${n} awaiting your call` : meta.eyebrow;
    if (profileState.name) {
      eyebrow = `${profileState.name} · encoder profile`;
    }
  }
  if (name === "settings" && lastSnapshot && lastSnapshot.settings.saved_at) {
    // Saved stamp lives in the actions strip for settings.
  }
  $("pane-eyebrow").textContent = eyebrow;

  const actions = $("pane-actions");
  actions.innerHTML = "";
  if (name === "dashboard") {
    actions.innerHTML =
      (dashEditing
        ? `<button class="pill ghost no-drag" id="btn-reset-layout" type="button">Reset layout</button>`
        : "") +
      `<button class="pill ghost no-drag" id="btn-customise" type="button">${dashEditing ? "Done" : "Customise"}</button>`;
    const cbtn = $("btn-customise");
    if (cbtn) cbtn.classList.toggle("is-active", dashEditing);
  } else if (name === "clips") {
    const cp = (lastSnapshot && lastSnapshot.clips_panel) || {};
    const sum = cp.summary || {};
    if (sum.count) {
      $("pane-eyebrow").textContent =
        `${sum.count} clip${sum.count === 1 ? "" : "s"} · ${sum.total_label}`;
    }
    actions.innerHTML = `
      <input class="clip-search no-drag" id="clip-search" type="search"
             placeholder="Search clips" value="${esc(clipState.query)}" autocomplete="off">
      ${listboxHtml({
        id: "clip-sort",
        className: "clip-sort",
        ariaLabel: "Sort clips",
        options: [
          { value: "Newest", label: "Newest" },
          { value: "Oldest", label: "Oldest" },
          { value: "Largest", label: "Largest" },
        ],
        value: clipState.sort,
      })}
      <button class="pill ghost no-drag" id="btn-refresh-clips" type="button">Refresh</button>`;
    bindListboxValue($("clip-sort"));
  } else if (name === "settings") {
    const saved = (lastSnapshot && lastSnapshot.settings.saved_at) || "";
    if (saved) {
      const stamp = document.createElement("span");
      stamp.className = "settings-saved";
      stamp.innerHTML = `<i></i>Saved ${esc(saved)}`;
      actions.appendChild(stamp);
    }
  }
  for (const [id, label] of meta.actions === "clips" ? [] : (meta.actions || [])) {
    const b = document.createElement("button");
    b.className = "pill ghost no-drag";
    b.id = id;
    if (id === "btn-refresh") {
      b.innerHTML = `${esc(label)}<i class="trail">&#8635;</i>`;
      b.className = "pill no-drag";
    } else {
      b.textContent = label;
    }
    actions.appendChild(b);
  }

  const body = document.querySelector(`.pane-body[data-pane="${name}"]`);
  if (body) {
    body.classList.remove("switching");
    void body.offsetWidth;
    body.classList.add("switching");
    // Take the entrance animation off again once it has played.
    //
    // `pane-in` animates transform, and an element with an animation that
    // *can* apply a transform is a containing block for position:fixed
    // descendants - for as long as the animation is attached, not just while
    // it runs. Leaving .switching on the active pane forever therefore turned
    // every fixed child of a pane into an absolute one: the customise-mode
    // drag ghost resolved against the pane's padding box and sat a pane
    // origin away from the cursor, which is most of why dragging a module
    // felt wrong. Nothing in a screenshot of a resting pane can show this.
    const done = () => body.classList.remove("switching");
    body.addEventListener("animationend", done, { once: true });
    // prefers-reduced-motion cancels the animation, so animationend never
    // fires and the class would stick.
    setTimeout(done, cssNum("--pane-change-ms", 260) + 60);
  }
  ensureSpots();
  paintAddModuleTile();
}

/* --- renderers --------------------------------------------------------- */

function renderHero(d) {
  const h = d.hero;
  const card = $("hero");
  card.classList.remove("is-ember", "is-accent", "is-recording", "is-paused");
  if (h.state === "disconnected") card.classList.add("is-ember");
  else if (h.state === "recording" || h.state === "paused") card.classList.add("is-accent");
  if (h.state === "recording") card.classList.add("is-recording");
  if (h.state === "paused") card.classList.add("is-paused");

  $("hero-eyebrow").textContent = h.eyebrow;
  $("hero-sub").textContent = h.state === "disconnected" ? "Can't reach OBS" : "";
  $("hero-title").textContent = h.title;
  $("hero-source").textContent = h.source || "";
  $("hero-hint").textContent = h.hint || "";
  $("hero-hint").classList.toggle("is-hidden", !h.hint);

  const ro = $("hero-readouts");
  ro.classList.toggle("is-hidden", !h.show_readouts);
  if (h.show_readouts) {
    $("hero-elapsed").textContent = h.elapsed || "";
    $("hero-size").textContent = h.size || "";
    $("hero-bitrate").textContent = h.bitrate || "";
  }

  $("preview-info").textContent =
    h.scene || (h.state === "disconnected" ? "No scene — OBS offline" : "Scene capture idle");
  $("preview-video").textContent = h.video || "";
  $("preview-chip").textContent = h.scene ? h.scene : "OBS scene";

  const actions = $("hero-actions");
  const labels = h.actions_enabled || [];
  actions.innerHTML = labels.map((label, i) => {
    const primary = i === 0;
    const cls = primary ? "pill no-drag" : "pill ghost no-drag";
    return `<button class="${cls}" data-hero-action="${esc(label)}">${esc(label)}</button>`;
  }).join("");
}

/* Customise mode is a modal editing state, and the 5s poll was rewriting the
   innerHTML of #tiles and #activity underneath it. Two consequences, both of
   which read as "it randomly updates": the Activity block changes height when
   a log line arrives, so the whole grid re-packs while you are aiming at it;
   and the block heights cached at grab time stop being true, so the
   placeholder lands somewhere the drag maths no longer agrees with.
   The dashboard freezes while you are arranging it and catches up on exit. */
function dashContentFrozen() {
  return dashEditing && currentPane === "dashboard";
}

function renderTiles(d) {
  if (dashContentFrozen()) return;
  $("tiles").innerHTML = d.tiles.map((t) => `
    <div class="tile"><div class="tile-core">
      <span class="k">${esc(t.k)}</span>
      <span class="v">${esc(t.v)}</span><span class="u">${esc(t.u || "")}</span>
      ${t.sub ? `<span class="sub">${esc(t.sub)}</span>` : ""}
    </div></div>`).join("");
}

function renderActivity(d) {
  if (dashContentFrozen()) return;
  const a = d.activity;
  const filt = a.filter || "All";
  $("btn-log-filter").textContent = filt === "All" ? "All tags" : filt;
  const rows = a.rows.filter((r) => filt === "All" || r.tag === filt);
  if (!rows.length) {
    $("activity").innerHTML = `<div class="empty" style="min-height:80px">No activity yet</div>`;
    return;
  }
  $("activity").innerHTML = rows.map((r) => `
    <div class="log-row">
      <span class="ts">${esc(r.ts)}</span>
      <span class="tag" style="${r.color ? `color:${r.color}` : ""}">[${esc(r.tag || "—")}]</span>
      <span class="msg">${esc(r.text)}</span>
    </div>`).join("");
}

/* The ribbon used to be one flat bar with everything - which game, how long,
   when - hidden inside a native `title`. Three things make it readable without
   inventing a second hue: gridlines so a position is a time, a "now" marker so
   the empty stretch reads as "not yet" rather than "nothing", and a legend
   that says what was recorded and for how long. Hovering a span writes its
   detail into the header, in one fixed place. */
function ribbonSummary(r) {
  const n = r.spans.length;
  if (!n) return "no spans today";
  return `${n} span${n > 1 ? "s" : ""} · ${fmtHMS(r.total_s)} recorded`;
}

function renderRibbon(d) {
  const track = $("ribbon");
  if (!track) return;
  const r = d.ribbon;
  const spans = r.spans;
  $("ribbon-meta").textContent = ribbonSummary(r);

  const marks = (r.hour_marks || [])
    .map((p) => `<span class="ribbon-mark" style="left:${(p * 100).toFixed(4)}%"></span>`)
    .join("");
  const now = r.now_pct === undefined ? ""
    : `<span class="ribbon-now" style="left:${(r.now_pct * 100).toFixed(4)}%"></span>`;

  if (!spans.length) {
    track.innerHTML = marks + now +
      `<span class="ribbon-empty">nothing recorded today</span>`;
  } else {
    track.innerHTML = marks + spans.map((s, i) => {
      const w = Math.max(0.4, s.width_pct * 100);
      const game = s.game || "unknown";
      // Only label a span with room for it; anything narrower would clip to
      // an ellipsis and say less than the legend already does.
      const label = w > 12 ? `<span class="blk-label">${esc(game)}</span>` : "";
      return `<div class="blk ${s.live ? "live" : ""}" data-span="${i}"
           style="left:${(s.start_pct * 100).toFixed(2)}%;width:${w.toFixed(2)}%"
           >${label}</div>`;
    }).join("") + now;
  }
  $("ribbon-axis").innerHTML = r.axis.map((a) => `<span>${esc(a)}</span>`).join("");

  const legend = $("ribbon-legend");
  if (legend) {
    legend.innerHTML = (r.by_game || []).map((g) => `
      <span class="ribbon-legend-row">
        <i></i>${esc(g.game)}
        <b>${esc(fmtHMS(g.seconds))}</b>
        ${g.count > 1 ? `<em>${g.count} spans</em>` : ""}
      </span>`).join("");
    legend.hidden = !(r.by_game || []).length;
  }

  track.onpointerleave = () => { $("ribbon-meta").textContent = ribbonSummary(r); };
  track.onpointerover = (e) => {
    const blk = e.target.closest(".blk");
    if (!blk) return;
    const s = spans[parseInt(blk.dataset.span, 10)];
    if (!s) return;
    $("ribbon-meta").textContent =
      `${s.game || "unknown"} · ${s.start_label}–${s.end_label} · ${fmtHMS(s.duration_s)}`;
  };
}

function filterClips(clips) {
  let rows = clips || [];
  const q = clipState.query.trim().toLowerCase();
  if (clipState.game) {
    rows = rows.filter((c) => c.game === clipState.game);
  }
  if (q) {
    rows = rows.filter((c) =>
      (c.rel || "").toLowerCase().includes(q) ||
      (c.game || "").toLowerCase().includes(q) ||
      (c.name || "").toLowerCase().includes(q) ||
      (c.title || "").toLowerCase().includes(q));
  }
  rows = [...rows];
  if (clipState.sort === "Oldest") {
    rows.sort((a, b) => a.mtime - b.mtime);
  } else if (clipState.sort === "Largest") {
    rows.sort((a, b) => b.size_bytes - a.size_bytes);
  } else {
    rows.sort((a, b) => b.mtime - a.mtime);
  }
  return rows;
}

function renderClipGames(cp) {
  const host = $("clip-games");
  if (!host) return;
  const games = cp.games || [];
  host.innerHTML = games.map((g) => {
    const key = g.key || "";
    const active = clipState.game === key;
    return `<button class="clip-game no-drag ${active ? "is-active" : ""}" type="button"
                    data-game="${esc(key)}">
      <span class="nm">${esc(g.name)}</span>
      <span class="ct">${g.count}</span>
    </button>`;
  }).join("");
}

function renderClips(d) {
  const cp = d.clips_panel || {};
  const rows = $("rows");
  const foot = $("clips-foot");
  if (!rows) return;

  renderClipGames(cp);
  if (foot) foot.textContent = cp.min_clip_note || "";

  if (currentPane === "clips") {
    const sum = cp.summary || {};
    if (sum.count) {
      $("pane-eyebrow").textContent =
        `${sum.count} clip${sum.count === 1 ? "" : "s"} · ${sum.total_label}`;
    }
  }

  if (cp.scanning) {
    rows.innerHTML = `<div class="empty clips-empty">Scanning…</div>`;
    return;
  }
  if (cp.error) {
    rows.innerHTML = `<div class="empty clips-empty">Couldn't read ${esc(cp.root)}<br>${esc(cp.error)}</div>`;
    return;
  }

  const filtered = filterClips(cp.clips || []);
  if (!filtered.length) {
    rows.innerHTML = `<div class="empty clips-empty">${esc(cp.min_clip_note || "No clips found")}</div>`;
    return;
  }

  rows.innerHTML = filtered.map((c) => `
    <div class="clip-row" data-path="${esc(c.path)}">
      <div class="clip-main">
        <div class="thumb">${c.thumb
          ? `<img src="${c.thumb}" alt="">`
          : `<span class="init">${esc(c.initials)}</span>`}</div>
        <div class="clip-text">
          <div class="name">${esc(c.title)}</div>
          <div class="sub">${esc(c.rel)}</div>
        </div>
      </div>
      <div class="len">${esc(c.length || "")}</div>
      <div class="size">${esc(c.size_label)}</div>
      <div class="rec">${esc(c.recorded)}</div>
      <div class="acts">
        <button class="row-act no-drag" type="button" data-reveal="${esc(c.path)}" title="Reveal in folder">&#xE838;</button>
        <button class="row-act no-drag" type="button" data-delete="${esc(c.path)}" title="Delete">&#xE74D;</button>
      </div>
    </div>`).join("");

  if (cp.capped && filtered.length >= (cp.cap || 400)) {
    rows.insertAdjacentHTML("beforeend",
      `<div class="clips-cap">Showing the newest ${cp.cap} clips. Narrow with search.</div>`);
  }
}

function renderForecast(d) {
  const f = d.forecast;
  $("fc-days").textContent = f.label;
  $("fc-rate").textContent = f.rate;
  // scaleX, NOT width. The bar is laid out at width:100% and scaled down -
  // animating width relayouts every frame, which the token lint rejects.
  // Setting width here did nothing except leave the initial scaleX(0) in
  // place, so the meter has been rendering as an empty track the whole time.
  const used = Math.max(0, Math.min(1, f.used_pct || 0));
  $("fc-meter").style.transform = "scaleX(" + used.toFixed(4) + ")";
}

function renderConn(d) {
  const el = $("conn");
  el.className = "conn " + (d.obs.live ? "live" : d.obs.connected ? "ok" : "");
  $("conn-label").textContent = d.obs.label;
}

/* The row's icon: the executable's own where Nebula has seen it run, and a
   monogram tile from the name otherwise. Both arrive as a data URL from
   app_icons.py, so this does not have to know which it got - and the empty
   .ico square stays as the fallback if a row somehow has neither. */
function appIconImg(row) {
  if (!row.icon) return "";
  return `<img src="${esc(row.icon)}" alt="" width="22" height="22">`;
}

function renderGames(d) {
  const g = d.games;
  const pending = g.pending || [];
  const card = $("pending-card");
  const core = $("pending-core");
  if (!pending.length) {
    core.innerHTML = `<div class="empty" style="min-height:64px;width:100%">Nothing awaiting a decision.</div>`;
  } else {
    const p = pending[0];
    core.innerHTML = `
      <div class="pending-icon">?</div>
      <div class="pending-body">
        <span class="pending-badge">Unclassified</span>
        <div class="pending-name">${esc(p.name)}</div>
        <div class="pending-sub">${esc(p.sub)}</div>
      </div>
      <div class="pending-actions">
        <button class="pill no-drag" data-classify="1" data-key="${esc(p.key)}">It's a game</button>
        <button class="pill ghost no-drag" data-classify="0" data-key="${esc(p.key)}">Not a game</button>
      </div>`;
  }

  $("games-head").textContent = `Games ${g.games.length}`;
  $("nongames-head").textContent = `Not games ${g.non_games.length}`;
  $("games-foot").textContent = g.foot_games || "";
  $("nongames-foot").textContent = g.foot_non || "";

  const glist = $("games-list");
  if (!g.games.length) {
    glist.innerHTML = `<div class="empty">Nothing classified yet.<br>Launch a game — Nebula asks once and remembers.</div>`;
  } else {
    glist.innerHTML = g.games.map((row) => {
      const basename = (row.exes && row.exes[0]) || "";
      const active = profileState.basename === basename;
      return `
      <div class="grow-row ${active ? "is-selected" : ""}" data-game="${esc(row.name)}"
           data-basename="${esc(basename)}">
        <span class="ico">${appIconImg(row)}</span>
        <span class="nm">${esc(row.name)}</span>
        <span class="meta">${esc(row.meta)}</span>
      </div>`;
    }).join("");
  }

  const nlist = $("nongames-list");
  if (!g.non_games.length) {
    nlist.innerHTML = `<div class="empty">Nothing ignored yet.</div>`;
  } else {
    nlist.innerHTML = g.non_games.map((row) => `
      <div class="grow-row is-app" data-promote="${esc(row.name)}" title="Right-click to move back to Games">
        <span class="ico">${appIconImg(row)}</span>
        <span class="nm">${esc(row.name)}</span>
        <span class="meta">${esc(row.meta)}</span>
      </div>`).join("");
  }

  if (currentPane === "games") {
    const n = pending.length;
    $("pane-eyebrow").textContent =
      profileState.name ? `${profileState.name} · encoder profile`
        : (n ? `${n} awaiting your call` : PANE_META.games.eyebrow);
  }

  if (pendingGameSelect) {
    const want = pendingGameSelect;
    pendingGameSelect = "";
    const row = glist.querySelector(`[data-game="${CSS.escape(want)}"]`);
    if (row) selectGame(row.dataset.basename, row.dataset.game);
  }
}

function profileFieldHtml(key, label, value, kind, err) {
  const errHtml = err ? `<div class="field-error">${esc(err)}</div>` : "";
  if (kind === "bool") {
    const on = value === true || value === "true" || value === "on";
    return `<div class="field toggle ${err ? "is-error" : ""}" data-profile-key="${esc(key)}">
      <div class="toggle-copy">
        <div class="field-head">
          <span class="field-label">${esc(label)}</span>
          <span class="field-key">${esc(key)}</span>
        </div>
      </div>
      <button type="button" class="switch no-drag ${on ? "is-on" : ""}" data-profile-toggle="${esc(key)}"
              aria-pressed="${on}"></button>
      ${errHtml}
    </div>`;
  }
  if (kind === "encoder") {
    const options = [{ value: "", label: PROFILE_INHERIT }]
      .concat(Object.entries(PROFILE_ENCODERS).map(([id, nm]) => ({ value: id, label: nm })));
    return `<div class="field ${err ? "is-error" : ""}" data-profile-key="${esc(key)}">
      <div class="field-head">
        <span class="field-label">${esc(label)}</span>
        <span class="field-key">${esc(key)}</span>
      </div>
      ${listboxHtml({
        className: "field-select",
        options,
        value: value || "",
        profile: key,
      })}
      ${errHtml}
    </div>`;
  }
  if (kind === "fps") {
    const options = [{ value: "", label: PROFILE_INHERIT }]
      .concat(PROFILE_FPS.map((n) => ({ value: String(n), label: String(n) })));
    return `<div class="field ${err ? "is-error" : ""}" data-profile-key="${esc(key)}">
      <div class="field-head">
        <span class="field-label">${esc(label)}</span>
        <span class="field-key">${esc(key)}</span>
      </div>
      ${listboxHtml({
        className: "field-select",
        options,
        value: value != null && value !== "" ? String(value) : "",
        profile: key,
      })}
      ${errHtml}
    </div>`;
  }
  const unit = key === "bitrate_kbps" ? `<span class="field-unit">kb/s</span>` : "";
  const ph = key === "res" ? "2560x1440"
    : key === "bitrate_kbps" ? "18000"
    : key === "scene" ? "leave blank to keep the current scene" : "";
  return `<div class="field ${err ? "is-error" : ""}" data-profile-key="${esc(key)}">
    <div class="field-head">
      <span class="field-label">${esc(label)}</span>
      <span class="field-key">${esc(key)}</span>
      ${unit}
    </div>
    <input class="field-input no-drag" data-profile="${esc(key)}"
           value="${esc(value ?? "")}" placeholder="${esc(ph)}" autocomplete="off">
    ${errHtml}
  </div>`;
}

function renderProfilePanel(errs) {
  const host = $("profile-body");
  const meta = $("profile-meta");
  if (!host) return;
  errs = errs || {};
  if (!profileState.basename) {
    if (meta) meta.textContent = "";
    host.innerHTML = `<div class="empty profile-empty">Select a game to edit its encoder profile.</div>`;
    return;
  }
  const p = profileState.profile || {};
  const hasProfile = p && Object.keys(p).length > 0;
  if (meta) meta.textContent = profileState.summary || (hasProfile ? "" : "inherits default");
  const inheritNote = (!hasProfile && !profileState.summary)
    ? `<div class="profile-inherit">inherits default profile</div>` : "";
  const gbLine = profileState.gb
    ? `<div class="profile-estimate">Estimated <b>${profileState.gb.toFixed(1)} GB/h</b> at this bitrate</div>`
    : `<div class="profile-estimate is-hidden" id="profile-estimate"></div>`;
  host.innerHTML = `
    <div class="profile-title">${esc(profileState.name)}</div>
    ${profileState.summary
      ? `<div class="profile-summary">${esc(profileState.summary)}</div>` : ""}
    ${inheritNote}
    <div class="profile-fields">
      ${profileFieldHtml("enabled", "Profile enabled", p.enabled !== false, "bool", errs.enabled)}
      <div class="profile-grid">
        ${profileFieldHtml("res", "Resolution", p.res || "", "text", errs.res)}
        ${profileFieldHtml("fps", "Frame rate", p.fps || "", "fps", errs.fps)}
        ${profileFieldHtml("encoder", "Encoder", p.encoder || "", "encoder", errs.encoder)}
        ${profileFieldHtml("bitrate_kbps", "Bitrate", p.bitrate_kbps || "", "text", errs.bitrate_kbps)}
      </div>
      ${profileFieldHtml("scene", "OBS scene", p.scene || "", "text", errs.scene)}
    </div>
    ${gbLine}`;
  host.querySelectorAll(".listbox").forEach(bindListboxValue);
  ensureSpots();
}

async function selectGame(basename, name) {
  basename = (basename || "").trim();
  name = (name || "").trim();
  if (!basename) return;
  profileState = { basename, name, profile: null, summary: "", gb: null };
  const r = await window.pywebview.api.profile_get(basename);
  if (!r.ok) {
    fail("profile", r.error || "load failed");
    renderProfilePanel();
    if (lastSnapshot) renderGames(lastSnapshot);
    return;
  }
  profileState.profile = r.profile || {};
  profileState.summary = r.summary || "";
  profileState.gb = r.gb_per_hour != null ? r.gb_per_hour : null;
  renderProfilePanel();
  if (lastSnapshot) renderGames(lastSnapshot);
  if (currentPane === "games") showPane("games");
}

function collectProfileRaw() {
  const host = $("profile-body");
  if (!host || !profileState.basename) return { enabled: true };
  const raw = { enabled: true };
  const toggle = host.querySelector("[data-profile-toggle='enabled']");
  if (toggle) raw.enabled = toggle.classList.contains("is-on");
  host.querySelectorAll("[data-profile]").forEach((el) => {
    const key = el.dataset.profile;
    let val = el.value;
    if (key === "fps" || key === "bitrate_kbps") {
      val = val.trim();
      if (val === "") raw[key] = null;
      else raw[key] = key === "fps" ? parseInt(val, 10) : parseInt(val, 10);
    } else {
      raw[key] = val.trim();
    }
  });
  return raw;
}

async function commitProfile(key) {
  if (!profileState.basename) return;
  const raw = collectProfileRaw();
  const r = await window.pywebview.api.profile_save(profileState.basename, raw);
  if (!r.ok) {
    const errs = {};
    errs[key || "scene"] = r.error || "Save rejected";
    renderProfilePanel(errs);
    return;
  }
  profileState.profile = r.profile || {};
  profileState.summary = r.summary || "";
  const kbps = profileState.profile && profileState.profile.bitrate_kbps;
  profileState.gb = kbps ? (kbps * 1000 * 3600 / 8 / (1024 ** 3)) : null;
  renderProfilePanel();
}

/* Segoe Fluent Icons — verified codepoints from gui.py._ICON_CODEPOINTS.
   Pick from row.action only; never sniff row.label. */
const PALETTE_GLYPHS = {
  goto: {
    dashboard: "\uE704",
    clips: "\uE714",
    games: "\uE7FC",
    macropad: "\uE765",
    settings: "\uE9E9",
  },
  transport: {
    record: "\uE7C8",
    pause: "\uE769",
  },
  replay: "\uE892",       /* Previous — Fluent has no ph-rewind twin */
  open: "\uE8DA",
  game: "\uE7FC",
};

function paletteRowGlyph(row) {
  const action = row && row.action;
  if (!action || !action.length) return "";
  const kind = action[0];
  const arg = action[1];
  switch (kind) {
    case "goto":
      return PALETTE_GLYPHS.goto[arg] || "";
    case "transport":
      return (PALETTE_GLYPHS.transport[arg] || "");
    case "replay":
      return PALETTE_GLYPHS.replay;
    case "open":
      return PALETTE_GLYPHS.open;
    case "game":
      return PALETTE_GLYPHS.game;
    default:
      return "";
  }
}

function paletteRowIconHtml(row) {
  const glyph = paletteRowGlyph(row);
  if (!glyph) {
    return `<span class="palette-row-icon palette-row-icon--empty" aria-hidden="true"></span>`;
  }
  return `<span class="palette-row-icon palette-glyph" aria-hidden="true">${glyph}</span>`;
}

function flattenPaletteGroups(groups) {
  const flat = [];
  for (const g of groups || []) {
    for (const row of g.rows || []) flat.push(row);
  }
  return flat;
}

async function paintPalette() {
  const list = $("palette-list");
  const foot = $("palette-foot");
  if (!list || !foot) return;
  const q = paletteState.query;
  let data = null;
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      if (!window.pywebview || !window.pywebview.api) throw new Error("bridge");
      data = await window.pywebview.api.palette_search(q);
      break;
    } catch (e) {
      if (attempt === 2) {
        /* Say WHAT failed. Swallowing the exception left a palette that opened,
           returned nothing, and passed every gate check - with no way to tell a
           missing bridge from a raising Api method. */
        const why = String((e && (e.message || e.name)) || e).slice(0, 140);
        list.innerHTML =
          `<div class="palette-empty">Couldn't reach the palette.<br>` +
          `<span class="palette-why">${why}</span></div>`;
        foot.innerHTML = `<span class="kbd">Esc</span> close`;
        console.error("palette_search failed", e);
        return;
      }
      await new Promise((r) => setTimeout(r, 120));
    }
  }
  paletteState.groups = data.groups || [];
  paletteState.flat = flattenPaletteGroups(paletteState.groups);
  paletteState.total = data.total || paletteState.flat.length;
  paletteState.index = Math.min(paletteState.index,
    Math.max(0, paletteState.flat.length - 1));

  if (!paletteState.flat.length) {
    const msg = q.trim()
      ? `Nothing matches "${esc(q.trim())}"<br><span style="color:var(--text-tertiary);font-size:var(--t-meta-size)">Try a game name, a clip date, or an action</span>`
      : "Nothing to suggest right now.";
    list.innerHTML = `<div class="palette-empty">${msg}</div>`;
    foot.innerHTML = `<span class="kbd">Esc</span> close`;
    return;
  }

  let html = "";
  let pos = 0;
  for (const g of paletteState.groups) {
    html += `<div class="palette-group">${esc(g.group)}</div>`;
    for (const row of g.rows || []) {
      const active = pos === paletteState.index;
      html += `<div class="palette-row ${active ? "is-active" : ""}" data-palette-idx="${pos}">
        ${paletteRowIconHtml(row)}
        <span class="palette-label">${boldLabel(row.label, row.spans)}</span>
        ${row.hint ? `<span class="palette-hint">${esc(row.hint)}</span>` : ""}
      </div>`;
      pos++;
    }
  }
  list.innerHTML = html;
  const shown = paletteState.flat.length;
  foot.innerHTML = `
    <span><span class="kbd">↑↓</span> navigate</span>
    <span><span class="kbd">↵</span> run</span>
    <span><span class="kbd">Esc</span> close</span>
    <span class="spacer"></span>
    <span>${shown} of ${paletteState.total} results</span>`;

  const activeRow = list.querySelector(".palette-row.is-active");
  if (activeRow) activeRow.scrollIntoView({ block: "nearest" });
}

function openPalette() {
  const backdrop = $("palette-backdrop");
  const input = $("palette-input");
  const kbd = $("palette-kbd");
  if (!backdrop || !input) return;
  paletteState = { open: true, query: "", index: 0, flat: [], total: 0, groups: [] };
  backdrop.hidden = false;
  backdrop.classList.remove("is-hidden");
  requestAnimationFrame(() => backdrop.classList.add("is-open"));
  if (kbd) kbd.textContent = paletteHotkeyLabel();
  input.value = "";
  paintPalette();
  setTimeout(() => input.focus(), 0);
}

function closePalette() {
  const backdrop = $("palette-backdrop");
  if (!backdrop || !paletteState.open) return;
  paletteState.open = false;
  backdrop.classList.remove("is-open");
  setTimeout(() => {
    backdrop.classList.add("is-hidden");
    backdrop.hidden = true;
  }, cssNum("--pane-change-ms", 260));
}

async function runPaletteRow(idx) {
  const row = paletteState.flat[idx];
  if (!row) return;
  closePalette();
  let r;
  try {
    r = await window.pywebview.api.palette_run(row.action);
  } catch (e) {
    fail("palette", e);
    return;
  }
  if (!r.ok) {
    fail("palette", r.error || "action failed");
    return;
  }
  if (r.goto) showPane(r.goto);
  if (r.select) pendingGameSelect = r.select;
  await load();
}

window.openPalette = openPalette;

function renderMacropad(d) {
  const m = d.macropad;
  $("macropad-title").textContent = m.title;
  $("macropad-body").textContent = m.body;
  $("macropad-foot").textContent = m.foot;
}

/* The appearance layer: four keys, and each one is an override of tokens that
   tokens.css already generates. No second stylesheet, no per-theme rules - the
   preference lands as a handful of variables on :root and everything that
   reads them follows. The ground colours are not among them on purpose. */
function applyAppearance(a) {
  if (!a) return;
  const root = document.documentElement;
  const hue = a.accent || "violet";
  for (const [to, from] of [
    ["--accent", `--accent-${hue}`],
    ["--accent-text", `--accent-${hue}-text`],
    ["--accent-rgb", `--accent-${hue}-rgb`],
  ]) {
    root.style.setProperty(to, `var(${from})`);
  }
  root.style.setProperty("--density", String((a.densities || {})[a.density] ?? 1));
  root.style.setProperty("--radius-scale", String((a.radii || {})[a.radius] ?? 1));
  for (const mode of ["aurora", "subtle", "off"]) {
    root.classList.toggle(`motion-${mode}`, a.motion === mode);
  }
}

function renderSettings(d) {
  const s = d.settings;
  applyAppearance(s.appearance);
  const nav = $("settings-nav");
  nav.innerHTML = s.groups.map((g) => `
    <button class="settings-nav-item no-drag ${g.key === settingsGroup ? "is-active" : ""}"
            data-group="${esc(g.key)}">${esc(g.title)}</button>`).join("");

  $("cfg-path").textContent = s.config_path || "";

  const group = s.groups.find((g) => g.key === settingsGroup) || s.groups[0];
  if (group) settingsGroup = group.key;
  $("settings-blurb").textContent = (group && group.blurb) || "";

  const fields = s.fields.filter((f) => f.group === settingsGroup);
  const host = $("settings-fields");

  // Pair host/port and password/reconnect when both present (frame 2c grid).
  const used = new Set();
  const chunks = [];
  const pairWith = {
    obs_host: "obs_port",
    obs_password: "reconnect_interval_seconds",
  };
  for (const f of fields) {
    if (used.has(f.key)) continue;
    const mateKey = pairWith[f.key];
    const mate = mateKey && fields.find((x) => x.key === mateKey);
    if (mate) {
      used.add(f.key); used.add(mate.key);
      chunks.push(`<div class="field-row-2">${fieldHtml(f)}${fieldHtml(mate)}</div>`);
    } else {
      used.add(f.key);
      chunks.push(fieldHtml(f));
    }
  }
  host.innerHTML = chunks.join("");
  host.querySelectorAll(".listbox").forEach(bindListboxValue);

  const foot = $("settings-footer");
  if (settingsGroup === "obs") {
    foot.classList.remove("is-hidden");
    foot.innerHTML = `
      <span>${esc(s.obs_footer.text)}</span>
      <button class="pill ghost no-drag" id="btn-test-obs">Test again</button>`;
  } else {
    foot.classList.add("is-hidden");
    foot.innerHTML = "";
  }

  if (currentPane === "settings" && s.saved_at) {
    const actions = $("pane-actions");
    let stamp = actions.querySelector(".settings-saved");
    if (!stamp) {
      stamp = document.createElement("span");
      stamp.className = "settings-saved";
      actions.prepend(stamp);
    }
    stamp.innerHTML = `<i></i>Saved ${esc(s.saved_at)}`;
  }
}

function fieldHtml(f) {
  if (f.kind === "bool") {
    const on = f.value === "on";
    return `<div class="field toggle" data-key="${esc(f.key)}">
      <div class="toggle-copy">
        <div class="field-head">
          <span class="field-label">${esc(f.label)}</span>
          <span class="field-key">${esc(f.key)}</span>
        </div>
        ${f.hint ? `<div class="toggle-hint">${esc(f.hint)}</div>` : ""}
      </div>
      <button type="button" class="switch no-drag ${on ? "is-on" : ""}" data-toggle="${esc(f.key)}"
              aria-pressed="${on}"></button>
    </div>`;
  }
  if (f.kind === "choice") {
    const options = (f.choices || []).map((c) => ({ value: c, label: c }));
    return `<div class="field" data-key="${esc(f.key)}">
      <div class="field-head">
        <span class="field-label">${esc(f.label)}</span>
        <span class="field-key">${esc(f.key)}</span>
      </div>
      ${listboxHtml({
        className: "field-select",
        options,
        value: f.value,
        setting: f.key,
      })}
      ${f.hint ? `<div class="field-hint">${esc(f.hint)}</div>` : ""}
    </div>`;
  }
  const secret = f.kind === "secret" ? ` type="password"` : "";
  return `<div class="field" data-key="${esc(f.key)}">
    <div class="field-head">
      <span class="field-label">${esc(f.label)}</span>
      <span class="field-key">${esc(f.key)}</span>
      ${f.unit ? `<span class="field-unit">${esc(f.unit)}</span>` : ""}
    </div>
    <input class="field-input no-drag" data-setting="${esc(f.key)}" value="${esc(f.value)}"${secret}>
    ${f.hint ? `<div class="field-hint">${esc(f.hint)}${f.restart ? " Takes effect after a restart." : ""}</div>` : ""}
  </div>`;
}

async function load() {
  const d = await window.pywebview.api.snapshot();
  lastSnapshot = d;
  renderConn(d);
  renderHero(d);
  renderTiles(d);
  renderActivity(d);
  renderRibbon(d);
  renderClips(d);
  renderForecast(d);
  renderGames(d);
  renderProfilePanel();
  renderMacropad(d);
  renderSettings(d);
  ensureSpots();
}

/* --- 1l first run ------------------------------------------------------ */
/* "A four-step setup that gets someone from install to auto-recording in
   under a minute — with live connection feedback so there's no guesswork."
   The feedback is the part that matters: step 2 is the only step that can
   fail for a reason the reader cannot guess, so it says which of the three
   things went wrong rather than showing a socket error. */

const SETUP_STEPS = [
  {
    key: "welcome",
    nav: "Welcome",
    title: "Welcome to Nebula",
    body: "Nebula sits in your tray and watches for games. When one starts it tells "
        + "OBS to record, and when you stop playing it files the clip under that "
        + "game's name. Nothing to press. This takes about a minute, and you can "
        + "change any of it later in Settings.",
    fields: [],
  },
  {
    key: "obs",
    nav: "Connect to OBS",
    title: "Connect to OBS",
    body: "Nebula drives OBS over its websocket. In OBS, open Tools → WebSocket Server "
        + "Settings and tick “Enable WebSocket server”, then confirm the details below. "
        + "Nebula can launch OBS for you afterwards.",
    fields: [
      { key: "obs_host", label: "Host", half: true },
      { key: "obs_port", label: "Port", half: true },
      { key: "obs_password", label: "Password", hint: "Blank unless you ticked authentication in OBS.", secret: true },
    ],
    test: "Test connection",
  },
  {
    key: "folder",
    nav: "Choose a recordings folder",
    title: "Where should clips go?",
    body: "Nebula creates one folder per game inside this one. Point it at the drive "
        + "with room on it — a session can be several gigabytes.",
    fields: [{ key: "recording_root", label: "Recording root", browse: true }],
  },
  {
    key: "steam",
    nav: "Scan Steam & set a hotkey",
    title: "Find your games, pick a key",
    body: "Scanning Steam teaches Nebula which of your installed apps are games, so it "
        + "does not have to ask the first time you launch one. The hotkey toggles "
        + "watching on and off from anywhere, even mid-game.",
    fields: [{ key: "toggle_hotkey", label: "Toggle key", hint: "A key name, e.g. ` or f12 or ctrl+alt+r." }],
    scan: "Scan Steam library",
  },
];

let setupState = { step: 0, values: {}, active: false, busy: false };

function setupFieldHtml(f, value) {
  const secret = f.secret ? ` type="password"` : "";
  const inner = `<div class="field" data-key="${esc(f.key)}">
      <div class="field-head">
        <span class="field-label">${esc(f.label)}</span>
        <span class="field-key">${esc(f.key)}</span>
      </div>
      <input class="field-input no-drag" data-setup="${esc(f.key)}" value="${esc(value || "")}"${secret}>
      ${f.hint ? `<div class="field-hint">${esc(f.hint)}</div>` : ""}
    </div>`;
  if (!f.browse) return inner;
  return `<div class="setup-row is-path">${inner}
    <button class="pill ghost no-drag" id="setup-browse" type="button">Browse…</button></div>`;
}

function renderSetup() {
  const step = SETUP_STEPS[setupState.step];
  $("setup-steps").innerHTML = SETUP_STEPS.map((s, i) => `
    <li class="setup-step ${i === setupState.step ? "is-current" : (i < setupState.step ? "is-done" : "")}">
      <span class="n">${i + 1}</span>${esc(s.nav)}
    </li>`).join("");
  $("setup-eyebrow").textContent = `Step ${setupState.step + 1} of ${SETUP_STEPS.length}`;
  $("setup-title").textContent = step.title;
  $("setup-body").textContent = step.body;

  const halves = step.fields.filter((f) => f.half);
  const rest = step.fields.filter((f) => !f.half);
  $("setup-fields").innerHTML =
    (halves.length
      ? `<div class="setup-row">${halves.map((f) => setupFieldHtml(f, setupState.values[f.key])).join("")}</div>`
      : "") +
    rest.map((f) => setupFieldHtml(f, setupState.values[f.key])).join("");

  const actions = $("setup-actions") || $("setup-next").parentElement;
  let extra = actions.querySelector("#setup-action");
  if (extra) extra.remove();
  const label = step.test || step.scan;
  if (label) {
    extra = document.createElement("button");
    extra.className = "pill ghost no-drag";
    extra.id = "setup-action";
    extra.type = "button";
    extra.textContent = label;
    actions.insertBefore(extra, $("setup-skip"));
  }

  $("setup-back").hidden = setupState.step === 0;
  $("setup-next").textContent =
    setupState.step === SETUP_STEPS.length - 1 ? "Finish" : "Continue";
  setSetupStatus(null);
}

function setSetupStatus(kind, text, detail) {
  const host = $("setup-status");
  if (!kind) {
    host.hidden = true;
    host.className = "setup-status";
    host.innerHTML = "";
    return;
  }
  host.hidden = false;
  host.className = "setup-status" + (kind === "ok" ? " is-ok" : kind === "bad" ? " is-bad" : "");
  host.innerHTML = `<i></i><b>${esc(text)}</b>` + (detail ? `<span>${esc(detail)}</span>` : "");
}

function readSetupFields() {
  document.querySelectorAll("[data-setup]").forEach((el) => {
    setupState.values[el.dataset.setup] = el.value;
  });
}

async function setupTestObs() {
  readSetupFields();
  setSetupStatus("busy", "Trying…");
  const r = await window.pywebview.api.setup_test_obs(
    setupState.values.obs_host, setupState.values.obs_port, setupState.values.obs_password);
  if (r.ok) setSetupStatus("ok", r.text, r.detail);
  else setSetupStatus("bad", "Not connected", r.error);
}

async function setupScanSteam() {
  setSetupStatus("busy", "Scanning your Steam libraries…");
  const r = await window.pywebview.api.setup_scan_steam();
  if (r.ok) {
    setSetupStatus("ok", `${r.games} game${r.games === 1 ? "" : "s"} known`,
                   r.games ? "Nebula will record these without asking." : "Nothing found — it will ask the first time you play.");
  } else {
    setSetupStatus("bad", "Scan failed", r.error);
  }
}

async function setupBrowse() {
  readSetupFields();
  const r = await window.pywebview.api.setup_choose_folder(setupState.values.recording_root || "");
  if (r && r.ok) {
    setupState.values.recording_root = r.path;
    renderSetup();
  }
}

async function finishSetup(skipped) {
  if (setupState.busy) return;
  setupState.busy = true;
  readSetupFields();
  const r = await window.pywebview.api.setup_finish(setupState.values, !!skipped);
  setupState.busy = false;
  if (!r.ok) {
    setSetupStatus("bad", "Couldn't save", (r.errors || []).join(" · "));
    return;
  }
  setupState.active = false;
  $("setup").hidden = true;
  await load();
  showPane("dashboard");
}

function startSetup(cfg) {
  setupState = { step: 0, values: Object.assign({}, cfg.setup.values), active: true, busy: false };
  $("setup").hidden = false;
  renderSetup();
}

function wireSetup() {
  $("setup").addEventListener("click", async (e) => {
    if (!setupState.active) return;
    if (e.target.closest("#setup-back")) {
      readSetupFields();
      setupState.step = Math.max(0, setupState.step - 1);
      renderSetup();
      return;
    }
    if (e.target.closest("#setup-next")) {
      readSetupFields();
      if (setupState.step === SETUP_STEPS.length - 1) {
        await finishSetup(false);
      } else {
        setupState.step += 1;
        renderSetup();
      }
      return;
    }
    if (e.target.closest("#setup-skip")) { await finishSetup(true); return; }
    if (e.target.closest("#setup-browse")) { await setupBrowse(); return; }
    if (e.target.closest("#setup-action")) {
      const step = SETUP_STEPS[setupState.step];
      if (step.test) await setupTestObs();
      else if (step.scan) await setupScanSteam();
    }
  });
}

/* --- perf HUD ---------------------------------------------------------- */

function startHud() {
  let frames = 0, last = performance.now(), prev = last;
  const times = [];

  function tick(now) {
    frames++;
    times.push(now - prev); prev = now;
    if (times.length > 240) times.shift();
    if (now - last >= 1000) {
      const fps = (frames * 1000) / (now - last);
      const sorted = [...times].sort((a, b) => a - b);
      const p50 = sorted[Math.floor(sorted.length / 2)] || 0;
      $("hud-fps").textContent = fps.toFixed(0);
      const p = $("hud-p50");
      p.textContent = p50.toFixed(1) + "ms";
      p.className = p50 > 20 ? "warn" : "";
      frames = 0; last = now;
    }
    requestAnimationFrame(tick);
  }
  // Opt-in only. A permanent rAF loop forces a composite every refresh even
  // when nothing on screen has changed, which is most of what was pinning the
  // integrated GPU. Enable with ?hud=1 when you actually want frame numbers.
  const hudOn = new URLSearchParams(location.search).get("hud") === "1";
  // ...and the *panel* is opt-in too, which it was not: ?hud=1 gated only the
  // frame counter, so the readout shipped visible in the packaged exe. It is
  // absolutely positioned bottom-right of the pane, so it sat on top of the
  // Settings "Test again" button, the last Clips row's actions and the Games
  // "right-click a row" hint. Developer instrumentation is not chrome.
  if (!hudOn) $("hud").classList.add("is-hidden");
  if (hudOn) {
    requestAnimationFrame(tick);
  } else {
    $("hud-fps").textContent = "off";
    $("hud-p50").textContent = "off";
  }

  document.addEventListener("visibilitychange", () => {
    setAwake(!document.hidden);
  });

  setInterval(async () => {
    if (!window.pywebview) return;
    // proc() walks the whole process tree for RSS and CPU. With the panel
    // hidden nothing consumes the answer, so don't pay for it.
    if (hudOn) {
      const p = await window.pywebview.api.proc();
      $("hud-rss").textContent = p.rss_mb.toFixed(0) + "MB";
      const c = $("hud-cpu");
      c.textContent = p.cpu_pct.toFixed(1) + "%";
      c.className = p.cpu_pct > 8 ? "warn" : "";
    }
    // This one stays unconditional: Python never pushes the sleep state, the
    // page polls for it. Gate this and the backdrop never goes to sleep.
    try {
      const a = await window.pywebview.api.page_awake();
      setAwake(a.awake);
    } catch (_) { /* bridge not ready yet */ }
  }, 1000);
}

/* --- awake / asleep ----------------------------------------------------- */

/* Nebula is a tray app: it is hidden for almost all of its life, and it is
   hidden precisely when a game owns the GPU. Measured before this existed:
   76% of the integrated GPU whether the window was visible or minimised,
   because a compositor animation keeps compositing regardless of whether a
   human can see it. `document.hidden` never fired - a Win32 minimise of a
   frameless WebView2 does not background the document - so the Python host
   calls setAwake(false) on hide and setAwake(true) on show. */
function setAwake(on) {
  document.documentElement.classList.toggle("asleep", !on);
  const el = document.getElementById("hud-vis");
  if (el) el.textContent = on ? "visible" : "asleep";
}
window.setAwake = setAwake;

/* --- wiring ------------------------------------------------------------ */

function ready() {
  return new Promise((resolve) => {
    const go = () => window.pywebview && window.pywebview.api && (resolve(), true);
    if (go()) return;
    window.addEventListener("pywebviewready", go, { once: true });
    const t = setInterval(() => go() && clearInterval(t), 50);
  });
}

function fail(where, err) {
  const hud = $("hud");
  const row = document.createElement("div");
  row.className = "hud-row";
  row.style.display = "block";
  row.innerHTML = `<span>${where}</span> <b class="warn">${
    String((err && (err.message || err.name)) || err).slice(0, 90)}</b>`;
  hud.appendChild(row);
  console.error(where, err);
}

(async function init() {
  await ready();
  try {
    bootCfg = await window.pywebview.api.config();
    applyAppearance(bootCfg.appearance);
    buildBackdrop(bootCfg.background, bootCfg.seed);
    initDashboard(bootCfg);
    wireDashCustomise();
    wireSetup();
    if (bootCfg.setup && bootCfg.setup.needed) startSetup(bootCfg);
    ensureSpots();
    wirePointer(bootCfg.background.motion.pointer_lean_window_px);
  } catch (e) { fail("backdrop", e); }
  try { startHud(); } catch (e) { fail("hud", e); }
  try {
    await load();
    let bootPane = "dashboard";
    try {
      const r = await window.pywebview.api.consume_goto_pane();
      if (r && r.pane) bootPane = r.pane;
    } catch (_) { /* bridge not ready */ }
    showPane(bootPane);
    let pollMs = 5000;
    const pollLoop = async () => {
      await load();
      const live = lastSnapshot && lastSnapshot.hero &&
        (lastSnapshot.hero.state === "recording" || lastSnapshot.hero.state === "paused");
      const onClips = currentPane === "clips";
      pollMs = live ? 1000 : (onClips ? 3000 : 5000);
      setTimeout(pollLoop, pollMs);
    };
    setTimeout(pollLoop, pollMs);
    /* Dev shoot-loop: write a pane name to shots/goto_pane.txt (repo root)
       and this polls it, or pass it at boot before the window opens. */
    setInterval(async () => {
      try {
        const r = await window.pywebview.api.consume_goto_pane();
        if (r && r.pane) showPane(r.pane);
      } catch (_) { /* bridge not ready */ }
    }, 400);
    const bootQ = new URLSearchParams(location.search);
    if (bootQ.get("palette") === "1") openPalette();
    if (bootQ.get("listbox") === "1") {
      showPane("clips");
      setTimeout(() => {
        const lb = $("clip-sort");
        if (lb) openListbox(lb);
      }, 900);
    }
    if (bootQ.get("customise") === "1") {
      showPane("dashboard");
      const omit = (bootQ.get("dashomit") || "").split(",").map((s) => s.trim()).filter(Boolean);
      if (omit.length) {
        applyDashLayout(dashLayout.filter((it) => !omit.includes(it.id)), { animate: false });
      }
      setDashEditing(true);
    }
    /* ?settings=<group> — the Settings pane opens on "obs", which has no
       boolean fields, so the toggle row could not be photographed at all.
       Same shape as the switches above. e.g. ?settings=replay */
    if (bootQ.get("settings")) {
      settingsGroup = bootQ.get("settings");
      showPane("settings");
      if (lastSnapshot) renderSettings(lastSnapshot);
    }
    if (bootQ.get("game")) {
      const gname = bootQ.get("game");
      showPane("games");
      const g = (lastSnapshot && lastSnapshot.games && lastSnapshot.games.games) || [];
      const row = g.find((x) => x.name === gname);
      if (row && row.exes && row.exes[0]) await selectGame(row.exes[0], row.name);
    }
  } catch (e) { fail("data", e); }
})();

async function commitSetting(key, raw) {
  const r = await window.pywebview.api.set_setting(key, raw);
  if (!r.ok) {
    fail("settings", r.error || "reject");
    await load();
    return;
  }
  if (r.saved_at && lastSnapshot) {
    lastSnapshot.settings.saved_at = r.saved_at;
    if (currentPane === "settings") {
      showPane("settings");
    }
  }
}

document.addEventListener("click", async (e) => {
  const lbOpt = e.target.closest(".listbox-option");
  if (lbOpt && listboxState.host) {
    selectListboxOption(lbOpt.dataset.listboxValue);
    return;
  }

  const lbTrigger = e.target.closest(".listbox-trigger");
  if (lbTrigger) {
    const host = lbTrigger.closest(".listbox");
    if (listboxState.host === host) closeListboxPanel(false);
    else openListbox(host);
    return;
  }

  if (listboxState.host &&
      !e.target.closest(".listbox") &&
      !e.target.closest("#listbox-panel")) {
    closeListboxPanel(false);
  }

  if (e.target.closest("#btn-customise")) {
    toggleCustomise();
    if (currentPane === "dashboard") showPane("dashboard");
    return;
  }

  if (e.target.closest("#btn-palette")) {
    openPalette();
    return;
  }

  const paletteRow = e.target.closest(".palette-row");
  if (paletteRow && paletteState.open) {
    const idx = parseInt(paletteRow.dataset.paletteIdx, 10);
    if (Number.isFinite(idx)) await runPaletteRow(idx);
    return;
  }

  if (e.target.closest("#palette-backdrop") === $("palette-backdrop") &&
      !e.target.closest("#palette")) {
    closePalette();
    return;
  }

  const gameRow = e.target.closest(".grow-row[data-basename]");
  if (gameRow) {
    await selectGame(gameRow.dataset.basename, gameRow.dataset.game);
    return;
  }

  const rail = e.target.closest(".rail-item[data-pane]");
  if (rail) {
    showPane(rail.dataset.pane);
    return;
  }

  if (e.target.closest("#btn-close")) return window.pywebview.api.close();
  if (e.target.closest("#btn-min")) return window.pywebview.api.minimise();
  if (e.target.closest("#btn-refresh")) return load();
  if (e.target.closest("#btn-refresh-clips")) {
    await window.pywebview.api.refresh_clips();
    await load();
    return;
  }
  if (e.target.closest("#btn-reveal-root")) {
    return window.pywebview.api.open_recording_root();
  }

  const clipGame = e.target.closest(".clip-game");
  if (clipGame) {
    clipState.game = clipGame.dataset.game || "";
    if (lastSnapshot) renderClips(lastSnapshot);
    return;
  }

  const reveal = e.target.closest("[data-reveal]");
  if (reveal) {
    return window.pywebview.api.reveal_clip(reveal.dataset.reveal);
  }

  const delBtn = e.target.closest("[data-delete]");
  if (delBtn) {
    const path = delBtn.dataset.delete;
    let check = await window.pywebview.api.delete_clip(path, false);
    if (check.refused) {
      alert(check.message || "Can't delete yet");
      return;
    }
    if (check.need_confirm) {
      const msg = `Permanently delete ${check.rel}?\n\n${check.size_label} · this cannot be undone.`;
      if (!confirm(msg)) return;
      check = await window.pywebview.api.delete_clip(path, true);
    }
    if (!check.ok) {
      if (check.error && check.error !== "clip not found") alert(check.error || "Delete failed");
      return;
    }
    await load();
    return;
  }
  if (e.target.closest("#btn-open-folder")) {
    return window.pywebview.api.open_recording_root();
  }
  if (e.target.closest("#btn-rescan")) {
    await window.pywebview.api.rescan_steam();
    return;
  }
  if (e.target.closest("#btn-bench")) {
    const b = e.target.closest("#btn-bench");
    b.textContent = "measuring…";
    const r = await window.pywebview.api.bench(10);
    b.textContent = `cpu ${r.cpu_pct.toFixed(1)}% · rss ${r.rss_mb.toFixed(0)}MB`;
    setTimeout(() => (b.textContent = "Run 10s bench"), 6000);
    return;
  }

  if (e.target.closest("#btn-copy-log")) {
    await window.pywebview.api.copy_log();
    return;
  }
  if (e.target.closest("#btn-log-filter")) {
    const tags = (lastSnapshot && lastSnapshot.activity.tags) || ["All"];
    const cur = (lastSnapshot && lastSnapshot.activity.filter) || "All";
    const i = tags.indexOf(cur);
    const next = tags[(i + 1) % tags.length];
    await window.pywebview.api.set_log_filter(next);
    await load();
    return;
  }

  const heroAct = e.target.closest("[data-hero-action]");
  if (heroAct) {
    const label = heroAct.dataset.heroAction;
    if (label === "Connection settings") {
      showPane("settings");
      return;
    }
    await window.pywebview.api.hero_action(label);
    await load();
    return;
  }

  const classify = e.target.closest("[data-classify]");
  if (classify) {
    await window.pywebview.api.classify_pending(
      classify.dataset.key, classify.dataset.classify === "1");
    await load();
    return;
  }

  const nav = e.target.closest(".settings-nav-item");
  if (nav) {
    settingsGroup = nav.dataset.group;
    if (lastSnapshot) renderSettings(lastSnapshot);
    ensureSpots();
    return;
  }

  if (e.target.closest("#btn-reveal-cfg")) {
    return window.pywebview.api.reveal_config();
  }
  if (e.target.closest("#btn-test-obs")) {
    /* Real handshake lands in step 2. Refresh the honest footer for now. */
    await load();
    return;
  }

  const sw = e.target.closest("[data-toggle]");
  if (sw) {
    const on = !sw.classList.contains("is-on");
    sw.classList.toggle("is-on", on);
    await commitSetting(sw.dataset.toggle, on ? "on" : "off");
    return;
  }

  const psw = e.target.closest("[data-profile-toggle]");
  if (psw) {
    psw.classList.toggle("is-on");
    await commitProfile(psw.dataset.profileToggle);
    return;
  }
});

document.addEventListener("contextmenu", async (e) => {
  const row = e.target.closest("[data-promote]");
  if (!row) return;
  e.preventDefault();
  await window.pywebview.api.promote_non_game(row.dataset.promote);
  await load();
});

document.addEventListener("focusout", async (e) => {
  const pinput = e.target.closest("[data-profile]");
  if (pinput && !pinput.classList.contains("listbox")) {
    await commitProfile(pinput.dataset.profile);
    return;
  }
  const input = e.target.closest("[data-setting]");
  if (!input || input.classList.contains("listbox")) return;
  await commitSetting(input.dataset.setting, input.value);
});

document.addEventListener("input", (e) => {
  if (e.target.id === "palette-input") {
    paletteState.query = e.target.value;
    paletteState.index = 0;
    paintPalette();
    return;
  }
  if (e.target.id === "clip-search") {
    clipState.query = e.target.value;
    if (lastSnapshot) renderClips(lastSnapshot);
    return;
  }
});

document.addEventListener("change", async (e) => {
  const lb = e.target.closest(".listbox");
  if (!lb) return;
  if (lb.id === "clip-sort") {
    clipState.sort = lb.value;
    if (lastSnapshot) renderClips(lastSnapshot);
    return;
  }
  if (lb.dataset.profile) {
    await commitProfile(lb.dataset.profile);
    return;
  }
  if (lb.dataset.setting) {
    await commitSetting(lb.dataset.setting, lb.value);
  }
});

document.addEventListener("keydown", async (e) => {
  if (dashEditing && !paletteState.open) {
    if (e.key === "Escape") {
      e.preventDefault();
      cancelCustomise();
      if (currentPane === "dashboard") showPane("dashboard");
      return;
    }
    const grip = e.target.closest(".dash-strip-grip");
    if ((e.key === " " || e.key === "Enter") && grip) {
      e.preventDefault();
      setKbdHeld(dashKbdHeld ? null : grip.dataset.strip);
      return;
    }
    if (grip && (e.key === "Delete" || e.key === "Backspace")) {
      e.preventDefault();
      removeDashBlock(grip.dataset.strip);
      return;
    }
    if (dashKbdHeld && e.shiftKey && (e.key === "ArrowLeft" || e.key === "ArrowRight")) {
      e.preventDefault();
      stepKbdSpan(e.key === "ArrowRight" ? 1 : -1);
      return;
    }
    // The layout is an ordered list, so all four arrows step through it. Left
    // and right read naturally for two modules sharing a row; up and down for
    // two stacked. Both mean "one place along".
    if (dashKbdHeld && ["ArrowDown", "ArrowRight", "ArrowUp", "ArrowLeft"].includes(e.key)) {
      e.preventDefault();
      moveKbdHeld(e.key === "ArrowDown" || e.key === "ArrowRight" ? 1 : -1);
      return;
    }
  }

  if (listboxState.host) {
    if (e.key === "Escape") {
      e.preventDefault();
      closeListboxPanel(true);
      return;
    }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      if (listboxState.options.length) {
        listboxState.index = (listboxState.index + 1) % listboxState.options.length;
        paintListboxPanel();
      }
      return;
    }
    if (e.key === "ArrowUp") {
      e.preventDefault();
      if (listboxState.options.length) {
        listboxState.index = (listboxState.index - 1 + listboxState.options.length) %
          listboxState.options.length;
        paintListboxPanel();
      }
      return;
    }
    if (e.key === "Enter") {
      e.preventDefault();
      const opt = listboxState.options[listboxState.index];
      if (opt) selectListboxOption(opt.value);
      return;
    }
    return;
  }

  const lbTrigger = e.target.closest(".listbox-trigger");
  if (lbTrigger && (e.key === "ArrowDown" || e.key === "ArrowUp" || e.key === " " || e.key === "Enter")) {
    e.preventDefault();
    const host = lbTrigger.closest(".listbox");
    openListbox(host);
    if (e.key === "ArrowUp" && listboxState.options.length) {
      listboxState.index = (listboxState.index - 1 + listboxState.options.length) %
        listboxState.options.length;
      paintListboxPanel();
    }
    return;
  }

  if (paletteState.open) {
    if (e.key === "Escape") {
      e.preventDefault();
      closePalette();
      return;
    }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      if (paletteState.flat.length) {
        paletteState.index = (paletteState.index + 1) % paletteState.flat.length;
        paintPalette();
      }
      return;
    }
    if (e.key === "ArrowUp") {
      e.preventDefault();
      if (paletteState.flat.length) {
        paletteState.index = (paletteState.index - 1 + paletteState.flat.length) % paletteState.flat.length;
        paintPalette();
      }
      return;
    }
    if (e.key === "Enter") {
      e.preventDefault();
      await runPaletteRow(paletteState.index);
      return;
    }
    return;
  }

  if (paletteHotkeyMatch(e)) {
    e.preventDefault();
    openPalette();
    return;
  }

  if (e.key !== "Enter") return;
  const input = e.target.closest("input[data-setting]");
  if (!input) return;
  input.blur();
});
