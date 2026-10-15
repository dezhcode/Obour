/* بیلیارد — همان فیزیک و قواعد game_club/billiard.py در مرورگر.
   فقط برای حالت نمایشی بیرون از تلگرام (demo-billiard.js) و پیش بینی خط نشانه؛
   داخل تلگرام همه چیز (ضربه، افتادن توپ، خطا، برد) روی سرور حساب می شود. */
(() => {
const W = 834, H = 1516, R = 20, D = 40, HEAD = 1099;
const MIN_X = 97, MAX_X = 737, MIN_Y = 97, MAX_Y = 1419, BREAK_MIN_Y = HEAD + R;
const CUE_START = [W / 2 - 5, HEAD + R], FOOT = [W - 418, H / 2];
const DAMP = .625, D_AXIS = .94, D_CROSS = .41, D_CLAMP = 1650, D_DIV = 3500;
const MAT_BALL = [0, .99], MAT_RAIL = [.1, .95], MAT_MOUTH = [.8, .2], INV_I = 1 / (R * R);
const STEP_SHOT = [.01111, 10], STEP_BREAK = [.0093, 2], DC = 1 / 120;
const IMPULSE = 2375, SPIN_ANG = 250, SPIN_MAX = Math.PI / 6, MIN_POWER = .02, BREAK_MIN = .35;
const BREAK_BONUS = 1.25, BREAK_RAND = .15, BREAK_JIT = .3 * Math.PI / 180;
const SPIN_K = .003, SPIN_DAMP = .99, SPIN_DAMP_HIT = .97, SPIN_GAIN = 10;
const POCKET_MAX_V = 550, POCKET_FORCE = 3.8, SENSOR = .49, SINK_TIME = .55, SINK_PULL = 60, SINK_DRAG = 5;
const SLEEP_V = 10, SLEEP_T = .2, MAX_SIM = 25, FPS = 30;
// جیب: [x، y، شعاع، مرکز سوراخ x، y]
const POCKETS = [[49, 47, 70, 63, 63], [W - 49, 47, 70, W - 63, 63], [49, H - 47, 70, 63, H - 63], [W - 49, H - 47, 70, W - 63, H - 63],
  [21, H / 2, 60, 50, H / 2], [W - 21, H / 2, 60, W - 50, H / 2]];
const RAILS = [
  [[0, 116], [[0, 0], [60, 0], [76, 15], [76, 598], [65, 602], [0, 602]]],
  [[0, 798], [[0, 0], [65, 0], [76, 4], [76, 587], [60, 602], [0, 602]]],
  [[773, 116], [[0, 0], [60, 0], [60, 602], [-5, 602], [-16, 598], [-16, 15]]],
  [[777, 798], [[0, 0], [56, 0], [56, 602], [-4, 602], [-20, 587], [-20, 4]]],
  [[116, 0], [[0, 0], [599, 0], [599, 61], [585, 77], [14, 77], [0, 61]]],
  [[130, 1438], [[0, 0], [571, 0], [585, 16], [585, 77], [-14, 77], [-14, 16]]],
];
const MOUTHS = [
  [[0, 0], [[0, 0], [115, 0], [115, 58], [101, 43], [93, 35], [88, 32], [82, 28], [72, 25], [57, 24], [47, 28], [38, 33], [28, 45], [25, 51], [24, 56], [24, 71], [27, 80], [35, 91], [58, 114], [58, 116], [0, 116]]],
  [[833, 0], [[0, 0], [0, 116], [-58, 116], [-58, 114], [-35, 91], [-27, 80], [-24, 71], [-24, 56], [-25, 51], [-28, 45], [-38, 33], [-47, 28], [-57, 24], [-72, 25], [-82, 28], [-88, 32], [-93, 35], [-101, 43], [-115, 58], [-115, 0]]],
  [[0, 1515], [[0, 0], [0, -116], [58, -116], [58, -114], [35, -91], [27, -80], [24, -71], [24, -56], [25, -51], [28, -45], [38, -33], [47, -28], [57, -24], [72, -25], [82, -28], [88, -32], [93, -35], [101, -43], [115, -58], [115, 0]]],
  [[833, 1515], [[0, 0], [-115, 0], [-115, -58], [-101, -43], [-93, -35], [-88, -32], [-82, -28], [-72, -25], [-57, -24], [-47, -28], [-38, -33], [-28, -45], [-25, -51], [-24, -56], [-24, -71], [-27, -80], [-35, -91], [-58, -114], [-58, -116], [0, -116]]],
  [[-20, 710], [[-20, 0], [58, 0], [58, 8], [48, 8], [38, 10], [32, 13], [25, 18], [20, 25], [15, 36], [13, 44], [13, 51], [16, 62], [20, 70], [27, 78], [34, 83], [47, 87], [58, 87], [58, 95], [-20, 95]]],
  [[853, 710], [[20, 0], [20, 95], [-58, 95], [-58, 87], [-47, 87], [-34, 83], [-27, 78], [-20, 70], [-16, 62], [-13, 51], [-13, 44], [-15, 36], [-20, 25], [-25, 18], [-32, 13], [-38, 10], [-48, 8], [-58, 8], [-58, 0]]],
];
const RAIL = 0, MOUTH = 1;
function edges(polys, kind) {
  const out = [];
  for (const [[px, py], path] of polys) {
    const ox = px - path[0][0], oy = py - path[0][1];
    let v = path.map(([x, y]) => [ox + x, oy + y]), area = 0;
    for (let i = 0, j = v.length - 1; i < v.length; j = i++) area += v[j][0] * v[i][1] - v[i][0] * v[j][1];
    if (area < 0) v = v.reverse();
    for (let i = 0; i < v.length; i++) {
      const [ax, ay] = v[i], [bx, by] = v[(i + 1) % v.length], ln = Math.hypot(bx - ax, by - ay);
      if (ln > 1e-9) out.push([ax, ay, bx, by, (by - ay) / ln, -(bx - ax) / ln, kind]);
    }
  }
  return out;
}
const EDGES = edges(RAILS, RAIL).concat(edges(MOUTHS, MOUTH));
const CELL = 40;
function grid(es) {
  const g = new Map();
  for (const e of es) {
    const x0 = Math.min(e[0], e[2]) - R - 2, x1 = Math.max(e[0], e[2]) + R + 2, y0 = Math.min(e[1], e[3]) - R - 2, y1 = Math.max(e[1], e[3]) + R + 2;
    for (let cx = Math.floor(x0 / CELL); cx <= Math.floor(x1 / CELL); cx++) for (let cy = Math.floor(y0 / CELL); cy <= Math.floor(y1 / CELL); cy++) {
      const k = cx * 10000 + cy; if (!g.has(k)) g.set(k, []); g.get(k).push(e);
    }
  }
  return g;
}
const GRID_ALL = grid(EDGES), GRID_MOUTH = grid(EDGES.filter(e => e[6] === MOUTH));

function mkBall(n, x, y) { return { n, x, y, vx: 0, vy: 0, w: 0, sx: 0, sy: 0, sd: SPIN_DAMP, first: -1, firstDone: false, rail: false, sink: null, sinkT: 0, capT: 0, potted: false, sleepT: 0, asleep: false }; }
function damping(b, dt) {
  const ax = Math.abs(b.vx), ay = Math.abs(b.vy);
  let o = ax > ay ? ax * D_AXIS + ay * D_CROSS : ay * D_AXIS + ax * D_CROSS; if (o > D_CLAMP) o = D_CLAMP;
  const a = (1 - DAMP) * (1 + o / D_DIV), fa = Math.pow(a, dt);
  b.vx *= fa; b.vy *= fa; b.w *= Math.pow(a, dt);
}
function spinStep(b, dt) {
  if (b.sx === 0 && b.sy === 0) return;
  const v = Math.hypot(b.vx, b.vy), k = (D * SPIN_K) / Math.max(1, Math.min(10, v / 100)), ax = b.sx * k, ay = b.sy * k;
  if (ax * ax + ay * ay > 1) { b.vx += ax; b.vy += ay; }
  const sc = Math.pow(b.sd, dt / DC); b.sx *= sc; b.sy *= sc;
}
function ballIn(b, p) {
  const d = Math.hypot(p[0] - b.x, p[1] - b.y), cap = p[2] - R;
  if (d < cap * .25) return true;
  return Math.hypot(b.vx, b.vy) <= POCKET_MAX_V && d < cap;
}
function contacts(balls) {
  const out = [], live = balls.filter(b => !b.potted);
  for (let i = 0; i < live.length; i++) {
    const a = live[i], g = a.sink ? GRID_MOUTH : GRID_ALL;
    if (!a.sink) for (let j = i + 1; j < live.length; j++) {
      const b = live[j]; if (b.sink) continue;
      const dx = b.x - a.x, dy = b.y - a.y;
      if (dx > D || dx < -D || dy > D || dy < -D) continue;
      const d2 = dx * dx + dy * dy; if (d2 >= D * D) continue;
      let d = Math.sqrt(d2), nx, ny;
      if (d > 1e-9) { nx = dx / d; ny = dy / d; } else { nx = 1; ny = 0; d = 0; }
      out.push({ a, b, nx, ny, pen: D - d, e: MAT_BALL[1], mu: MAT_BALL[0], kind: 2 });
    }
    const es = g.get(Math.floor(a.x / CELL) * 10000 + Math.floor(a.y / CELL)); if (!es) continue;
    for (const [ax, ay, bx, by, enx, eny, kind] of es) {
      const ex = bx - ax, ey = by - ay, l2 = ex * ex + ey * ey;
      let t = l2 > 0 ? ((a.x - ax) * ex + (a.y - ay) * ey) / l2 : 0; t = t < 0 ? 0 : t > 1 ? 1 : t;
      const dx = ax + ex * t - a.x, dy = ay + ey * t - a.y, d2 = dx * dx + dy * dy;
      if (d2 >= R * R) continue;
      let d = Math.sqrt(d2), nx, ny;
      if (d > 1e-9) { nx = dx / d; ny = dy / d; } else { nx = -enx; ny = -eny; d = 0; }
      const m = kind === RAIL ? MAT_RAIL : MAT_MOUTH;
      out.push({ a, b: null, nx, ny, pen: R - d, e: m[1], mu: m[0], kind });
    }
  }
  return out;
}
function solve(cs, iters) {
  for (const c of cs) {
    const bvx = c.b ? c.b.vx : 0, bvy = c.b ? c.b.vy : 0;
    c.vn0 = (bvx - c.a.vx) * c.nx + (bvy - c.a.vy) * c.ny; c.target = c.vn0 < -1e-4 ? -c.e * c.vn0 : 0; c.pn = 0; c.pt = 0;
  }
  for (let it = 0; it < iters; it++) for (const c of cs) {
    const { a, b, nx, ny } = c, tx = -ny, ty = nx;
    const vn = ((b ? b.vx : 0) - a.vx) * nx + ((b ? b.vy : 0) - a.vy) * ny, kn = b ? 2 : 1;
    let pn = c.pn + (c.target - vn) / kn; if (pn < 0) pn = 0;
    const dp = pn - c.pn; c.pn = pn;
    a.vx -= nx * dp; a.vy -= ny * dp; if (b) { b.vx += nx * dp; b.vy += ny * dp; }
    if (c.mu > 0) {
      const sa = (nx * ty - ny * tx) * R;
      const vt = ((b ? b.vx : 0) - a.vx) * tx + ((b ? b.vy : 0) - a.vy) * ty + (b ? b.w * -sa : 0) - a.w * sa;
      const kt = kn + INV_I * sa * sa * (b ? 2 : 1), mx = c.mu * c.pn;
      let pt = c.pt - vt / kt; pt = pt > mx ? mx : pt < -mx ? -mx : pt;
      const d = pt - c.pt; c.pt = pt;
      a.vx -= tx * d; a.vy -= ty * d; a.w -= INV_I * d * sa;
      if (b) { b.vx += tx * d; b.vy += ty * d; b.w += INV_I * d * sa; }
    }
  }
  for (const c of cs) {
    const pen = c.pen - .02; if (pen <= 0) continue;
    const corr = pen * .9 / (c.b ? 2 : 1);
    c.a.x -= c.nx * corr; c.a.y -= c.ny * corr; if (c.b) { c.b.x += c.nx * corr; c.b.y += c.ny * corr; }
  }
}
function hitBall(b, other) {
  if (b.first === -1) b.first = other;
  if (!b.firstDone && b.sd === SPIN_DAMP) { b.firstDone = true; b.sd = SPIN_DAMP_HIT; b.vx += b.sx * SPIN_K * SPIN_GAIN; b.vy += b.sy * SPIN_K * SPIN_GAIN; }
}
function sinkStep(b, h) {
  const p = b.sink; b.sinkT += h;
  b.vx += (p[3] - b.x) * SINK_PULL * h; b.vy += (p[4] - b.y) * SINK_PULL * h;
  const k = Math.exp(-SINK_DRAG * h); b.vx *= k; b.vy *= k;
  const dx = p[3] - b.x, dy = p[4] - b.y, settled = dx * dx + dy * dy < 9 && b.vx * b.vx + b.vy * b.vy < 625;
  return b.sinkT >= SINK_TIME || (settled && b.sinkT > .18);
}

/* simulate: همان خروجی سرور (فریم ها با ids، توپ های افتاده، برخورد اول، ریل ها، صداها) */
function simulate(pos, angle, power, spin, breaking) {
  const balls = []; pos.forEach((p, n) => { if (p) balls.push(mkBall(n, p[0], p[1])); });
  const cue = balls.find(b => b.n === 0), nx = Math.cos(angle), ny = Math.sin(angle), imp = power * IMPULSE;
  if (spin[1]) { cue.sx = nx * spin[1] * power * SPIN_ANG; cue.sy = ny * spin[1] * power * SPIN_ANG; }
  cue.vx = nx * imp; cue.vy = ny * imp;
  if (spin[0]) { const s = angle + spin[0] * SPIN_MAX, px = Math.cos(s) * R, py = Math.sin(s) * R; cue.w = (px * ny * imp - py * nx * imp) * INV_I; }
  const [step, iters] = breaking ? STEP_BREAK : STEP_SHOT;
  let t = 0, nextF = 1 / FPS;
  const frames = [], pots = [], hits = [], moved = new Set([0]);
  const frame = () => { const f = []; for (const b of balls) { if (b.potted) f.push(-1, -1); else f.push(Math.round(b.x), Math.round(b.y)); } frames.push(f); };
  const moving = () => balls.some(b => !b.potted && (b.sink || (b.vx * b.vx + b.vy * b.vy >= SLEEP_V * SLEEP_V) || (!b.asleep && (b.vx || b.vy))));
  frame();
  while (t < MAX_SIM && moving()) {
    let vmax = 0; for (const b of balls) if (!b.potted) vmax = Math.max(vmax, Math.hypot(b.vx, b.vy));
    const n = Math.max(1, Math.min(16, Math.ceil(vmax * step / (R * .25)))), h = step / n;
    for (let s = 0; s < n; s++) {
      t += h;
      for (const b of balls) {
        if (b.potted || b.sink) continue;
        for (let pi = 0; pi < POCKETS.length; pi++) {
          const p = POCKETS[pi], dx = p[0] - b.x, dy = p[1] - b.y;
          if (dx * dx + dy * dy >= (p[2] + R * SENSOR) ** 2) continue;
          if (ballIn(b, p)) { b.sink = p.concat([pi]); b.sinkT = 0; b.capT = t; b.rail = false; break; }
          b.vx += dx * POCKET_FORCE * h; b.vy += dy * POCKET_FORCE * h;
        }
      }
      for (const b of balls) if (!b.potted && !b.sink && !b.asleep) damping(b, h);
      const cs = contacts(balls);
      if (cs.length) {
        solve(cs, iters);
        for (const c of cs) {
          if (!(c.pn > 0 && c.vn0 < -1)) continue;
          if (c.b) {
            hitBall(c.a, c.b.n); hitBall(c.b, c.a.n); c.a.asleep = c.b.asleep = false; moved.add(c.a.n); moved.add(c.b.n);
            if (c.vn0 < -60 && hits.length < 48) hits.push([+t.toFixed(2), 'b', +Math.min(1, -c.vn0 / 1500).toFixed(2), Math.round(c.a.x)]);
          } else {
            c.a.rail = true;
            if (c.vn0 < -60 && hits.length < 48) hits.push([+t.toFixed(2), c.kind === RAIL ? 'r' : 'p', +Math.min(1, -c.vn0 / 1000).toFixed(2), Math.round(c.a.x)]);
          }
        }
      }
      for (const b of balls) if (!b.potted) { b.x += b.vx * h; b.y += b.vy * h; }
      for (const b of balls) if (!b.potted && !b.sink && !b.asleep) spinStep(b, h);
      for (const b of balls) if (b.sink && sinkStep(b, h)) {
        pots.push([b.n, +b.capT.toFixed(2), +t.toFixed(2), b.sink[5]]); b.sink = null; b.potted = true; b.vx = b.vy = b.w = b.sx = b.sy = 0; moved.add(b.n);
      }
      for (const b of balls) {
        if (b.potted || b.sink) continue;
        if (b.vx * b.vx + b.vy * b.vy < SLEEP_V * SLEEP_V) { b.sleepT += h; if (b.sleepT >= SLEEP_T) { b.asleep = true; b.vx = b.vy = b.w = 0; } }
        else { b.sleepT = 0; b.asleep = false; moved.add(b.n); }
      }
    }
    if (t >= nextF) { frame(); nextF += 1 / FPS; }
  }
  frame();
  const ids = balls.map(b => b.n), keep = []; ids.forEach((n, i) => { if (moved.has(n)) keep.push(i); });
  const outF = frames.map(f => { const o = []; for (const i of keep) o.push(f[2 * i], f[2 * i + 1]); return o; });
  const fin = new Array(16).fill(null); for (const b of balls) if (!b.potted) fin[b.n] = [+b.x.toFixed(2), +b.y.toFixed(2)];
  return { pos: fin, ids: keep.map(i => ids[i]), frames: outF, dur: +(frames.length / FPS).toFixed(2), pots, first: cue.first,
    rails: balls.filter(b => b.rail).map(b => b.n).sort((a, b) => a - b), hits };
}

/* ---------- چیدمان و جای خالی ---------- */
function free(pos, me, x, y) { for (let i = 0; i < pos.length; i++) { const p = pos[i]; if (i !== me && p && (p[0] - x) ** 2 + (p[1] - y) ** 2 < D * D - 1e-6) return false; } return true; }
function shuffle(a) { for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; } return a; }
function rack() {
  const order = shuffle([1, 2, 3, 4, 5, 6, 7, 9, 10, 11, 12, 13, 14, 15]), pair = [];
  for (const v of order.slice()) if (pair.length < 2 && (!pair.length || (v < 8) !== (pair[0] < 8))) { pair.push(v); order.splice(order.indexOf(v), 1); }
  order.splice(4, 0, 8); order.splice(10, 0, pair[0]); order.splice(14, 0, pair[1]);
  const sp = D + 2; let pos;
  for (let tr = 0; tr < 500; tr++) {
    const ang = (29 + Math.random() * 2) * Math.PI / 180, f = Math.sin(ang) * sp, d = Math.cos(ang) * sp;
    const p = -Math.sin(ang + Math.PI / 3) * sp, m = -Math.cos(ang + Math.PI / 3) * sp, ax = 415 + Math.random() * 4, ay = 414 + Math.random() * 8;
    pos = new Array(16).fill(null); let k = 0;
    [1, 2, 3, 4, 5].forEach((n, e) => {
      let s = ax - f * (n - 1) + (Math.random() * .06 - .03) * Math.sin(ang), l = ay - d * e + (Math.random() * .06 - .03) * Math.cos(ang);
      for (let j = 0; j < n; j++) { pos[order[k++]] = [+s.toFixed(2), +l.toFixed(2)]; s -= p; l += m; }
    });
    pos[0] = CUE_START.slice();
    let ok = true; for (let i = 1; i < 16; i++) if (!free(pos, i, pos[i][0], pos[i][1])) { ok = false; break; }
    if (ok) return pos;
  }
  return pos;
}
function spot(pos, n) {
  for (let k = 0; k < 400; k++) {
    const ring = Math.floor(k / 8), a = (k % 8) * Math.PI / 4;
    const x = Math.min(MAX_X, Math.max(MIN_X, FOOT[0] + Math.cos(a) * 4 * ring)), y = Math.min(MAX_Y, Math.max(MIN_Y, FOOT[1] + Math.sin(a) * 4 * ring / 1.2));
    if (free(pos, n, x, y)) return [x, y];
  }
  return FOOT.slice();
}
function cueSpot(pos, breaking) {
  const [x, y] = breaking ? CUE_START : [W / 2 - 5, MIN_Y + (MAX_Y - MIN_Y) * .78];
  if (free(pos, 0, x, y)) return [x, y];
  for (let k = 1; k < 60; k++) for (const dx of [k * 6, -k * 6]) if (x + dx >= MIN_X && x + dx <= MAX_X && free(pos, 0, x + dx, y)) return [x + dx, y];
  return [x, y];
}
const validPlace = (balls, breaking, x, y) => x >= MIN_X && x <= MAX_X && y >= MIN_Y && y <= MAX_Y && (!breaking || y >= BREAK_MIN_Y) && free(balls, 0, x, y);

/* ---------- پیش بینی خط نشانه: اولین توپ یا دیواره سر راه ---------- */
function aim(balls, angle) {
  const c = balls[0]; if (!c) return null;
  const dx = Math.cos(angle), dy = Math.sin(angle);
  let best = Infinity, hit = -1;
  for (let k = 1; k < 16; k++) {
    const b = balls[k]; if (!b) continue;
    const lx = b[0] - c[0], ly = b[1] - c[1], tca = lx * dx + ly * dy; if (tca < 0) continue;
    const d2 = lx * lx + ly * ly - tca * tca; if (d2 > D * D) continue;
    const t0 = tca - Math.sqrt(D * D - d2); if (t0 >= 0 && t0 < best) { best = t0; hit = k; }
  }
  let tw = Infinity;
  if (dx > 1e-9) tw = Math.min(tw, (MAX_X - c[0]) / dx); if (dx < -1e-9) tw = Math.min(tw, (MIN_X - c[0]) / dx);
  if (dy > 1e-9) tw = Math.min(tw, (MAX_Y - c[1]) / dy); if (dy < -1e-9) tw = Math.min(tw, (MIN_Y - c[1]) / dy);
  const t = Math.max(0, Math.min(best, tw));
  return { dist: t, ghost: [c[0] + dx * t, c[1] + dy * t], hit: best <= tw ? hit : -1 };
}

window.BLEngine = { W, H, R, D, HEAD, MIN_X, MAX_X, MIN_Y, MAX_Y, BREAK_MIN_Y, CUE_START, POCKETS, RAILS, MOUTHS, EDGES,
  IMPULSE, MIN_POWER, BREAK_MIN, BREAK_BONUS, BREAK_RAND, BREAK_JIT, simulate, rack, spot, cueSpot, free, validPlace, aim };
})();
