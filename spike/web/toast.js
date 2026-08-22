/* Toast — one slot, one tick chain, replace in place (frame 2i).
   Status: single-row copy + tinted dust. Prompt: stacked copy + actions. */

const $ = (id) => document.getElementById(id);

const DEFAULT_CFG = {
  w: 384,
  h: 60,
  prompt_w: 448,
  prompt_h: 136,
  drain_h: 2,
  life_ms: 4000,
  prompt_life_ms: 30000,
  in_ms: 420,
  in_rise: 28,
  out_ms: 320,
  dust: [],
};

const state = {
  cfg: null,
  remaining: 0,
  life: 4000,
  hovering: false,
  dismissing: false,
  ticking: false,
  tickHandle: null,
  dustStyle: "drift",
  prompt: false,
  actions: [],
};

function waitApi(timeoutMs) {
  const limit = typeof timeoutMs === "number" ? timeoutMs : 8000;
  return new Promise((resolve, reject) => {
    const go = () => window.pywebview && window.pywebview.api && resolve();
    if (go()) return;
    window.addEventListener("pywebviewready", go, { once: true });
    const t = setInterval(() => { if (go()) clearInterval(t); }, 16);
    setTimeout(() => {
      clearInterval(t);
      if (!(window.pywebview && window.pywebview.api)) {
        reject(new Error("pywebview api timeout"));
      }
    }, limit);
  });
}

function ensureCfg(cfg) {
  if (cfg && typeof cfg === "object") {
    state.cfg = Object.assign({}, DEFAULT_CFG, cfg);
  } else if (!state.cfg) {
    state.cfg = Object.assign({}, DEFAULT_CFG);
  }
  return state.cfg;
}

function applyTokens(cfg, prompt) {
  const root = document.documentElement;
  const w = prompt ? (cfg.prompt_w || DEFAULT_CFG.prompt_w) : cfg.w;
  const h = prompt ? (cfg.prompt_h || DEFAULT_CFG.prompt_h) : cfg.h;
  root.style.setProperty("--toast-w", w + "px");
  root.style.setProperty("--toast-h", h + "px");
  root.style.setProperty("--toast-drain-h", cfg.drain_h + "px");
  root.style.setProperty("--toast-in-ms", cfg.in_ms + "ms");
  root.style.setProperty("--toast-in-rise", cfg.in_rise + "px");
  root.style.setProperty("--toast-out-ms", cfg.out_ms + "ms");
}

function setDrain(fraction) {
  document.documentElement.style.setProperty(
    "--drain-frac",
    String(Math.max(0, Math.min(1, fraction))),
  );
}

function seedDust(content) {
  const host = $("dust");
  if (!host) return;
  host.innerHTML = "";
  const style = content.dust_style || "drift";
  const amp = typeof content.dust_amp === "number" ? content.dust_amp : 1;
  const anchor = content.dust_anchor || "left";
  host.dataset.style = style;
  host.dataset.anchor = anchor;

  const specs = (state.cfg && state.cfg.dust) || [];
  const ox = anchor === "right" ? 8 : 0;
  specs.forEach((spec, i) => {
    const [dx, dy, r, a] = spec;
    const el = document.createElement("span");
    const size = Math.max(1.5, r * 2);
    // lint-allow: dust motes sized once when seeded; not animated layout
    el.style.width = size + "px";
    el.style.height = size + "px";
    el.style.setProperty("--dust-dx", (dx * amp) + "px");
    el.style.setProperty("--dust-dy", (dy * amp) + "px");
    el.style.setProperty("--dust-a", String(Math.max(0.12, Math.min(1, a * amp))));
    el.style.setProperty("--dust-orbit", (4 + (i % 3) * 2) + "px");
    el.style.marginLeft = (dx * amp + ox) + "px";
    el.style.marginTop = (dy * amp) + "px";
    el.style.animationDelay = (-i * 0.17) + "s";
    host.appendChild(el);
  });
  state.dustStyle = style;
}

