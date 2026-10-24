/* لشگر کاغذی — صفحهٔ جنگ (طرح «میز مدرسه»). وضعیت از سرور می آید (game_club/lashgar.py) و نقاشی جدا
   (lashgar/ink) تا هر poll سبک بماند.
   مرحله ها: اسم لشگر ← چیدن نیروها و نقاشی ← «آماده‌ام» ← جنگ ← پایان.
   - مداد را با یک انگشت می بری و سرش کمی بالای انگشت است تا دیده شود؛ فقط وقتی دکمهٔ گرد «رنگ کن» را
     نگه داشته ای رنگ می دهد (یک ضربهٔ کوتاه روشنش نگه می دارد، ضربهٔ بعد خاموش). پاک کن هم همین طور.
   - نیروها را از سینی می کشی روی برگه (نیرو هم کمی بالای انگشت می آید)؛ با لمس، می چرخد یا برمی گردد.
   - جنگ: نقطه را با مداد قرمز روی نیمهٔ خودت می گذاری، برگه را از دستهٔ پایین می کشی بالا (هر چه صاف تر،
     دقیق تر) و از پشت روی نقطه نگه می داری تا پررنگ شود؛ رد قرینه روی نیمهٔ حریف می افتد.
   بیرون از تلگرام یک جنگ نمونه با حریف ساختگی پخش می شود (demo-lashgar.js). */
