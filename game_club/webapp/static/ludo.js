/* منچ — نسخه پیش نمایش. در نسخه واقعی تاس، نوبت و حرکت مجاز روی سرور حساب می شود
   و این فایل فقط نمایش و ورودی کاربر را نگه می دارد (POST /api/ludo/roll و /move). */
(() => {
const { S, save, fa, FD, store, avatar, COL, pawn, pips, LUDO, sfx, setSound, sheet, sheetHead, toast, sleep, rand, ledger, icon, amount, mount } = GC;
const { TRACK, SEAT, ORDER, SOCKETS } = LUDO;
const SAFE = new Set(LUDO.SAFE);
const $ = id => document.getElementById(id);
const TURN_MS = 20000, STEP_MS = 165;

/* ---------- میز: از لابی، یا تمرین پیش فرض ---------- */
let M = store.get('match', null);
if (!M || !M.opp || !M.opp.length) M = { how: 'bot', stake: false, entry: 0, players: 2, pawns: 2, opp: [{ c: 'red', name: 'ربات سارا', av: 4 }] };

/* ---------- ساخت صفحه ---------- */
const STAR = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2.5l2.9 6 6.6.9-4.8 4.6 1.2 6.5L12 17.4l-5.9 3.1 1.2-6.5L2.5 9.4l6.6-.9z"/></svg>';
const ARROW = deg => `<svg viewBox="0 0 24 24" aria-hidden="true" style="transform:rotate(${deg}deg)"><path d="M8 5l11 7-11 7z" fill="#fff"/></svg>`;
function buildBoard() {
  const startOf = {}; for (const c of ORDER) startOf[SEAT[c].start] = c;
  let h = '';
  TRACK.forEach(([x, y], i) => {
    const c = startOf[i], at = `style="grid-column:${x + 1};grid-row:${y + 1}"`;
    h += c ? `<div class="tile start c-${c}" ${at}>${ARROW(SEAT[c].arrow)}</div>`
      : SAFE.has(i) ? `<div class="tile safe" ${at}>${STAR}</div>` : `<div class="tile" ${at}></div>`;
  });
  for (const c of ORDER) SEAT[c].lane.forEach(([x, y]) => { h += `<div class="tile lane c-${c}" style="grid-column:${x + 1};grid-row:${y + 1}"></div>`; });
  for (const c of ORDER) {
    const [x, y] = SEAT[c].yard;
    h += `<div class="yard c-${c}" data-yard="${c}" style="grid-column:${x + 1}/${x + 7};grid-row:${y + 1}/${y + 7}"><span class="panel"></span>${SOCKETS.map(([sx, sy]) => `<span class="sock" style="left:${sx / 6 * 100}%;top:${sy / 6 * 100}%"></span>`).join('')}<span class="who"></span></div>`;
  }
  h += `<div class="home"><svg viewBox="0 0 3 3" preserveAspectRatio="none" aria-hidden="true"><path d="M0 0L1.5 1.5L0 3z" fill="#2F7BF6"/><path d="M0 0L3 0L1.5 1.5z" fill="#EF4136"/><path d="M3 0L3 3L1.5 1.5z" fill="#2FB24C"/><path d="M0 3L3 3L1.5 1.5z" fill="#FFC226"/></svg><span class="home-mark">${icon('trophy', 2.4)}</span></div>`;
  h += '<div class="layer" id="layer"></div>';
  $('board').innerHTML = h;
}

/* ---------- موقعیت ها ---------- */
function posOf(c, p, k) {
  const s = SEAT[c];
  if (p < 0) return [s.yard[0] + SOCKETS[k][0], s.yard[1] + SOCKETS[k][1]];
  if (p <= 50) { const [x, y] = TRACK[(s.start + p) % 52]; return [x + .5, y + .5]; }
  if (p <= 55) { const [x, y] = s.lane[p - 51]; return [x + .5, y + .5]; }
  return s.fin;
}
const tIdx = (c, p) => p >= 0 && p <= 50 ? (SEAT[c].start + p) % 52 : -1;
const pct = v => (v / 15 * 100) + '%';

/* ---------- وضعیت ---------- */
let G = null;
function newGame() {
  const players = { yellow: { name: 'شما', av: 7, human: true } };
  M.opp.forEach(o => { players[o.c] = { name: o.name, av: o.av, human: false }; });
  const seats = ORDER.filter(c => players[c]);
  G = { id: {}, seats, players, stake: !!M.stake, entry: M.entry, pot: M.stake ? M.entry * seats.length : 0, nP: M.pawns,
    pawns: {}, els: {}, last: {}, turn: seats.indexOf('yellow'), sixes: 0, phase: 'start', misses: 0, t0: Date.now(),
    stats: { caps: 0, sixes: 0 } };
  const layer = $('layer'); layer.innerHTML = '';
  for (const c of seats) {
    G.pawns[c] = Array(M.pawns).fill(-1); G.els[c] = [];
    for (let k = 0; k < M.pawns; k++) {
      const el = document.createElement('button');
      el.className = 'pawn c-' + c; el.innerHTML = pawn(c); el.dataset.c = c; el.dataset.k = k;
      el.setAttribute('aria-label', `مهرهٔ ${COL[c].fa} ${FD(k + 1)}`);
      layer.appendChild(el); G.els[c].push(el);
    }
  }
  if (G.stake) { S.bal -= G.entry; S.spent += G.entry; ledger('ورودی منچ', -G.entry, 'entry'); save(); }
  $('modeTag').innerHTML = G.stake ? `جایزه ${amount(G.pot)}` : M.how === 'bot' ? 'تمرین' : 'آزاد';
  $('feed').innerHTML = '';
  renderSeats(); layout(); mount();
  return G;
}

/* ---------- نمایش ---------- */
function layout() {
  const groups = {};
  for (const c of G.seats) G.pawns[c].forEach((p, k) => {
    const [x, y] = posOf(c, p, k), key = x.toFixed(2) + ',' + y.toFixed(2);
    (groups[key] = groups[key] || []).push([c, k, x, y]);
  });
  for (const list of Object.values(groups)) list.forEach(([c, k, x, y], i) => {
    const el = G.els[c][k], n = list.length, off = n > 1 ? (i - (n - 1) / 2) * .36 : 0;
    el.style.left = pct(x + off); el.style.top = pct(y + (n > 1 ? .12 : 0));
    el.style.setProperty('--s', n > 1 ? .8 : 1);
    el.style.zIndex = Math.round(y * 10) + (el.classList.contains('can') ? 300 : 0);
  });
}
function renderSeats() {
  for (const c of ORDER) {
    const el = document.querySelector(`[data-seat="${c}"]`), pl = G.players[c];
    const yard = document.querySelector(`[data-yard="${c}"]`);
    yard.classList.toggle('off', !pl);
    yard.querySelector('.who').textContent = pl ? pl.name : 'خالی';
    el.classList.toggle('empty', !pl);
    if (!pl) { el.innerHTML = ''; continue; }
    const done = G.pawns[c].filter(p => p === 56).length;
    el.innerHTML = `<span class="avatar timer" style="--ring:var(--c)"><span>${avatar(pl.av)}</span></span>
      <div class="seat-txt" dir="rtl"><span class="seat-name">${pl.name}</span><span class="prog" title="مهره‌های رسیده">${G.pawns[c].map((_, i) => `<i class="${i < done ? 'done' : ''}"></i>`).join('')}</span></div>
      <span class="die sm c-${c}${G.last[c] ? '' : ' ghost'}">${pips(G.last[c] || 0)}</span>`;
  }
  markTurn();
}
function markTurn() {
  const cur = G.seats[G.turn];
  document.querySelectorAll('.seat').forEach(s => s.classList.toggle('turn', s.dataset.seat === cur && G.phase !== 'over'));
  document.querySelectorAll('.yard').forEach(y => y.classList.toggle('turn', y.dataset.yard === cur && G.phase !== 'over'));
  const tb = $('turnbar'); tb.className = 'turnbar c-' + cur;
  const pl = G.players[cur];
  $('turnTxt').textContent = G.phase === 'over' ? 'بازی تمام شد' : pl.human ? 'نوبت شماست' : 'نوبت ' + pl.name;
}
function dock(title, sub, state) {
  $('dockT').textContent = title; $('dockS').textContent = sub || '';
  const b = $('roll');
  b.setAttribute('aria-disabled', String(state !== 'roll'));
  b.classList.toggle('ask', state === 'roll');
}
function feed(c, text) {
  const f = $('feed'), d = document.createElement('div');
  d.className = 'c-' + c; d.innerHTML = `<i></i><span>${text}</span>`;
  f.prepend(d); while (f.children.length > 2) f.lastChild.remove();
}
function setDie(el, v) { el.innerHTML = pips(v); }

/* ---------- تایمر نوبت (فقط برای بازیکن انسانی) ---------- */
let tmr = null;
function startTimer(onEnd) {
  stopTimer(); const t0 = Date.now(), av = document.querySelector('[data-seat="yellow"] .avatar');
  let warned = false;
  tmr = setInterval(() => {
    const left = Math.max(0, 1 - (Date.now() - t0) / TURN_MS);
    $('timeBar').style.transform = `scaleX(${left})`; if (av) av.style.setProperty('--t', left);
    if (left < .25 && !warned) { warned = true; sfx.tick(); }
    if (!left) { stopTimer(); onEnd(); }
  }, 200);
}
function stopTimer() {
  clearInterval(tmr); tmr = null; $('timeBar').style.transform = 'scaleX(1)';
  document.querySelectorAll('.avatar.timer').forEach(a => a.style.setProperty('--t', 1));
}

/* ---------- قواعد ---------- */
function legal(c, d) { const out = []; G.pawns[c].forEach((p, k) => { if ((p < 0 && d === 6) || (p >= 0 && p + d <= 56)) out.push(k); }); return out; }
function danger(c, ti) {
  for (const o of G.seats) if (o !== c) for (const q of G.pawns[o]) {
    const oi = tIdx(o, q); if (oi < 0) continue;
    const dist = (ti - oi + 52) % 52; if (dist >= 1 && dist <= 6) return true;
  }
  return false;
}
function bestMove(c, d, moves) {
  let best = moves[0], bs = -1e9;
  for (const k of moves) {
    const p = G.pawns[c][k], np = p < 0 ? 0 : p + d, ti = tIdx(c, np), cur = tIdx(c, p);
    let s = np / 8 + Math.random() * 3;
    if (p < 0) s += 50;
    if (np === 56) s += 80;
    if (p <= 50 && np > 50) s += 35;
    if (ti >= 0) {
      if (SAFE.has(ti)) s += 15;
      else { for (const o of G.seats) if (o !== c && G.pawns[o].some(q => tIdx(o, q) === ti)) s += 100; if (danger(c, ti)) s -= 40; }
    }
    if (cur >= 0 && !SAFE.has(cur) && danger(c, cur)) s += 25;
    if (s > bs) { bs = s; best = k; }
  }
  return best;
}

/* ---------- حرکت ها ---------- */
async function rollAnim(c) {
  const el = G.players[c].human ? $('myDie') : document.querySelector(`[data-seat="${c}"] .die`);
  el.classList.remove('ghost'); el.classList.add('rolling'); sfx.dice();
  for (let i = 0; i < 8; i++) { setDie(el, 1 + rand(6)); await sleep(60); }
  const v = 1 + rand(6); // نسخه واقعی: عدد از سرور
  el.classList.remove('rolling'); setDie(el, v);
  G.last[c] = v;
  const small = document.querySelector(`[data-seat="${c}"] .die`); if (small) { small.classList.remove('ghost'); setDie(small, v); }
  if (v === 6) { sfx.six(); if (G.players[c].human) G.stats.sixes++; }
  return v;
}
function flash(c, x, y) {
  const f = document.createElement('span'); f.className = 'flash c-' + c; f.style.left = pct(x); f.style.top = pct(y);
  $('layer').appendChild(f); setTimeout(() => f.remove(), 600);
}
async function doMove(c, k, d) {
  const g = G, el = g.els[c][k];
  if (g.pawns[c][k] < 0) { g.pawns[c][k] = 0; sfx.enter(); layout(); await sleep(280); }
  else for (let i = 0; i < d; i++) {
    g.pawns[c][k]++; el.classList.remove('hop'); void el.offsetWidth; el.classList.add('hop'); sfx.step(i); layout();
    await sleep(STEP_MS); if (g !== G) return {};
  }
  const p = g.pawns[c][k], ti = tIdx(c, p), victims = [];
  if (ti >= 0 && !SAFE.has(ti)) for (const o of g.seats) if (o !== c) g.pawns[o].forEach((q, j) => { if (tIdx(o, q) === ti) victims.push([o, j]); });
  if (victims.length) {
    const [x, y] = posOf(c, p, k); flash(victims[0][0], x, y); sfx.capture();
    victims.forEach(([o, j]) => { g.pawns[o][j] = -1; });
    if (g.players[c].human) g.stats.caps += victims.length;
    await sleep(160); layout(); await sleep(320);
  }
  if (p === 56) { sfx.home(); const [x, y] = SEAT[c].fin; flash(c, x, y); }
  renderSeats();
  return { captured: victims.length ? victims : null, finished: p === 56, entered: d === 6 && p === 0 };
}
function clearHints() {
  for (const c of G.seats) G.els[c].forEach(e => e.classList.remove('can'));
  $('layer').querySelectorAll('.dest').forEach(e => e.remove());
}
function showHints(c, d, moves) {
  for (const k of moves) {
    G.els[c][k].classList.add('can');
    const p = G.pawns[c][k], np = p < 0 ? 0 : p + d, [x, y] = posOf(c, np, k);
    const m = document.createElement('button');
    m.className = 'dest c-' + c; m.dataset.k = k; m.style.left = pct(x); m.style.top = pct(y);
    m.setAttribute('aria-label', 'مقصد این مهره'); m.textContent = np === 56 ? '★' : '';
    $('layer').appendChild(m);
  }
  layout();
}

/* ---------- حلقه بازی ---------- */
async function loop(g) {
  while (g === G && g.phase !== 'over') {
    const c = g.seats[g.turn], pl = g.players[c];
    g.phase = pl.human ? 'roll' : 'bot'; markTurn();
    let d;
    if (pl.human) {
      $('myDie').classList.remove('ghost'); setDie($('myDie'), G.last.yellow || 0);
      sfx.turn();
      dock('نوبت شماست', g.sixes ? '۶ آورده بودی؛ یک تاس دیگر بریز' : 'روی تاس بزن تا بریزد', 'roll');
      const auto = await new Promise(res => { g.onRoll = () => res(false); startTimer(() => res(true)); });
      stopTimer(); g.onRoll = null; if (g !== G) return;
      if (auto) { g.misses++; feed(c, 'وقتت تمام شد؛ تاس خودکار ریخته شد'); if (g.misses >= 3 && g.stake) return forfeit('سه نوبت پشت‌سرهم غایب بودی'); }
      else g.misses = 0;
      g.phase = 'anim'; dock('در حال ریختن…', '', 'busy');
      d = await rollAnim(c);
    } else {
      dock('نوبت ' + pl.name, 'صبر کن تا تاس بریزد', 'busy');
      setDie($('myDie'), G.last.yellow || 0); $('myDie').classList.add('ghost');
      await sleep(650); if (g !== G) return;
      g.phase = 'anim'; d = await rollAnim(c);
    }
    if (g !== G) return;
    const moves = legal(c, d);
    if (!moves.length) {
      sfx.nomove();
      const why = g.pawns[c].every(p => p < 0) ? 'برای وارد کردن مهره ۶ لازم است' : 'عدد تاس برای هیچ مهره‌ای جا ندارد';
      if (pl.human) dock(FD(d) + ' آوردی', 'حرکتی نداری؛ ' + why, 'busy');
      feed(c, (pl.human ? FD(d) + ' آوردی' : pl.name + ' ' + FD(d) + ' آورد') + '؛ حرکتی ممکن نبود');
      await sleep(1000); advance(g, false, d); continue;
    }
    let k;
    const allYard = moves.every(m => g.pawns[c][m] < 0);
    if (pl.human && (moves.length > 1 && !allYard)) {
      g.phase = 'move';
      dock(FD(d) + ' آوردی', 'مهره‌ای را که بالا و پایین می‌پرد بزن؛ دایرهٔ خط‌چین مقصدش است', 'pick');
      showHints(c, d, moves);
      const r = await new Promise(res => { g.onPick = kk => res(kk); startTimer(() => res(-1)); });
      stopTimer(); g.onPick = null; clearHints(); if (g !== G) return;
      k = r < 0 ? bestMove(c, d, moves) : r;
      if (r < 0) { g.misses++; feed(c, 'وقتت تمام شد؛ بهترین حرکت انجام شد'); } else g.misses = 0;
    } else {
      k = pl.human ? moves[0] : bestMove(c, d, moves);
      if (pl.human) dock(FD(d) + ' آوردی', allYard && d === 6 ? 'یک مهره وارد بازی شد' : 'تنها حرکت ممکن انجام شد', 'busy');
      await sleep(pl.human ? 250 : 380);
    }
    g.phase = 'anim';
    const r = await doMove(c, k, d);
    if (g !== G) return;
    const who = pl.human ? 'تو' : pl.name;
    if (r.captured) feed(c, pl.human ? `مهرهٔ ${g.players[r.captured[0][0]].name} را زدی! یک نوبت اضافه` : r.captured[0][0] === 'yellow' ? `${pl.name} مهرهٔ تو را زد و به لانه برگرداند` : `${pl.name} مهرهٔ ${g.players[r.captured[0][0]].name} را زد`);
    else if (r.finished) feed(c, `${who} یک مهره به مرکز رساند${pl.human ? 'ی' : ''}! یک نوبت اضافه`);
    else if (r.entered) feed(c, `${who} ۶ آورد${pl.human ? 'ی' : ''} و مهره وارد کرد${pl.human ? 'ی' : ''}`);
    if (g.pawns[c].every(p => p === 56)) return over(c);
    advance(g, d === 6 || !!r.captured || r.finished, d);
  }
}
function advance(g, extra, d) {
  g.sixes = d === 6 ? g.sixes + 1 : 0;
  if (g.sixes >= 3) { feed(g.seats[g.turn], 'سه بار ۶ پشت‌سرهم؛ نوبت سوخت'); g.sixes = 0; g.turn = (g.turn + 1) % g.seats.length; return; }
  if (extra) return;
  g.sixes = 0; g.turn = (g.turn + 1) % g.seats.length;
}

/* ---------- پایان ---------- */
function over(c, reason) {
  G.phase = 'over'; stopTimer(); markTurn(); dock('بازی تمام شد', '', 'busy');
  const pl = G.players[c], me = pl.human;
  S.games++;
  if (me) { S.wins++; if (G.stake) { S.bal += G.pot; S.won += G.pot; ledger('جایزهٔ منچ', G.pot, 'prize'); } }
  save(); me ? sfx.win() : sfx.lose();
  const secs = Math.round((Date.now() - G.t0) / 1000);
  const sh = sheet(`<div class="result">
      <div class="crown-pawn">${pawn(c, true).replace('viewBox="0 0 40 50"', 'viewBox="0 -4 40 54"')}</div>
      <h2>${me ? 'بردی!' : pl.name + ' برد'}</h2>
      ${reason ? `<p class="muted">${reason}</p>` : ''}
      ${G.stake ? `<div class="prize">${amount(me ? G.pot : G.entry, 'lg')}</div><p class="muted">${me ? 'جایزه به کیف امتیازت اضافه شد.' : 'ورودی این دست را باختی.'}</p>`
        : `<p class="muted">${me ? 'بازی آزاد بود و جایزه نداشت.' : 'بازی آزاد بود؛ چیزی از دست ندادی.'}</p>`}
      <div class="facts"><div><b>${FD(G.stats.caps)}</b><span>مهره زدی</span></div><div><b>${FD(G.stats.sixes)}</b><span>بار ۶ آوردی</span></div><div><b>${FD(Math.floor(secs / 60))}:${FD(String(secs % 60).padStart(2, '0'))}</b><span>مدت بازی</span></div></div>
    </div>
    <button class="btn btn-block" id="again">${icon('dice')}یک دست دیگر</button>
    <div class="choice-row"><a class="btn btn-light" href="ludo-lobby.html">میز جدید</a><a class="btn btn-light" href="index.html">خانه</a></div>`, { center: true, dismiss: false });
  sh.querySelector('#again').onclick = () => {
    if (M.stake && S.bal < M.entry) { sfx.error(); toast('امتیاز کافی برای ورودی نداری'); return; }
    GC.close(); start();
  };
}
function forfeit(reason) {
  const other = G.seats.find(c => c !== 'yellow');
  over(other, reason);
}

/* ---------- ورودی کاربر ---------- */
$('roll').onclick = () => { if (G && G.phase === 'roll' && G.onRoll) G.onRoll(); };
$('board').addEventListener('click', e => {
  if (!G || G.phase !== 'move' || !G.onPick) return;
  const t = e.target.closest('.pawn.can, .dest'); if (!t) return;
  if (t.classList.contains('pawn') && t.dataset.c !== 'yellow') return;
  G.onPick(+t.dataset.k);
});
document.addEventListener('keydown', e => { if ((e.key === ' ' || e.key === 'Enter') && G && G.phase === 'roll' && document.activeElement === document.body) { e.preventDefault(); G.onRoll && G.onRoll(); } });

const sndBtn = $('snd');
const syncSnd = () => { sndBtn.innerHTML = icon(S.sound ? 'soundOn' : 'soundOff'); sndBtn.setAttribute('aria-pressed', String(!!S.sound)); sndBtn.setAttribute('aria-label', S.sound ? 'خاموش کردن صدا' : 'روشن کردن صدا'); };
sndBtn.onclick = () => { setSound(!S.sound); syncSnd(); };
syncSnd();

$('rules').onclick = () => sheet(`${sheetHead('قوانین منچ')}
  <ul class="rules-mini">
    <li>تو <b>زرد</b> هستی (پایین چپ). مهره‌ها در جهت فلش‌ها می‌چرخند و از راهروی زرد به مرکز می‌رسند.</li>
    <li>فقط با <b>۶</b> مهره از لانه بیرون می‌آید.</li>
    <li>۶، زدن مهرهٔ حریف یا رسیدن به مرکز <b>یک نوبت اضافه</b> می‌دهد. سه بار ۶ پشت‌سرهم نوبت را می‌سوزاند.</li>
    <li>اگر دقیقاً روی مهرهٔ حریف بنشینی، به لانه‌اش برمی‌گردد. روی <b>ستاره</b> و خانهٔ شروع کسی زده نمی‌شود.</li>
    <li>هر نوبت <b>۲۰ ثانیه</b> وقت داری؛ بعدش تاس و حرکت خودکار انجام می‌شود.</li>
  </ul>
  <a class="btn btn-light btn-block" href="help.html">راهنمای کامل</a>`);

$('exit').onclick = () => {
  if (!G || G.phase === 'over') { location.href = 'index.html'; return; }
  const sh = sheet(`<h2 style="font-size:22px;font-weight:900">از بازی بیرون می‌روی؟</h2>
    <p class="muted">${G.stake ? `بازی با امتیاز است. خروج یعنی باخت و ${fa(G.entry)} امتیاز ورودی برنمی‌گردد.` : 'بازی آزاد است و چیزی از دست نمی‌دهی.'}</p>
    <button class="btn btn-danger btn-block" id="leave">بیرون برو</button>
    <button class="btn btn-light btn-block" data-close>ادامهٔ بازی</button>`, { center: true });
  sh.querySelector('#leave').onclick = () => { S.games++; save(); G = null; location.href = 'index.html'; };
};

/* ---------- آموزش بار اول ---------- */
function coach() {
  return new Promise(res => {
    const SL = [
      ['تو زرد هستی', 'لانهٔ تو پایین سمت چپ است. مهره‌هایت را دور صفحه ببر و به مرکز برسان.', `<svg viewBox="0 0 100 100"><rect x="6" y="6" width="88" height="88" rx="18" fill="#FFC226"/><rect x="22" y="22" width="56" height="56" rx="12" fill="#FFFDF6"/><g transform="translate(30 20) scale(1)">${pawn('yellow').replace(/^<svg[^>]*>|<\/svg>$/g, '')}</g></svg>`],
      ['روی تاس بزن', 'تاس پایین صفحه است. با ۶ یک مهره وارد بازی می‌شود و یک نوبت دیگر داری.', `<svg viewBox="0 0 100 100"><rect x="18" y="18" width="64" height="64" rx="16" fill="#FFC226"/><g fill="#fff"><circle cx="35" cy="35" r="6"/><circle cx="65" cy="35" r="6"/><circle cx="35" cy="50" r="6"/><circle cx="65" cy="50" r="6"/><circle cx="35" cy="65" r="6"/><circle cx="65" cy="65" r="6"/></g></svg>`],
      ['مهره را انتخاب کن', 'مهره‌ای که بالا و پایین می‌پرد قابل حرکت است. دایرهٔ خط‌چین نشان می‌دهد کجا می‌رود.', `<svg viewBox="0 0 100 100"><rect x="8" y="58" width="24" height="24" rx="6" fill="#FFFDF6" stroke="#D6E2CB" stroke-width="2"/><rect x="38" y="58" width="24" height="24" rx="6" fill="#FFFDF6" stroke="#D6E2CB" stroke-width="2"/><rect x="68" y="58" width="24" height="24" rx="6" fill="#FFFDF6" stroke="#D6E2CB" stroke-width="2"/><circle cx="80" cy="70" r="9" fill="rgba(255,255,255,.8)" stroke="#FFC226" stroke-width="3" stroke-dasharray="4 3"/><g transform="translate(6 18) scale(.7)">${pawn('yellow').replace(/^<svg[^>]*>|<\/svg>$/g, '')}</g><path d="M34 40c14-12 34-12 44 14" fill="none" stroke="#1C2A16" stroke-width="2.5" stroke-dasharray="4 4"/></svg>`],
    ];
    let i = 0;
    const draw = () => {
      const [t, d, svg] = SL[i];
      const sh = sheet(`<div class="coach"><div class="pic">${svg}</div><h2>${t}</h2><p class="muted">${d}</p><div class="dots">${SL.map((_, j) => `<i class="${j === i ? 'on' : ''}"></i>`).join('')}</div></div>
        <button class="btn btn-block" id="nx">${i < SL.length - 1 ? 'بعدی' : 'فهمیدم، شروع'}</button>
        <button class="btn btn-light btn-block" id="sk">${i < SL.length - 1 ? 'رد کردن آموزش' : 'قوانین کامل'}</button>`, { center: true, dismiss: false });
      sh.querySelector('#nx').onclick = () => { if (++i < SL.length) draw(); else { S.tutorial = true; save(); GC.close(); res(); } };
      sh.querySelector('#sk').onclick = () => { S.tutorial = true; save(); GC.close(); if (i === SL.length - 1) $('rules').click(); res(); };
    };
    draw();
  });
}

async function start() {
  const g = newGame();
  dock('آماده‌ای؟', '', 'busy');
  if (!S.tutorial) await coach();
  if (g !== G) return;
  loop(g);
}
buildBoard();
$('myDie').classList.add('ghost'); setDie($('myDie'), 0);
start();
})();