function paintActions(actions) {
  const host = $("actions");
  const list = Array.isArray(actions) ? actions : [];
  state.actions = list;
  if (!host) return;
  if (!list.length) {
    host.hidden = true;
    return;
  }
  host.hidden = false;
  list.forEach((entry, i) => {
    const btn = $("btn" + i);
    if (!btn) return;
    const label = Array.isArray(entry) ? entry[0] : (entry && entry.label) || "";
    btn.textContent = label || (i === 0 ? "Record" : "Not now");
    btn.hidden = !label;
  });
  // Hide unused slots when fewer than two actions arrive.
  for (let i = list.length; i < 2; i++) {
    const btn = $("btn" + i);
    if (btn) btn.hidden = true;
  }
}

function paint(content) {
  const toast = $("toast");
  const tint = content.tint || "accent";
  const actions = content.actions || [];
  const prompt = Boolean(content.prompt) || actions.length > 0;
  state.prompt = prompt;
  toast.classList.toggle("is-ember", tint === "ember");
  toast.classList.toggle("is-prompt", prompt);
  applyTokens(state.cfg || DEFAULT_CFG, prompt);

  $("icon").textContent = content.glyph || "";
  $("title").textContent = content.title || "";

  const sub = (content.sub || "").trim();
  const detail = (content.detail || "").trim();
  const subEl = $("sub");
  const sepEl = $("sep");
  const detailEl = $("detail");

  if (prompt) {
    // Stacked: title over game name — no middot row (matches Tk prompt).
    sepEl.hidden = true;
    detailEl.hidden = true;
    detailEl.textContent = "";
    if (sub) {
      subEl.textContent = sub;
      subEl.hidden = false;
    } else {
      subEl.textContent = "";
      subEl.hidden = true;
    }
  } else if (sub) {
    subEl.textContent = sub;
    subEl.hidden = false;
    sepEl.hidden = false;
    if (detail) {
      detailEl.textContent = "·  " + detail;
      detailEl.hidden = false;
      if ((content.title || "").length > 22) {
        subEl.hidden = true;
        sepEl.hidden = true;
        detailEl.textContent = detail;
      }
    } else {
      detailEl.textContent = "";
      detailEl.hidden = true;
    }
  } else {
    subEl.textContent = "";
    subEl.hidden = true;
    sepEl.hidden = true;
    if (detail) {
      detailEl.textContent = detail;
      detailEl.hidden = false;
    } else {
      detailEl.textContent = "";
      detailEl.hidden = true;
    }
  }

  paintActions(actions);
  seedDust(content);
  setDrain(1);
}

function riseIn() {
  const toast = $("toast");
  toast.classList.remove("is-dismissing");
  toast.classList.remove("is-visible");
  toast.classList.remove("is-swap");
  toast.style.opacity = "";
  void toast.offsetWidth;
  toast.classList.add("is-visible");
}

function swapPulse() {
  const toast = $("toast");
  toast.classList.add("is-swap");
  toast.style.opacity = "0.72";
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      toast.style.opacity = "";
      toast.classList.remove("is-swap");
      toast.classList.add("is-visible");
    });
  });
}

function cancelDismiss() {
  state.dismissing = false;
  const toast = $("toast");
  toast.classList.remove("is-dismissing");
  toast.classList.add("is-visible");
  toast.style.opacity = "";
}

function fadeOut() {
  state.dismissing = true;
  $("toast").classList.add("is-dismissing");
  $("toast").classList.remove("is-visible");
  const outMs = (state.cfg && state.cfg.out_ms) || DEFAULT_CFG.out_ms;
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
  if (!state.dismissing && state.life > 0) {
    setDrain(state.remaining / state.life);
  }
  state.tickHandle = setTimeout(tick, 50);
}

function ensureTicking() {
  if (state.ticking) return;
  state.ticking = true;
  tick();
}

