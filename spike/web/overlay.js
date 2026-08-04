/* Mini overlay — frame 2k + transport buttons. */

const $ = (id) => document.getElementById(id);

const state = {
  cfg: null,
  faded: false,
  fadeTimer: null,
  drag: null,
};

function waitApi() {
  return new Promise((resolve) => {
    const go = () => window.pywebview && window.pywebview.api && resolve();
    if (go()) return;
    window.addEventListener("pywebviewready", go, { once: true });
    const t = setInterval(() => { if (go()) clearInterval(t); }, 16);
  });
}

function applyTokens(cfg) {
  const root = document.documentElement;
  root.style.setProperty("--mini-w", cfg.w + "px");
  root.style.setProperty("--mini-h", cfg.h + "px");
  root.style.setProperty("--mini-faded-a", String(cfg.faded_opacity));
}

function glyph(name) {
  return (state.cfg && state.cfg.glyphs && state.cfg.glyphs[name]) || "";
}

function setFaded(faded) {
  if (state.faded === faded) return;
  state.faded = faded;
  $("overlay").classList.toggle("is-faded", faded);
}

function scheduleFade() {
  if (state.fadeTimer) clearTimeout(state.fadeTimer);
  const delay = (state.cfg && state.cfg.fade_after_ms) || 3000;
  state.fadeTimer = setTimeout(() => setFaded(true), delay);
}

function wakeFade() {
  setFaded(false);
  scheduleFade();
}

function paint(data) {
  const timer = $("timer");
  timer.textContent = data.elapsed || "";
  $("game").textContent = data.game || "";
  const dot = $("dot");
  dot.textContent = glyph("record");
  dot.classList.toggle("is-paused", !!data.paused);
  $("act-pause").textContent = data.paused ? glyph("resume") : glyph("pause");
  $("act-pause").title = data.paused ? "Resume" : "Pause";
  $("act-stop").textContent = glyph("square");
  $("act-mark").textContent = glyph("mark_clip");
  $("act-collapse").textContent = glyph("collapse_mini");
}

/* Called from Python when host poll pushes new readouts. */
window.overlayUpdate = function (data) {
  paint(data || {});
};

async function boot() {
  await waitApi();
  state.cfg = await window.pywebview.api.config();
  applyTokens(state.cfg);

  $("act-mark").textContent = glyph("mark_clip");
  $("act-stop").textContent = glyph("square");
  $("act-pause").textContent = glyph("pause");
  $("act-collapse").textContent = glyph("collapse_mini");
  $("dot").textContent = glyph("record");

  const body = $("body");
  const controls = new Set([
    $("act-mark"), $("act-stop"), $("act-pause"), $("act-collapse"),
  ]);

  body.addEventListener("mousedown", (e) => {
    if (controls.has(e.target)) return;
    state.drag = { x: e.screenX, y: e.screenY };
    body.classList.add("is-dragging");
    wakeFade();
  });
  window.addEventListener("mousemove", (e) => {
    if (!state.drag) return;
    window.pywebview.api.drag_by(e.screenX - state.drag.x, e.screenY - state.drag.y);
    state.drag.x = e.screenX;
    state.drag.y = e.screenY;
  });
  window.addEventListener("mouseup", async () => {
    if (!state.drag) return;
    state.drag = null;
    body.classList.remove("is-dragging");
    await window.pywebview.api.drag_end();
  });

  $("overlay").addEventListener("mouseenter", wakeFade);
  $("overlay").addEventListener("mouseleave", scheduleFade);

  $("act-pause").addEventListener("click", () => window.pywebview.api.action("pause"));
  $("act-stop").addEventListener("click", () => window.pywebview.api.action("stop"));
  $("act-mark").addEventListener("click", () => window.pywebview.api.action("mark"));
  $("act-collapse").addEventListener("click", () => window.pywebview.api.action("collapse"));

  const snap = await window.pywebview.api.consume_snapshot();
  if (snap) paint(snap);
  scheduleFade();
  await window.pywebview.api.ready();
}

/* An unhandled rejection in boot() is otherwise completely silent - the page
   just sits there half-built, which is exactly how 2k's failure presented. */
boot().catch((e) => console.error("[overlay] boot failed", e));
