/* Canvas backgrounds from Nebula Dial Menu v4.dc.html.
   The pool is the round-5 likes. The other ring and field keys stay so a
   named background still paints; the random roll only uses POOL. */

const W = 314, H = 154, TAU = Math.PI * 2;

const CELL = 4;
const BR = { cx: 327, cy: 167 }, TR = { cx: 327, cy: -13 };
const RINGS = {
  rlow:   { rings: [{ ...BR, R: 112, rows: 6, rate: 40 / 18, pat: "blocks" }] },
  tilt:   { rings: [{ cx: 260, cy: 96, R: 100, rows: 6, rate: 24 / 18, pat: "blocks", sy: .4, axis: -16, depth: true }] },
  tiltTR: { rings: [{ cx: 260, cy: 60, R: 100, rows: 6, rate: -24 / 18, pat: "blocks", sy: .4, axis: 16, depth: true }] },
  trail:  { rings: [{ ...BR, R: 112, rows: 6, rate: 40 / 18, pat: "trail" }] },
  dash:   { rings: [{ ...BR, R: 112, rows: 6, rate: 30 / 18, pat: "dash" }] },
  twin:   { rings: [{ ...BR, R: 116, rows: 5, rate: 36 / 18, pat: "blocks" }, { ...BR, R: 82, rows: 4, rate: -30 / 18, pat: "dash", dim: .8 }] },
  half:   { rings: [{ cx: 300, cy: 96, R: 64, rows: 5, rate: 40 / 18, pat: "trail" }] },
  twinTR: { rings: [{ ...TR, R: 116, rows: 5, rate: -36 / 18, pat: "blocks" }, { ...TR, R: 82, rows: 4, rate: 30 / 18, pat: "dash", dim: .8 }] }
};
const RC = ["#8B7CF6", "#B9AEF9", "#D471E0", "#E9B872"];
const RZ = [[0, 1], [1, 2], [2, 3], [0, 2], [3, 0], [1, 2]];
const rhash = (a, b) => { let h = (a * 73856093) ^ (b * 19349663); h = Math.imul(h ^ (h >>> 13), 1274126177); return ((h ^ (h >>> 16)) >>> 0) / 4294967295; };
const mod = (a, n) => ((a % n) + n) % n;
function ringCell(g, x, y, t) {
  let px = x - g.cx, py = y - g.cy;
  if (g.sy) { const a = -g.axis * Math.PI / 180, c = Math.cos(a), s = Math.sin(a); [px, py] = [px * c - py * s, px * s + py * c]; py /= g.sy; }
  const d = Math.hypot(px, py), band = g.rows * CELL, inner = g.R - band / 2;
  if (d < inner || d >= inner + band) return null;
  const row = Math.floor((d - inner) / (band / g.rows)), raw = Math.atan2(py, px) * 180 / Math.PI, ang = raw - g.rate * t;
  let c = null, a = 1;
  if (g.pat === "blocks") {
    const N = Math.round(g.R * (40 * Math.PI / 180) / CELL), u = mod(ang, 40) / 40, jm = Math.floor(u * N), zone = Math.floor(u * RZ.length);
    const blk = Math.floor(jm / 3) * 7 + Math.floor(row / 2), h1 = rhash(blk + 11, row + 3), h2 = rhash(jm + 5, row * 17 + 1);
    if (((row === 0 || row === g.rows - 1) && h2 < .32) || h2 < .1) return null;
    c = RC[RZ[zone][h1 < .62 ? 0 : 1]]; if (h2 > .9) c = RC[RZ[(zone + 1) % RZ.length][0]];
  } else if (g.pat === "dash") {
    const seg = Math.floor(mod(ang, 360) / 30), u = mod(ang, 30) / 30;
    if (u > .7) return null;
    const h2 = rhash(Math.floor(u * 12) + seg * 31, row + 7);
    if ((row === 0 || row === g.rows - 1) && h2 < .25) return null;
    c = RC[[0, 2, 1, 3, 0, 2, 1, 2, 0, 3, 1, 2][seg]]; if (h2 > .88) c = RC[(seg + 1) % 4];
  } else if (g.pat === "trail") {
    const u = mod(ang, 120) / 120;
    if (u < .38) return null;
    const p = (u - .38) / .62, h2 = rhash(Math.floor(mod(ang, 360) / 3), row + 5);
    if (h2 > p * 1.15 + .05) return null;
    c = p > .9 ? (h2 < .3 ? "#E9B872" : "#F5F3FF") : p > .7 ? "#B9AEF9" : p > .4 ? "#8B7CF6" : "#D471E0";
    a = .35 + .65 * p;
  }
  if (g.depth) a *= .5 + .5 * (Math.sin(Math.atan2(py, px)) * .5 + .5);
  return [c, a * (g.dim || 1)];
}
function drawRing(ctx, k, t, spec, h, dy) {
  ctx.imageSmoothingEnabled = false;
  const limit = h || H;
  const shift = dy || 0;
  for (let j = 0; j < Math.ceil(limit / CELL); j++) for (let i = 0; i < Math.ceil(W / CELL); i++) {
    const x = i * CELL + CELL / 2, y = j * CELL + CELL / 2;
    let hit = null;
    for (const g of spec.rings) {
      const placed = shift && g.cy >= H * 0.5 ? { ...g, cy: g.cy + shift } : g;
      const r = ringCell(placed, x, y, t);
      if (r) { hit = r; break; }
    }
    if (!hit) continue;
    ctx.globalAlpha = hit[1] * (y < 32 ? .55 : 1) * (x < 150 ? .5 : 1);
    ctx.fillStyle = hit[0];
    const x0 = Math.round(i * CELL * k), y0 = Math.round(j * CELL * k);
    ctx.fillRect(x0, y0, Math.round((i + 1) * CELL * k) - x0, Math.round((j + 1) * CELL * k) - y0);
  }
}

