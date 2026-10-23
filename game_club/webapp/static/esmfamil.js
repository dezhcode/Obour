/* صفحهٔ بازی اسم‌فامیل (طرح «برگ دفتر»). وضعیت از سرور می آید (game_club/esmfamil.py)؛ این صفحه برگ را نشان
   می دهد، نوشته ها را خودکار ذخیره می کند و استپ، تحویل، اعتراض، رأی و «دور بعد» را می فرستد.
   جواب هایی که بازیکن ها تایپ می کنند با خط دست (Digi Maryam) و جوهر آبی؛ نمره و نظر داور قرمز.
   بیرون از تلگرام یک بازی نمونه با سه بازیکن ساختگی پخش می شود (EsmDemo پایین همین فایل). */
(() => {
const { FD, store, icon, sheet, close, toast, sfx, haptic, errText, face } = GC;
const $ = id => document.getElementById(id);
const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
// همان شکل مقایسهٔ سرور (esmfamil.norm): عربی به فارسی، آ = ا، بدون اعراب و فاصله
const MAP = { 'ي': 'ی', 'ى': 'ی', 'ئ': 'ی', 'ك': 'ک', 'ة': 'ه', 'ۀ': 'ه', 'أ': 'ا', 'إ': 'ا', 'آ': 'ا', 'ٱ': 'ا', 'ؤ': 'و' };
const norm = s => String(s || '').replace(/[يىئكةۀأإآٱؤ]/g, ch => MAP[ch]).replace(/[ً-ٰٟـ‌‍‎‏\s\-_.,،؛:!?؟"'«»()]/g, '').toLowerCase();
const starts = (a, L) => { const k = norm(a); return !!k && !!L && k[0] === norm(L)[0]; };
const PEN = icon('pen');
const CLOCK = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="13" r="8"/><path d="M12 9v4l3 2M9 2.5h6"/></svg>';
const RING = '<svg viewBox="0 0 100 100" aria-hidden="true"><path class="ring" d="M52 8C78 7 94 26 92 52C90 77 71 93 48 92C24 91 8 73 9 49C10 27 26 9 55 9"/></svg>';

const watchMid = GC.watchId();
const API = GC.live ? GC.esm : window.EsmDemo;
let mid = watchMid || store.get('emid', null), WATCH = false, snap = null, since = 0, pollT = null, busy = false, overShown = false;
let deadlineAt = 0, built = '', phaseAt = 0, lastTick = -1, tab = null;
let vals = {}, sent = {}, saveT = null, saving = null, flushed = false;
const G = () => snap && snap.game;
const me = () => (G() && !WATCH ? G().me : null);
const nameOf = c => c === me() ? 'تو' : (G() && G().players[c] ? G().players[c].name : '؟');
const who = c => c === me() ? 'تو' : `<span class="uname">${esc(nameOf(c))}</span>`;
const active = () => G().order.filter(c => !G().players[c].out);
const filled = () => G().cols.filter(({ k }) => (vals[k] || '').trim()).length;
const secsLeft = () => Math.max(0, Math.ceil((deadlineAt - performance.now()) / 1000));

/* ---------- ذخیرهٔ خودکار برگ ---------- */
function diff() {
  const out = {};
  for (const { k } of G().cols) { const v = (vals[k] || '').trim(); if (v !== (sent[k] || '')) out[k] = v; }
  return out;
}
function queueSave(ms) { clearTimeout(saveT); saveT = setTimeout(save, ms); }
async function save() {
  clearTimeout(saveT);
  if (WATCH || !G() || !['write', 'stop'].includes(G().phase) || G().submitted) return;
  const d = diff(); if (!Object.keys(d).length) return;
  if (saving) { await saving.catch(() => {}); return save(); }
  saving = API.answer(mid, d);
  try { await saving; Object.assign(sent, d); for (const k in d) if (!d[k]) delete sent[k]; }
  catch (e) { if (!['closed', 'submitted'].includes(e.code)) queueSave(2500); }
  saving = null;
}
const fullSheet = () => Object.fromEntries(G().cols.map(({ k }) => [k, (vals[k] || '').trim()]));

/* ---------- سربرگ و ساعت ---------- */
function head() {
  const g = G(); if (!g) return;
  const L = g.letter;
  $('mini').classList.toggle('blank', !L);
  $('miniCh').textContent = L || '؟';
  $('round').textContent = g.over ? 'برگ نهایی' : `دور ${FD(g.round + 1)} از ${FD(g.rounds_n)}`;
}
function tickClock() {
  const g = G(), el = $('clock');
  if (!g) return;
  const on = ['letter', 'write', 'stop', 'show'].includes(g.phase) && !g.over;
  const s = secsLeft();
  el.style.visibility = g.over ? 'hidden' : '';
  el.classList.toggle('off', !on || (g.phase === 'letter' && !g.letter));
  el.classList.toggle('low', on && ['write', 'stop'].includes(g.phase) && s <= 10);
  $('clockTxt').textContent = !on ? (g.phase === 'judge' ? 'داوری' : '—') : g.phase === 'letter' && !g.letter ? '…' : `${FD(Math.floor(s / 60))}:${FD(String(s % 60).padStart(2, '0'))}`;
  if (['write', 'stop'].includes(g.phase)) {
    if (s <= 5 && s > 0 && s !== lastTick) { lastTick = s; sfx.tick(); }
    // آخرین ثانیه: هر چه نوشته شده همین حالا برود (سرور تا ۱٫۵ ثانیه بعد از وقت هم می پذیرد)
    if (s <= 1 && !flushed) { flushed = true; save(); }
  }
  if (g.phase === 'letter' && g.letter) { const c = document.getElementById('cnt'); if (c) c.textContent = FD(Math.max(1, s)); }
  if (g.phase === 'show') { const b = document.getElementById('rdyS'); if (b) b.textContent = FD(s); }
  if (g.phase === 'judge') { const p = document.getElementById('prog'); if (p) p.style.width = Math.round(92 * (1 - Math.exp(-(performance.now() - phaseAt) / 9000))) + '%'; }
}
setInterval(tickClock, 250);

function note(html, ic) {
  const n = $('note');
  if (!html) { n.hidden = true; n.dataset.k = ''; return; }
  if (n.dataset.k === html) return;
  n.dataset.k = html; n.hidden = false;
  n.innerHTML = (ic || CLOCK) + `<span>${html}</span>`;
}

/* ---------- مرحلهٔ حرف ---------- */
function viewLetter() {
  const g = G();
  if (!g.letter) {
    const waiting = (g.waiting || []).filter(c => c !== me());
    return `<section class="ef-reveal"><span class="ef-think">${PEN}</span><h2>داور دارد حرف را انتخاب می‌کند…</h2>
      <p class="ef-sub">هوش مصنوعی عبور حرف همهٔ دورها را می‌چیند. حرف برای همه هم‌زمان رو می‌شود.</p>
      ${waiting.length ? `<div class="ef-wait"><b>هنوز نیامده‌اند:</b>${waiting.map(c => `<span class="ef-chip">${who(c)}</span>`).join('')}</div>` : ''}</section>`;
  }
  return `<section class="ef-reveal"><div class="ef-big">${RING}<b>${esc(g.letter)}</b></div>
    ${g.line ? `<p class="ef-line">${esc(g.line)}</p>` : `<p class="ef-line">حرف «${esc(g.letter)}»!</p>`}
    <p class="ef-sub">برگ تا چند لحظهٔ دیگر باز می‌شود؛ آماده باش</p><span class="ef-count" id="cnt">${FD(secsLeft() || 1)}</span></section>`;
}

/* ---------- مرحلهٔ نوشتن ---------- */
function viewWrite() {
  const g = G(), done = g.submitted;
  if (WATCH) {
    return `<div class="ef-card" style="padding:14px"><p class="ef-sub" style="margin:0 0 10px">برگ‌ها تا داوری پنهان است؛ فقط پیداست هر کس چند خانه نوشته.</p>
      <ol class="ef-rank" style="margin:0">${active().map(c => `<li><span class="nm">${who(c)}</span><span class="v">${FD(g.players[c].filled || 0)}/${FD(g.cols.length)}</span></li>`).join('')}</ol></div>`;
  }
  return `<div class="ef-sheet${done ? ' done' : ''}" id="sheet">${g.cols.map(({ k, fa }, i) => `<div class="ef-row" data-k="${k}">
      <label for="in-${k}">${fa}</label>
      <input id="in-${k}" data-k="${k}" maxlength="32" autocomplete="off" autocorrect="off" autocapitalize="off" spellcheck="false" dir="rtl"
        enterkeyhint="${i < g.cols.length - 1 ? 'next' : 'done'}" placeholder="با «${esc(g.letter)}»…" value="${esc(vals[k] || '')}"${done ? ' disabled' : ''}>
      <i class="ef-flag" aria-hidden="true"></i></div>`).join('')}</div>`;
}
function flags() {
  const g = G();
  document.querySelectorAll('#sheet .ef-row').forEach(r => {
    const v = (vals[r.dataset.k] || '').trim();
    r.classList.toggle('ok', !!v && starts(v, g.letter));
    r.classList.toggle('bad', !!v && !starts(v, g.letter));
  });
}
function footWrite() {
  const g = G(), n = filled(), all = n === g.cols.length;
  const others = active().filter(c => c !== me());
  const doneC = others.filter(c => g.players[c].done), writing = others.length - doneC.length;
  const chips = `<div class="ef-who"><b>برگ‌ها:</b>${doneC.map(c => `<span class="ef-chip done">${who(c)} ✓</span>`).join('')}${writing ? `<span class="ef-chip">${FD(writing)} نفر می‌نویسند</span>` : ''}</div>`;
  if (WATCH) return chips;
  let btn;
  if (g.submitted) btn = `<button class="ef-go soft" disabled>${icon('check')}تحویل شد؛ منتظر بقیه</button>`;
  else if (g.phase === 'write' && all) btn = `<button class="ef-go stop" id="stopB">استپ!</button>`;
  else btn = `<button class="ef-go${all ? '' : ' soft'}" id="subB">تحویل برگ (${FD(n)} از ${FD(g.cols.length)})</button>`;
  return chips + btn;
}
function noteWrite() {
  const g = G();
  if (g.phase === 'stop') {
    const s = Math.max(0, secsLeft());
    return note(g.stopper === me() ? `استپ زدی! بقیه فقط ${FD(s)} ثانیه وقت دارند` : `${who(g.stopper)} استپ زد! ${FD(s)} ثانیه تا جمع شدن برگ‌ها`);
  }
  if (WATCH) return note('در حال تماشا؛ برگ‌ها بعد از داوری رو می‌شود', icon('eye'));
  note(null);
}
function bindWrite() {
  const ins = [...document.querySelectorAll('#sheet input')];
  ins.forEach((el, i) => {
    el.addEventListener('input', () => {
      vals[el.dataset.k] = el.value; flags(); flushed = false;
      queueSave(secsLeft() <= 4 ? 250 : 1200);
      const f = $('foot'); const sig = filled() === G().cols.length;
      if (f.dataset.full !== String(sig)) { f.dataset.full = String(sig); renderFoot(); }
      else { const b = $('subB'); if (b) b.textContent = `تحویل برگ (${FD(filled())} از ${FD(G().cols.length)})`; }
    });
    el.addEventListener('keydown', e => {
      if (e.key !== 'Enter') return;
      e.preventDefault();
      const next = ins.slice(i + 1).find(x => !x.value.trim()) || ins[i + 1];
      if (next) next.focus(); else el.blur();
    });
    el.addEventListener('blur', () => queueSave(150));
  });
  flags();
}

/* ---------- مرحلهٔ داوری ---------- */
function viewJudge() {
  const g = G();
  const mine = WATCH ? '' : `<div class="ef-sheet">${g.cols.map(({ k, fa }) => `<div class="ef-row"><label>${fa}</label>
      ${(g.sheet && g.sheet[k]) || vals[k] ? `<span class="ro hand">${esc((g.sheet && g.sheet[k]) || vals[k])}</span>` : '<span class="ro empty">خالی</span>'}</div>`).join('')}</div>`;
  return `<div class="ef-jhead"><span class="ic">${PEN}</span><div><h2>داور دارد تصحیح می‌کند…</h2><small>هوش مصنوعی عبور برگ همه را می‌خواند</small></div></div>
    <div class="ef-prog"><i id="prog" style="width:4%"></i></div>${mine}
    <p class="ef-tip">جواب درستِ تکی ۱۰، درستِ تکراری ۵، غلط یا خالی ۰. داور دلیل هر جواب ردشده را کنارش می‌نویسد.</p>`;
}

/* ---------- برگ دور (جدول) ---------- */
function upto(g, i, c) { return g.results.slice(0, i + 1).reduce((s, r) => s + (r.scores[c] || 0), 0); }
function tableHtml(g, i) {
  const rec = g.results[i], cols = g.order.filter(c => rec.cells[c]);
  const last = i === g.results.length - 1 && g.phase === 'show';
  const best = Math.max(0, ...cols.map(c => upto(g, i, c)));
  const mc = c => (c === me() ? ' class="me"' : '');
  const cell = (c, k) => {
    const x = rec.cells[c][k], ap = last ? g.appeals[`${c}:${k}`] : null;
    const cls = [c === me() ? 'me' : '', x.a ? 'tap' : ''].filter(Boolean).join(' ');
    if (!x.a) return `<td${cls ? ` class="${cls}"` : ''}><span class="w empty">—</span><span class="s">${FD(0)}</span></td>`;
    return `<td class="${cls}" data-cell="${i}:${c}:${k}"><span class="w${x.ok ? '' : ' x'}">${esc(x.a)}</span><span class="s">${FD(x.s)}</span>${ap && ap.res == null ? '<span class="ap">اعتراض</span>' : ''}</td>`;
  };
  return `<div class="ef-tw"><table class="ef-t" style="--n:${cols.length}"><colgroup><col class="c0">${cols.map(() => '<col>').join('')}</colgroup>
    <thead><tr><th class="h" scope="col">ستون</th>${cols.map(c => `<th scope="col"${mc(c)}>${who(c)}</th>`).join('')}</tr></thead>
    <tbody>${g.cols.map(({ k, fa }) => `<tr><th class="h" scope="row">${fa}</th>${cols.map(c => cell(c, k)).join('')}</tr>`).join('')}
      <tr><th class="h" scope="row">این دور</th>${cols.map(c => `<td${mc(c)}><span class="s big">${FD(rec.scores[c] || 0)}</span></td>`).join('')}</tr>
      <tr><th class="h" scope="row">جمع</th>${cols.map(c => { const t = upto(g, i, c); return `<td${mc(c)}><span class="s big${t === best && best > 0 ? ' ring' : ''}">${FD(t)}</span></td>`; }).join('')}</tr>
    </tbody></table></div>`;
}
function whyHtml(g, i) {
  const rec = g.results[i], out = [];
  for (const c of g.order) for (const { k, fa } of g.cols) {
    const x = rec.cells[c] && rec.cells[c][k];
    if (!x || !x.a) continue;
    if (!x.ok && x.why) out.push(`<span><span class="hand">${esc(x.a)}</span> (${fa}، ${who(c)}): ${esc(x.why)}</span>`);
    else if (x.appealed) out.push(`<span><span class="hand">${esc(x.a)}</span> (${fa}، ${who(c)}): با رأی بقیه قبول شد</span>`);
  }
  return out.length ? `<div class="ef-why">${out.join('')}</div>` : '';
}
function appealsHtml(g) {
  const aps = Object.entries(g.appeals || {});
  if (!aps.length) return '';
  const rec = g.results[g.results.length - 1];
  return `<div class="ef-aps">${aps.map(([key, ap]) => {
    const x = rec.cells[ap.c][ap.col], fa = (g.cols.find(c => c.k === ap.col) || {}).fa || '';
    const mine = ap.c === me(), canVote = !WATCH && !mine && me() && !g.players[me()].out;
    const res = ap.res == null ? '' : ap.res ? 'قبول شد ✓' : 'رد شد';
    return `<div class="ef-ap${ap.res == null ? '' : ' res'}">${who(ap.c)} به <span class="hand">${esc(x.a)}</span> در ستون ${fa} اعتراض ${mine ? 'کردی' : 'کرد'}.
      <div class="ef-apr"><span class="cnt">${res || `${FD(ap.yes)} موافق، ${FD(ap.no)} مخالف`}</span>
      ${ap.res == null && canVote ? `<span class="vb"><button data-vote="${key}" data-yes="1" aria-pressed="${ap.mine === 'yes'}">قبول است</button><button data-vote="${key}" data-yes="0" aria-pressed="${ap.mine === 'no'}">قبول نیست</button></span>` : ''}</div></div>`;
  }).join('')}</div>`;
}
function viewShow() {
  const g = G(), i = g.results.length - 1, rec = g.results[i];
  const mineBad = me() && g.cols.some(({ k }) => { const x = rec.cells[me()] && rec.cells[me()][k]; return x && x.a && !x.ok && !x.fix && !g.appeals[`${me()}:${k}`]; });
  return `<div class="ef-rhead"><b>برگ دور ${FD(i + 1)}، حرف «${esc(rec.letter)}»</b><small>${rec.by === 'ai' ? 'داور: هوش مصنوعی عبور' : 'داوری خودکار'}</small></div>
    ${appealsHtml(g)}<div class="ef-card">${tableHtml(g, i)}${whyHtml(g, i)}</div>
    ${mineBad ? '<p class="ef-hint">فکر می‌کنی داور اشتباه کرده؟ روی جواب ردشدهٔ خودت بزن و اعتراض کن.</p>' : ''}`;
}
function footShow() {
  const g = G(), act = active(), rd = act.filter(c => g.players[c].ready).length, mine = me() && g.players[me()].ready;
  const lastRound = g.round + 1 >= g.rounds_n;
  if (WATCH) return `<div class="ef-who"><b>آماده:</b><span class="ef-chip">${FD(rd)} از ${FD(act.length)}</span></div>`;
  return `<div class="ef-who"><b>آماده:</b><span class="ef-chip${rd ? ' done' : ''}">${FD(rd)} از ${FD(act.length)} نفر</span></div>
    <button class="ef-go${mine ? ' soft' : ''}" id="rdy"${mine ? ' disabled' : ''}>${mine ? 'منتظر بقیه…' : lastRound ? 'برگ نهایی' : 'دور بعد'} <span id="rdyS" class="ef-sec">${FD(secsLeft())}</span></button>`;
}

/* ---------- پایان ---------- */
function viewOver() {
  const g = G(), tot = g.totals || {}, wins = g.winners || [];
  const rank = g.order.slice().sort((a, b) => (tot[b] || 0) - (tot[a] || 0) || g.order.indexOf(a) - g.order.indexOf(b));
  const myPos = me() ? rank.indexOf(me()) + 1 : 0, n = g.results.length;
  if (tab == null || tab >= n) tab = n - 1;
  const title = !wins.length ? 'بازی بی‌برنده تمام شد' : wins.includes(me()) ? (wins.length > 1 ? 'مساوی شدی؛ تو هم بردی!' : 'تو بردی!') : `${who(wins[0])}${wins.length > 1 ? ' و بقیه' : ''} برد!`;
  return `<div class="ef-win"><div class="t"><small>پایان بازی، ${FD(n)} دور</small><h1>${title}</h1>
      <span>${wins.length ? `${FD(tot[wins[0]] || 0)} امتیاز` : 'کسی امتیاز نگرفت'}${myPos ? `؛ تو ${myPos === 1 ? 'اول' : FD(myPos) + 'ام'} شدی` : ''}</span></div>
      ${wins.length ? `<div class="ef-stamp">برنده<b>${FD(tot[wins[0]] || 0)}</b></div>` : ''}</div>
    <ol class="ef-rank">${rank.map((c, j) => `<li class="${c === me() ? 'me' : ''}${g.players[c].out ? ' out' : ''}"><span class="n">${FD(j + 1)}</span>${face(g.players[c])}<span class="nm">${who(c)}${g.players[c].out ? ' (رفت)' : ''}</span><span class="v">${FD(tot[c] || 0)}</span></li>`).join('')}</ol>
    ${n > 1 ? `<div class="ef-tabs" role="tablist">${g.results.map((r, j) => `<button role="tab" data-tab="${j}" aria-selected="${j === tab}">دور ${FD(j + 1)}، «${esc(r.letter)}»</button>`).join('')}</div>` : ''}
    ${n ? `<div class="ef-card">${tableHtml(g, tab)}${whyHtml(g, tab)}</div><p class="ef-hint">برگ همه با امتیازها در گروه هم فرستاده شد.</p>` : ''}`;
}
function footOver() {
  return `<div class="ef-acts"><button class="ef-go" id="again">${icon('send')}بازی دوباره در گروه</button><a class="ef-go soft" href="index.html">خانه</a></div>`;
}

/* ---------- چیدن صفحه ---------- */
function renderFoot() {
  const g = G(), f = $('foot');
  const html = g.over ? footOver() : ['write', 'stop'].includes(g.phase) ? footWrite() : g.phase === 'show' ? footShow() : '';
  f.hidden = !html; f.innerHTML = html;
}
function render(force) {
  const g = G(); if (!g) return;
  head();
  // نوشتن و «استپ» یک برگ اند: با استپ برگ از نو ساخته نمی شود تا نوشتن (و کیبورد) قطع نشود
  const sheetPh = ['write', 'stop'].includes(g.phase);
  const key = g.over ? 'over' : `${g.round}:${sheetPh ? 'sheet' : g.phase}:${g.phase === 'letter' ? (g.letter ? 'L' : 'W') : ''}`;
  const main = $('main');
  if (key !== built || force) {
    const was = built; built = key; phaseAt = performance.now();
    if (sheetPh && g.phase === 'write' && was) startSheet(g);
    main.innerHTML = g.over ? viewOver() : g.phase === 'letter' ? viewLetter() : sheetPh ? viewWrite() : g.phase === 'judge' ? viewJudge() : viewShow();
    if (sheetPh && !WATCH) bindWrite();
    if (g.phase === 'write' && !WATCH && !g.submitted && was) { const f = document.querySelector('#sheet input'); if (f) setTimeout(() => f.focus({ preventScroll: true }), 120); }
    window.scrollTo(0, 0);
  } else if (g.phase === 'letter' && !g.letter) main.innerHTML = viewLetter();
  else if (g.phase === 'show') {
    const sig = JSON.stringify([g.appeals, g.results.length && g.results[g.results.length - 1].scores]);
    if (main.dataset.sig !== sig) { main.dataset.sig = sig; main.innerHTML = viewShow(); }
  } else if (WATCH && ['write', 'stop'].includes(g.phase)) main.innerHTML = viewWrite();
  if (sheetPh) {
    noteWrite();
    const sh = $('sheet'); if (sh && g.submitted && !sh.classList.contains('done')) main.innerHTML = viewWrite();
  } else if (g.over || g.phase === 'show' || g.phase === 'judge' || g.phase === 'letter') note(WATCH && !g.over ? 'در حال تماشا' : null, icon('eye'));
  renderFoot();
  tickClock();
}
function startSheet(g) {
  // برگ تازه: نوشته های ذخیره شدهٔ سرور (اگر صفحه دوباره باز شده) پایهٔ برگ است
  vals = Object.assign({}, g.sheet || {}); sent = Object.assign({}, g.sheet || {}); flushed = false; lastTick = -1;
}

/* ---------- رویدادها: صدا و لرزش ---------- */
function events(list) {
  for (const e of list || []) {
    if (e.t === 'stop' && e.c !== me()) { sfx.turn(); haptic('warning'); }
    else if (e.t === 'write') { sfx.turn(); haptic('success'); }
    else if (e.t === 'scored') { sfx.coin(); haptic('light'); }
    else if (e.t === 'appeal' && e.c !== me()) { sfx.tap(); haptic('light'); }
    else if (e.t === 'win') { (e.c || []).includes(me()) ? sfx.win() : sfx.lose(); }
  }
}

async function apply(v) {
  snap = v;
  const g = v.game;
  if (!g) return;
  deadlineAt = performance.now() + (g.deadline_ms || 0);
  if (g.sheet && ['write', 'stop'].includes(g.phase) && !Object.keys(vals).length) vals = Object.assign({}, g.sheet);
  if (since && g.seq > since) events(g.events);
  since = g.seq;
  render();
  if (v.status === 'over' && !overShown) {
    overShown = true; GC.guardClose(false);
    if (!WATCH) store.set('emid', null);
    GC.refreshMe().catch(() => {});
  }
  if (v.status === 'cancelled') cancelled();
}

/* ---------- کارها ---------- */
async function act(fn, ok) {
  if (busy) return; busy = true;
  try { const v = await fn(); if (v && v.game) await apply(v); if (ok) ok(); }
  catch (e) { sfx.error(); haptic('error'); toast(errText(e)); }
  busy = false;
}
function confirmSubmit() {
  const g = G(), n = filled(), left = g.cols.length - n;
  if (!left || g.phase === 'stop') return doSubmit();
  const sh = sheet(`<div class="dlg" role="alertdialog" aria-labelledby="sT" aria-describedby="sD"><span class="dlg-ic">${PEN}</span>
    <h2 id="sT">برگ را تحویل می‌دهی؟</h2><p id="sD">${FD(left)} خانه هنوز خالی است. بعد از تحویل دیگر نمی‌توانی چیزی بنویسی؛ خانهٔ خالی صفر می‌گیرد.</p>
    <div class="dlg-acts"><button class="btn" data-close>ادامهٔ نوشتن</button><button class="btn btn-light" id="ok">تحویل بده</button></div></div>`, { center: true });
  sh.querySelector('#ok').onclick = () => { close(); doSubmit(); };
}
function doSubmit() {
  clearTimeout(saveT);
  act(() => API.submit(mid, fullSheet(), since), () => { Object.assign(sent, fullSheet()); sfx.coin(); haptic('success'); });
}
function doStop() {
  clearTimeout(saveT);
  act(() => API.stop(mid, fullSheet(), since), () => { Object.assign(sent, fullSheet()); haptic('heavy'); sfx.turn(); });
}
function cellSheet(ref) {
  const g = G(); const [i, c, k] = ref.split(':'); const rec = g.results[+i];
  const x = rec && rec.cells[c] && rec.cells[c][k]; if (!x) return;
  const fa = (g.cols.find(y => y.k === k) || {}).fa || '';
  const current = +i === g.results.length - 1 && g.phase === 'show' && !g.over;
  const key = `${c}:${k}`, ap = current ? g.appeals[key] : null;
  const canAppeal = current && c === me() && !x.ok && !x.fix && !ap;
  const canVote = current && ap && ap.res == null && !WATCH && me() && c !== me();
  const verdict = x.ok ? (x.appealed ? 'با رأی بقیه قبول شد' : x.s === 10 ? 'درست و تکی: ۱۰ امتیاز' : 'درست ولی تکراری: ۵ امتیاز') : 'رد شد: ۰ امتیاز';
  const sh = sheet(`<div class="ef-detail"><small>${fa}، ${who(c)}، دور ${FD(+i + 1)}</small><b class="hand">${esc(x.a)}</b>
      <span class="verdict ${x.ok ? 'ok' : 'no'}">${verdict}</span>${!x.ok && x.why ? `<span class="why">${esc(x.why)}</span>` : ''}
      ${ap ? `<span class="verdict">${ap.res == null ? `اعتراض در جریان: ${FD(ap.yes)} موافق، ${FD(ap.no)} مخالف` : ap.res ? 'اعتراض قبول شد' : 'اعتراض رد شد'}</span>` : ''}</div>
    ${canAppeal ? `<button class="btn btn-block" id="apB">${icon('flag')}اعتراض به داور</button><p class="hint">بقیهٔ بازیکن‌ها رأی می‌دهند؛ اگر موافق‌ها بیشتر بودند جوابت قبول می‌شود.</p>` : ''}
    ${canVote ? `<div class="dlg-acts"><button class="btn" id="vY">قبول است</button><button class="btn btn-light" id="vN">قبول نیست</button></div>` : ''}
    <button class="btn btn-light btn-block" data-close>بستن</button>`, { center: true });
  const a = sh.querySelector('#apB'); if (a) a.onclick = () => { close(); act(() => API.appeal(mid, k, since), () => toast('اعتراض ثبت شد؛ بقیه رأی می‌دهند')); };
  const y = sh.querySelector('#vY'); if (y) y.onclick = () => { close(); act(() => API.vote(mid, key, true, since)); };
  const n = sh.querySelector('#vN'); if (n) n.onclick = () => { close(); act(() => API.vote(mid, key, false, since)); };
}
document.addEventListener('click', e => {
  const t = e.target;
  if (t.closest('#stopB')) return doStop();
  if (t.closest('#subB')) return confirmSubmit();
  if (t.closest('#rdy')) return act(() => API.ready(mid, since), () => haptic('light'));
  const v = t.closest('[data-vote]'); if (v) return act(() => API.vote(mid, v.dataset.vote, v.dataset.yes === '1', since));
  const c = t.closest('[data-cell]'); if (c) return cellSheet(c.dataset.cell);
  const tb = t.closest('[data-tab]'); if (tb) { tab = +tb.dataset.tab; GC.sfx.tap(); $('main').innerHTML = viewOver(); return; }
  if (t.closest('#again')) return again(t.closest('#again'));
});
async function again(btn) {
  const w = GC.tg, at = v => w && w.isVersionAtLeast && w.isVersionAtLeast(v);
  btn.disabled = true;
  try {
    const r = await GC.data.groupShare('esmfamil');
    if (r.demo) toast('در تلگرام، گروه را انتخاب می‌کنی و کارت میز همان‌جا فرستاده می‌شود');
    else if (at('8.0') && w.shareMessage) w.shareMessage(r.id, ok => { if (ok) { sfx.turn(); haptic('success'); toast('کارت میز فرستاده شد'); } });
    else if (at('6.7') && w.switchInlineQuery) w.switchInlineQuery('esmfamil', ['groups']);
    else toast('در گروه بنویس /esmfamil');
  } catch (e) { toast(errText(e)); }
  btn.disabled = false;
}

/* ---------- خروج ---------- */
function askExit() {
  const g = G();
  if (!snap || snap.status !== 'playing' || WATCH || !g || g.over) { location.href = 'index.html'; return; }
  const sh = sheet(`<div class="dlg" role="alertdialog" aria-labelledby="dT" aria-describedby="dD">
      <span class="dlg-ic warn">${icon('exit')}</span><h2 id="dT">از بازی بیرون می‌روی؟</h2>
      <p id="dD">با خروج، از بقیهٔ دورها کنار می‌روی و برگت دیگر حساب نمی‌شود. امتیاز دورهای قبل در برگ می‌ماند.</p>
      <div class="dlg-acts"><button class="btn" data-close>ادامهٔ بازی</button><button class="btn btn-danger-soft" id="leave">${icon('exit')}خروج</button></div>
      <button class="btn btn-light btn-block dlg-home" id="home">${icon('home')}فقط برو خانه؛ بازی می‌ماند</button>
      <p class="dlg-fine">برگت تا وقتی نوشته‌ای ذخیره شده و با یک لمس از صفحهٔ خانه برمی‌گردی؛ ولی وقت دور برای کسی صبر نمی‌کند.</p></div>`, { center: true });
  sh.querySelector('#home').onclick = async () => { await save().catch(() => {}); GC.guardClose(false); location.href = 'index.html'; };
  sh.querySelector('#leave').onclick = async () => { try { await API.leave(mid); } catch (e) {} GC.guardClose(false); store.set('emid', null); location.href = 'index.html'; };
}
$('exit').onclick = askExit;
GC.back(askExit);
function dialog(title, text) {
  sheet(`<div class="dlg" role="alertdialog" aria-labelledby="dT" aria-describedby="dD"><span class="dlg-ic">${PEN}</span>
      <h2 id="dT">${title}</h2><p id="dD">${text}</p>
      <div class="dlg-acts"><a class="btn" href="esmfamil-lobby.html">اسم‌فامیل</a><a class="btn btn-light" href="index.html">خانه</a></div></div>`, { center: true, dismiss: false });
}
function cancelled() { store.set('emid', null); GC.guardClose(false); dialog('این بازی بسته شد', 'بازی پیش از تمام شدن بسته شد.'); }
function noMatch() { if (!watchMid) store.set('emid', null); dialog(watchMid ? 'این بازی را نمی‌شود دید' : 'بازی‌ای پیدا نشد', watchMid ? 'بازی تمام شده یا هنوز شروع نشده است.' : 'این بازی تمام شده یا هنوز سر برگی ننشسته‌ای.'); }

/* ---------- پرسیدن پیاپی وضعیت ---------- */
async function poll() {
  clearTimeout(pollT);
  if (snap && snap.status !== 'playing') return;
  if (!busy) {
    try { await apply(await API.match(mid, since)); }
    catch (e) { if (e.code === 'not_found') return noMatch(); }
  }
  const ph = G() && G().phase;
  pollT = setTimeout(poll, document.hidden ? 4000 : ph === 'show' || ph === 'judge' ? 1500 : 1000);
}
document.addEventListener('visibilitychange', () => { if (!document.hidden) { if (snap && snap.status === 'playing') poll(); } else save(); });
addEventListener('pagehide', () => { save(); });

async function start() {
  GC.portrait(true);
  let first;
  try { first = await API.match(mid, 0); }
  catch (e) { return e.code === 'not_found' ? noMatch() : (toast(errText(e)), setTimeout(start, 2500)); }
  WATCH = !!first.watch;
  if (first.status === 'lobby') { if (watchMid) return noMatch(); location.href = 'esmfamil-lobby.html'; return; }
  mid = first.id;
  if (!WATCH) store.set('emid', mid);
  if (first.status === 'playing' && !WATCH) GC.guardClose(true);
  since = 0;
  await apply(first);
  since = first.game ? first.game.seq : 0;
  poll();
}
document.addEventListener('pointerdown', () => GC.loadSamples && GC.loadSamples(), { once: true });
GC.mount();
start();
})();
