/* صفحهٔ بازی مار و پله. وضعیت و تاس از سرور می آید (game_club/snakes.py)؛ این صفحه فقط نشان می دهد و
   «تاس بریز» را می فرستد. هر رویداد roll این طور نمایش داده می شود: چرخیدن تاس، پریدن مهره خانه به خانه،
   بعد سرخوردن روی بدن همان مار یا بالا رفتن از نردبان. زمان بندی همان زمان بندی سرور است (snakes.py: DICE_T، STEP_T، SLIDE_T). */
(() => {
const { FD, fa, store, S, setSound, icon, sheet, toast, sfx, haptic, sleep, errText, face, amount } = GC;
const $ = id => document.getElementById(id);
const B = SNBoard;
// رنگ ثابت هر صندلی: زرد، آبی، قرمز، سبز (سازندهٔ میز همیشه زرد)
const COL = { 0: '#FFC531', 1: '#4C8DFF', 2: '#FF5A6A', 3: '#2FC584' };
const PIPS = { 1: [4], 2: [0, 8], 3: [0, 4, 8], 4: [0, 2, 6, 8], 5: [0, 2, 4, 6, 8], 6: [0, 2, 3, 5, 6, 8] };
const DICE_MS = 700, STEP_MS = 170, SLIDE_MS = 950;
const SVG = {
  snake: '<svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M18 5c2 1 2 4-1 5L7 13c-3 1-3 4-1 5s4 0 5 0"/><path d="M18 5h-2"/><path d="M11 18h3"/></svg>',
  ladder: '<svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.4" stroke-linecap="round"><path d="M8 3v18M16 3v18M8 7h8M8 12h8M8 17h8"/></svg>',
  six: '<svg viewBox="0 0 24 24" fill="#2a1b02"><circle cx="8" cy="6.5" r="2"/><circle cx="16" cy="6.5" r="2"/><circle cx="8" cy="12" r="2"/><circle cx="16" cy="12" r="2"/><circle cx="8" cy="17.5" r="2"/><circle cx="16" cy="17.5" r="2"/></svg>',
  arrow: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round"><path d="M19 12H5"/><path d="M10 7l-5 5 5 5"/></svg>',
  trophy: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 21h8M12 17v4M7 4h10v5a5 5 0 0 1-10 0z"/><path d="M17 5h3v2a3 3 0 0 1-3 3M7 5H4v2a3 3 0 0 0 3 3"/></svg>',
};

const watchMid = GC.watchId();
let WATCH = false;
let mid = watchMid || store.get('snmid', null), me = '0', snap = null, since = 0, busy = false, acting = false, pollT = null, overShown = false;
let W = 0, readyAt = 0, deadlineAt = 0, turnMs = 15000, warned = false, lastTurn = null, spunAt = 0, drawn = '';
// کسی که رویداد تاسش همین الان نمایش داده می شود؛ تا تمام شدن انیمیشن، صندلی و نوار پایین مال اوست نه نوبت بعدی
let animC = null;
const vpos = {}, els = {}, moving = new Set();
const G = () => snap && snap.game;
const isMe = c => c === me && !WATCH;
const nameOf = c => isMe(c) ? 'تو' : (G() && G().players[c] ? G().players[c].name : 'حریف');

/* ---------- صفحه و مهره ها ---------- */
const cs = () => W / 10;
const pw = () => Math.round(cs() * .62);
function at(cell, seat, solo) {
  // چند مهره در یک خانه کمی کنار هم می ایستند
  const [ux, uy] = B.cell(cell), c = cs(), p = pw();
  let ox = 0, oy = 0;
  if (!solo) {
    const here = (G() ? G().order : []).filter(s => vpos[s] === cell && !moving.has(s));
    if (here.length > 1) { const k = here.indexOf(seat), O = [[-.2, -.14], [.2, -.14], [-.2, .16], [.2, .16]][Math.max(0, k)]; ox = O[0] * c; oy = O[1] * c; }
  }
  return [ux * c + ox - p / 2, uy * c + oy - p * .78];
}
const tf = ([x, y], lift = 0, sc = 1) => `translate(${x.toFixed(1)}px,${(y - lift).toFixed(1)}px) scale(${sc})`;
function placeAll() { for (const s of Object.keys(els)) if (!moving.has(s)) els[s].style.transform = tf(at(vpos[s], s)); }
function fit() {
  const g = G(); if (!g) return;
  const r = $('arena').getBoundingClientRect();
  const w = Math.floor(Math.max(220, Math.min(r.width - 20, r.height - 20, 560)) - 14);
  const sig = w + '|' + JSON.stringify(g.snakes) + JSON.stringify(g.ladders);
  if (sig === drawn) return;
  drawn = sig; W = w;
  B.draw($('cv'), W, g.snakes, g.ladders);
  const L = $('layer'); L.style.width = L.style.height = W + 'px'; L.style.setProperty('--pw', pw() + 'px');
  placeAll();
}
function build(g) {
  const L = $('layer');
  for (const s of g.order) {
    if (els[s]) continue;
    const el = document.createElement('div'); el.className = 'sn-pawn'; el.style.setProperty('--pc', COL[s]);
    el.innerHTML = '<i class="sh"></i><i class="rg"></i><i class="bd"></i><i class="hd"></i>';
    L.appendChild(el); els[s] = el;
  }
  if (!$('tgt')) { const t = document.createElement('div'); t.id = 'tgt'; t.className = 'sn-target'; L.appendChild(t); }
}
// حرکت روی چند نقطه (کادرهای Web Animations؛ فقط transform)
function run(el, frames, ms, easing = 'linear') {
  return new Promise(res => {
    const a = el.animate(frames.map(f => ({ transform: f })), { duration: ms, easing, fill: 'forwards' });
    a.onfinish = () => { el.style.transform = frames[frames.length - 1]; a.cancel(); res(); };
    a.oncancel = () => res();
  });
}
async function hop(s, from, to) {
  const el = els[s]; moving.add(s);
  for (let n = from + 1, i = 0; n <= to; n++, i++) {
    const a = at(n - 1, s, true), b = at(n, s, true), m = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
    sfx.step(i);
    await run(el, [tf(a), tf(m, cs() * .38, 1.08), tf(b)], STEP_MS, 'ease-in-out');
    vpos[s] = n;
  }
  moving.delete(s);
}
async function slide(s, from, to, via) {
  const el = els[s]; moving.add(s);
  let pts;
  if (via === 'snake') {
    const P = B.snakePath(from, to), step = Math.max(1, Math.floor(P.length / 24)), c = cs(), p = pw();
    pts = P.filter((_, i) => i % step === 0 || i === P.length - 1).map(([x, y]) => tf([x * c - p / 2, y * c - p * .78]));
  } else {
    const a = at(from, s, true), b = at(to, s, true);
    pts = [0, .25, .5, .75, 1].map(k => tf([a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k], Math.sin(k * Math.PI) * cs() * .15));
  }
  await run(el, pts, SLIDE_MS, via === 'snake' ? 'ease-in' : 'ease-in-out');
  vpos[s] = to; moving.delete(s);
}
function target(cell) {
  const t = $('tgt'); if (!t) return;
  if (!cell) { t.classList.remove('on'); return; }
  const [ux, uy] = B.cell(cell), c = cs();
  Object.assign(t.style, { width: c * .92 + 'px', height: c * .92 + 'px', transform: `translate(${ux * c - c * .46}px,${uy * c - c * .46}px)` });
  t.classList.add('on');
}

/* ---------- تاس ---------- */
const die = $('die');
die.innerHTML = '<i></i>'.repeat(9);
const faceDie = v => [...die.children].forEach((e, i) => e.classList.toggle('on', (PIPS[v] || PIPS[1]).includes(i)));
faceDie(6);
let spinId = 0;
async function spin(v) {
  const id = ++spinId;
  die.classList.remove('roll'); void die.offsetWidth; die.classList.add('roll'); sfx.dice();
  for (let i = 0; i < 8; i++) { if (id !== spinId) return; faceDie(1 + Math.floor(Math.random() * 6)); await sleep(DICE_MS / 9); }
  if (v && id === spinId) faceDie(v);
}
die.addEventListener('animationend', () => die.classList.remove('roll'));

/* ---------- نمایش ---------- */
let popT = null;
function pop(kind, title, from, to, ms = 1500) {
  const el = $('pop'); clearTimeout(popT);
  el.className = 'sn-pop ' + kind;
  el.innerHTML = `<span class="ic">${SVG[kind] || SVG.six}</span><b>${title}</b>${from != null ? `<span class="ft"><span style="color:#9FB0D6">${FD(from)}</span><span style="color:${kind === 'snake' ? '#FF8FA3' : '#7CF29A'}">${SVG.arrow}</span><span style="color:${kind === 'snake' ? '#FF8FA3' : '#7CF29A'}">${FD(to)}</span></span>` : ''}`;
  el.hidden = false; void el.offsetWidth; el.classList.add('in');
  popT = setTimeout(() => { el.hidden = true; }, ms);
}
function feed(text, kind = '') { const f = $('feed'); f.textContent = text; f.className = 'sn-pill' + (kind ? ' ' + kind : ''); }
function renderSeats(g) {
  const box = $('seats'); box.style.setProperty('--n', g.n);
  box.innerHTML = g.order.map(s => {
    const p = g.players[s], on = (animC != null ? animC : g.turn) === s && !g.over;
    return `<div class="sn-seat${on ? ' on' : ''}${p.out ? ' out' : ''}" data-s="${s}" style="--pc:${COL[s]}"><span class="tm"><i></i></span>${isMe(s) ? '<span class="me">تو</span>' : ''}
      ${face(p, COL[s])}<span class="nm">${isMe(s) ? 'خودت' : String(p.name || '').replace(/[<>&]/g, '')}</span><span class="ps">خونهٔ ${FD(vpos[s] || p.pos)}</span>
      <span class="pb"><i style="transform:scaleX(${((vpos[s] || p.pos) / 100).toFixed(3)})"></i></span></div>`;
  }).join('');
  for (const s of g.order) if (els[s]) { els[s].classList.toggle('turn', (animC != null ? animC : g.turn) === s && !g.over); els[s].classList.toggle('win', g.over && g.winner === s); }
  $('mode').textContent = `${FD(g.n)} نفره`;
}
function canRoll() { const g = G(); return !!(g && g.can_roll && !g.over && !WATCH && !busy && !acting && Date.now() >= readyAt - 150); }
let readyT = null;
function renderDock(g) {
  const mine = canRoll(), myTurn = g.turn === me && !WATCH && !g.over;
  die.disabled = !mine; die.classList.toggle('ask', mine);
  const t = $('dt'), sub = $('ds');
  t.classList.toggle('mine', myTurn);
  if (animC != null && !g.over) { t.classList.toggle('mine', isMe(animC)); t.textContent = isMe(animC) ? 'تاس تو' : `نوبت ${nameOf(animC)}`; sub.textContent = 'مهره داره می‌ره…'; }
  else if (g.over) { t.textContent = g.winner != null ? `${nameOf(g.winner)} برد!` : 'بازی تموم شد'; sub.textContent = ''; }
  else if (myTurn) { t.textContent = g.bonus ? 'باز نوبت توئه!' : 'نوبت توئه'; sub.textContent = mine ? 'روی تاس بزن تا بریزه' : 'یه لحظه…'; }
  else if (g.turn) { t.textContent = `نوبت ${nameOf(g.turn)}`; sub.textContent = g.players[g.turn].bot || g.players[g.turn].out ? 'داره تاس می‌ریزه…' : 'منتظر تاسشیم…'; }
  clearTimeout(readyT);
  if (myTurn && !mine && !busy && !acting && readyAt > Date.now()) readyT = setTimeout(() => G() && renderDock(G()), readyAt - Date.now() + 30);
}
function renderAll(g) { if (!g) return; renderSeats(g); renderDock(g); }
function syncFrom(g) { for (const s of g.order) if (!moving.has(s) && vpos[s] !== g.players[s].pos) vpos[s] = g.players[s].pos; placeAll(); }
function timers() {
  const g = G(), bar = $('tbar').parentNode, seat = document.querySelector('.sn-seat.on .tm');
  const live = !!(g && deadlineAt && !g.over);
  bar.classList.toggle('live', live && g.turn === me && !WATCH);
  if (seat) seat.classList.toggle('live', live);
  if (!live) return;
  const fr = Math.max(0, Math.min(1, (deadlineAt - Date.now()) / turnMs));
  $('tbar').style.transform = `scaleX(${fr.toFixed(3)})`;
  if (seat) { const i = seat.firstChild; i.style.transform = `scaleX(${fr.toFixed(3)})`; i.style.background = fr > .25 ? '' : '#e8503f'; }
  if (g.turn === me && !WATCH && fr < .3 && !warned) { warned = true; sfx.tick(); haptic('warning'); }
}
setInterval(timers, 250);

/* ---------- رویدادها ---------- */
async function play(e) {
  const g = G();
  if (e.t === 'start') { pop('six', 'بزن بریم! هر کی زودتر دقیقاً به ۱۰۰ برسه', null, null, 1400); return; }
  if (e.t === 'roll') {
    animC = e.c; renderSeats(g); renderDock(g);
    try { await showRoll(e, g); } finally { animC = null; }
    return;
  }
  if (e.t === 'turn') { if (isMe(e.c) && G() && !G().over) { sfx.turn(); haptic('light'); } return; }
  if (e.t === 'timeout') { if (isMe(e.c)) feed('وقتت تموم شد و خودمون جات تاس ریختیم', 'bad'); return; }
  if (e.t === 'leave' && !isMe(e.c)) { toast(`${nameOf(e.c)} ${e.why === 'timeout' ? 'غایب بود' : 'بازیو ول کرد و رفت'}${g && g.n > 2 ? ' و ربات جاش تاس می‌ریزه' : ''}`); return; }
  if (e.t === 'win') { if (els[e.c]) els[e.c].classList.add('win'); pop('six', isMe(e.c) ? 'رسیدی به ۱۰۰!' : `${nameOf(e.c)} رسید به ۱۰۰`, null, null, 1600); }
}
async function showRoll(e, g) {
  {
    const who = nameOf(e.c), mine = isMe(e.c);
    // تاس خودم از لحظهٔ لمس می چرخد؛ جواب سرور فقط عددش را رویش می نشاند
    if (Date.now() - spunAt < 1500 && mine) { await sleep(Math.max(0, DICE_MS - (Date.now() - spunAt))); spinId++; faceDie(e.v); }
    else await spin(e.v);
    if (e.v === 6) sfx.six();
    if (e.stay) {
      feed(mine ? `${FD(e.v)} آوردی ولی باید دقیقاً برسی ۱۰۰` : `${who} ${FD(e.v)} آورد ولی باید دقیقاً برسه ۱۰۰`, mine ? 'mine' : '');
      if (mine) { sfx.nomove(); haptic('warning'); }
      await sleep(STEP_MS * 2);
    } else {
      feed(mine ? `${FD(e.v)} آوردی` : `${who} ${FD(e.v)} آورد`, mine ? 'mine' : '');
      if (mine && e.via) target(e.mid);
      await hop(e.c, e.frm, e.mid);
      renderSeats(g);
      if (e.via) {
        await sleep(120); target(0);
        if (e.via === 'ladder') {
          sfx.ladder(); if (mine) haptic('success');
          pop('ladder', mine ? 'یوهو! رفتی بالا' : `${who} از نردبون رفت بالا`, e.mid, e.to);
          feed(mine ? `با نردبون از ${FD(e.mid)} رفتی ${FD(e.to)}` : `${who} با نردبون از ${FD(e.mid)} رفت ${FD(e.to)}`, 'good');
        } else {
          sfx.snake(); if (mine) { haptic('error'); const b = $('board'); b.classList.remove('hurt'); void b.offsetWidth; b.classList.add('hurt'); }
          pop('snake', mine ? 'آخ! مار نیشت زد' : `${who} رو مار نیش زد`, e.mid, e.to);
          feed(mine ? `مار از ${FD(e.mid)} پایینت آورد ${FD(e.to)}` : `مار ${who} رو از ${FD(e.mid)} آورد ${FD(e.to)}`, 'bad');
        }
        await slide(e.c, e.mid, e.to, e.via);
      }
      target(0);
    }
    if (e.bonus) { pop('six', mine ? 'شیش آوردی یه نوبت دیگه!' : `${who} شیش آورد و دوباره می‌ریزه`, null, null, 1100); }
    placeAll(); renderSeats(g);
    await sleep(120);
  }
}

/* ---------- گفتگو ---------- */
const QUICK = ['سلام!', 'خوش‌بازی!', 'شیش بیا!', 'اون مار مال من نبود 😅', 'زود باش', 'یه دست دیگه؟'];
const chat = TChat.init({
  btn: $('chatBtn'), badge: $('chatBadge'), quick: QUICK, face: m => face(m, COL[m.color] || '#FFFFFF'),
  rest: () => { const r = $('dock').getBoundingClientRect(); return r.height ? innerHeight - r.top + 8 : 140; },
  canSend: () => !!mid && !WATCH,
  send: async text => { await GC.snakes.chat(mid, text); return (await GC.snakes.match(mid, since, chat.last())).chat; },
  onNew: () => sfx.tap(), onError: e => { sfx.error(); toast(errText(e)); },
});
const chatIn = (list, quiet) => chat.add(list, quiet);

/* ---------- همگام سازی با سرور ---------- */
async function apply(next, anim = true) {
  if (next && next.chat && !overShown && next.status !== 'over' && next.status !== 'cancelled') chatIn(next.chat);
  if (next && next.status === 'cancelled') return cancelled();
  if (!next || !next.game) return;
  next.game._at = Date.now();   // مهلت و «آماده» از لحظهٔ رسیدن پاسخ حساب می شوند
  busy = true; renderDock(next.game);
  try {
    const first = !snap;
    snap = Object.assign({}, snap || {}, next);
    const g = next.game;
    if (first) for (const s of g.order) vpos[s] = g.players[s].pos;
    build(g); fit();
    const evs = (g.events || []).filter(e => e.seq > since).sort((a, b) => a.seq - b.seq);
    for (const e of evs) { if (anim) await play(e); since = e.seq; }
    since = Math.max(since, g.seq);
    syncFrom(g);
  } finally { busy = false; }
  const g = G();
  readyAt = g._at + (g.ready_ms || 0);
  const d = g.deadline_ms ? g._at + g.deadline_ms : 0;
  if (!d) deadlineAt = 0; else { if (!deadlineAt || Math.abs(d - deadlineAt) > 1500) warned = false; if (!deadlineAt || Math.abs(d - deadlineAt) > 700) deadlineAt = d; }
  turnMs = g.turn_ms || 15000;
  if (g.turn !== lastTurn) { lastTurn = g.turn; warned = false; }
  renderAll(g);
  if (next.status === 'over' && !overShown) { overShown = true; setTimeout(() => over(next), 1100); }
}
function pollMs() { const g = G(); if (!g || g.over) return 1500; return g.turn && g.turn !== me ? 650 : 1300; }
async function poll() {
  clearTimeout(pollT);
  if (document.hidden || overShown) { pollT = setTimeout(poll, pollMs()); return; }
  if (!busy && !acting) {
    try { await apply(await GC.snakes.match(mid, since, chat.last())); }
    catch (e) { if (e.code === 'not_found') return noMatch(); }
  }
  pollT = setTimeout(poll, pollMs());
}
async function roll() {
  if (!canRoll()) return;
  acting = true; die.disabled = true; die.classList.remove('ask');
  spunAt = Date.now(); spin(0);
  try { const res = await GC.snakes.roll(mid, since); acting = false; await apply(res); }
  catch (e) { acting = false; spunAt = 0; sfx.error(); haptic('error'); toast(errText(e)); if (G()) renderAll(G()); }
  finally { acting = false; }
}
die.onclick = roll;
document.addEventListener('visibilitychange', () => { if (!document.hidden) poll(); });

/* ---------- پایان، خروج ---------- */
function over(v) {
  const g = v.game;
  if (WATCH) { sfx.win(); return GC.watchOver('snakes', 'بازی تموم شد', g.winner == null ? 'بازی بی برنده بسته شد' : `${nameOf(g.winner)} اول رسید ۱۰۰ و برد`); }
  chat.end(); $('chatBtn').hidden = true;
  const r = v.result || {}, won = !!r.won;
  GC.guardClose(false); store.set('snmid', null);
  won ? (sfx.win(), haptic('success')) : (sfx.lose(), haptic('warning'));
  const secs = Math.max(0, Math.round(Date.now() / 1000 - g.started)), st = g.stats || { rolls: 0, ladders: 0, snakes: 0 };
  const stake = v.cfg.mode === 'stake', ended = g.winner == null, left = g.n === 2 && Object.values(g.players).some(p => !p.me && p.out);
  const rank = (g.ranking || g.order).map((s, i) => `<div class="${s === g.winner ? 'w' : ''}" style="--pc:${COL[s]}"><b class="k">${FD(i + 1)}</b><i></i><span>${isMe(s) ? 'خودت' : String(g.players[s].name || '').replace(/[<>&]/g, '')}</span><small>خونهٔ ${FD(g.players[s].pos)}</small></div>`).join('');
  sheet(`<div class="sn-res">
      <span class="ic${won ? '' : ' lost'}">${SVG.trophy}</span>
      <h2>${ended ? 'بازی تموم شد' : won ? (left ? 'حریف رفت و تو بردی!' : 'برنده شدی!') : `${nameOf(g.winner)} زودتر رسید`}</h2>
      ${stake ? (won ? `<div class="prize">${amount(r.prize || 0, 'lg')}</div><p>جایزه ریخت تو کیف امتیازت 🎉</p>` : ended ? '<p>ورودیا برگشت</p>' : `<p>ورودی این بازیو (${fa(r.lost || v.cfg.entry)} امتیاز) باختی فدای سرت</p>`)
        : `<p>${won ? 'اولین نفری بودی که دقیقاً رسید ۱۰۰ دمت گرم' : 'بازی آزاد بود و چیزی از دست ندادی'}</p>`}
      <div class="sn-rank">${rank}</div>
      <div class="facts"><div><b>${FD(st.rolls)}</b><span>بار تاس</span></div><div><b>${FD(st.ladders)}</b><span>نردبون</span></div><div><b>${FD(st.snakes)}</b><span>نیش مار</span></div><div><b>${FD(Math.floor(secs / 60))}:${FD(String(secs % 60).padStart(2, '0'))}</b><span>مدت</span></div></div>
    </div>
    <a class="btn btn-block" href="snakes-lobby.html">یه دست دیگه</a>
    <a class="btn btn-light btn-block" href="index.html">خونه</a>`, { center: true, dismiss: false });
  GC.refreshMe().catch(() => {});
}
function cancelled() {
  if (overShown) return;
  overShown = true;
  if (WATCH) { GC.watchOver('snakes', 'این بازی بسته شد', 'بازی قبل از اینکه تموم شه بسته شد'); return; }
  chat.end(); GC.guardClose(false); store.set('snmid', null); GC.refreshMe().catch(() => {});
  sheet(`<div class="dlg" role="alertdialog" aria-labelledby="dT" aria-describedby="dD"><span class="dlg-ic">${icon('table')}</span>
      <h2 id="dT">این بازی بسته شد</h2><p id="dD">پشتیبانی این بازیو بست و ورودی همه برگشت تو کیفشون</p>
      <div class="dlg-acts"><a class="btn" href="snakes-lobby.html">بازی تازه</a><a class="btn btn-light" href="index.html">خونه</a></div></div>`, { center: true, dismiss: false });
}
function noMatch() {
  if (watchMid) { GC.watchOver('snakes', 'این بازیو نمی‌شه دید', 'بازی یا تموم شده یا هنوز شروع نشده'); return; }
  store.set('snmid', null);
  sheet(`<div class="dlg" role="alertdialog" aria-labelledby="dT" aria-describedby="dD"><span class="dlg-ic">${icon('table')}</span>
      <h2 id="dT">بازی‌ای پیدا نشد</h2><p id="dD">این بازی یا تموم شده یا هنوز تو هیچ بازی‌ای نیستی</p>
      <div class="dlg-acts"><a class="btn" href="snakes-lobby.html">شروع بازی</a><a class="btn btn-light" href="index.html">خونه</a></div></div>`, { center: true, dismiss: false });
}
function askExit() {
  if (!snap || snap.status === 'over' || WATCH) { location.href = 'index.html'; return; }
  const stake = snap.cfg.mode === 'stake', many = G() && G().n > 2;
  const sh = sheet(`<div class="dlg" role="alertdialog" aria-labelledby="dT" aria-describedby="dD">
      <span class="dlg-ic warn">${icon('exit')}</span>
      <h2 id="dT">می‌خوای بری؟</h2>
      <p id="dD">${many ? 'بری یعنی باختی و ربات تا آخر بازی جات تاس می‌ریزه' : 'بری یعنی همین بازیو باختی و حریف می‌بره'}</p>
      <div class="dlg-note">${stake ? `ورودی ${amount(snap.cfg.entry)} برنمی‌گرده` : 'بازی آزاده و امتیازی از دست نمی‌دی'}</div>
      <div class="dlg-acts"><button class="btn" data-close>ادامهٔ بازی</button><button class="btn btn-danger-soft" id="leave">${icon('exit')}خروج</button></div>
      <button class="btn btn-light btn-block dlg-home" id="home">${icon('home')}فعلاً برو خونه بازی سر جاش می‌مونه</button>
      <p class="dlg-fine">بازی تو صفحهٔ خونه می‌مونه و با یه لمس برمی‌گردی<br>تا نیستی وقت هر نوبتت که تموم شه تاس به جات ریخته می‌شه${stake ? '<br>تو بازی امتیازی سه نوبت غیبت پشت‌سرهم یعنی باخت' : ''}</p>
    </div>`, { center: true });
  sh.querySelector('#home').onclick = () => { GC.guardClose(false); location.href = 'index.html'; };
  sh.querySelector('#leave').onclick = async () => {
    try { await GC.snakes.leave(mid); } catch (e) {}
    GC.guardClose(false); store.set('snmid', null); location.href = 'index.html';
  };
}
$('exit').onclick = askExit;
GC.back(askExit);
const sndBtn = $('snd');
const syncSnd = () => { sndBtn.innerHTML = icon(S.sound ? 'soundOn' : 'soundOff'); sndBtn.setAttribute('aria-pressed', String(!!S.sound)); sndBtn.setAttribute('aria-label', S.sound ? 'خاموش کردن صدا' : 'روشن کردن صدا'); };
sndBtn.onclick = () => { setSound(!S.sound); syncSnd(); };
syncSnd();
GC.onFit(fit);   // فقط وقتی اندازهٔ صفحه واقعا عوض شد؛ باز شدن کیبورد گفتگو صفحه را دوباره نمی کشد
document.fonts && document.fonts.ready.then(() => { drawn = ''; fit(); });

/* ---------- شروع ---------- */
async function start() {
  GC.portrait(true);
  let first;
  try { first = await GC.snakes.match(mid, 0, 0); }
  catch (e) { return e.code === 'not_found' ? noMatch() : (toast(errText(e)), setTimeout(start, 2500)); }
  WATCH = !!first.watch;
  if (first.status === 'lobby') { if (watchMid) return noMatch(); location.href = 'snakes-lobby.html'; return; }
  if (first.status === 'cancelled') return cancelled();
  mid = first.id; me = WATCH ? (first.game ? first.game.order[0] : '0') : first.me;
  if (WATCH) GC.watchPill(); else store.set('snmid', mid);
  if (first.cfg.mode === 'stake' && first.status === 'playing') GC.guardClose(true);
  chatIn(first.chat, true);
  since = first.game ? first.game.seq : 0;
  await apply(first, false);
  feed(WATCH ? 'داری بازی رو زنده می‌بینی' : 'هر کی زودتر دقیقاً به ۱۰۰ برسه می‌بره');
  poll();
}
start();

/* ---------- آموزش بار اول (نوبتت که برسد و وقت کم شود، کنار می رود) ---------- */
function tour() {
  return {
    id: 'snakes', name: 'مار و پله', color: '#f2c14e', ink: '#2a1b02', help: 'help.html#hSnakes',
    intro: 'تاس بریز و از خونهٔ ۱ برو بالا و هر کی زودتر دقیقاً برسه خونهٔ ۱۰۰ برده',
    ready: () => !!(G() && !WATCH && !G().over && els[me]),
    turn: () => ({ mine: !!(G() && G().turn === me && !G().over), left: deadlineAt ? deadlineAt - Date.now() : null }),
    steps: [
      { el: () => els[me], title: 'این مهرهٔ توئه', text: () => `مهرهٔ ${me === '0' ? 'زرد' : me === '1' ? 'آبی' : me === '2' ? 'قرمز' : 'سبز'} مال توئه و از خونهٔ <b>۱</b> شروع می‌کنی<br>خونه‌ها مارپیچ تا <b>۱۰۰</b> می‌رن بالا`, pad: 14, round: 999 },
      { el: '#die', title: 'تاس بریز', text: 'نوبتت که شد تاس طلایی می‌شه و بزن روش تا بریزه<br>مهره‌ت خودش همون‌قدر می‌ره جلو و <b>شیش</b> بیاری یه نوبت دیگه داری!', hand: 'tap' },
      { el: '#board', title: 'نردبون و مار', text: 'پای <b>نردبون</b> برسی می‌ری بالا و سر <b>مار</b> برسی تا دمش سُر می‌خوری پایین' },
      { el: '#board', title: 'دقیقاً ۱۰۰', text: 'برای بردن باید <b>دقیقاً</b> برسی ۱۰۰ و اگه تاس بیشتر از لازم بیاد همون‌جا می‌مونی' },
      { el: '#seats', title: 'نوبت و وقت', text: 'نوار طلایی بالا سر کسیه که نوبتشه<br>وقتت تموم بشه خودمون جات تاس می‌ریزیم' },
      { el: '#chatBtn', title: 'با بقیه حرف بزن', text: 'پیام سریع یا یه متن کوتاه بفرست', hand: 'tap' },
    ],
  };
}
GCTour.auto(tour());
$('help').onclick = () => GCTour.start(tour());
})();