(() => {
const { FD, store, icon, sheet, close, toast, sfx, haptic, errText, face } = GC;
const $ = id => document.getElementById(id);
const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
const API = GC.live ? GC.lashgar : window.LgDemo;

/* ---------- همان ثابت های سرور (lashgar.py) ---------- */
const W = 1000, H = 700, UNIT_S = 2.8, MARK_R = 12;
const KINDS = ['sol', 'tank', 'gun', 'heli', 'flag'];
const KIND_FA = { sol: 'سرباز', tank: 'تانک', gun: 'توپ', heli: 'هلیکوپتر', flag: 'پرچم' };
const REACH = { sol: 37.6, tank: 78.5, gun: 59.0, heli: 87.7, flag: 68.1 };
const EDGE = 0.6, SPREAD = 0.62, FOLD_MAX = 8, FOLD_K = 0.5;
const VB = { sol: '-10 -14 20 28', tank: '-24 -15 49 28', gun: '-13 -13 32 26', heli: '-19 -13 50 26', flag: '-3 -17 23 31' };
// مدادها (اسم، رنگ بدنه، رنگ نوک) و ضخامت ها؛ همان PENCILS و WIDTHS در lashgar_art.py
const PENCILS = [['مداد سیاه', '#3D3D3D', '#2A2A2A'], ['قرمز', '#C8323C', '#A8202A'], ['نارنجی', '#E07B24', '#B95F12'], ['زرد', '#E8B422', '#B98A0E'],
  ['سبز', '#3E8E3A', '#2F7A2F'], ['آبی', '#1F5FC8', '#1A4FB0'], ['قهوه‌ای', '#8A5A2B', '#6E4520']];
const WIDTHS = [4, 7, 12, 20], PEN_W = 1, ERASE_W = 2, STROKE_MAX = 380;
const TIP = { x: -26, y: -64 };      // سر مداد نسبت به انگشت (پیکسل صفحه)
const LIFT = -54;                    // نیرویی که جابه جا می شود، بالای انگشت
const COLORS = { 0: '#2F7BF6', 1: '#EF4136' };
const ARMY_A = ['لشگر', 'گردان', 'تیپ', 'یگان', 'گروهان'];
const ARMY_B = ['شیرها', 'عقاب‌ها', 'نیمکت آخر', 'زنگ تفریح', 'مداد سیاه‌ها', 'پاک‌کن دورنگ', 'کلاس پنجم', 'تخته‌سیاه', 'گچ‌های رنگی', 'دفتر مشق', 'جامدادی‌ها', 'پلنگ‌ها', 'ستاره‌ها', 'ساندویچ کالباس'];
const SUGGEST = ['شیرهای کلاس پنجم', 'گردان نیمکت آخر', 'تیپ زنگ تفریح', 'لشگر مداد سیاه‌ها', 'یگان پاک‌کن دورنگ'];
const QUICK = ['ای ول!', 'چه شلیکی!', 'نوبت توئه، بزن!', 'آخ!', 'دمت گرم', 'صاف تا کن 😄'];
const CLOCK_C = 56.55, PRESS_C = 163.4, PRESS_MS = 900;

/* ---------- وضعیت ---------- */
const watchMid = GC.watchId();
let mid = watchMid || store.get('lgmid', null), WATCH = false, snap = null, since = 0, pollT = 0, busy = false, overShown = false;
let s = 0.36, strip = 130, dpr = Math.min(2, window.devicePixelRatio || 1), layout = '';
let units = null, unitsT = 0, unitsWait = null, unitsSent = '';
const ink = { 0: [], 1: [] };
let inkFor = '';
let tool = null, tab = 'units', pen = null, penFinger = null, painting = false, lock = false, stroke = null, lastScratch = 0;
const queue = [];
let sending = null, inkErr = 0;
let sel = -1, drag = null;
let aim = null, fold = { st: 'flat', a: 0 }, pressT = 0, pressStart = 0;
let shown = -1, fresh = false, animating = false, applying = Promise.resolve(), deadlineAt = 0, readyAt = 0, lastTick = -1, lastDock = '';
let chat = null;
const G = () => snap && snap.game;
const me = () => (G() && !WATCH ? G().me : null);
const botC = () => me() || (G() ? G().order[0] : '0');
const topC = () => (G() ? G().order.find(c => c !== botC()) : '1');
const P = c => G().players[c];
const armyOf = c => (G() && P(c) && P(c).army) || (c === me() ? 'لشگر تو' : 'حریف');
const nameOf = c => (c === me() ? 'تو' : `<span class="uname">${esc(P(c).name)}</span>`);
const total = () => (G() ? Object.values(G().army).reduce((a, b) => a + b, 0) : 11);
const phase = () => (G() ? G().phase : '');
const myTurn = () => G() && G().turn && G().turn === me();
const sheetEl = $('sheet'), view = $('view'), clip = $('clip');

/* ---------- چیدمان برگه: مرحلهٔ چیدن فقط نیمهٔ خودم و لبهٔ دفتر؛ جنگ کل برگه ---------- */
let fitLater = false;
function fit(force, soft) {
  if (soft && (fold.st !== 'flat' || animating || gripD)) { fitLater = true; return; }
  fitLater = false;
  const stage = $('stage');
  const want = phase() === 'draw' && !WATCH ? 'draw' : 'full';
  const sw = stage.clientWidth, sh = Math.max(160, stage.clientHeight - 8), sW = (Math.min(sw, 560) - 28) / W;
  document.body.classList.toggle('h700', innerHeight < 760);
  document.body.classList.toggle('h640', innerHeight < 680);
  // چیدن: نیمهٔ خودم و هر قدر جا بود از لبهٔ دفتر روی نیمهٔ حریف (اسم لشگرش و «داره می‌کشه…»)
  strip = want === 'draw' ? Math.round(Math.max(130, Math.min(300, sh / sW - H))) : 0;
  const visH = want === 'draw' ? H + strip : 2 * H;
  let ns = Math.max(0.12, Math.min(sW, sh / visH));
  // فقط کارت پایین عوض شده: برای تغییر کوچک، برگه همان اندازه می ماند (بی پرش و بی کشیدن دوبارهٔ نقاشی)
  if (soft && want === layout && Math.abs(ns - s) / s < 0.06) ns = s;
  const changed = force || ns !== s || want !== layout;
  if (want !== layout && layout) sheetEl.classList.remove('instant'); else sheetEl.classList.add('instant');
  s = ns; layout = want;
  const vw = W * s, vh = visH * s, M = want === 'draw' ? 16 : 0;
  view.style.width = vw + 'px'; view.style.height = vh + 'px';
  clip.classList.toggle('draw', want === 'draw');
  Object.assign(clip.style, { left: -M + 'px', top: '0px', width: vw + 2 * M + 'px', height: vh + M + 'px' });
  sheetEl.style.transform = `translate(${M}px, ${want === 'draw' ? -(H - strip) * s : 0}px) scale(${s})`;
  if (changed) { sizeCanvas('0'); sizeCanvas('1'); }
  placeOverlays();
  if (G()) turnUi(true);
}
GC.onFit(() => fit());
// کارت پایین (ابزار، نوبت، نتیجه) که بلند و کوتاه شود، برگه دوباره اندازه می شود
if (window.ResizeObserver) new ResizeObserver(() => { if (layout) fit(false, true); }).observe($('dock'));
const sheetRect = () => sheetEl.getBoundingClientRect();
// نقطهٔ صفحه ← مختصات نیمهٔ پایین (y فاصله از خط وسط)
function toBot(cx, cy) { const r = sheetRect(), k = r.width / W; return { x: (cx - r.left) / k, y: (cy - r.top) / k - H }; }
// نقطهٔ نیمهٔ color (مختصات خودش) ← پیکسل نسبت به view
function toView(c, x, y) {
  const r = sheetRect(), v = view.getBoundingClientRect(), k = r.width / W;
  const sx = c === botC() ? x : W - x, sy = c === botC() ? H + y : H - y;
  return { x: r.left - v.left + sx * k, y: r.top - v.top + sy * k };
}

/* ---------- نقاشی: بوم هر نیمه با بافت مداد ---------- */
function canvasOf(c) { return c === botC() ? $('cBot') : $('cTop'); }
function sizeCanvas(c) {
  const el = canvasOf(c), w = Math.round(W * s * dpr), h = Math.round(H * s * dpr);
  if (el.width !== w || el.height !== h) { el.width = w; el.height = h; el._pat = null; }
  redraw(c);
}
function hex(h) { const n = parseInt(h.slice(1), 16); return [n >> 16 & 255, n >> 8 & 255, n & 255]; }
function pat(ctx, c) {
  ctx._pat = ctx._pat || {};
  if (ctx._pat[c]) return ctx._pat[c];
  const t = document.createElement('canvas'); t.width = t.height = 24;
  const x = t.getContext('2d'), img = x.createImageData(24, 24), [r, g, b] = hex(PENCILS[c] ? PENCILS[c][1] : '#3D3D3D');
  for (let i = 0; i < img.data.length; i += 4) { img.data[i] = r; img.data[i + 1] = g; img.data[i + 2] = b; img.data[i + 3] = 120 + Math.random() * 135; }
  x.putImageData(img, 0, 0);
  return (ctx._pat[c] = ctx.createPattern(t, 'repeat'));
}
function ctxOf(c) { const el = canvasOf(c), ctx = el.getContext('2d'); ctx.setTransform(el.width / W, 0, 0, el.height / H, 0, 0); return ctx; }
function strokeStyle(ctx, st) {
  ctx.globalCompositeOperation = st.e ? 'destination-out' : 'source-over';
  ctx.strokeStyle = ctx.fillStyle = st.e ? '#000' : pat(ctx, st.c);
  ctx.lineWidth = WIDTHS[st.w] * (st.e ? 2.2 : 1); ctx.lineCap = 'round'; ctx.lineJoin = 'round';
}
function drawStroke(ctx, st) {
  const p = st.p; if (!p || p.length < 2) return;
  ctx.save(); strokeStyle(ctx, st); ctx.beginPath(); ctx.moveTo(p[0], p[1]);
  if (p.length === 2) ctx.lineTo(p[0] + 0.1, p[1] + 0.1);
  else {
    for (let i = 2; i < p.length - 2; i += 2) ctx.quadraticCurveTo(p[i], p[i + 1], (p[i] + p[i + 2]) / 2, (p[i + 1] + p[i + 3]) / 2);
    ctx.lineTo(p[p.length - 2], p[p.length - 1]);
  }
  ctx.stroke(); ctx.restore();
}
function redraw(c) {
  const ctx = ctxOf(c); ctx.clearRect(0, 0, W, H);
  for (const st of ink[c]) drawStroke(ctx, st);
  if (stroke && c === me()) drawStroke(ctx, stroke);
}
// کارهای نقاشی به ترتیب و یکی یکی می روند (حداکثر چند خط در هر درخواست، زیر سقف بدنهٔ سرور)
function enqueue(op) { queue.push(op); flushInk(); }
function flushInk() {
  if (sending || !queue.length || !mid) return sending;
  const batch = [];
  let size = 0;
  while (queue.length && batch.length < 20) {
    const n = queue[0].op === 's' ? queue[0].s.p.length * 4.4 + 40 : 12;
    if (batch.length && size + n > 6600) break;
    batch.push(queue.shift()); size += n;
  }
  sending = (async () => {
    try { await API.ink(mid, batch.map(o => (o.op === 's' ? { op: 's', s: { c: o.s.c, w: o.s.w, e: o.s.e, p: o.s.p } } : { op: o.op }))); inkErr = 0; }
    catch (e) {
      if (['is_ready', 'not_draw', 'not_found', 'bad_ink'].includes(e.code)) { queue.length = 0; }
      else if (e.code === 'ink_full') { toast(errText(e)); }
      else { queue.unshift(...batch); inkErr++; await GC.sleep(Math.min(8000, 900 * inkErr)); }
    }
    sending = null;
    if (queue.length) flushInk();
  })();
  return sending;
}
async function inkSettled() { for (let i = 0; i < 40 && (sending || queue.length); i++) { flushInk(); await (sending || GC.sleep(60)); } }
// خط ها از سرور: در چیدن فقط مال خودم (مثلا بعد از باز کردن دوبارهٔ صفحه)، از شروع جنگ هر دو
async function loadInk() {
  const want = phase() === 'draw' ? (WATCH ? 'none' : 'draw:' + me()) : 'all';
  if (want === inkFor || want === 'none') return;
  inkFor = want;
  const got = { 0: [], 1: [] };
  let v = 0;
  try {
    for (let i = 0; i < 30; i++) {
      const r = await API.inkGet(mid, v, true);
      for (const o of r.ops || []) if (o.op === 's' && got[o.c]) got[o.c].push(Object.assign({ id: o.id }, o.s));
      v = r.v;
      if (!r.more) break;
    }
  } catch (e) { inkFor = ''; return; }
  for (const c of ['0', '1']) if (want === 'all' || c === me()) { ink[c] = got[c]; redraw(c); }
}

/* ---------- نیروها ---------- */
const sym = (u, extra = '') => `<g class="lg-u${extra}" transform="translate(${u.x} ${u.y}) rotate(${u.r || 0}) scale(${UNIT_S})">${u.k === 'flag' ? `<path class="fl" d="M0 -16H17V-4H0Z" fill="${COLORS[u.c] || COLORS[0]}"/>` : ''}<use href="#u-${u.k}"/></g>`;
const left = () => { const n = Object.assign({}, G().army); for (const u of units || []) n[u.k]--; return n; };
function okAt(list, u, skip) {
  const m = REACH[u.k] * EDGE;
  if (u.x < m || u.x > W - m || u.y < m || u.y > H - m) return false;
  return list.every((v, i) => i === skip || Math.hypot(u.x - v.x, u.y - v.y) >= (REACH[u.k] + REACH[v.k]) * SPREAD);
}
function freeSpot(k, list) {
  for (let t = 0; t < 600; t++) {
    const m = REACH[k] * EDGE, u = { k, x: Math.round(m + Math.random() * (W - 2 * m)), y: Math.round(m + Math.random() * (H - 2 * m)), r: 0 };
    if (okAt(list, u, -1)) return u;
  }
  return null;
}
function saveUnits(now) {
  clearTimeout(unitsT);
  const go = async () => {
    const body = JSON.stringify(units);
    if (body === unitsSent) return;
    try { await API.units(mid, units.map(u => ({ k: u.k, x: u.x, y: u.y, r: u.r || 0 }))); unitsSent = body; }
    catch (e) { if (!['is_ready', 'not_draw'].includes(e.code)) { toast(errText(e)); unitsT = setTimeout(() => saveUnits(true), 2500); } }
  };
  if (now) return (unitsWait = go());
  unitsT = setTimeout(() => { unitsWait = go(); }, 450);
}
// ردها و ضربدرها: فقط شلیک هایی که تا اینجا نشان داده شده اند
function marksOf(c) {
  const g = G(), list = g.shots.slice(0, shown < 0 ? g.shots.length : shown).filter(x => x.by !== c), dead = new Set();
  for (const x of list) for (const i of x.hit || []) dead.add(i);
  return { list, dead };
}
function halfSvg(c) {
  const g = G(), p = P(c), mineDraw = c === me() && phase() === 'draw';
  const list = mineDraw ? units || [] : p.units || [];
  if (!list.length && !mineDraw) return '';
  const { list: shots, dead } = mineDraw ? { list: [], dead: new Set() } : marksOf(c);
  const newest = shown > 0 && g.shots[shown - 1] && g.shots[shown - 1].by !== c ? g.shots[shown - 1] : null;
  let out = `<g>${list.map((u, i) => (drag && drag.i === i && mineDraw ? '' : sym(Object.assign({ c }, u), (dead.has(i) ? ' dead' : '') + (mineDraw && sel === i ? ' pick' : '')))).join('')}</g>`;
  out += shots.map(x => x.off ? '' : `<circle class="lg-mark${x.hit && x.hit.length ? '' : ' miss'}${x === newest && fresh ? ' new' : ''}" cx="${x.x}" cy="${x.y}" r="${MARK_R}"/>`).join('');
  out += [...dead].map(i => {
    const u = list[i]; if (!u) return '';
    const k = REACH[u.k] * 0.5, isNew = newest && fresh && (newest.hit || []).includes(i);
    return `<path class="lg-x${isNew ? ' new' : ''}" d="M${u.x - k} ${u.y - k * 0.72}L${u.x + k} ${u.y + k * 0.72}M${u.x - k} ${u.y + k * 0.72}L${u.x + k} ${u.y - k * 0.72}"/>`;
  }).join('');
  return out;
}
// نقطهٔ نشانه روی لایهٔ خودش: کشیدن انگشت فقط دو دایره را جابه جا می کند، نه کل نیروها
function drawAim() {
  const on = !!(aim && phase() === 'battle' && myTurn()), x = on ? aim.x : -99, y = on ? aim.y : -99;
  for (const id of ['aimRing', 'aimDot']) { const el = $(id); el.setAttribute('cx', x); el.setAttribute('cy', y); }
}
function renderSheet() {
  if (!G()) return;
  $('sBot').innerHTML = halfSvg(botC());
  $('sTop').innerHTML = halfSvg(topC());
  drawAim();
  fresh = false;
}

/* ---------- مداد در دست ---------- */
function penSvg(t) {
  if (t && t.k === 'eraser') return '<svg viewBox="0 0 28 156" aria-hidden="true"><g class="tip"><rect x="2" y="0" width="24" height="26" rx="5" fill="#D64541"/><rect x="2" y="22" width="24" height="26" rx="5" fill="#2F6FBF"/><rect x="2" y="20" width="24" height="6" fill="#2F6FBF"/><rect x="5" y="3" width="4" height="40" rx="2" fill="#fff" opacity=".25"/></g></svg>';
  const c = t && t.k === 'pen' ? t.c : 1, [, body, lead] = PENCILS[c];
  return `<svg viewBox="0 0 28 156" aria-hidden="true"><g class="tip"><path d="M14 0L22 28H6Z" fill="#E9C9A0"/><path d="M14 0L16.9 9.8H11.1Z" fill="${lead}"/></g><path d="M6 28q2.67-4 5.33 0t5.33 0t5.34 0V33H6Z" fill="${body}"/><rect x="6" y="30" width="16" height="126" fill="${body}"/><rect x="11" y="30" width="4.5" height="126" fill="#fff" opacity=".24"/><rect x="18" y="30" width="4" height="126" fill="#000" opacity=".14"/><rect x="6" y="150" width="16" height="6" fill="rgba(0,0,0,.25)"/></svg>`;
}
function penKind() { return phase() === 'battle' ? { k: 'aim' } : tool; }
function placePen() {
  const el = $('pen'), t = penKind();
  const on = !!(pen && t && (phase() === 'draw' ? tool : myTurn() && fold.st === 'flat'));
  el.hidden = !on;
  if (!on) return;
  const key = t.k + (t.c != null ? t.c : '');
  if (el.dataset.k !== key) { el.dataset.k = key; el.innerHTML = penSvg(t); }
  const v = toView(botC(), pen.x, pen.y);
  el.style.transform = `translate(${v.x - 14}px, ${v.y}px) rotate(-22deg)`;
  el.classList.toggle('on', painting);
}
function clampHalf(p) { return { x: Math.max(0, Math.min(W, p.x)), y: Math.max(0, Math.min(H, p.y)) }; }
function penFrom(e) { return clampHalf(toBot(e.clientX + TIP.x, e.clientY + TIP.y)); }
function beginStroke() {
  if (!tool || !pen) return;
  stroke = tool.k === 'eraser' ? { c: 0, w: ERASE_W, e: 1, p: [Math.round(pen.x), Math.round(pen.y)] } : { c: tool.c, w: PEN_W, e: 0, p: [Math.round(pen.x), Math.round(pen.y)] };
  const ctx = ctxOf(me()); drawStroke(ctx, stroke);
}
function extendStroke(p) {
  if (!stroke) return beginStroke();
  const n = stroke.p.length, lx = stroke.p[n - 2], ly = stroke.p[n - 1];
  if (Math.hypot(p.x - lx, p.y - ly) < 2.2) return;
  const x = Math.round(p.x), y = Math.round(p.y), ctx = ctxOf(me());
  ctx.save(); strokeStyle(ctx, stroke); ctx.beginPath(); ctx.moveTo(lx, ly); ctx.lineTo(x, y); ctx.stroke(); ctx.restore();
  stroke.p.push(x, y);
  const now = performance.now();
  if (now - lastScratch > 70) { lastScratch = now; sfx.paper.scratch(stroke.e ? 0.3 : 0.6); }
  if (stroke.p.length >= STROKE_MAX * 2) { endStroke(); beginStroke(); }
}
function endStroke() {
  if (!stroke) return;
  const st = stroke; stroke = null;
  ink[me()].push(st);
  enqueue({ op: 's', s: st });
  renderTools();
}
function startPaint() { if (painting) return; painting = true; if (pen && penFinger != null) beginStroke(); haptic('light'); renderPaint(); placePen(); }
function stopPaint() { painting = false; lock = false; endStroke(); renderPaint(); placePen(); }
function undo() {
  if (stroke) endStroke();
  const mine = ink[me()];
  if (!mine.length) return toast('چیزی برای برگردوندن نیست');
  mine.pop(); redraw(me());
  const q = queue.length && queue[queue.length - 1];
  if (q && q.op === 's' && !sending) queue.pop(); else enqueue({ op: 'u' });
  sfx.tap(); renderTools();
}
function setTool(t) {
  if (painting) stopPaint();
  tool = t; sel = -1;
  if (t && !pen) pen = { x: W / 2, y: H * 0.45 };
  renderSheet(); renderTools(); placePen(); placeOverlays();
}

/* ---------- لمس روی برگه ---------- */
view.addEventListener('pointerdown', e => {
  if (!G() || WATCH || e.target.closest('.lg-sel,.lg-grip')) return;
  const ph = phase();
  if (ph === 'draw' && !P(me()).ready) {
    if (tool) {
      e.preventDefault(); view.setPointerCapture(e.pointerId); penFinger = e.pointerId;
      if (stroke) endStroke();
      pen = penFrom(e); if (painting) beginStroke(); placePen();
      return;
    }
    const p = toBot(e.clientX, e.clientY), i = hitUnit(p);
    if (i < 0) { if (sel >= 0) { sel = -1; renderSheet(); placeOverlays(); } return; }
    e.preventDefault(); view.setPointerCapture(e.pointerId);
    drag = { i, k: units[i].k, r: units[i].r || 0, x0: e.clientX, y0: e.clientY, from: Object.assign({}, units[i]), moved: false, id: e.pointerId };
    moveDrag(e);
    return;
  }
  if (ph === 'battle' && myTurn() && fold.st === 'flat' && !animating) {
    e.preventDefault(); view.setPointerCapture(e.pointerId); penFinger = e.pointerId;
    pen = penFrom(e); aim = { x: Math.round(pen.x), y: Math.round(pen.y) }; drawAim(); placeOverlays(); renderDock();
    return;
  }
  if (ph === 'battle' && fold.st === 'folded') { const g = ghostView(); if (g && Math.hypot(e.clientX - g.cx, e.clientY - g.cy) < 90) { e.preventDefault(); view.setPointerCapture(e.pointerId); pressOn(); } }
});
view.addEventListener('pointermove', e => {
  if (drag && drag.id === e.pointerId) { moveDrag(e); return; }
  if (penFinger !== e.pointerId) return;
  const p = penFrom(e);
  if (phase() === 'battle') { if (myTurn() && fold.st === 'flat' && !animating) { pen = p; aim = { x: Math.round(p.x), y: Math.round(p.y) }; drawAim(); placeOverlays(); } return; }
  pen = p; if (painting) extendStroke(p); placePen();
});
const upView = e => {
  if (drag && drag.id === e.pointerId) return dropDrag(e);
  if (fold.st === 'pressing') pressOff();
  if (penFinger === e.pointerId) { penFinger = null; if (stroke) endStroke(); if (phase() === 'battle' && aim) { sfx.tap(); renderDock(); placeOverlays(); } }
};
view.addEventListener('pointerup', upView);
view.addEventListener('pointercancel', upView);
function hitUnit(p) {
  let best = -1, bd = 1e9;
  (units || []).forEach((u, i) => { const d = Math.hypot(u.x - p.x, u.y - p.y); if (d < REACH[u.k] * 0.75 && d < bd) { best = i; bd = d; } });
  return best;
}
// نیروی در حال کشیدن (از سینی یا روی برگه): کمی بالای انگشت؛ آبی = جای درست، قرمز = نمی شود
function moveDrag(e) {
  const p = toBot(e.clientX, e.clientY + LIFT);
  drag.moved = drag.moved || Math.hypot(e.clientX - drag.x0, e.clientY - drag.y0) > 7;
  drag.u = { k: drag.k, x: Math.round(p.x), y: Math.round(p.y), r: drag.r };
  drag.ok = okAt(units, drag.u, drag.i == null ? -1 : drag.i);
  const v = toView(botC(), drag.u.x, drag.u.y), k = s * UNIT_S;
  $('drag').innerHTML = drag.moved || drag.i == null ? `<g transform="translate(${v.x} ${v.y}) rotate(${drag.r}) scale(${k})"><g class="lg-u ${drag.ok ? 'pick' : 'bad'}" style="stroke-width:${1.6}">${drag.k === 'flag' ? `<path class="fl" d="M0 -16H17V-4H0Z" fill="${COLORS[me()]}"/>` : ''}<use href="#u-${drag.k}"/></g></g>` : '';
  if (drag.i != null && drag.moved && !drag.hid) { drag.hid = true; sel = -1; renderSheet(); placeOverlays(); }
}
function dropDrag(e) {
  const d = drag; drag = null; $('drag').innerHTML = '';
  if (d.i != null) {
    if (!d.moved) { sel = sel === d.i ? -1 : d.i; sfx.tap(); }
    else if (d.ok) { units[d.i] = d.u; sel = d.i; sfx.paper.press(); saveUnits(); }
    else { toast(d.u.y < 0 ? 'نیرو باید روی نیمهٔ خودت باشه' : 'اینجا جا نمی‌شه؛ نیروها روی هم نیفتن'); sfx.error(); }
  } else if (!d.moved) { autoOne(d.k); }
  else if (d.ok) { units.push(d.u); sel = units.length - 1; sfx.paper.press(); haptic('light'); saveUnits(); }
  else { toast(d.u.y < -20 ? 'نیرو رو روی نیمهٔ خودت بذار' : 'اینجا جا نمی‌شه؛ یه جای خالی‌تر'); sfx.error(); }
  renderSheet(); renderTools(); placeOverlays();
}
function autoOne(k) {
  const u = freeSpot(k, units);
  if (!u) return toast('دیگه جای خالی نیست؛ نیروها رو جابه‌جا کن');
  units.push(u); sel = units.length - 1; sfx.paper.press(); saveUnits(); renderSheet(); renderTools(); placeOverlays();
}
function autoAll() {
  const n = left();
  for (const k of ['heli', 'tank', 'gun', 'flag', 'sol']) for (let i = 0; i < n[k]; i++) { const u = freeSpot(k, units); if (u) units.push(u); }
  sel = -1; sfx.paper.press(); haptic('success'); saveUnits(); renderSheet(); renderTools(); placeOverlays();
}
$('selRot').onclick = e => { e.stopPropagation(); const u = units[sel]; if (!u) return; const nu = Object.assign({}, u, { r: ((u.r || 0) + 45) % 360 }); if (okAt(units, nu, sel)) { units[sel] = nu; saveUnits(); sfx.tap(); } else { toast('این‌جا نمی‌چرخه؛ جاش تنگه'); sfx.error(); } renderSheet(); placeOverlays(); };
$('selDel').onclick = e => { e.stopPropagation(); if (sel < 0) return; units.splice(sel, 1); sel = -1; saveUnits(); sfx.tap(); renderSheet(); renderTools(); placeOverlays(); };

/* ---------- جای دکمه های روی برگه (دستگیرهٔ نیرو، دستهٔ تا، حلقهٔ فشار) ---------- */
function ghostView() {
  if (!aim) return null;
  // وقتی برگه تا شده، جای واقعی لک روی صفحه (با کجی تا)؛ وگرنه قرینهٔ ساده
  const gh = fold.st !== 'flat' && $('bBot').querySelector('.ghost'), gr = gh && gh.getBoundingClientRect();
  if (gr && gr.width) return { cx: gr.left + gr.width / 2, cy: gr.top + gr.height / 2 };
  const r = sheetRect(), k = r.width / W;
  return { cx: r.left + aim.x * k, cy: r.top + (H - aim.y) * k };
}
function placeOverlays() {
  const sl = $('sel');
  if (sel >= 0 && units && units[sel] && phase() === 'draw' && !tool && !drag) {
    const u = units[sel], v = toView(botC(), u.x, u.y - REACH[u.k] * 0.62);
    sl.hidden = false; sl.style.left = v.x + 'px'; sl.style.top = Math.max(18, v.y) + 'px';
  } else sl.hidden = true;
  const gr = $('grip'), on = phase() === 'battle' && myTurn() && !!aim && fold.st === 'flat' && !G().over;
  gr.hidden = !on;
  if (on) { const v = toView(botC(), W / 2, H); gr.style.left = v.x + 'px'; gr.style.top = v.y + 'px'; }
  const pr = $('press'), pg = fold.st === 'folded' || fold.st === 'pressing' ? ghostView() : null;
  pr.hidden = !pg;
  if (pg) { const vr = view.getBoundingClientRect(); pr.style.left = pg.cx - vr.left + 'px'; pr.style.top = pg.cy - vr.top + 'px'; }
  placePen();
}

/* ---------- تا کردن برگه و فشار از پشت ---------- */
const flap = c => (c === botC() ? $('fBot') : $('fTop'));
const half = c => (c === botC() ? $('hBot') : $('hTop'));
function backFace(c, ax, ay) {
  // پشت برگه: نقاشی و نیروهای همان نیمه کم رنگ و قرینه (از پشت کاغذ پیداست) + لک نقطهٔ قرمز
  const b = c === botC() ? $('bBot') : $('bTop'), list = (c === me() && phase() === 'draw' ? units : P(c).units) || [];
  b.innerHTML = `<canvas class="thru"></canvas><svg class="thru" viewBox="0 0 1000 700" preserveAspectRatio="none"><g>${list.map(u => sym(Object.assign({ c }, u))).join('')}</g></svg>`;
  const t = b.querySelector('canvas'), src = canvasOf(c);
  t.width = src.width; t.height = src.height;
  try { t.getContext('2d').drawImage(src, 0, 0); } catch (e) {}     // برگرداندنش با CSS (.thru)
  if (ax != null) {
    const g = document.createElement('div'); g.className = 'ghost';
    Object.assign(g.style, c === botC() ? { left: ax + 'px', top: H - ay + 'px' } : { left: W - ax + 'px', top: ay + 'px' });
    b.appendChild(g);
  }
}
function setFold(c, deg, a, cls) {
  const f = flap(c), sign = c === botC() ? 1 : -1, th = Math.max(-FOLD_MAX, Math.min(FOLD_MAX, a || 0)) * FOLD_K;
  f.classList.toggle('drag', cls === 'drag'); f.classList.toggle('slow', cls === 'slow');
  // بلند شدن و «تا شده» همین حالا؛ پایین آمدنشان بعد از تمام شدن باز شدن (foldTo)
  if (deg > 1 || cls === 'drag') half(c).classList.toggle('lift', deg > 1);
  if (deg > 90 || cls === 'drag') sheetEl.classList.toggle('folded', deg > 90);
  // تا روی خطی که th درجه کج است: در ۱۸۰ درجه همان قرینهٔ چرخیده (۲th دور وسط خط) که سرور حساب می کند
  f.style.transform = deg > 0.1 ? `rotateZ(${th}deg) rotateX(${sign * deg}deg) rotateZ(${-th}deg)` : '';
}
const wait = ms => new Promise(r => setTimeout(r, ms));
async function foldTo(c, deg, a, ms = 620) {
  setFold(c, deg, a, ms > 700 ? 'slow' : ''); await wait(ms);
  if (deg <= 90) { sheetEl.classList.remove('folded'); half(c).classList.remove('lift'); }   // میز زیر برگه تا آخر باز شدن پیدا بماند
}
// دستهٔ پایین را بکش بالا: هر چه صاف تر، کجی کمتر
let gripD = null;
$('grip').addEventListener('pointerdown', e => {
  if (!aim || !myTurn() || fold.st !== 'flat') return;
  e.preventDefault(); e.stopPropagation(); $('grip').setPointerCapture(e.pointerId); $('grip').classList.add('held');
  gripD = { x0: e.clientX, y0: e.clientY, id: e.pointerId, a: 0, p: 0 };
  backFace(botC(), aim.x, aim.y); fold.st = 'drag'; placePen(); sfx.paper.fold();
});
$('grip').addEventListener('pointermove', e => {
  if (!gripD || gripD.id !== e.pointerId) return;
  const dy = gripD.y0 - e.clientY, dx = e.clientX - gripD.x0, hpx = H * sheetRect().width / W;
  gripD.p = Math.max(0, Math.min(1, dy / (hpx * 0.85)));
  if (dy > 18) gripD.a = Math.max(-FOLD_MAX, Math.min(FOLD_MAX, Math.atan2(dx, dy) * 180 / Math.PI));
  setFold(botC(), gripD.p * 180, gripD.a, 'drag');
  $('grip').style.transform = `translate(calc(-50% + ${Math.round(dx)}px), calc(-50% - ${Math.round(Math.max(0, dy))}px))`;
});
const gripUp = async e => {
  if (!gripD || gripD.id !== e.pointerId) return;
  const d = gripD; gripD = null; $('grip').classList.remove('held'); $('grip').style.transform = '';
  if (d.p > 0.5) { fold = { st: 'folding', a: d.a }; await foldTo(botC(), 180, d.a, 360); folded(); }
  else { await foldTo(botC(), 0, 0, 380); fold = { st: 'flat', a: 0 }; placeOverlays(); renderDock(); }
};
$('grip').addEventListener('pointerup', gripUp);
$('grip').addEventListener('pointercancel', gripUp);
async function foldButton() {
  if (!aim || !myTurn() || fold.st !== 'flat') return;
  // دکمه هم مثل دست آدم کمی کج تا می کند
  const a = Math.max(-FOLD_MAX, Math.min(FOLD_MAX, (Math.random() + Math.random() + Math.random() - 1.5) * 2.2));
  fold = { st: 'folding', a }; backFace(botC(), aim.x, aim.y); placePen(); sfx.paper.fold();
  await foldTo(botC(), 180, a, 820); folded();
}
function folded() {
  if (fold.st !== 'folding') return;
  fold.st = 'folded'; haptic('light'); placeOverlays(); renderDock();
}
async function unfoldMine() {
  fold.st = 'folding'; $('press').hidden = true;
  await foldTo(botC(), 0, 0, 560);
  fold = { st: 'flat', a: 0 }; placeOverlays(); renderDock();
  if (fitLater) fit(false, true);
}
function pressOn() {
  if (fold.st !== 'folded') return;
  fold.st = 'pressing'; pressStart = performance.now(); sfx.paper.press(); haptic('light');
  const ring = $('pressRing'), bar = () => document.getElementById('pressBar');
  const step = () => {
    if (fold.st !== 'pressing') return;
    const f = Math.min(1, (performance.now() - pressStart) / PRESS_MS);
    ring.style.strokeDashoffset = PRESS_C * (1 - f);
    const b = bar(); if (b) b.style.transform = `scaleX(${f})`;
    if (f >= 1) { fire(); return; }
    pressT = requestAnimationFrame(step);
  };
  pressT = requestAnimationFrame(step);
}
function pressOff() {
  if (fold.st !== 'pressing') return;
  cancelAnimationFrame(pressT); fold.st = 'folded';
  $('pressRing').style.strokeDashoffset = PRESS_C;
  const b = document.getElementById('pressBar'); if (b) b.style.transform = 'scaleX(0)';
  toast('تا پر نشده ول نکن؛ از اول نگه دار');
}
async function fire() {
  cancelAnimationFrame(pressT);
  fold.st = 'firing'; haptic('heavy'); sfx.paper.press();
  $('pressRing').style.strokeDashoffset = PRESS_C;
  const early = readyAt - performance.now();
  if (early > 0) await wait(early + 250);
  try {
    let r;
    try { r = await API.shoot(mid, aim.x, aim.y, fold.a, since); }
    catch (e) { if (e.code !== 'not_ready') throw e; await wait(700); r = await API.shoot(mid, aim.x, aim.y, fold.a, since); }
    await apply(r);
  } catch (e) {
    sfx.error(); toast(e.code === 'not_ready' ? 'یه لحظه صبر کن، هنوز نوبت شروع نشده' : errText(e));
    if (fold.st === 'firing') await unfoldMine();
  }
}

/* ---------- پخش شلیک ها و رویدادها ---------- */
function popWord(c, x, y, text, miss) {
  const v = toView(c, x, y), el = document.createElement('span');
  el.className = 'w' + (miss ? ' miss' : ''); el.textContent = text;
  el.style.left = v.x + 'px'; el.style.top = v.y + 'px';
  $('pop').appendChild(el); setTimeout(() => el.remove(), 2000);
}
async function playShot(x, idx) {
  const by = x.by, target = G().order.find(c => c !== by), mine = by === me();
  if (mine && (fold.st === 'firing' || fold.st === 'folded')) { await unfoldMine(); }
  else if (!mine) {
    // بقیه: تا شدن نیمهٔ تیرانداز روی نیمهٔ هدف، فشار، باز شدن
    animating = true; $('pen').hidden = true;
    backFace(by, x.ax, x.ay);
    sfx.paper.fold();
    await foldTo(by, 180, x.a, 760);
    sfx.paper.press(); haptic('light');
    await wait(420);
    await foldTo(by, 0, 0, 560);
    animating = false;
  }
  shown = idx + 1; fresh = true; renderSheet();
  const hit = x.hit && x.hit.length, kinds = (x.hit || []).map(i => KIND_FA[(P(target).units[i] || {}).k]).filter(Boolean);
  if (x.off) { popWord(target, Math.max(60, Math.min(W - 60, x.x)), Math.max(40, Math.min(H - 40, x.y)), 'بیرون برگه!', true); sfx.paper.miss(); }
  else if (hit) {
    popWord(target, x.x, x.y, 'خورد!'); sfx.paper.boom(); haptic(target === me() ? 'error' : 'success');
    if (!WATCH) note(target === me() ? `آخ! ${kinds.join(' و ')}ت خورد 😖` : `زدی به ${kinds.join(' و ')} ${esc(armyOf(target))}! 💥`, target === me() ? 'bad' : 'ok');
  } else { popWord(target, x.x, x.y, 'خطا رفت', true); sfx.paper.miss(); if (!WATCH) note(target === me() ? `${esc(armyOf(by))} خطا زد؛ نفس راحت 😅` : 'خطا رفت؛ دفعهٔ بعد صاف‌تر تا کن', ''); }
  if (mine) aim = null;
  await wait(hit ? 900 : 500);
}
let noteMsg = null;
function note(text, kind) { noteMsg = { text, kind, at: Date.now() }; renderDock(); }
async function playEvent(e) {
  const g = G();
  if (e.t === 'battle') { await reveal(e.first); return; }
  if (e.t === 'shot') { const idx = g.shots.findIndex(x => x.n === e.n); if (idx >= 0 && idx >= shown) await playShot(g.shots[idx], idx); return; }
  if (e.t === 'timeout') { toast(e.c === me() ? 'وقتت تموم شد و نوبتت سوخت ⏳' : `نوبت ${armyOf(e.c)} سوخت ⏳`); if (e.c === me()) { aim = null; if (fold.st !== 'flat') await unfoldMine(); } sfx.nomove(); return; }
  if (e.t === 'auto' && e.c !== me()) toast(`${armyOf(e.c)} خیلی معطل کرد؛ نیروهاش خودکار چیده شد`);
  if (e.t === 'auto' && e.c === me()) toast('خیلی معطل کردی؛ بقیهٔ نیروهات خودکار چیده شد');
  if (e.t === 'leave' && e.c !== me()) toast(`${armyOf(e.c)} از جنگ رفت`);
}
// شروع جنگ: دفتر از روی نیمهٔ حریف کنار می رود، کل برگه پیدا می شود و نقاشی هر دو نفر می آید
async function reveal(first, quiet) {
  const cv = $('cover');
  if (layout !== 'draw' && cv.hidden) return;
  if (stroke) endStroke();
  tool = null; painting = false; lock = false; sel = -1; drag = null; $('drag').innerHTML = '';
  if (!quiet) { cv.classList.add('off'); sfx.paper.fold(); await wait(760); }
  cv.hidden = true; cv.classList.remove('off'); pen = null;
  fit(); renderSheet();
  await loadInk();
  if (quiet) return;
  await wait(300);
  shownTurn = '';            // بنر نوبت اول را turnUi با «سکه انداختیم» نشان می دهد
  coinToss = true;
}

/* ---------- نوبت کیست: بنر بزرگ وقتی نوبت عوض می شود، برچسب روی خط وسط، نیمهٔ فعال ---------- */
let shownTurn = '', coinToss = false;
function turnUi(first) {
  const g = G(), t = g && g.phase === 'battle' && !g.over ? g.turn : null, mine = !!(t && t === me());
  view.classList.toggle('my-turn', mine); view.classList.toggle('foe-turn', !!t && !mine && !WATCH);
  const tag = $('turnTag');
  tag.hidden = !t;
  if (t) {
    tag.className = 'lg-tag' + (mine ? '' : ' foe');
    tag.textContent = mine ? '🎯 نوبت تو' : WATCH ? `⏳ نوبت ${armyOf(t)}` : '⏳ نوبت حریف';
    const v = toView(botC(), 0, 0); tag.style.top = v.y + 'px';
  }
  if ((t || '') === shownTurn) return;
  shownTurn = t || '';
  if (!t) return;
  const ban = $('turnBan'), toss = coinToss; coinToss = false;
  const sub = toss ? (mine ? 'سکه انداختیم؛ اول تو شلیک می‌کنی' : 'سکه انداختیم؛ اول حریف شلیک می‌کنه') : mine ? 'یه نقطه روی نیمهٔ خودت بذار' : 'صبر کن تا شلیک کنه…';
  ban.className = 'lg-ban' + (mine ? '' : ' foe');
  ban.innerHTML = `<b>${mine ? 'نوبت توئه! 🎯' : WATCH ? `نوبت ${esc(armyOf(t))}` : `نوبت ${esc(armyOf(t))}`}</b><small>${sub}</small>`;
  void ban.offsetWidth; ban.classList.add('show');
  if (!first || toss) { if (mine) { sfx.turn(); haptic('medium'); } }
}

/* ---------- سربرگ، امتیاز و ساعت ---------- */
function renderHead() {
  const g = G(); if (!g) return;
  const ph = g.phase;
  $('sub').textContent = WATCH ? 'داری تماشا می‌کنی 👀' : g.over ? 'جنگ تموم شد' : ph === 'draw'
    ? (P(me()).army ? `لشگر ${P(me()).army}` : 'اول یه اسم برای لشگرت') : myTurn() ? 'نوبت توئه!' : `نوبت ${armyOf(g.turn)}`;
  const sc = $('score'); sc.hidden = ph === 'draw';
  if (!sc.hidden) {
    sc.innerHTML = [botC(), topC()].map(c => {
      const p = P(c);
      return `<div class="lg-pl${g.turn === c ? ' turn' : ''}${p.out ? ' out' : ''}" style="--c:${COLORS[c]}">${face(p)}
        <span class="t"><b>${esc(p.army || p.name)}</b><small>${c === me() ? 'تو' : esc(p.name)}، ${FD(p.alive)} از ${FD(p.units ? p.units.length : total())} سالم</small></span></div>`;
    }).join('');
  }
}
function tickClock() {
  const g = G(), el = $('clock');
  if (!g) return;
  const on = g.phase === 'battle' && !!g.turn && !g.over;
  el.hidden = !on;
  if (!on) return;
  const now = performance.now(), ms = Math.max(0, deadlineAt - now), wait0 = readyAt > now;
  const sec = Math.ceil((wait0 ? g.turn_ms : ms) / 1000);
  el.classList.toggle('foe', g.turn !== me());
  el.classList.toggle('low', g.turn === me() && sec <= 10 && !wait0);
  $('clockTxt').textContent = `${FD(Math.floor(sec / 60))}:${FD(String(sec % 60).padStart(2, '0'))}`;
  $('clockRing').style.strokeDashoffset = CLOCK_C * (1 - (wait0 ? 1 : ms / g.turn_ms));
  el.setAttribute('aria-label', `${FD(sec)} ثانیه از وقت شلیک ${g.turn === me() ? 'تو' : armyOf(g.turn)} مونده`);
  if (g.turn === me() && !wait0 && sec <= 5 && sec > 0 && sec !== lastTick) { lastTick = sec; sfx.tick(); }
}
setInterval(tickClock, 250);

/* ---------- پایین صفحه: ابزار چیدن، نوبت، نتیجه ---------- */
const UNIT_ICON = k => `<svg viewBox="${VB[k]}" aria-hidden="true"><g class="lg-u" style="stroke-width:1.6">${k === 'flag' ? `<path class="fl" d="M0 -16H17V-4H0Z" fill="${COLORS[me()] || COLORS[0]}"/>` : ''}<use href="#u-${k}"/></g></svg>`;
const ERASER = '<svg class="er" viewBox="0 0 56 34" aria-hidden="true"><g transform="rotate(-10 28 17)"><rect x="3" y="8" width="50" height="20" rx="4" fill="#D64541"/><path d="M7 8H28V28H7a4 4 0 0 1 -4 -4V12a4 4 0 0 1 4 -4Z" fill="#2F6FBF"/><rect x="5" y="10" width="46" height="3" rx="1.5" fill="#fff" opacity=".22"/></g></svg>';
const pencilBtn = (c, out) => { const [nm, body, lead] = PENCILS[c]; return `<button class="lg-pc${out ? ' out' : ''}" role="radio" aria-checked="${out}" aria-label="${nm}${out ? '، الان دستته' : ''}" data-pc="${c}"><svg viewBox="0 0 20 112"><path d="M10 0L18 26H2Z" fill="#E9C9A0"/><path d="M10 0L12.6 8.5H7.4Z" fill="${lead}"/><path d="M2 26q2.67-4 5.33 0t5.33 0t5.34 0V30H2Z" fill="${body}"/><rect x="2" y="27" width="16" height="85" fill="${body}"/><rect x="7" y="27" width="4" height="85" fill="#fff" opacity=".22"/><rect x="14" y="27" width="4" height="85" fill="#000" opacity=".14"/></svg></button>`; };
function toolsHtml() {
  const n = left(), rem = Object.values(n).reduce((a, b) => a + b, 0);
  const tabs = `<div class="lg-tabs" role="tablist"><button role="tab" aria-selected="${!tool}" data-tab="units">${icon('users')}نیروها${rem ? `<span class="n">${FD(rem)}</span>` : `<span class="n ok">✓</span>`}</button>
    <button role="tab" aria-selected="${!!tool}" data-tab="draw">${icon('pen')}مداد و پاک‌کن</button></div>`;
  if (!tool) {
    return `${tabs}<div class="lg-units"><div class="lg-uhead"><b>نیروهات</b><span class="left${rem ? '' : ' ok'}">${rem ? `${FD(rem)} تا دیگه مونده` : 'همه چیده شد'}</span>
      ${rem ? `<button class="lg-auto" id="auto">${icon('spark')}بقیه رو خودت بچین</button>` : ''}</div>
      <div class="lg-chips">${KINDS.map(k => `<button class="lg-chip${n[k] ? '' : ' done'}" data-k="${k}" aria-label="${KIND_FA[k]}، ${n[k] ? FD(n[k]) + ' تا مونده' : 'همه چیده شد'}">${UNIT_ICON(k)}<span>${KIND_FA[k]}</span><i class="n">${n[k] ? FD(n[k]) : '✓'}</i></button>`).join('')}</div>
      <p class="lg-uhint">از اینجا بکش روی برگه؛ با یه لمس روی نیرو بچرخونش یا برش دار. نقاشی‌ها فقط برای قشنگی‌ان و هدف نیستن.</p></div>`;
  }
  const pc = tool.k === 'pen' ? tool.c : -1;
  return `${tabs}<div class="lg-draw"><div class="lg-box"><div class="lg-pcs" role="radiogroup" aria-label="مدادرنگی‌ها">${PENCILS.map((_, c) => pencilBtn(c, c === pc)).join('')}</div>
      <div class="lg-tools"><button class="lg-tool${tool.k === 'eraser' ? ' on' : ''} keep" id="eraser" aria-pressed="${tool.k === 'eraser'}">${ERASER}پاک‌کن</button>
        <button class="lg-tool keep" id="undo"><span class="b">${icon('undo')}</span>برگردون</button>
        <button class="lg-tool" id="hand"><span class="b">${icon('users')}</span>نیروها</button></div></div>
    <div class="lg-btn"><button class="lg-paint" id="paint" aria-pressed="false" style="--pc:${tool.k === 'eraser' ? '#2F6FBF' : PENCILS[pc][2]};--pc2:${tool.k === 'eraser' ? '#5B8FD6' : PENCILS[pc][1]}" aria-label="${tool.k === 'eraser' ? 'پاک کن' : 'رنگ کن'}؛ تا وقتی نگهش داری کار می‌کنه، یه ضربه روشن می‌مونه">
      ${icon(tool.k === 'eraser' ? 'close' : 'pen')}<b>${tool.k === 'eraser' ? 'پاک کن' : 'رنگ کن'}</b></button>
      <small id="paintHint"></small></div></div>`;
}
function renderPaint() {
  const b = $('paint'); if (!b) return;
  b.classList.toggle('on', painting); b.classList.toggle('lock', lock); b.setAttribute('aria-pressed', String(painting));
  const h = $('paintHint'); if (h) h.textContent = lock ? 'روشنه؛ یه ضربه خاموش' : painting ? 'داره می‌کشه' : 'نگه دار؛ یه ضربه روشن';
}
function renderTools() { if (phase() === 'draw' && !WATCH && me() && !P(me()).ready && P(me()).army) renderDock(); }
function dockDraw() {
  const n = (units || []).length, all = n === total();
  return `${toolsHtml()}<button class="lg-go blue" id="ready"${all ? '' : ' disabled'}><span>آماده‌ام</span>${all ? '' : `<small>اول ${FD(total() - n)} نیروی دیگه رو بچین</small>`}</button>`;
}
function dockWait() {
  const f = topC(), fp = P(f);
  return `<div class="lg-card"><div class="lg-row"><span class="ic ok">${icon('check')}</span><span class="tx"><h2>آماده‌ای!</h2>
      <p>${fp.ready ? 'الان جنگ شروع می‌شه…' : `منتظر ${esc(fp.army || fp.name)} ایم؛ ${fp.army ? `${FD(fp.placed)} از ${FD(total())} نیرو چیده` : 'هنوز داره اسم می‌ذاره'}.`}</p></span>
      <span class="lg-dots" aria-hidden="true" style="--c:${COLORS[f]}"><i></i><i></i><i></i></span></div>
    <button class="lg-link" id="unready">یه لحظه، می‌خوام عوضش کنم</button></div>`;
}
const steps = n => `<ol class="lg-steps" aria-label="قدم های شلیک">${['نقطه بذار', 'تا کن', 'فشار بده'].map((t, i) =>
  `<li class="${i + 1 < n ? 'done' : i + 1 === n ? 'on' : ''}"${i + 1 === n ? ' aria-current="step"' : ''}><i>${i + 1 < n ? '✓' : FD(i + 1)}</i>${t}</li>`).join('')}</ol>`;
function dockBattle() {
  const g = G();
  const msg = noteMsg && Date.now() - noteMsg.at < 6000 ? `<p class="lg-hint" style="font-weight:800;color:${noteMsg.kind === 'bad' ? 'var(--lg-red)' : noteMsg.kind === 'ok' ? 'var(--lg-green)' : 'var(--lg-muted)'}">${noteMsg.text}</p>` : '';
  if (WATCH) return `<div class="lg-card"><div class="lg-row"><span class="ic">${icon('eye')}</span><span class="tx"><h2>${g.turn ? `نوبت ${esc(armyOf(g.turn))}` : 'جنگ'}</h2><p>داری جنگ رو تماشا می‌کنی؛ هر شلیک رو زنده می‌بینی.</p></span></div>${msg}</div>`;
  if (!myTurn()) {
    const f = g.turn;
    return `<div class="lg-card"><div class="lg-row"><span class="ic" style="background:#EEF2EA;color:var(--lg-muted)">${icon('clock')}</span><span class="tx"><h2>نوبت ${esc(armyOf(f))}</h2><p>داره نشونه می‌گیره…</p></span>
      <span class="lg-dots" aria-hidden="true" style="--c:${COLORS[f] || COLORS[1]}"><i></i><i></i><i></i></span></div>${msg}
      <div class="lg-react">${QUICK.slice(0, 4).map(q => `<button data-q="${esc(q)}">${esc(q)}</button>`).join('')}</div></div>`;
  }
  if (fold.st === 'folded' || fold.st === 'pressing' || fold.st === 'firing') {
    return `<div class="lg-card">${steps(3)}<div class="lg-row"><span class="ic">${icon('bolt')}</span><span class="tx"><h2>محکم فشار بده!</h2><p>از پشت برگه، انگشتت رو روی نقطه نگه دار تا پررنگ بشه.</p></span></div>
      <div role="progressbar" aria-label="پررنگ شدن نقطه" style="height:12px;border-radius:6px;background:var(--lg-sunk);overflow:hidden"><div id="pressBar" style="width:100%;height:100%;border-radius:6px;background:var(--lg-red);transform:scaleX(0);transform-origin:right"></div></div>
      ${fold.st === 'folded' ? '<button class="lg-link" id="unfold">باز کن، دوباره نشونه بگیرم</button>' : ''}</div>`;
  }
  return `<div class="lg-card">${steps(aim ? 2 : 1)}<div class="lg-row"><span class="ic">${icon('spark')}</span><span class="tx"><h2>نوبت توئه!</h2>
      <p>${aim ? 'حالا برگه رو از دستهٔ پایین بکش بالا؛ هر چی صاف‌تر، دقیق‌تر.' : 'با مداد قرمز یه نقطه روی نیمهٔ خودت بذار؛ همون فاصله تا خط، اون‌ور می‌خوره.'}</p></span></div>${msg}
    <button class="lg-go" id="foldB"${aim && fold.st === 'flat' ? '' : ' disabled'}><span>${icon('up')}تا کن و شلیک کن</span></button></div>`;
}
function dockOver() {
  const g = G(), w = g.winner, mine = w && w === me();
  const title = !w ? 'جنگ بی‌برنده تموم شد 🕊' : WATCH ? `${esc(armyOf(w))} برد!` : mine ? 'لشگرت جنگ رو برد! 🎉' : `${esc(armyOf(w))} برد 😅`;
  const why = { flag: 'پرچم خورد و جنگ همون‌جا تموم شد.', army: 'همهٔ نیروها خط خوردن.', left: 'حریف وسط جنگ رفت.', timeout: 'سه بار پشت هم نوبت سوخت.', idle: 'خیلی وقت کسی کاری نکرد.' }[g.why] || '';
  const row = c => {
    const mineS = g.shots.filter(x => x.by === c), good = mineS.filter(x => x.hit && x.hit.length).length;
    return `<tr><td>${esc(armyOf(c))}</td><td>${FD(mineS.length)}</td><td>${FD(good)}</td><td>${FD(mineS.length ? Math.round(good * 100 / mineS.length) : 0)}٪</td><td>${FD(P(c).alive)}</td></tr>`;
  };
  return `<div class="lg-card"><div class="lg-win">${w ? `<span class="lg-stamp">${mine || WATCH ? 'برنده' : 'باخت'}</span>` : ''}<h2>${title}</h2><p>${why}</p></div>
      <table class="lg-tbl"><thead><tr><th>لشگر</th><th>شلیک</th><th>خورد</th><th>دقت</th><th>سالم</th></tr></thead><tbody>${[w || botC(), ...g.order.filter(c => c !== (w || botC()))].map(row).join('')}</tbody></table>
      <p class="lg-hint">عکس برگهٔ آخر جنگ توی گروه هم رفت 📣</p>
      <div class="lg-acts"><button class="lg-go" id="again"><span>${icon('send')}یه جنگ دیگه</span></button><a class="lg-go blue" href="index.html"><span>${icon('home')}خونه</span></a></div></div>`;
}
function dockWatchDraw() {
  return `<div class="lg-card"><div class="lg-row"><span class="ic">${icon('eye')}</span><span class="tx"><h2>دارن ارتششون رو می‌چینن</h2>
    <p>${G().order.map(c => `${esc(P(c).army || P(c).name)}: ${P(c).ready ? 'آماده ✓' : 'داره می‌کشه…'}`).join('، ')}</p></span></div></div>`;
}
function renderDock() {
  const g = G(), d = $('dock'); if (!g) return;
  let html;
  if (g.over) html = dockOver();
  else if (g.phase === 'draw') html = WATCH ? dockWatchDraw() : P(me()).ready ? dockWait() : P(me()).army ? dockDraw() : '';
  else html = dockBattle();
  // فقط وقتی چیزی عوض شده: هر poll نباید دکمه ای را که زیر انگشت است (رنگ کن، نیروی در حال کشیدن) از نو بسازد
  if (html !== lastDock) { lastDock = html; d.innerHTML = html; GC.mount(d); bindDock(); }
  renderPaint();
}
function bindDock() {
  const d = $('dock');
  d.querySelectorAll('[data-tab]').forEach(b => b.onclick = () => { sfx.tap(); if (b.dataset.tab === 'units') setTool(null); else if (!tool) setTool({ k: 'pen', c: 0 }); });
  d.querySelectorAll('[data-pc]').forEach(b => b.onclick = () => { const c = +b.dataset.pc; sfx.tap(); haptic('select'); setTool({ k: 'pen', c }); });
  const er = $('eraser'); if (er) er.onclick = () => { sfx.tap(); setTool(tool && tool.k === 'eraser' ? { k: 'pen', c: 0 } : { k: 'eraser' }); };
  const un = $('undo'); if (un) un.onclick = undo;
  const hd = $('hand'); if (hd) hd.onclick = () => setTool(null);
  const au = $('auto'); if (au) au.onclick = autoAll;
  d.querySelectorAll('.lg-chip').forEach(b => {
    b.addEventListener('pointerdown', e => {
      const k = b.dataset.k; if (!left()[k]) { sfx.error(); toast(`از ${KIND_FA[k]} دیگه نداری`); return; }
      e.preventDefault(); b.setPointerCapture(e.pointerId);
      drag = { i: null, k, r: 0, x0: e.clientX, y0: e.clientY, moved: false, id: e.pointerId };
      sel = -1; placeOverlays();
      const mv = ev => { if (drag && drag.id === ev.pointerId) moveDrag(ev); };
      const up = ev => { b.removeEventListener('pointermove', mv); b.removeEventListener('pointerup', up); b.removeEventListener('pointercancel', up); if (drag && drag.id === ev.pointerId) dropDrag(ev); };
      b.addEventListener('pointermove', mv); b.addEventListener('pointerup', up); b.addEventListener('pointercancel', up);
    });
  });
  const pt = $('paint');
  if (pt) {
    let t0 = 0, moved0 = 0;
    pt.addEventListener('pointerdown', e => { e.preventDefault(); pt.setPointerCapture(e.pointerId); t0 = performance.now(); moved0 = stroke ? stroke.p.length : 0; if (!lock) startPaint(); });
    const up = () => {
      const quick = performance.now() - t0 < 240 && (!stroke || stroke.p.length - moved0 <= 2);
      if (quick) { if (lock) { stopPaint(); } else { lock = true; painting = true; renderPaint(); sfx.tap(); } }
      else if (!lock) stopPaint();
    };
    pt.addEventListener('pointerup', up); pt.addEventListener('pointercancel', () => { if (!lock) stopPaint(); });
  }
  const rd = $('ready'); if (rd) rd.onclick = doReady;
  const ur = $('unready'); if (ur) ur.onclick = () => act(() => API.unready(mid, since));
  const fb = $('foldB'); if (fb) fb.onclick = foldButton;
  const uf = $('unfold'); if (uf) uf.onclick = () => { aim = null; unfoldMine().then(renderSheet); };
  d.querySelectorAll('[data-q]').forEach(b => b.onclick = () => { if (chat) chat.send(b.dataset.q); sfx.tap(); });
  const ag = $('again'); if (ag) ag.onclick = () => again(ag);
}
async function doReady() {
  const b = $('ready'); if (b) b.disabled = true;
  if (stroke) endStroke();
  clearTimeout(unitsT);
  try { await saveUnits(true); await inkSettled(); } catch (e) {}
  await act(() => API.ready(mid, since), () => { sfx.turn(); haptic('success'); });
}

/* ---------- اسم لشگر ---------- */
function randomArmy() { return ARMY_A[Math.floor(Math.random() * ARMY_A.length)] + ' ' + ARMY_B[Math.floor(Math.random() * ARMY_B.length)]; }
function nameScreen() {
  const scr = $('nameScr'), g = G(), mine = P(me()), f = P(topC());
  const want = g.phase === 'draw' && !WATCH && !mine.army && !g.over;
  scr.hidden = !want;
  if (!want) return;
  if (scr.dataset.on) { const fs = $('nFoe'); if (fs) fs.innerHTML = foeLine(f); return; }
  scr.dataset.on = '1';
  const v0 = store.get('lg_army', '') || '';
  scr.innerHTML = `<div class="lg-nhead"><button class="lg-ib" id="nExit" aria-label="خروج">${icon('exit')}</button>
      <div class="lg-head"><b>لشگر کاغذی</b><span>قبل از جنگ، لشگرت یه اسم می‌خواد</span></div><button class="lg-ib" id="nHelp" aria-label="راهنما"><b>؟</b></button></div>
    <div class="lg-hero"><div class="lg-book"><div class="lab"><span>نام لشگر:</span><b id="nPrev"></b><span>فرمانده: ${esc(mine.name)}</span></div>
      <div class="tag"><svg viewBox="-6 -20 34 36" aria-hidden="true"><path d="M0 -16H17V-4H0Z" fill="${COLORS[me()]}" opacity=".7"/><g class="lg-u" style="stroke-width:1.4"><use href="#u-flag"/></g></svg>پرچم تو</div></div></div>
    <div class="lg-ncard"><div class="lg-row" style="gap:8px"><label for="nIn">اسم لشگرت</label><span class="cnt" id="nCnt"></span></div>
      <div class="lg-in"><input id="nIn" maxlength="24" autocomplete="off" autocorrect="off" spellcheck="false" dir="rtl" placeholder="مثلا: شیرهای کلاس پنجم" enterkeyhint="done" value="${esc(v0)}">
        <button id="nClr" aria-label="پاک کردن اسم">${icon('close', 3)}</button></div>
      <span style="font-size:12.5px;font-weight:700;color:var(--lg-muted)">یا یکی از این‌ها رو بردار:</span>
      <div class="lg-sug" id="nSug">${SUGGEST.map(x => `<button data-s="${esc(x)}">${esc(x)}</button>`).join('')}<button class="rnd" id="nRnd">${icon('spin')}یه اسم شانسی</button></div>
      <p class="lg-err" id="nErr" role="alert"></p>
      <span style="font-size:11.5px;color:var(--lg-muted)">اسمت توی گروه و آخر جنگ هم نشون داده می‌شه.</span></div>
    <div class="lg-foe" id="nFoe">${foeLine(f)}</div><div class="sp"></div>
    <button class="lg-go blue" id="nGo"><span>ثبت اسم، بریم سراغ نقاشی</span></button>`;
  GC.mount(scr);
  const inp = $('nIn'), prev = $('nPrev'), cnt = $('nCnt');
  const sync = () => {
    const v = inp.value.replace(/\s+/g, ' ');
    prev.innerHTML = `${esc(v.trim())}<i></i>`; cnt.textContent = `${FD(v.trim().length)} از ${FD(20)} حرف`;
    scr.querySelectorAll('#nSug [data-s]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.s === v.trim())));
    $('nGo').disabled = v.trim().length < 2;
  };
  inp.addEventListener('input', () => { $('nErr').textContent = ''; sync(); });
  inp.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); submitName(); } });
  $('nClr').onclick = () => { inp.value = ''; sync(); inp.focus(); };
  scr.querySelectorAll('#nSug [data-s]').forEach(b => b.onclick = () => { inp.value = b.dataset.s; sync(); sfx.tap(); });
  $('nRnd').onclick = () => { let n = randomArmy(); for (let i = 0; i < 6 && n === inp.value; i++) n = randomArmy(); inp.value = n; sync(); sfx.tap(); haptic('select'); };
  $('nGo').onclick = submitName;
  $('nExit').onclick = askExit;
  $('nHelp').onclick = howTo;
  sync();
}
function foeLine(f) {
  return `${face(f)}<span>${esc(f.name)}${f.army ? ' اسم گذاشت:' : ''}</span>${f.army ? `<span class="hand">${esc(f.army)}</span>` : '<span style="color:var(--lg-muted)">هنوز داره فکر می‌کنه…</span>'}`;
}
async function submitName() {
  const inp = $('nIn'), v = inp.value.replace(/\s+/g, ' ').trim(), b = $('nGo');
  if (v.length < 2) return;
  b.disabled = true;
  try {
    const r = await API.army(mid, v, since);
    store.set('lg_army', v); inp.blur(); sfx.turn(); haptic('success');
    $('nameScr').dataset.on = ''; await apply(r);
  } catch (e) { $('nErr').textContent = errText(e); sfx.error(); haptic('error'); b.disabled = false; }
}

