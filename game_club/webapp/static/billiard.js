/* بیلیارد — نمایش و کنترل. فیزیک، نوبت، خطا و برنده روی سرور است (game_club/billiard.py)؛
   اینجا رویدادهای سرور پخش می شوند (مسیر هر ضربه با فریم های سرور، افتادن توپ، خطا و
   نوبت) و ضربهٔ کاربر (زاویه، قدرت، پیچ و جای توپ سفید) فرستاده می شود.
   بیرون از تلگرام همان API را demo-billiard.js در مرورگر شبیه سازی می کند.

   چیدمان صفحه همان طرح بازی است (قاب مرجع ۶۰۰×۱۲۸۰): هدر با بازیکن ها و VS، پیام روی
   میز، ستون توپ های هر طرف کنار میز، ITEMS و نوار قدرت چپ، خط راهنما و پیچ و FINE AIM
   راست، نوار پیام پایین. کنترل: یک لمس = نوک چوب همان جا؛ کشیدن = چوب برعکس جهت انگشت می چرخد · نوار قدرت را پایین بکش و
   رها کن · FINE AIM نگه داشتن = چرخش آرام ۱ درجه در ثانیه. */
(() => {
const { S, fa, FD, store, face, icon, sheet, sheetHead, toast, sleep, sfx, haptic, errText, setSound, amount } = GC;
const E = BLEngine, W = E.W, H = E.H, R = E.R, D = E.D;
const $ = id => document.getElementById(id);
const POLL_MS = 1000, SINK_TIME = .55;
// رنگ توپ ها (پالت استاندارد بیلیارد ۸ توپ)
const BASE = { 1: '#FEC625', 2: '#1937A5', 3: '#FF2A24', 4: '#371594', 5: '#FF6A28', 6: '#1F530D', 7: '#560C11', 8: '#111111' };
const colOf = k => k === 0 ? '#EAE9E3' : BASE[k > 8 ? k - 8 : k];
const MSG = {
  break: 'بریک', open: 'میز باز است', solids: 'گروه‌ها مشخص شد', stripes: 'گروه‌ها مشخص شد',
  potted: 'افتاد! دوباره بزن', wrong_pot: 'توپ حریف افتاد', on_8: 'حالا نوبت توپ ۸ است',
  scratch: 'خطا: توپ سفید افتاد', wrong_first: 'خطا: اول به توپ اشتباه خورد', no_hit: 'خطا: به هیچ توپی نخورد',
  hit_8_first: 'خطا: اول باید به توپ ۸ بخوری', no_rail: 'خطا: هیچ توپی به ریل نخورد', jump: 'خطا: توپ از میز بیرون پرید',
  timeout: 'وقت تمام شد', break_8: 'توپ ۸ در بریک افتاد؛ دوباره چیده شد', break_illegal: 'بریک ضعیف بود؛ دوباره چیده شد',
};
const GROUP_FA = { solids: 'تک‌رنگ', stripes: 'راه‌راه' };

/* ---------- وضعیت ---------- */
const watchMid = GC.watchId();
let WATCH = false;
let mid = watchMid || store.get('bmid', null), me = '0', snap = null, since = 0, busy = false, acting = false, pollT = null, overShown = false;
let deadlineAt = 0, readyAt = 0, turnMs = 30000, warned = false, flash = null;
let angle = -Math.PI / 2, power = 0, spin = [0, 0], showLines = store.get('blEye', true);
let place = null, placing = false, aiming = false, anim = null, strike = null, hintAt = 0, lastInput = 0;
const balls = [...Array(16)].map((_, k) => ({ k, x: 0, y: 0, on: false, q: startQuat(), sink: null, _rc: null }));
function startQuat() {   // شماره رو به بیننده (مثل GAP_Q پلاتو: ۱۸۰° حول y) با کمی کجی تصادفی
  const a = (Math.random() - .5) * .9, b = (Math.random() - .5) * .9, h = Math.PI / 2;
  return mulQ([Math.cos(a / 2), 0, Math.sin(a / 2), 0], mulQ([Math.cos(b / 2), Math.sin(b / 2), 0, 0], [Math.cos(h), 0, Math.sin(h), 0]));
}
function mulQ(p, q) {
  return [p[0] * q[0] - p[1] * q[1] - p[2] * q[2] - p[3] * q[3], p[0] * q[1] + p[1] * q[0] + p[2] * q[3] - p[3] * q[2],
    p[0] * q[2] - p[1] * q[3] + p[2] * q[0] + p[3] * q[1], p[0] * q[3] + p[1] * q[2] - p[2] * q[1] + p[3] * q[0]];
}
// غلت بدون لغزش: قاب x راست، y پایین، z به درون میز ⇒ محور = (dy، -dx، ۰)
function roll(b, dx, dy) {
  const d = Math.hypot(dx, dy); if (d < 1e-4) return;
  const ang = d / R, s2 = Math.sin(ang / 2) / d;
  const q = mulQ([Math.cos(ang / 2), dy * s2, -dx * s2, 0], b.q), l = Math.hypot(q[0], q[1], q[2], q[3]) || 1;
  b.q = [q[0] / l, q[1] / l, q[2] / l, q[3] / l];
}
const G = () => (snap && snap.game) || null;
const P = () => (G() ? G().players : {});
const isMe = c => c === me && !WATCH;
const teamOf = c => { const g = G(); return g ? g.order.indexOf(c) % 2 : 0; };
const nameOf = c => isMe(c) ? 'تو' : (P()[c] ? P()[c].name : 'حریف');
const myTeam = () => teamOf(me);

/* ---------- قاب مرجع و بوم ---------- */
const frameEl = $('frame'), cv = $('table'), ctx = cv.getContext('2d');
let dpr = 1, u = 1, s = .4, ox = 0, oy = 0, cw = 600, ch = 1280, tableBuf = null, dy = 0;
const TABLE_RECT = [75, 250, 450, 820];            // جای میز در قاب (واحد مرجع)
// میز همیشه به اندازهٔ عرض صفحه (مثل پلاتو)؛ در صفحه های کوتاه (تلگرام غیر تمام صفحه، گوشی های
// کوتاه تر) به جای کوچک شدن همه چیز، فاصلهٔ خالی بالا و پایین میز کم می شود: قاب تا FH_MIN کوتاه
// می شود و میز و دکمه های کنارش به اندازهٔ نصف آن (dy) بالا می آیند؛ نوار پیام پایین قاب می ماند.
const FH_MIN = 1100;
function fit() {
  const w = $('wrap'), cs = getComputedStyle(w);
  const aw = w.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
  const ah = w.clientHeight - parseFloat(cs.paddingTop) - parseFloat(cs.paddingBottom);
  u = Math.max(.3, Math.min(aw / 600, ah / FH_MIN));
  const fh = Math.max(FH_MIN, Math.min(1280, ah / u));
  dy = (1280 - fh) / 2;
  frameEl.style.setProperty('--u', u + 'px'); document.body.style.setProperty('--u', u + 'px');
  frameEl.style.setProperty('--fh', fh.toFixed(2)); frameEl.style.setProperty('--dy', dy.toFixed(2));
  dpr = Math.min(2.5, window.devicePixelRatio || 1);
  cw = 600 * u; ch = fh * u;
  cv.width = Math.round(cw * dpr); cv.height = Math.round(ch * dpr);
  const [tx, ty, tw, th] = [TABLE_RECT[0], TABLE_RECT[1] - dy, TABLE_RECT[2], TABLE_RECT[3]].map(v => v * u);
  s = Math.min(tw / W, th / H); ox = tx + (tw - W * s) / 2; oy = ty + (th - H * s) / 2;
  tableBuf = null;
  for (const b of balls) { b._rc = null; b._pc = null; }
  for (const k in GAP) { GAP[k]._rc = null; GAP[k]._pc = null; }
}
const toS = (x, y) => [ox + x * s, oy + y * s];
const toT = (sx, sy) => [(sx - ox) / s, (sy - oy) / s];

/* ---------- آرت و استایل پلاتو ----------
   همان دارایی های بازی Pool پلاتو (کپی در static/plato): اطلس ui.webp (توپ ها، چوب، پاورمتر،
   پد انگلیش، چشم و ...)، کاشی گوشهٔ میز th_basic_table و خط سر th_basic_head_line.
   تا وقتی بار نشده اند رندر رویه ای قبلی به کار می رود تا صفحه همیشه کار کند. */
const ART = { ui: null, table: null, head: null };
const AT = {   // مستطیل های اطلس ui.webp (۱۳۴۳×۶۲۵) — عیناً از خود بازی پلاتو
  ball0: [854, 219, 128, 64], ball1: [984, 219, 128, 64], ball2: [847, 357, 128, 64], ball3: [977, 357, 128, 64],
  ball4: [1107, 357, 128, 64], ball5: [635, 448, 128, 64], ball6: [765, 448, 128, 64], ball7: [895, 448, 128, 64],
  ball8: [1025, 448, 128, 64], ball9: [1155, 448, 128, 64], ball10: [1114, 219, 128, 64], ball11: [717, 291, 128, 64],
  ball12: [847, 291, 128, 64], ball13: [977, 291, 128, 64], ball14: [1107, 291, 128, 64], ball15: [717, 357, 128, 64],
  ball_shadow: [707, 514, 45, 45], hilite: [754, 514, 43, 43], valid_ball_highlight: [635, 514, 70, 70],
  cs_basic: [0, 595, 1020, 30], power_meter: [635, 0, 708, 70], dot: [1312, 151, 14, 14],
  btn_english: [0, 0, 350, 350], red_circle: [1238, 72, 77, 77], preset_highlight: [1001, 72, 130, 130],
};
(function loadArt() {
  const one = src => new Promise(ok => { const im = new Image(); im.onload = () => ok(im); im.onerror = () => ok(null); im.src = src; });
  Promise.all([one('static/plato/ui.webp'), one('static/plato/th_basic_table.webp'), one('static/plato/th_basic_head_line.webp')]).then(([ui, table, head]) => {
    ART.ui = ui; ART.table = table; ART.head = head;
    tableBuf = null; SPH = null; SPH_SRC = null;
    for (const b of balls) b._rc = null;
    for (const k in GAP) GAP[k]._rc = null;
    drawPower(); drawSpin();
  });
})();

/* ---------- میز: کاشی گوشهٔ پلاتو ×۴ آینه ای + خال های الماسی + خط سر ---------- */
// خال های الماسی ریل ها — عیناً از Nv پلاتو (گوشهٔ بالا-چپِ اسپرایت، ۱۸ نقطه)
const DIAMONDS = [[241, 25], [411, 25], [581, 25], [241, 1481], [411, 1481], [581, 1481], [22, 241], [22, 411], [22, 581], [22, 922], [22, 1092], [22, 1262],
  [797, 241], [797, 411], [797, 581], [797, 922], [797, 1092], [797, 1262]];
const TILE = { w: 433, h: 773, ox: 16, oy: 15 };   // th_basic_table: کاشی گوشه با حاشیهٔ شفاف
function poly(c, pos, path) {
  const ox0 = pos[0] - path[0][0], oy0 = pos[1] - path[0][1];
  c.beginPath(); path.forEach(([x, y], i) => i ? c.lineTo(ox0 + x, oy0 + y) : c.moveTo(ox0 + x, oy0 + y)); c.closePath();
}
function rr(c, x, y, w, h, r) { c.beginPath(); c.moveTo(x + r, y); c.arcTo(x + w, y, x + w, y + h, r); c.arcTo(x + w, y + h, x, y + h, r); c.arcTo(x, y + h, x, y, r); c.arcTo(x, y, x + w, y, r); c.closePath(); }
// شبه تصادفی ثابت (هر بار همان رگه و دانه)
function prng(seed) { let x = seed | 0; return () => { x ^= x << 13; x ^= x >>> 17; x ^= x << 5; return ((x >>> 0) % 10000) / 10000; }; }
const TRAD = 46, RAIL_IN = 58;                       // شعاع گوشهٔ بیرونی میز، پهنای چوب
// نمودار رنگ بر حسب فاصله: [[فاصله، مقدار]...] ← درون یابی خطی
function prof(stops, d) {
  if (d <= stops[0][0]) return stops[0][1];
  for (let i = 1; i < stops.length; i++) if (d <= stops[i][0]) { const [a, va] = stops[i - 1], [b, vb] = stops[i]; return va + (vb - va) * (d - a) / (b - a); }
  return stops[stops.length - 1][1];
}
/* کروم گوشه: زانویی لوله مانند. روشنایی هر نقطه تابع فاصله از لبهٔ بیرونی گرد میز است
   (لبهٔ تیز روشن، شیار تیره، نوار براق، بعد خاکستری صاف) و نزدیک دهانهٔ سوراخ تیره می شود. */
const CHROME_OUT = [[0, 85], [1.4, 250], [3, 255], [5, 118], [7.5, 238], [11, 255], [16, 242], [22, 212], [32, 184], [46, 166], [60, 156]];
let CORNER_TEX = null, SIDE_TEX = null;
function cornerTex() {
  if (CORNER_TEX) return CORNER_TEX;
  const K = 4, N = 120 * K, c = document.createElement('canvas'); c.width = c.height = N;
  const x = c.getContext('2d'), im = x.createImageData(N, N), d8 = im.data;
  for (let j = 0; j < N; j++) for (let i = 0; i < N; i++) {
    const px = (i + .5) / K, py = (j + .5) / K;
    const d = px < TRAD && py < TRAD ? TRAD - Math.hypot(px - TRAD, py - TRAD) : Math.min(px, py);
    const e = Math.hypot(px - 63, py - 63) - 41;                 // فاصله تا لبهٔ سوراخ
    let v = prof(CHROME_OUT, d) * (e < 7 ? .5 + .5 * Math.max(0, e) / 7 : 1);
    if (e > 1 && e < 2.6) v = Math.min(255, v + 40);                   // لبهٔ برق خورده دور سوراخ
    const o = (j * N + i) * 4; d8[o] = v; d8[o + 1] = v; d8[o + 2] = v + 2; d8[o + 3] = 255;
  }
  x.putImageData(im, 0, 0);
  return (CORNER_TEX = c);
}
// کروم جیب وسط: صفحهٔ خمیده روی پهنای ریل (براق نزدیک لبهٔ بیرونی، تیره تر رو به ماهوت)
const CHROME_SIDE = [[0, 60], [2, 140], [4.5, 255], [10, 255], [15, 232], [24, 205], [36, 182], [48, 165], [58, 140]];
function sideTex() {
  if (SIDE_TEX) return SIDE_TEX;
  const K = 4, w = 60 * K, h = 110 * K, c = document.createElement('canvas'); c.width = w; c.height = h;
  const x = c.getContext('2d'), im = x.createImageData(w, h), d8 = im.data;
  for (let j = 0; j < h; j++) for (let i = 0; i < w; i++) {
    const px = (i + .5) / K, py = (j + .5) / K + 703;               // مختصات میز (جیب چپ)
    const e = Math.hypot(px - 47, py - 758) - 34;
    let v = prof(CHROME_SIDE, px);
    const ey = Math.min(Math.abs(py - 708), Math.abs(py - 808));
    if (ey < 2.5) v *= .62 + .15 * ey;                               // لبهٔ بالا و پایین صفحه
    if (e < 6) v *= .55 + .45 * Math.max(0, e) / 6;
    const o = (j * w + i) * 4; d8[o] = v; d8[o + 1] = v; d8[o + 2] = v + 2; d8[o + 3] = 255;
  }
  x.putImageData(im, 0, 0);
  return (SIDE_TEX = c);
}
// چوب ریل: قرمز قهوه ای با رگهٔ طولی، لبهٔ بیرونی پخ خورده و لب روشن کنار کوشن
const WOOD = [[0, '#5b3a2c'], [2.5, '#62301d'], [8, '#76361f'], [28, '#7b3a22'], [48, '#713220'], [54, '#5f2918'], [56.2, '#3c1a10'], [57, '#7c4f41'], [58, '#5a3528']];
function rail(c, x, y, w, h, vertical, flip, seed) {
  const g = vertical ? c.createLinearGradient(flip ? x + w : x, 0, flip ? x : x + w, 0) : c.createLinearGradient(0, flip ? y + h : y, 0, flip ? y : y + h);
  for (const [d, col] of WOOD) g.addColorStop(d / RAIL_IN, col);
  c.fillStyle = g; c.fillRect(x, y, w, h);
  const r = prng(seed), n = 46;
  c.save(); c.beginPath(); c.rect(x, y, w, h); c.clip();
  for (let i = 0; i < n; i++) {
    const p = (vertical ? x + 3 : y + 3) + r() * (RAIL_IN - 8), L = vertical ? h : w, wob = 1 + r() * 2.5, ph = r() * 6, per = 90 + r() * 90;
    c.strokeStyle = r() < .6 ? `rgba(45,12,3,${.05 + r() * .1})` : `rgba(255,170,120,${.025 + r() * .05})`;
    c.lineWidth = .5 + r() * 1.6; c.beginPath();
    for (let t = 0; t <= L; t += 18) { const q = p + Math.sin(t / per + ph) * wob; if (vertical) { if (t) c.lineTo(q, y + t); else c.moveTo(q, y + t); } else if (t) c.lineTo(x + t, q); else c.moveTo(x + t, q); }
    c.stroke();
  }
  c.restore();
}
function opening(c, i) {
  // دهانهٔ سیاه جیب: درون منحنی دیوارهٔ جیب تا خط فک ها + دایرهٔ سوراخ
  const [pos, path] = E.MOUTHS[i], ox0 = pos[0] - path[0][0], oy0 = pos[1] - path[0][1], p = E.POCKETS[i];
  c.beginPath();
  path.slice(2, path.length - 2).forEach(([x, y], k) => k ? c.lineTo(ox0 + x, oy0 + y) : c.moveTo(ox0 + x, oy0 + y));
  c.closePath(); c.fill();
  c.beginPath(); c.arc(p[3] + (i >= 4 ? (i === 4 ? -3 : 3) : 0), p[4], i >= 4 ? 34 : 41, 0, Math.PI * 2); c.fill();
}
/* tableArt — کاشی گوشه ×۴ آینه ای + خال ها + خط سر؛ اول با آرت پلاتو، وگرنه آرت رویه ای */
function paintTable(c) {
  if (ART.table) {
    // چهار ربع میز مثل tableBuffer پلاتو: کاشی با مقیاس ۱:۱ و offset منفی (حاشیهٔ شفافش
    // که خودش سایهٔ نرمِ لبهٔ میز است بیرون می افتد)؛ برای ربع آینه ای به لبهٔ دور منتقل می شود
    const q = [[0, 0, 1, 1], [W, 0, -1, 1], [0, H, 1, -1], [W, H, -1, -1]];
    for (const [x, y, fx, fy] of q) {
      c.save(); c.translate(x, y); c.scale(fx, fy);
      c.drawImage(ART.table, 0, 0, TILE.w, TILE.h, -TILE.ox, -TILE.oy, TILE.w, TILE.h);
      c.restore();
    }
    if (ART.ui) for (const [x, y] of DIAMONDS) c.drawImage(ART.ui, AT.dot[0], AT.dot[1], 14, 14, x, y, 14, 14);
    if (ART.head) c.drawImage(ART.head, 77, E.HEAD - 8, 680, 16);      // خط سرِ پلاتو (۳۴۲×۱۶ کشیده به ۶۸۰)
    return;
  }
  paintTableProc(c);
}
function paintTableProc(c) {
  c.save(); rr(c, 0, 0, W, H, TRAD); c.clip();
  // ریل های چوبی
  rail(c, 0, 0, RAIL_IN, H, true, false, 11); rail(c, W - RAIL_IN, 0, RAIL_IN, H, true, true, 23);
  c.save(); c.beginPath(); c.moveTo(0, 0); c.lineTo(W, 0); c.lineTo(W - RAIL_IN, RAIL_IN); c.lineTo(RAIL_IN, RAIL_IN); c.closePath(); c.clip(); rail(c, 0, 0, W, RAIL_IN, false, false, 37); c.restore();
  c.save(); c.beginPath(); c.moveTo(0, H); c.lineTo(W, H); c.lineTo(W - RAIL_IN, H - RAIL_IN); c.lineTo(RAIL_IN, H - RAIL_IN); c.closePath(); c.clip(); rail(c, 0, H - RAIL_IN, W, RAIL_IN, false, true, 41); c.restore();
  // ماهوت: بیضی روشن وسط، لبه های تیره تر، دانهٔ ریز پارچه
  c.save(); c.beginPath(); c.rect(RAIL_IN, RAIL_IN, W - 2 * RAIL_IN, H - 2 * RAIL_IN); c.clip();
  c.save(); c.translate(W / 2, H / 2); c.scale(1, H / W * .62);
  let g = c.createRadialGradient(0, 0, 10, 0, 0, W * .95);
  g.addColorStop(0, '#59b252'); g.addColorStop(.45, '#4fa448'); g.addColorStop(.8, '#43903e'); g.addColorStop(1, '#3a7b35');
  c.fillStyle = g; c.fillRect(-W, -W * 2, W * 2, W * 4); c.restore();
  const nz = document.createElement('canvas'); nz.width = nz.height = 128;
  const nx = nz.getContext('2d'), id = nx.createImageData(128, 128), rn = prng(7);
  for (let i = 0; i < id.data.length; i += 4) { const v = rn() < .5 ? 0 : 255; id.data[i] = id.data[i + 1] = id.data[i + 2] = v; id.data[i + 3] = 9 + rn() * 14; }
  nx.putImageData(id, 0, 0); c.fillStyle = c.createPattern(nz, 'repeat'); c.fillRect(0, 0, W, H);
  // سایهٔ گلوی جیب روی ماهوت
  for (const p of E.POCKETS) {
    const tx = p[3] + (W / 2 - p[3]) * .2, ty = p[4] + (H / 2 - p[4]) * .03, rr2 = p[2] === 70 ? 70 : 52;
    const sg = c.createRadialGradient(p[3], p[4], 30, tx, ty, rr2); sg.addColorStop(0, 'rgba(0,0,0,.55)'); sg.addColorStop(1, 'rgba(0,0,0,0)');
    c.fillStyle = sg; c.beginPath(); c.arc(tx, ty, rr2, 0, Math.PI * 2); c.fill();
  }
  // کوشن ها: لاستیک سبز، تیره کنار چوب و روشن رو به ماهوت
  for (const [pos, path] of E.RAILS) {
    poly(c, pos, path);
    const side = pos[1] > 100 && pos[1] < H - 100;
    const gr = side ? (pos[0] < W / 2 ? c.createLinearGradient(RAIL_IN, 0, 76, 0) : c.createLinearGradient(W - RAIL_IN, 0, W - 77, 0))
      : (pos[1] < H / 2 ? c.createLinearGradient(0, RAIL_IN, 0, 77) : c.createLinearGradient(0, H - RAIL_IN, 0, H - 78));
    gr.addColorStop(0, '#29511f'); gr.addColorStop(.35, '#2f6328'); gr.addColorStop(.75, '#3b8433'); gr.addColorStop(.93, '#4aa040'); gr.addColorStop(1, '#2a5c22');
    c.fillStyle = gr; c.fill();
  }
  // سایهٔ کوشن روی ماهوت
  const sh = (x, y, w, h, x0, y0, x1, y1) => { const gg = c.createLinearGradient(x0, y0, x1, y1); gg.addColorStop(0, 'rgba(10,40,5,.42)'); gg.addColorStop(.4, 'rgba(10,40,5,.16)'); gg.addColorStop(1, 'rgba(10,40,5,0)'); c.fillStyle = gg; c.fillRect(x, y, w, h); };
  sh(76, 130, 16, 612, 76, 0, 92, 0); sh(76, 774, 16, 612, 76, 0, 92, 0); sh(W - 93, 130, 16, 612, W - 77, 0, W - 93, 0); sh(W - 93, 774, 16, 612, W - 77, 0, W - 93, 0);
  sh(132, 77, W - 264, 16, 0, 77, 0, 93); sh(132, H - 94, W - 264, 16, 0, H - 78, 0, H - 94);
  c.restore();
  // دهانهٔ سیاه جیب ها (روی چوب و ماهوت، زیر کروم)
  c.fillStyle = '#000';
  for (let i = 0; i < 6; i++) opening(c, i);
  // خط سر
  c.strokeStyle = 'rgba(255,255,255,.17)'; c.lineWidth = 2; c.beginPath(); c.moveTo(77, E.HEAD); c.lineTo(W - 77, E.HEAD); c.stroke();
  // کروم گوشه ها (یک بافت، آینه شده) و جیب های وسط
  const tex = cornerTex(), stx = sideTex();
  const corner = (i, sx2, sy2) => {
    const [pos, path] = E.MOUTHS[i];
    c.save(); poly(c, pos, path); c.clip();
    c.translate(sx2 < 0 ? W : 0, sy2 < 0 ? H : 0); c.scale(sx2, sy2); c.drawImage(tex, 0, 0, 120, 120);
    c.restore();
    c.save(); poly(c, pos, path); c.strokeStyle = 'rgba(25,25,25,.6)'; c.lineWidth = 1.3; c.stroke(); c.restore();
  };
  corner(0, 1, 1); corner(1, -1, 1); corner(2, 1, -1); corner(3, -1, -1);
  [[4, 1], [5, -1]].forEach(([i, sx2]) => {
    const [pos, path] = E.MOUTHS[i];
    c.save(); poly(c, pos, path); c.clip(); c.translate(sx2 < 0 ? W : 0, 0); c.scale(sx2, 1); c.drawImage(stx, 0, 703, 60, 110); c.restore();
    c.save(); poly(c, pos, path); c.strokeStyle = 'rgba(25,25,25,.6)'; c.lineWidth = 1.3; c.stroke(); c.restore();
  });
  // خال های صدفی روی چوب
  for (const [x, y] of DIAMONDS) {
    g = c.createRadialGradient(x - 1.2, y - 1.4, .4, x, y, 4.6); g.addColorStop(0, '#ffffff'); g.addColorStop(.7, '#ebe6dc'); g.addColorStop(1, 'rgba(200,190,175,.6)');
    c.fillStyle = g; c.beginPath(); c.arc(x, y, 4.4, 0, Math.PI * 2); c.fill();
  }
  c.restore();
  // لبهٔ بیرونی میز
  rr(c, .8, .8, W - 1.6, H - 1.6, TRAD); c.strokeStyle = 'rgba(0,0,0,.6)'; c.lineWidth = 1.6; c.stroke();
}
function tableImage() {
  if (tableBuf) return tableBuf;
  const b = document.createElement('canvas');
  b.width = W; b.height = H;                                    // رزولوشن اصلی میز (مثلِ tableBuffer پلاتو)
  paintTable(b.getContext('2d'));
  return (tableBuf = b);
}

/* ---------- توپ ها: بافت کروی مثل شیدر توپ پلاتو ----------
   اسپرایت های ball0..ball15 اطلس یک نقشهٔ equirectangular (۱۲۸×۶۴) هستند: هر پیکسلِ کره با
   چرخش کواترنیون توپ نمونه گیری می شود (نور یکنواخت و براقی از اسپرایت hilite می آید). */
let SPH = null, SPH_SRC = null;
function buildSphereTextures(ui) {
  if (!ui) return null;
  const out = {};
  try {
    for (let rank = 0; rank <= 15; rank++) {                       // هر توپ + هرم mipmap (میانگین ۲×۲)
      const r = AT['ball' + rank]; if (!r) continue;
      const cv = document.createElement('canvas'); cv.width = r[2]; cv.height = r[3];
      const cx = cv.getContext('2d'); cx.drawImage(ui, r[0], r[1], r[2], r[3], 0, 0, r[2], r[3]);
      let w = r[2], h = r[3], d = cx.getImageData(0, 0, w, h).data, levels = [{ w, h, d }];
      while (w > 8) {
        const nw = w >> 1, nh = Math.max(1, h >> 1), nd = new Uint8ClampedArray(nw * nh * 4), pd = levels[levels.length - 1].d;
        for (let y = 0; y < nh; y++) for (let x = 0; x < nw; x++) for (let c = 0; c < 4; c++) {
          const y0 = Math.min(h - 1, y * 2), y1 = Math.min(h - 1, y * 2 + 1);
          nd[(y * nw + x) * 4 + c] = (pd[(y0 * w + x * 2) * 4 + c] + pd[(y0 * w + x * 2 + 1) * 4 + c] +
            pd[(y1 * w + x * 2) * 4 + c] + pd[(y1 * w + x * 2 + 1) * 4 + c]) >> 2;
        }
        w = nw; h = nh; levels.push({ w, h, d: nd });
      }
      out[rank] = levels;
    }
  } catch (e) { return null; }                                     // بوم آلوده (مثلاً file://)
  return out;
}
function sphere(b, rpx) {
  if (SPH_SRC !== ART.ui) { SPH_SRC = ART.ui; SPH = buildSphereTextures(ART.ui); for (const x of balls) x._rc = null; for (const k in GAP) GAP[k]._rc = null; }
  const levels = SPH && SPH[b.k];
  if (!levels) return null;
  const D2 = Math.ceil(rpx * 2) + 2, q = b.q, rc = b._rc;
  if (rc && rc.D === D2 && rc.q[0] === q[0] && rc.q[1] === q[1] && rc.q[2] === q[2] && rc.q[3] === q[3]) return rc.cv;
  let r = rc;
  if (!r || r.D !== D2) { const c = document.createElement('canvas'); c.width = c.height = D2; r = b._rc = { cv: c, cx: c.getContext('2d'), D: D2 }; r.img = r.cx.createImageData(D2, D2); }
  r.q = q.slice();
  let L2 = 0;                                                      // سطح mip: تکسل بر پیکسل در مرکز ≈ w / (2π·r)
  while (L2 < levels.length - 1 && levels[L2].w / (2 * Math.PI * rpx) > 1.25) L2++;
  const tex = levels[L2], tw = tex.w, th = tex.h, td = tex.d;
  const [w, x, y, z] = q;
  const m00 = 1 - 2 * (y * y + z * z), m01 = 2 * (x * y - w * z), m02 = 2 * (x * z + w * y);
  const m10 = 2 * (x * y + w * z), m11 = 1 - 2 * (x * x + z * z), m12 = 2 * (y * z - w * x);
  const m20 = 2 * (x * z - w * y), m21 = 2 * (y * z + w * x), m22 = 1 - 2 * (x * x + y * y);
  const out = r.img.data, cc = D2 / 2, inv = 1 / rpx, TP = Math.PI * 2;
  for (let j = 0; j < D2; j++) {
    const uy = (j + .5 - cc) * inv;
    for (let i = 0; i < D2; i++) {
      const ux = (i + .5 - cc) * inv, o = (j * D2 + i) * 4, d2 = ux * ux + uy * uy;
      let cov = (1 - Math.sqrt(d2)) * rpx + .5;                    // پوشش لبه (ضد پله)
      if (cov <= 0) { out[o + 3] = 0; continue; }
      if (cov > 1) cov = 1;
      const nz = -Math.sqrt(Math.max(0, 1 - d2));                  // رو به بیننده = −z
      const lx = m00 * ux + m10 * uy + m20 * nz;                   // world → body (ترانهادهٔ چرخش)
      const ly0 = m01 * ux + m11 * uy + m21 * nz;
      const lz = m02 * ux + m12 * uy + m22 * nz;
      const ly = ly0 > 1 ? 1 : ly0 < -1 ? -1 : ly0;
      const fu = ((Math.atan2(-lx, lz) + Math.PI) / TP) * tw - .5;
      const fv = ((Math.asin(ly) + Math.PI / 2) / Math.PI) * th - .5;
      let x0 = Math.floor(fu), y0 = Math.floor(fv);                // نمونه برداری دوخطی
      const ax = fu - x0, ay = fv - y0;
      let x1 = x0 + 1, y1 = y0 + 1;
      x0 = ((x0 % tw) + tw) % tw; x1 = ((x1 % tw) + tw) % tw;
      y0 = y0 < 0 ? 0 : y0 > th - 1 ? th - 1 : y0; y1 = y1 < 0 ? 0 : y1 > th - 1 ? th - 1 : y1;
      const p00 = (y0 * tw + x0) * 4, p10 = (y0 * tw + x1) * 4, p01 = (y1 * tw + x0) * 4, p11 = (y1 * tw + x1) * 4;
      const w00 = (1 - ax) * (1 - ay), w10 = ax * (1 - ay), w01 = (1 - ax) * ay, w11 = ax * ay;
      out[o] = td[p00] * w00 + td[p10] * w10 + td[p01] * w01 + td[p11] * w11;
      out[o + 1] = td[p00 + 1] * w00 + td[p10 + 1] * w10 + td[p01 + 1] * w01 + td[p11 + 1] * w11;
      out[o + 2] = td[p00 + 2] * w00 + td[p10 + 2] * w10 + td[p01 + 2] * w01 + td[p11 + 2] * w11;
      out[o + 3] = 255 * cov;
    }
  }
  r.cx.putImageData(r.img, 0, 0);
  return r.cv;
}

/* مسیر جایگزین (بدون اطلس): بافت رویه ای + نور و برق */
const TEX = {};
function texture(k) {
  if (TEX[k]) return TEX[k];
  const c = document.createElement('canvas'); c.width = 256; c.height = 128;
  const x = c.getContext('2d'), col = colOf(k), stripe = k > 8;
  x.fillStyle = stripe || k === 0 ? '#F4F1E8' : col; x.fillRect(0, 0, 256, 128);
  if (stripe) { x.fillStyle = col; x.fillRect(0, 34, 256, 60); }
  if (k > 0) {
    for (const cx of [128, 0, 256]) {
      x.fillStyle = '#F9F7F1'; x.beginPath(); x.ellipse(cx, 64, 24, 21, 0, 0, Math.PI * 2); x.fill();
      x.fillStyle = '#141414'; x.font = `900 ${k > 9 ? 23 : 28}px "Arial Black",Arial,system-ui,sans-serif`; x.textAlign = 'center'; x.textBaseline = 'middle';
      x.fillText(String(k), cx, 66);
      if (k === 6 || k === 9) x.fillRect(cx - 7, 80, 14, 2.5);   // خط زیر ۶ و ۹
    }
  }
  return (TEX[k] = { w: 256, h: 128, d: x.getImageData(0, 0, 256, 128).data });
}
const LX = -.38, LY = -.52, LZ = -.76;
const HL = (() => { const hx = LX, hy = LY, hz = LZ - 1, l = Math.hypot(hx, hy, hz); return [hx / l, hy / l, hz / l]; })();
function sphereProc(b, rpx) {
  const D2 = Math.ceil(rpx * 2) + 2, q = b.q, rc = b._pc;
  if (rc && rc.D === D2 && rc.q[0] === q[0] && rc.q[1] === q[1] && rc.q[2] === q[2] && rc.q[3] === q[3]) return rc.cv;
  let r = rc;
  if (!r || r.D !== D2) { const c = document.createElement('canvas'); c.width = c.height = D2; r = b._pc = { cv: c, cx: c.getContext('2d'), D: D2 }; r.img = r.cx.createImageData(D2, D2); }
  r.q = q.slice();
  const t = texture(b.k), tw = t.w, th = t.h, td = t.d;
  const [w, x, y, z] = q;
  const m00 = 1 - 2 * (y * y + z * z), m01 = 2 * (x * y - w * z), m02 = 2 * (x * z + w * y);
  const m10 = 2 * (x * y + w * z), m11 = 1 - 2 * (x * x + z * z), m12 = 2 * (y * z - w * x);
  const m20 = 2 * (x * z - w * y), m21 = 2 * (y * z + w * x), m22 = 1 - 2 * (x * x + y * y);
  const out = r.img.data, cc = D2 / 2, inv = 1 / rpx, TP = Math.PI * 2;
  for (let j = 0; j < D2; j++) {
    const uy = (j + .5 - cc) * inv;
    for (let i = 0; i < D2; i++) {
      const ux = (i + .5 - cc) * inv, o = (j * D2 + i) * 4, d2 = ux * ux + uy * uy;
      let cov = (1 - Math.sqrt(d2)) * rpx + .5;
      if (cov <= 0) { out[o + 3] = 0; continue; }
      if (cov > 1) cov = 1;
      const nz = -Math.sqrt(Math.max(0, 1 - d2));
      const lx = m00 * ux + m10 * uy + m20 * nz, ly0 = m01 * ux + m11 * uy + m21 * nz, lz = m02 * ux + m12 * uy + m22 * nz;
      const ly = ly0 > 1 ? 1 : ly0 < -1 ? -1 : ly0;
      const tu = Math.floor(((Math.atan2(-lx, lz) + Math.PI) / TP) * tw) % tw, tv = Math.min(th - 1, Math.floor(((Math.asin(ly) + Math.PI / 2) / Math.PI) * th));
      const p = (tv * tw + (tu < 0 ? tu + tw : tu)) * 4;
      // رنگ تقریبا تخت + برق براق بزرگ بالا چپ + لکهٔ تیز + تیرگی گرم لبهٔ پایین راست
      const rr0 = Math.sqrt(d2), gx = ux + .4, gy = uy + .42;
      let gl = 1 - Math.sqrt(gx * gx + gy * gy) / .5; gl = gl > 0 ? Math.pow(gl, 1.5) * .8 : 0;
      const hh = Math.max(0, ux * HL[0] + uy * HL[1] + nz * HL[2]), spk = Math.pow(hh, 180) * .9;
      const t2 = Math.max(0, (rr0 - .66) / .34), rim = t2 * t2 * (3 - 2 * t2) * (.4 + .6 * Math.max(0, (ux + uy) / 1.41 + .3)) * .62;
      const flat = .93 + .07 * Math.max(0, ux * LX + uy * LY + nz * LZ), wgt = Math.min(1, gl + spk);
      for (let ch2 = 0; ch2 < 3; ch2++) {
        let v = td[p + ch2] * flat;
        v = v * (1 - rim) + [52, 30, 18][ch2] * rim;
        out[o + ch2] = v * (1 - wgt) + 255 * wgt;
      }
      out[o + 3] = 255 * cov;
    }
  }
  r.cx.putImageData(r.img, 0, 0);
  return r.cv;
}
// رسم کره + براقی رویی (اسپرایت hilite پلاتو با اندازهٔ قطر + ۲×1.75، هم مرکز توپ)
function ballSprite(b, sx, sy, rp, hiliteD) {
  const img = sphere(b, rp * dpr) || sphereProc(b, rp * dpr);
  const d = img.width / dpr;
  ctx.drawImage(img, sx - d / 2, sy - d / 2, d, d);
  if (SPH && ART.ui && SPH[b.k]) {
    const hs = ((hiliteD || D) + 2 * 1.75) * s;
    ctx.drawImage(ART.ui, AT.hilite[0], AT.hilite[1], 43, 43, sx - hs / 2, sy - hs / 2, hs, hs);
  }
}
function drawBall(b, now) {
  const [sx, sy] = toS(b.x, b.y), rp = R * s;
  if (b.sink) {
    const p = E.POCKETS[b.sink.p], dep = Math.min(1, Math.max(0, (now - b.sink.t0) / (SINK_TIME * 1000))), e = dep * dep * (3 - 2 * dep);
    const [hx, hy] = toS(p[3], p[4]), hr = (p[2] === 70 ? 39 : 37) * s;
    ctx.save(); ctx.beginPath(); ctx.arc(hx, hy, hr + (1 - e) * rp * 3, 0, Math.PI * 2); ctx.clip();
    ctx.translate(sx, sy); ctx.scale(1 - .32 * e, 1 - .32 * e); ctx.translate(-sx, -sy);
    ballSprite(b, sx, sy, rp);
    ctx.globalAlpha = .15 + .7 * e; ctx.fillStyle = '#000'; ctx.beginPath(); ctx.arc(sx, sy, rp * 1.06, 0, Math.PI * 2); ctx.fill();
    ctx.restore(); return;
  }
  ballSprite(b, sx, sy, rp);
}
function drawShadows() {
  for (const b of balls) {
    if (!b.on || b.sink) continue;
    const [sx, sy] = toS(b.x, b.y), rp = R * s;
    if (ART.ui) {
      // سایهٔ اسپرایت پلاتو: جابه جایی شعاعی از مرکز میز (نور بالای مرکز است)
      const sw = 45 * s, dx = 45 * .11 * (b.x - W / 2) / (W / 2) * s, dy = 45 * .11 * (b.y - H / 2) / (H / 2) * s;
      ctx.drawImage(ART.ui, AT.ball_shadow[0], AT.ball_shadow[1], 45, 45, sx - sw / 2 + dx, sy - sw / 2 + dy, sw, sw);
      continue;
    }
    // جایگزین بدون آرت: سایهٔ تخت نیمه شفاف با لبهٔ نرم کوتاه
    const g = ctx.createRadialGradient(sx, sy, rp * .9, sx, sy, rp * 1.14); g.addColorStop(0, 'rgba(0,0,0,.5)'); g.addColorStop(1, 'rgba(0,0,0,0)');
    ctx.fillStyle = g; ctx.beginPath(); ctx.arc(sx, sy, rp * 1.14, 0, Math.PI * 2); ctx.fill();
  }
}

/* ---------- ستون توپ های هر طرف کنار میز: چپ حریف، راست تو؛ آخرش جای ۸ ---------- */
const GAP = {};
function drawColumns() {
  const g = G(); if (!g || g.solids < 0) return;
  const mt = WATCH ? 1 : myTeam();
  [[1 - mt, 36.5], [mt, 562.5]].forEach(([tm, cx]) => {
    const solids = g.solids === tm, base = solids ? 1 : 9, list = [];
    for (let k = base; k < base + 7; k++) if (g.balls[k]) list.push(k);
    const eight = !list.length && g.balls[8];
    const active = g.turn != null && teamOf(g.turn) === tm;
    ctx.save(); ctx.globalAlpha = active ? 1 : .55;
    for (let i = 0; i <= list.length; i++) {
      const x = cx * u, y = (280 - dy + i * 29) * u, r = 11.5 * u, k = i < list.length ? list[i] : (eight ? 8 : -1);
      if (k < 0) { ctx.fillStyle = 'rgba(0,0,0,.55)'; ctx.beginPath(); ctx.arc(x, y, r * .86, 0, Math.PI * 2); ctx.fill(); continue; }
      const gb = GAP[k] || (GAP[k] = { k, q: [0, 0, 1, 0], _rc: null, _pc: null });   // شماره رو به بیننده (GAP_Q پلاتو)
      ballSprite(gb, x, y, r, 43);
    }
    ctx.restore();
  });
}

/* ---------- چوب و خط های نشانه ---------- */
function cuePath(c, len, th) {
  c.beginPath(); c.moveTo(0, -th * .3); c.lineTo(-len, -th * .55); c.arcTo(-len - th * .5, 0, -len, th * .55, th * .5); c.lineTo(-len, th * .55); c.lineTo(0, th * .3); c.closePath();
}
// نوک آبی تیره، حلقهٔ سفید، میلهٔ افرا، اتصال فلزی، دستهٔ چوب تیره با حلقه های طلایی، ته لاستیکی
function cueFill(c, len) {
  const g = c.createLinearGradient(0, 0, -len, 0), st = (t, col) => g.addColorStop(Math.min(1, t), col);
  st(0, '#2b4a7c'); st(.008, '#2b4a7c'); st(.009, '#f4f1e9'); st(.032, '#e9e4d8'); st(.033, '#ecd7ab'); st(.25, '#e3c792'); st(.5, '#d6b27a');
  st(.555, '#c9a066'); st(.556, '#cfcfcf'); st(.565, '#7d7d7d'); st(.574, '#d8d8d8'); st(.575, '#1a1a1a'); st(.59, '#1a1a1a'); st(.591, '#5b2310');
  st(.7, '#3d1608'); st(.71, '#c79b3c'); st(.716, '#3d1608'); st(.86, '#2e1006'); st(.865, '#c79b3c'); st(.87, '#2e1006'); st(.975, '#2a0e05'); st(.976, '#111'); st(1, '#111');
  return g;
}
function drawCue(cx, cy, a, pull) {
  const [sx, sy] = toS(cx, cy), gap = (D * .8 + 250 * pull) * s;    // فاصلهٔ نوک تا مرکز توپ
  ctx.save(); ctx.translate(sx, sy); ctx.rotate(a); ctx.translate(-gap, 0);
  if (ART.ui) {
    const len = 1022 * s, th = 30 * s;                              // اندازهٔ چوب پلاتو (Qh×Vv)
    // سایهٔ پلاتو: دور از مرکز میز (نور بالای مرکز است) — مثلِ سایهٔ توپ ها
    const mx = cx - Math.cos(a) * (gap / s + 511), my = cy - Math.sin(a) * (gap / s + 511);
    const dx = mx - W / 2, dy = my - H / 2, dl = Math.hypot(dx, dy) || 1;
    const off = (4 + 6 * Math.min(1, dl / (H / 2))) * s * dpr;
    ctx.shadowColor = 'rgba(0,0,0,.38)'; ctx.shadowBlur = 5 * s * dpr;
    ctx.shadowOffsetX = dx / dl * off; ctx.shadowOffsetY = dy / dl * off;
    ctx.drawImage(ART.ui, AT.cs_basic[0], AT.cs_basic[1], 1020, 30, -len, -th / 2, len, th);
    ctx.restore(); return;
  }
  const len = 1000 * s, th = 16 * s;
  ctx.shadowColor = 'rgba(0,0,0,.45)'; ctx.shadowBlur = 7 * s * dpr; ctx.shadowOffsetX = 5 * s * dpr; ctx.shadowOffsetY = 9 * s * dpr;
  cuePath(ctx, len, th); ctx.fillStyle = cueFill(ctx, len); ctx.fill();
  ctx.shadowColor = 'transparent';
  // براقی استوانه ای
  const hg = ctx.createLinearGradient(0, -th * .55, 0, th * .55);
  hg.addColorStop(0, 'rgba(0,0,0,.35)'); hg.addColorStop(.28, 'rgba(255,255,255,.38)'); hg.addColorStop(.42, 'rgba(255,255,255,.05)'); hg.addColorStop(1, 'rgba(0,0,0,.45)');
  cuePath(ctx, len, th); ctx.fillStyle = hg; ctx.fill();
  ctx.restore();
}
// رنگ توپ ها برای خطِ مسیر توپ هدف (AIM_COLORS پلاتو؛ ۸ مشکی)
const AIM_COLORS = ['#fffff1', '#ffc625', '#1937a4', '#ff2a25', '#371594', '#ff6a27', '#1f530c', '#560c11', '#000000'];
function stroke(pts, color) {
  ctx.save(); ctx.lineJoin = 'round'; ctx.lineCap = 'butt'; ctx.beginPath();
  pts.forEach(([x, y], i) => { const [a, b] = toS(x, y); i ? ctx.lineTo(a, b) : ctx.moveTo(a, b); });
  // حاشیهٔ تیره + سایهٔ نرم، بعد هستهٔ رنگی (خط نشانهٔ پلاتو)
  ctx.shadowColor = 'rgba(0,0,0,.2)'; ctx.shadowBlur = 3 * s * dpr;
  ctx.strokeStyle = 'rgba(0,0,0,.67)'; ctx.lineWidth = 10 * s; ctx.stroke();
  ctx.shadowColor = 'transparent'; ctx.shadowBlur = 0;
  ctx.strokeStyle = color; ctx.lineWidth = 6 * s; ctx.stroke(); ctx.restore();
}
function cur() { return balls.map(b => b.on && !b.sink ? [b.x, b.y] : null); }
function drawAim() {
  if (!showLines) return;
  const pos = cur(); if (!pos[0]) return;
  const a = E.aim(pos, angle); if (!a) return;
  const c = pos[0], dx = Math.cos(angle), dy = Math.sin(angle), ln = a.dist - D;
  if (ln > 0) stroke([[c[0] + dx * R, c[1] + dy * R], [c[0] + dx * (a.dist - R), c[1] + dy * (a.dist - R)]], AIM_COLORS[0]);
  const g = G(), invalid = a.hit > 0 && g && g.solids >= 0 && g.mine && g.mine.indexOf(a.hit) < 0;
  const gr = R - 10 * .2;                                             // حلقهٔ توپ شبح: R − حاشیه×.2 = ۱۸
  const ring = [...Array(40)].map((_, i) => [a.ghost[0] + Math.cos(i / 40 * Math.PI * 2) * gr, a.ghost[1] + Math.sin(i / 40 * Math.PI * 2) * gr]);
  stroke(ring, invalid ? '#ff0000' : AIM_COLORS[0]);
  if (invalid) { const d = gr * .72; stroke([[a.ghost[0] - d, a.ghost[1] - d], [a.ghost[0] + d, a.ghost[1] + d]], '#ff0000'); }
  if (a.hit > 0) {
    const t = pos[a.hit]; let ux = t[0] - a.ghost[0], uy = t[1] - a.ghost[1]; const ul = Math.hypot(ux, uy) || 1; ux /= ul; uy /= ul;
    const cs = dx * ux + dy * uy, hl = Math.max(15, Math.min(75, (1250 - ln) / 12 * cs * cs));
    stroke([[t[0] + ux * R, t[1] + uy * R], [t[0] + ux * (R + hl), t[1] + uy * (R + hl)]], AIM_COLORS[a.hit > 8 ? a.hit - 8 : a.hit] || AIM_COLORS[0]);
    const dl = Math.min(75, (1 - cs) * 200);
    if (dl > 3.5) {
      const cr = dx * uy - dy * ux, px = cr >= 0 ? uy : -uy, py = cr >= 0 ? -ux : ux, gw = (2 * R + 10 * .5) * .5;
      stroke([[a.ghost[0] + px * gw, a.ghost[1] + py * gw], [a.ghost[0] + px * (gw + dl), a.ghost[1] + py * (gw + dl)]], AIM_COLORS[0]);
    }
  }
}

/* ---------- حلقهٔ رسم ---------- */
function myTurnNow() { const g = G(); return !!(g && !WATCH && snap.status === 'playing' && g.turn === me && !g.over && !anim); }
/* انیمیشن هالهٔ راهنما (کلاس Mc پلاتو): scale .25→1 و alpha .36→.75 در ۳۰۰ms، ۱۰۰ms مکث،
   بعد scale→.3 و alpha→.1 در ۵۰۰ms، سپس ۳ ثانیه خاموش و تکرار */
function hintPulse(t) {
  t = t % 3.9;
  let k;
  if (t < .3) { k = t / .3; k = 1 - (1 - k) * (1 - k); return { s: .25 + .75 * k, a: .36 + .39 * k }; }
  if (t < .4) return { s: 1, a: .75 };
  if (t < .9) { k = (t - .4) / .5; k = k * k; return { s: 1 - .7 * k, a: .75 - .65 * k }; }
  return null;
}
function frame(now) {
  requestAnimationFrame(frame);
  if (document.hidden) return;
  if (anim) stepAnim(now);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, cw, ch);
  if (ART.table) {
    ctx.drawImage(tableImage(), ox, oy, W * s, H * s);               // سایهٔ نرم لبه خودِ کاشی پلاتوست
  } else {
    ctx.save(); ctx.shadowColor = 'rgba(0,0,0,.55)'; ctx.shadowBlur = 24 * u; ctx.shadowOffsetY = 8 * u;
    ctx.drawImage(tableImage(), ox, oy, W * s, H * s); ctx.restore();
  }
  drawColumns();
  drawShadows();
  // هالهٔ راهنما روی توپ های خودم (شروع نوبت و وقتی مدتی دست نزده ام) — اسپرایت پلاتو
  const g = G(), mine = myTurnNow() && g.solids >= 0 ? g.mine || [] : [];
  if (mine.length) {
    const idle = now - Math.max(lastInput, hintAt);
    if (idle < 900 || now - lastInput > 3000) {
      const hl = hintPulse(idle / 1000);
      if (hl) for (const n of mine) {
        const b = balls[n]; if (!b.on) continue;
        const [sx, sy] = toS(b.x, b.y);
        if (ART.ui) {
          const hr0 = 70 * hl.s * s;
          ctx.save(); ctx.globalAlpha = hl.a;
          ctx.drawImage(ART.ui, AT.valid_ball_highlight[0], AT.valid_ball_highlight[1], 70, 70, sx - hr0 / 2, sy - hr0 / 2, hr0, hr0);
          ctx.restore();
        } else {
          const rad = R * s * (.6 + 1.15 * hl.s);
          const gr = ctx.createRadialGradient(sx, sy, R * s * .8, sx, sy, rad); gr.addColorStop(0, `rgba(255,255,255,${.75 * hl.a})`); gr.addColorStop(1, 'rgba(255,255,255,0)');
          ctx.fillStyle = gr; ctx.beginPath(); ctx.arc(sx, sy, rad, 0, Math.PI * 2); ctx.fill();
        }
      }
    }
  }
  for (const b of balls) if (b.on && b.k !== 0) drawBall(b, now);
  if (balls[0].on) drawBall(balls[0], now);
  if (myTurnNow() && g.bih && balls[0].on) {
    const [sx, sy] = toS(balls[0].x, balls[0].y), ok = E.validPlace(cur().map((p, i) => i ? p : null), g.breaking, balls[0].x, balls[0].y);
    ctx.save(); ctx.setLineDash([5 * u, 4 * u]); ctx.lineWidth = 2.2 * u; ctx.strokeStyle = ok ? 'rgba(245,196,81,.95)' : '#ff3b30';
    ctx.beginPath(); ctx.arc(sx, sy, R * s * 1.8, 0, Math.PI * 2); ctx.stroke(); ctx.restore();
  }
  if (myTurnNow() && !placing && balls[0].on) { drawAim(); drawCue(balls[0].x, balls[0].y, angle, power); }
  if (strike) {
    const k = Math.min(1, (now - strike.t0) / strike.dur), pull = strike.p * (k < .7 ? 1 - k / .7 * .15 : (1 - (k - .7) / .3) * .85) - (k > .95 ? .1 : 0);
    drawCue(strike.x, strike.y, strike.a, Math.max(-.12, pull));
    if (k >= 1 && !strike.hold) strike = null;
  }
}

/* ---------- پخش یک ضربه از فریم های سرور ---------- */
function playShot(e) {
  return new Promise(done => {
    const ids = e.ids || [], F = e.frames || [];
    if (!F.length) { done(); return; }
    const hits = (e.hits || []).slice(), pots = (e.pots || []).map(p => ({ k: p[0], cap: p[1], end: p[2], p: p[3] }));
    for (const k of ids) { const b = balls[k]; b.on = true; b.sink = null; }
    anim = { e, ids, F, hits, pots, t0: performance.now(), done };
  });
}
function stepAnim(now) {
  // زمان rAF گاهی کمی پیش از performance.now() لحظهٔ شروع است
  const a = anim, t = Math.max(0, (now - a.t0) / 1000), fi = t * 30, i0 = Math.min(a.F.length - 1, Math.floor(fi)), i1 = Math.min(a.F.length - 1, i0 + 1), f = Math.min(1, fi - i0);
  a.ids.forEach((k, j) => {
    const b = balls[k], x0 = a.F[i0][2 * j], y0 = a.F[i0][2 * j + 1], x1 = a.F[i1][2 * j], y1 = a.F[i1][2 * j + 1];
    if (x1 < 0 && x0 < 0) { b.on = false; b.sink = null; return; }
    const nx = x1 < 0 ? x0 : x0 + (x1 - x0) * f, ny = y1 < 0 ? y0 : y0 + (y1 - y0) * f;
    if (b.on) roll(b, nx - b.x, ny - b.y);
    b.x = nx; b.y = ny;
  });
  for (const p of a.pots) {
    const b = balls[p.k];
    if (t >= p.end) { b.on = false; b.sink = null; }
    else if (t >= p.cap && !b.sink) { b.sink = { p: p.p, t0: a.t0 + p.cap * 1000 }; snd.pocket(p.k, E.POCKETS[p.p][0]); }
  }
  while (a.hits.length && a.hits[0][0] <= t) {
    const [, kind, gg, hx] = a.hits.shift();
    if (kind === 'b') snd.ball(gg, hx); else snd.rail(gg * (kind === 'r' ? 1 : .6), hx);
    if (kind === 'b' && gg > .6) haptic('light');
  }
  if (t >= a.F.length / 30) { anim = null; a.done(); }
}
function setBalls(pos) { pos.forEach((p, k) => { const b = balls[k]; b.sink = null; if (p) { b.on = true; b.x = p[0]; b.y = p[1]; } else b.on = false; }); }

/* ---------- صدا: فایل های واقعی پلاتو (static/sfx/plato) — برخورد، ریل، جیب، ضربهٔ چوب ---------- */
const pan = x => x == null ? 0 : Math.max(-1, Math.min(1, (x / W - .5) * 1.3));
const snd = {
  ball(g, x) { sfx.bl.ball(g, pan(x)); },
  rail(g, x) { sfx.bl.rail(g, pan(x)); },
  pocket(k, x) { sfx.bl.pocket(k, pan(x)); },
  cue(p, x) { sfx.bl.cue(p, pan(x)); },
  rack() { sfx.bl.rack(); },
  turn() { sfx.bl.turn(); },
  tap() { sfx.bl.tap(); },
};

/* ---------- هدر: بازیکن ها (حریف چپ، خودت راست)، VS، تایمر بالای سر نوبت دار ---------- */
let headKey = '';
function seatsLayout(g) {
  const mt = WATCH ? 1 : myTeam(), team = t => g.order.filter((c, k) => k % 2 === t);
  const mine = team(mt).sort((a, b) => (a === me) - (b === me)), theirs = team(1 - mt);
  if (g.n === 4) return [[theirs[0], 105], [theirs[1], 222], [mine[0], 378], [mine[1], 494]];
  return [[theirs[0], 222], [mine[0], 378]];
}
function renderPlayers(g) {
  const key = JSON.stringify([g.order.map(c => [g.players[c].name, g.players[c].pic, g.players[c].out]), g.turn, g.over, me, WATCH]);
  if (key === headKey) return;
  headKey = key;
  // تایمر فقط یکی است و بالای سر کسی می نشیند که نوبتش است
  const at = seatsLayout(g).find(([c]) => c === g.turn), tm = $('timer');
  tm.hidden = !at || !!g.over;
  if (at) tm.style.left = `calc(${at[1]} * var(--u))`;
  $('players').innerHTML = seatsLayout(g).map(([c, x]) => {
    const p = g.players[c] || {}, turn = g.turn === c && !g.over;
    return `<div class="pl${turn ? ' turn' : ''}${isMe(c) ? ' mine' : ''}${p.out ? ' out' : ''}" data-seat="${c}" style="left:calc(${x} * var(--u))">${face(p, 'transparent')}<span class="pname">${(p.name || '').replace(/[<>&]/g, '')}</span><span class="yturn">Your Turn</span></div>`;
  }).join('');
}
function msgText(g) {
  if (flash && Date.now() < flash.until) return flash;
  if (g.over) return { t: 'پایان بازی' };
  if (!g.turn) return { t: '…' };
  if (isMe(g.turn)) {
    if (g.breaking) return { t: 'بریک با توست' };
    if (g.bih) return { t: 'توپ در دست؛ سفید را بگذار' };
    if (g.solids < 0) return { t: MSG.open };
    const grp = g.players[me] && g.players[me].group;
    return { t: g.mine && g.mine.length === 1 && g.mine[0] === 8 ? MSG.on_8 : `گروه تو: ${GROUP_FA[grp] || ''}` };
  }
  const q = g.players[g.turn] || {}, mate = !WATCH && teamOf(g.turn) === myTeam();
  return { t: `نوبت ${mate ? 'یارت ' : ''}${q.name || 'حریف'}`, em: q.bot || q.out ? 'فکر می‌کند…' : '' };
}
function renderMsg(g) {
  const m = msgText(g), el = $('msg'), html = `${m.t}${m.em ? `<em>${m.em}</em>` : ''}`;
  if (html !== el.dataset.k) { el.dataset.k = html; el.innerHTML = html; }
  el.classList.toggle('foul', !!m.foul);
}
function flashMsg(t, foul) { flash = { t, foul, until: Date.now() + 2600 }; if (G()) renderMsg(G()); setTimeout(() => { if (G()) renderMsg(G()); }, 2700); }
function renderAll(g) {
  renderPlayers(g); renderMsg(g);
  setDeadline(g.deadline_ms);
  readyAt = Date.now() + (g.ready_ms || 0);
  turnMs = g.turn_ms || 30000;
  frameEl.classList.toggle('wait', !myTurnNow());
  tickTimer();
}
function setDeadline(ms) {
  const d = ms ? Date.now() + ms : 0;
  if (!d) { deadlineAt = 0; return; }
  if (!deadlineAt || Math.abs(d - deadlineAt) > 1500) warned = false;
  if (!deadlineAt || Math.abs(d - deadlineAt) > 700) deadlineAt = d;
}
function tickTimer() {
  const g = G(); if (!g) return;
  const left = deadlineAt ? Math.max(0, deadlineAt - Date.now()) : 0, fr = deadlineAt ? Math.min(1, left / turnMs) : 1;
  const bar = $('timerBar'); bar.style.width = (fr * 100).toFixed(1) + '%'; bar.style.background = fr > .25 ? '#f2c832' : '#e8503f';
  if (isMe(g.turn) && deadlineAt && fr < .25 && !warned) { warned = true; sfx.tick(); haptic('warning'); }
}
setInterval(tickTimer, 250);

/* ---------- ورودی: نشانه گیری و توپ در دست ---------- */
function pt(ev) { const r = cv.getBoundingClientRect(); return toT((ev.clientX - r.left) * cw / r.width, (ev.clientY - r.top) * ch / r.height); }
const canAct = () => myTurnNow() && !acting && !busy && Date.now() >= readyAt - 250;
// یک لمس (بدون کشیدن): نوک چوب به همان نقطه نشانه می رود.
// کشیدن: چوب برعکس جهت کشیدن می چرخد؛ ته چوب خلاف جهت انگشت می رود و چوب دور توپ سفید
// می چرخد (بی پرش، نسبت به جای شروع کشیدن). اهرم بلند = چرخش آرام تر و نشانه گیری دقیق تر.
const DRAG_PX = 7, LEVER = 520;      // آستانهٔ تشخیص کشیدن (پیکسل صفحه) و طول اهرم (واحد میز)
let grab = null;
cv.addEventListener('pointerdown', ev => {
  GC.loadSamples(); closeMenu();
  if (!canAct()) return;
  const [x, y] = pt(ev), g = G(), c = balls[0];
  lastInput = performance.now();
  try { cv.setPointerCapture(ev.pointerId); } catch (e) {}
  if (g.bih && c.on && Math.hypot(x - c.x, y - c.y) < R * 3) { placing = true; movePlace(x, y); return; }
  aiming = true;
  grab = { x, y, cx: ev.clientX, cy: ev.clientY, a: angle, moved: false };
});
cv.addEventListener('pointermove', ev => {
  if (!placing && !aiming) return;
  const [x, y] = pt(ev); lastInput = performance.now();
  if (placing) { movePlace(x, y); return; }
  if (!grab) return;
  if (!grab.moved && Math.hypot(ev.clientX - grab.cx, ev.clientY - grab.cy) < DRAG_PX) return;
  grab.moved = true;
  dragButt(grab.x - x, grab.y - y);     // برعکس جهت انگشت
});
const endPtr = ev => {
  if (placing) { placing = false; const g = G(); if (g && !E.validPlace(cur().map((p, i) => i ? p : null), g.breaking, balls[0].x, balls[0].y)) toast(errText({ code: 'bad_place' })); }
  if (aiming && grab && !grab.moved && ev && ev.type === 'pointerup') aimAt(grab.x, grab.y);   // فقط یک لمس
  aiming = false; grab = null;
};
cv.addEventListener('pointerup', endPtr); cv.addEventListener('pointercancel', endPtr);
function aimAt(x, y) { const c = balls[0]; if (Math.hypot(x - c.x, y - c.y) > R * .6) angle = Math.atan2(y - c.y, x - c.x); }
// ته چوب (پشت توپ سفید، روی امتداد مخالف نشانه) به اندازهٔ جابه جایی داده شده جابه جا می شود
function dragButt(dx, dy) {
  const c = balls[0], bx = c.x - Math.cos(grab.a) * LEVER + dx, by = c.y - Math.sin(grab.a) * LEVER + dy;
  if (Math.hypot(c.x - bx, c.y - by) > R) angle = Math.atan2(c.y - by, c.x - bx);
}
function movePlace(x, y) {
  const g = G();
  x = Math.min(E.MAX_X, Math.max(E.MIN_X, x)); y = Math.min(E.MAX_Y, Math.max(g.breaking ? E.BREAK_MIN_Y : E.MIN_Y, y));
  balls[0].x = x; balls[0].y = y; place = [x, y];
}

/* ---------- نوار قدرت: اسپرایت پاورمتر پلاتو (عمودی) — پایین بکش و رها کن ---------- */
const pw = $('power'), pcv = $('powerCv'), pctx = pcv.getContext('2d');
function drawPower() {
  pw.setAttribute('aria-valuenow', String(Math.round(power * 100)));
  const Wc = pcv.width, Hc = pcv.height; pctx.clearRect(0, 0, Wc, Hc);
  if (ART.ui) {
    // power_meter پلاتو چرخیده ۹۰°− (قرمز اسپرایت ← پایین) و کمی جاسازی شده
    const r = AT.power_meter;
    pctx.save(); pctx.translate(0, Hc); pctx.rotate(-Math.PI / 2);
    pctx.drawImage(ART.ui, r[0] + 12, r[1] + 12, r[2] - 24, r[3] - 24, 0, 0, Hc, Wc);
    pctx.restore();
    // کم نور کردن کل، به جز بخش کشیده شده (از بالا تا قدرت)
    const lit = power * Hc;
    pctx.fillStyle = 'rgba(10,8,6,.62)'; pctx.fillRect(0, lit, Wc, Hc - lit);
    if (lit > 0) { pctx.fillStyle = 'rgba(10,8,6,.15)'; pctx.fillRect(0, 0, Wc, lit); }
    // چوب عمودی: نوک بالا، با قدرت به پایین می لغزد
    const len = Hc * 1.15, th = Wc * .42, tipY = Hc * .03 + power * Hc * .78;
    pctx.save(); pctx.translate(Wc / 2, tipY); pctx.rotate(-Math.PI / 2);
    pctx.shadowColor = 'rgba(0,0,0,.5)'; pctx.shadowBlur = Wc * .12;
    pctx.drawImage(ART.ui, AT.cs_basic[0], AT.cs_basic[1], 1020, 30, -len, -th / 2, len, th);
    pctx.restore();
    return;
  }
  const gg = pctx.createLinearGradient(0, 0, 0, Hc);
  gg.addColorStop(0, '#a8d81f'); gg.addColorStop(.35, '#e8d21d'); gg.addColorStop(.65, '#ff9c1a'); gg.addColorStop(1, '#ff3d1f');
  pctx.fillStyle = gg; pctx.fillRect(0, 0, Wc, Hc);
  const lit = power * Hc;
  pctx.fillStyle = 'rgba(10,8,6,.62)'; pctx.fillRect(0, lit, Wc, Hc - lit);
  if (lit > 0) { pctx.fillStyle = 'rgba(10,8,6,.12)'; pctx.fillRect(0, 0, Wc, lit); }
  const y = Hc * .03 + power * Hc * .78, len = Hc * 1.15, th = Wc * .42;
  pctx.save(); pctx.translate(Wc / 2, y); pctx.rotate(-Math.PI / 2);
  pctx.shadowColor = 'rgba(0,0,0,.5)'; pctx.shadowBlur = 8;
  cuePath(pctx, len, th); pctx.fillStyle = cueFill(pctx, len); pctx.fill();
  pctx.shadowColor = 'transparent';
  const hg = pctx.createLinearGradient(0, -th * .55, 0, th * .55); hg.addColorStop(0, 'rgba(0,0,0,.35)'); hg.addColorStop(.3, 'rgba(255,255,255,.35)'); hg.addColorStop(1, 'rgba(0,0,0,.45)');
  cuePath(pctx, len, th); pctx.fillStyle = hg; pctx.fill(); pctx.restore();
}
let pDrag = null;
pw.addEventListener('pointerdown', ev => { GC.loadSamples(); closeMenu(); if (!canAct()) return; pDrag = ev.clientY; lastInput = performance.now(); try { pw.setPointerCapture(ev.pointerId); } catch (e) {} ev.preventDefault(); });
pw.addEventListener('pointermove', ev => { if (pDrag == null) return; const r = pw.getBoundingClientRect(); power = Math.max(0, Math.min(1, (ev.clientY - pDrag) / (r.height * .8))); lastInput = performance.now(); drawPower(); });
const pUp = () => { if (pDrag == null) return; pDrag = null; if (power >= .03) shoot(); else { power = 0; drawPower(); } };
pw.addEventListener('pointerup', pUp); pw.addEventListener('pointercancel', () => { pDrag = null; power = 0; drawPower(); });

/* ---------- پیچ (انگلیش): توپ کنار میز ← پنل با توپ بزرگ، PRESET و CLOSE ---------- */
function padArt(c, sp, big, pressed) {
  const x = c.getContext('2d'), w = c.width, h = c.height;
  x.clearRect(0, 0, w, h);
  if (ART.ui) {
    x.drawImage(ART.ui, AT.btn_english[0], AT.btn_english[1], AT.btn_english[2], AT.btn_english[3], 0, 0, w, h);
  } else {
    const r = w / 2 - 1;
    const g = x.createRadialGradient(w * .38, h * .3, w * .04, w / 2, h / 2, r);
    g.addColorStop(0, '#ffffff'); g.addColorStop(.55, '#ece8de'); g.addColorStop(.9, '#bdb6a6'); g.addColorStop(1, '#8f897c');
    x.fillStyle = g; x.beginPath(); x.arc(w / 2, h / 2, r, 0, Math.PI * 2); x.fill();
  }
  if (big) { x.strokeStyle = 'rgba(0,0,0,.18)'; x.lineWidth = w * .006; x.beginPath(); x.moveTo(w / 2, h * .12); x.lineTo(w / 2, h * .88); x.moveTo(w * .12, h / 2); x.lineTo(w * .88, h / 2); x.stroke(); }
  const cx = w / 2 + sp[0] * w * .36, cy = h / 2 - sp[1] * h * .36, rs = w * (big ? .15 : .22);
  if (ART.ui) {
    x.drawImage(ART.ui, AT.red_circle[0], AT.red_circle[1], AT.red_circle[2], AT.red_circle[3], cx - rs / 2, cy - rs / 2, rs, rs);
  } else {
    x.strokeStyle = '#d60000'; x.lineWidth = rs * .5; x.beginPath(); x.arc(cx, cy, rs * .45, 0, Math.PI * 2); x.stroke();
  }
  if (pressed && ART.ui) {                       // preset_highlight هنگام فشردن دکمه پیش فرض
    const e = w * .04;
    x.drawImage(ART.ui, AT.preset_highlight[0], AT.preset_highlight[1], AT.preset_highlight[2], AT.preset_highlight[3], -e, -e, w + 2 * e, h + 2 * e);
  }
}
const presets = [...document.querySelectorAll('#spinPop .preset')];
function drawSpin() {
  padArt($('english'), spin, false); padArt($('spinBig'), spin, true);
  presets.forEach(c => padArt(c, [+c.dataset.sx, +c.dataset.sy], false, c._pressed));
}
const pop = $('spinPop');
const openSpin = () => { if (!myTurnNow()) return; closeMenu(); pop.classList.add('open'); drawSpin(); };
$('english').addEventListener('pointerup', openSpin);
$('english').addEventListener('click', openSpin);
$('spinClose').onclick = () => { pop.classList.remove('open'); snd.tap(); };
(() => {
  const big = $('spinBig'); let drag = false;
  const set = ev => { const r = big.getBoundingClientRect(); let x = ((ev.clientX - r.left) / r.width - .5) / .36, y = -((ev.clientY - r.top) / r.height - .5) / .36; const l = Math.hypot(x, y); if (l > 1) { x /= l; y /= l; } spin = [x, y]; drawSpin(); };
  big.addEventListener('pointerdown', ev => { drag = true; try { big.setPointerCapture(ev.pointerId); } catch (e) {} set(ev); ev.preventDefault(); });
  big.addEventListener('pointermove', ev => { if (drag) set(ev); });
  big.addEventListener('pointerup', () => { drag = false; });
  big.addEventListener('dblclick', () => { spin = [0, 0]; drawSpin(); });
  presets.forEach(c => {
    c.addEventListener('pointerdown', ev => { c._pressed = true; drawSpin(); try { c.setPointerCapture(ev.pointerId); } catch (e) {} ev.preventDefault(); });
    c.addEventListener('pointerup', ev => {
      const r = c.getBoundingClientRect(), inside = ev.clientX >= r.left && ev.clientX <= r.right && ev.clientY >= r.top && ev.clientY <= r.bottom;
      const was = c._pressed; c._pressed = false;
      if (was && inside) { spin = [+c.dataset.sx, +c.dataset.sy]; snd.tap(); pop.classList.remove('open'); }
      drawSpin();
    });
    c.addEventListener('pointercancel', () => { c._pressed = false; drawSpin(); });
  });
})();

/* ---------- FINE AIM: نگه داشتن = ۱ درجه در ثانیه، ضربهٔ کوتاه = ۰٫۰۵ درجه ---------- */
function bindFine(id, sign) {
  const b = $(id); let hold = false, t0 = 0, last = 0;
  const tick = now => { if (!hold) return; if (now - t0 > 180) angle += sign * Math.PI / 180 * Math.min(.05, (now - last) / 1000); last = now; lastInput = now; requestAnimationFrame(tick); };
  b.addEventListener('pointerdown', ev => { if (!canAct()) return; hold = true; t0 = last = performance.now(); b.classList.add('pressed'); try { b.setPointerCapture(ev.pointerId); } catch (e) {} ev.preventDefault(); requestAnimationFrame(tick); });
  const stop = () => { if (!hold) return; hold = false; b.classList.remove('pressed'); if (performance.now() - t0 <= 180) angle += sign * Math.PI / 180 * .05; };
  b.addEventListener('pointerup', stop); b.addEventListener('pointercancel', stop); b.addEventListener('lostpointercapture', stop);
  b.addEventListener('contextmenu', e => e.preventDefault());
}
bindFine('fineUp', 1); bindFine('fineDown', -1);
const syncEye = () => $('eye').setAttribute('aria-pressed', String(!!showLines));
$('eye').onclick = () => { showLines = !showLines; store.set('blEye', showLines); syncEye(); };

/* ---------- ضربه ---------- */
async function shoot() {
  const g = G(); if (!canAct() || !g) { power = 0; drawPower(); return; }
  const p = power, c = balls[0], pl = g.bih && place ? place.slice() : null;
  if (pl && !E.validPlace(cur().map((q, i) => i ? q : null), g.breaking, pl[0], pl[1])) { toast(errText({ code: 'bad_place' })); power = 0; drawPower(); return; }
  strike = { x: c.x, y: c.y, a: angle, p, t0: performance.now(), dur: 160, hold: true };
  snd.cue(p, c.x); haptic('medium');
  power = 0; drawPower();
  await act(() => GC.billiard.shot(mid, angle, p, spin[0], spin[1], pl ? pl[0] : null, pl ? pl[1] : null, since));
  if (strike) strike.hold = false;
  place = null;
}

/* ---------- پخش رویدادها ---------- */
async function play(e) {
  if (e.t === 'start') { setBalls(e.balls); return; }
  if (e.t === 'shot') {
    if (!(isMe(e.c) && !e.auto)) {
      strike = { x: e.cue[0], y: e.cue[1], a: e.a, p: Math.min(1, e.p), t0: performance.now(), dur: 700, hold: false };
      balls[0].x = e.cue[0]; balls[0].y = e.cue[1]; balls[0].on = true;
      await sleep(560); snd.cue(Math.min(1, e.p), e.cue[0]);
    } else if (strike) strike.hold = false;
    await playShot(e);
    if (e.auto && isMe(e.c)) toast('وقتت تمام شد؛ ربات جای تو زد');
    return;
  }
  if (e.t === 'groups') { const g = G(), mg = e.solids === myTeam() ? 'solids' : 'stripes'; flashMsg(WATCH ? 'گروه‌ها مشخص شد' : `گروه ${g && g.n === 4 ? 'تیم ' : ''}تو: ${GROUP_FA[mg]}`); snd.turn(); return; }
  if (e.t === 'turn') {
    setBalls(e.balls);
    if (e.foul && e.foul !== 'timeout') { flashMsg(`${MSG[e.foul] || 'خطا'} · ${isMe(e.c) ? 'توپ در دست داری' : nameOf(e.c) + ' توپ در دست دارد'}`, true); sfx.error(); }
    else if (e.msg === 'potted' || e.msg === 'on_8') { flashMsg(MSG[e.msg]); sfx.coin(); }
    else if (e.msg === 'wrong_pot') flashMsg(MSG.wrong_pot, true);
    if (isMe(e.c)) { snd.turn(); haptic('light'); hintAt = performance.now(); place = null; }
    return;
  }
  if (e.t === 'rack') { flashMsg(MSG[e.why] || 'دوباره چیده شد', true); await sleep(500); snd.rack(); setBalls(e.balls); for (const b of balls) b.q = startQuat(); return; }
  if (e.t === 'spot') { const b = balls[e.k]; b.on = true; b.x = e.at[0]; b.y = e.at[1]; return; }
  if (e.t === 'timeout') { if (WATCH) return; flashMsg(isMe(e.c) ? (snap.cfg.mode === 'stake' && e.n >= 2 ? (e.n >= 3 ? 'سه نوبت غایب بودی' : 'یک نوبت دیگر غیبت = خروج') : 'وقتت تمام شد؛ حریف توپ در دست گرفت') : `${nameOf(e.c)} ضربه نزد؛ توپ در دست`, true); return; }
  if (e.t === 'leave' && !isMe(e.c)) { toast(`${nameOf(e.c)} ${e.why === 'timeout' ? 'غایب بود' : 'بازی را ترک کرد'}${G() && G().n === 4 ? '؛ ربات جایش بازی می‌کند' : ''}`); return; }
  if (e.t === 'win' || e.t === 'end') { if (e.balls) setBalls(e.balls); return; }
}

/* ---------- گفتگو: نوار «Say hello...» و پیام های شناور روی میز مثل پلاتو (tchat.js) ---------- */
const QUICK = ['سلام!', 'خوش‌بازی!', 'عجب ضربه‌ای!', 'شانس آوردی', 'زود باش', 'یک دست دیگه؟'];
const chat = TChat.init({
  bar: $('chatbar'), quick: QUICK, face: m => face(m, 'transparent'),
  canSend: () => mid && !WATCH,
  send: async text => { await GC.billiard.chat(mid, text); return (await GC.billiard.match(mid, since, chat.last())).chat; },
  onNew: () => snd.tap(), onError: e => { sfx.error(); toast(errText(e)); },
});
const chatIn = (list, quiet) => chat.add(list, quiet);
function quickSheet() {
  const sh = sheet(`${sheetHead('پیام سریع')}<div class="quick" style="justify-content:center">${QUICK.map(q => `<button class="chip" data-q>${q}</button>`).join('')}</div>`);
  sh.querySelectorAll('[data-q]').forEach(b => { b.onclick = () => { GC.close(); chat.send(b.textContent); }; });
}
$('items').onclick = quickSheet;

/* ---------- منوی ⋮ ---------- */
const menu = $('menuPop');
function closeMenu() { menu.classList.remove('open'); }
const syncSnd = () => { $('mSound').textContent = S.sound ? '🔊 صدا روشن' : '🔇 صدا خاموش'; };
$('menuBtn').onclick = e => { e.stopPropagation(); menu.classList.toggle('open'); };
$('mSound').onclick = () => { setSound(!S.sound); syncSnd(); if (S.sound) GC.loadSamples(); closeMenu(); };
$('mExit').onclick = () => { closeMenu(); askExit(); };
document.addEventListener('pointerdown', e => { if (menu.classList.contains('open') && !e.target.closest('#menuPop,#menuBtn')) closeMenu(); });

/* ---------- همگام سازی با سرور ---------- */
async function apply(next, animate = true) {
  if (next && next.chat && !overShown && next.status !== 'over' && next.status !== 'cancelled') chatIn(next.chat);
  if (next && next.status === 'cancelled') return cancelled();
  if (!next || !next.game) return;
  busy = true;
  try {
    snap = Object.assign({}, snap || {}, next);
    const g = next.game, evs = (g.events || []).filter(e => e.seq > since).sort((a, b) => a.seq - b.seq);
    for (const e of evs) { if (animate) await play(e); since = e.seq; }
    since = Math.max(since, g.seq);
    if (!anim) {
      const keep = placing || (myTurnNow() && g.bih && place), c0 = [balls[0].x, balls[0].y];
      setBalls(g.balls); if (keep) { balls[0].x = c0[0]; balls[0].y = c0[1]; balls[0].on = true; }
    }
    renderAll(g);
    if (next.status === 'over' && !overShown) { overShown = true; over(next); }
  } finally { busy = false; }
}
function pollMs() { const g = G(); if (!g || g.over) return POLL_MS; return g.turn && g.turn !== me ? 700 : 1500; }
async function poll() {
  clearTimeout(pollT);
  if (document.hidden || overShown) { pollT = setTimeout(poll, pollMs()); return; }
  if (!busy && !acting && !anim) {
    try { await apply(await GC.billiard.match(mid, since, chat.last())); }
    catch (e) { if (e.code === 'not_found') return noMatch(); }
  }
  pollT = setTimeout(poll, pollMs());
}
async function act(fn) {
  if (acting) return;
  acting = true;
  try { const res = await fn(); acting = false; await apply(res); }
  catch (e) { strike = null; sfx.error(); haptic('error'); toast(errText(e)); if (snap && snap.game) renderAll(snap.game); }
  finally { acting = false; }
}
document.addEventListener('visibilitychange', () => { if (!document.hidden) poll(); });

/* ---------- پایان، خروج ---------- */
const TROPHY = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 21h8M12 17v4M7 4h10v5a5 5 0 0 1-10 0z"/><path d="M17 5h3v2a3 3 0 0 1-3 3M7 5H4v2a3 3 0 0 0 3 3"/></svg>';
const WHY = { pot8: 'توپ ۸ با ضربهٔ قانونی افتاد', foul8: 'توپ ۸ همراه با خطا افتاد', early8: 'توپ ۸ زودتر از وقتش افتاد', left: 'یک طرف بازی را ترک کرد' };
function over(v) {
  chat.end();
  const g = v.game, lastWin = (g.events || []).filter(e => e.t === 'win' || e.t === 'end').pop() || {};
  if (WATCH) {
    sfx.win();
    const names = g.winner == null ? '' : g.order.filter((c, k) => k % 2 === g.winner).map(c => g.players[c].name).join(' و ');
    return GC.watchOver('billiard', 'بازی تمام شد', g.winner == null ? 'بازی بدون برنده بسته شد.' : `${names} برد${g.n === 4 ? 'ند' : ''}.`);
  }
  const r = v.result || {}, won = !!r.won, team = g.n === 4;
  GC.guardClose(false); store.set('bmid', null);
  won ? (sfx.win(), haptic('success')) : (sfx.lose(), haptic('warning'));
  const secs = Math.max(0, Math.round(Date.now() / 1000 - g.started)), st = g.stats || { shots: 0, pots: 0, fouls: 0 };
  const stake = v.cfg.mode === 'stake', ended = g.winner == null;
  sheet(`<div class="bl-res">
      <span class="ic${won ? '' : ' lost'}">${TROPHY}</span>
      <h2>${ended ? 'بازی تمام شد' : won ? (team ? 'تیم شما برد!' : 'بردی!') : (team ? 'تیم حریف برد' : 'این بازی را باختی')}</h2>
      ${WHY[lastWin.why] ? `<p>${WHY[lastWin.why]}</p>` : ''}
      ${stake ? (won ? `<div class="prize">${amount(r.prize || 0, 'lg')}</div><p>جایزه به کیف امتیازت اضافه شد.</p>` : ended ? '<p>ورودی‌ها برگشت.</p>' : `<p>ورودی این بازی (${fa(r.lost || v.cfg.entry)} امتیاز) را باختی.</p>`)
        : `<p>${won ? 'بازی آزاد بود و جایزه نداشت.' : 'بازی آزاد بود؛ چیزی از دست ندادی.'}</p>`}
      <div class="facts"><div><b>${FD(st.pots)}</b><span>توپ انداختی</span></div><div><b>${FD(st.shots)}</b><span>ضربه</span></div><div><b>${FD(st.fouls)}</b><span>خطا</span></div><div><b>${FD(Math.floor(secs / 60))}:${FD(String(secs % 60).padStart(2, '0'))}</b><span>مدت</span></div></div>
    </div>
    <a class="btn btn-block" href="billiard-lobby.html">یک بازی دیگر</a>
    <a class="btn btn-light btn-block" href="index.html">خانه</a>`, { center: true, dismiss: false });
  GC.refreshMe().catch(() => {});
}
function cancelled() {
  if (overShown) return;
  overShown = true; chat.end();
  if (WATCH) { GC.watchOver('billiard', 'این بازی بسته شد', 'بازی پیش از تمام شدن بسته شد.'); return; }
  GC.guardClose(false); store.set('bmid', null); GC.refreshMe().catch(() => {});
  sheet(`<div class="dlg" role="alertdialog" aria-labelledby="dT" aria-describedby="dD"><span class="dlg-ic">${icon('table')}</span>
      <h2 id="dT">این بازی بسته شد</h2><p id="dD">پشتیبانی این بازی را بست و ورودی همه به کیف امتیازشان برگشت.</p>
      <div class="dlg-acts"><a class="btn" href="billiard-lobby.html">بازی تازه</a><a class="btn btn-light" href="index.html">خانه</a></div></div>`, { center: true, dismiss: false });
}
function noMatch() {
  if (watchMid) { GC.watchOver('billiard', 'این بازی را نمی‌شود دید', 'بازی تمام شده یا هنوز شروع نشده است.'); return; }
  store.set('bmid', null);
  sheet(`<div class="dlg" role="alertdialog" aria-labelledby="dT" aria-describedby="dD"><span class="dlg-ic">${icon('table')}</span>
      <h2 id="dT">بازی‌ای پیدا نشد</h2><p id="dD">این بازی تمام شده یا هنوز وارد بازی‌ای نشده‌ای.</p>
      <div class="dlg-acts"><a class="btn" href="billiard-lobby.html">شروع بازی</a><a class="btn btn-light" href="index.html">خانه</a></div></div>`, { center: true, dismiss: false });
}
function askExit() {
  if (!snap || snap.status === 'over' || WATCH) { location.href = 'index.html'; return; }
  const stake = snap.cfg.mode === 'stake', team = G() && G().n === 4;
  const sh = sheet(`<div class="dlg" role="alertdialog" aria-labelledby="dT" aria-describedby="dD">
      <span class="dlg-ic warn">${icon('exit')}</span>
      <h2 id="dT">از بازی بیرون می‌روی؟</h2>
      <p id="dD">${team ? 'از این به بعد ربات جای تو کنار یارت بازی می‌کند و اگر تیمت ببرد سهمی نمی‌گیری.' : 'خروج یعنی باخت همین بازی و حریف برنده می‌شود.'}</p>
      <div class="dlg-note">${stake ? `ورودی ${amount(snap.cfg.entry)} برنمی‌گردد` : 'بازی آزاد است؛ امتیازی از دست نمی‌دهی'}</div>
      <div class="dlg-acts"><button class="btn" data-close>ادامهٔ بازی</button><button class="btn btn-danger-soft" id="leave">${icon('exit')}خروج</button></div>
      <button class="btn btn-light btn-block dlg-home" id="home">${icon('home')}فقط برو خانه؛ بازی می‌ماند</button>
      <p class="dlg-fine">تا نیستی نوبتت می‌سوزد و حریف توپ در دست می‌گیرد${stake ? '؛ در بازی امتیازی سه نوبت غیبت پشت‌سرهم یعنی خروج' : ''}.</p>
    </div>`, { center: true });
  sh.querySelector('#home').onclick = () => { GC.guardClose(false); location.href = 'index.html'; };
  sh.querySelector('#leave').onclick = async () => {
    try { await GC.billiard.leave(mid); } catch (e) {}
    GC.guardClose(false); store.set('bmid', null); location.href = 'index.html';
  };
}
$('exit').onclick = askExit;
GC.back(askExit);
syncSnd(); syncEye(); drawPower(); drawSpin();
window.addEventListener('resize', fit);
try { new ResizeObserver(fit).observe($('wrap')); } catch (e) {}
try { Telegram.WebApp.onEvent('viewportChanged', fit); Telegram.WebApp.onEvent('fullscreenChanged', () => setTimeout(fit, 50)); Telegram.WebApp.onEvent('safeAreaChanged', fit); Telegram.WebApp.onEvent('contentSafeAreaChanged', fit); } catch (e) {}
document.addEventListener('pointerdown', () => GC.loadSamples(), { once: true });

/* ---------- شروع ---------- */
async function start() {
  GC.portrait(true);
  fit(); requestAnimationFrame(frame);
  let first;
  try { first = await GC.billiard.match(mid, 0, 0); }
  catch (e) { return e.code === 'not_found' ? noMatch() : (toast(errText(e)), setTimeout(start, 2500)); }
  WATCH = !!first.watch;
  if (first.status === 'lobby') { if (watchMid) return noMatch(); location.href = 'billiard-lobby.html'; return; }
  if (first.status === 'cancelled') return cancelled();
  mid = first.id; me = first.me;
  if (WATCH) { $('chatbar').hidden = true; } else store.set('bmid', mid);
  if (first.cfg.mode === 'stake' && first.status === 'playing') GC.guardClose(true);
  chatIn(first.chat, true);
  snap = first; since = first.game.seq;
  hintAt = performance.now();
  await apply(first, false);
  const g = first.game;
  if (g.breaking && g.balls[0]) { const ap = g.balls.slice(1).filter(Boolean).sort((a, b) => a[1] - b[1])[0]; if (ap) angle = Math.atan2(ap[1] - g.balls[0][1], ap[0] - g.balls[0][0]); }
  poll();
}
start();
})();
