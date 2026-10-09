/* فیزیک فوتبال: کپی دقیق simulate در game_club/football.py.
   مینی اپ با همین، شوت خودت را همان لحظه رها کردن نشان می دهد (بی منتظر ماندن برای سرور)
   و نسخه نمایشی (demo-football.js) هم با همین بازی می کند. ترتیب حلقه ها و همه عملیات
   مثل نسخه پایتون است (فقط + - * / و sqrt)، پس نتیجه دو طرف یکی است؛ سرور همیشه مرجع است. */
(function (root) {
const W = 600, H = 1040, GOAL_W = 220, GOAL_D = 60, GX0 = (W - GOAL_W) / 2, GX1 = (W + GOAL_W) / 2;
const DISC_R = 36, BALL_R = 18, DISC_M = 1, BALL_M = .55, BALL = 12, N = 13, VMAX = 2200, MIN_POWER = .06;
const DT = 1 / 120, FRAME_EVERY = 4, MAX_SIM = 9, AFTER_GOAL = .5, DRAG = [.9, 1.3], FRIC = [360, 280], BALL_VMAX = 1200;
const E_PAIR = .82, E_BALL_DISC = .68, E_DISC_WALL = .5, E_BALL_WALL = .65, STOP = 4;
const BALL_SLIDE = .9, SLIDE_V = 700, MU_PAIR = .12, MU_WALL = [.15, .08];
const SEGS = [[[0, 0], [GX0, 0]], [[GX1, 0], [W, 0]], [[GX0, 0], [GX0, -GOAL_D]], [[GX0, -GOAL_D], [GX1, -GOAL_D]], [[GX1, -GOAL_D], [GX1, 0]],
  [[0, H], [GX0, H]], [[GX1, H], [W, H]], [[GX0, H], [GX0, H + GOAL_D]], [[GX0, H + GOAL_D], [GX1, H + GOAL_D]], [[GX1, H + GOAL_D], [GX1, H]],
  [[0, 0], [0, H]], [[W, 0], [W, H]]];
const sorted = set => [...set].sort((a, b) => a - b);
const r2 = v => Math.round(v * 100) / 100;

function simulate(pos, vel) {
  const x = pos.map(p => +p[0]), y = pos.map(p => +p[1]), vx = Array(N).fill(0), vy = Array(N).fill(0);
  const r = i => i === BALL ? BALL_R : DISC_R, m = i => i === BALL ? BALL_M : DISC_M, kind = i => i === BALL ? 1 : 0;
  const moving = new Set(), moved = new Set(), hits = [], touch = [];
  for (const [i, [a, b]] of Object.entries(vel)) { vx[i] = +a; vy[i] = +b; moving.add(+i); moved.add(+i); }
  const frames = [[x.slice(), y.slice()]];
  let goal = null, after = 0, t = 0, step = 0;
  while (moving.size && t < MAX_SIM) {
    step++; t += DT;
    for (const i of moving) { x[i] += vx[i] * DT; y[i] += vy[i] * DT; }
    for (const i of sorted(moving)) {
      for (let j = 0; j < N; j++) {
        if (j === i || (moving.has(j) && j < i)) continue;
        const rr = r(i) + r(j), dx = x[j] - x[i], dy = y[j] - y[i];
        if (dx > rr || dx < -rr || dy > rr || dy < -rr) continue;
        const d2 = dx * dx + dy * dy;
        if (d2 >= rr * rr || d2 === 0) continue;
        const d = Math.sqrt(d2), nx = dx / d, ny = dy / d;
        const rel = (vx[j] - vx[i]) * nx + (vy[j] - vy[i]) * ny, inv = 1 / m(i) + 1 / m(j);
        if (rel < 0) {
          if (rel < -120 && hits.length < 24) hits.push([r2(t), i === BALL || j === BALL ? 'b' : 'd', r2(Math.min(1, -rel / 2000))]);
          if (i === BALL || j === BALL) {
            const o = j === BALL ? i : j;
            if (vx[BALL] * vx[BALL] + vy[BALL] * vy[BALL] > vx[o] * vx[o] + vy[o] * vy[o] && !touch.includes(o)) touch.push(o);
          }
          const imp = -(1 + (i === BALL || j === BALL ? E_BALL_DISC : E_PAIR)) * rel / inv;
          vx[i] -= imp / m(i) * nx; vy[i] -= imp / m(i) * ny; vx[j] += imp / m(j) * nx; vy[j] += imp / m(j) * ny;
          const tx = -ny, ty = nx, vt = (vx[j] - vx[i]) * tx + (vy[j] - vy[i]) * ty, jt = -MU_PAIR * vt / inv;
          vx[i] -= jt / m(i) * tx; vy[i] -= jt / m(i) * ty; vx[j] += jt / m(j) * tx; vy[j] += jt / m(j) * ty;
        }
        const over = rr - d, ki = (1 / m(i)) / inv, kj = (1 / m(j)) / inv;
        x[i] -= nx * over * ki; y[i] -= ny * over * ki; x[j] += nx * over * kj; y[j] += ny * over * kj;
        moving.add(j); moved.add(j);
      }
    }
    if (moving.has(BALL)) {
      const sp2 = vx[BALL] * vx[BALL] + vy[BALL] * vy[BALL];
      if (sp2 > BALL_VMAX * BALL_VMAX) { const f = BALL_VMAX / Math.sqrt(sp2); vx[BALL] *= f; vy[BALL] *= f; }
    }
    for (const i of moving) {
      const e = kind(i) ? E_BALL_WALL : E_DISC_WALL, ri = r(i);
      for (const [[ax, ay], [bx, by]] of SEGS) {
        const ex = bx - ax, ey = by - ay, ll = ex * ex + ey * ey;
        let u = ((x[i] - ax) * ex + (y[i] - ay) * ey) / ll; u = u < 0 ? 0 : u > 1 ? 1 : u;
        const qx = ax + ex * u, qy = ay + ey * u, dx = x[i] - qx, dy = y[i] - qy;
        if (dx > ri || dx < -ri || dy > ri || dy < -ri) continue;
        const d2 = dx * dx + dy * dy;
        if (d2 >= ri * ri || d2 === 0) continue;
        const d = Math.sqrt(d2), nx = dx / d, ny = dy / d, vn = vx[i] * nx + vy[i] * ny;
        if (vn < 0) {
          if (vn < -150 && hits.length < 24) {
            const post = (u === 0 || u === 1) && (Math.abs(qx - GX0) < 1 || Math.abs(qx - GX1) < 1) && (Math.abs(qy) < 1 || Math.abs(qy - H) < 1);
            hits.push([r2(t), post ? 'p' : 'w', r2(Math.min(1, -vn / 2000))]);
          }
          vx[i] -= (1 + e) * vn * nx; vy[i] -= (1 + e) * vn * ny;
          const vt = vx[i] * -ny + vy[i] * nx;
          vx[i] -= MU_WALL[kind(i)] * vt * -ny; vy[i] -= MU_WALL[kind(i)] * vt * nx;
        }
        x[i] += nx * (ri - d); y[i] += ny * (ri - d);
      }
    }
    for (const i of sorted(moving)) {
      const sp = Math.sqrt(vx[i] * vx[i] + vy[i] * vy[i]), k = kind(i), dg = DRAG[k] + (k === 1 && sp > SLIDE_V ? BALL_SLIDE : 0), ns = sp - (dg * sp + FRIC[k]) * DT;
      if (ns <= STOP) { vx[i] = vy[i] = 0; moving.delete(i); } else { const f = ns / sp; vx[i] *= f; vy[i] *= f; }
    }
    if (goal == null) { if (y[BALL] < -BALL_R) goal = 0; else if (y[BALL] > H + BALL_R) goal = 1; }
    else if ((after += DT) >= AFTER_GOAL) break;
    if (step % FRAME_EVERY === 0) frames.push([x.slice(), y.slice()]);
  }
  frames.push([x.slice(), y.slice()]);
  const ids = sorted(moved);
  return { pos: x.map((v, i) => [Math.round(v * 10) / 10, Math.round(y[i] * 10) / 10]), raw: [x, y], ids,
    frames: frames.map(f => ids.flatMap(i => [Math.round(f[0][i]), Math.round(f[1][i])])),
    dur: Math.round(frames.length * DT * FRAME_EVERY * 100) / 100, goal, hits, touch };
}
// شوت مثل سرور: قدرت محدود، جهت نرمال، سرعت = VMAX * قدرت / طول
function shotVel(dx, dy, power) {
  const ln = Math.sqrt(dx * dx + dy * dy); if (!(ln > 1e-6)) return null;
  power = Math.min(1, Math.max(MIN_POWER, power));
  const v = VMAX * power / ln;
  return [dx * v, dy * v];
}
// پاس: توپ بعد از شوت به یکی دیگر از مهره های خودی خورده باشد
const passOf = (i, disc, res) => { const d = res.touch.find(d => d >= i * 6 && d < i * 6 + 6 && d !== disc); return d == null ? null : d; };
// پاس مثل آهنربا: توپ جلوی گیرنده رو به دروازه حریف می چسبد (مثل catch_pos پایتون)
const C30 = 0.8660254037844386, S30 = .5, HOLD_GAP = DISC_R + BALL_R + 1;
const CATCH_DIRS = [[0, -1], [S30, -C30], [-S30, -C30], [C30, -S30], [-C30, -S30], [1, 0], [-1, 0], [C30, S30], [-C30, S30], [0, 1]];
function free(pos, d, bx, by) {
  if (bx < BALL_R || bx > W - BALL_R || by < BALL_R || by > H - BALL_R) return false;
  const lim = (DISC_R + BALL_R + .5) * (DISC_R + BALL_R + .5);
  for (let j = 0; j < 12; j++) { if (j === d) continue; const dx = pos[j][0] - bx, dy = pos[j][1] - by; if (dx * dx + dy * dy < lim) return false; }
  return true;
}
function catchPos(pos, i, d) {
  const [cx, cy] = pos[d], sg = i === 0 ? 1 : -1;
  for (const [fx, fy] of CATCH_DIRS) {
    const bx = cx + fx * sg * HOLD_GAP, by = cy + fy * sg * HOLD_GAP;
    if (free(pos, d, bx, by)) return [Math.round(bx * 10) / 10, Math.round(by * 10) / 10];
  }
  return null;
}
// مهره ای که توپ را دارد: توپ قبل از شوت درست جلویش در جهت شوت (مثل hold_pos پایتون)؛ جا نبود همان pos
function holdPos(pos, d, dx, dy) {
  const ln = Math.sqrt(dx * dx + dy * dy), bx = pos[d][0] + dx / ln * HOLD_GAP, by = pos[d][1] + dy / ln * HOLD_GAP;
  if (!free(pos, d, bx, by)) return pos;
  const out = pos.map(p => p.slice()); out[BALL] = [bx, by]; return out;
}
const api = { simulate, shotVel, passOf, catchPos, holdPos, HOLD_GAP, MAX_PASS: 3, W, H, GOAL_W, GOAL_D, GX0, GX1, DISC_R, BALL_R, BALL, VMAX, MIN_POWER };
if (typeof module !== 'undefined' && module.exports) module.exports = api;
if (root) root.FBPhysics = api;
})(typeof window !== 'undefined' ? window : null);
