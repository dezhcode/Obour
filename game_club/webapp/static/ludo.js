/* منچ — نمایش. تاس، نوبت و حرکت مجاز روی سرور حساب می شود (game_club/ludo.py)؛
   اینجا فقط رویدادهای سرور به ترتیب پخش می شوند (تاس، پرش مهره، زدن) و
   ورودی کاربر (تاس بنداز، این مهره) فرستاده می شود. بیرون از تلگرام همان
   API را demo.js در مرورگر شبیه سازی می کند.

   هر بازیکن رنگ خودش را پایین چپ می بیند: صفحه به اندازه رنگ او می چرخد
   و مهره ها و برچسب ها برعکس می چرخند تا سرپا بمانند. */
(() => {
const { S, save, fa, FD, store, face, COL, pawn, pips, LUDO, sfx, setSound, sheet, sheetHead, toast, sleep, icon, amount, mount, haptic, errText } = GC;
const { TRACK, SEAT, ORDER, SOCKETS } = LUDO;
const SAFE = new Set(LUDO.SAFE);
const $ = id => document.getElementById(id);
const ROT = { yellow: 0, green: 90, red: 180, blue: 270 };
const BASE = { blue: 0, red: 1, green: 2, yellow: 3 };
const POLL_MS = 900, STEP_MS = 150;

let mid = store.get('mid', null);
let me = 'yellow', rot = 0, since = 0, snap = null, shown = {}, els = {}, busy = false, acting = false, overShown = false;
let deadlineAt = 0, turnMs = 20000, warned = false, pollT = null;

/* ---------- صفحه ---------- */
const STAR = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2.5l2.9 6 6.6.9-4.8 4.6 1.2 6.5L12 17.4l-5.9 3.1 1.2-6.5L2.5 9.4l6.6-.9z"/></svg>';
const ARROW = deg => `<svg viewBox="0 0 24 24" aria-hidden="true" style="transform:rotate(${deg}deg)"><path d="M8 5l11 7-11 7z" fill="#fff"/></svg>`;
function buildBoard() {
  const startOf = {}; for (const c of ORDER) startOf[SEAT[c].start] = c;
  let h = '';
  TRACK.forEach(([x, y], i) => {
    const c = startOf[i], at = `style="grid-column:${x + 1};grid-row:${y + 1}"`;
    h += c ? `<div class="tile start c-${c}" ${at}>${ARROW(SEAT[c].arrow)}</div>` : SAFE.has(i) ? `<div class="tile safe" ${at}>${STAR}</div>` : `<div class="tile" ${at}></div>`;
  });
  for (const c of ORDER) SEAT[c].lane.forEach(([x, y]) => { h += `<div class="tile lane c-${c}" style="grid-column:${x + 1};grid-row:${y + 1}"></div>`; });
  for (const c of ORDER) {
    const [x, y] = SEAT[c].yard;
    h += `<div class="yard c-${c}" data-yard="${c}" style="grid-column:${x + 1}/${x + 7};grid-row:${y + 1}/${y + 7}"><span class="panel"></span>${SOCKETS.map(([sx, sy]) => `<span class="sock" style="left:${sx / 6 * 100}%;top:${sy / 6 * 100}%"></span>`).join('')}</div>`;
  }
  h += `<div class="home"><svg viewBox="0 0 3 3" preserveAspectRatio="none" aria-hidden="true"><path d="M0 0L1.5 1.5L0 3z" fill="#4C8DFF"/><path d="M0 0L3 0L1.5 1.5z" fill="#FF5A6A"/><path d="M3 0L3 3L1.5 1.5z" fill="#2FC584"/><path d="M0 3L3 3L1.5 1.5z" fill="#FFC531"/></svg><span class="home-mark">${icon('trophy', 2.4)}</span></div>`;
  h += '<div class="layer" id="layer"></div>';
  $('board').innerHTML = h;
}
function posOf(c, p, k) {
  const s = SEAT[c];
  if (p < 0) return [s.yard[0] + SOCKETS[k][0], s.yard[1] + SOCKETS[k][1]];
  if (p <= 50) { const [x, y] = TRACK[(s.start + p) % 52]; return [x + .5, y + .5]; }
  if (p <= 55) { const [x, y] = s.lane[p - 51]; return [x + .5, y + .5]; }
  return s.fin;
}
const pct = v => (v / 15 * 100) + '%';
function setRotation() {
  rot = ROT[me] || 0;
  const b = $('board');
  b.style.setProperty('--rot', rot + 'deg'); b.style.setProperty('--counter', -rot + 'deg');
}
const cornerOf = c => (BASE[c] + rot / 90) % 4;

/* ---------- مهره ها ---------- */
function ensurePawns(g) {
  const layer = $('layer');
  for (const c of g.order) {
    const n = (g.pawns[c] || []).length;
    if (!els[c] || els[c].length !== n) {
      (els[c] || []).forEach(e => e.remove());
      els[c] = [];
      for (let k = 0; k < n; k++) {
        const el = document.createElement('button');
        el.className = 'pawn c-' + c; el.innerHTML = pawn(c); el.dataset.c = c; el.dataset.k = k;
        el.setAttribute('aria-label', `مهرهٔ ${COL[c].fa} ${FD(k + 1)}`);
        layer.appendChild(el); els[c].push(el);
      }
    }
  }
}
function layout() {
  const groups = {};
  for (const c of Object.keys(shown)) (shown[c] || []).forEach((p, k) => {
    if (!els[c] || !els[c][k]) return;
    const [x, y] = posOf(c, p, k), key = x.toFixed(2) + ',' + y.toFixed(2);
    (groups[key] = groups[key] || []).push([c, k, x, y]);
  });
  for (const list of Object.values(groups)) list.forEach(([c, k, x, y], i) => {
    const el = els[c][k], n = list.length, off = n > 1 ? (i - (n - 1) / 2) * .36 : 0;
    el.style.left = pct(x + off); el.style.top = pct(y + (n > 1 ? .12 : 0));
    el.style.setProperty('--s', n > 1 ? .8 : 1);
    el.style.setProperty('--counter', -rot + 'deg');
    el.style.zIndex = Math.round(y * 10) + (el.classList.contains('can') ? 300 : 0);
  });
}
const clone = o => JSON.parse(JSON.stringify(o));
const nameOf = c => { const p = snap && snap.game.players[c]; return !p ? '' : p.me ? 'تو' : p.name; };

/* ---------- صندلی ها، نوبت، داک ---------- */
function renderSeats(g) {
  document.querySelectorAll('.seat').forEach(el => { el.className = 'seat' + (+el.dataset.corner === 1 || +el.dataset.corner === 2 ? ' right' : '') + ' empty'; el.innerHTML = ''; });
  for (const c of ORDER) {
    const yard = document.querySelector(`[data-yard="${c}"]`), pl = g.players[c];
    yard.classList.toggle('off', !pl || pl.out);
    if (!pl) continue;
    const el = document.querySelector(`.seat[data-corner="${cornerOf(c)}"]`);
    el.classList.remove('empty'); el.classList.add('c-' + c);
    el.classList.toggle('turn', g.turn === c);
    const done = g.done[c] || 0, total = Math.max((g.pawns[c] || []).length, done);
    el.innerHTML = `${face(pl, 'var(--c)', 'timer')}
      <div class="seat-txt" dir="rtl"><span class="seat-name">${pl.me ? 'شما' : pl.name}${pl.out ? ' (رفت)' : ''}</span><span class="prog" title="مهره‌های رسیده">${Array.from({ length: total }, (_, i) => `<i class="${i < done ? 'done' : ''}"></i>`).join('')}</span></div>
      <span class="die sm c-${c}${g.last[c] ? '' : ' ghost'}" data-die="${c}">${pips(g.last[c] || 0)}</span>`;
  }
  document.querySelectorAll('.yard').forEach(y => y.classList.toggle('turn', g.turn === y.dataset.yard));
  for (const c of Object.keys(bubbles)) showBubble(c);
}
function dock(title, sub, state) {
  $('dockT').textContent = title; $('dockS').textContent = sub || '';
  const b = $('roll');
  b.setAttribute('aria-disabled', String(state !== 'roll'));
  b.classList.toggle('ask', state === 'roll');
  $('myDie').classList.toggle('ghost', state === 'wait');
}
function feed(c, text) {
  const f = $('feed');
  f.className = 'feed1 c-' + c; f.innerHTML = `<i></i><span>${text}</span>`;
}
function renderTurn(g) {
  const tb = $('turnbar');
  if (g.over) { tb.className = 'turnbar c-' + (g.winner || me); $('turnTxt').textContent = 'بازی تمام شد'; dock('بازی تمام شد', '', 'wait'); return; }
  tb.className = 'turnbar c-' + g.turn;
  const mine = g.turn === me;
  $('turnTxt').textContent = mine ? 'نوبت شماست' : 'نوبت ' + nameOf(g.turn);
  clearHints();
  if (mine && g.phase === 'roll') dock('نوبت شماست', 'روی تاس بزن تا بریزد', 'roll');
  else if (mine && g.phase === 'move') {
    dock(FD(g.dice) + ' آوردی', 'مهره‌ای را که بالا و پایین می‌پرد بزن؛ دایرهٔ خط‌چین مقصدش است', 'pick');
    showHints(g.dice, g.movable);
  } else dock('نوبت ' + nameOf(g.turn), g.players[g.turn] && g.players[g.turn].bot ? 'ربات فکر می‌کند…' : 'منتظر حرکت حریف…', 'wait');
  deadlineAt = g.deadline_ms ? Date.now() + g.deadline_ms : 0; turnMs = g.turn_ms || 20000; warned = false;
}
function clearHints() {
  for (const c in els) els[c].forEach(e => e.classList.remove('can'));
  document.querySelectorAll('#layer .dest').forEach(e => e.remove());
}
function showHints(d, moves) {
  for (const k of moves) {
    els[me][k].classList.add('can');
    const p = shown[me][k], np = p < 0 ? 0 : p + d, [x, y] = posOf(me, np, k);
    const m = document.createElement('button');
    m.className = 'dest c-' + me; m.dataset.k = k; m.style.left = pct(x); m.style.top = pct(y);
    m.setAttribute('aria-label', 'مقصد این مهره'); m.textContent = np === 56 ? '★' : '';
    $('layer').appendChild(m);
  }
  layout();
}

/* ---------- تایمر نوبت ---------- */
setInterval(() => {
  const left = deadlineAt ? Math.max(0, deadlineAt - Date.now()) / turnMs : 1;
  $('timeBar').style.transform = `scaleX(${Math.min(1, left)})`;
  const av = snap && snap.game.turn ? document.querySelector(`.seat.c-${snap.game.turn} .avatar`) : null;
  document.querySelectorAll('.seat .avatar').forEach(a => a.style.setProperty('--t', a === av ? Math.min(1, left) : 1));
  if (snap && snap.game.turn === me && deadlineAt && left < .25 && !warned) { warned = true; sfx.tick(); haptic('warning'); }
}, 200);

/* ---------- پخش رویدادها ---------- */
async function rollAnim(c, v) {
  const el = c === me ? $('myDie') : document.querySelector(`[data-die="${c}"]`);
  if (el) { el.classList.remove('ghost'); el.classList.add('rolling'); }
  sfx.dice(); if (c === me) haptic('medium');
  for (let i = 0; i < 7; i++) { if (el) el.innerHTML = pips(1 + Math.floor(Math.random() * 6)); await sleep(60); }
  if (el) { el.classList.remove('rolling'); el.innerHTML = pips(v); }
  const small = document.querySelector(`[data-die="${c}"]`); if (small) { small.classList.remove('ghost'); small.innerHTML = pips(v); }
  if (v === 6) { sfx.six(); if (c === me) haptic('success'); }
}
function flash(c, x, y) {
  const f = document.createElement('span'); f.className = 'flash c-' + c; f.style.left = pct(x); f.style.top = pct(y);
  $('layer').appendChild(f); setTimeout(() => f.remove(), 600);
}
/* تاسی که حرکتی نمی دهد: تاس «نه» می گوید (لرزش افقی و حلقه قرمز)، مهره های آن رنگ
   سر جایشان می لرزند و یک برچسب کوتاه وسط صفحه می آید */
function blocked(c, v, allYard) {
  [c === me ? $('myDie') : null, document.querySelector(`[data-die="${c}"]`)].forEach(d => {
    if (!d) return; d.classList.remove('nope'); void d.offsetWidth; d.classList.add('nope'); setTimeout(() => d.classList.remove('nope'), 1100);
  });
  (els[c] || []).forEach(el => { el.classList.remove('stuck'); void el.offsetWidth; el.classList.add('stuck'); setTimeout(() => el.classList.remove('stuck'), 700); });
  const b = document.createElement('div');
  b.className = 'blocked c-' + c; b.setAttribute('aria-hidden', 'true');
  b.innerHTML = `<span class="die sm c-${c}">${pips(v)}</span><span>${allYard ? 'برای ورود ۶ لازم است' : 'حرکتی نیست'}</span>`;
  $('frame').appendChild(b); setTimeout(() => b.remove(), 1300);
}
async function play(e) {
  const c = e.c;
  if (e.t === 'roll') { await rollAnim(c, e.v); if (e.auto && c === me) feed(c, 'وقتت تمام شد؛ تاس خودکار ریخته شد'); return; }
  if (e.t === 'nomove') {
    sfx.nomove(); if (c === me) haptic('warning');
    const allYard = (shown[c] || []).every(p => p < 0);
    blocked(c, e.v, allYard);
    feed(c, (c === me ? FD(e.v) + ' آوردی' : nameOf(c) + ' ' + FD(e.v) + ' آورد') + '؛ ' + (allYard ? 'برای ورود مهره ۶ لازم است' : 'حرکتی ممکن نبود'));
    await sleep(1000); return;
  }
  if (e.t === 'move') {
    if (!shown[c] || !els[c] || !els[c][e.k]) return;
    const el = els[c][e.k];
    if (e.frm < 0) { shown[c][e.k] = 0; sfx.enter(); layout(); await sleep(260); }
    else for (let p = e.frm + 1, i = 0; p <= e.to; p++, i++) {
      shown[c][e.k] = p; el.classList.remove('hop'); void el.offsetWidth; el.classList.add('hop'); sfx.step(i); layout(); await sleep(STEP_MS);
    }
    if (e.cap && e.cap.length) {
      const [x, y] = posOf(c, e.to, e.k); flash(e.cap[0][0], x, y); sfx.capture(); haptic(c === me || e.cap[0][0] === me ? 'heavy' : 'light');
      await sleep(160);
      e.cap.forEach(([o, j]) => { if (shown[o]) shown[o][j] = -1; });
      layout(); await sleep(300);
      const v = e.cap[0][0];
      feed(c, c === me ? `مهرهٔ ${nameOf(v)} را زدی! یک نوبت اضافه` : v === me ? `${nameOf(c)} مهرهٔ تو را زد و به لانه برگرداند` : `${nameOf(c)} مهرهٔ ${nameOf(v)} را زد`);
    } else if (e.fin) { sfx.home(); const [x, y] = SEAT[c].fin; flash(c, x, y); feed(c, (c === me ? 'یک مهره به مرکز رساندی' : nameOf(c) + ' یک مهره به مرکز رساند') + '! یک نوبت اضافه'); }
    else if (e.frm < 0) feed(c, c === me ? '۶ آوردی و مهره وارد شد' : nameOf(c) + ' ۶ آورد و مهره وارد کرد');
    if (e.auto && c === me) feed(c, 'وقتت تمام شد؛ بهترین حرکت انجام شد');
    return;
  }
  if (e.t === 'six3') { feed(c, (c === me ? 'سه بار ۶ آوردی' : nameOf(c) + ' سه بار ۶ آورد') + '؛ نوبت سوخت'); return; }
  if (e.t === 'timeout' && c === me && e.n >= 2 && snap && snap.cfg.mode === 'stake') { toast(e.n >= 3 ? 'سه نوبت غایب بودی' : 'یک نوبت دیگر غیبت = باخت'); return; }
  if (e.t === 'leave') { feed(c, (c === me ? 'از بازی بیرون رفتی' : nameOf(c) + (e.why === 'timeout' ? ' به‌خاطر غیبت حذف شد' : ' از بازی رفت'))); return; }
}

/* ---------- گفتگوی سر میز (مثل پلاتو) ----------
   پیام ها با همان پرس و جوی هر ۰٫۹ ثانیه می آیند (chat=آخرین شماره). پیام تازه
   چند ثانیه به شکل حباب کنار صندلی فرستنده دیده می شود؛ تاریخچه در برگه گفتگو. */
const QUICK = ['سلام!', 'خوش‌بازی!', 'آفرین', 'شانسی بود', 'زود باش', 'یک دست دیگه؟'];
const esc = t => String(t == null ? '' : t).replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
let chatId = 0, chatLog = [], unread = 0, chatSheet = null, sending = false;
const bubbles = {};
function showBubble(c) {
  const b = bubbles[c], seat = document.querySelector(`.seat.c-${c}`);
  if (!b || !seat) return;
  if (Date.now() > b.until) { delete bubbles[c]; return; }
  seat.querySelectorAll('.bubble').forEach(x => x.remove());
  const el = document.createElement('div'); el.className = 'bubble'; el.textContent = b.text; el.setAttribute('aria-hidden', 'true');
  seat.appendChild(el);
}
function bubble(m) {
  bubbles[m.color] = { text: m.text, until: Date.now() + 4200 };
  showBubble(m.color);
  setTimeout(() => { if (bubbles[m.color] && Date.now() >= bubbles[m.color].until) { delete bubbles[m.color]; document.querySelectorAll(`.seat.c-${m.color} .bubble`).forEach(x => x.remove()); } }, 4300);
}
function badge() {
  const b = $('chatBadge'); b.hidden = !unread; b.textContent = unread > 9 ? '+۹' : FD(unread);
  $('chatBtn').setAttribute('aria-label', unread ? `گفتگوی میز، ${FD(unread)} پیام تازه` : 'گفتگوی میز');
}
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
  log.innerHTML = chatLog.length ? chatLog.map(m => `<div class="msg${m.me ? ' mine' : ''}">${m.me ? '' : face(m, COL[m.color] ? COL[m.color].hex : 'var(--surface)')}<div class="bub">${m.me ? '' : `<b>${esc(m.name)}</b>`}<span>${esc(m.text)}</span></div></div>`).join('')
    : '<p class="hint">هنوز کسی چیزی نگفته. سلام کن!</p>';
  log.scrollTop = log.scrollHeight;
}
async function send(text) {
  text = String(text || '').trim();
  if (!text || sending || !mid) return false;
  sending = true;
  try {
    await GC.ludo.chat(mid, text);
    chatIn((await GC.ludo.match(mid, since, chatId)).chat);
    return true;
  } catch (e) { sfx.error(); toast(errText(e)); return false; }
  finally { sending = false; }
}
function openChat() {
  unread = 0; badge();
  const sh = sheet(`${sheetHead('گفتگوی میز')}<div class="chat-log" id="chatLog" aria-live="polite"></div>
    <div class="quick">${QUICK.map(q => `<button class="chip sm" data-q>${q}</button>`).join('')}</div>
    <form class="chat-form" id="chatForm"><button class="send" aria-label="فرستادن">${icon('up', 2.6)}</button><input id="chatTxt" maxlength="140" placeholder="یه چیزی بگو…" autocomplete="off" enterkeyhint="send" aria-label="پیام به میز"></form>`,
  { onClose: () => { chatSheet = null; } });
  chatSheet = sh; renderChat();
  sh.querySelectorAll('[data-q]').forEach(b => { b.onclick = () => send(b.textContent); });
  const input = sh.querySelector('#chatTxt');
  sh.querySelector('#chatForm').onsubmit = async e => { e.preventDefault(); if (await send(input.value)) input.value = ''; input.focus(); };
}
$('chatBtn').onclick = openChat;
// پایان یا بستن میز: گفتگوی آن میز روی سرور پاک شده؛ اینجا هم پاک و دکمه پنهان می شود
function endChat() {
  chatLog = []; unread = 0; chatSheet = null;
  for (const c of Object.keys(bubbles)) delete bubbles[c];
  document.querySelectorAll('.bubble').forEach(x => x.remove());
  $('chatBtn').hidden = true;
}

/* ---------- همگام سازی با سرور ---------- */
async function apply(next) {
  if (next && next.chat && !overShown && next.status !== 'over' && next.status !== 'cancelled') chatIn(next.chat);
  if (next && next.status === 'cancelled') return cancelled();
  if (!next || !next.game) return;
  busy = true;
  try {
    const g = next.game;
    snap = Object.assign({}, snap || {}, next);
    ensurePawns(g);
    for (const e of (g.events || []).filter(e => e.seq > since).sort((a, b) => a.seq - b.seq)) { await play(e); since = e.seq; }
    since = Math.max(since, g.seq);
    shown = clone(g.pawns); ensurePawns(g); clearHints(); layout();
    renderSeats(g); renderTurn(g);
    if (next.status === 'over' && !overShown) { overShown = true; over(next); }
  } finally { busy = false; }
}
async function poll() {
  clearTimeout(pollT);
  if (document.hidden || overShown) { pollT = setTimeout(poll, POLL_MS); return; }
  if (!busy && !acting) {
    try { await apply(await GC.ludo.match(mid, since, chatId)); }
    catch (e) { if (e.code === 'not_found') return noMatch(); }
  }
  pollT = setTimeout(poll, POLL_MS);
}
async function act(fn) {
  if (acting || busy) return;
  acting = true;
  try { await apply(await fn()); }
  catch (e) { sfx.error(); haptic('error'); toast(errText(e)); }
  finally { acting = false; }
}
$('roll').onclick = () => {
  if (!snap || snap.game.turn !== me || snap.game.phase !== 'roll') return;
  $('roll').classList.remove('ask');
  act(() => GC.ludo.roll(mid, since));
};
$('board').addEventListener('click', e => {
  if (!snap || snap.game.turn !== me || snap.game.phase !== 'move') return;
  const t = e.target.closest('.pawn.can, .dest'); if (!t) return;
  if (t.classList.contains('pawn') && t.dataset.c !== me) return;
  clearHints();
  act(() => GC.ludo.move(mid, +t.dataset.k, since));
});
document.addEventListener('keydown', e => { if ((e.key === ' ' || e.key === 'Enter') && document.activeElement === document.body) { e.preventDefault(); $('roll').click(); } });
document.addEventListener('visibilitychange', () => { if (!document.hidden) poll(); });

/* ---------- پایان، خروج ---------- */
function over(v) {
  endChat();
  const g = v.game, r = v.result || {}, w = g.winner, won = w === me;
  GC.guardClose(false); store.set('mid', null);
  won ? (sfx.win(), haptic('success')) : (sfx.lose(), haptic('warning'));
  const secs = Math.max(0, Math.round(Date.now() / 1000 - g.started)), st = g.stats || { caps: 0, sixes: 0 };
  const stake = v.cfg.mode === 'stake';
  sheet(`<div class="result">
      <div class="crown-pawn">${pawn(w || me, !!w).replace('viewBox="0 0 40 50"', 'viewBox="0 -4 40 54"')}</div>
      <h2>${won ? 'بردی!' : w ? nameOf(w) + ' برد' : 'بازی تمام شد'}</h2>
      ${stake ? (won ? `<div class="prize">${amount(r.prize || 0, 'lg')}</div><p class="muted">جایزه به کیف امتیازت اضافه شد.</p>` : `<p class="muted">ورودی این دست (${fa(r.lost || v.cfg.entry)} امتیاز) را باختی.</p>`)
        : `<p class="muted">${won ? 'بازی آزاد بود و جایزه نداشت.' : 'بازی آزاد بود؛ چیزی از دست ندادی.'}</p>`}
      <div class="facts"><div><b>${FD(st.caps)}</b><span>مهره زدی</span></div><div><b>${FD(st.sixes)}</b><span>بار ۶ آوردی</span></div><div><b>${FD(Math.floor(secs / 60))}:${FD(String(secs % 60).padStart(2, '0'))}</b><span>مدت بازی</span></div></div>
    </div>
    <a class="btn btn-block" href="ludo-lobby.html">${icon('dice')}یک دست دیگر</a>
    <a class="btn btn-light btn-block" href="index.html">خانه</a>`, { center: true, dismiss: false });
  GC.refreshMe().catch(() => {});
}
function cancelled() {
  if (overShown) return;
  overShown = true; endChat(); GC.guardClose(false); store.set('mid', null); GC.refreshMe().catch(() => {});
  sheet(`<h2 style="font-size:22px;font-weight:900">این میز بسته شد</h2><p class="muted">پشتیبانی این میز را بست و ورودی همه به کیف امتیازشان برگشت.</p>
    <a class="btn btn-block" href="ludo-lobby.html">${icon('dice')}میز تازه</a><a class="btn btn-light btn-block" href="index.html">خانه</a>`, { center: true, dismiss: false });
}
function noMatch() {
  store.set('mid', null);
  sheet(`<h2 style="font-size:22px;font-weight:900">میزی پیدا نشد</h2><p class="muted">این بازی تمام شده یا هنوز سر میزی ننشسته‌ای.</p>
    <a class="btn btn-block" href="ludo-lobby.html">${icon('dice')}یک میز بساز</a><a class="btn btn-light btn-block" href="index.html">خانه</a>`, { center: true, dismiss: false });
}
function askExit() {
  if (!snap || snap.status === 'over') { location.href = 'index.html'; return; }
  const stake = snap.cfg.mode === 'stake';
  const sh = sheet(`<h2 style="font-size:22px;font-weight:900">از بازی بیرون می‌روی؟</h2>
    <p class="muted">${stake ? `بازی با امتیاز است. خروج یعنی باخت و ${fa(snap.cfg.entry)} امتیاز ورودی برنمی‌گردد.` : 'بازی آزاد است و چیزی از دست نمی‌دهی.'}</p>
    <button class="btn btn-danger btn-block" id="leave">بیرون برو</button>
    <button class="btn btn-light btn-block" data-close>ادامهٔ بازی</button>`, { center: true });
  sh.querySelector('#leave').onclick = async () => {
    try { await GC.ludo.leave(mid); } catch (e) {}
    GC.guardClose(false); store.set('mid', null); location.href = 'index.html';
  };
}
$('exit').onclick = askExit;
GC.back(askExit);

const sndBtn = $('snd');
const syncSnd = () => { sndBtn.innerHTML = icon(S.sound ? 'soundOn' : 'soundOff'); sndBtn.setAttribute('aria-pressed', String(!!S.sound)); sndBtn.setAttribute('aria-label', S.sound ? 'خاموش کردن صدا' : 'روشن کردن صدا'); };
sndBtn.onclick = () => { setSound(!S.sound); syncSnd(); };
syncSnd();
$('rules').onclick = () => sheet(`${sheetHead('قوانین منچ')}
  <ul class="rules-mini">
    <li>رنگ تو همیشه <b>پایین چپ</b> است. مهره‌ها در جهت فلش‌ها می‌چرخند و از راهروی رنگ خودت به مرکز می‌رسند.</li>
    <li>فقط با <b>۶</b> مهره از لانه بیرون می‌آید.</li>
    <li>۶، زدن مهرهٔ حریف یا رسیدن به مرکز <b>یک نوبت اضافه</b> می‌دهد. سه بار ۶ پشت‌سرهم نوبت را می‌سوزاند.</li>
    <li>اگر دقیقاً روی مهرهٔ حریف بنشینی، به لانه‌اش برمی‌گردد. روی <b>ستاره</b> و خانهٔ شروع کسی زده نمی‌شود.</li>
    <li>هر نوبت <b>${FD(Math.round(turnMs / 1000))} ثانیه</b> وقت داری؛ بعدش تاس و حرکت خودکار انجام می‌شود.</li>
    <li>تاس روی سرور ریخته می‌شود؛ نه گوشی تو و نه حریف عددش را تعیین نمی‌کند.</li>
  </ul>
  <a class="btn btn-light btn-block" href="help.html">راهنمای کامل</a>`);

/* ---------- اندازه صفحه: هر چه ارتفاع جا بدهد، بدون اسکرول ---------- */
function fitBoard() {
  const frame = $('frame'), page = document.querySelector('.page');
  const H = (window.Telegram && Telegram.WebApp && Telegram.WebApp.viewportStableHeight) || window.innerHeight;
  const other = $('appbar').offsetHeight + $('seatsTop').offsetHeight + $('seatsBot').offsetHeight + $('feed').offsetHeight + $('dock').offsetHeight
    + 6 * 8 + 16 + (parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--sa-b')) || 0);
  const w = page.clientWidth - 2 * parseFloat(getComputedStyle(page).paddingInlineStart || 16);
  frame.style.setProperty('--board', Math.max(240, Math.min(w, H - other)) + 'px');
}
window.addEventListener('resize', fitBoard);
try { Telegram.WebApp.onEvent('viewportChanged', fitBoard); Telegram.WebApp.onEvent('fullscreenChanged', () => setTimeout(fitBoard, 50)); } catch (e) {}

/* ---------- شروع ---------- */
async function start() {
  buildBoard(); fitBoard(); GC.portrait(true);
  dock('در حال وصل شدن…', '', 'wait');
  let first;
  try { first = await GC.ludo.match(mid, 0, 0); }
  catch (e) { return e.code === 'not_found' ? noMatch() : (toast(errText(e)), setTimeout(start, 2500)); }
  if (first.status === 'lobby') { location.href = 'ludo-lobby.html'; return; }
  if (first.status === 'cancelled') return cancelled();
  mid = first.id; store.set('mid', mid); me = first.me; setRotation();
  const g = first.game;
  $('myDie').className = 'die c-' + me + ' ghost';
  if (first.cfg.mode === 'stake' && first.status === 'playing') GC.guardClose(true);
  chatIn(first.chat, true);
  snap = first; since = g.seq; shown = clone(g.pawns); ensurePawns(g); layout(); renderSeats(g); renderTurn(g); mount(); fitBoard();
  if (first.status === 'over') { overShown = true; over(first); return; }
  if (!S.tutorial) await GC.coach(me);
  poll();
}
start();
})();
