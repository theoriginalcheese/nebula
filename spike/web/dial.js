/* One dial menu. Opens, holds one background, moves the highlight, closes. */

const $ = (id) => document.getElementById(id);

let bgKey = "trail";
let bgIndex = -1;
let t = 0;
let last = 0;
let raf = 0;
let drewStill = false;

function reduced() {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches
    || document.documentElement.classList.contains("asleep");
}

function frame(now) {
  raf = 0;
  const cv = $("bg");
  if (!cv) return;
  if (reduced()) {
    if (!drewStill) {
      cv.dataset.bg = bgKey;
      paint(cv, t);
      drewStill = true;
    }
    return;
  }
  if (!last) last = now;
  const dt = Math.min(0.1, (now - last) / 1000);
  last = now;
  t += dt;
  cv.dataset.bg = bgKey;
  paint(cv, t);
  raf = requestAnimationFrame(frame);
}

function startLoop() {
  drewStill = false;
  if (raf) return;
  last = 0;
  raf = requestAnimationFrame(frame);
}

function stopLoop() {
  if (raf) cancelAnimationFrame(raf);
  raf = 0;
}

function setAsleep(on) {
  document.documentElement.classList.toggle("asleep", !!on);
  if (on) {
    stopLoop();
    const cv = $("bg");
    if (cv) {
      cv.dataset.bg = bgKey;
      paint(cv, t);
    }
    drewStill = true;
    return;
  }
  startLoop();
}
window.setAsleep = setAsleep;

function holdBackground(key) {
  if (RINGS[key] || FIELDS[key]) {
    bgKey = key;
    const at = POOL.indexOf(key);
    if (at >= 0) bgIndex = at;
    return;
  }
  bgIndex = pickIndex(Math.random, bgIndex);
  bgKey = POOL[bgIndex];
}

function waitApi(timeoutMs) {
  const limit = typeof timeoutMs === "number" ? timeoutMs : 8000;
  return new Promise((resolve, reject) => {
    const go = () => window.pywebview && window.pywebview.api && resolve();
    if (go()) return;
    window.addEventListener("pywebviewready", go, { once: true });
    const tmr = setInterval(() => { if (go()) clearInterval(tmr); }, 16);
    setTimeout(() => {
      clearInterval(tmr);
      if (!(window.pywebview && window.pywebview.api)) {
        reject(new Error("pywebview api timeout"));
      }
    }, limit);
  });
}

function setStatus(text) {
  $("statusWord").textContent = text || "";
}

function setPauseLabel(text) {
  const label = document.querySelector('[data-i="1"] .label');
  if (label) label.textContent = text || "Pause recording";
}

function setDeleteLabel(text, armed) {
  const row = document.querySelector('[data-i="4"]');
  if (!row) return;
  const label = row.querySelector(".label");
  if (label) label.textContent = text || "Delete this clip";
  row.classList.toggle("is-armed", !!armed);
}

function rowCount() {
  return document.querySelectorAll(".row").length || 1;
}

function highlight(index, instant) {
  const dial = $("dial");
  const i = Math.max(0, Math.min(rowCount() - 1, index | 0));
  if (instant) dial.classList.add("no-travel");
  dial.style.setProperty("--sel", String(i));
  document.querySelectorAll(".row").forEach((row) => {
    row.classList.toggle("is-on", Number(row.getAttribute("data-i")) === i);
  });
  if (instant) {
    void dial.offsetWidth;
    dial.classList.remove("no-travel");
  }
}

function applyChrome(payload) {
  setStatus(payload.status);
  setPauseLabel(payload.pauseLabel);
  setDeleteLabel(payload.deleteLabel, payload.deleteArmed);
  highlight(payload.index || 0, true);
}

function sizeCanvas(cv) {
  const cssW = cv.clientWidth || 314;
  const cssH = cv.clientHeight || 154;
  const scale = 2 * Math.min(2, window.devicePixelRatio || 1);
  const wantW = Math.round(cssW * scale);
  const wantH = Math.round(cssH * scale);
  if (cv.width !== wantW || cv.height !== wantH) {
    cv.width = wantW;
    cv.height = wantH;
  }
}

function dialOpen(payload) {
  payload = payload || {};
  // A sleep class left over from the hidden slot would freeze the rings
  // on one dark frame. Opening means the plate is on screen.
  document.documentElement.classList.remove("asleep");
  applyChrome(payload);
  holdBackground(payload.bg);
  t = Number.isFinite(payload.t) ? payload.t : Math.random() * 18;
  const cv = $("bg");
  if (cv) {
    sizeCanvas(cv);
    cv.dataset.bg = bgKey;
    paint(cv, t);
  }
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    stopLoop();
    drewStill = true;
  } else {
    drewStill = false;
    startLoop();
  }
}
window.dialOpen = dialOpen;

function dialHighlight(index) {
  highlight(index, false);
}
window.dialHighlight = dialHighlight;

function dialStatus(payload) {
  if (!payload) return;
  setStatus(payload.status);
  setPauseLabel(payload.pauseLabel);
  setDeleteLabel(payload.deleteLabel, payload.deleteArmed);
}
window.dialStatus = dialStatus;

function dialPreview(mode) {
  document.documentElement.classList.add("shot");
  const paused = mode === "row1";
  applyChrome({
    status: paused ? "Paused" : "Idle",
    pauseLabel: paused ? "Resume recording" : "Pause recording",
    index: mode === "row1" ? 1 : mode === "row2" ? 2 : 0,
  });
  holdBackground("trail");
  t = 4;
  const cv = $("bg");
  if (cv) {
    cv.dataset.bg = bgKey;
    paint(cv, t);
  }
}
window.dialPreview = dialPreview;

function rowIndex(row) {
  const i = Number(row && row.getAttribute("data-i"));
  return Number.isFinite(i) ? i : 0;
}

function bindRows() {
  document.querySelectorAll(".row").forEach((row) => {
    row.addEventListener("pointerenter", () => {
      const i = rowIndex(row);
      highlight(i, false);
      const api = window.pywebview && window.pywebview.api;
      if (api && api.point) api.point(i);
    });
    row.addEventListener("click", (ev) => {
      ev.preventDefault();
      const i = rowIndex(row);
      highlight(i, false);
      const api = window.pywebview && window.pywebview.api;
      if (api && api.choose) api.choose(i);
    });
  });
}

function bootPaint() {
  const cv = $("bg");
  if (!cv) return;
  holdBackground(bgKey);
  sizeCanvas(cv);
  cv.dataset.bg = bgKey;
  paint(cv, t || 1.2);
  if (!reduced()) startLoop();
}

bindRows();
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", bootPaint);
} else {
  bootPaint();
}

waitApi().then(() => {
  const api = window.pywebview.api;
  if (api && api.ready) api.ready();
}).catch(() => {});
