/* صفحهٔ بازی دیوار (کوریدور). وضعیت از سرور می آید (game_club/divar.py)؛ این صفحه فقط نشان می دهد،
   حرکت و دیوار را می فرستد و پیش از فرستادن، جای مجاز دیوار را با همان قواعد (divar-engine.js) نشان می دهد.
   صفحه طوری چرخانده می شود که هر کس خودش را پایین ببیند؛ رنگ من همیشه آبی است. */
(() => {
const { FD, fa, store, S, setSound, icon, sheet, toast, sfx, haptic, sleep, errText, face, amount } = GC;
const $ = id => document.getElementById(id);
const E = DVEngine;
// رنگ ها نسبت به من: من آبی، نفر بعد (چپ) سبز، روبه رو قرمز، راست زرد
const COLORS = [{ pc: '#4C8DFF', pd: '#2B62D6' }, { pc: '#2FC584', pd: '#1E8A5E' }, { pc: '#FF5A6A', pd: '#C93447' }, { pc: '#FFC531', pd: '#C98A00' }];
const ROT = { 0: 0, 1: 3, 2: 2, 3: 1 };          // چند بار ۹۰ درجهٔ ساعتگرد تا ضلع من پایین بیاید
const GOAL_SIDE = { 0: 0, 1: 1, 2: 2, 3: 3 };    // ضلع مقصد هر صندلی روی صفحهٔ سرور (۰ بالا، ۱ راست، ۲ پایین، ۳ چپ)
const START_SIDE = { 0: 2, 1: 3, 2: 0, 3: 1 };   // ضلع شروع هر صندلی (همان شماره گذاری)
const STAR = '<svg viewBox="0 0 24 24"><path fill="#F5C451" stroke="#B9801E" stroke-width="1" d="M12 2l2.9 6.6 7.1.6-5.4 4.7 1.6 7L12 17.3 5.8 20.9l1.6-7L2 9.2l7.1-.6z"/></svg>';
const CLOCK = '<svg viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="6" cy="6" r="4.6"/><path d="M6 3.4V6l1.8 1.1" stroke-linecap="round"/></svg>';

const watchMid = GC.watchId();
let WATCH = false;
let mid = watchMid || store.get('dmid', null), me = '0', snap = null, since = 0, busy = false, acting = false, pollT = null, overShown = false;
let N = 9, rot = 0, built = '', deadlineAt = 0, readyAt = 0, turnMs = 25000, warned = false, flash = null, lastTurn = null;
const vpos = {};               // جای نمایش هر مهره (مختصات سرور)
let vwalls = [];               // دیوارهای نمایش (مختصات سرور) [o, r, c, صاحب]
const els = { pawns: {}, walls: {} };
const G = () => snap && snap.game;
const isMe = c => c === me && !WATCH;
const nameOf = c => isMe(c) ? 'تو' : (G() && G().players[c] ? G().players[c].name : 'حریف');
const nameH = c => isMe(c) ? 'تو' : (G() && G().players[c] ? GC.uname(G().players[c].name) : 'حریف');   // برای innerHTML
const colorOf = c => COLORS[((+c) - (+me) + 4) % 4];
const wkey = (o, r, c) => o + r + ',' + c;

/* ---------- چرخش صفحه (سرور ↔ نمایش) ---------- */
function cellV([r, c]) { let a = r, b = c; for (let i = 0; i < rot; i++) [a, b] = [b, N - 1 - a]; return [a, b]; }
function wallV(o, r, c) { for (let i = 0; i < rot; i++) [o, r, c] = [o === 'h' ? 'v' : 'h', c, N - 2 - r]; return [o, r, c]; }
function wallB(o, r, c) { for (let i = 0; i < (4 - rot) % 4; i++) [o, r, c] = [o === 'h' ? 'v' : 'h', c, N - 2 - r]; return [o, r, c]; }

/* ---------- اندازه و ساختن صفحه ---------- */
let W = 300;
function geo() {
  const P = W * .03, Gp = W * (N === 9 ? .017 : .014), Sz = (W - 2 * P - (N - 1) * Gp) / N;
  return { W, P, G: Gp, S: Sz, x: i => P + i * (Sz + Gp), T: Math.max(3.5, Gp * 1.1) };
}
function fit() {
  const r = $('arena').getBoundingClientRect();
  const w = Math.floor(Math.max(200, Math.min(r.width - 24, r.height - 14, 560)));
  if (w !== W) { W = w; const b = $('board'); b.style.width = b.style.height = W + 'px'; build(true); }
}
function build(force) {
  const g = G(); if (!g) return;
  const sig = [N, rot, W, g.order.join(), g.star].join('|');
  if (!force && sig === built) return;
  built = sig;
  const b = $('board'), q = geo();
  b.innerHTML = '<span class="dv-lampbox"><span class="dv-lamp"></span></span>';
  dotsKey = '';
  for (let r = 0; r < N; r++) for (let c = 0; c < N; c++) {
    const el = document.createElement('i'); el.className = 'dv-cell';
    Object.assign(el.style, { left: q.x(c) + 'px', top: q.x(r) + 'px', width: q.S + 'px', height: q.S + 'px' }); b.appendChild(el);
  }
  if (g.star) {
    // سکوی چهار رنگ: هر ربع و هر پرتو به رنگ بازیکنی که از همان ضلع می آید
    const m = (N - 1) / 2, el = document.createElement('i'); el.className = 'dv-star';
    el.innerHTML = '<span class="plat"></span>' + STAR;
    Object.assign(el.style, { left: q.x(m) + 'px', top: q.x(m) + 'px', width: q.S + 'px', height: q.S + 'px' });
    const mid = q.x(m) + q.S / 2, bw = q.S * .34, bl = q.S * 1.4;
    for (const s of g.order) {
      const side = (START_SIDE[s] + rot) % 4, col = colorOf(s).pc;
      el.style.setProperty(['--cT', '--cR', '--cB', '--cL'][side], col);
      const bm = document.createElement('i'); bm.className = 'dv-beam';
      bm.style.background = `linear-gradient(${['0deg', '90deg', '180deg', '270deg'][side]},${col},transparent)`;
      Object.assign(bm.style, side === 0 ? { left: mid - bw / 2 + 'px', top: q.x(m) - bl + 'px', width: bw + 'px', height: bl + 'px' }
        : side === 2 ? { left: mid - bw / 2 + 'px', top: q.x(m) + q.S + 'px', width: bw + 'px', height: bl + 'px' }
        : side === 1 ? { top: mid - bw / 2 + 'px', left: q.x(m) + q.S + 'px', width: bl + 'px', height: bw + 'px' }
        : { top: mid - bw / 2 + 'px', left: q.x(m) - bl + 'px', width: bl + 'px', height: bw + 'px' });
      b.appendChild(bm);
    }
    b.appendChild(el);
  } else {
    const t = Math.max(3, q.P * .35), len = W - 2 * q.P;
    for (const s of g.order) {
      const side = (GOAL_SIDE[s] + rot) % 4, e = document.createElement('i'); e.className = 'dv-edge'; e.dataset.side = side;
      e.style.setProperty('--gc', colorOf(s).pc);
      Object.assign(e.style, side % 2 === 0 ? { left: q.P + 'px', width: len + 'px', height: t + 'px', top: (side === 0 ? q.P * .5 - t / 2 : W - q.P * .5 - t / 2) + 'px' }
        : { top: q.P + 'px', height: len + 'px', width: t + 'px', left: (side === 1 ? W - q.P * .5 - t / 2 : q.P * .5 - t / 2) + 'px' });
      b.appendChild(e);
    }
  }
  els.walls = {};
  for (const w of vwalls) addWall(w, false);
  els.pawns = {};
  for (const s of g.order) {
    const el = document.createElement('i'); el.className = 'dv-pawn' + (isMe(s) ? ' me' : '');
    const col = colorOf(s); el.style.setProperty('--pc', col.pc); el.style.setProperty('--pd', col.pd); el.innerHTML = '<b></b>';
    b.appendChild(el); els.pawns[s] = el; placePawn(s);
  }
  const pv = document.createElement('i'); pv.className = 'dv-pv dv-wall'; pv.id = 'pv'; pv.hidden = true; b.appendChild(pv);
  renderDots();
}
function wallRect(o, r, c) {
  const q = geo(), L = 2 * q.S + q.G;
  return o === 'h' ? { left: q.x(c), top: q.x(r + 1) - q.G / 2 - q.T / 2, width: L, height: q.T } : { left: q.x(c + 1) - q.G / 2 - q.T / 2, top: q.x(r), width: q.T, height: L };
}
function setRect(el, R) { for (const k in R) el.style[k] = R[k] + 'px'; }
function addWall(w, anim) {
  const k = wkey(w[0], w[1], w[2]);
  // دیوار موجود: فقط رنگ صاحبش به روز شود (اگر پیش تر بی صاحب کشیده شده بود)
  if (els.walls[k]) { if (w[3] != null) els.walls[k].style.setProperty('--wc', colorOf(w[3]).pc); return; }
  const [o, r, c] = wallV(w[0], w[1], w[2]), el = document.createElement('i');
  el.className = 'dv-wall ' + o + (anim ? ' drop' : ''); setRect(el, wallRect(o, r, c));
  if (w[3] != null) el.style.setProperty('--wc', colorOf(w[3]).pc);   // رنگ کسی که دیوار را گذاشته
  $('board').appendChild(el); els.walls[k] = el;
}
function placePawn(s) {
  const el = els.pawns[s], p = vpos[s]; if (!el || !p) return;
  const q = geo(), sz = q.S * .74, o = (q.S - sz) / 2, [r, c] = cellV(p);
  Object.assign(el.style, { left: q.x(c) + o + 'px', top: q.x(r) + o + 'px', width: sz + 'px', height: sz + 'px' });
}
function hop(s) { const el = els.pawns[s]; if (!el) return; el.classList.remove('hop'); void el.offsetWidth; el.classList.add('hop'); }

/* ---------- خانه های مجاز ---------- */
function myTurnNow() { const g = G(); return !!(g && !WATCH && !g.over && g.turn === me && !busy && !acting && Date.now() >= readyAt - 250); }
// فقط وقتی خانه های مجاز عوض شده اند دوباره ساخته می شوند (نه با هر پرسش از سرور)
let dotsKey = '';
function renderDots() {
  const g = G(), show = myTurnNow() && g.moves, key = show ? JSON.stringify(g.moves) + W + rot : '';
  if (key === dotsKey) return;
  dotsKey = key;
  const b = $('board'); b.querySelectorAll('.dv-dot').forEach(d => d.remove());
  if (!show) return;
  const q = geo();
  for (const m of g.moves) {
    const [r, c] = cellV(m), d = document.createElement('button'); d.className = 'dv-dot'; d.setAttribute('aria-label', 'برو تو این خونه');
    Object.assign(d.style, { left: q.x(c) + 'px', top: q.x(r) + 'px', width: q.S + 'px', height: q.S + 'px' });
    d.onclick = () => doMove(m); b.appendChild(d);
  }
}

/* ---------- سربرگ و وضعیت ---------- */
let playersKey = '';
function renderPlayers(g) {
  const key = JSON.stringify([g.turn, g.over, me, g.order.map(s => { const p = g.players[s] || {}; return [p.name, p.pic, p.walls, p.out]; })]);
  if (key === playersKey) { tickTimer(); return; }
  playersKey = key;
  const box = $('players'), order = g.order.slice();
  // من اول (راست)، بقیه به ترتیب نوبت
  while (order[0] !== me && order.includes(me)) order.push(order.shift());
  box.classList.toggle('four', g.n === 4);
  box.innerHTML = order.map(s => {
    const p = g.players[s] || {}, col = colorOf(s);
    return `<div class="dv-pl${g.turn === s ? ' on' : ''}${p.out ? ' out' : ''}" data-seat="${s}" style="--pc:${col.pc}"><span class="tm">${CLOCK}<span class="tr"><i></i></span></span>${face(p, col.pc)}<span class="tx"><span class="nm">${isMe(s) ? 'خودت' : GC.uname(p.name || '')}</span><span class="wc"><i></i>${FD(p.walls)}</span></span></div>`;
  }).join('');
  tickTimer();
}
function renderStatus(g) {
  const el = $('status');
  let t, cls = '';
  if (flash && Date.now() < flash.until) { t = flash.t; cls = flash.warn ? 'warn' : ''; }
  else if (g.over) t = 'پایان بازی';
  else if (!g.turn) t = '…';
  else if (isMe(g.turn)) { t = 'نوبت توئه · یه قدم برو یا دیوار بذار'; cls = 'mine'; }
  else t = `نوبت ${nameH(g.turn)}…`;
  el.innerHTML = t; el.className = 'dv-pill' + (cls ? ' ' + cls : '');
}
function flashMsg(t, warn) { flash = { t, warn, until: Date.now() + 2400 }; if (G()) renderStatus(G()); setTimeout(() => { if (G()) renderStatus(G()); }, 2500); }
function renderTray(g) {
  const mine = g.players[me];
  $('cnt').textContent = FD(mine ? mine.walls : 0);
  $('tray').classList.toggle('off', !myTurnNow() || !mine || mine.walls <= 0);
}
function renderAll(g) {
  // تا لحظهٔ «آماده» سرور حرکت قبول نمی شود؛ همان لحظه خانه ها و سینی دیوار روشن می شوند
  readyAt = (g._at || Date.now()) + (g.ready_ms || 0);
  if (Date.now() < readyAt - 250) setTimeout(() => { if (G() === g) { renderDots(); renderTray(g); } }, readyAt - 250 - Date.now() + 20);
  N = g.size; rot = WATCH ? 0 : ROT[me] || 0;
  build(false);
  for (const s of g.order) { if (els.pawns[s]) { els.pawns[s].classList.toggle('turn', g.turn === s && !g.over); els.pawns[s].classList.toggle('out', !!g.players[s].out); } }
  renderPlayers(g); renderStatus(g); renderTray(g); renderDots();
  $('mode').textContent = g.n === 2 ? '۲ نفره' : g.star ? '۴ نفره · ستاره' : '۴ نفره';
  const d = g.deadline_ms ? (g._at || Date.now()) + g.deadline_ms : 0;
  if (!d) deadlineAt = 0; else { if (!deadlineAt || Math.abs(d - deadlineAt) > 1500) warned = false; if (!deadlineAt || Math.abs(d - deadlineAt) > 700) deadlineAt = d; }
  turnMs = g.turn_ms || 25000;
  if (g.turn !== lastTurn) { lastTurn = g.turn; if (isMe(g.turn) && !g.over) { sfx.turn(); haptic('light'); } }
}
function tickTimer() {
  const pl = document.querySelector('.dv-pl.on'); if (!pl) return;
  const tm = pl.querySelector('.tm'), bar = pl.querySelector('.tr i');
  tm.classList.toggle('live', !!deadlineAt);
  if (!deadlineAt) return;
  const fr = Math.max(0, Math.min(1, (deadlineAt - Date.now()) / turnMs));
  bar.style.transform = `scaleX(${fr.toFixed(3)})`; bar.style.background = fr > .25 ? '#F5C451' : '#e8503f';
  const g = G(); if (g && isMe(g.turn) && fr < .25 && !warned) { warned = true; sfx.tick(); haptic('warning'); }
}
setInterval(tickTimer, 250);

/* ---------- رویدادها ---------- */
async function play(e) {
  const g = G();
  if (e.t === 'move') {
    vpos[e.c] = e.to; placePawn(e.c); hop(e.c);
    sfx.step(); if (e.jump) haptic('light');
    await sleep(isMe(e.c) ? 120 : 330); return;
  }
  if (e.t === 'wall') {
    if (!vwalls.some(w => wkey(w[0], w[1], w[2]) === wkey(...e.w))) { vwalls.push([...e.w, e.c]); addWall([...e.w, e.c], true); sfx.enter(); }
    if (!isMe(e.c)) flashMsg(`${nameH(e.c)} دیوار گذاشت`);
    await sleep(isMe(e.c) ? 120 : 300); return;
  }
  if (e.t === 'timeout') { if (WATCH) return; flashMsg(isMe(e.c) ? 'وقتت تموم شد و یه قدم جات برداشتیم' : `${nameH(e.c)} دیر کرد`, true); return; }
  if (e.t === 'leave' && !isMe(e.c)) { toast(`${nameOf(e.c)} ${e.why === 'timeout' ? 'غایب بود' : 'بازیو ول کرد و رفت'}${g && g.n === 4 ? ' و ربات جاش بازی می‌کنه' : ''}`); return; }
  if (e.t === 'win') { const el = els.pawns[e.c]; if (el) el.classList.add('win'); }
}
function syncFrom(g) {
  for (const s of g.order) { const p = g.players[s].pos; if (!vpos[s] || vpos[s][0] !== p[0] || vpos[s][1] !== p[1]) { vpos[s] = p; placePawn(s); } }
  const keys = new Set(g.walls.map(w => wkey(w[0], w[1], w[2])));
  for (const k of Object.keys(els.walls)) if (!keys.has(k)) { els.walls[k].remove(); delete els.walls[k]; }
  vwalls = g.walls.map(w => w.slice());
  for (const w of vwalls) addWall(w, false);
}

/* ---------- حرکت و دیوار من ---------- */
async function doMove(m) {
  if (!myTurnNow()) return;
  const prev = vpos[me];
  vpos[me] = m; placePawn(me); hop(me); sfx.step();
  $('board').querySelectorAll('.dv-dot').forEach(d => d.remove()); dotsKey = '';
  const ok = await act(() => GC.divar.move(mid, m[0], m[1], since));
  if (!ok) { vpos[me] = prev; placePawn(me); }
}
async function doWall(o, r, c) {
  const b = wallB(o, r, c), k = wkey(...b);
  vwalls.push([...b, me]); addWall(b, true); sfx.enter(); haptic('light');
  const ok = await act(() => GC.divar.wall(mid, b[0], b[1], b[2], since));
  if (!ok) { vwalls = vwalls.filter(w => wkey(w[0], w[1], w[2]) !== k); if (els.walls[k]) { els.walls[k].remove(); delete els.walls[k]; } }
}
// برای نمایش جای مجاز: وضعیت فعلی با مختصات سرور
function engineState() {
  const g = G();
  return { size: N, star: g.star, order: g.order, players: Object.fromEntries(g.order.map(s => [s, { pos: vpos[s] || g.players[s].pos }])), walls: vwalls };
}
document.querySelectorAll('.dv-slot').forEach(slot => slot.addEventListener('pointerdown', e => {
  const g = G(), mine = g && g.players[me];
  if (!myTurnNow() || !mine || mine.walls <= 0) {
    if (g && !g.over && !WATCH) flashMsg(!mine || mine.walls > 0 ? 'صبر کن نوبتت بشه' : 'دیوارات تموم شده و فقط می‌تونی حرکت کنی', true);
    return;
  }
  e.preventDefault();
  slot.setPointerCapture(e.pointerId);
  const o = slot.dataset.o, q = geo(), L = 2 * q.S + q.G, gw = o === 'h' ? L : q.T, gh = o === 'h' ? q.T : L;
  const lift = e.pointerType === 'mouse' ? 0 : 48;
  const ghost = document.createElement('i'); ghost.className = 'dv-wall dv-ghost ' + o;
  ghost.style.width = gw + 'px'; ghost.style.height = gh + 'px'; document.body.appendChild(ghost);
  const pv = $('pv'); let key = null, ok = false;
  const at = ev => {
    const br = $('board').getBoundingClientRect(), x = ev.clientX, y = ev.clientY - lift;
    ghost.style.transform = `translate(${x - gw / 2}px,${y - gh / 2}px) scale(1.08)`;
    const bx = x - br.left, by = y - br.top;
    if (bx < -q.S || by < -q.S || bx > W + q.S || by > W + q.S) { key = null; pv.hidden = true; ghost.style.opacity = 1; return; }
    const cl = v => Math.max(1, Math.min(N - 1, Math.round((v - q.P + q.G / 2) / (q.S + q.G))));
    const i = cl(bx), j = cl(by), k = wkey(o, j - 1, i - 1);
    if (k !== key) {
      key = k; ok = !E.wallError(engineState(), ...wallB(o, j - 1, i - 1));
      pv.className = 'dv-pv dv-wall ' + o + (ok ? '' : ' bad'); setRect(pv, wallRect(o, j - 1, i - 1));
      if (ok) haptic('light');
    }
    pv.hidden = false; ghost.style.opacity = .3;
  };
  at(e);
  const mv = ev => at(ev);
  const up = () => {
    slot.removeEventListener('pointermove', mv); slot.removeEventListener('pointerup', up); slot.removeEventListener('pointercancel', up);
    pv.hidden = true;
    if (key && ok) { ghost.remove(); const [, oo, r, c] = key.match(/^([hv])(\d+),(\d+)$/); doWall(oo, +r, +c); return; }
    if (key && !ok) { flashMsg('اینجا نمی‌شه داش یا می‌افته رو یه دیوار دیگه یا راه یکیو کامل می‌بنده', true); sfx.error(); }
    const sr = slot.getBoundingClientRect();
    ghost.classList.add('back'); ghost.style.transform = `translate(${sr.left + sr.width / 2 - gw / 2}px,${sr.top + sr.height / 2 - gh / 2}px) scale(.7)`; ghost.style.opacity = 0;
    setTimeout(() => ghost.remove(), 260);
  };
  slot.addEventListener('pointermove', mv); slot.addEventListener('pointerup', up); slot.addEventListener('pointercancel', up);
}));

/* ---------- گفتگو: نوار پایین و پیام های شناور مثل بیلیارد (tchat.js) ---------- */
const QUICK = ['سلام!', 'خوش‌بازی!', 'عجب دیواری!', 'راهمو بستی 😅', 'زود باش', 'یه دست دیگه؟'];
const chat = TChat.init({
  bar: $('chatbar'), quick: QUICK, face: m => face(m, colorOf(m.color).pc),
  canSend: () => mid && !WATCH,
  send: async text => { await GC.divar.chat(mid, text); return (await GC.divar.match(mid, since, chat.last())).chat; },
  onNew: () => sfx.tap(), onError: e => { sfx.error(); toast(errText(e)); },
});
const chatIn = (list, quiet) => chat.add(list, quiet);

/* ---------- همگام سازی با سرور ---------- */
async function apply(next, anim = true) {
  if (next && next.chat && !overShown && next.status !== 'over' && next.status !== 'cancelled') chatIn(next.chat);
  if (next && next.status === 'cancelled') return cancelled();
  if (!next || !next.game) return;
  next.game._at = Date.now();   // زمان رسیدن پاسخ: مهلت و «آماده» از همین لحظه حساب می شوند، نه بعد از انیمیشن
  busy = true;
  try {
    const first = !snap;
    snap = Object.assign({}, snap || {}, next);
    const g = next.game;
    N = g.size; rot = WATCH ? 0 : ROT[me] || 0;
    if (first) { for (const s of g.order) vpos[s] = g.players[s].pos; vwalls = g.walls.map(w => w.slice()); }
    build(false);
    const evs = (g.events || []).filter(e => e.seq > since).sort((a, b) => a.seq - b.seq);
    for (const e of evs) { if (anim) await play(e); since = e.seq; }
    since = Math.max(since, g.seq);
    syncFrom(g);
    if (g.over && g.winner && els.pawns[g.winner]) els.pawns[g.winner].classList.add('win');
  } finally { busy = false; }
  renderAll(G());
  if (next.status === 'over' && !overShown) { overShown = true; setTimeout(() => over(next), 900); }
}
function pollMs() { const g = G(); if (!g || g.over) return 1500; return g.turn && g.turn !== me ? 700 : 1500; }
async function poll() {
  clearTimeout(pollT);
  if (document.hidden || overShown) { pollT = setTimeout(poll, pollMs()); return; }
  if (!busy && !acting) {
    try { await apply(await GC.divar.match(mid, since, chat.last())); }
    catch (e) { if (e.code === 'not_found') return noMatch(); }
  }
  pollT = setTimeout(poll, pollMs());
}
async function act(fn) {
  if (acting) return false;
  acting = true; renderDots(); renderTray(G());
  try { const res = await fn(); acting = false; await apply(res); return true; }
  catch (e) { acting = false; sfx.error(); haptic('error'); toast(errText(e)); if (G()) renderAll(G()); return false; }
  finally { acting = false; }
}
document.addEventListener('visibilitychange', () => { if (!document.hidden) poll(); });

/* ---------- پایان، خروج ---------- */
const TROPHY = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 21h8M12 17v4M7 4h10v5a5 5 0 0 1-10 0z"/><path d="M17 5h3v2a3 3 0 0 1-3 3M7 5H4v2a3 3 0 0 0 3 3"/></svg>';
function over(v) {
  const g = v.game;
  if (WATCH) { sfx.win(); return GC.watchOver('divar', 'بازی تموم شد', g.winner == null ? 'بازی بی برنده بسته شد' : `${nameH(g.winner)} اول رسید و برد`); }
  chat.end();
  const r = v.result || {}, won = !!r.won;
  GC.guardClose(false); store.set('dmid', null);
  won ? (sfx.win(), haptic('success')) : (sfx.lose(), haptic('warning'));
  const secs = Math.max(0, Math.round(Date.now() / 1000 - g.started)), st = g.stats || { moves: 0, walls: 0 };
  const ended = g.winner == null, left = g.n === 2 && Object.values(g.players).some(p => !p.me && p.out);
  sheet(`<div class="dv-res">
      <span class="ic${won ? '' : ' lost'}">${TROPHY}</span>
      <h2>${ended ? 'بازی تموم شد' : won ? (left ? 'حریف رفت و تو بردی!' : 'اول رسیدی و بردی!') : `${nameH(g.winner)} زودتر رسید`}</h2>
      ${v.cfg.mode === 'free' ? `<p>${won ? 'بازی دوستانه بود و جام و سکه نداشت ولی دمت گرم' : 'بازی دوستانه بود و چیزی از دست ندادی'}</p>` : GC.rankResult(v, ended)}
      <div class="facts"><div><b>${FD(st.moves)}</b><span>قدم</span></div><div><b>${FD(st.walls)}</b><span>دیوار گذاشتی</span></div><div><b>${FD(Math.floor(secs / 60))}:${FD(String(secs % 60).padStart(2, '0'))}</b><span>مدت بازی</span></div></div>
    </div>
    <a class="btn btn-block" href="divar-lobby.html">یه دست دیگه</a>
    <a class="btn btn-light btn-block" href="index.html">خونه</a>`, { center: true, dismiss: false });
  GC.refreshMe().catch(() => {});
}
function cancelled() {
  if (overShown) return;
  overShown = true;
  if (WATCH) { GC.watchOver('divar', 'این بازی بسته شد', 'بازی قبل از اینکه تموم شه بسته شد'); return; }
  chat.end(); GC.guardClose(false); store.set('dmid', null); GC.refreshMe().catch(() => {});
  sheet(`<div class="dlg" role="alertdialog" aria-labelledby="dT" aria-describedby="dD"><span class="dlg-ic">${icon('table')}</span>
      <h2 id="dT">این بازی بسته شد</h2><p id="dD">پشتیبانی این بازیو بست و جام کسی کم نشد</p>
      <div class="dlg-acts"><a class="btn" href="divar-lobby.html">بازی تازه</a><a class="btn btn-light" href="index.html">خونه</a></div></div>`, { center: true, dismiss: false });
}
function noMatch() {
  if (watchMid) { GC.watchOver('divar', 'این بازیو نمی‌شه دید', 'بازی یا تموم شده یا هنوز شروع نشده'); return; }
  store.set('dmid', null);
  sheet(`<div class="dlg" role="alertdialog" aria-labelledby="dT" aria-describedby="dD"><span class="dlg-ic">${icon('table')}</span>
      <h2 id="dT">بازی‌ای پیدا نشد</h2><p id="dD">این بازی یا تموم شده یا هنوز تو هیچ بازی‌ای نیستی</p>
      <div class="dlg-acts"><a class="btn" href="divar-lobby.html">شروع بازی</a><a class="btn btn-light" href="index.html">خونه</a></div></div>`, { center: true, dismiss: false });
}
function askExit() {
  if (!snap || snap.status === 'over' || WATCH) { location.href = 'index.html'; return; }
  const stake = snap.cfg.mode !== 'free', four = G() && G().n === 4;
  const sh = sheet(`<div class="dlg" role="alertdialog" aria-labelledby="dT" aria-describedby="dD">
      <span class="dlg-ic warn">${icon('exit')}</span>
      <h2 id="dT">می‌خوای بری؟</h2>
      <p id="dD">${four ? 'بری یعنی باختی و ربات تا آخر جات بازی می‌کنه' : 'بری یعنی همین بازیو باختی و حریف می‌بره'}</p>
      <div class="dlg-note">${stake ? 'بازی رتبه‌ایه و رفتنت یعنی باخت و کم شدن جام' : 'بازی دوستانه‌ست و چیزی از دست نمی‌دی'}</div>
      <div class="dlg-acts"><button class="btn" data-close>ادامهٔ بازی</button><button class="btn btn-danger-soft" id="leave">${icon('exit')}خروج</button></div>
      <button class="btn btn-light btn-block dlg-home" id="home">${icon('home')}فعلاً برو خونه بازی سر جاش می‌مونه</button>
      <p class="dlg-fine">بازی تو صفحهٔ خونه می‌مونه و با یه لمس برمی‌گردی<br>تا نیستی وقت هر نوبتت که تموم شه یه قدم به جات برداشته می‌شه${stake ? '<br>تو بازی رتبه‌ای سه نوبت غیبت پشت‌سرهم یعنی باخت' : ''}</p>
    </div>`, { center: true });
  sh.querySelector('#home').onclick = () => { GC.guardClose(false); location.href = 'index.html'; };
  sh.querySelector('#leave').onclick = async () => {
    try { await GC.divar.leave(mid); } catch (e) {}
    GC.guardClose(false); store.set('dmid', null); location.href = 'index.html';
  };
}
$('exit').onclick = askExit;
GC.back(askExit);
// میز: همهٔ تم ها رایگان؛ همان لحظه عوض می شود و برای بازی های بعد هم می ماند
DVThemes.apply(document.body, DVThemes.get());
$('look').onclick = () => {
  const draw = sh => { sh.querySelector('.dv-looks').innerHTML = DVThemes.LIST.map(t => `<button class="dv-look" data-look="${t.id}" aria-pressed="${DVThemes.get() === t.id}">${DVThemes.mini(t.id)}<b>${t.name}</b></button>`).join(''); };
  const sh = GC.sheet(`${GC.sheetHead('میز')}<div class="dv-looks"></div>`);
  draw(sh);
  sh.querySelector('.dv-looks').onclick = e => {
    const b = e.target.closest('[data-look]'); if (!b) return;
    DVThemes.set(b.dataset.look); DVThemes.apply(document.body, b.dataset.look); sfx.tap(); draw(sh);
  };
};
const sndBtn = $('snd');
const syncSnd = () => { sndBtn.innerHTML = icon(S.sound ? 'soundOn' : 'soundOff'); sndBtn.setAttribute('aria-pressed', String(!!S.sound)); sndBtn.setAttribute('aria-label', S.sound ? 'خاموش کردن صدا' : 'روشن کردن صدا'); };
sndBtn.onclick = () => { setSound(!S.sound); syncSnd(); if (S.sound) GC.loadSamples(); };
syncSnd();
document.addEventListener('pointerdown', () => GC.loadSamples(), { once: true });
GC.onFit(fit);   // فقط وقتی اندازهٔ صفحه واقعا عوض شد؛ باز شدن کیبورد گفتگو بازی را دوباره نمی چیند

/* ---------- شروع ---------- */
async function start() {
  GC.portrait(true);
  let first;
  try { first = await GC.divar.match(mid, 0, 0); }
  catch (e) { return e.code === 'not_found' ? noMatch() : (toast(errText(e)), setTimeout(start, 2500)); }
  WATCH = !!first.watch;
  if (first.status === 'lobby') { if (watchMid) return noMatch(); location.href = 'divar-lobby.html'; return; }
  if (first.status === 'cancelled') return cancelled();
  mid = first.id; me = WATCH ? (first.game ? first.game.order[0] : '0') : first.me;
  // تماشاگر چیزی نمی نویسد: جای نوار پیام، برچسب «در حال تماشا»
  if (WATCH) { $('chatbar').innerHTML = '<button class="dv-say" id="chatBtn"></button>'; GC.watchPill(); } else store.set('dmid', mid);
  if (first.cfg.mode !== 'free' && first.status === 'playing') GC.guardClose(true);
  chatIn(first.chat, true);
  since = first.game ? first.game.seq : 0;
  fit();
  await apply(first, false); fit();
  poll();
}
start();

/* ---------- آموزش بار اول (نوبتت که برسد و وقت کم شود، کنار می رود) ---------- */
function tour() {
  const pawn = () => $('board').querySelector('.dv-pawn.me');
  const walls = () => { const g = G(); return g && g.players[me] ? g.players[me].walls : 10; };
  return {
    id: 'divar', name: 'دیوار', color: '#4C8DFF', ink: '#fff', help: 'help.html#hDivar',
    intro: 'یه مسابقهٔ فکری 🧠 زودتر از بقیه برس اون‌ور صفحه و با دیوار راه حریفو دراز کن',
    ready: () => !!(G() && !WATCH && !G().over && pawn()),
    turn: () => ({ mine: !!(G() && G().turn === me && !G().over), left: deadlineAt ? deadlineAt - Date.now() : null }),
    steps: [
      { el: pawn, title: 'مهرهٔ تو آبیه', text: 'تو همیشه از <b>پایین صفحه</b> شروع می‌کنی و باید زودتر از بقیه برسی به <b>ضلع روبه‌رو</b><br>لبهٔ مقصد هر کی به رنگ خودشه', pad: 12, round: 999 },
      { el: '#board', title: 'یه قدم برو', text: 'نوبتت که شد بزن رو یکی از <b>خونه‌های روشن</b> کنار مهره‌ت تا یه خونه بری<br>اگه مهرهٔ کسی درست کنارت باشه از روش می‌پری', hand: 'tap', at: [0.5, 0.82] },
      { el: '#tray', title: 'یا دیوار بذار', text: () => `به جای قدم یه دیوار <b>افقی یا عمودی</b> از این سینی بردار و بذارش رو شیار بین خونه‌ها<br>${FD(walls())} تا دیوار داری پس حساب‌شده خرجشون کن!`, hand: { type: 'drag', from: [0.3, 0.5], to: [0.45, -2.2] } },
      { el: '#board', title: 'قانون دیوار', text: 'هر دیوار <b>دو تا خونه</b> رو می‌پوشونه و دیگه برداشته نمی‌شه<br>دیوارا رو هم نمی‌افتن و <b>نباید راه کسیو کامل ببندن</b> و جای غیرمجاز قرمز می‌شه' },
      { el: '#players', title: 'نوبت و وقت', text: 'تایمر بالا سر کسیه که نوبتشه<br>وقتت تموم بشه یه قدم تو کوتاه‌ترین راه خودکار برات برداشته می‌شه' },
      { el: '#chatbar', title: 'با بقیه حرف بزن', text: 'پیام سریع یا یه متن کوتاه بفرست' },
    ],
  };
}
GCTour.auto(tour());
$('help').onclick = () => GCTour.start(tour());
})();