const lerp = (a, b, t) => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];
const hx = s => { const n = parseInt(s.slice(1), 16); return [n >> 16, (n >> 8) & 255, n & 255]; };
const VIO = hx("#8B7CF6"), MAG = hx("#D471E0"), INK = hx("#F5F3FF"), AMB = hx("#E9B872"), AMB2 = hx("#F2D2A4");
const coolPal = base => (e, v) => {
  let c = e < .55 ? lerp(VIO, MAG, e / .55) : lerp(MAG, INK, (e - .55) / .45);
  if (v > 1.15 && e >= .99) c = lerp(c, AMB, Math.min(.7, (v - 1.15) * 1.4));
  return [c, base + (1 - base) * e];
};
const warmPal = (e, v) => {
  let c = e < .45 ? lerp(MAG, AMB, e / .45) : e < .8 ? lerp(AMB, AMB2, (e - .45) / .35) : lerp(AMB2, INK, (e - .8) / .2);
  if (v > .9 && e > .25 && e < .5) c = lerp(c, VIO, .3);
  return [c, .25 + .75 * e];
};
const sparsePal = (e) => [e < .5 ? lerp(VIO, MAG, e / .5) : lerp(MAG, INK, (e - .5) / .5), .15 + .85 * e];
const BLOOM = [
  { bx: 232, by: 66, R: 46, ax: 12, ay: 8, px: 14, py: 14, phx: 0, phy: 1.6, rp: 9, ra: .22 },
  { bx: 190, by: 116, R: 40, ax: -10, ay: 10, px: 14, py: 14, phx: 2.4, phy: .3, rp: 11, ra: .26 },
  { bx: 288, by: 116, R: 32, ax: 12, ay: 8, px: 18, py: 18, phx: 1, phy: 2.6, rp: 13, ra: .3, w: .6 }
];
const ROSE = (e) => [e < .5 ? lerp(VIO, MAG, e / .5) : lerp(MAG, hx("#E7A9EE"), Math.min(1, (e - .5) / .3)).map((v, i) => e > .8 ? v + (INK[i] - v) * (e - .8) / .2 : v), .2 + .8 * e];
const DUSK = (e, v) => { let c = e < .4 ? lerp(VIO, MAG, e / .4) : e < .75 ? lerp(MAG, AMB, (e - .4) / .35) : lerp(AMB, AMB2, (e - .75) / .25); return [c, .2 + .8 * e]; };
const patch = (bx, by, R, px, py, ph) => [
  { bx, by, R, ax: 12, ay: 8, px, py, phx: ph, phy: ph + 1.4, rp: 10, ra: .2 },
  { bx, by, R: R * .6, ax: 12, ay: 8, px, py, phx: ph, phy: ph + 1.4, rp: 13, ra: .3, ox: R * .5, oy: R * .35, op: 10 + ph },
  { bx, by, R: R * .5, ax: 12, ay: 8, px, py, phx: ph, phy: ph + 1.4, rp: 9, ra: .3, ox: -R * .45, oy: R * .4, op: 13 + ph }
];
const FIELDS = {
  hpatches: { cores: [...patch(236, 52, 24, 16, 13, 0), ...patch(196, 118, 20, 14, 17, 2), ...patch(288, 112, 18, 18, 11, 4)], pal: sparsePal },
  hrose: { cores: BLOOM, pal: ROSE },
  hdusk: { cores: BLOOM, pal: DUSK },
  hbloom: { cores: BLOOM, pal: coolPal(.2) },
  hwide: { cores: BLOOM.map(c => ({ ...c, R: c.R * 1.5, bx: c.bx - 18, ax: Math.sign(c.ax) * 16, ay: Math.sign(c.ay || 1) * 11, px: 16, py: 16 })), pal: coolPal(.2) },
  hsparse: { cores: [
    { bx: 232, by: 84, R: 30, ax: 14, ay: 9, px: 16, py: 16, phx: 0, phy: 1.4, rp: 10, ra: .2 },
    { bx: 232, by: 84, R: 18, ax: 14, ay: 9, px: 16, py: 16, phx: 0, phy: 1.4, rp: 13, ra: .3, ox: 16, oy: 10, op: 10 },
    { bx: 232, by: 84, R: 16, ax: 14, ay: 9, px: 16, py: 16, phx: 0, phy: 1.4, rp: 9, ra: .3, ox: -14, oy: 12, op: 13 }
  ], pal: sparsePal },
  hwarm: { cores: BLOOM, pal: warmPal }
};
function drawField(ctx, k, t, f, h, dy) {
  ctx.setTransform(k, 0, 0, k, 0, 0);
  const limit = h || H;
  const shift = dy || 0;
  const cores = shift ? f.cores.map(c => ({ ...c, by: c.by + shift })) : f.cores;
  const cs = cores.map(c => {
    let x = c.bx + Math.sin(TAU * t / c.px + c.phx) * c.ax, y = c.by + Math.sin(TAU * t / c.py + c.phy) * c.ay;
    if (c.op) { x += Math.sin(TAU * t / c.op) * c.ox; y += Math.cos(TAU * t / c.op) * c.oy; }
    return { x, y, R: c.R * (1 + Math.sin(TAU * t / c.rp + c.phx) * c.ra), w: c.w || 1 };
  });
  for (let gy = 4; gy < limit + 4; gy += 8) for (let gx = 4; gx < W + 4; gx += 8) {
    let v = 0;
    for (const c of cs) { const dx = Math.abs(gx - c.x), dy = Math.abs(gy - c.y), d = Math.cbrt(dx * dx * dx + dy * dy * dy), q = 1 - d / c.R; if (q > 0) v += c.w * q * q * (3 - 2 * q); }
    const cap = (gy < 32 && gx > 200) || (gx < 150 && gy > 32) ? .45 : 1, e = Math.min(cap, v);
    const [col, a] = f.pal(e, v);
    ctx.globalAlpha = a; ctx.fillStyle = `rgb(${col[0] | 0},${col[1] | 0},${col[2] | 0})`;
    ctx.beginPath(); ctx.arc(gx, gy, .75 + 2.75 * e, 0, TAU); ctx.fill();
  }
}
function paint(cv, t) {
  if (!cv) return;
  const ctx = cv.getContext("2d");
  if (!ctx) return;
  if (!Number.isFinite(t)) t = 0;
  const key = cv.dataset.bg, k = cv.width / W;
  const h = k > 0 ? cv.height / k : H;
  const dy = h - H;
  ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.globalAlpha = 1;
  ctx.fillStyle = "#100D1C"; ctx.fillRect(0, 0, cv.width, cv.height);
  if (RINGS[key]) drawRing(ctx, k, t, RINGS[key], h, dy);
  else if (FIELDS[key]) drawField(ctx, k, t, FIELDS[key], h, dy);
  ctx.globalAlpha = 1;
}

const POOL = ["trail", "twin", "twinTR", "hpatches", "hrose", "hdusk"];

function pickIndex(rng, previousIndex) {
  const n = POOL.length;
  const roll = rng || Math.random;
  if (previousIndex == null || previousIndex < 0 || n < 2) {
    const choice = Math.floor(roll() * n);
    return Math.min(n - 1, Math.max(0, choice));
  }
  let choice = Math.floor(roll() * (n - 1));
  if (choice < 0) choice = 0;
  if (choice > n - 2) choice = n - 2;
  if (choice >= previousIndex) choice += 1;
  return choice;
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = { paint, RINGS, FIELDS, POOL, ringCell, pickIndex, W, H };
}
