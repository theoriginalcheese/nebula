/* Break the v4 canvas painter. Run: node tests/test_dial_bg.js */
const path = require("path");
const bg = require(path.join(__dirname, "..", "spike", "web", "dial-bg.js"));

let failed = 0;
function check(name, ok, extra) {
  if (ok) return;
  failed += 1;
  console.error("FAIL", name, extra === undefined ? "" : extra);
}

function mockCanvas(key, w) {
  const calls = [];
  const ctx = {
    imageSmoothingEnabled: true,
    globalAlpha: 1,
    fillStyle: "",
    setTransform() {},
    fillRect(x, y, rw, rh) {
      calls.push({ op: "rect", x, y, w: rw, h: rh, a: this.globalAlpha, s: this.fillStyle });
    },
    beginPath() {},
    arc(x, y, r) {
      calls.push({ op: "arc", x, y, r, a: this.globalAlpha, s: this.fillStyle });
    },
    fill() {},
  };
  return {
    width: w || 628,
    height: Math.round((w || 628) * 154 / 314),
    dataset: { bg: key },
    getContext() { return ctx; },
    calls,
  };
}

function paintAll(key, t) {
  const cv = mockCanvas(key);
  bg.paint(cv, t);
  return cv.calls;
}

const keys = Object.keys(bg.RINGS).concat(Object.keys(bg.FIELDS));
for (const key of keys) {
  for (const t of [0, 8, 16, -4, 1e12]) {
    let threw = false;
    try { paintAll(key, t); } catch (err) { threw = err; }
    check(key + " at " + t + " does not throw", !threw, threw && threw.message);
  }
}

check("unknown key does not throw", (() => {
  try { paintAll("nope", 1); return true; } catch (e) { return false; }
})());
check("null context does not throw", (() => {
  try { bg.paint({ width: 628, dataset: {}, getContext() { return null; } }, 1); return true; }
  catch (e) { return false; }
})());
check("NaN time does not throw", (() => {
  try { paintAll("trail", NaN); return true; } catch (e) { return false; }
})());

const trail = paintAll("trail", 4).filter((c) => c.op === "rect" && c.s !== "#100D1C");
check("trail draws squares", trail.length > 20, trail.length);
check("trail squares have area", trail.every((c) => c.w > 0 && c.h > 0));
check("trail alpha stays in range", trail.every((c) => c.a > 0 && c.a <= 1));
check("the ring stays in the right half",
  trail.every((c) => c.x >= 400), trail.map((c) => c.x).slice(0, 4));
for (const key of ["twin", "twinTR"]) {
  const squares = paintAll(key, 4).filter((c) => c.op === "rect" && c.s !== "#100D1C");
  check(key + " stays in the right half", squares.length > 20 && squares.every((c) => c.x >= 400));
}

const moved = paintAll("trail", 22).filter((c) => c.op === "rect" && c.s !== "#100D1C");
const sig = (rows) => rows.map((c) => c.x + "," + c.y + ":" + c.s).join("|");
check("the ring has travelled", sig(trail) !== sig(moved));

function mockTall(key) {
  const cv = mockCanvas(key, 628);
  cv.height = Math.round(628 * 230 / 314);
  return cv;
}
const tallTrail = (() => {
  const cv = mockTall("trail");
  bg.paint(cv, 4);
  return cv.calls.filter((c) => c.op === "rect" && c.s !== "#100D1C");
})();
check("a tall panel still draws the ring", tallTrail.length > 20, tallTrail.length);
check("the ring follows the taller corner",
  tallTrail.some((c) => c.y > 320),
  tallTrail.reduce((m, c) => Math.max(m, c.y), 0));

for (const key of Object.keys(bg.FIELDS)) {
  const a = paintAll(key, 0).filter((c) => c.op === "arc");
  const b = paintAll(key, 10).filter((c) => c.op === "arc");
  check(key + " keeps the dot grid", a.length === b.length && a.length > 10
    && a.every((c, i) => c.x === b[i].x && c.y === b[i].y));
  check(key + " dots stay a positive size", a.every((c) => c.r > 0));
  check(key + " dot alpha stays in range", a.every((c) => c.a >= 0 && c.a <= 1));
  check(key + " colour is an rgb triple", a.every((c) => /^rgb\(\d+,\d+,\d+\)$/.test(c.s)));
  const look = (rows) => rows.map((c) => c.r.toFixed(3) + c.s).join("");
  check(key + " melts between frames", look(a) !== look(b));
}

check("pool is the six likes", bg.POOL.join() === "trail,twin,twinTR,hpatches,hrose,hdusk");
for (let prev = 0; prev < bg.POOL.length; prev++) {
  const zero = bg.pickIndex(() => 0, prev);
  const almost = bg.pickIndex(() => 0.999999, prev);
  check("js roll stays off the previous", zero !== prev && almost !== prev, [prev, zero, almost]);
  check("js roll stays inside the pool", zero >= 0 && zero < 6 && almost >= 0 && almost < 6);
}
check("js 1.0 roll stays inside", bg.pickIndex(() => 1, 5) !== 5 && bg.pickIndex(() => 1, 5) < 6);
check("js negative roll stays inside", bg.pickIndex(() => -1, 0) >= 0);

if (failed) {
  console.error(failed + " failed");
  process.exit(1);
}
console.log("painter break pass ok");