/* ---------- راهنما ---------- */
function howTo() {
  const mini = (body, extra = '') => `<svg viewBox="0 0 150 104" aria-hidden="true"><rect x="8" y="8" width="134" height="88" rx="3" fill="#FCFBF7" stroke="#D8D2C2"/>${extra}<g filter="url(#lgPn)" class="lg-u" style="stroke-width:1.2">${body}</g></svg>`;
  const sh = sheet(`<div style="display:flex;flex-direction:column;gap:12px"><h2 style="margin:0;font-family:var(--font-rokh);font-weight:900;font-size:22px">لشگر کاغذی چطوریه؟</h2>
    <p style="margin:0;font-size:13.5px;line-height:22px;color:var(--lg-muted)">همون جنگ کاغذی زنگ تفریح: یه برگه، وسطش یه خط، این‌ور ارتش تو و اون‌ور ارتش حریف.</p>
    <div class="lg-how">
      <div>${mini('<use href="#u-tank" transform="translate(46 62) scale(.9)"/><use href="#u-sol" transform="translate(92 52) scale(.9)"/><use href="#u-flag" transform="translate(120 52) scale(.9)"/>', '<path d="M8 22q4 -3 8 0t8 0t8 0t8 0t8 0t8 0t8 0t8 0t8 0t8 0t8 0t8 0t8 0t8 0t8 0t8 0t6 0" fill="none" stroke="#3A3A3A" stroke-width="1.4"/>')}<b>۱. ارتشت رو بچین</b><span>نیروها رو بکش رو برگه؛ مداد رو با انگشت ببر و «رنگ کن» رو نگه دار.</span></div>
      <div>${mini('<use href="#u-tank" transform="translate(40 66) scale(.8)" opacity=".5"/>', '<circle cx="76" cy="46" r="4.5" fill="#C8323C"/>')}<b>۲. یه نقطه بذار</b><span>روی نیمهٔ خودت؛ همون فاصله تا خط، اون‌ور شلیک می‌شه.</span></div>
      <div>${mini('', '<path d="M8 52L142 52L130 90L20 90Z" fill="#F1EEE6" stroke="#CFC8B6"/><path d="M140 92C150 70 150 44 128 30" fill="none" stroke="#1668D9" stroke-width="2.4" stroke-linecap="round"/>')}<b>۳. برگه رو تا کن</b><span>دستهٔ پایین رو بکش بالا؛ هر چی صاف‌تر، دقیق‌تر.</span></div>
      <div>${mini('<use href="#u-tank" transform="translate(60 38) rotate(180) scale(.95)"/>', '<circle cx="62" cy="40" r="4.5" fill="#C8323C"/><path d="M38 26L84 52M38 52L84 26" stroke="#C8323C" stroke-width="2.4" stroke-linecap="round"/>')}<b>۴. فشار بده</b><span>روی نقطه نگه دار؛ به هر نیرویی بخوره، خط می‌خوره.</span></div>
    </div>
    <ul class="lg-rules"><li>اول یه اسم باحال برای لشگرت می‌ذاری. نقاشی وقت نداره، ولی هر شلیک ۱ دقیقه وقت داره.</li><li>هر نیرو با یه بار خوردن خط می‌خوره؛ نقاشی‌ها فقط برای قشنگی‌ان.</li><li>پرچم فرماندهٔ توئه: اگه بخوره، جنگ همون‌جا تمومه.</li><li>هر کی زودتر کل ارتش حریف رو خط بزنه، برنده‌ست.</li></ul>
    <button class="btn btn-block" data-close>فهمیدم، بریم!</button></div>`);
  GC.mount(sh);
}

