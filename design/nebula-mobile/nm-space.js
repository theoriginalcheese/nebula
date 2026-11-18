(function () {
  const TAU = Math.PI * 2, W = 402, H = 874;
  const BASE = 'https://cdn.jsdelivr.net/gh/mrdoob/three.js@r160/examples/textures/planets/';
  const S = Math.sin, C = Math.cos;
  const clamp = (v, a, b) => v < a ? a : v > b ? b : v;
  const sstep = (a, b, v) => { const t = clamp((v - a) / (b - a), 0, 1); return t * t * (3 - 2 * t); };
  const hx = s => { const n = parseInt(s.slice(1), 16); return [n >> 16, (n >> 8) & 255, n & 255]; };
  const lerp = (a, b, t) => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];
  const ramp = (P, v) => { v = clamp(v, 0, .9999) * (P.length - 1); const i = v | 0; return lerp(P[i], P[i + 1], v - i); };

  /* ---------- noise ---------- */
  function h3(i, j, k, s) { let h = (i * 374761393 + j * 668265263 + k * 2147483647 + s * 1274126177) | 0; h = Math.imul(h ^ (h >>> 13), 1274126177); return ((h ^ (h >>> 16)) >>> 0) / 4294967295; }
  function vn(x, y, z, s) {
    const i = Math.floor(x), j = Math.floor(y), k = Math.floor(z), fx = x - i, fy = y - j, fz = z - k;
    const u = fx * fx * (3 - 2 * fx), v = fy * fy * (3 - 2 * fy), w = fz * fz * (3 - 2 * fz);
    const a = h3(i, j, k, s), b = h3(i + 1, j, k, s), c = h3(i, j + 1, k, s), d = h3(i + 1, j + 1, k, s);
    const e = h3(i, j, k + 1, s), f = h3(i + 1, j, k + 1, s), g = h3(i, j + 1, k + 1, s), hh = h3(i + 1, j + 1, k + 1, s);
    const x1 = a + (b - a) * u, x2 = c + (d - c) * u, x3 = e + (f - e) * u, x4 = g + (hh - g) * u;
    const y1 = x1 + (x2 - x1) * v, y2 = x3 + (x4 - x3) * v; return y1 + (y2 - y1) * w;
  }
  function fbm(x, y, z, s, o) { let a = .5, t = 0, n = 0; for (let i = 0; i < o; i++) { t += a * vn(x, y, z, s + i * 17); n += a; x *= 2.03; y *= 2.03; z *= 2.03; a *= .5; } return t / n; }

  /* ---------- textures ---------- */
  const TW = 1024, TH = 512;
  const tex = {};
  function loadTex(name, file) {
    return new Promise(res => {
      const im = new Image(); im.crossOrigin = 'anonymous';
      im.onload = () => { try { const c = document.createElement('canvas'); c.width = TW; c.height = TH; const x = c.getContext('2d'); x.drawImage(im, 0, 0, TW, TH); tex[name] = { w: TW, h: TH, d: x.getImageData(0, 0, TW, TH).data }; } catch (e) {} res(); };
      im.onerror = () => res(); im.src = BASE + file;
    });
  }
  const ready = Promise.all([loadTex('day', 'earth_atmos_2048.jpg'), loadTex('night', 'earth_lights_2048.png'), loadTex('clouds', 'earth_clouds_1024.png'), loadTex('moon', 'moon_1024.jpg')]);

  const PAL_GAS = [
    ['#1E1638', '#4B3A8F', '#8B7CF6', '#C9B8FF', '#F2D2A4', '#9A6FC0', '#2E2458'],
    ['#14223A', '#2F5E96', '#7FB2D8', '#E3E6E0', '#C8A882', '#3A4C7A', '#172238'],
    ['#2A1426', '#7A3A5E', '#D471E0', '#F2C2A0', '#FFE8D0', '#A0506E', '#2A1426'],
    ['#0F2426', '#21706E', '#7FD3C4', '#E6F0E0', '#B9AEF9', '#3A4F86', '#121C30'],
    ['#2B1C10', '#7A4E2A', '#C99560', '#F0D9B0', '#E9B872', '#8C5A3A', '#24160E']
  ].map(p => p.map(hx));
  const PAL_ROCK = [
    ['#120E18', '#3B2F4A', '#6E5E7E', '#A898B0', '#E2D8E8'],
    ['#1A100C', '#5A3422', '#A0603A', '#D8A070', '#F2DCC0'],
    ['#0C1418', '#24404A', '#4E7A84', '#9CC4C8', '#EAF4F2'],
    ['#140C10', '#4A1E26', '#8E3A3A', '#D98A5A', '#FFD9A8']
  ].map(p => p.map(hx));
  const SYL = ['Ves', 'Tha', 'Ori', 'Kae', 'Nyx', 'Lum', 'Seren', 'Aru', 'Volo', 'Iri', 'Meka', 'Zan', 'Cal', 'Eos'];
  function genPlanet(seed) {
    let s = seed * 9301 + 49297; const rnd = () => (s = (s * 16807) % 2147483647) / 2147483647;
    for (let i = 0; i < 4; i++) rnd();
    const gas = rnd() < .6, P = gas ? PAL_GAS[(rnd() * PAL_GAS.length) | 0] : PAL_ROCK[(rnd() * PAL_ROCK.length) | 0];
    const w = 512, h = 256, d = new Uint8ClampedArray(w * h * 4), bands = 6 + rnd() * 10, warp = 1.2 + rnd() * 2.4, sd = (rnd() * 1000) | 0;
    const storms = gas ? Array.from({ length: 1 + (rnd() * 3 | 0) }, () => ({ la: (rnd() - .5) * 1.6, lo: rnd() * TAU, r: .08 + rnd() * .16 })) : [];
    for (let j = 0; j < h; j++) {
      const lat = (.5 - (j + .5) / h) * Math.PI, cl = C(lat), sl = S(lat);
      for (let i = 0; i < w; i++) {
        const lon = (i + .5) / w * TAU, px = cl * C(lon), py = sl, pz = cl * S(lon);
        let col;
        if (gas) {
          const n = fbm(px * 2.2, py * 6, pz * 2.2, sd, 5), t2 = fbm(px * 7, py * 18, pz * 7, sd + 3, 3);
          let v = .5 + .5 * S(lat * bands + (n - .5) * warp * 4) * .8 + (t2 - .5) * .35;
          for (const st of storms) { const dl = (lat - st.la) / st.r, dn = Math.atan2(S(lon - st.lo), C(lon - st.lo)) / (st.r * 2.2), dd = dl * dl + dn * dn; if (dd < 1) v = v + (1 - dd) * (.25 + .2 * S(dd * 12)); }
          col = ramp(P, v);
        } else {
          const n = fbm(px * 2.5, py * 2.5, pz * 2.5, sd, 6), r2 = fbm(px * 9, py * 9, pz * 9, sd + 5, 3);
          let v = n * 1.1 - .05 + (r2 - .5) * .25;
          col = ramp(P, v); const ice = sstep(.78, .9, Math.abs(sl) + (n - .5) * .3); col = lerp(col, P[P.length - 1], ice * .9);
        }
        const k = (j * w + i) * 4; d[k] = col[0]; d[k + 1] = col[1]; d[k + 2] = col[2]; d[k + 3] = 255;
      }
    }
    const name = SYL[(rnd() * SYL.length) | 0] + SYL[(rnd() * SYL.length) | 0].toLowerCase() + ' ' + ['b', 'c', 'd', 'IV', 'VII', 'II'][(rnd() * 6) | 0];
    return { tex: { w, h, d }, gas, name, atm: gas ? lerp(P[2], [140, 124, 246], .5) : [150, 140, 220] };
  }

  /* ---------- sphere renderer ---------- */
  const SC = 1.5, TOP = 618, BW = Math.round(W * SC), BH = Math.round((H - TOP) * SC);
  function geom(R, cap, tilt) {
    const cx = W / 2, cy = H + R - cap, idx = [], NX = [], NY = [], NZ = [], LF = [], VR = [], AA = [];
    const ct = C(tilt), st = S(tilt);
    for (let by = 0; by < BH; by++) for (let bx = 0; bx < BW; bx++) {
      const X = (bx + .5) / SC, Y = TOP + (by + .5) / SC, dx = (X - cx) / R, dy = (Y - cy) / R, r2 = dx * dx + dy * dy;
      if (r2 >= 1) continue;
      const nz = Math.sqrt(1 - r2), nx = dx, ny = -dy;
      const ny2 = ny * ct - nz * st, nz2 = ny * st + nz * ct;
      idx.push(by * BW + bx); NX.push(nx); NY.push(ny); NZ.push(nz);
      LF.push(Math.atan2(nx, nz2) / TAU + .5); VR.push(clamp(.5 - Math.asin(clamp(ny2, -1, 1)) / Math.PI, 0, .9999));
      AA.push(clamp((1 - Math.sqrt(r2)) * R * SC, 0, 1));
    }
    return { cx, cy, R, idx: Int32Array.from(idx), NX: Float32Array.from(NX), NY: Float32Array.from(NY), NZ: Float32Array.from(NZ), LF: Float32Array.from(LF), VR: Float32Array.from(VR), AA: Float32Array.from(AA) };
  }
  const G = { big: geom(560, 236, 1.15), moon: geom(420, 250, 1.0) };
  const bufs = {};
  function buffer(key) { if (!bufs[key]) { const c = document.createElement('canvas'); c.width = BW; c.height = BH; const x = c.getContext('2d'); bufs[key] = { c, x, im: x.createImageData(BW, BH) }; } return bufs[key]; }
  function norm(v) { const l = Math.hypot(v[0], v[1], v[2]); return [v[0] / l, v[1] / l, v[2] / l]; }

  function renderSphere(key, g, o) {
    const B = buffer(key); if (B.rot === o.rot && B.tk === o.tex) return B.c; B.rot = o.rot; B.tk = o.tex; const d = B.im.data; d.fill(0);
    const T = o.tex, tw = T.w, th = T.h, td = T.d, N = o.night, Cl = o.clouds, L = o.L, atm = o.atm;
    for (let p = 0; p < g.idx.length; p++) {
      const k = g.idx[p] * 4, nx = g.NX[p], ny = g.NY[p], nz = g.NZ[p];
      const dot = nx * L[0] + ny * L[1] + nz * L[2], diff = dot > 0 ? dot : 0, day = sstep(-.1, .28, dot);
      let u = g.LF[p] + o.rot; u -= Math.floor(u);
      const tx = (u * tw) | 0, ty = (g.VR[p] * th) | 0, ti = (ty * tw + tx) * 4;
      const amb = o.amb || .015;
      let r = td[ti] * (amb + 1.15 * diff), gg = td[ti + 1] * (amb + 1.15 * diff), b = td[ti + 2] * (amb + 1.15 * diff);
      if (N) { const ni = (((g.VR[p] * N.h) | 0) * N.w + ((u * N.w) | 0)) * 4, nl = N.d[ni] / 255 * Math.pow(1 - day, 2) * 1.6; r += 255 * nl; gg += 205 * nl; b += 140 * nl; }
      if (Cl) { let u2 = g.LF[p] + o.rot * 1.25 + .1; u2 -= Math.floor(u2); const ci = (((g.VR[p] * Cl.h) | 0) * Cl.w + ((u2 * Cl.w) | 0)) * 4, ca = Cl.d[ci] / 255 * (Cl.d[ci + 3] / 255) * .9, cl = 245 * (.02 + diff * 1.05); r = r * (1 - ca) + cl * ca; gg = gg * (1 - ca) + cl * ca; b = b * (1 - ca) + (cl + 8) * ca; }
      const f = Math.pow(1 - nz, 2.6) * (o.atmK == null ? 1 : o.atmK), a = f * (.12 + .95 * day);
      r += atm[0] * a; gg += atm[1] * a; b += atm[2] * a;
      if (o.spec && N) { const hv = norm([L[0], L[1], L[2] + 1]), sp = Math.pow(Math.max(0, nx * hv[0] + ny * hv[1] + nz * hv[2]), 60) * (td[ti + 2] > td[ti] + 10 ? .9 : .1); r += 255 * sp; gg += 236 * sp; b += 210 * sp; }
      d[k] = r; d[k + 1] = gg; d[k + 2] = b; d[k + 3] = 255 * g.AA[p];
    }
    B.x.putImageData(B.im, 0, 0); return B.c;
  }

  /* ---------- space backdrop ---------- */
  let s0 = 11; const rnd0 = () => (s0 = (s0 * 16807) % 2147483647) / 2147483647;
  const STARS = Array.from({ length: 190 }, () => [rnd0(), rnd0(), .35 + rnd0() * rnd0() * 1.5, rnd0() * TAU, .3 + rnd0()]);
  function glow(x, cx, cy, r, col, a) { const g = x.createRadialGradient(cx, cy, 0, cx, cy, r); g.addColorStop(0, `rgba(${col},${a})`); g.addColorStop(.5, `rgba(${col},${a * .35})`); g.addColorStop(1, `rgba(${col},0)`); x.fillStyle = g; x.fillRect(0, 0, W, H); }
  function space(x, t, o) {
    o = o || {};
    x.fillStyle = '#06050C'; x.fillRect(0, 0, W, H);
    x.save(); x.translate(W * .55, H * (o.bandY || .38)); x.rotate(-.9 + S(t * .02) * .03); x.scale(1, .2);
    let g = x.createRadialGradient(0, 0, 0, 0, 0, H * .75); g.addColorStop(0, 'rgba(150,130,255,.34)'); g.addColorStop(.3, 'rgba(120,96,230,.16)'); g.addColorStop(.6, 'rgba(212,113,224,.05)'); g.addColorStop(1, 'rgba(90,70,200,0)');
    x.fillStyle = g; x.fillRect(-H, -H, H * 2, H * 2);
    g = x.createRadialGradient(-30, 10, 0, -30, 10, H * .3); g.addColorStop(0, 'rgba(255,232,200,.10)'); g.addColorStop(1, 'rgba(255,232,200,0)'); x.fillStyle = g; x.fillRect(-H, -H, H * 2, H * 2);
    x.restore();
    for (const s of STARS) {
      const px = ((s[0] * W + t * s[4] * 1.4) % W + W) % W, py = s[1] * H;
      const tw = .5 + .5 * S(t * (.5 + s[4]) + s[3]), a = .2 + .65 * tw;
      x.fillStyle = s[2] > 1.4 ? `rgba(255,236,206,${a})` : `rgba(228,224,255,${a})`;
      x.beginPath(); x.arc(px, py, s[2] * .75, 0, TAU); x.fill();
      if (s[2] > 1.55) { x.fillStyle = `rgba(228,224,255,${a * .25})`; x.fillRect(px - 4, py - .25, 8, .5); x.fillRect(px - .25, py - 4, .5, 8); }
    }
  }
  function planetScene(x, t, key, g, o, rimCol) {
    space(x, t, o);
    const L = o.L, ang = Math.atan2(L[1], L[0]), b = .86 + .14 * S(t * .4);
    const lx = g.cx + g.R * C(ang), ly = g.cy - g.R * S(ang);
    let gr = x.createRadialGradient(g.cx, g.cy, g.R * .98, g.cx, g.cy, g.R * 1.32);
    gr.addColorStop(0, `rgba(${o.atm.map(v => v | 0).join(',')},${.32 * b})`); gr.addColorStop(.25, `rgba(${o.atm.map(v => v | 0).join(',')},${.1 * b})`); gr.addColorStop(1, 'rgba(0,0,0,0)');
    x.fillStyle = gr; x.fillRect(0, 0, W, H);
    x.globalCompositeOperation = 'screen'; glow(x, lx, ly, W * .7, rimCol, .4 * b); glow(x, lx, ly, W * .22, '255,240,220', .35 * b); x.globalCompositeOperation = 'source-over';
    const cv = renderSphere(key, g, o);
    x.drawImage(cv, 0, TOP, W, H - TOP);
    const lg = x.createLinearGradient(lx - W * .6, ly, lx + W * .6, ly);
    lg.addColorStop(0, 'rgba(160,140,255,0)'); lg.addColorStop(.5, 'rgba(255,244,226,.95)'); lg.addColorStop(1, 'rgba(160,140,255,0)');
    x.save(); x.strokeStyle = lg; x.lineWidth = 1.2; x.shadowColor = `rgba(${rimCol},.9)`; x.shadowBlur = 14; x.beginPath(); x.arc(g.cx, g.cy, g.R, Math.PI * 1.04, Math.PI * 1.96); x.stroke(); x.restore();
  }

    function earthOpts(t) { return { tex: tex.day, night: tex.night, clouds: tex.clouds, L: norm([.62, .5, -.18]), rot: t / 240, atm: [110, 140, 255], spec: true, amb: .02 }; }

  /* ---------- desktop dot field, phone scale ---------- */
  const VIO = hx('#8B7CF6'), MAG = hx('#D471E0'), INK = hx('#F5F3FF'), AMB = hx('#E9B872');
  const CORES = [
    { bx: 300, by: 230, R: 130, ax: 46, ay: 70, px: 21, py: 27, ph: 0, rp: 9, ra: .25 },
    { bx: 100, by: 480, R: 120, ax: -54, ay: 80, px: 25, py: 19, ph: 2.4, rp: 11, ra: .3 },
    { bx: 290, by: 720, R: 140, ax: 50, ay: 56, px: 29, py: 23, ph: 1, rp: 13, ra: .3 },
    { bx: 200, by: 420, R: 70, ax: 130, ay: 230, px: 17, py: 23, ph: 3, rp: 7, ra: .35, w: .85 }
  ];
  function dots(x, t) {
    x.fillStyle = '#100D1C'; x.fillRect(0, 0, W, H);
    const cs = CORES.map(c => ({ x: c.bx + S(TAU * t / c.px + c.ph) * c.ax, y: c.by + S(TAU * t / c.py + c.ph + 1.6) * c.ay, R: c.R * (1 + S(TAU * t / c.rp + c.ph) * c.ra), w: c.w || 1 }));
    const wp = (t % 7) / 7, wr = wp * 760, wa = 1 - wp;
    for (let gy = 4; gy < H; gy += 8) for (let gx = 4; gx < W; gx += 8) {
      let v = 0;
      for (const c of cs) { const dx = Math.abs(gx - c.x), dy = Math.abs(gy - c.y), d = Math.cbrt(dx * dx * dx + dy * dy * dy), q = 1 - d / c.R; if (q > 0) v += c.w * q * q * (3 - 2 * q); }
      const dw = Math.hypot(gx - 201, gy - 300) - wr; v += Math.exp(-dw * dw / 900) * .38 * wa;
      const e = Math.min(1, v);
      let col = e < .55 ? lerp(VIO, MAG, e / .55) : lerp(MAG, INK, (e - .55) / .45);
      if (v > 1.1) col = lerp(col, AMB, Math.min(.7, (v - 1.1) * 1.4));
      x.globalAlpha = .12 + .88 * e; x.fillStyle = `rgb(${col[0] | 0},${col[1] | 0},${col[2] | 0})`;
      x.beginPath(); x.arc(gx, gy, .75 + 2.75 * e, 0, TAU); x.fill();
    }
    x.globalAlpha = 1;
  }

  /* ---------- desktop pixel ring, phone scale ---------- */
  const RC = ['#8B7CF6', '#B9AEF9', '#D471E0', '#E9B872'], RZ = [[0, 1], [1, 2], [2, 3], [0, 2], [3, 0], [1, 2]];
  const rh = (a, b) => { let h = (a * 73856093) ^ (b * 19349663); h = Math.imul(h ^ (h >>> 13), 1274126177); return ((h ^ (h >>> 16)) >>> 0) / 4294967295; };
  const mod = (a, n) => ((a % n) + n) % n, CELL = 4;
  const RINGS = [{ cx: 250, cy: 330, R: 236, rows: 9, rate: 14, pat: 'trail', sy: .36, axis: -20 }, { cx: 250, cy: 330, R: 170, rows: 6, rate: -7, pat: 'blocks', sy: .36, axis: -20, dim: .8 }];
  function cell(g, X, Y, t) {
    let px = X - g.cx, py = Y - g.cy; const a = -g.axis * Math.PI / 180, c = C(a), s = S(a); [px, py] = [px * c - py * s, px * s + py * c]; py /= g.sy;
    const d = Math.hypot(px, py), band = g.rows * CELL, inner = g.R - band / 2; if (d < inner || d >= inner + band) return null;
    const row = Math.floor((d - inner) / CELL), raw = Math.atan2(py, px) * 180 / Math.PI, ang = raw - g.rate * t; let col, al = 1;
    if (g.pat === 'blocks') {
      const N = Math.round(g.R * (40 * Math.PI / 180) / CELL), u = mod(ang, 40) / 40, jm = Math.floor(u * N), zone = Math.floor(u * RZ.length);
      const h1 = rh(Math.floor(jm / 3) * 7 + Math.floor(row / 2) + 11, row + 3), h2 = rh(jm + 5, row * 17 + 1);
      if (((row === 0 || row === g.rows - 1) && h2 < .32) || h2 < .1) return null;
      col = RC[RZ[zone][h1 < .62 ? 0 : 1]];
    } else {
      const u = mod(ang, 120) / 120; if (u < .3) return null;
      const p = (u - .3) / .7, h2 = rh(Math.floor(mod(ang, 360) / 2.4), row + 5); if (h2 > p * 1.15 + .05) return null;
      col = p > .92 ? (h2 < .3 ? '#E9B872' : '#F5F3FF') : p > .7 ? '#B9AEF9' : p > .4 ? '#8B7CF6' : '#D471E0'; al = .3 + .7 * p;
    }
    al *= .35 + .65 * (S(Math.atan2(py, px)) * .5 + .5);
    return [col, al * (g.dim || 1)];
  }
  function ring(x, t) {
    space(x, t, { bandY: .62 });
    glow(x, 250, 330, 260, '139,124,246', .16);
    for (let j = 40; j < 160; j++) for (let i = 0; i < W / CELL; i++) {
      const X = i * CELL + 2, Y = j * CELL + 2; let hit = null;
      for (const g of RINGS) { hit = cell(g, X, Y, t); if (hit) break; }
      if (!hit) continue; x.globalAlpha = hit[1]; x.fillStyle = hit[0]; x.fillRect(i * CELL + .4, j * CELL + .4, CELL - .8, CELL - .8);
    }
    x.globalAlpha = 1;
  }

  /* ---------- live solar system ---------- */
  const PL = [
    ['Mercury', .387, 252.25, 4.09233, 2.2, [184, 176, 170]], ['Venus', .723, 181.98, 1.60213, 3.4, [236, 214, 170]],
    ['Earth', 1, 100.46, .98561, 3.6, [110, 160, 255]], ['Mars', 1.524, 355.45, .52403, 2.8, [226, 120, 80]],
    ['Jupiter', 5.203, 34.40, .08309, 7.5, [222, 190, 150]], ['Saturn', 9.537, 49.94, .03346, 6.4, [233, 210, 160]],
    ['Uranus', 19.19, 313.23, .01173, 4.6, [160, 220, 230]], ['Neptune', 30.07, 304.88, .00598, 4.4, [110, 140, 240]]
  ];
  const J2000 = Date.UTC(2000, 0, 1, 12);
  function solar(x, t) {
    space(x, t, { bandY: .22 });
    const days = (Date.now() - J2000) / 864e5, cx = W * .5, cy = 330, tilt = .34, yaw = t * .012;
    const rad = a => 26 + 58 * Math.sqrt(a);
    for (let i = 0; i < PL.length; i++) {
      const r = rad(PL[i][1]);
      x.strokeStyle = i === 2 ? 'rgba(185,174,249,.42)' : 'rgba(185,174,249,.13)'; x.lineWidth = i === 2 ? 1 : .7;
      x.beginPath(); x.ellipse(cx, cy, r, r * tilt, 0, 0, TAU); x.stroke();
    }
    const P = PL.map((p, i) => { const L = ((p[2] + p[3] * days) % 360) * Math.PI / 180 + yaw, r = rad(p[1]); return { p, i, x: cx + r * C(L), y: cy + r * S(L) * tilt, z: S(L) }; });
    const sun = () => {
      x.globalCompositeOperation = 'screen'; glow(x, cx, cy, 150, '255,190,120', .35); glow(x, cx, cy, 46, '255,236,200', .9); x.globalCompositeOperation = 'source-over';
      const g = x.createRadialGradient(cx - 4, cy - 4, 1, cx, cy, 14); g.addColorStop(0, '#FFF8EA'); g.addColorStop(.6, '#FFD9A0'); g.addColorStop(1, '#F0A860');
      x.fillStyle = g; x.beginPath(); x.arc(cx, cy, 13, 0, TAU); x.fill();
    };
    const body = q => {
      const [name, , , , s, c] = q.p, ang = Math.atan2(cy - q.y, cx - q.x);
      const g = x.createRadialGradient(q.x + C(ang) * s * .5, q.y + S(ang) * s * .5, s * .1, q.x, q.y, s);
      g.addColorStop(0, `rgb(${Math.min(255, c[0] + 40)},${Math.min(255, c[1] + 40)},${Math.min(255, c[2] + 40)})`); g.addColorStop(.55, `rgb(${c[0] * .7 | 0},${c[1] * .7 | 0},${c[2] * .7 | 0})`); g.addColorStop(1, 'rgb(10,8,20)');
      if (name === 'Saturn') { x.strokeStyle = 'rgba(233,210,160,.55)'; x.lineWidth = 1.2; x.beginPath(); x.ellipse(q.x, q.y, s * 2.1, s * .7, -.3, Math.PI, TAU); x.stroke(); }
      x.fillStyle = g; x.beginPath(); x.arc(q.x, q.y, s, 0, TAU); x.fill();
      if (name === 'Saturn') { x.strokeStyle = 'rgba(233,210,160,.7)'; x.beginPath(); x.ellipse(q.x, q.y, s * 2.1, s * .7, -.3, 0, Math.PI); x.stroke(); }
      if (name === 'Earth') { x.strokeStyle = `rgba(255,232,188,${.5 + .4 * S(t * 2)})`; x.lineWidth = 1; x.beginPath(); x.arc(q.x, q.y, s + 5 + 2 * S(t * 2), 0, TAU); x.stroke(); }
      x.font = '600 9px -apple-system, system-ui, sans-serif'; x.letterSpacing = '1.5px'; x.fillStyle = name === 'Earth' ? 'rgba(255,232,188,.95)' : 'rgba(201,196,230,.6)';
      x.fillText((name === 'Earth' ? 'EARTH · YOU' : name.toUpperCase()), q.x + s + 6, q.y + 3);
    };
    P.filter(q => q.z < 0).sort((a, b) => a.z - b.z).forEach(body); sun(); P.filter(q => q.z >= 0).sort((a, b) => a.z - b.z).forEach(body);
    const d = new Date(); x.font = '600 10px -apple-system, system-ui, sans-serif'; x.letterSpacing = '2px'; x.fillStyle = 'rgba(201,196,230,.55)';
    x.fillText('LIVE · ' + d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }).toUpperCase(), 20, 800 - 0);
    x.letterSpacing = '0px';
  }

  /* ---------- pixel variants ---------- */
  const cellFill = (x, i, j, col, a) => { x.globalAlpha = a; x.fillStyle = col; x.fillRect(i * CELL + .4, j * CELL + .4, CELL - .8, CELL - .8); };
  function galaxy(x, t) {
    space(x, t, { bandY: .3 });
    const cx = 210, cy = 700, ax = -24 * Math.PI / 180, ca = C(ax), sa = S(ax), sy = .42;
    glow(x, cx, cy, 260, '139,124,246', .2);
    for (let j = 110; j < H / CELL; j++) for (let i = 0; i < W / CELL; i++) {
      let px = i * CELL + 2 - cx, py = j * CELL + 2 - cy; [px, py] = [px * ca - py * sa, px * sa + py * ca]; py /= sy;
      const r = Math.hypot(px, py); if (r > 300) continue;
      const th = Math.atan2(py, px), arm = C(2 * (th - Math.log(r + 8) * 2.4 + t * .05)), core = Math.exp(-r / 34);
      const v = Math.max(0, arm) * Math.exp(-r / 150) * 1.2 + core * 1.3, h = rh(i, j);
      if (v < .06 || h < .12) continue;
      const col = core > .5 ? (h < .4 ? '#FFE8BC' : '#F5F3FF') : v > .7 ? '#B9AEF9' : r > 150 ? '#D471E0' : '#8B7CF6';
      cellFill(x, i, j, col, sstep(.06, .7, v) * (.5 + .5 * (S(th) * .5 + .5)) * (.75 + .25 * h));
    }
    x.globalAlpha = 1;
  }
  function saturn(x, t) {
    space(x, t, { bandY: .3 });
    const cx = 250, cy = 712, PR = 92, ax = -18 * Math.PI / 180, ca = C(ax), sa = S(ax), sy = .3, BANDS = ['#2E2458', '#4B3A8F', '#8B7CF6', '#B9AEF9', '#E9B872', '#D471E0', '#8B7CF6', '#4B3A8F'];
    glow(x, cx, cy, 260, '139,124,246', .16);
    const ringAt = (i, j, front) => {
      let px = i * CELL + 2 - cx, py = j * CELL + 2 - cy; [px, py] = [px * ca - py * sa, px * sa + py * ca];
      if (front ? py < 0 : py >= 0) return null; py /= sy; const r = Math.hypot(px, py);
      if (r < 124 || r > 214 || (r > 168 && r < 177)) return null;
      const ang = Math.atan2(py, px) * 180 / Math.PI - t * 9, seg = Math.floor(mod(ang, 360) / 3), h = rh(seg, Math.floor(r / 4));
      if (h < .18) return null;
      return [r < 168 ? (h > .85 ? '#E9B872' : '#B9AEF9') : (h > .8 ? '#D471E0' : '#8B7CF6'), (r < 168 ? .85 : .55) * (front ? 1 : .6)];
    };
    for (const pass of [0, 1, 2]) for (let j = 140; j < H / CELL; j++) for (let i = 0; i < W / CELL; i++) {
      if (pass === 1) {
        const X = i * CELL + 2 - cx, Y = j * CELL + 2 - cy, d = Math.hypot(X, Y); if (d > PR) continue;
        let lat = Y * ca - X * sa; const band = Math.floor((lat / PR + 1) * 6 + .6 * S((X * ca + Y * sa) / 18 + t * .5 + lat / 9));
        const sh = Math.max(.15, Math.min(1, .35 + (-X / PR) * .5 + (1 - d / PR) * .5));
        cellFill(x, i, j, BANDS[mod(band, BANDS.length)], sh);
      } else { const h = ringAt(i, j, pass === 2); if (h) cellFill(x, i, j, h[0], h[1]); }
    }
    x.globalAlpha = 1;
  }
  const BAYER = [0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5];
  const DPAL = ['#100D1C', '#2E2458', '#4B3A8F', '#8B7CF6', '#D471E0', '#F2D2A4'];
  function dither(x, t) {
    x.fillStyle = '#0B0916'; x.fillRect(0, 0, W, H);
    const z = t * .05;
    for (let j = 0; j < H / CELL; j++) for (let i = 0; i < W / CELL; i++) {
      const X = i / 26, Y = j / 26;
      const wx = fbm(X + z, Y, z, 3, 2), v = fbm(X + wx * 1.6, Y - z * 1.4, z * .7, 9, 3);
      let e = (v - .38) * 2.6 - j / (H / CELL) * .35 + (1 - Math.abs(i / (W / CELL) - .62) * 1.4) * .25; if (e <= 0) continue;
      const lv = e * (DPAL.length - 1), k = Math.floor(lv), f = lv - k, b = BAYER[(j & 3) * 4 + (i & 3)] / 16;
      const idx = Math.min(DPAL.length - 1, k + (f > b ? 1 : 0)); if (idx === 0) continue;
      cellFill(x, i, j, DPAL[idx], 1);
    }
    x.globalAlpha = 1;
  }

  /* ---------- public ---------- */
  function draw(kind, x, t, seed) {
    if (kind === 'earth') {
      if (!tex.day) { const p = getProc(3); planetScene(x, t, 'earthF', G.big, { tex: p.tex, L: norm([.62, .5, -.18]), rot: t / 240, atm: [110, 140, 255] }, '255,210,160'); return; }
      planetScene(x, t, 'earth', G.big, earthOpts(t), '255,206,150');
    } else if (kind === 'proc') {
      const p = getProc(seed);
      planetScene(x, t, 'proc', G.big, { tex: p.tex, L: norm([-.45, .55, .5]), rot: t / 180, atm: p.atm, atmK: 1.2, amb: .03 }, '200,184,255');
    } else if (kind === 'moon') {
      if (!tex.moon) { space(x, t, {}); return; }
      planetScene(x, t, 'moon', G.moon, { tex: tex.moon, L: norm([.78, .5, .05]), rot: t / 300, atm: [60, 50, 110], atmK: .4, amb: .01 }, '255,226,180');
    } else if (kind === 'dots') dots(x, t);
    else if (kind === 'ring') ring(x, t);
    else if (kind === 'solar') solar(x, t);
    else if (kind === 'galaxy') galaxy(x, t);
    else if (kind === 'saturn') saturn(x, t);
    else if (kind === 'dither') dither(x, t);
  }
  const procs = {}; function getProc(seed) { return procs[seed] || (procs[seed] = genPlanet(seed)); }
  window.NMSpace = { draw, ready, W, H, name: seed => getProc(seed).name };
})();
