/* فیزیک برگ روی میز حکم؛ بدون DOM (hokm.js آن را می راند، با node هم آزموده می شود).
   واحدها: پیکسلِ توده وسط میز (برگ ۶۴×۹۰؛ ۹۰۰ پیکسل ≈ یک متر)، ثانیه، رادیان؛ x به راست، y به پایین.
   هر برگ جسمی تخت است با مرکز (x,y)، زاویه a، سرعت (vx,vy) و سرعت چرخش w:
   - جاذبه: شیب میز برگ را می کشد. env = { ax, ay: کشش در صفحهٔ میز، gn: مؤلفهٔ عمود جاذبه } (پیکسل بر ثانیه^۲).
   - اصطکاک کولمب، ایستا و جنبشی: ماهوت زبرتر است و برگ روی برگ لغزنده تر. برگی که روی برگ دیگر
     افتاده نسبت به همان برگ می لغزد: اگر زیری آرام برود رویی هم با آن می رود، اگر تند کشیده یا
     یک باره متوقف شود رویی جا می ماند یا جلو می رود.
   - چرخش با اصطکاک آرام می شود؛ گوشهٔ برگ که به لبهٔ میز بخورد ضربه و چرخش می گیرد.
   - برگ زیر انگشت (held): نقطهٔ گرفته شده دنبال انگشت می رود و برگ دور همان نقطه می چرخد تا مرکزش
     پشت سر بیاید (مثل هل دادن برگ واقعی از گوشه اش).
   - پرتاب: پرواز با جاذبه و مقاومت هوا، جهش کوتاه روی میز و سُر خوردن تا ایستادن. نقطهٔ فرود و
     سرعت چرخش طوری پیدا می شود که روی میز صاف، برگ درست در جای خودش و با زاویهٔ خودش بایستد. */
