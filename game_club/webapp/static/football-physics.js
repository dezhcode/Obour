/* فیزیک فوتبال میزی: کپی دقیق game_club/football_phys.py (پورت موتور p2 بازی پلاتو).
   مینی اپ با همین، شوت خودت را همان لحظه رها کردن نشان می دهد (بی منتظر ماندن برای سرور)
   و نسخهٔ نمایشی (demo-football.js) هم با همین بازی می کند. ترتیب معادله ها و همهٔ عملیات
   مثل نسخهٔ پایتون است (فقط + - * / و sqrt در شوت)، پس نتیجهٔ دو طرف یکی است؛ سرور همیشه مرجع است.
   مراحل هر گام (World.internalStep): میرایی ← برخوردها ← بیدار کردن ← حل کننده ← انتگرال ← خواب ← postStep. */
(function (root) {
const MAXF = Number.MAX_VALUE;
const W = 1042, H = 1920, GOAL_W = 354, BALL_R = 32, GOAL_H = BALL_R * 3, POST_R = 5, BOX_W = (W - GOAL_W) * .5, BALL = 12, N = 13;
const REG_R = 55, KEEP_R = 64, REG_M = .76, KEEP_M = 1, REG_D = .41, KEEP_D = .46, TOK_DVAR = 1.005, TOK_ANG = .4;
const BALL_M = .11, BALL_D = .36, BALL_DVAR = 1.003, BALL_CTL_D = .75, BALL_ANG = .5;
const CONTROL_RADIUS = 236, SLEEP_TOK = 10, SLEEP_BALL = 30, SLEEP_T = .02, IMPULSE_MULT = 4.6, IMPULSE_MAX = 250, MAGNET_PASS = 1.5, MAGNET_CTRL = 2.25;
const DT = .015, FRAME_EVERY = 2, MAX_STEPS = 3000, ITER = 10, TOL = 1e-7, FRIC_G = 10;
const CM = {
  'ball|goal': [0, 30, 1e4, 8], 'ball|wall': [.95, 400, MAXF, 4], 'ball|player': [.8, 500, MAXF, 4],
  'player|goal': [0, 40, 1e4, 8], 'player|wall': [.7, 500, MAXF, 4], 'player|player': [.77, 200, MAXF, 4],
};
const FRIC_K = 1e6, FRIC_RELAX = 4, CON_K = 1e6, CON_RELAX = 4;
const AUTO_V_MAX = 600, AUTO_V_MIN = 500, CONTROL_ANGLE_DIF = 3 * .0174533, CONTROL_MAX_STEPS = 900;
const rd2 = v => Math.floor(v * 100 + .5) / 100;

// base ** DT فقط با + - * / و sqrt
function ln_(x) {
  let y = x; for (let i = 0; i < 6; i++) y = Math.sqrt(y);
  const z = (y - 1) / (y + 1), z2 = z * z;
  return 128 * (z * (1 + z2 * (1 / 3 + z2 * (1 / 5 + z2 * (1 / 7 + z2 * (1 / 9 + z2 * (1 / 11 + z2 * (1 / 13))))))));
}
function exp_(t) {
  const u = t / 64;
  let e = 1 + u * (1 + u * (1 / 2 + u * (1 / 6 + u * (1 / 24 + u * (1 / 120 + u * (1 / 720 + u * (1 / 5040)))))));
  for (let i = 0; i < 6; i++) e = e * e;
  return e;
}
function dpow(b) { if (b <= 0) return 0; if (b >= 1) return 1; return exp_(DT * ln_(b)); }

// هندسهٔ ثابت: اسلات ۰ توپ، ۱..۴ صفحه ها، ۵..۸ جعبه ها، ۹..۱۰ حسگر دروازه، ۱۱..۱۴ تیرک، ۱۵..۲۶ مهره ها
const PLANES = [[[0, 0], [0, 1], 'goal'], [[W, 0], [-1, 0], 'wall'], [[0, H], [0, -1], 'goal'], [[0, 0], [1, 0], 'wall']];
const BOX_HW = BOX_W * .5, BOX_HH = GOAL_H * .5;
const BOXES = [[BOX_HW, BOX_HH], [W - BOX_HW, BOX_HH], [BOX_HW, H - BOX_HH], [W - BOX_HW, H - BOX_HH]];
const GH = GOAL_H - BALL_R * 2, GOAL_HW = GOAL_W * .5, GOAL_HH = GH * .5;
const GOALS = [[W * .5, GOAL_HH], [W * .5, H - GOAL_HH]];
const PX0 = W * .5 - GOAL_W * .5 - POST_R, PX1 = W * .5 + GOAL_W * .5 + POST_R;
const POSTS = [[PX0, GOAL_H], [PX1, GOAL_H], [PX0, H - GOAL_H], [PX1, H - GOAL_H]];
const slotDyn = s => s === 0 ? BALL : (s >= 15 ? s - 15 : -1);
const dynSlot = d => d === BALL ? 0 : d + 15;
// کران پایین x جعبهٔ AABB اسلات های ثابت برای مرتب سازی SAP (صفحه: نیم صفحهٔ «توپر»)
const STATIC_LOWER = { 1: -1e7, 2: W, 3: -1e7, 4: -1e7 };

const radiusOf = k => k === BALL ? BALL_R : (k % 6 === 0 ? KEEP_R : REG_R);
BOXES.forEach((b, i) => { STATIC_LOWER[5 + i] = b[0] - BOX_HW; });
GOALS.forEach((g, i) => { STATIC_LOWER[9 + i] = g[0] - GOAL_HW; });
POSTS.forEach((q, i) => { STATIC_LOWER[11 + i] = q[0] - POST_R; });
const PAIRDATA = [], PAIR_BY_DYN = Array.from({ length: N }, () => []);
(function () {
  const grp = {}, msk = {};
  for (let s = 0; s < 27; s++) {
    if (s === 0) { grp[s] = 8; msk[s] = 1 | 2 | 4 | 16; }
    else if (s <= 8) { grp[s] = 1; msk[s] = 4 | 8; }
    else if (s <= 10) { grp[s] = 2; msk[s] = 8; }
    else if (s <= 14) { grp[s] = 16; msk[s] = 4 | 8; }
    else { grp[s] = 4; msk[s] = 1 | 4 | 8 | 16; }
  }
  for (let i = 1; i < 27; i++) for (let j = 0; j < i; j++) {
    if (!(i === 0 || i >= 15 || j === 0 || j >= 15)) continue;
    if (!((grp[i] & msk[j]) && (grp[j] & msk[i]))) continue;
    if ((i >= 9 && i <= 10) || (j >= 9 && j <= 10)) continue;
    const di = slotDyn(i), dj = slotDyn(j), n = PAIRDATA.length;
    PAIRDATA.push([i, j, di, dj]);
    if (di >= 0) PAIR_BY_DYN[di].push(n);
    if (dj >= 0) PAIR_BY_DYN[dj].push(n);
  }
})();
const matKey = (a, b) => (CM[a + '|' + b] ? a + '|' + b : b + '|' + a);

class Sim {
  constructor(pos, team, passOk) {
    const n = N;
    this.x = pos.map(p => +p[0]); this.y = pos.map(p => +p[1]);
    this.vx = Array(n).fill(0); this.vy = Array(n).fill(0); this.w = Array(n).fill(0);
    this.r = Array.from({ length: n }, (_, k) => radiusOf(k));
    this.m = Array.from({ length: n }, (_, k) => k === BALL ? BALL_M : (k % 6 === 0 ? KEEP_M : REG_M));
    this.im = this.m.map(m => 1 / m);
    this.ii = Array.from({ length: n }, (_, k) => k === BALL ? 0 : 1 / (this.r[k] * this.r[k] / 2));
    this.baseD = Array.from({ length: n }, (_, k) => k === BALL ? BALL_D : (k % 6 === 0 ? KEEP_D : REG_D));
    this.damp = this.baseD.slice();
    this.angf = Array.from({ length: n }, (_, k) => dpow(1 - (k === BALL ? BALL_ANG : TOK_ANG)));
    this.angfBase = this.angf.slice();
    this.slim2 = Array.from({ length: n }, (_, k) => (k === BALL ? SLEEP_BALL : SLEEP_TOK) ** 2);
    this.st = Array(n).fill(2); this.idle = Array(n).fill(0);
    this.mmx = Array(n).fill(1); this.mmy = Array(n).fill(1);
    this.time = 0; this.lastPairs = new Set(); this.prevOv = new Set(); this.hits = [];
    this.axis = Array.from({ length: 27 }, (_, i) => i);
    this.team = team; this.passOk = !!passOk; this.shooter = null; this.receiver = null; this.goal = null;
    this.magnet = null; this.magnetDist = 0; this.ctl = false;
  }
  wake(k) { this.st[k] = 0; this.idle[k] = 0; }
  sleep(k) { this.st[k] = 2; this.vx[k] = this.vy[k] = this.w[k] = 0; }
  setImpulse(k, ix, iy) { this.vx[k] += ix * this.im[k] * this.mmx[k]; this.vy[k] += iy * this.im[k] * this.mmy[k]; }
  magnetize(k, control = false, secure = true) {
    this.demagnetize(false);
    this.magnet = k; this.magnetDist = this.r[k] + BALL_R * (control && secure ? MAGNET_CTRL : MAGNET_PASS);
    this.wake(k); this.wake(BALL);
    if (control) {
      this.mmx[BALL] = this.mmy[BALL] = 0;
      for (let p = 0; p < 12; p++) { this.angf[p] = 0; if (p !== k) this.damp[p] = .9999999; }
    } else this.damp[BALL] = BALL_CTL_D;
  }
  demagnetize(full) {
    if (this.magnet !== null) {
      if (full) {
        this.mmx[BALL] = this.mmy[BALL] = 1;
        for (let p = 0; p < 12; p++) { this.angf[p] = this.angfBase[p]; if (p !== this.magnet) this.damp[p] = this.baseD[p]; }
      } else this.damp[BALL] = BALL_D;
      this.magnet = null;
    } else this.mmx[BALL] = this.mmy[BALL] = 1;
  }
  sortAxis() {
    const x = this.x, r = this.r, lower = new Array(27);
    for (let q = 0; q < 27; q++) lower[q] = q === 0 ? x[BALL] - r[BALL] : (q >= 15 ? x[q - 15] - r[q - 15] : STATIC_LOWER[q]);
    const ax = this.axis;
    for (let q = 1; q < 27; q++) {
      const e = ax[q], t = lower[e]; let i = q - 1;
      while (i >= 0 && lower[ax[i]] > t) { ax[i + 1] = ax[i]; i--; }
      ax[i + 1] = e;
    }
    const pos = new Array(27); ax.forEach((sl, idx) => { pos[sl] = idx; });
    return pos;
  }
  step() {
    const x = this.x, y = this.y, vx = this.vx, vy = this.vy, w = this.w, st = this.st, h = DT;
    for (let k = 0; k < N; k++) {
      if (vx[k] !== 0 || vy[k] !== 0 || w[k] !== 0) {
        const f = dpow(1 - this.damp[k]);
        vx[k] *= f; vy[k] *= f; w[k] *= this.angf[k];
      }
    }
    const axpos = this.sortAxis();
    this.ballEvents(axpos);
    const contacts = [], curPairs = new Set(), wakeAfter = [];
    const awake = []; for (let d = 0; d < N; d++) if (st[d] !== 2) awake.push(d);
    let idxs;
    if (awake.length === 1) idxs = PAIR_BY_DYN[awake[0]];
    else { const seen = new Set(); for (const d of awake) for (const q of PAIR_BY_DYN[d]) seen.add(q); idxs = [...seen].sort((a, b) => a - b); }
    for (const n of idxs) {
      const [i, j, di, dj] = PAIRDATA[n], c = this.contact(i, j, di, dj, axpos);
      if (c === null) continue;
      if (di >= 0 && dj >= 0) {
        for (const [a, b] of [[di, dj], [dj, di]]) {
          if (st[a] === 2 && st[b] === 0 && vx[b] * vx[b] + vy[b] * vy[b] + w[b] * w[b] >= this.slim2[b] * 2) wakeAfter.push(a);
        }
      }
      curPairs.add(i * 32 + j);
      const pa = axpos[i], pb = axpos[j];
      contacts.push([pa < pb ? pa * 32 + pb : pb * 32 + pa, c, !this.lastPairs.has(i * 32 + j)]);
    }
    for (const a of wakeAfter) this.wake(a);
    this.lastPairs = curPairs;
    contacts.sort((a, b) => a[0] - b[0]);
    const eqs = this.buildEquations(contacts);
    if (eqs.length) this.solveIslands(eqs);
    for (let k = 0; k < N; k++) if (vx[k] !== 0 || vy[k] !== 0) { x[k] += vx[k] * h; y[k] += vy[k] * h; }
    for (let k = 0; k < N; k++) {
      if (vx[k] * vx[k] + vy[k] * vy[k] + w[k] * w[k] >= this.slim2[k]) { this.idle[k] = 0; st[k] = 0; }
      else { this.idle[k] += h; if (st[k] !== 1) st[k] = 1; }
      if (this.idle[k] > SLEEP_T) this.sleep(k);
    }
    this.time += h;
    if (this.receiver !== null && !this.ctl && (this.magnet === null || this.magnet !== this.receiver)) {
      vx[BALL] = vy[BALL] = 0; this.magnetize(this.receiver);
    }
    if (st[BALL] === 1) this.damp[BALL] = this.magnet !== null ? BALL_CTL_D : BALL_D;
    else if (st[BALL] === 0 && this.damp[BALL] < 1) { const d = this.damp[BALL] * BALL_DVAR; this.damp[BALL] = d < 1 ? d : 1; }
    for (let k = 0; k < 12; k++) {
      if (st[k] === 1) this.damp[k] = this.baseD[k];
      else if (st[k] === 0 && this.damp[k] < 1) { const d = this.damp[k] * TOK_DVAR; this.damp[k] = d < 1 ? d : 1; }
    }
  }
  ballEvents(axpos) {
    const x = this.x, y = this.y, bx = x[BALL], by = y[BALL], R = BALL_R, cur = new Set(), news = [];
    for (let g = 0; g < 2; g++) {
      const [gx, gy] = GOALS[g], lx = bx - gx, ly = by - gy;
      const qx = lx < -GOAL_HW ? -GOAL_HW : (lx > GOAL_HW ? GOAL_HW : lx), qy = ly < -GOAL_HH ? -GOAL_HH : (ly > GOAL_HH ? GOAL_HH : ly);
      const dx = qx - lx, dy = qy - ly;
      if (dx * dx + dy * dy <= R * R) {
        cur.add(g);
        if (!this.prevOv.has(g)) news.push([Math.min(axpos[0], axpos[9 + g]), Math.max(axpos[0], axpos[9 + g]), 0, g]);
      }
    }
    for (let k = 0; k < 12; k++) {
      const rr = this.r[k] + R, dx = x[k] - bx, dy = y[k] - by;
      if (dx > rr || dx < -rr || dy > rr || dy < -rr) continue;
      if (dx * dx + dy * dy <= rr * rr) {
        cur.add(10 + k);
        if (!this.prevOv.has(10 + k)) news.push([Math.min(axpos[0], axpos[15 + k]), Math.max(axpos[0], axpos[15 + k]), 1, k]);
      }
    }
    this.prevOv = cur;
    news.sort((a, b) => a[0] - b[0] || a[1] - b[1] || a[2] - b[2] || a[3] - b[3]);
    for (const [, , kind, q] of news) {
      if (kind === 0) { if (this.goal === null) { this.goal = q; this.receiver = null; } }
      else this.touch(q);
    }
  }
  touch(o) {
    if (!this.passOk || Math.floor(o / 6) !== this.team) return;
    if (this.shooter === null) this.shooter = o;
    else if (o !== this.shooter && o !== this.receiver) this.receiver = o;
  }
  contact(i, j, di, dj, axpos) {
    const x = this.x, y = this.y, r = this.r;
    if (di >= 0 && dj >= 0) {                 // دایره/دایره: A دیرتر در فهرست محوری
      const a = axpos[i] > axpos[j] ? di : dj, b = axpos[i] > axpos[j] ? dj : di;
      const ax = x[a], ay = y[a], bx = x[b], by = y[b], ra = r[a], rb = r[b], dx = bx - ax, dy = by - ay, rr = ra + rb;
      if (dx > rr || dx < -rr || dy > rr || dy < -rr) return null;
      const d2 = dx * dx + dy * dy; if (d2 > rr * rr) return null;
      const d = Math.sqrt(d2), nx = d === 0 ? 1 : dx / d, ny = d === 0 ? 0 : dy / d;
      return [a, b, nx, ny, nx * ra, ny * ra, -nx * rb, -ny * rb, d - ra - rb, a === BALL ? 'ball' : 'player', b === BALL ? 'ball' : 'player', (di === BALL || dj === BALL) ? 'b' : 'd'];
    }
    const d_ = di >= 0 ? di : dj, s_ = di >= 0 ? j : i, cx = x[d_], cy = y[d_], R = r[d_], matD = d_ === BALL ? 'ball' : 'player';
    if (s_ >= 1 && s_ <= 4) {
      const [[px, py], [nx, ny], mt] = PLANES[s_ - 1], dd = nx * (cx - px) + ny * (cy - py);
      if (dd > R) return null;
      return [13, d_, nx, ny, (cx - px) - nx * dd, (cy - py) - ny * dd, -nx * R, -ny * R, dd - R, mt, matD, 'w'];
    }
    if (s_ >= 5 && s_ <= 8) {
      const [bx0, by0] = BOXES[s_ - 5], lx = cx - bx0, ly = cy - by0;
      let qx = lx < -BOX_HW ? -BOX_HW : (lx > BOX_HW ? BOX_HW : lx), qy = ly < -BOX_HH ? -BOX_HH : (ly > BOX_HH ? BOX_HH : ly);
      let dx = qx - lx, dy = qy - ly, d2 = dx * dx + dy * dy;
      if (d2 > R * R) return null;
      if (d2 === 0) {
        const gx = BOX_HW - Math.abs(lx), gy = BOX_HH - Math.abs(ly);
        if (gx < gy) { qx = lx >= 0 ? BOX_HW : -BOX_HW; qy = ly; } else { qx = lx; qy = ly >= 0 ? BOX_HH : -BOX_HH; }
        dx = qx - lx; dy = qy - ly; d2 = dx * dx + dy * dy;
      }
      const d = Math.sqrt(d2), nx = d === 0 ? 0 : dx / d, ny = d === 0 ? 1 : dy / d;
      return [d_, 13, nx, ny, nx * R, ny * R, qx, qy, d - R, matD, 'wall', 'w'];
    }
    const [px, py] = POSTS[s_ - 11];
    let ax, ay, bx, by, ra, rb, A, B;
    if (axpos[s_] > axpos[dynSlot(d_)]) { ax = px; ay = py; bx = cx; by = cy; ra = POST_R; rb = R; A = 13; B = d_; }
    else { ax = cx; ay = cy; bx = px; by = py; ra = R; rb = POST_R; A = d_; B = 13; }
    const dx = bx - ax, dy = by - ay, rr = ra + rb;
    if (dx > rr || dx < -rr || dy > rr || dy < -rr) return null;
    const d2 = dx * dx + dy * dy; if (d2 > rr * rr) return null;
    const d = Math.sqrt(d2), nx = d === 0 ? 1 : dx / d, ny = d === 0 ? 0 : dy / d;
    return [A, B, nx, ny, nx * ra, ny * ra, -nx * rb, -ny * rb, d - ra - rb, matD, 'wall', 'p'];
  }
  gwOf(g, A, B) {
    const vx = this.vx, vy = this.vy, w = this.w;
    const vAx = A !== 13 ? vx[A] : 0, vAy = A !== 13 ? vy[A] : 0, wA = A !== 13 ? w[A] : 0;
    const vBx = B !== 13 ? vx[B] : 0, vBy = B !== 13 ? vy[B] : 0, wB = B !== 13 ? w[B] : 0;
    return g[0] * vAx + g[1] * vAy + g[2] * wA + g[3] * vBx + g[4] * vBy + g[5] * wB;
  }
  // هر معادله: [A، B، g0..g5، نوع (۰ تماس، ۱ اصطکاک، ۲ قید)، gq، a، b، eps، invC، λ، minDt، maxDt، iMA، iIA، iMB، iIB، ضریب برگشت، firstImpact، ایندکس، B]
  buildEquations(contacts) {
    const x = this.x, y = this.y, st = this.st, im = this.im, ii = this.ii, mmx = this.mmx, mmy = this.mmy, m = this.m;
    const eqs = [], fr = [];
    const mk = (A, B, g, kind, gq, a, b, eps, mn, mx, rest, first) => {
      const sA = A === 13 || st[A] === 2, sB = B === 13 || st[B] === 2;
      const iMA = sA ? 0 : im[A], iIA = sA ? 0 : ii[A], iMB = sB ? 0 : im[B], iIB = sB ? 0 : ii[B];
      const mAx = A !== 13 ? mmx[A] : 1, mAy = A !== 13 ? mmy[A] : 1, mBx = B !== 13 ? mmx[B] : 1, mBy = B !== 13 ? mmy[B] : 1;
      const gimgt = g[0] * g[0] * iMA * mAx + g[1] * g[1] * iMA * mAy + g[2] * g[2] * iIA + g[3] * g[3] * iMB * mBx + g[4] * g[4] * iMB * mBy + g[5] * g[5] * iIB;
      return [A, B, g[0], g[1], g[2], g[3], g[4], g[5], kind, gq, a, b, eps, 1 / (gimgt + eps), 0, mn, mx, iMA, iIA, iMB, iIB, rest, first, 0, 0];
    };
    for (const [, c, first] of contacts) {
      const [A, B, nx, ny, cax, cay, cbx, cby, gq, matA, matB, kind] = c;
      const [rest, mu, k, relax] = CM[matKey(matA, matB)];
      const aS = 4 / (DT * (1 + 4 * relax)), bS = 4 * relax / (1 + 4 * relax), eps = 4 / (DT * DT * k * (1 + 4 * relax));
      const g = [-nx, -ny, -(cax * ny - cay * nx), nx, ny, cbx * ny - cby * nx];
      if (first && (-this.gwOf(g, A, B)) > 120 && this.hits.length < 40) this.hits.push([Math.floor(this.time * 100 + .5) / 100, kind, -this.gwOf(g, A, B)]);
      eqs.push(mk(A, B, g, 0, gq, aS, bS, eps, 0, MAXF * DT, rest, first));
      const tx = ny, ty = -nx;
      const red = A === 13 ? m[B] : (B === 13 ? m[A] : m[A] * m[B] / (m[A] + m[B]));
      const slip = mu * FRIC_G * red, aF = 4 / (DT * (1 + 4 * FRIC_RELAX)), bF = 4 * FRIC_RELAX / (1 + 4 * FRIC_RELAX), epsF = 4 / (DT * DT * FRIC_K * (1 + 4 * FRIC_RELAX));
      const gf = [-tx, -ty, -(cax * ty - cay * tx), tx, ty, cbx * ty - cby * tx];
      fr.push(mk(A, B, gf, 1, 0, aF, bF, epsF, -slip * DT, slip * DT, 0, false));
    }
    for (const e of fr) eqs.push(e);
    if (this.magnet !== null) {
      const k = this.magnet, dx = x[BALL] - x[k], dy = y[BALL] - y[k], ln = Math.sqrt(dx * dx + dy * dy);
      if (ln > 0) {
        const ux = dx / ln, uy = dy / ln, aC = 4 / (DT * (1 + 4 * CON_RELAX)), bC = 4 * CON_RELAX / (1 + 4 * CON_RELAX), epsC = 4 / (DT * DT * CON_K * (1 + 4 * CON_RELAX));
        eqs.push(mk(k, BALL, [-ux, -uy, 0, ux, uy, 0], 2, ln - this.magnetDist, aC, bC, epsC, -MAXF * DT, MAXF * DT, 0, false));
      }
    }
    eqs.forEach((e, n) => { e[23] = n; });
    return eqs;
  }
  solveIslands(eqs) {
    const idp = Array.from({ length: 28 }, (_, i) => i), sz = Array(28).fill(1);
    const find = i => { while (i !== idp[i]) { idp[i] = idp[idp[i]]; i = idp[i]; } return i; };
    for (const e of eqs) {
      const A = e[0], B = e[1];
      if (A !== 13 && B !== 13) {
        const a = find(dynSlot(A)), b = find(dynSlot(B));
        if (a !== b) { if (sz[a] < sz[b]) { idp[a] = b; sz[b] += sz[a]; } else { idp[b] = a; sz[a] += sz[b]; } }
      }
    }
    const island = { 13: -1 }; for (let k = 0; k < N; k++) island[k] = find(dynSlot(k));
    const key = e => island[e[0]] > 0 ? island[e[0]] : island[e[1]];
    eqs.sort((a, b) => key(a) - key(b) || a[23] - b[23]);
    const n = eqs.length; let s = 0;
    while (s < n) {
      const kk = key(eqs[s]); let t = s + 1;
      while (t < n && key(eqs[t]) === kk) t++;
      this.solve(eqs.slice(s, t)); s = t;
    }
  }
  solve(eqs) {
    const vlx = Array(14).fill(0), vly = Array(14).fill(0), wl = Array(14).fill(0), mmx = this.mmx, mmy = this.mmy, vx = this.vx, vy = this.vy, w = this.w;
    const neq = eqs.length, tol2 = (TOL * neq) * (TOL * neq);
    for (const e of eqs) {
      const A = e[0], B = e[1];
      const vAx = A !== 13 ? vx[A] : 0, vAy = A !== 13 ? vy[A] : 0, wA = A !== 13 ? w[A] : 0, vBx = B !== 13 ? vx[B] : 0, vBy = B !== 13 ? vy[B] : 0, wB = B !== 13 ? w[B] : 0;
      const gw = e[2] * vAx + e[3] * vAy + e[4] * wA + e[5] * vBx + e[6] * vBy + e[7] * wB, kind = e[8];
      if (kind === 0) { if (e[22] && e[21] !== 0) e[24] = -(1 / e[11] * (1 + e[21]) * gw) * e[11]; else e[24] = -e[9] * e[10] - gw * e[11]; }
      else if (kind === 1) e[24] = -gw * e[11];
      else e[24] = -e[9] * e[10] - gw * e[11];
      e[14] = 0;
    }
    for (let it = 0; it < ITER; it++) {
      let tot = 0;
      for (const e of eqs) {
        const A = e[0], B = e[1], lam = e[14];
        let dl = e[13] * (e[24] - (e[2] * vlx[A] + e[3] * vly[A] + e[4] * wl[A] + e[5] * vlx[B] + e[6] * vly[B] + e[7] * wl[B]) - e[12] * lam);
        const s = lam + dl;
        if (s < e[15]) dl = e[15] - lam; else if (s > e[16]) dl = e[16] - lam;
        e[14] = lam + dl;
        if (A !== 13) { vlx[A] += e[2] * e[17] * dl * mmx[A]; vly[A] += e[3] * e[17] * dl * mmy[A]; wl[A] += e[18] * e[4] * dl; }
        if (B !== 13) { vlx[B] += e[5] * e[19] * dl * mmx[B]; vly[B] += e[6] * e[19] * dl * mmy[B]; wl[B] += e[20] * e[7] * dl; }
        tot += Math.abs(dl);
      }
      if (tot * tot < tol2) break;
    }
    for (let k = 0; k < N; k++) { this.vx[k] += vlx[k]; this.vy[k] += vly[k]; this.w[k] += wl[k]; }
  }
    allAsleep() { let c = 0; for (let k = 0; k < N; k++) if (this.st[k] === 2) c++; return c === N; }
}

function pack(sim, frames, x0, force) {
  const moved = new Set(force);
  for (let q = 0; q < N; q++) if (Math.abs(sim.x[q] - x0[0][q]) > 1e-9 || Math.abs(sim.y[q] - x0[1][q]) > 1e-9) moved.add(q);
  const ids = [...moved].sort((a, b) => a - b);
  return { ids, out: frames.map(f => { const row = []; for (const q of ids) { row.push(rd2(f[0][q])); row.push(rd2(f[1][q])); } return row; }) };
}
function runShot(pos, k, ix, iy, team, passOk) {
  const sim = new Sim(pos, team, passOk);
  sim.setImpulse(k, ix, iy);
  const x0 = [sim.x.slice(), sim.y.slice()], frames = [[sim.x.slice(), sim.y.slice()]];
  let steps = 0;
  for (;;) {
    sim.step(); steps++;
    if (steps % FRAME_EVERY === 0) frames.push([sim.x.slice(), sim.y.slice()]);
    if (sim.allAsleep() || steps >= MAX_STEPS) break;
  }
  sim.demagnetize(false);
  frames.push([sim.x.slice(), sim.y.slice()]);
  const { ids, out } = pack(sim, frames, x0, [k]);
  return { pos: sim.x.map((_, q) => [sim.x[q], sim.y[q]]), ids, frames: out, steps, dur: rd2(steps * DT), goal: sim.goal, shooter: sim.shooter, receiver: sim.receiver, hits: sim.hits };
}

// کنترل بعد از پاس: گیرنده پشت توپ و رو به دروازه می نشیند (سرور مرجع است؛ این نسخه برای نمایشی)
function secureDist(pos, k) { const t = radiusOf(k) + BALL_R * MAGNET_CTRL; return t < pos[k][0] && pos[k][0] < W - t && GOAL_H + t < pos[k][1] && pos[k][1] < H - GOAL_H - t; }
function pointingToGoal(pos, k, team) {
  const [px, py] = pos[k], [bx, by] = pos[BALL], dx = bx - px, dy = by - py, ln = Math.hypot(dx, dy);
  if (ln === 0) return false;
  const ex = px + dx / ln * H, ey = py + dy / ln * H, [gx, gy] = GOALS[team], x1 = gx - GOAL_HW + POST_R, x2 = gx + GOAL_HW - POST_R;
  const rx = ex - px, ry = ey - py, sx = x2 - x1, sy = 0, den = rx * sy - ry * sx;
  if (den === 0) return false;
  const t = ((x1 - px) * sy - (gy - py) * sx) / den, u = ((x1 - px) * ry - (gy - py) * rx) / den;
  return t > 0 && t <= 1 && u >= 0 && u <= 1;
}
function controlDestination(pos, k, team) {
  if (pointingToGoal(pos, k, team)) return null;
  const [px, py] = pos[k], [bx, by] = pos[BALL], [gx, gy] = GOALS[team], r = radiusOf(k) + BALL_R * MAGNET_CTRL;
  let n = Math.atan2(gy - by, gx - bx) + Math.PI; if (n < 0) n += 2 * Math.PI;
  const ax = bx + Math.cos(n) * r, ay = by + Math.sin(n) * r;
  let s = Math.atan2(py - by, px - bx); if (s < 0) s += 2 * Math.PI;
  s = Math.abs(n - s); s = Math.abs(s - Math.PI);
  const rad = radiusOf(k);
  let wall = false;
  if ((bx - r - rad <= 0 && ax <= bx) || (bx + r + rad >= W && ax >= bx)) wall = team === 0 ? py <= by : py >= by;
  if (s < Math.PI / 6 || wall) {
    const sg = ax < W * .5 ? (team === 0 ? -1 : 1) : (team === 0 ? 1 : -1), dist = Math.hypot(px - bx, py - by), pts = [[ax, ay]];
    for (let q = 1; q < 5; q++) { const ang = n + sg * Math.PI / 5 * q; pts.unshift([bx + Math.cos(ang) * dist, by + Math.sin(ang) * dist]); }
    return pts;
  }
  return [ax, ay];
}
function runControl(pos, k, team) {
  let dest = controlDestination(pos, k, team);
  if (dest === null) return { pos: pos.map(p => [+p[0], +p[1]]), ids: [], frames: [], steps: 0, dur: 0, moved: false };
  const single = d => typeof d[0] === 'number';
  const sim = new Sim(pos, team, false); sim.ctl = true; sim.magnetize(k, true, secureDist(pos, k));
  for (let q = 0; q < 12; q++) { sim.sleep(q); sim.idle[q] = 0; }
  const x0 = [sim.x.slice(), sim.y.slice()], frames = [[sim.x.slice(), sim.y.slice()]];
  let cv = AUTO_V_MAX, steps = 0, done = false;
  while (steps < CONTROL_MAX_STEPS) {
    if (!done) {
      const e = single(dest) ? dest : dest[0], bx = sim.x[BALL], by = sim.y[BALL];
      const ia = Math.atan2(sim.y[k] - by, sim.x[k] - bx), ta = Math.atan2(e[1] - by, e[0] - bx);
      if (Math.abs(ia - ta) > CONTROL_ANGLE_DIF) {
        const dx = e[0] - sim.x[k], dy = e[1] - sim.y[k], ln = Math.hypot(dx, dy);
        if (ln > 0) { sim.vx[k] = dx / ln * cv; sim.vy[k] = dy / ln * cv; sim.wake(k); }
      } else if (!single(dest) && dest.length > 1) dest = dest.slice(1);
      else { sim.vx[k] = sim.vy[k] = 0; sim.damp[k] = 1; done = true; }
      cv = Math.max(AUTO_V_MIN, cv - 1);
    }
    sim.step(); steps++;
    if (steps % FRAME_EVERY === 0) frames.push([sim.x.slice(), sim.y.slice()]);
    if (done && sim.allAsleep()) break;
  }
  sim.demagnetize(true);
  frames.push([sim.x.slice(), sim.y.slice()]);
  const { ids, out } = pack(sim, frames, x0, []);
  return { pos: sim.x.map((_, q) => [sim.x[q], sim.y[q]]), ids, frames: out, steps, dur: rd2(steps * DT), moved: ids.length > 0 };
}
// جهت (dx، dy) و قدرت ۰..۱ ← ضربهٔ پلاتو (طول = قدرت × ۲۵۰ × ۴٫۶)
function impulse(dx, dy, power) {
  const ln = Math.sqrt(dx * dx + dy * dy); if (ln < 1e-9) return null;
  const f = Math.min(1, Math.max(.02, power)) * IMPULSE_MAX * IMPULSE_MULT / ln;
  return [dx * f, dy * f];
}
root.FBPhysics = { W, H, GOAL_W, BALL_R, REG_R, KEEP_R, GOAL_H, POST_R, BOX_W, BALL, N, CONTROL_RADIUS, IMPULSE_MAX, IMPULSE_MULT, DT, FRAME_EVERY,
  GOALS, radiusOf, runShot, runControl, impulse, rd2, Sim };
})(typeof window !== 'undefined' ? window : globalThis);
