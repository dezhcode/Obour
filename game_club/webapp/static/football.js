/* فوتبال — نمایش. فیزیک، نوبت، گل و برنده روی سرور است (game_club/football.py)؛
   اینجا رویدادهای سرور به ترتیب پخش می شوند (انتخاب تیم، «مقابل»، مسیر هر شوت با
   فریم های سرور، جشن گل، برگشت مهره ها) و شوت کاربر (جهت و قدرت) فرستاده می شود.
   بیرون از تلگرام همان API را demo-football.js در مرورگر شبیه سازی می کند.

   هر بازیکن دروازه خودش را پایین می بیند: برای صندلی ۱ زمین ۱۸۰ درجه می چرخد. */
(() => {
const { S, fa, FD, store, face, icon, sheet, sheetHead, toast, sleep, sfx, haptic, errText, setSound, amount, mount } = GC;
const $ = id => document.getElementById(id);
const POLL_MS = 900;
const W = 600, H = 1040, MID = H / 2, GOAL_W = 220, GOAL_D = 60, GX0 = (W - GOAL_W) / 2, DISC_R = 36, BALL_R = 18, BALL = 12;
const STAR = 'M16 7.5l2.5 5.2 5.7.8-4.1 4 1 5.6-5.1-2.7-5.1 2.7 1-5.6-4.1-4 5.7-.8z';
const TEAM = {
  eagles: { fa: 'عقاب‌ها', sub: 'آبی · ستاره' },
  lions: { fa: 'شیرها', sub: 'قرمز · طلایی' },
  cheetahs: { fa: 'یوزها', sub: 'نارنجی · خال‌دار' },
  mountain: { fa: 'کوهستان', sub: 'سبز · قله' },
  storm: { fa: 'طوفان', sub: 'بنفش · صاعقه' },
  sea: { fa: 'دریا', sub: 'فیروزه‌ای · موج' },
};
const TEAM_IDS = Object.keys(TEAM);
const FORM_IDS = ['132', '123', '141', '1212'];
const FORM_FA = { 132: '۱-۳-۲', 123: '۱-۲-۳', 141: '۱-۴-۱', 1212: '۱-۲-۱-۲' };
const MINI = { a: { 132: [[20, 64], [50, 68], [80, 64], [34, 38], [66, 38]], 123: [[32, 66], [68, 66], [18, 40], [50, 36], [82, 40]], 141: [[14, 60], [38, 64], [62, 64], [86, 60], [50, 36]], 1212: [[32, 72], [68, 72], [50, 56], [32, 36], [68, 36]] },
  d: { 132: [[22, 72], [50, 78], [78, 72], [34, 54], [66, 54]], 123: [[34, 78], [66, 78], [18, 56], [50, 54], [82, 56]], 141: [[14, 74], [38, 78], [62, 78], [86, 74], [50, 54]], 1212: [[34, 80], [66, 80], [50, 66], [32, 50], [68, 50]] } };
let uid = 0;
function emblem(team, kit) {
  const id = 'e' + (++uid), away = kit === 'away';
  const c = (a, b) => away ? b : a;
  switch (team) {
    case 'eagles': return away ? `<svg viewBox="0 0 32 32"><circle cx="16" cy="16" r="16" fill="#fff"/><path d="${STAR}" fill="#1E5BD8"/></svg>`
      : `<svg viewBox="0 0 32 32"><defs><pattern id="${id}" width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(35)"><rect width="4" height="8" fill="#1E5BD8"/><rect x="4" width="4" height="8" fill="#5AA2FF"/></pattern></defs><circle cx="16" cy="16" r="16" fill="url(#${id})"/><path d="${STAR}" fill="#fff"/></svg>`;
    case 'lions': return `<svg viewBox="0 0 32 32"><circle cx="16" cy="16" r="16" fill="${c('#D7263D', '#2B2D42')}"/><rect x="0" y="12" width="32" height="8" fill="${c('#F5C451', '#D7263D')}"/><path d="M9 20l7-6 7 6" fill="none" stroke="${c('#fff', '#F5C451')}" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
    case 'cheetahs': { const bg = c('#F2994A', '#3b2410'), sp = c('#3b2410', '#F2994A');
      return `<svg viewBox="0 0 32 32"><circle cx="16" cy="16" r="16" fill="${bg}"/>${[[9, 10, 2.4], [20, 8, 2], [24, 17, 2.6], [12, 20, 2.2], [18, 25, 2], [7, 17, 1.6]].map(([x, y, r]) => `<circle cx="${x}" cy="${y}" r="${r}" fill="${sp}"/>`).join('')}</svg>`; }
    case 'mountain': return `<svg viewBox="0 0 32 32"><circle cx="16" cy="16" r="16" fill="${c('#1F9D55', '#fff')}"/><path d="M4 24l8-11 5 6 4-4 7 9z" fill="${c('#fff', '#1F9D55')}"/></svg>`;
    case 'storm': return `<svg viewBox="0 0 32 32"><circle cx="16" cy="16" r="16" fill="${c('#6C2BD9', '#F5C451')}"/><path d="M18 5L9 18h7l-2 9 9-13h-7z" fill="${c('#F5C451', '#6C2BD9')}"/></svg>`;
    case 'sea': return `<svg viewBox="0 0 32 32"><circle cx="16" cy="16" r="16" fill="${c('#0FA3B1', '#fff')}"/><path d="M3 14c3-3 6-3 9 0s6 3 9 0 6-3 8 0M3 21c3-3 6-3 9 0s6 3 9 0 6-3 8 0" fill="none" stroke="${c('#fff', '#0FA3B1')}" stroke-width="2.6" stroke-linecap="round"/></svg>`;
    default: return '<svg viewBox="0 0 32 32"><circle cx="16" cy="16" r="16" fill="#8b93a3"/><circle cx="16" cy="16" r="6" fill="#c9ced6"/></svg>';
  }
}
// مهره سه بعدی: لبه فلزی با ضخامت و سایه، نشان تیم فرورفته و براق (ظاهر در football.css)
const discHtml = (team, kit, size, cls = '') => `<span class="fd ${cls}" style="width:${size}px;height:${size}px;--d:${size}px"><span class="in">${emblem(team, kit)}</span></span>`;
// توپ سه بعدی: الگوی واقعی توپ (بیست وجهی بریده: ۱۲ پنج ضلعی سیاه و درزها) با یک ماتریس
// چرخش؛ هر جابه جایی توپ را حول محوری عمود بر جهت حرکت می غلتاند، پس به هر سمتی می چرخد
const BALL3 = (() => {
  const f = (1 + Math.sqrt(5)) / 2, V = [];
  for (const a of [-1, 1]) for (const b of [-f, f]) V.push([0, a, b], [a, b, 0], [b, 0, a]);
  const nrm = v => { const l = Math.hypot(v[0], v[1], v[2]); return [v[0] / l, v[1] / l, v[2] / l]; };
  const near = (a, b) => Math.abs(Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]) - 2) < 1e-6;
  const third = (a, b) => nrm([(2 * a[0] + b[0]) / 3, (2 * a[1] + b[1]) / 3, (2 * a[2] + b[2]) / 3]);
  const pents = V.map(v => {
    const c = nrm(v), nb = V.filter(w => near(v, w)).map(w => third(v, w));
    const u = nrm(Math.abs(c[2]) < .9 ? [-c[1], c[0], 0] : [0, -c[2], c[1]]);
    const w = [c[1] * u[2] - c[2] * u[1], c[2] * u[0] - c[0] * u[2], c[0] * u[1] - c[1] * u[0]];
    nb.sort((p, q) => Math.atan2(p[0] * w[0] + p[1] * w[1] + p[2] * w[2], p[0] * u[0] + p[1] * u[1] + p[2] * u[2]) - Math.atan2(q[0] * w[0] + q[1] * w[1] + q[2] * w[2], q[0] * u[0] + q[1] * u[1] + q[2] * u[2]));
    return { c, pts: nb };
  });
  const seams = [];
  V.forEach((a, i) => V.forEach((b, j) => { if (j > i && near(a, b)) seams.push([third(a, b), third(b, a)]); }));
  return { pents, seams };
})();
let ballM = [[1, 0, 0], [0, 1, 0], [0, 0, 1]], ballAt = null, ballN = 0;
const mul = (M, v) => [M[0][0] * v[0] + M[0][1] * v[1] + M[0][2] * v[2], M[1][0] * v[0] + M[1][1] * v[1] + M[1][2] * v[2], M[2][0] * v[0] + M[2][1] * v[1] + M[2][2] * v[2]];
function rollBall(dx, dy) {
  const d = Math.hypot(dx, dy); if (d < 1e-3) return;
  const ax = -dy / d, ay = dx / d, t = d / BALL_R, c = Math.cos(t), sn = Math.sin(t), k = 1 - c;
  const R = [[c + ax * ax * k, ax * ay * k, ay * sn], [ay * ax * k, c + ay * ay * k, -ax * sn], [-ay * sn, ax * sn, c]];
  ballM = R.map(r => [0, 1, 2].map(j => r[0] * ballM[0][j] + r[1] * ballM[1][j] + r[2] * ballM[2][j]));
  if (++ballN % 120 === 0) {   // جلوی انباشت خطای عددی
    const n = v => { const l = Math.hypot(v[0], v[1], v[2]); return v.map(x => x / l); };
    const a = n(ballM[0]), b0 = ballM[1], dt = a[0] * b0[0] + a[1] * b0[1] + a[2] * b0[2];
    const b = n([b0[0] - dt * a[0], b0[1] - dt * a[1], b0[2] - dt * a[2]]);
    ballM = [a, b, [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]];
  }
}
function drawBall(el) {
  const g = el && el.querySelector('.pat'); if (!g) return;
  if (!g.firstChild) {
    const ns = 'http://www.w3.org/2000/svg';
    BALL3.seams.forEach(() => g.appendChild(document.createElementNS(ns, 'line')));
    BALL3.pents.forEach(() => g.appendChild(document.createElementNS(ns, 'polygon')));
  }
  const R = 18.6, kids = g.childNodes, n = BALL3.seams.length;
  BALL3.seams.forEach(([a, b], i) => {
    const A = mul(ballM, a), B = mul(ballM, b), l = kids[i];
    if (A[2] > .02 && B[2] > .02) { l.setAttribute('x1', (A[0] * R).toFixed(2)); l.setAttribute('y1', (A[1] * R).toFixed(2)); l.setAttribute('x2', (B[0] * R).toFixed(2)); l.setAttribute('y2', (B[1] * R).toFixed(2)); l.style.display = ''; }
    else l.style.display = 'none';
  });
  BALL3.pents.forEach((pt, i) => {
    const poly = kids[n + i];
    if (mul(ballM, pt.c)[2] < .08) { poly.style.display = 'none'; return; }
    poly.setAttribute('points', pt.pts.map(q => { const v = mul(ballM, q); return `${(v[0] * R).toFixed(2)},${(v[1] * R).toFixed(2)}`; }).join(' '));
    poly.style.display = '';
  });
}
function ballSvg() {
  const id = 'b' + (++uid);
  return `<svg viewBox="-20 -20 40 40"><defs><radialGradient id="${id}g" cx="38%" cy="32%" r="72%"><stop offset="0" stop-color="#fff"/><stop offset=".6" stop-color="#eef0f3"/><stop offset="1" stop-color="#9aa2aa"/></radialGradient>
    <radialGradient id="${id}s" cx="50%" cy="50%" r="50%"><stop offset=".55" stop-color="#000" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity=".42"/></radialGradient>
    <radialGradient id="${id}h" cx="34%" cy="28%" r="30%"><stop offset="0" stop-color="#fff" stop-opacity=".95"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient><clipPath id="${id}c"><circle r="18.6"/></clipPath></defs>
    <circle r="19" fill="url(#${id}g)"/>
    <g clip-path="url(#${id}c)"><g class="pat" fill="#1d2129" stroke="#2a2f38" stroke-width=".7" stroke-linejoin="round"></g></g>
    <circle r="19" fill="url(#${id}s)"/><circle r="19" fill="url(#${id}h)"/>
    <circle r="18.7" fill="none" stroke="rgba(0,0,0,.35)" stroke-width=".7"/></svg>`;
}

let pred = null;
let mid = store.get('fmid', null), me = '0', snap = null, since = 0, busy = false, acting = false, pollT = null, overShown = false;
let s = .5, cur = [], els = [], teams = {}, deadlineAt = 0, readyAt = 0, turnMs = 15000, warned = false, kickedAt = 0, aim = null;
const opp = () => (me === '0' ? '1' : '0');
const flip = () => me === '1';
const P = () => (snap && snap.game ? snap.game.players : {});
const nameOf = c => c === me ? 'تو' : (P()[c] ? P()[c].name : 'حریف');
const mine = i => (me === '0' ? i < 6 : i >= 6 && i < 12);
const toView = ([x, y]) => flip() ? [W - x, H - y] : [x, y];

/* ---------- زمین ---------- */
function fit() {
  const r = $('arena').getBoundingClientRect();
  const k = Math.min((r.width - 2 * 36 - 10) / W, (r.height - 14) / (H + GOAL_D * 1.6));
  if (k > 0 && Math.abs(k - s) > .002) { s = k; build(); }
}
function line(st) { const d = document.createElement('div'); d.className = 'fb-ln'; d.style.cssText = st; return d; }
function build() {
  const pitch = $('pitch');
  pitch.style.width = W * s + 'px'; pitch.style.height = H * s + 'px'; pitch.style.setProperty('--s', s);
  pitch.innerHTML = '';
  const px = v => (v * s).toFixed(1) + 'px';
  const b = Math.max(1.5, 2.2 * s * 1.5).toFixed(1) + 'px';
  const arc = (cx, cy, r, clip) => line(`left:${px(cx - r)};top:${px(cy - r)};width:${px(2 * r)};height:${px(2 * r)};border-width:${b};border-radius:50%;clip-path:${clip}`);
  const spot = (cx, cy) => line(`left:${px(cx) };top:${px(cy)};width:${px(9)};height:${px(9)};margin:${px(-4.5)} 0 0 ${px(-4.5)};border-radius:50%;background:rgba(255,255,255,.9)`);
  const cut = ((130 - (105 - 72)) / 144 * 100).toFixed(1);
  pitch.append(
    line(`left:${px(10)};right:${px(10)};top:0;bottom:0;border-width:${b}`),
    line(`left:${px(10)};right:${px(10)};top:${px(MID)};border-top-width:${b};transform:translateY(-50%)`),
    arc(W / 2, MID, 100, 'none'), spot(W / 2, MID),
    line(`left:${px(150)};top:0;width:${px(300)};height:${px(130)};border-width:0 ${b} ${b} ${b}`),
    line(`left:${px(215)};top:0;width:${px(170)};height:${px(55)};border-width:0 ${b} ${b} ${b}`),
    spot(W / 2, 105), arc(W / 2, 105, 72, `inset(${cut}% 0 0 0)`),
    line(`left:${px(150)};bottom:0;width:${px(300)};height:${px(130)};border-width:${b} ${b} 0 ${b}`),
    line(`left:${px(215)};bottom:0;width:${px(170)};height:${px(55)};border-width:${b} ${b} 0 ${b}`),
    spot(W / 2, H - 105), arc(W / 2, H - 105, 72, `inset(0 0 ${cut}% 0)`),
    arc(10, 0, 24, 'inset(50% 0 0 50%)'), arc(W - 10, 0, 24, 'inset(50% 50% 0 0)'),
    arc(10, H, 24, 'inset(0 0 50% 50%)'), arc(W - 10, H, 24, 'inset(0 50% 50% 0)'),
  );
  const net = (cls, pos) => {
    const d = document.createElement('div'); d.className = 'fb-net ' + cls;
    d.style.cssText = `left:${px(GX0)};${pos};width:${px(GOAL_W)};height:${px(GOAL_D)}`;
    d.innerHTML = '<i class="mesh"></i><i class="bar"></i><i class="post l"></i><i class="post r"></i>';
    pitch.appendChild(d); return d;
  };
  net('fb-goal-top', `top:${px(-GOAL_D)}`); net('fb-goal-bot', `bottom:${px(-GOAL_D)}`);
  const flag = (cls, col) => { const d = document.createElement('div'); d.className = 'fb-flag ' + cls; d.innerHTML = `<svg viewBox="0 0 14 22"><path d="M2 21V2" stroke="#e9edf1" stroke-width="1.6" stroke-linecap="round"/><path d="M2.6 2.5l9 3.2-9 3.3z" fill="${col}"/></svg>`; pitch.appendChild(d); };
  flag('tl', '#E63946'); flag('tr', '#E63946'); flag('bl', '#2F80ED'); flag('br', '#2F80ED');
  els = [];
  for (let i = 0; i < 13; i++) {
    const w = document.createElement('div');
    if (i === BALL) { w.innerHTML = `<span class="fb-ball" style="width:${px(2 * BALL_R)};height:${px(2 * BALL_R)}"><i class="sh"></i>${ballSvg()}</span>`; }
    else { const t = teams[i < 6 ? '0' : '1'] || {}; w.innerHTML = discHtml(t.team, t.kit, 2 * DISC_R * s, mine(i) ? 'me pulse' : ''); }
    const el = w.firstElementChild; el.dataset.i = i; pitch.appendChild(el); els.push(el);
    if (cur[i]) setPos(i, cur[i]);
  }
  // نشانه گیری زیر مهره ها و توپ کشیده می شود
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg'); svg.classList.add('fb-aim'); svg.id = 'aim';
  svg.setAttribute('viewBox', `0 0 ${W * s} ${H * s}`); pitch.insertBefore(svg, els[0]);
  syncTurn();
}
function setPos(i, p) {
  cur[i] = p;
  const el = els[i]; if (!el) return;
  const [x, y] = toView(p), r = i === BALL ? BALL_R : DISC_R;
  el.style.transform = `translate3d(${((x - r) * s).toFixed(1)}px,${((y - r) * s).toFixed(1)}px,0)`;
  if (i === BALL) {
    // غلتیدن واقعی در جهت حرکت (در مختصات نمایش، پس برای هر دو بازیکن درست است)
    if (ballAt && Math.hypot(x - ballAt[0], y - ballAt[1]) < 400) rollBall(x - ballAt[0], y - ballAt[1]);
    ballAt = [x, y];
    drawBall(el);
  }
}
function setAll(pos) { pos.forEach((p, i) => setPos(i, p)); }
function setTeams(t) {
  teams = {}; for (const [c, v] of Object.entries(t || {})) if (v && v.team) teams[c] = v;
  build();
}

/* ---------- سربرگ و وضعیت ---------- */
let headKey = '';
function renderHead(g) {
  const pm = g.players[me] || {}, po = g.players[opp()] || {};
  const key = JSON.stringify([pm.name, pm.pic, po.name, po.pic, po.out, teams, g.score, g.target, g.phase, g.over, g.turn, me]);
  if (key === headKey && $('head').firstElementChild) return;
  headKey = key;
  const tm = TEAM[(teams[me] || pm).team], to = TEAM[(teams[opp()] || po).team];
  const turn = g.phase === 'play' && !g.over;
  $('head').innerHTML = `
    <div class="fb-pl me" data-seat="${me}">${face(pm, 'var(--me)', turn && g.turn === me ? 'timer' : '')}<span class="nm"><b>${pm.name || 'تو'}</b><span>${tm ? tm.fa : 'تیم تو'}</span></span></div>
    <div class="fb-sc"><b id="score">${FD(g.score[+me])} - ${FD(g.score[+opp()])}</b><span>تا ${FD(g.target)} گل</span></div>
    <div class="fb-pl op${po.out ? ' away' : ''}" data-seat="${opp()}">${face(po, '#FF7A85', turn && g.turn === opp() ? 'timer' : '')}<span class="dot"></span><span class="nm"><b>${po.name || 'حریف'}</b><span>${to ? to.fa : 'حریف'}</span></span></div>`;
  for (const c of Object.keys(bubbles)) showBubble(c);
}
function renderStatus(g) {
  const st = $('status');
  st.classList.toggle('mine', g.phase === 'play' && g.turn === me);
  if (g.over) st.textContent = 'پایان بازی';
  else if (g.phase === 'setup') st.textContent = 'انتخاب تیم و چیدمان…';
  else if (g.turn === me) st.innerHTML = `نوبت توست${g.deadline_ms ? '<em id="clock"></em>' : ''}`;
  else { const q = g.players[g.turn] || {}; st.innerHTML = `نوبت ${q.name || 'حریف'}<em>${q.bot || q.out ? 'فکر می‌کند…' : ''}</em>`; }
  setDeadline(g.deadline_ms);
  readyAt = Date.now() + (g.ready_ms || 0);
  turnMs = g.turn_ms || 15000;
}
function syncTurn() {
  const g = snap && snap.game, on = !!(g && g.phase === 'play' && !g.over && g.turn === me);
  $('pitch').classList.toggle('myturn', on);
  const hint = $('hint'), n = store.get('fbHints', 0);
  hint.hidden = !(on && n < 6);
}
function renderAll(g) { renderHead(g); renderStatus(g); syncTurn(); mount($('head')); tickTimer(); }
// مهلت نوبت: پرسش های پی در پی سرور با تاخیر شبکه کمی جابه جایش می کنند؛ فقط تغییر
// واقعی (نوبت تازه) را بپذیر تا حلقه زمان یکنواخت کم شود و هشدار یک بار بیاید
function setDeadline(ms) {
  const d = ms ? Date.now() + ms : 0;
  if (!d) { deadlineAt = 0; return; }
  if (!deadlineAt || Math.abs(d - deadlineAt) > 1500) warned = false;
  if (!deadlineAt || Math.abs(d - deadlineAt) > 700) deadlineAt = d;
}
function tickTimer() {
  if (!snap || !snap.game) return;
  const g = snap.game, left = deadlineAt ? Math.max(0, deadlineAt - Date.now()) : 0, frac = deadlineAt ? Math.min(1, left / turnMs) : 1;
  document.querySelectorAll('.fb-pl .avatar').forEach(a => a.style.setProperty('--t', a.classList.contains('timer') ? frac : 1));
  const ck = $('clock'); if (ck) ck.textContent = FD(Math.ceil(left / 1000)) + ' ثانیه';
  if (g.turn === me && g.phase === 'play' && deadlineAt && frac < .3 && !warned) { warned = true; sfx.tick(); haptic('warning'); }
  if (setupEl) tickSetup();
}
setInterval(tickTimer, 200);

/* ---------- نشانه گیری و شوت ---------- */
const canShoot = () => snap && snap.status === 'playing' && snap.game.phase === 'play' && snap.game.turn === me && !busy && !acting && Date.now() >= readyAt - 250;
const maxDrag = () => Math.max(84, DISC_R * s * 4.6);
function local(ev) { const r = $('pitch').getBoundingClientRect(); return [ev.clientX - r.left, ev.clientY - r.top]; }
let aimRaf = 0, aimDX = 0, aimDY = 0;
function drawAim(dx, dy) {
  aimDX = dx; aimDY = dy;
  if (!aimRaf) aimRaf = requestAnimationFrame(() => { aimRaf = 0; paintAim(aimDX, aimDY); });
}
// فلش سفید پهن شونده با سر مثلثی؛ نوکش هیچ وقت از دایره قدرت بیرون نمی زند. کمان سفید لبه دایره = قدرت
function paintAim(dx, dy) {
  const svg = $('aim'); if (!svg || !aim) return;
  const R = maxDrag(), d = Math.hypot(dx, dy), p = Math.min(1, d / R), r = DISC_R * s, cx = aim.cx, cy = aim.cy;
  const ux = d ? -dx / d : 0, uy = d ? -dy / d : -1, px = -uy, py = ux;
  const f = n => n.toFixed(1);
  let body = '';
  if (d > 4) {
    const s0 = r * .3, tip = r * .75 + p * (R - 5 - r * .75), ah = Math.min(R * .24, 11 + p * 9), hw = ah * .8;
    const w0 = 3, w1 = 6 + p * 5, neck = tip - ah;
    const P = (t, w) => `${f(cx + ux * t + px * w)},${f(cy + uy * t + py * w)}`;
    const arrow = `${P(s0, w0)} ${P(neck, w1)} ${P(neck, hw)} ${P(tip, 0)} ${P(neck, -hw)} ${P(neck, -w1)} ${P(s0, -w0)}`;
    const pl = Math.min(d, R) - 2, dots = [];
    for (let t = r + 6; t < pl; t += 9) dots.push(`<circle cx="${f(cx - ux * t)}" cy="${f(cy - uy * t)}" r="${f(1.6 + (t / R) * 1.2)}"/>`);
    const arc = Math.PI * R * p, ang = Math.atan2(uy, ux) * 180 / Math.PI - (arc / R) * 90 / Math.PI;
    body = `<circle cx="${f(cx)}" cy="${f(cy)}" r="${f(R - 1.5)}" fill="none" stroke="#fff" stroke-width="3.2" stroke-linecap="round" stroke-dasharray="${f(arc)} ${f(2 * Math.PI * R)}" transform="rotate(${f(ang)} ${f(cx)} ${f(cy)})" opacity=".9"/>
      <g fill="rgba(255,255,255,.75)">${dots.join('')}</g>
      <polygon points="${arrow}" fill="rgba(0,0,0,.28)" transform="translate(1.2 2)"/>
      <polygon points="${arrow}" fill="#fff" stroke="rgba(30,40,50,.25)" stroke-width="1" stroke-linejoin="round"/>`;
  }
  svg.innerHTML = `<circle cx="${f(cx)}" cy="${f(cy)}" r="${f(R)}" fill="rgba(0,0,0,.24)" stroke="rgba(255,255,255,.35)" stroke-width="1.5"/>${body}`;
  aim.p = p; aim.dx = ux; aim.dy = uy;
}
function endAim() { if (aimRaf) { cancelAnimationFrame(aimRaf); aimRaf = 0; } if (aim && els[aim.i]) els[aim.i].classList.remove('aim'); aim = null; const svg = $('aim'); if (svg) svg.innerHTML = ''; }
$('pitch').addEventListener('pointerdown', ev => {
  if (!canShoot()) return;
  const [px, py] = local(ev);
  let best = null, bd = DISC_R * s * 1.7;
  for (let i = 0; i < 12; i++) {
    if (!mine(i) || !cur[i]) continue;
    const [x, y] = toView(cur[i]), d = Math.hypot(x * s - px, y * s - py);
    if (d < bd) { bd = d; best = i; }
  }
  if (best == null) return;
  const [x, y] = toView(cur[best]);
  aim = { i: best, cx: x * s, cy: y * s, p: 0, dx: 0, dy: -1 };
  els[best].classList.add('aim'); haptic('select');
  try { $('pitch').setPointerCapture(ev.pointerId); } catch (e) {}
  drawAim(0, 0); ev.preventDefault();
});
$('pitch').addEventListener('pointermove', ev => { if (!aim) return; const [px, py] = local(ev); drawAim(px - aim.cx, py - aim.cy); }, { passive: true });
$('pitch').addEventListener('pointercancel', endAim);
$('pitch').addEventListener('pointerup', () => {
  if (!aim) return;
  if (aimRaf) { cancelAnimationFrame(aimRaf); aimRaf = 0; paintAim(aimDX, aimDY); }
  const a = aim; endAim();
  if (a.p < .1 || !canShoot()) return;
  const k = a.i % 6, dx = flip() ? -a.dx : a.dx, dy = flip() ? -a.dy : a.dy;
  store.set('fbHints', store.get('fbHints', 0) + 1);
  kickedAt = Date.now(); sfx.fb.kick(a.p); haptic('medium');
  $('pitch').classList.remove('myturn');
  const wdx = Math.round(dx * 10000) / 10000, wdy = Math.round(dy * 10000) / 10000, wp = Math.round(a.p * 1000) / 1000;
  // همان فیزیک سرور همین جا اجرا می شود تا شوت بی تاخیر دیده شود؛ جواب سرور فقط تایید یا اصلاحش است
  const PH = window.FBPhysics, g = snap.game, v = PH && PH.shotVel(wdx, wdy, wp);
  if (v && g.pos && g.pos.length === 13) {
    const res = PH.simulate(g.pos, { [(+me) * 6 + k]: v });
    pred = { pos: res.pos, done: playFrames({ frames: res.frames, ids: res.ids, hits: res.hits, c: me }) };
  }
  act(() => GC.football.shot(mid, k, wdx, wdy, wp, since));
});

/* ---------- انیمیشن ها ---------- */
function jolt(g) {
  const p = $('stadium'); p.style.setProperty('--j', (1 + g * 1.6).toFixed(1) + 'px');
  p.classList.remove('jolt'); void p.offsetWidth; p.classList.add('jolt');
  if (g > .8) haptic('light');
}
function playFrames(e) {
  return new Promise(done => {
    const F = e.frames, ids = e.ids, n = F.length, hits = (e.hits || []).slice(), t0 = performance.now();
    if (!(e.c === me && Date.now() - kickedAt < 4000)) sfx.fb.kick(.8);
    kickedAt = 0;
    const put = (fr, j, id) => setPos(id, [fr[2 * j], fr[2 * j + 1]]);
    const step = t => {
      const el = Math.max(0, (t - t0) / 1000), f = el * 30;  // زمان rAF می تواند کمی قبل از t0 باشد
      while (hits.length && hits[0][0] <= el) { const [, kd, g] = hits.shift(); (kd === 'w' ? sfx.fb.wall : kd === 'p' ? sfx.fb.post : kd === 'b' ? sfx.fb.ball : sfx.fb.clack)(g); if (g > .55 && kd !== 'b') jolt(g); }
      if (f >= n - 1) { ids.forEach((id, j) => put(F[n - 1], j, id)); done(); return; }
      const a = Math.floor(f), u = f - a, A = F[a], B = F[a + 1];
      ids.forEach((id, j) => setPos(id, [A[2 * j] + (B[2 * j] - A[2 * j]) * u, A[2 * j + 1] + (B[2 * j + 1] - A[2 * j + 1]) * u]));
      requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  });
}
function glide(pos, ms = 700) {
  return new Promise(done => {
    const from = cur.map(p => p.slice()), t0 = performance.now();
    const step = t => {
      const u = Math.max(0, Math.min(1, (t - t0) / ms)), k = u < .5 ? 2 * u * u : 1 - Math.pow(-2 * u + 2, 2) / 2;
      pos.forEach((p, i) => { const a = from[i] || p; setPos(i, [a[0] + (p[0] - a[0]) * k, a[1] + (p[1] - a[1]) * k]); });
      if (u < 1) requestAnimationFrame(step); else done();
    };
    requestAnimationFrame(step);
  });
}
async function showVS(e) {
  const t = e.teams || {}, pm = P()[me] || {}, po = P()[opp()] || {};
  const side = (c, p, cls, lab) => `<div class="side ${cls}"><small>${lab}</small>${discHtml(t[c] && t[c].team, t[c] && t[c].kit, 104)}<b>${TEAM[t[c] && t[c].team] ? TEAM[t[c].team].fa : ''}</b><span>${p.name || ''}</span></div>`;
  const el = document.createElement('div'); el.className = 'fb-layer fb-vs'; el.setAttribute('role', 'status');
  el.innerHTML = `<div class="band">${side(me, pm, '', 'تیم تو')}<span class="vs">مقابل</span>${side(opp(), po, 'op', 'حریف')}
    <span class="info">تا ${FD(snap.game.target)} گل · ${e.kick === me ? 'شروع با توست؛ آماده شو!' : 'شروع با ' + (po.name || 'حریف')}</span></div>`;
  document.body.appendChild(el); sfx.enter();
  await sleep(2300); sfx.fb.whistle();
  await sleep(450); el.remove();
}
async function showGoal(e) {
  const scoredMe = e.c === me, sc = e.score;
  const by = P()[e.by] || {};
  document.querySelectorAll('.fb-net').forEach(n => { n.classList.remove('shake'); void n.offsetWidth; });
  const goalNet = document.querySelector(scoredMe ? '.fb-goal-top' : '.fb-goal-bot'); if (goalNet) goalNet.classList.add('shake');
  document.querySelectorAll('.fb-crowd').forEach(c => { c.classList.remove('cheer'); void c.offsetWidth; c.classList.add('cheer'); });
  sfx.fb.goal(); sfx.fb.roar(); haptic(scoredMe ? 'success' : 'warning');
  await sleep(450);
  const t = teams[e.c] || {}, title = scoredMe ? (e.own ? 'گل به خودی حریف!' : 'تو گل زدی!') : (e.own ? 'گل به خودی!' : (by.name || 'حریف') + ' گل زد');
  const el = document.createElement('div'); el.className = 'fb-layer fb-goal'; el.setAttribute('role', 'status');
  const conf = scoredMe ? Array.from({ length: 26 }, (_, i) => `<span class="fb-cf" style="left:${(i * 37) % 100}%;background:${['#F5C451', '#3D7BFF', '#FF7A85', '#3DD08E', '#fff', '#B78CFF'][i % 6]};animation-duration:${1.6 + (i % 5) * .3}s;animation-delay:${(i % 7) * .08}s"></span>`).join('') : '';
  el.innerHTML = `<span class="rays"></span>${conf}<b class="word${scoredMe ? '' : ' sad'}">گُل!</b>
    <div class="who">${discHtml(t.team, t.kit, 44)}<span><b>${title}</b><span>${FD(sc[+me])} - ${FD(sc[+opp()])} · تا ${FD(snap.game.target)} گل</span></span></div>
    <div class="boxes"><span class="t" style="color:#8DB4FF">${TEAM[(teams[me] || {}).team] ? TEAM[teams[me].team].fa : 'تو'}</span>
      <span class="n${scoredMe ? ' hot' : ''}" style="background:#2F6FE0">${FD(sc[+me])}</span><span class="n${scoredMe ? '' : ' hot'}" style="background:#D7263D">${FD(sc[+opp()])}</span>
      <span class="t" style="color:#FF9F9F">${TEAM[(teams[opp()] || {}).team] ? TEAM[teams[opp()].team].fa : 'حریف'}</span></div>`;
  document.body.appendChild(el);
  const b = $('score'); if (b) { b.textContent = `${FD(sc[+me])} - ${FD(sc[+opp()])}`; b.classList.remove('bump'); void b.offsetWidth; b.classList.add('bump'); }
  await sleep(2300); el.remove();
}

/* ---------- انتخاب تیم و چیدمان ---------- */
let setupEl = null, setupStep = 'team', setupEnds = 0, choice = Object.assign({ team: 'eagles', fa: '132', fd: '132' }, store.get('fbSetup', {}));
function tickSetup() {
  const left = Math.max(0, setupEnds - Date.now()), el = setupEl && setupEl.querySelector('.fb-cd');
  if (!el) return;
  el.querySelector('i').textContent = FD(Math.ceil(left / 1000));
  el.querySelector('i').style.setProperty('--t', Math.min(1, left / 20000));
  el.lastChild.textContent = 'شروع بازی تا ' + FD(Math.ceil(left / 1000)) + ' ثانیه';
}
function openSetup(g) {
  setupEnds = Date.now() + (g.setup_ms || 0);
  if (g.players[me] && g.players[me].ready) setupStep = 'wait';
  if (!setupEl) { setupEl = document.createElement('div'); setupEl.className = 'fb-layer fb-setup'; document.body.appendChild(setupEl); }
  renderSetup();
}
function closeSetup() { if (setupEl) { setupEl.remove(); setupEl = null; } }
const cd = () => '<span class="fb-cd"><i></i><span></span></span>';
function renderSetup() {
  const el = setupEl; if (!el) return;
  const g = snap && snap.game, oppReady = g && g.players[opp()] && g.players[opp()].ready;
  if (setupStep === 'team') {
    el.innerHTML = `<div class="top"><span></span>${cd()}</div>
      <div><h1>تیمت را انتخاب کن</h1><p class="sub">اگر حریف هم همین تیم را بردارد، یکی از شما لباس مهمان می‌پوشد.</p></div>
      <div class="fb-tabs"><button aria-pressed="true">همه تیم‌ها</button><button disabled>ویژه · به‌زودی</button></div>
      <div class="fb-teams">${TEAM_IDS.map(t => `<button class="fb-team" data-team="${t}" aria-pressed="${choice.team === t}"><span><b>${TEAM[t].fa}</b><small>${TEAM[t].sub}</small></span>
        <span class="fb-kit">${discHtml(t, 'home', 44)}خانگی</span><span class="fb-kit">${discHtml(t, 'away', 44)}مهمان</span></button>`).join('')}</div>
      <button class="fb-go" id="setNext">همین تیم · بعدی</button>`;
    el.querySelectorAll('[data-team]').forEach(b => b.onclick = () => { choice.team = b.dataset.team; sfx.tap(); haptic('select'); el.querySelectorAll('[data-team]').forEach(x => x.setAttribute('aria-pressed', String(x === b))); });
    el.querySelector('#setNext').onclick = () => { setupStep = 'form'; sfx.tap(); renderSetup(); };
  } else if (setupStep === 'form') {
    const opt = (kind, f) => `<button class="fb-opt" data-k="${kind}" data-f="${f}" aria-pressed="${choice[kind === 'a' ? 'fa' : 'fd'] === f}"><span class="fb-mini"><i style="left:50%;top:90%"></i>${MINI[kind][f].map(([x, y]) => `<i style="left:${x}%;top:${y}%"></i>`).join('')}</span>${FORM_FA[f]}</button>`;
    el.innerHTML = `<div class="top"><button class="fb-ib" id="setBack" aria-label="برگشت به انتخاب تیم">${icon('back')}</button>${cd()}</div>
      <div><h1>چیدمان تیم</h1><p class="sub">بعد از هر گل مهره‌ها با همین چیدمان سر جایشان برمی‌گردند.</p></div>
      <section class="fb-forms"><div class="h"><i style="background:rgba(61,123,255,.2);color:#8DB4FF"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M12 19V5M6 11l6-6 6 6"/></svg></i><b>حمله</b><span>وقتی شروع با توست</span></div>
        <div class="row">${FORM_IDS.map(f => opt('a', f)).join('')}</div></section>
      <section class="fb-forms"><div class="h"><i style="background:rgba(242,96,63,.2);color:#FF9F86"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linejoin="round"><path d="M12 3l7 3v5c0 4.6-3 8.3-7 10-4-1.7-7-5.4-7-10V6z"/></svg></i><b>دفاع</b><span>وقتی شروع با حریف است</span></div>
        <div class="row">${FORM_IDS.map(f => opt('d', f)).join('')}</div></section>
      <div style="flex:1"></div>
      <button class="fb-go" id="setOk">تایید و آماده‌ام</button>`;
    el.querySelectorAll('.fb-opt').forEach(b => b.onclick = () => {
      const key = b.dataset.k === 'a' ? 'fa' : 'fd'; choice[key] = b.dataset.f; sfx.tap(); haptic('select');
      el.querySelectorAll(`.fb-opt[data-k="${b.dataset.k}"]`).forEach(x => x.setAttribute('aria-pressed', String(x === b)));
    });
    el.querySelector('#setBack').onclick = () => { setupStep = 'team'; renderSetup(); };
    el.querySelector('#setOk').onclick = async () => {
      store.set('fbSetup', choice); setupStep = 'wait'; renderSetup(); sfx.turn(); haptic('success');
      await act(() => GC.football.setup(mid, choice.team, choice.fa, choice.fd, since));
    };
  } else {
    el.innerHTML = `<div class="top"><span></span>${cd()}</div>
      <div class="fb-wait">${discHtml(choice.team, 'home', 110)}<b>${TEAM[choice.team] ? TEAM[choice.team].fa : ''} آماده است</b>
        <span>${oppReady ? 'حریف هم آماده است؛ الان شروع می‌شود…' : 'منتظر حریف که تیمش را انتخاب کند…'}</span><span class="spinner" style="border-color:rgba(255,255,255,.25);border-top-color:#fff"></span></div>`;
  }
  tickSetup(); mount(el);
}

/* ---------- پخش رویدادها ---------- */
async function play(e) {
  if (e.t === 'ready') { if (setupStep === 'wait') renderSetup(); return; }
  if (e.t === 'start') { closeSetup(); setTeams(e.teams); setAll(e.pos); renderHead(snap.game); $('status').textContent = 'شروع بازی…'; await showVS(e); return; }
  if (e.t === 'shot') {
    if (pred && e.c === me && !e.auto) {
      const p = pred; pred = null; await p.done;
      const off = e.pos.some((q, i) => !p.pos[i] || Math.hypot(q[0] - p.pos[i][0], q[1] - p.pos[i][1]) > 2);
      if (off) await glide(e.pos, 300); else setAll(e.pos);
    } else if (e.frames && e.frames.length) await playFrames(e); else setAll(e.pos);
    if (e.auto && e.c === me) toast('وقتت تمام شد؛ یک شوت خودکار زده شد');
    return;
  }
  if (e.t === 'goal') { await showGoal(e); return; }
  if (e.t === 'reset') { sfx.fb.whistle(); await glide(e.pos); return; }
  if (e.t === 'timeout') { if (e.c === me) toast(snap.cfg.mode === 'stake' && e.n >= 2 ? (e.n >= 3 ? 'سه نوبت غایب بودی؛ بازی را باختی' : 'یک نوبت دیگر غیبت = باخت') : 'وقتت تمام شد؛ نوبت به حریف رسید'); else toast(`${nameOf(e.c)} شوت نزد؛ نوبت توست`); return; }
  if (e.t === 'leave' && e.c !== me) { toast(`${nameOf(e.c)} ${e.why === 'timeout' ? 'غایب بود' : 'بازی را ترک کرد'}`); return; }
}

/* ---------- گفتگو ---------- */
const QUICK = ['سلام!', 'خوش‌بازی!', 'چه شوتی!', 'شانس آوردی', 'زود باش', 'یک بازی دیگه؟'];
const esc = t => String(t == null ? '' : t).replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
let chatId = 0, chatLog = [], unread = 0, chatSheet = null, sending = false;
const bubbles = {};
function showBubble(c) {
  const b = bubbles[c], seat = document.querySelector(`.fb-pl[data-seat="${c}"]`);
  if (!b || !seat) return;
  if (Date.now() > b.until) { delete bubbles[c]; return; }
  seat.querySelectorAll('.fb-bubble').forEach(x => x.remove());
  const el = document.createElement('div'); el.className = 'fb-bubble'; el.textContent = b.text; el.setAttribute('aria-hidden', 'true');
  seat.appendChild(el);
}
function bubble(m) {
  bubbles[m.color] = { text: m.text, until: Date.now() + 4200 };
  showBubble(m.color);
  setTimeout(() => { if (bubbles[m.color] && Date.now() >= bubbles[m.color].until) { delete bubbles[m.color]; document.querySelectorAll(`.fb-pl[data-seat="${m.color}"] .fb-bubble`).forEach(x => x.remove()); } }, 4300);
}
function badge() { const b = $('chatBadge'); b.hidden = !unread; b.textContent = unread > 9 ? '+۹' : FD(unread); }
function chatIn(list, quiet) {
  if (!list || !list.length) return;
  for (const m of list) {
    if (m.id <= chatId) continue;
    chatId = m.id; chatLog.push(m);
    if (quiet) continue;
    bubble(m);
    if (!m.me && !(chatSheet && document.body.contains(chatSheet))) { unread++; sfx.tap(); }
  }
  chatLog = chatLog.slice(-60); badge();
  if (chatSheet && document.body.contains(chatSheet)) renderChat();
}
function renderChat() {
  const log = chatSheet.querySelector('#chatLog');
  log.innerHTML = chatLog.length ? chatLog.map(m => `<div class="msg${m.me ? ' mine' : ''}">${m.me ? '' : face(m)}<div class="bub">${m.me ? '' : `<b>${esc(m.name)}</b>`}<span>${esc(m.text)}</span></div></div>`).join('')
    : '<p class="hint">هنوز کسی چیزی نگفته. سلام کن!</p>';
  log.scrollTop = log.scrollHeight;
}
async function send(text) {
  text = String(text || '').trim();
  if (!text || sending || !mid) return false;
  sending = true;
  try { await GC.football.chat(mid, text); chatIn((await GC.football.match(mid, since, chatId)).chat); return true; }
  catch (e) { sfx.error(); toast(errText(e)); return false; }
  finally { sending = false; }
}
function openChat() {
  unread = 0; badge();
  const sh = sheet(`${sheetHead('گفتگوی بازی')}<div class="chat-log" id="chatLog" aria-live="polite"></div>
    <div class="quick">${QUICK.map(q => `<button class="chip sm" data-q>${q}</button>`).join('')}</div>
    <form class="chat-form" id="chatForm"><button class="send" aria-label="فرستادن">${icon('up', 2.6)}</button><input id="chatTxt" maxlength="140" placeholder="یه چیزی بگو…" autocomplete="off" enterkeyhint="send" aria-label="پیام به حریف"></form>`,
  { onClose: () => { chatSheet = null; } });
  chatSheet = sh; renderChat();
  sh.querySelectorAll('[data-q]').forEach(b => { b.onclick = () => send(b.textContent); });
  const input = sh.querySelector('#chatTxt');
  sh.querySelector('#chatForm').onsubmit = async e => { e.preventDefault(); if (await send(input.value)) input.value = ''; input.focus(); };
}
$('chatBtn').onclick = openChat;
$('emoBtn').onclick = () => {
  const sh = sheet(`${sheetHead('پیام سریع')}<div class="quick" style="justify-content:center">${QUICK.map(q => `<button class="chip" data-q>${q}</button>`).join('')}</div>`);
  sh.querySelectorAll('[data-q]').forEach(b => { b.onclick = () => { GC.close(); send(b.textContent); }; });
};
function endChat() { chatLog = []; unread = 0; chatSheet = null; for (const c of Object.keys(bubbles)) delete bubbles[c]; document.querySelectorAll('.fb-bubble').forEach(x => x.remove()); }

/* ---------- همگام سازی با سرور ---------- */
async function apply(next, anim = true) {
  if (next && next.chat && !overShown && next.status !== 'over' && next.status !== 'cancelled') chatIn(next.chat);
  if (next && next.status === 'cancelled') return cancelled();
  if (!next || !next.game) return;
  busy = true;
  try {
    snap = Object.assign({}, snap || {}, next);
    const g = next.game, evs = (g.events || []).filter(e => e.seq > since).sort((a, b) => a.seq - b.seq);
    for (const e of evs) { if (anim) await play(e); since = e.seq; }
    since = Math.max(since, g.seq);
    if (g.phase === 'setup') openSetup(g); else closeSetup();
    const tt = {}; for (const c of ['0', '1']) if (g.players[c] && g.players[c].team && g.phase !== 'setup') tt[c] = { team: g.players[c].team, kit: g.players[c].kit };
    if (JSON.stringify(tt) !== JSON.stringify(teams)) setTeams(tt);
    setAll(g.pos);
    renderAll(g);
    if (next.status === 'over' && !overShown) { overShown = true; over(next); }
  } finally { busy = false; }
}
async function poll() {
  clearTimeout(pollT);
  if (document.hidden || overShown) { pollT = setTimeout(poll, POLL_MS); return; }
  if (!busy && !acting) {
    try { await apply(await GC.football.match(mid, since, chatId)); }
    catch (e) { if (e.code === 'not_found') return noMatch(); }
  }
  pollT = setTimeout(poll, POLL_MS);
}
async function act(fn) {
  if (acting) return;
  acting = true;
  try { const res = await fn(); acting = false; await apply(res); }
  catch (e) {
    if (pred) { const p = pred; pred = null; await p.done; if (snap && snap.game) await glide(snap.game.pos, 350); }
    sfx.error(); haptic('error'); toast(errText(e)); if (snap && snap.game) { if (snap.game.phase === 'setup') { setupStep = 'form'; renderSetup(); } renderAll(snap.game); } }
  finally { acting = false; }
}
document.addEventListener('visibilitychange', () => { if (!document.hidden) { poll(); if (!overShown) sfx.fb.crowd(true); } else sfx.fb.crowd(false); });

/* ---------- پایان، خروج ---------- */
const TROPHY = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 21h8M12 17v4M7 4h10v5a5 5 0 0 1-10 0z"/><path d="M17 5h3v2a3 3 0 0 1-3 3M7 5H4v2a3 3 0 0 0 3 3"/></svg>';
function over(v) {
  endChat(); closeSetup(); sfx.fb.crowd(false);
  const g = v.game, r = v.result || {}, won = !!r.won;
  GC.guardClose(false); store.set('fmid', null);
  won ? (sfx.win(), haptic('success')) : (sfx.lose(), haptic('warning'));
  const secs = Math.max(0, Math.round(Date.now() / 1000 - g.started)), st = g.stats || { shots: 0, goals: 0 };
  const stake = v.cfg.mode === 'stake', ended = g.winner == null, left = (g.players[opp()] || {}).out;
  sheet(`<div class="fb-res">
      <span class="ic${won ? '' : ' lost'}">${TROPHY}</span>
      <h2>${ended ? 'بازی تمام شد' : won ? (left ? 'حریف رفت؛ تو بردی!' : 'بردی!') : 'این بازی را باختی'}</h2>
      <div class="final">${discHtml((teams[me] || {}).team, (teams[me] || {}).kit, 40)}<b>${FD(g.score[+me])} - ${FD(g.score[+opp()])}</b>${discHtml((teams[opp()] || {}).team, (teams[opp()] || {}).kit, 40)}</div>
      ${stake ? (won ? `<div class="prize">${amount(r.prize || 0, 'lg')}</div><p>جایزه به کیف امتیازت اضافه شد.</p>` : ended ? '<p>ورودی‌ها برگشت.</p>' : `<p>ورودی این بازی (${fa(r.lost || v.cfg.entry)} امتیاز) را باختی.</p>`)
        : `<p>${won ? 'بازی آزاد بود و جایزه نداشت.' : 'بازی آزاد بود؛ چیزی از دست ندادی.'}</p>`}
      <div class="facts"><div><b>${FD(st.goals)}</b><span>گل زدی</span></div><div><b>${FD(st.shots)}</b><span>شوت</span></div><div><b>${FD(Math.floor(secs / 60))}:${FD(String(secs % 60).padStart(2, '0'))}</b><span>مدت بازی</span></div></div>
    </div>
    <a class="btn btn-block" href="football-lobby.html">یک بازی دیگر</a>
    <a class="btn btn-light btn-block" href="index.html">خانه</a>`, { center: true, dismiss: false });
  GC.refreshMe().catch(() => {});
}
function cancelled() {
  if (overShown) return;
  overShown = true; endChat(); closeSetup(); GC.guardClose(false); store.set('fmid', null); GC.refreshMe().catch(() => {});
  sheet(`<div class="dlg" role="alertdialog" aria-labelledby="dT" aria-describedby="dD"><span class="dlg-ic">${icon('table')}</span>
      <h2 id="dT">این بازی بسته شد</h2><p id="dD">پشتیبانی این بازی را بست و ورودی همه به کیف امتیازشان برگشت.</p>
      <div class="dlg-acts"><a class="btn" href="football-lobby.html">بازی تازه</a><a class="btn btn-light" href="index.html">خانه</a></div></div>`, { center: true, dismiss: false });
}
function noMatch() {
  store.set('fmid', null); closeSetup();
  sheet(`<div class="dlg" role="alertdialog" aria-labelledby="dT" aria-describedby="dD"><span class="dlg-ic">${icon('table')}</span>
      <h2 id="dT">بازی‌ای پیدا نشد</h2><p id="dD">این بازی تمام شده یا هنوز وارد بازی‌ای نشده‌ای.</p>
      <div class="dlg-acts"><a class="btn" href="football-lobby.html">شروع بازی</a><a class="btn btn-light" href="index.html">خانه</a></div></div>`, { center: true, dismiss: false });
}
function askExit() {
  if (!snap || snap.status === 'over') { location.href = 'index.html'; return; }
  const stake = snap.cfg.mode === 'stake';
  const sh = sheet(`<div class="dlg" role="alertdialog" aria-labelledby="dT" aria-describedby="dD">
      <span class="dlg-ic warn">${icon('exit')}</span>
      <h2 id="dT">از بازی بیرون می‌روی؟</h2>
      <p id="dD">خروج یعنی باخت همین بازی و حریف برنده می‌شود.</p>
      <div class="dlg-note">${stake ? `ورودی ${amount(snap.cfg.entry)} برنمی‌گردد` : 'بازی آزاد است؛ امتیازی از دست نمی‌دهی'}</div>
      <div class="dlg-acts"><button class="btn" data-close>ادامهٔ بازی</button><button class="btn btn-danger-soft" id="leave">${icon('exit')}خروج</button></div>
      <button class="btn btn-light btn-block dlg-home" id="home">${icon('home')}فقط برو خانه؛ بازی می‌ماند</button>
      <p class="dlg-fine">بازی در صفحهٔ خانه می‌ماند و با یک لمس برمی‌گردی. تا نیستی نوبتت می‌سوزد${stake ? '؛ در بازی امتیازی سه نوبت غیبت پشت‌سرهم یعنی باخت' : ''}.</p>
    </div>`, { center: true });
  sh.querySelector('#home').onclick = () => { GC.guardClose(false); location.href = 'index.html'; };
  sh.querySelector('#leave').onclick = async () => {
    try { await GC.football.leave(mid); } catch (e) {}
    GC.guardClose(false); store.set('fmid', null); location.href = 'index.html';
  };
}
$('exit').onclick = askExit;
GC.back(askExit);
const sndBtn = $('snd');
const syncSnd = () => { sndBtn.innerHTML = icon(S.sound ? 'soundOn' : 'soundOff'); sndBtn.setAttribute('aria-pressed', String(!!S.sound)); sndBtn.setAttribute('aria-label', S.sound ? 'خاموش کردن صدا' : 'روشن کردن صدا'); };
sndBtn.onclick = () => { setSound(!S.sound); syncSnd(); if (S.sound) { GC.loadSamples(); if (!overShown) sfx.fb.crowd(true); } };
syncSnd();
document.addEventListener('pointerdown', () => { GC.loadSamples(); if (!overShown) sfx.fb.crowd(true); }, { once: true });
window.addEventListener('resize', fit);
try { Telegram.WebApp.onEvent('viewportChanged', fit); Telegram.WebApp.onEvent('fullscreenChanged', () => setTimeout(fit, 50)); } catch (e) {}

/* ---------- شروع ---------- */
async function start() {
  GC.portrait(true);
  build(); fit();
  let first;
  try { first = await GC.football.match(mid, 0, 0); }
  catch (e) { return e.code === 'not_found' ? noMatch() : (toast(errText(e)), setTimeout(start, 2500)); }
  if (first.status === 'lobby') { location.href = 'football-lobby.html'; return; }
  if (first.status === 'cancelled') return cancelled();
  mid = first.id; store.set('fmid', mid); me = first.me;
  if (first.cfg.mode === 'stake' && first.status === 'playing') GC.guardClose(true);
  chatIn(first.chat, true);
  const g = first.game;
  snap = first;
  const evs = (g.events || []).slice().sort((a, b) => a.seq - b.seq), startEv = evs.find(e => e.t === 'start');
  // تازه شروع شده (از لابی آمده ایم): «مقابل» را ببیند
  if (first.status === 'playing' && startEv && !evs.some(e => e.seq > startEv.seq && e.t === 'shot')) {
    since = startEv.seq - 1;
    fit(); await apply(first); poll(); return;
  }
  since = g.seq;
  await apply(first, false); fit();
  poll();
}
start();
})();