/* ---------- همگام سازی ---------- */
// پاسخ ها (poll، شلیک، آماده) یکی یکی و به ترتیب اعمال می شوند تا انیمیشن ها روی هم نیفتند
function apply(v) { return (applying = applying.then(() => applyNow(v)).catch(e => console.error(e))); }
async function applyNow(v) {
  if (!v) return;
  if (v.chat && chat && !overShown) chat.add(v.chat);
  if (v.status === 'cancelled') return cancelled();
  if (!v.game) return;
  const g = v.game;
  if (G() && g.seq < G().seq) return;              // پاسخ کهنه (مثلا poll ای که پیش از شلیک رفته بود)
  snap = Object.assign({}, snap || {}, v);
  deadlineAt = performance.now() + (g.deadline_ms || 0); readyAt = performance.now() + (g.ready_ms || 0);
  if (shown < 0) shown = g.shots.length;          // بار اول: شلیک های قبلی بی انیمیشن
  if (g.phase === 'draw' && me()) {
    const mine = P(me());
    if (units == null || mine.ready) { units = (mine.units || []).map(u => ({ k: u.k, x: u.x, y: u.y, r: u.r || 0 })); unitsSent = JSON.stringify(units); }
  }
  if (!layout) fit(true);
  const cv = $('cover');
  if (g.phase === 'draw' && !g.over) { cv.hidden = false; coverHtml(); }
  else if (layout !== 'draw') cv.hidden = true;
  loadInk();
  const evs = (g.events || []).filter(e => e.seq > since).sort((a, b) => a.seq - b.seq);
  const first = !since;
  // سربرگ (نوبت کیست) بعد از پخش شلیک ها عوض می شود تا با کارت پایین یکی باشد
  if (first || !evs.some(e => ['shot', 'battle', 'timeout'].includes(e.t))) renderHead();
  nameScreen();
  since = Math.max(since, g.seq);
  if (!first) for (const e of evs) await playEvent(e);
  if (g.phase !== 'draw' && (layout === 'draw' || !cv.hidden)) await reveal(g.turn, first);   // رویداد شروع جا ماند
  shown = g.shots.length;
  renderHead(); renderSheet(); renderDock(); placeOverlays(); tickClock(); turnUi(first);
  if (g.over && !overShown) {
    overShown = true; GC.guardClose(false); if (!WATCH) store.set('lgmid', null);
    if (chat) { chat.end(); $('chatBtn').hidden = true; }
    const won = g.winner && g.winner === me();
    if (!WATCH) setTimeout(() => (won ? sfx.win() : g.winner ? sfx.lose() : null), 300);
    GC.refreshMe().catch(() => {});
  }
}
function coverHtml() {
  const c = WATCH ? topC() : topC(), p = P(c), el = $('cover');
  const sig = JSON.stringify([p.army, p.ready, p.placed, p.name]);
  if (el.dataset.sig === sig) return;
  el.dataset.sig = sig;
  el.innerHTML = `<div class="lg-label"><span>لشگر: ${esc(p.army || '…')}</span><span>فرمانده: ${esc(p.name)}</span><span class="no">دید زدن ممنوع!</span></div>
    <div class="lg-who${p.ready ? ' ok' : ''}">${face(p, '#fff')}<span>${p.ready ? 'آماده‌ست!' : 'داره می‌کشه…'}</span><small>${p.ready ? 'منتظر توئه' : 'عجله‌ای نیست'}</small></div>`;
}
async function act(fn, ok) {
  if (busy) return; busy = true;
  try { const v = await fn(); if (v && v.game) await apply(v); if (ok) ok(); }
  catch (e) { sfx.error(); haptic('error'); toast(errText(e)); renderDock(); }
  busy = false;
}
async function again(btn) {
  const w = GC.tg, at = v => w && w.isVersionAtLeast && w.isVersionAtLeast(v);
  btn.disabled = true;
  try {
    const r = await GC.data.groupShare('lashgar');
    if (r.demo) toast('توی تلگرام گروهتو انتخاب می‌کنی و کارت میز همون‌جا می‌ره');
    else if (at('8.0') && w.shareMessage) w.shareMessage(r.id, ok => { if (ok) { sfx.turn(); haptic('success'); toast('کارت میز رفت توی گروه؛ بچه‌ها رو خبر کن! 🎉'); } });
    else if (at('6.7') && w.switchInlineQuery) w.switchInlineQuery('lashgar', ['groups']);
    else toast('توی گروه بنویس /lashgar');
  } catch (e) { toast(errText(e)); }
  btn.disabled = false;
}