function lifeFor(content) {
  const cfg = state.cfg || DEFAULT_CFG;
  const prompt = Boolean(content && (content.prompt || (content.actions || []).length));
  return prompt
    ? (cfg.prompt_life_ms || DEFAULT_CFG.prompt_life_ms)
    : (cfg.life_ms || DEFAULT_CFG.life_ms);
}

/* Called from Python via evaluate_js — the replace path. */
window.toastReplace = function (content) {
  ensureCfg(state.cfg);
  content = content || {};
  const wasDismissing = state.dismissing;
  if (state.dismissing) cancelDismiss();
  paint(content);
  state.life = lifeFor(content);
  state.remaining = state.life;
  if (wasDismissing) {
    riseIn();
  } else if ($("toast").classList.contains("is-visible")) {
    swapPulse();
  } else {
    riseIn();
  }
  ensureTicking();
};

/* Rescue path for a blank/opacity-0 surface (Python paint check). */
window.toastForceVisible = function () {
  ensureCfg(state.cfg);
  const toast = $("toast");
  toast.classList.remove("is-dismissing");
  toast.classList.add("is-visible");
  toast.style.opacity = "1";
  toast.style.transform = "translateY(0)";
  if (!(document.getElementById("title") || {}).textContent) {
    paint({
      tint: "ember",
      glyph: "",
      title: "Toast ready",
      sub: "",
      detail: "",
    });
  }
  if (!state.ticking) {
    state.life = (state.cfg && state.cfg.life_ms) || DEFAULT_CFG.life_ms;
    state.remaining = state.life;
    ensureTicking();
  }
};

function failVisible(message) {
  ensureCfg(null);
  applyTokens(state.cfg, false);
  paint({
    tint: "ember",
    glyph: "",
    title: message || "Toast failed to load",
    sub: "",
    detail: "",
  });
  riseIn();
  document.documentElement.setAttribute("data-toast-fail", "1");
}

function onActionClick(i) {
  if (window.pywebview && window.pywebview.api && window.pywebview.api.action) {
    window.pywebview.api.action(i);
  }
}

async function boot() {
  try {
    await waitApi(8000);
  } catch (err) {
    failVisible("Toast bridge timed out");
    return;
  }
  try {
    const cfg = await window.pywebview.api.config();
    ensureCfg(cfg);
    applyTokens(state.cfg, false);
  } catch (err) {
    failVisible("Toast config failed");
    return;
  }

  const toast = $("toast");
  toast.addEventListener("mouseenter", () => { state.hovering = true; });
  toast.addEventListener("mouseleave", () => { state.hovering = false; });
  toast.addEventListener("click", (ev) => {
    // Action pills handle their own clicks; body click focuses main.
    if (ev.target && ev.target.closest && ev.target.closest(".toast-btn")) {
      return;
    }
    if (state.prompt) return; // prompt body is not a focus shortcut
    window.pywebview.api.focus_main();
  });
  ["btn0", "btn1"].forEach((id) => {
    const btn = $(id);
    if (!btn) return;
    btn.addEventListener("click", (ev) => {
      ev.stopPropagation();
      const i = parseInt(btn.getAttribute("data-i") || "0", 10);
      onActionClick(i);
    });
  });

  try {
    const pending = await window.pywebview.api.consume_pending();
    if (pending) window.toastReplace(pending);
  } catch (err) {
    failVisible("Toast pending failed");
  }
  try {
    await window.pywebview.api.ready();
  } catch (err) {
    /* paint already attempted */
  }

  setTimeout(() => {
    const el = $("toast");
    const cs = el ? getComputedStyle(el) : null;
    const title = (document.getElementById("title") || {}).textContent || "";
    if (!el || !cs) return;
    if (parseFloat(cs.opacity) < 0.2 || !title.trim()) {
      window.toastForceVisible();
    }
  }, 900);
}

boot();
