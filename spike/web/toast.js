/* Toast — one slot, one tick chain, replace in place (frame 2i). */

const $ = (id) => document.getElementById(id);

const state = {
  cfg: null,
  remaining: 0,
  hovering: false,
  dismissing: false,
  ticking: false,
  tickHandle: null,
  hasDetail: false,
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
  root.style.setProperty("--toast-w", cfg.w + "px");
  root.style.setProperty("--toast-h", cfg.h + "px");
  root.style.setProperty("--toast-drain-h", cfg.drain_h + "px");
  root.style.setProperty("--toast-in-ms", cfg.in_ms + "ms");
  root.style.setProperty("--toast-in-rise", cfg.in_rise + "px");
  root.style.setProperty("--toast-out-ms", cfg.out_ms + "ms");
}

function tintCss(name) {
  if (name === "ember") return "var(--ember)";
  if (name === "accent") return "var(--accent)";
  return name || "var(--accent)";
}

function chipBg(name) {
  if (name === "ember") return "rgb(var(--ember-rgb) / .14)";
  return "rgb(var(--accent-rgb) / .14)";
}

function setDrain(fraction) {
  document.documentElement.style.setProperty(
    "--drain-frac",
    String(Math.max(0, Math.min(1, fraction))),
  );
}

function paint(content) {
  const toast = $("toast");
  const tint = content.tint || "accent";
  $("chip").style.background = chipBg(tint);
  const icon = $("icon");
  icon.textContent = content.glyph || "";
  icon.style.color = tintCss(tint);
  $("title").textContent = content.title || "";
  $("sub").textContent = content.sub || "";
  const detail = $("detail");
  if (content.detail) {
    detail.textContent = content.detail;
    detail.hidden = !state.hovering;
    state.hasDetail = true;
  } else {
    detail.textContent = "";
    detail.hidden = true;
    state.hasDetail = false;
  }
  $("drain").style.background = tintCss(tint);
  setDrain(1);
}

function riseIn() {
  const toast = $("toast");
  toast.classList.remove("is-dismissing");
  toast.classList.remove("is-visible");
  void toast.offsetWidth;
  toast.classList.add("is-visible");
}

function cancelDismiss() {
  state.dismissing = false;
  const toast = $("toast");
  toast.classList.remove("is-dismissing");
  toast.classList.add("is-visible");
}

function fadeOut() {
  state.dismissing = true;
  $("toast").classList.add("is-dismissing");
  $("toast").classList.remove("is-visible");
  const outMs = (state.cfg && state.cfg.out_ms) || 200;
  setTimeout(() => {
    if (!state.dismissing) return;
    state.ticking = false;
    state.tickHandle = null;
    if (window.pywebview && window.pywebview.api) {
      window.pywebview.api.on_expired();
    }
  }, outMs + 20);
}

function tick() {
  if (!state.ticking) return;
  if (!state.hovering && !state.dismissing) {
    state.remaining -= 50;
  }
  if (state.remaining <= 0 && !state.dismissing) {
    fadeOut();
    return;
  }
  if (!state.dismissing && state.cfg) {
    setDrain(state.remaining / state.cfg.life_ms);
  }
  state.tickHandle = setTimeout(tick, 50);
}

function ensureTicking() {
  if (state.ticking) return;
  state.ticking = true;
  tick();
}

/* Called from Python via evaluate_js — the replace path. */
window.toastReplace = function (content) {
  if (!state.cfg) return;
  if (state.dismissing) cancelDismiss();
  paint(content);
  state.remaining = state.cfg.life_ms;
  riseIn();
  ensureTicking();
};

async function boot() {
  await waitApi();
  state.cfg = await window.pywebview.api.config();
  applyTokens(state.cfg);

  const toast = $("toast");
  toast.addEventListener("mouseenter", () => {
    state.hovering = true;
    if (state.hasDetail) $("detail").hidden = false;
  });
  toast.addEventListener("mouseleave", () => {
    state.hovering = false;
    if (state.hasDetail) $("detail").hidden = true;
  });
  toast.addEventListener("click", () => {
    window.pywebview.api.focus_main();
  });

  const pending = await window.pywebview.api.consume_pending();
  if (pending) window.toastReplace(pending);
  await window.pywebview.api.ready();
}

boot();