(() => {
const G = 9.81, PX = 900;
const W = 64, H = 90, I = (W * W + H * H) / 12;
const FELT = { s: .3, k: .25 }, CARD = { s: .18, k: .13 };
const STICK = 3;                          // کمتر از این (پیکسل بر ثانیه) یعنی ایستاده
const ROT = .042;                         // کندشدن چرخش با اصطکاک: شعاع میانگین / ممان اینرسی
const RAIL_E = .3, RAIL_MU = .25;         // لبهٔ میز: جهش و اصطکاک
const IMPACT = .3;                        // سرعتی که برگ در لحظهٔ خوردن به میز از دست می دهد (ضریب ضربهٔ عمودی)
const AIR_G = .6 * G * PX, AIR_DRAG = 1.4, AIR_SPIN = 1.1;   // برگ تخت در هوا کمی شناور است
const LEVEL = { ax: 0, ay: 0, gn: G * PX };
const CORNERS = [[-W / 2, -H / 2], [W / 2, -H / 2], [W / 2, H / 2], [-W / 2, H / 2]];

// آیا نقطهٔ (x,y) روی برگ b است
function on(b, x, y) {
  const dx = x - b.x, dy = y - b.y, c = Math.cos(b.a), s = Math.sin(b.a);
  return Math.abs(dx * c + dy * s) <= W / 2 && Math.abs(dy * c - dx * s) <= H / 2;
}
// برگ زیر مرکز b: بالاترین برگی که پایین تر از b است
function under(B, b) {
  let u = null;
  for (const o of B) if (o !== b && o.z < b.z && (!u || o.z > u.z) && on(o, b.x, b.y)) u = o;
  return u;
}
const normal = env => Math.max(env.gn, .2 * G * PX);

// یک گام برای برگ آزاد روی سطح زیرش (u: برگ زیری یا null یعنی ماهوت)
function slide(b, u, env, dt) {
  const mu = u ? CARD : FELT, N = normal(env);
  const svx = u ? u.vx : 0, svy = u ? u.vy : 0, sax = u ? u.ax : 0, say = u ? u.ay : 0;
  // در قاب برگ زیری: کشش = شیب میز منهای شتاب خود زیری (اگر زیری یک باره بایستد، رویی جلو می رود).
  // سرعت نسبی با سرعت زیری در شروع همین گام (زیری در این گام زودتر حساب شده)
  const dx = env.ax - sax, dy = env.ay - say, dm = Math.hypot(dx, dy);
  const ux = b.vx - (svx - sax * dt), uy = b.vy - (svy - say * dt), su = Math.hypot(ux, uy);
  if (su < STICK && dm <= mu.s * N) { b.vx = svx; b.vy = svy; b.slip = false; }
  else {
    const f = mu.k * N, fx = su >= STICK ? ux / su : dx / dm, fy = su >= STICK ? uy / su : dy / dm;
    let nx = ux + (dx - f * fx) * dt, ny = uy + (dy - f * fy) * dt;
    if (su >= STICK && nx * ux + ny * uy <= 0) nx = ny = 0;   // اصطکاک می ایستاندش، برعکسش نمی کند
    b.vx = svx + nx; b.vy = svy + ny; b.slip = true;
  }
  if (b.w) { const d = mu.k * N * ROT * dt; b.w = Math.abs(b.w) <= d ? 0 : b.w - Math.sign(b.w) * d; }
  b.x += b.vx * dt; b.y += b.vy * dt; b.a += b.w * dt;
}
// برخورد گوشه های برگ با لبهٔ میز (box: l,t,r,b). hits: سرعت های برخورد برای صدا
function rail(b, box, hits) {
  for (const [px, py] of CORNERS) {
    const c = Math.cos(b.a), s = Math.sin(b.a), rx = px * c - py * s, ry = px * s + py * c;
    const X = b.x + rx, Y = b.y + ry;
    let nx = 0, ny = 0, pen = 0;
    if (X < box.l) { nx = 1; pen = box.l - X; } else if (X > box.r) { nx = -1; pen = X - box.r; }
    else if (Y < box.t) { ny = 1; pen = box.t - Y; } else if (Y > box.b) { ny = -1; pen = Y - box.b; }
    if (!pen) continue;
    b.x += nx * pen; b.y += ny * pen;
    if (b.held) continue;
    const vpx = b.vx - b.w * ry, vpy = b.vy + b.w * rx, vn = vpx * nx + vpy * ny;
    if (vn >= 0) continue;
    const rn = rx * ny - ry * nx, j = -(1 + RAIL_E) * vn / (1 + rn * rn / I);
    b.vx += j * nx; b.vy += j * ny; b.w += rn * j / I;
    // سرعت در امتداد لبه هم کمی گرفته می شود
    const tx = -ny, ty = nx, vt = vpx * tx + vpy * ty, jt = Math.min(Math.abs(vt) * .5, RAIL_MU * j) * Math.sign(vt);
    b.vx -= jt * tx; b.vy -= jt * ty;
    if (hits) hits.push({ b, v: -vn });
  }
}
// برگ زیر انگشت: نقطهٔ گرفته شده (pin) دنبال انگشت؛ اصطکاک زیر مرکز برگ آن را دور pin می چرخاند
function pinned(b, B, env, dt) {
  const p = b.pin, u = under(B, b), mu = u ? CARD : FELT, N = normal(env), q = 1 - Math.exp(-dt / .012);
  // نقطهٔ گرفته شده نرم به انگشت می رسد (هر گام کمی، نه یک باره در اولین گام فریم)
  p.cx = p.cx == null ? p.x : p.cx + (p.x - p.cx) * q; p.cy = p.cy == null ? p.y : p.cy + (p.y - p.cy) * q;
  const c = Math.cos(b.a), s = Math.sin(b.a), ox = p.rx * c - p.ry * s, oy = p.rx * s + p.ry * c;
  const vm = Math.hypot(b.vx, b.vy);
  if (vm > STICK) {
    const F = mu.k * N, fx = -b.vx / vm * F, fy = -b.vy / vm * F;
    b.w += (-ox * fy + oy * fx) / (I + ox * ox + oy * oy) * dt;
  }
  b.w *= Math.exp(-6 * dt);
  b.a += b.w * dt;
  const c2 = Math.cos(b.a), s2 = Math.sin(b.a);
  const nx = p.cx - (p.rx * c2 - p.ry * s2), ny = p.cy - (p.rx * s2 + p.ry * c2), k = 1 - Math.exp(-dt / .03);
  b.vx += ((nx - b.x) / dt - b.vx) * k; b.vy += ((ny - b.y) / dt - b.vy) * k;
  b.x = nx; b.y = ny;
}
// یک گام برای همهٔ برگ های میز (B به ترتیب لایه، زیرین اول). برمی گرداند: آیا چیزی تکان خورد
function step(B, env, dt, box, hits) {
  let moving = false;
  for (const b of B) {
    const pvx = b.vx, pvy = b.vy;
    if (b.held) pinned(b, B, env, dt);
    else slide(b, under(B, b), env, dt);
    if (box) rail(b, box, hits);
    b.ax = (b.vx - pvx) / dt; b.ay = (b.vy - pvy) / dt;
    if (b.held || b.vx || b.vy || b.w) moving = true;
  }
  return moving;
}

/* پرتاب. o: { sx, sy, h0: جای دست و ارتفاعش، a0: زاویهٔ شروع، T: زمان پرواز تا اولین برخورد،
   P: قدرت (۰ تا ۱)، B: برگ های روی میز، box } ؛ (lx,ly): نقطهٔ اولین برخورد، w0: سرعت چرخش.
   rec: نمونه ها برای انیمیشن (هر ۱/۶۰ ثانیه). */
function fly(o, lx, ly, w0, env, rec, dt = 1 / 240, maxGround = .8) {
  const T = o.T, c = AIR_DRAG, cw = AIR_SPIN, frames = [], lands = [];
  const kx = (1 - Math.exp(-c * T)) / c;
  let x = o.sx, y = o.sy, vx = (lx - o.sx) / kx, vy = (ly - o.sy) / kx, vz = (AIR_G * T * T / 2 - o.h0) / T, h = o.h0;
  let a = o.a0, w = w0, t = 0, nf = 0, seg = T;
  const b = { x, y, a, vx: 0, vy: 0, w: 0, z: Infinity, ax: 0, ay: 0 };
  // در هوا: حل دقیق (جاذبه ثابت، مقاومت هوای خطی)
  for (let n = 0; n < 4; n++) {
    const ex = Math.exp(-c * seg), ew = Math.exp(-cw * seg);
    if (rec) for (; nf < t + seg; nf += 1 / 60) {
      const q = nf - t, e1 = (1 - Math.exp(-c * q)) / c;
      frames.push({ t: nf, x: x + vx * e1, y: y + vy * e1, h: Math.max(0, h + vz * q - AIR_G * q * q / 2), a: a + w * (1 - Math.exp(-cw * q)) / cw });
    }
    x += vx * (1 - ex) / c; y += vy * (1 - ex) / c; a += w * (1 - ew) / cw;
    vx *= ex; vy *= ex; w *= ew; t += seg;
    const vin = AIR_G * seg - vz;        // سرعت رو به پایین هنگام برخورد
    b.x = x; b.y = y; b.a = a;
    const u = under(o.B, b), e = .08 + .2 * o.P, vh = Math.hypot(vx, vy);
    const dv = Math.min(vh * .75, IMPACT * (1 + e) * vin), f = vh ? (vh - dv) / vh : 0;
    vx *= f; vy *= f; w *= .7;
    lands.push({ t, v: vin, on: !!u, vh: vh - dv });
    vz = e * vin; h = 0;
    if (vz < 60) break;
    seg = 2 * vz / AIR_G;                // جهش کوتاه
  }
  // روی میز: همان فیزیک سُر خوردن
  Object.assign(b, { x, y, a, vx, vy, w });
  const t0 = t;
  while (t - t0 < maxGround) {
    slide(b, under(o.B, b), env, dt);
    if (o.box) rail(b, o.box, null);
    t += dt;
    if (rec && t >= nf) { frames.push({ t, x: b.x, y: b.y, h: 0, a: b.a }); nf += 1 / 60; }
    if (!b.vx && !b.vy && !b.w) break;
  }
  if (rec && (!frames.length || frames[frames.length - 1].t < t)) frames.push({ t, x: b.x, y: b.y, h: 0, a: b.a });
  return { x: b.x, y: b.y, a: b.a, vx: b.vx, vy: b.vy, w: b.w, t, lands, frames };
}
/* روی میز صاف: نقطهٔ برخورد و سرعت چرخش تا برگ در (tx,ty) با زاویهٔ a1 بایستد.
   جای ایستادن با جای برخورد پیوسته ولی تند عوض می شود (روی برگ دیگر لغزنده تر است)، پس فاصلهٔ
   سُر خوردن در امتداد پرتاب با دونیم کردن پیدا می شود، بعد خطای کناری و در آخر چرخش. */
function aim(o) {
  const dx = o.tx - o.sx, dy = o.ty - o.sy, d = Math.hypot(dx, dy) || 1, ux = dx / d, uy = dy / d;
  const run = (lx, ly, w) => fly(o, lx, ly, w, LEVEL, false, 1 / 120, 3);
  let lo = 0, hi = Math.min(d * .8, 320), side = 0, s = 0;
  const at = q => [o.tx - ux * q - uy * side, o.ty - uy * q + ux * side];
  for (let i = 0; i < 20; i++) {
    s = (lo + hi) / 2;
    const r = run(...at(s), 0);
    if ((r.x - o.tx) * ux + (r.y - o.ty) * uy > 0) lo = s; else hi = s;
  }
  for (let i = 0; i < 2; i++) { const r = run(...at(s), 0); side -= -(r.x - o.tx) * uy + (r.y - o.ty) * ux; }
  const [lx, ly] = at(s);
  let a = -90, b = 90;
  for (let i = 0; i < 18; i++) { const m = (a + b) / 2; if (run(lx, ly, m).a < o.a1) a = m; else b = m; }
  return { lx, ly, w0: (a + b) / 2 };
}

window.CardPhysics = { G, PX, W, H, FELT, CARD, LEVEL, on, under, step, rail, fly, aim };
})();