/* ---------- خروج ---------- */
function askExit() {
  const g = G();
  if (!snap || snap.status !== 'playing' || WATCH || !g || g.over) { location.href = 'index.html'; return; }
  const sh = sheet(`<div class="dlg" role="alertdialog" aria-labelledby="dT" aria-describedby="dD">
      <span class="dlg-ic warn">${icon('exit')}</span><h2 id="dT">از جنگ می‌ری؟</h2>
      <p id="dD">اگه بری، جنگ رو باختی و حریفت برنده می‌شه.</p>
      <div class="dlg-acts"><button class="btn" data-close>نه، می‌مونم</button><button class="btn btn-danger-soft" id="leave">${icon('exit')}آره، می‌رم</button></div>
      <button class="btn btn-light btn-block dlg-home" id="home">${icon('home')}فقط برم خونه؛ جنگ سر جاش می‌مونه</button>
      <p class="dlg-fine">${phase() === 'draw' ? 'نقاشی و نیروهات ذخیره شده؛ از صفحهٔ خونه با یه لمس برمی‌گردی.' : 'حواست باشه هر شلیک فقط ۱ دقیقه وقت داره ⏳'}</p></div>`, { center: true });
  sh.querySelector('#home').onclick = async () => { try { await saveUnits(true); await inkSettled(); } catch (e) {} GC.guardClose(false); location.href = 'index.html'; };
  sh.querySelector('#leave').onclick = async () => { try { await API.leave(mid); } catch (e) {} GC.guardClose(false); store.set('lgmid', null); location.href = 'index.html'; };
}
$('exit').onclick = askExit;
$('help').onclick = () => (phase() === 'draw' && !WATCH ? GCTour.start(tourDraw()) : phase() === 'battle' && !WATCH ? GCTour.start(tourBattle()) : howTo());
GC.back(askExit);
function dialog(title, text) {
  sheet(`<div class="dlg" role="alertdialog" aria-labelledby="dT" aria-describedby="dD"><span class="dlg-ic">${icon('flag')}</span>
      <h2 id="dT">${title}</h2><p id="dD">${text}</p>
      <div class="dlg-acts"><a class="btn" href="lashgar-lobby.html">لشگر کاغذی</a><a class="btn btn-light" href="index.html">برگرد خونه</a></div></div>`, { center: true, dismiss: false });
}
function cancelled() { store.set('lgmid', null); GC.guardClose(false); dialog('این جنگ بسته شد', 'جنگ قبل از اینکه تموم شه بسته شد؛ یه میز تازه بچینید 😉'); }
function noMatch() { if (!watchMid) store.set('lgmid', null); dialog(watchMid ? 'این جنگ رو نمی‌شه دید' : 'جنگی پیدا نشد', watchMid ? 'یا تموم شده یا هنوز شروع نشده.' : 'یا جنگ تموم شده یا هنوز سر هیچ میزی ننشستی.'); }

