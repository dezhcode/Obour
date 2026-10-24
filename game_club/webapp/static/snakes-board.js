/* صفحهٔ مار و پله با طرح «شب جنگل»: خانه های فیروزه ای براق، قاب طلایی، نردبان های طلایی و مارهای راه راه.
   صفحهٔ ثابت یک بار روی canvas کشیده می شود (هر بار که اندازه عوض شود)؛ مهره ها روی آن DOM اند و فقط transform می گیرند.
   مختصات به واحد خانه: (۰,۰) گوشهٔ بالا چپ، هر خانه یک واحد؛ خانهٔ ۱ پایین چپ و ردیف ها مارپیچ بالا می روند.
   مسیر مار همین جا ساخته می شود تا مهره هنگام سرخوردن دقیقاً روی بدن همان مار بیاید. */
(() => {
const SN = { 17: 7, 54: 34, 62: 19, 64: 60, 87: 24, 93: 73, 95: 75, 99: 78 };
const LD = { 4: 14, 9: 31, 20: 38, 28: 84, 40: 59, 51: 67, 63: 81, 71: 91 };
const FD = n => String(n).replace(/\d/g, d => '۰۱۲۳۴۵۶۷۸۹'[d]);
const SKIN = [['#2bb673', '#16804c', '#7dffb3'], ['#e0475b', '#a3253a', '#ff9aa8'], ['#9b5de5', '#6a35b0', '#d7b8ff'], ['#f28c28', '#b35a0c', '#ffd08a']];

// مرکز خانهٔ n به واحد خانه
function cell(n) {
  n = Math.max(1, Math.min(100, n));
  const r = Math.floor((n - 1) / 10); let c = (n - 1) % 10; if (r % 2) c = 9 - c;
  return [c + .5, 9 - r + .5];
}
// بدن مار از سر (خانهٔ بالاتر) تا دم؛ [x, y, شعاع] به واحد خانه
const paths = {};
function snakePath(a, b) {
  const k = a + ':' + b; if (paths[k]) return paths[k];
  const [x1, y1] = cell(a), [x2, y2] = cell(b), dx = x2 - x1, dy = y2 - y1, L = Math.hypot(dx, dy), nx = -dy / L, ny = dx / L;
  const waves = Math.max(2, Math.round(L / 1.6)), ph = a % 7, N = Math.max(40, Math.round(L * 14)), out = [];
  for (let i = 0; i <= N; i++) {
    const t = i / N, o = Math.sin(t * Math.PI * waves + ph) * Math.pow(Math.sin(Math.PI * t), .6) * .42;
    out.push([x1 + dx * t + nx * o, y1 + dy * t + ny * o, .065 + .09 * Math.pow(1 - t, .8)]);
  }
  return (paths[k] = out);
}

function draw(cv, px, snakes = SN, ladders = LD) {
  const dpr = Math.min(window.devicePixelRatio || 1, 2), s = px / 10;
  cv.width = cv.height = Math.round(px * dpr); cv.style.width = cv.style.height = px + 'px';
  const g = cv.getContext('2d'); g.setTransform(dpr, 0, 0, dpr, 0, 0);
  g.fillStyle = '#071c22'; g.fillRect(0, 0, px, px);
  const font = (w, sz) => `${w} ${sz}px Peyda, Rokh, Tahoma, sans-serif`;
  for (let n = 1; n <= 100; n++) {
    const [cx, cy] = cell(n), x0 = (cx - .5) * s, y0 = (cy - .5) * s, d = (Math.floor((n - 1) / 10) + Math.floor(cx)) % 2;
    const gr = g.createLinearGradient(x0, y0, x0, y0 + s);
    if (n === 100) { gr.addColorStop(0, '#ffe9a3'); gr.addColorStop(1, '#d89a1e'); }
    else if (d) { gr.addColorStop(0, '#228a7e'); gr.addColorStop(1, '#14595a'); }
    else { gr.addColorStop(0, '#174e63'); gr.addColorStop(1, '#0e3447'); }
    const p = s * .045, rr = s * .14;
    g.fillStyle = gr; round(g, x0 + p, y0 + p, s - 2 * p, s - 2 * p, rr); g.fill();
    g.strokeStyle = 'rgba(255,255,255,.14)'; g.lineWidth = 1; round(g, x0 + p + .5, y0 + p + .5, s - 2 * p - 1, s - 2 * p - 1, rr); g.stroke();
    // برق بالای کاشی
    const hl = g.createLinearGradient(x0, y0, x0, y0 + s * .5);
    hl.addColorStop(0, 'rgba(255,255,255,.12)'); hl.addColorStop(1, 'rgba(255,255,255,0)');
    g.fillStyle = hl; round(g, x0 + p, y0 + p, s - 2 * p, s * .45, rr); g.fill();
    g.font = font(800, s * .22); g.textBaseline = 'top'; g.textAlign = 'left';
    g.fillStyle = n === 100 ? '#5a3b05' : 'rgba(255,255,255,.62)'; g.fillText(FD(n), x0 + s * .1, y0 + s * .08);
    if (n === 1) { g.font = font(800, s * .2); g.textAlign = 'center'; g.fillStyle = 'rgba(255,255,255,.75)'; g.fillText('شروع', cx * s, y0 + s * .56); }
    if (n === 100) crown(g, cx * s, cy * s + s * .08, s * .5);
  }
  for (const [a, b] of Object.entries(ladders)) ladder(g, +a, +b, s);
  Object.entries(snakes).forEach(([a, b], i) => snake(g, +a, +b, s, SKIN[i % SKIN.length]));
  // سایهٔ داخلی لبهٔ صفحه
  const v = g.createRadialGradient(px / 2, px / 2, px * .45, px / 2, px / 2, px * .75);
  v.addColorStop(0, 'rgba(0,0,0,0)'); v.addColorStop(1, 'rgba(0,0,0,.35)');
  g.fillStyle = v; g.fillRect(0, 0, px, px);
}
function round(g, x, y, w, h, r) { g.beginPath(); g.moveTo(x + r, y); g.arcTo(x + w, y, x + w, y + h, r); g.arcTo(x + w, y + h, x, y + h, r); g.arcTo(x, y + h, x, y, r); g.arcTo(x, y, x + w, y, r); g.closePath(); }
function crown(g, x, y, w) {
  const h = w * .7;
  g.save(); g.translate(x - w / 2, y - h / 2);
  g.beginPath(); g.moveTo(0, h * .35); g.lineTo(w * .25, h * .62); g.lineTo(w * .5, h * .05); g.lineTo(w * .75, h * .62); g.lineTo(w, h * .35); g.lineTo(w * .86, h); g.lineTo(w * .14, h); g.closePath();
  g.fillStyle = '#fff3c4'; g.strokeStyle = 'rgba(90,59,5,.7)'; g.lineWidth = Math.max(1, w * .05); g.lineJoin = 'round'; g.fill(); g.stroke();
  g.restore();
}
function ladder(g, a, b, s) {
  const [x1, y1] = cell(a).map(v => v * s), [x2, y2] = cell(b).map(v => v * s), dx = x2 - x1, dy = y2 - y1, L = Math.hypot(dx, dy);
  const ux = dx / L, uy = dy / L, ox = -uy * s * .15, oy = ux * s * .15;
  g.save(); g.lineCap = 'round';
  const rails = (w, c) => { g.strokeStyle = c; g.lineWidth = w; [-1, 1].forEach(k => { g.beginPath(); g.moveTo(x1 + k * ox + ux * s * .12, y1 + k * oy + uy * s * .12); g.lineTo(x2 + k * ox - ux * s * .12, y2 + k * oy - uy * s * .12); g.stroke(); }); };
  g.shadowColor = 'rgba(0,0,0,.65)'; g.shadowBlur = s * .2; g.shadowOffsetY = s * .08;
  rails(s * .075, '#8a5412');
  g.shadowColor = 'rgba(0,0,0,.5)'; g.shadowBlur = s * .1; g.shadowOffsetY = s * .04;
  g.strokeStyle = '#c98a2b'; g.lineWidth = s * .05;
  for (let t = s * .3; t < L - s * .2; t += s * .3) { g.beginPath(); g.moveTo(x1 + ux * t - ox, y1 + uy * t - oy); g.lineTo(x1 + ux * t + ox, y1 + uy * t + oy); g.stroke(); }
  g.shadowColor = 'transparent';
  rails(s * .042, '#e9b44c'); rails(s * .013, '#fff1b8');
  g.restore();
}
function snake(g, a, b, s, [c1, c2, hi]) {
  const pts = snakePath(a, b), N = pts.length - 1;
  g.save();
  g.fillStyle = 'rgba(0,0,0,.4)';
  for (let i = N; i >= 0; i--) { const [x, y, r] = pts[i]; g.beginPath(); g.arc(x * s + s * .04, y * s + s * .09, r * s, 0, 7); g.fill(); }
  for (let i = N; i >= 0; i--) {
    const [x, y, r] = pts[i], st = Math.floor(i / 5) % 2;
    g.fillStyle = st ? c2 : c1; g.beginPath(); g.arc(x * s, y * s, r * s, 0, 7); g.fill();
    if (i % 2 === 0) { g.fillStyle = hi + '66'; g.beginPath(); g.arc(x * s - r * s * .25, y * s - r * s * .3, r * s * .42, 0, 7); g.fill(); }
  }
  // سر، چشم ها و زبان
  const [hx, hy, hr] = pts[0], [px2, py2] = pts[4], ang = Math.atan2(hy - py2, hx - px2), ex = Math.cos(ang), ey = Math.sin(ang), R = hr * s * 1.05;
  const X = hx * s, Y = hy * s;
  g.strokeStyle = '#e11d48'; g.lineWidth = Math.max(1.2, s * .025); g.lineCap = 'round';
  const tx = X + ex * R * 1.35, ty = Y + ey * R * 1.35;
  g.beginPath(); g.moveTo(X + ex * R * .9, Y + ey * R * .9); g.lineTo(tx, ty);
  g.lineTo(tx + ex * s * .06 - ey * s * .045, ty + ey * s * .06 + ex * s * .045); g.moveTo(tx, ty); g.lineTo(tx + ex * s * .06 + ey * s * .045, ty + ey * s * .06 - ex * s * .045); g.stroke();
  const hg = g.createRadialGradient(X - ex * R * .2, Y - ey * R * .2, R * .2, X, Y, R * 1.2);
  hg.addColorStop(0, c1); hg.addColorStop(1, c2);
  g.fillStyle = hg; g.beginPath(); g.ellipse(X, Y, R * 1.2, R, ang, 0, 7); g.fill();
  [-1, 1].forEach(k => {
    const ex2 = X + ex * R * .25 - ey * k * R * .55, ey2 = Y + ey * R * .25 + ex * k * R * .55;
    g.fillStyle = '#fff'; g.beginPath(); g.arc(ex2, ey2, R * .36, 0, 7); g.fill();
    g.fillStyle = '#111'; g.beginPath(); g.arc(ex2 + ex * R * .1, ey2 + ey * R * .1, R * .19, 0, 7); g.fill();
  });
  g.restore();
}
window.SNBoard = { SN, LD, cell, snakePath, draw, FD };
})();