/* ---------- پرسیدن پیاپی وضعیت ---------- */
async function poll() {
  clearTimeout(pollT);
  if (snap && snap.status !== 'playing') return;
  if (!busy && !(fold.st === 'pressing' || fold.st === 'firing' || fold.st === 'drag' || fold.st === 'folding')) {
    busy = true;
    try { await apply(await API.match(mid, since, chat ? chat.last() : null)); }
    catch (e) { if (e.code === 'not_found') { busy = false; return noMatch(); } }
    busy = false;
  }
  const ph = phase();
  pollT = setTimeout(poll, document.hidden ? 4000 : ph === 'draw' ? 2000 : 1000);
}
document.addEventListener('visibilitychange', () => { if (!document.hidden) { if (snap && snap.status === 'playing') poll(); } else { if (stroke) endStroke(); saveUnits(true); flushInk(); } });
addEventListener('pagehide', () => { if (stroke) endStroke(); saveUnits(true); flushInk(); });

async function start() {
  GC.portrait(true);
  // بافت کاغذ: یک بار، کوچک، تکرار شونده
  try {
    const t = document.createElement('canvas'); t.width = t.height = 96;
    const x = t.getContext('2d'), img = x.createImageData(96, 96);
    for (let i = 0; i < img.data.length; i += 4) { const v = 120 + Math.random() * 60; img.data[i] = v; img.data[i + 1] = v * .9; img.data[i + 2] = v * .75; img.data[i + 3] = Math.random() * 16; }
    x.putImageData(img, 0, 0);
    document.body.style.setProperty('--grain', `url(${t.toDataURL()})`);
  } catch (e) {}
  let first;
  try { first = await API.match(mid, 0); }
  catch (e) { return e.code === 'not_found' ? noMatch() : (toast(errText(e)), setTimeout(start, 2500)); }
  WATCH = !!first.watch;
  if (first.status === 'lobby') { if (watchMid) return noMatch(); location.href = 'lashgar-lobby.html'; return; }
  mid = first.id;
  if (!WATCH) store.set('lgmid', mid);
  if (first.status === 'playing' && !WATCH) GC.guardClose(true);
  if (!WATCH && window.TChat) {
    $('chatBtn').hidden = false;
    chat = TChat.init({
      btn: $('chatBtn'), badge: $('chatBadge'), quick: QUICK, face: m => face(m, COLORS[m.color]),
      canSend: () => mid && !WATCH, rest: () => $('dock').offsetHeight + 10,
      send: async text => { await API.chat(mid, text); return (await API.match(mid, since, chat.last())).chat; },
      onNew: () => sfx.tap(), onError: e => { sfx.error(); toast(errText(e)); },
    });
  }
  since = 0;
  await apply(first);
  since = first.game ? first.game.seq : 0;
  poll();
}
document.addEventListener('pointerdown', () => GC.loadSamples && GC.loadSamples(), { once: true });
/* ---------- آموزش بار اول: یکی برای چیدن و نقاشی (بعد از اسم)، یکی برای اولین جنگ ---------- */
const halfRect = top => { const r = sheetRect(); if (!r.width) return null; const h = r.height / 2; return { x: r.left, y: top ? r.top : r.top + h, w: r.width, h: Math.min(h, innerHeight - (top ? r.top : r.top + h)) }; };
function tourDraw() {
  return {
    id: 'lashgar', name: 'لشگر کاغذی', color: '#1A7A35', ink: '#fff', help: 'help.html#hLg',
    introTitle: 'جنگ کاغذی شروع شد!', intro: 'همون جنگ زنگ تفریح: ارتشت رو روی نیمهٔ خودت بچین، هر چی خواستی بکش و بعد با تا کردن برگه شلیک کن.',
    ready: () => !!(G() && !WATCH && phase() === 'draw' && me() && P(me()).army && !P(me()).ready && document.querySelector('.lg-chips') && $('nameScr').hidden),
    after: () => { if (phase() === 'draw') setTool(null); },
    steps: [
      { el: '.lg-chips', title: 'ارتشت رو بچین', text: 'نیروها رو از اینجا <b>بکش روی نیمهٔ خودت</b>. با یه لمس روی هر نیرو، می‌چرخونیش یا برش می‌داری.', hand: { type: 'drag', from: [0.5, 0.45], to: [0.45, -2.4] }, before: () => setTool(null) },
      { el: '#auto', title: 'عجله داری؟', text: '«بقیه رو خودت بچین» نیروهای باقی‌مونده رو یه جای خالی می‌ذاره؛ بعدش هم می‌تونی جابه‌جاشون کنی.', hand: 'tap' },
      { el: () => halfRect(false), title: 'پرچم فرمانده‌ست', text: 'هر نیرو با یه بار خوردن خط می‌خوره. <b>پرچم</b> رو خوب قایم کن: اگه بخوره، جنگ همون‌جا تمومه. نقاشی‌ها هدف نیستن.', pad: 2, round: 6 },
      { el: '.lg-pcs', title: 'یه مداد بردار', text: 'مداد رو با <b>یه انگشت</b> روی برگه ببر؛ سرش کمی بالای انگشتته تا ببینی کجا می‌کشی.', hand: 'tap', at: [0.85, 0.4], before: () => setTool({ k: 'pen', c: 0 }) },
      { el: '#paint', title: 'رنگ کن', text: 'فقط وقتی این دکمه رو <b>نگه داشتی</b> مداد رنگ می‌ده. یه ضربهٔ کوتاه روشن نگهش می‌داره و ضربهٔ بعد خاموشش می‌کنه.', hand: 'hold', round: 999 },
      { el: '.lg-tools', title: 'پاک‌کن و برگردون', text: 'پاک‌کن هم مثل مداده: با «رنگ کن» پاک می‌کنه. «برگردون» آخرین خط رو برمی‌داره.' },
      { el: '#ready', title: 'آماده‌ام', text: 'همه چیده شد؟ <b>«آماده‌ام»</b> رو بزن. هر دو که آماده شدید، دفتر کنار می‌ره و جنگ شروع می‌شه. این مرحله وقت نداره.', before: () => setTool(null) },
    ],
  };
}
function tourBattle() {
  return {
    id: 'lashgar2', artId: 'lashgar', name: 'لشگر کاغذی', color: '#C8323C', ink: '#fff', help: 'help.html#hLg', pauseAt: 15000,
    introTitle: 'وقت جنگه!', intro: 'هر شلیک سه حرکته: نقطه بذار، برگه رو تا کن و از پشت فشار بده.',
    ready: () => !!(G() && !WATCH && phase() === 'battle' && !animating && $('cover').hidden && fold.st === 'flat'),
    turn: () => ({ mine: !!myTurn(), left: deadlineAt ? deadlineAt - performance.now() : null }),
    steps: [
      { el: '#score', title: 'دو لشگر', text: 'لشگری که نوبتشه دورش روشنه؛ تعداد نیروهای سالم هر طرف هم همین‌جاست.' },
      { el: () => halfRect(false), title: 'یه نقطه بذار', text: 'نوبتت که شد، با <b>مداد قرمز</b> یه نقطه روی نیمهٔ خودت بذار. همون فاصله تا خط وسط، اون‌ور شلیک می‌شه.', hand: 'tap', at: [0.4, 0.3], pad: 2, round: 6 },
      { el: () => halfRect(false), title: 'برگه رو تا کن', text: 'دستهٔ پایین برگه رو <b>بکش بالا</b> تا تا بخوره؛ هر چی صاف‌تر بکشی دقیق‌تر. دکمهٔ «تا کن و شلیک کن» هم هست.', hand: { type: 'drag', from: [0.5, 0.96], to: [0.5, 0.1] }, pad: 2, round: 6 },
      { el: () => halfRect(true), title: 'محکم فشار بده', text: 'از پشت برگه روی نقطه <b>نگه دار</b> تا پررنگ بشه. ردش به هر نیرویی بخوره، خط می‌خوره.', hand: 'hold', at: [0.4, 0.7], pad: 2, round: 6 },
      { el: '#clock', title: 'هر شلیک ۱ دقیقه', text: 'وقتت تموم بشه نوبتت می‌سوزه؛ <b>۳ بار پشت هم</b> یعنی باخت. پرچم حریف رو بزنی، جنگ همون‌جا تمومه!', center: true },
    ],
  };
}
GCTour.auto(tourDraw()); GCTour.auto(tourBattle());

GC.mount();
start();
})();
