/* حکم — نمایش. پخش ورق، حکم، اجبار خال، برنده هر دور و امتیاز همه روی سرور است
   (game_club/hokm.py)؛ اینجا رویدادهای سرور به ترتیب پخش می شوند (پخش ورق، پرتاب
   برگ روی میز، جمع شدن دور، نتیجه دست) و ورودی کاربر (حکم، برگ) فرستاده می شود.
   بیرون از تلگرام همان API را demo-hokm.js در مرورگر شبیه سازی می کند.

   هر بازیکن خودش را پایین می بیند؛ نفر بعدی (نوبت خلاف عقربه ساعت) سمت راست، یار
   روبه رو و نفر قبلی سمت چپ. */
(() => {
const { S, fa, FD, store, face, icon, sheet, sheetHead, toast, sleep, sfx, haptic, errText, setSound, amount, mount } = GC;
const $ = id => document.getElementById(id);
const POLL_MS = 900;
const RANKS = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A'];
const SUIT_FA = ['پیک', 'دل', 'خشت', 'گشنیز'];
const SP = [
  'M12 2.4c-2.6 3.3-8.6 7-8.6 11.3 0 2.6 2 4.5 4.4 4.5 1.4 0 2.6-.6 3.4-1.6-.3 2-1 3.5-2.2 4.9h6c-1.2-1.4-1.9-2.9-2.2-4.9.8 1 2 1.6 3.4 1.6 2.4 0 4.4-1.9 4.4-4.5 0-4.3-6-8-8.6-11.3z',
  'M12 21.2C9.1 18.9 2.5 14.1 2.5 8.9 2.5 6 4.7 3.8 7.4 3.8c1.9 0 3.6 1 4.6 2.6 1-1.6 2.7-2.6 4.6-2.6 2.7 0 4.9 2.2 4.9 5.1 0 5.2-6.6 10-9.5 12.3z',
  'M12 2.2l7.6 9.8L12 21.8 4.4 12z',
  'M12 2.6a4.3 4.3 0 0 0-3.6 6.6A4.3 4.3 0 1 0 10.7 17c-.3 1.6-1 2.9-2 4h6.6c-1-1.1-1.7-2.4-2-4a4.3 4.3 0 1 0 2.3-7.8A4.3 4.3 0 0 0 12 2.6z',
];
const EMB = {
  11: 'M3 7.5l4.6 4.2L12 4.5l4.4 7.2L21 7.5l-1.7 9H4.7zM4.7 18h14.6v2H4.7z',
  10: 'M12 3.6a1.7 1.7 0 1 1 0 3.4 1.7 1.7 0 0 1 0-3.4zM5.2 6.6a1.5 1.5 0 1 1 0 3 1.5 1.5 0 0 1 0-3zm13.6 0a1.5 1.5 0 1 1 0 3 1.5 1.5 0 0 1 0-3zM5.6 16.5l-.6-5.4 3.9 2.9L12 8.6l3.1 5.4 3.9-2.9-.6 5.4zM5.6 18h12.8v2H5.6z',
  9: 'M12 3l7 3v5c0 4.6-3 8.3-7 10-4-1.7-7-5.4-7-10V6z',
};
const CROWN = EMB[11];
const suit = c => Math.floor(c / 13), rank = c => c % 13;
const red = s => s === 1 || s === 2;
const svgP = (d, fill = 'currentColor') => `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="${d}" fill="${fill}"/></svg>`;
const suitSvg = s => svgP(SP[s], red(s) ? '#D62839' : '#1C2230');
// ورق واقعی (خال چینی، تصویر دوسر، پشت ورق) از static/cards.js؛ طرحش با کلاس cards-* روی body
const C = window.GCCards;
// فیزیک برگ روی میز (جاذبه، اصطکاک، پرتاب): static/card-physics.js
const CP = window.CardPhysics;
const cardHtml = (c, cls = '', style = '') => C.face(c, cls, style);
const backHtml = (cls = '', style = '') => C.back(cls, style);
// صدای ورق هر بازیکن از سمت خودش: چپ، راست، روبه رو (وسط)
const panOf = s => { const r = rel(String(s)); return r === 1 ? .55 : r === 3 ? -.55 : 0; };
function winnerOf(trick, tr) {
  let [bi, b] = trick[0];
  for (const [i, c] of trick.slice(1)) { if (suit(c) === suit(b)) { if (rank(c) > rank(b)) [bi, b] = [i, c]; } else if (suit(c) === tr) [bi, b] = [i, c]; }
  return bi;
}

// تماشاگر (از کارت میز گروه): ?watch=شناسه؛ اگر خودش سر میز باشد همان بازیکن است
const watchMid = GC.watchId();
let WATCH = false;
let mid = watchMid || store.get('hmid', null), me = '0', snap = null, since = 0, busy = false, acting = false, pollT = null, overShown = false;
let deadlineAt = 0, turnMs = 20000, warned = false, pick = null, selfPlayed = null, pileShown = [], handShown = [];
let drag = null, dragged = false, handWait = null;
const rel = s => (+s - +me + 4) % 4;
const teamUs = () => +me % 2;
const P = () => (snap && snap.game ? snap.game.players : {});
const nameOf = s => s === me && !WATCH ? 'تو' : (P()[s] ? P()[s].name : 'بازیکن');
const seatEl = s => s === me ? document.querySelector('#meBar .avatar') : document.querySelector(`.hk-seat[data-rel="${rel(s)}"] .avatar`);
// جای هر برگ در توده وسط میز: کمی به سمت کسی که انداخته (بالا یار، راست نفر بعد، چپ نفر قبل، پایین خودم)
const SLOT = { 2: [71, 26, -5], 3: [36, 64, -13], 1: [106, 60, 13], 0: [72, 104, 4] };
// عدد شبه تصادفی ثابت از روی برگ و بازیکن (همه همان را می بینند، با هر بار رسم هم عوض نمی شود)
const hash01 = (a, b) => { let h = (a * 374761393 + b * 668265263) | 0; h = Math.imul(h ^ (h >>> 13), 1274126177); return ((h ^ (h >>> 16)) >>> 0) / 4294967296; };
const slotOf = (s, c) => {
  const [x, y, r] = SLOT[rel(String(s))], k = +s * 53 + c;
  return [x + (hash01(k, 1) * 2 - 1) * 24, y + (hash01(k, 2) * 2 - 1) * 20, r + (hash01(k, 3) * 2 - 1) * 24];
};

/* ---------- نمایش ---------- */
/* هر بخش فقط وقتی داده اش عوض شده (یا کد دیگری محتوایش را برداشته) دوباره ساخته می شود: پرسش های
   پی در پی سرور که چیزی را عوض نکرده اند به صفحه دست نمی زنند؛ نه لرزش روی گوشی، نه برگی که زیر انگشت
   است و ناگهان عوض می شود */
function stale(el, data) {
  const k = JSON.stringify(data);
  if (el._k === k && el.firstChild === el._n) return false;
  el._k = k; return true;
}
const painted = el => { el._n = el.firstChild; };   // بعد از نوشتن محتوا
function renderScore(g) {
  const us = teamUs(), tr = g.trump;
  if (!stale($('score'), [us, tr, g.score, g.target, g.tricks, WATCH])) return;
  $('score').innerHTML = `
    <div class="tm us"><span>${WATCH ? 'تیم ۱' : 'شما'}</span><b>${FD(g.score[us])}<small> / ${FD(g.target)}</small></b><em>${FD(g.tricks[us])} دست</em></div>
    <div class="hk-trump"><span class="disc${tr == null ? ' unset' : ''}" id="trumpDisc">${tr == null ? '؟' : suitSvg(tr)}</span><small>${tr == null ? 'حکم' : 'حکم ' + SUIT_FA[tr]}</small></div>
    <div class="tm"><span>${WATCH ? 'تیم ۲' : 'حریف'}</span><b>${FD(g.score[1 - us])}<small> / ${FD(g.target)}</small></b><em>${FD(g.tricks[1 - us])} دست</em></div>`;
  painted($('score'));
}
function renderSeats(g) {
  for (const s of g.order) {
    if (s === me) continue;
    const p = g.players[s], el = document.querySelector(`.hk-seat[data-rel="${rel(s)}"]`);
    const partner = p.team === teamUs(), hk = g.hakem === s, turn = g.turn === s;
    if (!stale(el, [s, p.name, p.pic, p.av, p.out, p.count, partner, hk, turn, WATCH])) continue;
    el.dataset.seat = s;
    el.classList.toggle('out', !!p.out);
    el.innerHTML = `${hk ? `<span class="hk-crown" title="حاکم">${svgP(CROWN, '#3A2A00')}</span>` : ''}${face(p, turn ? 'var(--gold)' : partner ? '#9BE3B8' : '#FFFFFF', turn ? 'timer' : '')}
      <b>${p.name}</b><em class="${hk ? 'hk' : ''}">${[partner && !WATCH ? 'یار تو' : '', hk ? 'حاکم' : '', p.out ? 'ربات جایش' : FD(p.count) + ' برگ'].filter(Boolean).join('، ')}</em>${fanHtml(p.count, rel(s))}`;
    painted(el);
  }
}
// برگ های حریف ها: یار روبه رو یک بادبزن افقی زیر اسمش، حریف های چپ و راست یک ستون برگ
// خوابیده که کمی به سمت وسط میز آمده (مثل وقتی برگ ها را جلویشان روی میز گذاشته اند)
function fanHtml(n, r) {
  n = Math.min(r === 2 ? 6 : 5, n || 0); if (!n) return '';
  const mid = (n - 1) / 2;
  if (r === 2) return `<span class="hk-fan top" aria-hidden="true">${Array.from({ length: n }, (_, i) => backHtml('',
    `transform:translate(${((i - mid) * 11).toFixed(1)}px,${(Math.abs(i - mid) * 1.6).toFixed(1)}px) rotate(${((i - mid) * 7).toFixed(1)}deg)`)).join('')}</span>`;
  const dir = r === 3 ? 1 : -1;
  return `<span class="hk-fan side ${r === 3 ? 'l' : 'r'}" aria-hidden="true">${Array.from({ length: n }, (_, i) => backHtml('',
    `transform:translate(${(dir * (6 + (i % 2) * 1.5)).toFixed(1)}px,${((i - mid) * 9.5).toFixed(1)}px) rotate(${(90 + (i - mid) * 2.2 * dir).toFixed(1)}deg)`)).join('')}</span>`;
}
// دسته برگ های برده شده هر تیم: ضربدری روی هم، با شمار
function renderStacks(tricks, drop = -1) {
  const us = teamUs();
  [[$('stackUs'), tricks ? tricks[us] : 0, drop === us], [$('stackThem'), tricks ? tricks[1 - us] : 0, drop === 1 - us]].forEach(([el, n, d]) => {
    if (!el || !stale(el, [n, d])) return;
    el.innerHTML = Array.from({ length: n }, (_, i) => backHtml(d && i === n - 1 ? 'drop' : '',
      `transform:translate(${(i * .8).toFixed(1)}px,${(-i * 1.4).toFixed(1)}px) rotate(${(i % 2 ? 90 : 0) + ((i * 37) % 9) - 4}deg);z-index:${i + 1}`)).join('')
      + (n ? `<span class="n">${FD(n)} دست</span>` : '');
    painted(el);
  });
}
function renderPile(g) {
  const pile = $('pile');
  if (g && g.phase === 'trump' && !g.over) return renderPick(g);
  const tr = g ? g.trump : null;
  const w = pileShown.length >= 2 && tr != null ? winnerOf(pileShown, tr) : null;
  const tip = w != null && pileShown.length < 4 ? `فعلا برگ ${nameOf(String(w))} بالاست` : '';
  const one = ([i, c], k) => { const [x, y, r] = slotOf(i, c); return cardHtml(c, 'tc', `left:${x}px;top:${y}px;z-index:${k + 1};transform:rotate(${r}deg)`); };
  const prev = pile._shown;
  // برگ تازه روی همان توده: فقط همان اضافه می شود و بقیهٔ برگ ها دست نمی خورند
  if (prev && pile.firstChild === pile._n && prev.length <= pileShown.length && prev.every((x, k) => x[0] === pileShown[k][0] && x[1] === pileShown[k][1])) {
    for (let k = prev.length; k < pileShown.length; k++) pile.insertAdjacentHTML('beforeend', one(pileShown[k], k));
    let t = pile.querySelector(':scope > .hk-tip');
    if (tip) { if (!t) { pile.insertAdjacentHTML('afterbegin', '<span class="hk-tip"></span>'); t = pile.firstElementChild; } t.textContent = tip; } else if (t) t.remove();
  } else pile.innerHTML = (tip ? `<span class="hk-tip">${tip}</span>` : '') + pileShown.map(one).join('');
  pile._shown = pileShown.map(x => x.slice()); pile._n = pile.firstChild;
  motion.changed();
}
function renderPick(g) {
  const pile = $('pile');
  if (g.hakem !== me || WATCH) {
    if (pile.querySelector(`.hk-choosing[data-h="${g.hakem}"]`)) return;
    const hp = g.players[g.hakem] || {};
    pile.innerHTML = `<div class="hk-choosing" data-h="${g.hakem}" role="status">
      <div class="hk-orbit"><span class="ring">${[0, 1, 2, 3].map(k => `<span class="o${k}">${suitSvg(k)}</span>`).join('')}</span>
        <span class="who">${face(hp, '#F5C451')}<i class="cr">${svgP(CROWN, '#3A2A00')}</i></span></div>
      <b>${nameOf(g.hakem)} دارد حکم می‌کند<span class="hk-dots"></span></b>
      <small>${WATCH ? 'حاکم' : hp.team === teamUs() ? 'یارت' : 'حریف'} از روی پنج برگ اولش خال حکم را انتخاب می‌کند</small></div>`;
    return;
  }
  if (pile.querySelector('.hk-pick')) { pile.querySelectorAll('[data-suit]').forEach(b => b.setAttribute('aria-pressed', String(+b.dataset.suit === pick))); syncPickBtn(); return; }
  pile.innerHTML = `<section class="hk-pick" aria-labelledby="pickT" style="position:absolute;left:1px;top:50%;translate:0 -56%">
    <span class="pick-cr">${svgP(CROWN, '#3A2A00')}</span><h2 id="pickT">تو حاکمی؛ حکم کن!</h2><p>از روی پنج برگ اولت خال حکم را بزن</p>
    <div class="suits">${[0, 1, 3, 2].map(s => `<button data-suit="${s}" aria-pressed="${s === pick}" style="color:${red(s) ? '#D62839' : '#1C2230'}">${svgP(SP[s])}${SUIT_FA[s]}</button>`).join('')}</div>
    <button class="btn ok" id="pickOk" disabled>یک خال را بزن</button></section>`;
  pile.querySelectorAll('[data-suit]').forEach(b => b.onclick = () => { pick = +b.dataset.suit; haptic('select'); renderPick(g); });
  $('pickOk').onclick = () => { if (pick == null) return; const k = pick; act(() => GC.hokm.trump(mid, k, since)); };
  syncPickBtn();
}
function syncPickBtn() {
  const b = $('pickOk'); if (!b) return;
  b.disabled = pick == null; b.textContent = pick == null ? 'یک خال را بزن' : `حکم ${SUIT_FA[pick]} باشد`;
}
function order(cards, tr) {
  // حکم اول، بعد بقیه خال ها یکی سیاه یکی قرمز؛ داخل هر خال از بزرگ به کوچک
  const base = [0, 1, 3, 2], seq = tr == null ? base : [tr, ...base.filter(s => s !== tr)];
  return cards.slice().sort((a, b) => seq.indexOf(suit(a)) - seq.indexOf(suit(b)) || rank(b) - rank(a));
}
function renderHand(g, anim = false) {
  const hand = $('hand');
  if (drag && !anim) { handWait = g; return; }   // برگی زیر انگشت است: بعد از رها کردن
  handWait = null;
  if (WATCH) { // تماشاگر برگ کسی را نمی بیند؛ فقط پشت برگ های بازیکن پایین
    const n = Math.min(13, (g.players[me] || {}).count || 0), step = n > 1 ? Math.min(6.5, 31 / (n - 1)) : 0;
    if (!stale(hand, ['w', n])) return;
    hand.innerHTML = Array.from({ length: n }, (_, i) => backHtml('', `transform:rotate(${(((n - 1) / 2 - i) * step).toFixed(2)}deg);z-index:${n - i}`)).join('');
    painted(hand); handShown = []; return;
  }
  const cards = order(g.hand || [], g.trump), n = cards.length;
  const mine = g.turn === me && g.phase === 'play', ok = new Set(mine ? g.legal : []);
  if (!stale(hand, [cards, mine, mine ? g.legal : 0]) && !anim) return;
  // نوبت من: برگ هایی که می شود انداخت جدا از بقیه، با فاصلهٔ بیشتر (هر کدام کامل دیده و زده شود)
  // و بالاتر؛ بقیه فشرده تر، پایین تر و کم رنگ
  const split = mine && ok.size > 0 && ok.size < n, GAP = 1.1;
  const wt = c => (split ? (ok.has(c) ? 2.2 : .75) : 1);
  let acc = 0;
  const pos = cards.map((c, i) => {
    if (i) { acc += (wt(c) + wt(cards[i - 1])) / 2; if (split && ok.has(c) !== ok.has(cards[i - 1])) acc += GAP; }
    return acc;
  });
  const total = n > 1 ? pos[n - 1] : 0;
  // کل بادبزن حدود ۳۱ درجه تا با ۱۳ برگ هم در عرض گوشی جا شود
  const step = total ? Math.min(split ? 9 : 6.5, (split ? 33 : 31) / total) : 0;
  const fresh = anim ? cards.filter(c => !handShown.includes(c)) : [];
  hand.innerHTML = cards.map((c, i) => {
    // دست آدم دقیق نمی چیند: هر برگ کمی کج تر یا جابه جا (ثابت برای هر برگ تا با هر رسم نلرزد)
    const a = (total / 2 - pos[i]) * step + (hash01(c, 21) * 2 - 1) * .5;
    const jx = (hash01(c, 22) * 2 - 1) * 1, jy = (hash01(c, 23) * 2 - 1) * 1.6;
    const cls = [mine ? (ok.has(c) ? 'ok' : 'no') : '', fresh.includes(c) ? 'in' : ''].filter(Boolean).join(' ');
    return cardHtml(c, cls, `--a:${a.toFixed(2)}deg;--jx:${jx.toFixed(1)}px;--jy:${jy.toFixed(1)}px;z-index:${n - i};animation-delay:${fresh.indexOf(c) * 45}ms`);
  }).join('');
  hand.querySelectorAll('.hk-card').forEach(el => { el.setAttribute('role', 'button'); el.tabIndex = el.classList.contains('ok') ? 0 : -1; });
  painted(hand); handShown = cards;
}
function renderMe(g) {
  const p = g.players[me], mine = g.turn === me && !WATCH, hakemMe = g.hakem === me && !WATCH;
  let t, sub = '';
  if (g.over) t = 'بازی تمام شد';
  else if (g.phase === 'trump') { t = hakemMe ? 'تو حاکمی' : 'حاکم: ' + nameOf(g.hakem); sub = hakemMe ? 'حکم را انتخاب کن' : 'منتظر انتخاب حکم'; }
  else if (g.phase === 'play' && mine) {
    t = 'نوبت شماست';
    if (g.led == null) sub = 'دور را تو شروع کن';
    else { const has = (g.hand || []).some(c => suit(c) === g.led); sub = `${SUIT_FA[g.led]} بازی شده؛ ` + (has ? `باید ${SUIT_FA[g.led]} بیاوری` : `${SUIT_FA[g.led]} نداری؛ حکم یا هر برگی`); }
  } else if (g.phase === 'play') { const q = g.players[g.turn] || {}; t = 'نوبت ' + nameOf(g.turn); sub = q.bot || q.out ? 'ربات فکر می‌کند…' : 'منتظر بازی…'; }
  else if (g.phase === 'collect') { t = 'دور تمام شد'; }
  else { t = 'دست بعد…'; sub = 'ورق‌ها بُر می‌خورد'; }
  const timer = (mine && g.phase === 'play') || (g.phase === 'trump' && hakemMe);
  const html = `<div class="hk-mb${timer ? ' mine' : ''}">${face(Object.assign({}, p, { name: p.name }), timer ? 'var(--gold)' : '#9BE3B8', timer ? 'timer' : '')}
    <span class="txt"><b>${t}${timer && g.deadline_ms ? '<span class="clock" id="clock"></span>' : ''}</b>${sub ? `<span>${sub}</span>` : ''}</span></div>`;
  const bar = $('meBar');
  if (stale(bar, html)) { bar.innerHTML = html; painted(bar); mount(bar); }
  setDeadline(g.deadline_ms, g._at); turnMs = g.turn_ms || 20000;
}
function renderAll(g, anim = false) {
  renderScore(g); renderSeats(g); renderPile(g); renderHand(g, anim); renderMe(g); renderStacks(g.tricks); tickTimer();
}

/* ---------- تایمر نوبت ---------- */
// مهلت نوبت: پرسش های پی در پی سرور با تاخیر شبکه کمی جابه جایش می کنند؛ فقط تغییر
// واقعی (نوبت تازه) را بپذیر تا حلقه زمان یکنواخت کم شود و هشدار یک بار بیاید
function setDeadline(ms, at) {
  const d = ms ? (at || Date.now()) + ms : 0;
  if (!d) { deadlineAt = 0; return; }
  if (!deadlineAt || Math.abs(d - deadlineAt) > 1500) warned = false;
  if (!deadlineAt || Math.abs(d - deadlineAt) > 700) deadlineAt = d;
}
function tickTimer() {
  if (!snap || !snap.game) return;
  const g = snap.game, left = deadlineAt ? Math.max(0, deadlineAt - Date.now()) : 0;
  const frac = deadlineAt ? Math.min(1, left / turnMs) : 1;
  document.querySelectorAll('.hk-seat .avatar, #meBar .avatar').forEach(a => a.style.setProperty('--t', a.classList.contains('timer') ? frac : 1));
  const ck = $('clock'); if (ck) ck.textContent = FD(Math.ceil(left / 1000)) + ' ثانیه';
  const mineNow = !WATCH && ((g.turn === me && g.phase === 'play') || (g.phase === 'trump' && g.hakem === me));
  if (mineNow && deadlineAt && frac < .25 && !warned) { warned = true; sfx.tick(); haptic('warning'); }
}
setInterval(tickTimer, 200);

/* ---------- انیمیشن ها ---------- */
function center(el) { const r = el.getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; }
function pileScale() { return parseFloat(getComputedStyle($('pile')).getPropertyValue('--pile')) || 1; }
function pilePoint(x, y) {
  const r = $('pile').getBoundingClientRect(), k = pileScale();
  return [r.left + (x + 32) * k, r.top + (y + 45) * k];
}
/* قدرت پرتاب (۰ آرام تا ۱ محکم): معمولا تصادفی؛ برگی که حکم می زند (می بُرد) همیشه محکم،
   برگی که سر می شود (از برگ های قبلی بالاتر) حدود دو سوم وقت ها محکم */
function throwPower(s, c) {
  let p = .28 + Math.random() * .5;
  const g = snap && snap.game, tr = g ? g.trump : null;
  if (pileShown.length && tr != null) {
    const led = suit(pileShown[0][1]);
    const cut = suit(c) === tr && led !== tr;
    const tops = winnerOf(pileShown.concat([[+s, c]]), tr) === +s;
    if (cut) p = .86 + Math.random() * .14;
    else if (tops && Math.random() < .65) p = .74 + Math.random() * .24;
  }
  return p;
}
/* پرتاب برگ با فیزیک (static/card-physics.js): از دست بازیکن با جاذبه و مقاومت هوا در هوا می چرخد،
   به میز می خورد، اگر محکم بود جهش کوتاهی می کند و بعد با اصطکاک (روی برگ دیگر لغزنده تر) تا ایستادن
   سُر می خورد. نقطهٔ برخورد و چرخش طوری حساب می شود که روی میز صاف، برگ درست در جای خودش بایستد؛
   اگر میز (گوشی) کج باشد، همان شیب مسیرش را عوض می کند. همهٔ حرکت از پیش حساب و با keyframe اجرا
   می شود تا روی رشتهٔ کمپوزیتور روان بماند؛ بعد برگ به موتور زندهٔ میز (motion) سپرده می شود.
   هر چه محکم تر: سریع تر، چرخش و جهش و سُر بیشتر، صدای تیزتر. power/dir: از تند کشیدن انگشت. */
async function throwCard(s, c, from, power, dir) {
  const [x, y, r] = slotOf(s, c), k = pileScale(), D = Math.PI / 180;
  const [tx, ty] = pilePoint(x, y);
  const [ox, oy] = from ? center(from) : [tx, ty + 200];
  const R = rel(String(s)), pan = panOf(s), mine = String(s) === me, P = power != null ? power : throwPower(s, c);
  const el = document.createElement('div'); el.className = 'hk-thrown';
  el.style.left = (tx - 32) + 'px'; el.style.top = (ty - 45) + 'px';
  el.innerHTML = '<i class="air"></i>' + cardHtml(c);
  $('fly').appendChild(el);
  const g = motion.geo(), sg = dir != null && Math.abs(dir) > 150 ? Math.sign(dir) : Math.random() < .5 ? -1 : 1;
  const spin = (mine ? 10 : 0) + 30 * P * sg;
  const o = { sx: (ox - g.pr.left) / g.k, sy: (oy - g.pr.top) / g.k, h0: mine ? 30 : 45, tx: x + 32, ty: y + 45,
    a0: ((mine ? r - 10 : R === 1 ? 78 : R === 3 ? -78 : 172) + spin) * D, a1: r * D, P, B: motion.bodies(), box: motion.zone(x + 32, y + 45, r * D) };
  o.T = Math.max(.2, Math.min(.46, (.16 + Math.hypot(o.tx - o.sx, o.ty - o.sy) * .0006) * (1.2 - .45 * P)));
  const A = CP.aim(o), run = CP.fly(o, A.lx, A.ly, A.w0, motion.env, true);
  const T1 = run.lands[0].t, end = run.t;
  // در هوا کج است (رو به کسی که انداخته) و هر چه پایین تر صاف تر؛ برگ حریف از کنار دستش بزرگ می شود
  const tilt = 16 + 22 * P, rx0 = R === 0 ? tilt : R === 2 ? -tilt : 0, ry0 = R === 1 ? -tilt : R === 3 ? tilt : 0;
  const keys = [], shade = [];
  for (const f of run.frames) {
    const q = f.t, off = Math.min(1, q / end), lift = Math.min(1, f.h / 25) * Math.exp(-2.5 * q);
    const grow = mine ? 1.04 - .04 * Math.min(1, q / T1) : .5 + .5 * (1 - Math.pow(1 - Math.min(1, q / (T1 * .7)), 2));
    keys.push({ offset: off, transform: `perspective(700px) translate(${((f.x - o.tx) * k).toFixed(1)}px,${((f.y - o.ty) * k).toFixed(1)}px) rotate(${(f.a / D).toFixed(1)}deg) rotateX(${(rx0 * lift).toFixed(1)}deg) rotateY(${(ry0 * lift).toFixed(1)}deg) scale(${(k * grow * (1 + f.h / 700)).toFixed(3)})` });
    // سایه روی ماهوت: نور از بالا چپ، هر چه بالاتر دورتر و کم رنگ تر (در قاب چرخیدهٔ برگ)
    const sx = f.h * .3, sy = f.h * .55, ca = Math.cos(f.a), sa = Math.sin(f.a);
    shade.push({ offset: off, opacity: f.h > .5 ? +(.2 + .25 * Math.min(1, f.h / 90)).toFixed(3) : 0, transform: `translate(${(sx * ca + sy * sa).toFixed(1)}px,${(sy * ca - sx * sa).toFixed(1)}px) scale(${(1 + f.h / 300).toFixed(3)})` });
  }
  sfx.card.throw(pan);
  run.lands.forEach((l, i) => setTimeout(() => {
    if (i) { sfx.card.place(Math.min(.5, l.v / 1600), pan); return; }
    sfx.card.place(P, pan); if (mine) haptic(P > .7 ? 'medium' : 'light');
    if (P > .85 && R !== 0) jolt();
  }, l.t * 1000));
  const last = run.lands[run.lands.length - 1];
  if (last.vh > 30) sfx.card.slide(Math.max(.15, Math.min(1, last.vh / 700)) * (last.on ? .7 : 1), pan, last.t);
  const anim = el.animate(keys, { duration: end * 1000, easing: 'linear' });
  el.firstChild.animate(shade, { duration: end * 1000, easing: 'linear' });
  await anim.finished.catch(() => {});
  motion.land(c, { x: run.x, y: run.y, a: run.a, vx: run.vx, vy: run.vy, w: run.w });
  pileShown.push([+s, c]);
  renderPile(snap && snap.game);
  el.remove();
}
// برگ محکم میز را کمی می لرزاند
function jolt() {
  const t = $('table'); if (!t) return;
  t.animate([{ transform: 'none' }, { transform: 'translate(0,1.5px)' }, { transform: 'translate(0,-.6px)' }, { transform: 'none' }], { duration: 160, easing: 'ease-out' });
}
/* جمع کردن دور: برگ ها از همان جایی که افتاده اند پشت رو به دسته برگ های تیم برنده
   سُر می خورند (دیگر وسط میز دوباره نمایش داده نمی شوند) */
async function collectTrick(w, tricks) {
  await sleep(420);
  const team = +w % 2, target = team === teamUs() ? $('stackUs') : $('stackThem');
  const [wx, wy] = target ? center(target) : [innerWidth / 2, innerHeight];
  const cards = [...$('pile').querySelectorAll('.hk-card')], k = pileScale(), pan = panOf(w);
  const D = 520;
  sfx.card.slide(.55, pan, 0);
  setTimeout(() => sfx.card.square(pan * .5), D * .85);
  const anims = cards.map((card, i) => {
    const r = card.getBoundingClientRect(), [x0, y0] = [r.left + r.width / 2, r.top + r.height / 2];
    const rot = +((card.style.transform.match(/-?[\d.]+/) || [0])[0]) + (parseFloat(card.style.rotate) || 0), jit = (i - 1.5) * 3;
    // روی برگ در مسیر کم کم پشت رو می شود (پشت ورق روی آن پیدا می شود)
    const clone = document.createElement('div'); clone.className = 'hk-thrown';
    clone.innerHTML = cardHtml(+card.dataset.card) + backHtml('', 'left:0;top:0;opacity:0');
    clone.style.left = (x0 - 32) + 'px'; clone.style.top = (y0 - 45) + 'px'; clone.style.zIndex = 30 + i;
    clone.style.transform = `rotate(${rot}deg) scale(${k})`;
    $('fly').appendChild(clone);
    const opt = { duration: D, delay: i * 45, easing: 'cubic-bezier(.45,.05,.3,1)', fill: 'backwards' };
    clone.lastElementChild.animate([{ opacity: 0 }, { opacity: 0, offset: .25 }, { opacity: 1, offset: .6 }, { opacity: 1 }], opt);
    return clone.animate([
      { transform: `rotate(${rot}deg) scale(${k})` },
      { transform: `translate(${wx - x0}px,${wy - y0}px) rotate(${(team === teamUs() ? 90 : -90) + jit}deg) scale(.47)` },
    ], opt).finished.catch(() => {}).then(() => clone.remove());
  });
  pileShown = []; renderPile(null);
  await Promise.all(anims);
  if (tricks) renderStacks(tricks, team);
}
/* بُر زدن: دسته دو نیم می شود و برگ ها یکی در میان لای هم می روند، بعد دسته جمع می شود */
async function riffle() {
  const pile = $('pile');
  pile.innerHTML = '';
  const L = pileEl(backHtml('deck', 'left:30px;top:73px;z-index:1;transform:rotate(-9deg)'));
  const Rt = pileEl(backHtml('deck', 'left:112px;top:73px;z-index:1;transform:rotate(9deg)'));
  sfx.card.shuffle();
  for (let i = 0; i < 16; i++) {
    const left = i % 2 === 0, b = pileEl(backHtml('', `left:71px;top:${73 - i * .4}px;z-index:${10 + i}`));
    b.animate([{ transform: `translate(${left ? -41 : 41}px,-10px) rotate(${left ? -9 : 9}deg)` }, { transform: `rotate(${((i * 37) % 7) - 3}deg)` }],
      { duration: 120, easing: 'cubic-bezier(.4,0,.8,1)', fill: 'forwards' });
    await sleep(36 + (i < 8 ? 10 : 0));
  }
  L.remove(); Rt.remove();
  await sleep(160);
  // جمع شدن دسته
  await Promise.all([...pile.querySelectorAll('.hk-back')].map(b => b.animate([{}, { transform: 'rotate(0deg)' }], { duration: 160, fill: 'forwards' }).finished.catch(() => {})));
  sfx.card.square(0);
  pile.innerHTML = backHtml('deck', 'left:71px;top:73px;z-index:1');
  await sleep(140);
}
async function dealAnim(rounds, first) {
  if (first) await riffle();
  const [cx, cy] = center($('pile'));
  const order4 = ['0', '1', '2', '3'];
  for (let r = 0; r < rounds; r++) {
    for (const s of order4) {
      const t = s === me ? $('hand') : seatEl(s);
      if (!t) continue;
      const [tx, ty] = center(t);
      const w = document.createElement('div'); w.innerHTML = backHtml();
      const b = w.firstElementChild; b.style.left = (cx - 32) + 'px'; b.style.top = (cy - 45) + 'px';
      $('fly').appendChild(b);
      sfx.card.flick(0, panOf(s));
      b.animate([{ transform: 'scale(.8) rotate(0deg)', opacity: 1 }, { transform: `translate(${tx - cx}px,${ty - cy}px) scale(${s === me ? .95 : .42}) rotate(${(+s * 90) + 200}deg)`, opacity: .35 }],
        { duration: 300, easing: 'cubic-bezier(.2,.7,.35,1)' }).finished.catch(() => {}).then(() => b.remove());
      await sleep(52);
    }
  }
  await sleep(260);
  $('pile').innerHTML = '';
}
/* حکم اعلام شد: خال از جای حاکم به وسط میز می پرد، با پرتو و حلقه، بعد به جای
   حکم در سربرگ می نشیند */
async function trumpReveal(s, c) {
  const pile = $('pile'), k = pileScale();
  pile.innerHTML = `<div class="hk-reveal" role="status"><span class="rays"></span><span class="big" id="bigDisc">${suitSvg(s)}</span>
    <b>حکم: ${SUIT_FA[s]}</b><small>${c === me ? 'تو حکم کردی' : (nameOf(c) + ' حکم کرد')}</small></div>`;
  const big = $('bigDisc'), from = seatEl(c);
  bar(`حکم: ${SUIT_FA[s]}`, 'هشت برگ بعدی پخش می‌شود…', c);
  sfx.card.trump(); haptic('success');
  if (from) {
    const [fx, fy] = center(from), [bx, by] = center(big);
    big.animate([{ transform: `translate(${(fx - bx) / k}px,${(fy - by) / k}px) scale(.3) rotate(-200deg)`, opacity: .3 },
      { transform: 'translate(0,0) scale(1.22) rotate(12deg)', opacity: 1, offset: .72 }, { transform: 'none' }],
    { duration: 700, easing: 'cubic-bezier(.2,.8,.3,1)' });
  }
  await sleep(1550);
  const disc = $('trumpDisc');
  if (disc) {
    const [dx, dy] = center(disc), [bx, by] = center(big);
    await big.animate([{ transform: 'none' }, { transform: `translate(${(dx - bx) / k}px,${(dy - by) / k}px) scale(.35)`, opacity: .9 }],
      { duration: 460, easing: 'cubic-bezier(.5,0,.6,1)', fill: 'forwards' }).finished.catch(() => {});
  }
  renderScore(Object.assign({}, snap.game, { trump: s }));
  const d2 = $('trumpDisc'); if (d2) d2.classList.add('pop');
  sfx.card.place();
  pile.innerHTML = '';
}

/* ---------- انتخاب حاکم ---------- */
// جای برگ های «آس کشی» جلوی هر بازیکن (مختصات داخل توده وسط)
const DRAW_AT = { 2: [71, 2, -4], 0: [71, 144, 3], 3: [2, 73, -8], 1: [140, 73, 8] };
function pileEl(html) { const w = document.createElement('div'); w.innerHTML = html; const el = w.firstElementChild; $('pile').appendChild(el); return el; }
function bar(t, sub, who) {
  const p = P()[who || me] || {};
  $('meBar').innerHTML = `<div class="hk-mb">${face(p, '#9BE3B8')}<span class="txt"><b>${t}</b>${sub ? `<span>${sub}</span>` : ''}</span></div>`;
  deadlineAt = 0;
}
async function flipTo(el, c, rot, ms) {
  el.style.transform = `rotate(${rot}deg) scaleX(0)`;
  await el.animate([{ transform: `rotate(${rot}deg) scaleX(1)` }, { transform: `rotate(${rot}deg) scaleX(0)` }], { duration: ms * .45, easing: 'ease-in' }).finished.catch(() => {});
  const f = pileEl(cardHtml(c, 'drawn', `left:${el.style.left};top:${el.style.top};z-index:${el.style.zIndex};transform:rotate(${rot}deg)`));
  el.remove();
  await f.animate([{ transform: `rotate(${rot}deg) scaleX(0)` }, { transform: `rotate(${rot}deg) scaleX(1.08)`, offset: .7 }, { transform: `rotate(${rot}deg) scaleX(1)` }], { duration: ms * .55, easing: 'ease-out' }).finished.catch(() => {});
  return f;
}
async function sweepPile() {
  const els = [...$('pile').querySelectorAll('.hk-card,.hk-back')];
  if (!els.length) return;
  sfx.card.collect();
  await Promise.all(els.map(el => {
    const x = parseFloat(el.style.left) || 71, y = parseFloat(el.style.top) || 73;
    return el.animate([{ transform: el.style.transform || 'none', opacity: 1 }, { transform: `translate(${71 - x}px,${73 - y}px) rotate(0deg) scale(.8)`, opacity: 0 }],
      { duration: 380, easing: 'cubic-bezier(.5,0,.7,1)', fill: 'forwards' }).finished.catch(() => {});
  }));
  $('pile').innerHTML = '';
}
function crownStage(s, kick, sub) {
  const p = P()[s] || {};
  return pileEl(`<div class="hk-stage" role="status"><div class="hk-crowned">${kick ? `<span class="kick">${kick}</span>` : ''}
    <span class="who">${face(p, '#F5C451')}<i class="cr">${svgP(CROWN, '#3A2A00')}</i></span>
    <b>${s === me ? 'تو حاکم شدی!' : nameOf(s) + ' حاکم شد'}</b>${sub ? `<small>${sub}</small>` : ''}</div></div>`);
}
async function crownTo(s, from) {
  const t = seatEl(s); if (!t) return;
  const [tx, ty] = center(t), [fx, fy] = from ? center(from) : center($('pile'));
  const el = document.createElement('div'); el.className = 'hk-flycrown'; el.innerHTML = svgP(CROWN, '#3A2A00');
  el.style.left = (tx - 16) + 'px'; el.style.top = (ty - 16) + 'px';
  $('fly').appendChild(el);
  await el.animate([{ transform: `translate(${fx - tx}px,${fy - ty}px) scale(1.7)`, opacity: 0 },
    { transform: `translate(${(fx - tx) / 2}px,${(fy - ty) / 2 - 70}px) scale(1.35) rotate(-18deg)`, opacity: 1, offset: .5 },
    { transform: 'translate(0,-30px) scale(.75)', opacity: 1 }], { duration: 720, easing: 'cubic-bezier(.3,.6,.4,1)' }).finished.catch(() => {});
  el.remove(); sfx.coin(); haptic(s === me ? 'success' : 'light');
}
// دست اول: برگ ها رو باز دور میز می روند تا اولین آس بیاید
async function aceDraw(e) {
  bar('انتخاب حاکم', 'برگ‌ها رو باز پخش می‌شود؛ اولین آس حاکم است');
  $('pile').innerHTML = backHtml('deck', 'left:71px;top:73px;z-index:1');
  sfx.card.shuffle(); haptic('light');
  await sleep(700);
  const n = e.draw.length, step = n > 14 ? 170 : n > 8 ? 230 : 300, cnt = {};
  let z = 2, last = null;
  for (const [s, c] of e.draw) {
    const r = rel(s), m = cnt[s] = (cnt[s] || 0) + 1, [x0, y0, a0] = DRAW_AT[r];
    const x = x0 + (r === 3 ? m * 3 : r === 1 ? -m * 3 : (m % 3 - 1) * 5), y = y0 + (r === 2 ? m * 2 : r === 0 ? -m * 2 : (m % 3 - 1) * 4);
    const rot = a0 + ((c * 37) % 9) - 4;
    const b = pileEl(backHtml('', `left:${x}px;top:${y}px;z-index:${++z};transform:rotate(${rot}deg)`));
    sfx.card.flick(0, panOf(s));
    await b.animate([{ transform: `translate(${71 - x}px,${73 - y}px) rotate(0deg) scale(.92)` }, { transform: `rotate(${rot}deg)` }],
      { duration: step * .5, easing: 'cubic-bezier(.2,.7,.3,1)' }).finished.catch(() => {});
    last = await flipTo(b, c, rot, step * .4);
    if (rank(c) !== 12) { sfx.card.place(); last.classList.add('dim'); await sleep(step * .1); }
  }
  const deck = $('pile').querySelector('.deck'); if (deck) deck.remove();
  last.classList.add('ace'); last.style.zIndex = 40;
  sfx.card.trump(); haptic('success');
  bar(e.c === me ? 'آس آمد؛ تو حاکمی!' : 'آس آمد!', `آس ${SUIT_FA[suit(last.dataset.card)]} برای ${nameOf(e.c)}`);
  await sleep(650);
  crownStage(e.c, 'اولین آس', `آس ${SUIT_FA[suit(+last.dataset.card)]}`);
  await sleep(1100);
  await crownTo(e.c, last);
  await sweepPile();
}
// دست های بعد: حاکم ماند یا به نفر بعد رسید
async function hakemAnnounce(e) {
  $('pile').innerHTML = '';
  const kept = e.prev != null && e.prev === e.c, moved = e.prev != null && e.prev !== e.c;
  bar(`دست ${FD((e.hand || 0) + 1)}`, kept ? 'تیم حاکم برد؛ حاکم همان می‌ماند' : moved ? 'تیم حاکم باخت؛ حکم به نفر بعد رسید' : 'حاکم این دست');
  sfx.turn();
  crownStage(e.c, `دست ${FD((e.hand || 0) + 1)}`, kept ? 'باز هم حاکم است' : moved ? `حاکمی از ${nameOf(e.prev)} به او رسید` : '');
  await sleep(1250);
  await crownTo(e.c, moved ? seatEl(e.prev) : $('pile'));
  $('pile').innerHTML = '';
}
async function hakemIntro(e) {
  const g = snap.game;
  pileShown = []; handShown = []; pick = null;
  $('hand').innerHTML = '';
  renderScore(Object.assign({}, g, { trump: null, tricks: [0, 0] }));
  renderSeats(Object.assign({}, g, { hakem: e.draw ? null : e.prev, turn: null }));
  if (e.draw && e.draw.length) await aceDraw(e); else await hakemAnnounce(e);
  renderSeats(Object.assign({}, g, { hakem: e.c, turn: null }));
}

/* ---------- پخش رویدادها ---------- */
async function play(e) {
  const g = snap.game;
  if (e.t === 'hakem') { await hakemIntro(e); return; }
  if (e.t === 'deal') {
    pileShown = []; handShown = [];
    $('hand').innerHTML = ''; $('pile').innerHTML = '';
    renderSeats(Object.assign({}, g, { hakem: e.hakem, turn: null }));
    bar(e.hakem === me ? 'تو حاکمی' : 'حاکم: ' + nameOf(e.hakem), 'پنج برگ اول پخش می‌شود…');
    await dealAnim(5, true);
    return;
  }
  if (e.t === 'trump') {
    await trumpReveal(e.suit, e.c);
    if (e.auto && e.c === me) toast('وقتت تمام شد؛ حکم خودکار انتخاب شد');
    pick = null;
    await dealAnim(4, false);
    return;
  }
  if (e.t === 'play') {
    if (e.c === me && selfPlayed === e.card) { selfPlayed = null; return; }
    let from = e.c === me ? $('hand').querySelector(`[data-card="${e.card}"]`) : seatEl(e.c);
    if (e.c === me && from) { const r = from.getBoundingClientRect(); const ghost = document.createElement('span'); ghost.style.cssText = `position:fixed;left:${r.left}px;top:${r.top}px;width:${r.width}px;height:${r.height}px`; $('fly').appendChild(ghost); from.remove(); from = ghost; setTimeout(() => ghost.remove(), 600); }
    await throwCard(e.c, e.card, from);
    if (e.auto && e.c === me) toast('وقتت تمام شد؛ یک برگ خودکار بازی شد');
    return;
  }
  if (e.t === 'trick') {
    await collectTrick(e.c, e.tricks);
    if (!store.get('hk_last_hint', false)) { store.set('hk_last_hint', true); toast('برای دیدن دست قبل، روی دستهٔ برگ‌های برده‌شده بزن'); }
    const us = teamUs();
    $('score').querySelectorAll('.tm em')[0].textContent = FD(e.tricks[us]) + ' دست';
    $('score').querySelectorAll('.tm em')[1].textContent = FD(e.tricks[1 - us]) + ' دست';
    return;
  }
  if (e.t === 'hand') { if (e.kot) await kotParty(e); if (e.score[e.team] < g.target) await handResult(e); return; }
  if (e.t === 'timeout' && e.c === me && snap.cfg.mode === 'stake' && e.n >= 2) { toast(e.n >= 3 ? 'سه نوبت غایب بودی؛ ربات جایت بازی می‌کند' : 'یک نوبت دیگر غیبت = بیرون رفتن از بازی'); return; }
  if (e.t === 'leave' && e.c !== me) { toast(`${nameOf(e.c)} ${e.why === 'timeout' ? 'غایب بود' : 'رفت'}؛ ربات جایش بازی می‌کند`); return; }
}
function bars(score, target) {
  const us = teamUs(), seg = (n, cls) => `<div class="hk-bar ${cls}"><span>${cls === 'us' ? 'ما' : 'حریف'}</span><span class="seg7" style="grid-template-columns:repeat(${target},minmax(0,1fr))">${Array.from({ length: target }, (_, i) => `<i class="${i < n ? 'on' : ''}"></i>`).join('')}</span><b>${FD(n)}</b></div>`;
  return `<div class="hk-bars">${seg(score[us], 'us')}${seg(score[1 - us], 'them')}</div>`;
}
/* کوت (هفت به صفر): میز می لرزد، برگ های برده شده از دستهٔ تیم برنده به هوا می روند و دوباره رویش
   می بارند، و «کوت!» طلایی وسط میز می درخشد. با «کاهش حرکت» گوشی فقط نوشته می آید. */
async function kotParty(e) {
  const won = e.team === teamUs(), stack = won ? $('stackUs') : $('stackThem');
  const [cx, cy] = center($('pile')), [sx, sy] = stack ? center(stack) : [cx, cy];
  const fx = document.createElement('div'); fx.className = 'hk-kotfx' + (won ? '' : ' them'); fx.setAttribute('role', 'status');
  fx.style.left = cx + 'px'; fx.style.top = cy + 'px';
  fx.innerHTML = `<b>${won ? (e.pts === 3 ? 'حاکم کوت شد!' : 'کوت!') : 'کوت شدید!'}</b><span>هفت به صفر · ${FD(e.pts)} امتیاز برای ${won ? 'شما' : 'حریف'}</span>`;
  $('fly').appendChild(fx);
  haptic(won ? 'success' : 'warning');
  if (reduced()) { await sleep(1600); fx.remove(); return; }
  const t = $('table');
  if (t) t.animate([{ transform: 'none' }, { transform: 'translate(-5px,2px) rotate(-.5deg)' }, { transform: 'translate(5px,-2px) rotate(.5deg)' }, { transform: 'translate(-2px,1px)' }, { transform: 'none' }], { duration: 440, easing: 'ease-out' });
  sfx.card.shuffle();
  setTimeout(() => (won ? sfx.win() : sfx.card.collect()), 380);
  setTimeout(() => sfx.card.square(0), 1350);
  fx.animate([{ transform: 'translate(-50%,-50%) scale(.3)', opacity: 0 }, { transform: 'translate(-50%,-50%) scale(1.15)', opacity: 1, offset: .25 },
    { transform: 'translate(-50%,-50%) scale(1)', opacity: 1, offset: .38 }, { transform: 'translate(-50%,-50%) scale(1)', opacity: 1, offset: .85 },
    { transform: 'translate(-50%,-50%) scale(1.06)', opacity: 0 }], { duration: 2100, easing: 'ease-out', fill: 'forwards' });
  // برگ ها دور تا دور وسط میز پخش می شوند، می چرخند و یکی یکی روی دسته برمی گردند
  const N = 21, flights = [];
  for (let i = 0; i < N; i++) {
    const w = document.createElement('div'); w.className = 'hk-thrown';
    w.innerHTML = backHtml('', 'left:0;top:0');
    w.style.left = (sx - 32) + 'px'; w.style.top = (sy - 45) + 'px';
    $('fly').appendChild(w);
    const a = i / N * Math.PI * 2 + Math.random() * .3, rr = 55 + Math.random() * 95;
    const dx = cx - sx + Math.cos(a) * rr, dy = cy - sy + Math.sin(a) * rr * .8 - 50, r1 = (Math.random() * 2 - 1) * 540;
    flights.push(w.animate([
      { transform: 'translate(0,0) rotate(0deg) scale(.47)' },
      { transform: `translate(${dx.toFixed(0)}px,${dy.toFixed(0)}px) rotate(${(r1 * .6).toFixed(0)}deg) scale(${(.8 + Math.random() * .3).toFixed(2)})`, offset: .42, easing: 'cubic-bezier(.3,.6,.4,1)' },
      { transform: `translate(${(dx * .92).toFixed(0)}px,${(dy * .92 + 22).toFixed(0)}px) rotate(${(r1 * .75).toFixed(0)}deg) scale(.78)`, offset: .58 },
      { transform: `translate(0,0) rotate(${(r1 + (i % 2 ? 90 : 0)).toFixed(0)}deg) scale(.47)` },
    ], { duration: 1500, delay: i * 22, easing: 'cubic-bezier(.45,.05,.35,1)', fill: 'backwards' }).finished.catch(() => {}).then(() => w.remove()));
  }
  await Promise.all(flights);
  await sleep(300);
  fx.remove();
}
async function handResult(e) {
  const us = teamUs(), won = e.team === us, g = snap.game;
  const nh = e.team === +e.hakem % 2 ? e.hakem : String((+e.hakem + 1) % 4);
  won ? (sfx.coin(), haptic('success')) : (sfx.nomove(), haptic('warning'));
  const kot = e.kot ? `<span class="kot">${e.pts === 3 ? 'حاکم کوت شد! ۳ امتیاز' : 'کوت! ۲ امتیاز'}</span>` : `<p>${won ? 'یک امتیاز برای شما' : 'یک امتیاز برای حریف'}</p>`;
  sheet(`<div class="hk-res" role="status">
      <span class="ic${won ? '' : ' lost'}">${svgP(CROWN)}</span>
      <h2>${won ? 'این دست مال شما شد' : 'این دست را باختید'}</h2>${kot}
      <div class="hk-tricks"><div><b>${FD(e.tricks[us])}</b><span>دست ما</span></div><div><b>${FD(e.tricks[1 - us])}</b><span>دست حریف</span></div></div>
      ${bars(e.score, g.target)}
      <p>حاکم دست بعد: <b>${nameOf(nh)}</b></p></div>`, { center: true, dismiss: false });
  await sleep(3000);
  GC.close();
}

/* ---------- دست قبل: زدن (یا نگه داشتن) روی دستهٔ برگ های برده شده ----------
   ۴ برگ دور قبل هر کدام سمت کسی که انداخته، با شمارهٔ ترتیب بازی و تاج روی برندهٔ دور (game.last_trick از سرور).
   زدن: باز می ماند تا زدن بعدی یا ۴ ثانیه؛ نگه داشتن: تا انگشت برداشته شود. */
const esc = v => String(v).replace(/[&<>"]/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[ch]));
let lastEl = null, lastAt = 0, lastT = 0;
function hideLast() { clearTimeout(lastT); if (lastEl) { lastEl.remove(); lastEl = null; } }
function showLast() {
  const lt = snap && snap.game && snap.game.last_trick;
  if (!lt || !lt.cards || !lt.cards.length) { toast('هنوز دوری جمع نشده'); return false; }
  hideLast();
  const box = $('center').getBoundingClientRect();
  const dx = Math.min(84, box.width / 2 - 14), dy = Math.max(40, Math.min(68, box.height / 2 - 46)), fs = dy < 56 ? 38 : 44;
  const AT = { 0: [0, dy], 1: [dx, 0], 2: [0, -dy], 3: [-dx, 0] }, w = String(lt.winner);
  lastEl = document.createElement('div'); lastEl.className = 'hk-last';
  lastEl.setAttribute('role', 'dialog'); lastEl.setAttribute('aria-label', 'دست قبل');
  lastEl.innerHTML = '<span class="t">دست قبل</span>' + lt.cards.map(([seat, c], i) => {
    const s = String(seat), [x, y] = AT[rel(s)];
    return `<div class="slot${s === w ? ' win' : ''}" style="left:calc(50% + ${x}px);top:calc(50% + ${y}px)">${cardHtml(+c, '', `position:relative;font-size:${fs}px`)}`
      + `<b><i class="no">${FD(i + 1)}</i><span>${esc(nameOf(s))}</span></b>${s === w ? `<i class="cr">${svgP(CROWN)}</i>` : ''}</div>`;
  }).join('');
  $('center').appendChild(lastEl);
  sfx.card.flip(); haptic('light');
  return true;
}
for (const id of ['stackUs', 'stackThem']) {
  const el = $(id);
  el.setAttribute('role', 'button'); el.tabIndex = 0; el.setAttribute('aria-label', 'دیدن دست قبل');
  el.addEventListener('pointerdown', e => { e.preventDefault(); if (lastEl) { hideLast(); lastAt = 0; return; } if (showLast()) lastAt = performance.now(); });
  el.addEventListener('pointerup', () => {
    if (!lastEl || !lastAt) return;
    if (performance.now() - lastAt > 350) hideLast(); else lastT = setTimeout(hideLast, 4000);
  });
  el.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); lastEl ? hideLast() : showLast(); } });
}
document.addEventListener('pointerdown', e => { if (lastEl && !e.target.closest('.hk-stack')) hideLast(); }, true);
addEventListener('keydown', e => { if (e.key === 'Escape') hideLast(); });

/* ---------- گفتگوی سر میز: نوار و پیام های شناور مثل بیلیارد (tchat.js) ---------- */
const QUICK = ['سلام!', 'خوش‌بازی!', 'آفرین یار', 'حکم خوبی بود', 'زود باش', 'یک دست دیگه؟'];
const chat = TChat.init({
  btn: $('chatBtn'), badge: $('chatBadge'), quick: QUICK, face: m => face(m, '#FFFFFF'),
  rest: () => { const r = $('meBar').getBoundingClientRect(); return r.height ? innerHeight - r.top + 8 : 140; },
  canSend: () => !!mid,
  send: async text => { await GC.hokm.chat(mid, text); return (await GC.hokm.match(mid, since, chat.last())).chat; },
  onNew: () => sfx.tap(), onError: e => { sfx.error(); toast(errText(e)); },
});
const chatIn = (list, quiet) => chat.add(list, quiet);
function endChat() { chat.end(); $('chatBtn').hidden = true; }

/* ---------- همگام سازی با سرور ---------- */
async function apply(next, anim = true) {
  if (next && next.chat && !overShown && next.status !== 'over' && next.status !== 'cancelled') chatIn(next.chat);
  if (next && next.status === 'cancelled') return cancelled();
  if (!next || !next.game) return;
  next.game._at = Date.now();   // زمان رسیدن پاسخ: مهلت و «آماده» از همین لحظه حساب می شوند، نه بعد از انیمیشن
  busy = true;
  try {
    snap = Object.assign({}, snap || {}, next);
    const g = next.game, evs = (g.events || []).filter(e => e.seq > since).sort((a, b) => a.seq - b.seq);
    const dealt = evs.some(e => e.t === 'deal' || e.t === 'trump');
    for (const e of evs) { if (anim) await play(e); since = e.seq; }
    since = Math.max(since, g.seq);
    // بعد از تمام شدن دور، سرور تا شروع دور بعد برگ ها را نگه می دارد؛ آن ها جمع شده اند و دوباره نشان داده نمی شوند
    pileShown = g.phase === 'collect' ? [] : (g.trick || []).map(([i, c]) => [+i, c]);
    renderAll(g, dealt);
    if (next.status === 'over' && !overShown) { overShown = true; over(next); }
  } finally { busy = false; }
}
async function poll() {
  clearTimeout(pollT);
  if (document.hidden || overShown) { pollT = setTimeout(poll, POLL_MS); return; }
  if (!busy && !acting) {
    try { await apply(await GC.hokm.match(mid, since, chat.last())); }
    catch (e) { if (e.code === 'not_found') return noMatch(); }
  }
  pollT = setTimeout(poll, POLL_MS);
}
async function act(fn, before) {
  if (acting || busy) return;
  acting = true;
  try {
    const [res] = await Promise.all([fn(), before ? before() : null]);
    await apply(res);
  } catch (e) {
    sfx.error(); haptic('error'); toast(errText(e));
    if (selfPlayed != null) { pileShown = pileShown.filter(([, c]) => c !== selfPlayed); selfPlayed = null; }
    $('hand')._k = null;                     // برگی که از دست برداشته شده بود برگردد
    if (snap && snap.game) renderAll(snap.game);
  } finally { acting = false; }
}
// flick: از تند کشیدن انگشت (قدرت پرتاب و سمت چرخش)؛ با زدن ساده خالی است
function playCard(el, flick) {
  if (!el || acting || busy || !snap || WATCH) return;
  const g = snap.game, c = +el.dataset.card;
  if (g.turn !== me || g.phase !== 'play' || !g.legal.includes(c)) { el.style.translate = ''; el.classList.remove('drag'); return; }
  selfPlayed = c;
  $('hand').querySelectorAll('.hk-card').forEach(x => x.classList.remove('ok', 'no'));
  const r = el.getBoundingClientRect(), ghost = document.createElement('span');
  ghost.style.cssText = `position:fixed;left:${r.left}px;top:${r.top}px;width:${r.width}px;height:${r.height}px`;
  $('fly').appendChild(ghost); el.remove(); setTimeout(() => ghost.remove(), 700);
  act(() => GC.hokm.play(mid, c, since), () => throwCard(me, c, ghost, flick && flick.P, flick && flick.dx));
}
// برگ را بزن، یا بگیر و رو به میز بکش و رها کن (کشیدن کوتاه = برگشت سر جایش)
$('hand').addEventListener('click', e => { if (dragged) { dragged = false; return; } playCard(e.target.closest('.hk-card.ok')); });
$('hand').addEventListener('pointerdown', e => {
  const el = e.target.closest('.hk-card.ok'); if (!el || acting || busy) return;
  drag = { el, x: e.clientX, y: e.clientY, id: e.pointerId, moved: false, hist: [[e.timeStamp, e.clientX, e.clientY]] };
});
$('hand').addEventListener('pointermove', e => {
  if (!drag || e.pointerId !== drag.id) return;
  const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
  drag.hist.push([e.timeStamp, e.clientX, e.clientY]); if (drag.hist.length > 8) drag.hist.shift();
  if (!drag.moved && Math.hypot(dx, dy) < 8) return;
  if (!drag.moved) { drag.moved = true; drag.el.classList.add('drag'); try { drag.el.setPointerCapture(drag.id); } catch (err) {} }
  drag.el.style.translate = `${dx.toFixed(0)}px ${Math.min(12, dy).toFixed(0)}px`;
});
const endDrag = e => {
  if (!drag || (e && e.pointerId !== drag.id)) return;
  const d = drag; drag = null;
  const w = handWait; handWait = null;
  // لمس ساده: اگر برگی انداخته نشد (کلیک بعدش)، دستِ تازه رسیده همین حالا کشیده می شود
  if (!d.moved) { if (w) setTimeout(() => { if (!acting && !drag) renderHand(w); }, 0); return; }
  dragged = true; setTimeout(() => { dragged = false; }, 60);
  const dy = e ? e.clientY - d.y : 0;
  if (dy < -55) {
    // سرعت انگشت در ۱۰۰ میلی ثانیهٔ آخر: کشیدن آرام = پرتاب آرام، تند کشیدن = محکم
    const h = d.hist, z = h[h.length - 1], a = h.find(p => z[0] - p[0] <= 100) || h[0], t = Math.max(16, z[0] - a[0]) / 1000;
    const vx = (z[1] - a[1]) / t, vy = (z[2] - a[2]) / t;
    playCard(d.el, { P: Math.max(.05, Math.min(1, (-vy - 250) / 2200)), dx: vx });
  }
  else { d.el.classList.remove('drag'); d.el.style.translate = ''; if (w) renderHand(w); }
};
$('hand').addEventListener('pointerup', endDrag);
$('hand').addEventListener('pointercancel', () => {
  if (!drag) return;
  drag.el.classList.remove('drag'); drag.el.style.translate = ''; drag = null;
  const w = handWait; handWait = null; if (w) renderHand(w);
});
$('hand').addEventListener('keydown', e => { if ((e.key === 'Enter' || e.key === ' ') && e.target.classList.contains('ok')) { e.preventDefault(); e.target.click(); } });
document.addEventListener('visibilitychange', () => { if (!document.hidden) poll(); });

/* ---------- پایان، خروج ---------- */
// صفحه پایان: تمام صفحه روی رنگ میز خود بازیکن. برد: نور طلایی چرخان، ریزش خال ها و مدال تاج؛
// باخت: آرام و سرد. دو تیم با چهره ها، امتیاز و جایزه با شمارش بالا می آیند.
const reduced = () => { try { return matchMedia('(prefers-reduced-motion: reduce)').matches; } catch (e) { return false; } };
function countUp(root) {
  root.querySelectorAll('[data-n]').forEach(el => {
    const to = +el.dataset.n, pre = el.dataset.pre || '', dur = 900, t0 = performance.now() + (+el.dataset.at || 0);
    if (reduced() || !to) { el.textContent = pre + FD(to); return; }
    el.textContent = pre + FD(0);
    const step = t => { const k = Math.min(1, Math.max(0, (t - t0) / dur)), e = 1 - Math.pow(1 - k, 3); el.textContent = pre + FD(Math.round(to * e)); if (k < 1) requestAnimationFrame(step); };
    requestAnimationFrame(step);
  });
}
function confetti(n = 34) {
  const cols = ['#F5C451', '#FFFFFF', '#E0263E', '#FFE29A', '#9BE3B8'];
  return `<div class="e-cf" aria-hidden="true">${Array.from({ length: n }, (_, i) => {
    const x = (i * 37 + 11) % 100, d = (i * 0.23) % 2.6, dur = 3.2 + (i * 7 % 10) / 5, sz = 12 + (i * 5 % 4) * 3, r = (i * 53) % 360, sway = ((i % 2) ? 1 : -1) * (14 + i % 5 * 6);
    return `<i style="left:${x}%;--d:${d.toFixed(2)}s;--cft:${dur.toFixed(2)}s;--r:${r}deg;--w:${sway}px;width:${sz}px;height:${sz}px;color:${cols[i % cols.length]}">${svgP(SP[i % 4])}</i>`;
  }).join('')}</div>`;
}
function watchEnd(v) {
  const g = v.game, P = g.players || {}, t = g.winner;
  const names = k => g.order.filter(s => (P[s] || {}).team === k).map(s => P[s].name).join(' و ');
  sfx.win();
  GC.watchOver('hokm', 'بازی تمام شد', t == null ? 'بازی پیش از رسیدن به امتیاز آخر بسته شد.'
    : `${names(+t % 2)} با ${FD(g.score[+t % 2])} به ${FD(g.score[1 - +t % 2])} بردند.`);
}
function over(v) {
  if (WATCH) return watchEnd(v);
  endChat();
  const g = v.game, r = v.result || {}, won = !!r.won, us = teamUs();
  GC.guardClose(false); store.set('hmid', null);
  won ? (sfx.win(), haptic('success')) : (sfx.lose(), haptic('warning'));
  const secs = Math.max(0, Math.round(Date.now() / 1000 - g.started)), st = g.stats || { tricks: 0, hakem: 0 };
  const stake = v.cfg.mode === 'stake', ended = g.winner == null;
  const P = g.players || {}, seat = k => String((+me + k) % 4), pa = P[seat(2)] || {}, o1 = P[seat(1)] || {}, o2 = P[seat(3)] || {};
  const oppsLeft = o1.out && o2.out, mine = g.score[us], theirs = g.score[1 - us];
  const kind = ended ? 'draw' : won ? 'win' : 'lose';
  const title = ended ? 'بازی تمام شد' : won ? (oppsLeft ? 'حریف‌ها رفتند؛ بردید!' : 'بردید!') : 'این بار نشد';
  const line = ended ? 'بازی پیش از رسیدن به امتیاز آخر بسته شد.'
    : won ? `شما و ${pa.name || 'یارت'} با ${FD(mine)} به ${FD(theirs)} بردید.` : `${o1.name || 'حریف'} و ${o2.name || 'یارش'} با ${FD(theirs)} به ${FD(mine)} بردند.`;
  const team = (cls, a, b, names, score, win) => `<div class="e-tm ${cls}${win ? ' e-won' : ''}">
      ${win ? `<span class="e-rib">${svgP(CROWN)}برنده</span>` : ''}
      <span class="e-duo">${face(a, cls === 'us' ? '#9BE3B8' : 'var(--surface)')}${face(b, cls === 'us' ? '#9BE3B8' : 'var(--surface)')}</span>
      <b class="e-sc" data-n="${score}" data-at="350">${FD(score)}</b><span class="e-nm">${names}</span></div>`;
  const reward = stake
    ? (won ? `<div class="e-rw e-gold"><span class="e-coin">${GC.coin()}</span><span><b data-n="${r.prize || 0}" data-pre="+" data-at="700">+${fa(r.prize || 0)}</b><small>جایزه به کیف امتیازت اضافه شد</small></span></div>`
      : ended ? `<div class="e-rw"><span class="e-ic">${icon('wallet')}</span><span><b>ورودی برگشت</b><small>${fa(v.cfg.entry)} امتیاز به کیفت برگشت</small></span></div>`
      : `<div class="e-rw e-dim"><span class="e-ic">${icon('wallet')}</span><span><b>−${fa(r.lost || v.cfg.entry)} امتیاز</b><small>ورودی این بازی؛ دست بعد جبران کن</small></span></div>`)
    : `<div class="e-rw"><span class="e-ic">${icon('users')}</span><span><b>بازی آزاد</b><small>${won ? 'جایزه نداشت؛ ولی برد برد است!' : 'چیزی از دست ندادی'}</small></span></div>`;
  const el = document.createElement('div');
  el.className = 'hk-end gc-ui ' + kind; el.setAttribute('role', 'dialog'); el.setAttribute('aria-modal', 'true'); el.setAttribute('aria-labelledby', 'endT');
  el.innerHTML = `${kind === 'win' && !reduced() ? confetti() : ''}
    <div class="e-in">
      <div class="e-hd">${kind === 'win' ? '<div class="e-rays" aria-hidden="true"></div>' : ''}
        <span class="e-medal" aria-hidden="true"><span>${svgP(kind === 'lose' ? SP[0] : CROWN)}</span></span>
        <small class="e-kick">پایان بازی · تا ${FD(g.target)} امتیاز</small>
        <h1 id="endT">${title}</h1><p>${line}</p>
      </div>
      <div class="e-teams">
        ${team('us', Object.assign({}, P[me], { name: 'شما' }), pa, `شما و ${pa.name || 'یار'}`, mine, !ended && won)}
        <span class="e-vs">به</span>
        ${team('them', o1, o2, `${o1.name || 'حریف'} و ${o2.name || 'حریف'}`, theirs, !ended && !won)}
      </div>
      ${reward}
      <div class="e-stats">
        <div><span class="e-ic">${svgP(SP[3])}</span><b data-n="${st.tricks}" data-at="900">${FD(st.tricks)}</b><small>دست بردی</small></div>
        <div><span class="e-ic">${svgP(CROWN)}</span><b data-n="${st.hakem}" data-at="900">${FD(st.hakem)}</b><small>بار حاکم شدی</small></div>
        <div><span class="e-ic">${icon('clock')}</span><b>${FD(Math.floor(secs / 60))}:${FD(String(secs % 60).padStart(2, '0'))}</b><small>مدت بازی</small></div>
      </div>
      <div class="e-acts">
        <a class="e-go" href="hokm-lobby.html">${won ? 'یک بازی دیگر' : 'دوباره بازی کن'}</a>
        <a class="e-home" href="index.html">${icon('home')}خانه</a>
      </div>
    </div>`;
  document.body.appendChild(el);
  countUp(el);
  if (kind === 'win' && stake && r.prize) setTimeout(() => { sfx.coin(); haptic('success'); }, 1500);
  GC.refreshMe().catch(() => {});
}
function cancelled() {
  if (overShown) return;
  if (WATCH) { overShown = true; GC.watchOver('hokm', 'این میز بسته شد', 'بازی پیش از تمام شدن بسته شد.'); return; }
  overShown = true; endChat(); GC.guardClose(false); store.set('hmid', null); GC.refreshMe().catch(() => {});
  sheet(`<div class="dlg" role="alertdialog" aria-labelledby="dT" aria-describedby="dD"><span class="dlg-ic">${icon('table')}</span>
      <h2 id="dT">این میز بسته شد</h2><p id="dD">پشتیبانی این میز را بست و ورودی همه به کیف امتیازشان برگشت.</p>
      <div class="dlg-acts"><a class="btn" href="hokm-lobby.html">میز تازه</a><a class="btn btn-light" href="index.html">خانه</a></div></div>`, { center: true, dismiss: false });
}
function noMatch() {
  if (watchMid) { GC.watchOver('hokm', 'این بازی را نمی‌شود دید', 'بازی تمام شده یا هنوز شروع نشده است.'); return; }
  store.set('hmid', null);
  sheet(`<div class="dlg" role="alertdialog" aria-labelledby="dT" aria-describedby="dD"><span class="dlg-ic">${icon('table')}</span>
      <h2 id="dT">میزی پیدا نشد</h2><p id="dD">این بازی تمام شده یا هنوز سر میزی ننشسته‌ای.</p>
      <div class="dlg-acts"><a class="btn" href="hokm-lobby.html">یک میز بساز</a><a class="btn btn-light" href="index.html">خانه</a></div></div>`, { center: true, dismiss: false });
}
// خروج: برگه تیره به رنگ میز؛ «تو ← ربات» نشان می دهد چه می شود، دو راه روشن و ادامه بازی
let exitEl = null;
function closeExit() { if (!exitEl) return; const el = exitEl; exitEl = null; el.classList.add('out'); setTimeout(() => el.remove(), 220); }
function askExit() {
  if (exitEl) { closeExit(); return; }
  if (!snap || snap.status === 'over' || WATCH) { location.href = 'index.html'; return; }
  const stake = snap.cfg.mode === 'stake', g = snap.game, P = g.players || {}, pa = P[String((+me + 2) % 4)] || {};
  haptic('light');
  exitEl = document.createElement('div'); exitEl.className = 'hk-exit gc-ui';
  exitEl.innerHTML = `<div class="x-sh" role="alertdialog" aria-modal="true" aria-labelledby="exT" aria-describedby="exD">
      <span class="x-grab" aria-hidden="true"></span>
      <div class="x-swap" aria-hidden="true">${face(Object.assign({}, P[me], { name: 'شما' }), '#9BE3B8')}<span class="x-arr"><i></i><i></i><i></i></span>${face({ bot: true, av: 9 }, 'var(--gold)')}</div>
      <h2 id="exT">از بازی بیرون می‌روی؟</h2>
      <p id="exD">اگر بروی، ربات جای تو کنار ${pa.name || 'یارت'} بازی می‌کند.</p>
      <div class="x-opts">
        <button class="x-opt" id="exHome"><span class="x-ic">${icon('home')}</span><span><b>فعلا برو خانه</b><small>سر میز می‌مانی و از صفحهٔ خانه با یک لمس برمی‌گردی</small></span></button>
        <button class="x-opt x-bad" id="exLeave"><span class="x-ic">${icon('exit')}</span><span><b>ترک بازی</b><small>${stake ? `ورودی ${fa(snap.cfg.entry)} امتیاز برنمی‌گردد و از جایزه سهمی نداری` : 'بازی آزاد است؛ امتیازی از دست نمی‌دهی'}</small></span></button>
      </div>
      <button class="x-stay" id="exStay">ادامهٔ بازی</button>
      <p class="x-fine">تا نیستی نوبت‌هایت خودکار بازی می‌شود${stake ? '؛ در بازی امتیازی سه نوبت غیبت پشت‌سرهم یعنی بیرون رفتن از بازی' : ''}.</p>
    </div>`;
  document.body.appendChild(exitEl);
  const el = exitEl;
  el.addEventListener('click', e => { if (e.target === el) closeExit(); });
  el.querySelector('#exStay').onclick = () => { sfx.tap(); closeExit(); };
  el.querySelector('#exHome').onclick = () => { GC.guardClose(false); location.href = 'index.html'; };
  let armed = 0;
  el.querySelector('#exLeave').onclick = async ev => {
    const b = ev.currentTarget;
    // بازی امتیازی: یک لمس دیگر برای اطمینان
    if (stake && Date.now() - armed > 3000) { armed = Date.now(); b.classList.add('x-arm'); b.querySelector('b').textContent = 'مطمئنی؟ دوباره بزن'; haptic('warning'); setTimeout(() => { if (b.isConnected && Date.now() - armed >= 2900) { b.classList.remove('x-arm'); b.querySelector('b').textContent = 'ترک بازی'; } }, 3000); return; }
    b.disabled = true;
    try { await GC.hokm.leave(mid); } catch (e) {}
    GC.guardClose(false); store.set('hmid', null); location.href = 'index.html';
  };
  setTimeout(() => { const f = el.querySelector('#exStay'); if (f) f.focus({ preventScroll: true }); }, 50);
}
$('exit').onclick = askExit;
GC.back(askExit);
const sndBtn = $('snd');
const syncSnd = () => { sndBtn.innerHTML = icon(S.sound ? 'soundOn' : 'soundOff'); sndBtn.setAttribute('aria-pressed', String(!!S.sound)); sndBtn.setAttribute('aria-label', S.sound ? 'خاموش کردن صدا' : 'روشن کردن صدا'); };
sndBtn.onclick = () => { setSound(!S.sound); syncSnd(); if (S.sound) GC.loadSamples(); };
syncSnd();
document.addEventListener('pointerdown', () => GC.loadSamples(), { once: true });

/* ---------- اندازه: توده وسط میز هر چه جا باشد ---------- */
function fit() {
  const c = $('center').getBoundingClientRect();
  const k = Math.max(.72, Math.min(1.12, c.height / 236, c.width / 206));
  $('pile').style.setProperty('--pile', k.toFixed(3));
  motion.resize();
}
GC.onFit(fit);   // فقط وقتی اندازهٔ صفحه واقعا عوض شد؛ باز شدن کیبورد گفتگو بازی را دوباره نمی چیند

/* ---------- برگ های وسط میز: میز واقعی با جاذبه ----------
   گوشی همان میز است: کج که شود، برگ ها با جاذبه سُر می خورند (اصطکاک ایستا نگهشان می دارد تا شیب
   کافی شود؛ برگ روی برگ زودتر از برگ روی ماهوت راه می افتد)، به لبهٔ میدان بازی وسط میز می خورند و
   برمی گردند و همان جا که ایستادند می مانند. تکان تند گوشی هم با لختی برگ ها را جابه جا می کند. هر برگ را می شود
   با انگشت هل داد (از گوشه بگیری دورش می چرخد) و پرت کرد؛ برگ های رویش با آن می آیند مگر تند کشیده
   شود. همه فقط نمایش است و به سرور نمی رسد؛ با جمع شدن دور تمام می شود. فیزیک: static/card-physics.js.
   «میز صاف» حالت عادی دست است: اول هر دور زود و وسط دور آرام دنبال گوشی می آید، پس فقط کج کردن
   و تکان دادن برگ ها را می بَرد، نه طرز گرفتن گوشی.
   حسگر: شتاب سنج تلگرام (نسخهٔ ۸ به بعد؛ جهت و واحدش از چند نمونهٔ اول شناخته می شود)، اگر نبود
   زاویهٔ گوشی از تلگرام، بیرون از تلگرام devicemotion یا deviceorientation مرورگر. با تنظیم «تکان
   برگ‌ها» در نمایه یا «کاهش حرکت» گوشی حسگر روشن نمی شود (کشیدن و پرتاب همچنان فیزیکی است). */
const motion = (() => {
  const pile = $('pile'), tw = window.Telegram && Telegram.WebApp || null;
  const tg8 = !!(tw && tw.isVersionAtLeast && tw.isVersionAtLeast('8.0'));
  const R2D = 180 / Math.PI, GPX = CP.G * CP.PX;
  const env = { ax: 0, ay: 0, gn: GPX };
  const bodies = new Map(), landed = new Map();
  let order = [], geo = null, raf = 0, prev = 0, held = null, live = false, src = '';

  // ---- حسگر: بردار «پایین» (شتاب ظاهری روی برگ، متر بر ثانیه^۲) در محورهای گوشی: x راست، y بالا، z بیرون صفحه
  let cal = [], sign = 0, unit = 1, flipB = null, F = null, ref = null, lastT = 0;
  const dot = (p, q) => p[0] * q[0] + p[1] * q[1] + p[2] * q[2];
  const unitv = v => { const m = Math.hypot(v[0], v[1], v[2]) || 1; return [v[0] / m, v[1] / m, v[2] / m]; };
  /* حساسیت: کج کردن گوشی و تکان تند هر کدام فقط بخشی از اثر واقعی را دارند، تا لرزش و جابه جایی
     معمولی دست برگ ها را نبرد. با TILT = .8 برگ روی برگ از حدود ۱۳ درجه و روی ماهوت از حدود ۲۱ درجه
     کج کردن نگه داشته راه می افتد (پیش تر ۱۰ و ۱۷) و آرام تر سُر می خورد. G: بخش آرام (جاذبه و کجی)،
     F - G: تکان تند (لختی). */
  const TILT = .8, SHAKE = .3;
  let G = null;
  function feed(A) {
    const now = performance.now(), dt = lastT ? Math.min(.5, (now - lastT) / 1000) : 0; lastT = now;
    const lp = (v, to, tau) => v ? v.map((x, i) => x + (to[i] - x) * (1 - Math.exp(-dt / tau))) : to.slice();
    F = lp(F, A, .06);                                 // لرزش حسگر
    G = lp(G, F, .15);
    const m = Math.hypot(G[0], G[1], G[2]); if (m < 2) return;
    const u = [G[0] / m, G[1] / m, G[2] / m];
    ref = ref ? unitv(ref.map((v, i) => v + (u[i] - v) * (1 - Math.exp(-dt / (bodies.size ? 6 : .5))))) : u;
    // صفحهٔ میز وقتی صاف است عمود بر ref است؛ محور X راست صفحه، Y رو به بالای صفحه
    const X = unitv([1 - ref[0] * ref[0], -ref[0] * ref[1], -ref[0] * ref[2]]);
    if (Math.abs(ref[0]) > .95) return;              // گوشی روی لبهٔ کناری اش
    const Y = [X[1] * ref[2] - X[2] * ref[1], X[2] * ref[0] - X[0] * ref[2], X[0] * ref[1] - X[1] * ref[0]];
    const L = [F[0] - G[0], F[1] - G[1], F[2] - G[2]];
    env.ax = (dot(G, X) * TILT + dot(L, X) * SHAKE) * CP.PX;
    env.ay = -(dot(G, Y) * TILT + dot(L, Y) * SHAKE) * CP.PX;
    env.gn = Math.max(.2 * CP.G, dot(G, ref)) * CP.PX;
    if (bodies.size && Math.hypot(env.ax, env.ay) > CP.CARD.s * env.gn * .9) kick();
    sheen(dot(G, X) / m, -dot(G, Y) / m);
  }
  /* برق ورق ها: با کج کردن گوشی نواری از نور روی برگ های دست و میز رد می شود (رنگین کمانی روی سرباز و
     بی‌بی و شاه؛ CSS: .hk-card .gloss::after). جای نوار در امتداد عمود بر آن، از کجی نسبت به حالت عادی دست؛
     گوشی که آرام بماند نور هم کم کم می رود. هر تغییر همهٔ برگ ها را دوباره می کشد، پس حداکثر ۲۰ بار در ثانیه
     و فقط وقتی واقعا عوض شده. */
  const shHosts = [$('hand'), pile];
  let shP = 9, shAt = 0;
  function sheen(x, y) {
    const p = Math.max(-1.2, Math.min(1.2, (x * .906 + y * .423) * 3)), now = performance.now();
    if (Math.abs(p - shP) < .03 || now - shAt < 50) return;
    shP = p; shAt = now;
    for (const h of shHosts) { h.style.setProperty('--sp', p.toFixed(3)); h.style.setProperty('--so', Math.min(1, Math.abs(p) * 3).toFixed(2)); }
  }
  // شتاب سنج: بعضی گوشی ها نیروی تکیه گاه را می دهند (رو به بالا)، بعضی خود جاذبه را؛ بعضی متر بر ثانیه^۲، بعضی g.
  // گوشی معمولا رو به آدم و سر بالا گرفته می شود، پس «پایین» باید سمت پایین صفحه و پشت گوشی باشد.
  function accel(x, y, z) {
    if (!isFinite(x) || !isFinite(y) || !isFinite(z) || x == null) return;
    if (!sign) {
      cal.push([x, y, z]); if (cal.length < 6) return;
      const M = [0, 1, 2].map(i => cal.reduce((a, v) => a + v[i], 0) / cal.length), m = Math.hypot(...M);
      cal = [];
      if (m < .5 || (m > 1.6 && m < 5)) return useOrient();   // جاذبه در آن نیست: از زاویهٔ گوشی
      unit = m <= 1.6 ? CP.G : 1; sign = M[1] + M[2] > 0 ? -1 : 1;
    }
    feed([x * sign * unit, y * sign * unit, z * sign * unit]);
  }
  // زاویهٔ گوشی (درجه، قرارداد W3C). اگر جلو و عقب برعکس گزارش شود (گوشیِ سر بالا منفی)، برگردانده می شود
  function orient(b, g) {
    if (b == null || g == null || !isFinite(b) || !isFinite(g)) return;
    if (flipB == null) { cal.push(b); if (cal.length < 5) return; flipB = cal.sort((p, q) => p - q)[2] < -10; cal = []; }
    const B = (flipB ? -b : b) / R2D, Gm = g / R2D, cb = Math.cos(B);
    feed([CP.G * cb * Math.sin(Gm), -CP.G * Math.sin(B), -CP.G * cb * Math.cos(Gm)]);
  }
  const tgAcc = () => { const a = tw.Accelerometer; accel(a.x, a.y, a.z); };
  const tgOri = () => { const o = tw.DeviceOrientation; if (o.beta != null) orient(o.beta * R2D, o.gamma * R2D); };
  // مرورگر گاهی اول یک رویداد خالی می فرستد؛ فقط اگر پشت سر هم خالی آمد سراغ زاویهٔ گوشی برو
  let empty = 0;
  const webAcc = e => { const a = e.accelerationIncludingGravity; if (a && a.x != null) { empty = 0; accel(a.x, a.y, a.z); } else if (++empty > 8) useOrient(); };
  const webOri = e => orient(e.beta, e.gamma);
  function begin(s) {
    src = s; cal = []; sign = 0; flipB = null; F = G = null; ref = null; lastT = 0;
    try {
      if (s === 'tgAcc') { tw.onEvent('accelerometerChanged', tgAcc); tw.Accelerometer.start({ refresh_rate: 25 }, ok => { if (!ok && src === s) useOrient(); }); }
      else if (s === 'tgOri') { tw.onEvent('deviceOrientationChanged', tgOri); tw.DeviceOrientation.start({ refresh_rate: 25 }, ok => { if (!ok && src === s) end(); }); }
      else if (s === 'webAcc') addEventListener('devicemotion', webAcc);
      else if (s === 'webOri') addEventListener('deviceorientation', webOri);
    } catch (e) { end(); }
  }
  function end() {
    const s = src; src = '';
    try {
      if (s === 'tgAcc') { tw.offEvent('accelerometerChanged', tgAcc); tw.Accelerometer.stop(); }
      else if (s === 'tgOri') { tw.offEvent('deviceOrientationChanged', tgOri); tw.DeviceOrientation.stop(); }
      else if (s === 'webAcc') removeEventListener('devicemotion', webAcc);
      else if (s === 'webOri') removeEventListener('deviceorientation', webOri);
    } catch (e) {}
    env.ax = env.ay = 0; env.gn = GPX;
  }
  function useOrient() {
    const tg = src.startsWith('tg'); end();
    if (live) begin(tg && tw.DeviceOrientation ? 'tgOri' : 'webOri');
  }
  function start() {
    if (live || S.tilt === false || reduced() || document.hidden) return;
    live = true;
    begin(tg8 && tw.Accelerometer ? 'tgAcc' : tg8 && tw.DeviceOrientation ? 'tgOri' : 'DeviceMotionEvent' in window ? 'webAcc' : 'webOri');
  }
  function stop() {
    if (!live) return;
    live = false; end();
    shP = 9; for (const h of shHosts) h.style.setProperty('--so', '0');
  }
  document.addEventListener('visibilitychange', () => document.hidden ? stop() : start());
  addEventListener('pagehide', stop);
  if (tw) { try { tw.onEvent('deactivated', stop); tw.onEvent('activated', start); } catch (e) {} }

  // ---- برگ های میز: هر برگ یک جسم با جای خودش (bx,by,br) که از آن جابه جا شده
  /* میدان بازی: فضای خالی وسط میز، بین بازیکن چپ و راست، زیر برگ های یار و بالای نوار من (با کمی
     فاصله)؛ برگ ها از آن بیرون نمی روند و زیر بازیکن ها و برگ هایشان نمی خزند. میدان هر برگ جای خود
     آن برگ را هم دارد: روی صفحهٔ باریک که بازیکن ها نزدیک ترند، برگ سر جای خودش می ماند ولی جلوتر نمی رود. */
  function zone(x, y, a) {
    const z = (geo || measure()).box, c = Math.cos(a), s = Math.sin(a);
    let l = z.l, r = z.r, t = z.t, b = z.b;
    for (const [px, py] of [[-32, -45], [32, -45], [32, 45], [-32, 45]]) {
      const X = x + px * c - py * s, Y = y + px * s + py * c;
      l = Math.min(l, X - 1); r = Math.max(r, X + 1); t = Math.min(t, Y - 1); b = Math.max(b, Y + 1);
    }
    return { l, t, r, b };
  }
  function measure() {
    const pr = pile.getBoundingClientRect(), k = pileScale(), t = $('table'), tr = t.getBoundingClientRect();
    const wall = (parseFloat(getComputedStyle(t).getPropertyValue('--wall')) || 6) + 2, gap = 6;
    const rects = sel => [...t.querySelectorAll(sel)].map(e => e.getBoundingClientRect()).filter(r => r.width && r.height);
    const l = Math.max(tr.left + wall, ...rects('.hk-seat[data-rel="3"] > *').map(r => r.right + gap));
    const r = Math.min(tr.right - wall, ...rects('.hk-seat[data-rel="1"] > *').map(r => r.left - gap));
    const top = Math.max(tr.top + wall, ...rects('.hk-seat[data-rel="2"] > *').map(r => r.bottom + gap));
    const bot = Math.min(tr.bottom - wall, ...rects('#meBar > *, #chatBtn').map(r => r.top - gap));
    geo = { pr, k, box: { l: (l - pr.left) / k, r: (r - pr.left) / k, t: (top - pr.top) / k, b: (bot - pr.top) / k } };
    for (const b of order) b.box = null;
    return geo;
  }
  function paint(b) {
    const t = `${(b.x - b.bx).toFixed(2)}px ${(b.y - b.by).toFixed(2)}px`, r = `${((b.a - b.br) * R2D).toFixed(2)}deg`;
    if (t !== b.pt) { b.pt = t; b.el.style.translate = t; }
    if (r !== b.pr) { b.pr = r; b.el.style.rotate = r; }
  }
  function sync() {
    const seen = new Set();
    for (const el of pile.querySelectorAll(':scope > .hk-card.tc')) {
      const c = +el.dataset.card; seen.add(c);
      let b = bodies.get(c);
      if (!b) {
        const bx = parseFloat(el.style.left) + 32, by = parseFloat(el.style.top) + 45, br = +((el.style.transform.match(/-?[\d.]+/) || [0])[0]) / R2D;
        b = { c, bx, by, br, x: bx, y: by, a: br, vx: 0, vy: 0, w: 0, ax: 0, ay: 0, z: +el.style.zIndex || 0 };
        const h = landed.get(c); if (h) { Object.assign(b, h); landed.delete(c); }
        bodies.set(c, b);
      }
      if (b.el !== el) { b.el = el; b.pt = b.pr = ''; paint(b); }
    }
    for (const c of bodies.keys()) if (!seen.has(c)) bodies.delete(c);
    order = [...bodies.values()].sort((p, q) => p.z - q.z);
    if (held && !bodies.has(held.c)) held = null;
  }
  // صدای برگ ها: خوردن به لبهٔ میز و راه افتادن روی ماهوت
  let hitAt = 0, slideAt = 0;
  const panX = x => Math.max(-1, Math.min(1, (x - 103) / 140)) * .6;
  function feel(hits) {
    const now = performance.now();
    let top = null; for (const h of hits) if (!top || h.v > top.v) top = h;
    if (top && top.v > 120 && now - hitAt > 90) { hitAt = now; sfx.card.place(Math.min(1, top.v / 1800) * .7, panX(top.b.x)); if (top.v > 900) haptic('light'); }
    for (const b of order) {
      const v = Math.hypot(b.vx, b.vy);
      if (b.slip && !b.ws && !b.held && v > 80 && now - slideAt > 250) { slideAt = now; sfx.card.slide(Math.min(1, v / 1200) * .6, panX(b.x), .01); }
      b.ws = b.slip;
    }
  }
  function frame(t) {
    raf = 0;
    if (order.length && !order[0].el.isConnected) sync();   // توده بی خبر خالی شد (پخش ورق، انتخاب حکم)
    if (!order.length) { prev = 0; return; }
    const g = geo || measure(), dt = prev ? Math.min(.05, (t - prev) / 1000) : 1 / 60; prev = t;
    for (const b of order) if (!b.box) b.box = zone(b.bx, b.by, b.br);
    const n = Math.max(1, Math.ceil(dt * 240)), h = dt / n, hits = [];
    let moving = false;
    for (let i = 0; i < n; i++) moving = CP.step(order, env, h, g.box, hits);
    for (const b of order) paint(b);
    feel(hits);
    if (moving || held) raf = requestAnimationFrame(frame); else prev = 0;
  }
  function kick() { if (!raf && order.length) raf = requestAnimationFrame(frame); }

  // ---- انگشت: برگ را از همان نقطه که گرفته شده هل می دهد؛ رها کردن با سرعت انگشت پرتش می کند
  const local = e => { const g = geo || measure(); return [(e.clientX - g.pr.left) / g.k, (e.clientY - g.pr.top) / g.k]; };
  pile.addEventListener('pointerdown', e => {
    const el = e.target.closest('.hk-card.tc');
    if (!el || e.button > 0 || held) return;
    sync();
    const b = bodies.get(+el.dataset.card); if (!b) return;
    const [x, y] = local(e), c = Math.cos(b.a), s = Math.sin(b.a), dx = x - b.x, dy = y - b.y;
    b.pin = { x, y, rx: dx * c + dy * s, ry: dy * c - dx * s };
    b.held = true; b.vx = b.vy = b.w = 0;
    held = { c: b.c, id: e.pointerId, x, y, moved: false };
    try { el.setPointerCapture(e.pointerId); } catch (err) {}
    el.classList.add('held'); kick();
  });
  document.addEventListener('pointermove', e => {
    if (!held || e.pointerId !== held.id) return;
    const b = bodies.get(held.c); if (!b) { held = null; return; }
    const [x, y] = local(e), box = b.box || zone(b.bx, b.by, b.br);
    b.pin.x = Math.max(box.l + 6, Math.min(box.r - 6, x)); b.pin.y = Math.max(box.t + 6, Math.min(box.b - 6, y));
    if (!held.moved && Math.hypot(x - held.x, y - held.y) > 6) { held.moved = true; haptic('light'); }
    kick();
  });
  const drop = e => {
    if (!held || e.pointerId !== held.id) return;
    const b = bodies.get(held.c); held = null;
    if (b) {
      b.held = false; delete b.pin;
      const v = Math.hypot(b.vx, b.vy); if (v > 2600) { b.vx *= 2600 / v; b.vy *= 2600 / v; }
      if (b.el) b.el.classList.remove('held');
    }
    kick();
  };
  document.addEventListener('pointerup', drop);
  document.addEventListener('pointercancel', drop);

  return {
    start, stop, env,
    changed() { geo = null; sync(); kick(); },     // توده عوض شد (برگ تازه یا جمع شدن دور)؛ میدان هم دوباره اندازه گرفته می شود
    land(c, s) { landed.set(c, s); },               // برگ پرتاب شده با همان جا و سرعتی که ایستاد به میز سپرده می شود
    bodies: () => order,
    geo: () => geo || measure(),
    zone,
    resize() { geo = null; },
  };
})();
motion.start();

/* ---------- شروع ---------- */
function applyStyle(st) {
  if (!st) return;
  const b = document.body;
  b.className = b.className.replace(/\b(tbl|cards)-[a-z]\b/g, '').trim();
  b.classList.add('tbl-' + (st.table || 'a'), 'cards-' + (st.cards || 'a'));
}
async function start() {
  GC.portrait(true);
  GC.data.me().then(m => applyStyle(m && m.style)).catch(() => {});
  $('meBar').innerHTML = '<div class="hk-mb solo"><span class="txt"><b>در حال وصل شدن…</b></span></div>';
  fit();
  let first;
  try { first = await GC.hokm.match(mid, 0, 0); }
  catch (e) { return e.code === 'not_found' ? noMatch() : (toast(errText(e)), setTimeout(start, 2500)); }
  WATCH = !!first.watch;
  if (first.status === 'lobby') { if (watchMid) return noMatch(); location.href = 'hokm-lobby.html'; return; }
  if (first.status === 'cancelled') return cancelled();
  mid = first.id; me = first.me;
  if (WATCH) GC.watchPill(); else store.set('hmid', mid);
  if (first.cfg.mode === 'stake' && first.status === 'playing') GC.guardClose(true);
  chatIn(first.chat, true);
  const g = first.game;
  const evs = (g.events || []).slice().sort((a, b) => a.seq - b.seq);
  const intro = [...evs].reverse().find(e => e.t === 'hakem');
  if (first.status === 'playing' && intro && !evs.some(e => e.seq > intro.seq && e.t === 'play')) {
    // هنوز هیچ برگی در این دست بازی نشده: انتخاب حاکم و حکم را از اول ببیند
    snap = first; since = intro.seq - 1; pileShown = [];
    renderScore(Object.assign({}, g, { trump: null })); renderSeats(Object.assign({}, g, { hakem: null, turn: null }));
    $('hand').innerHTML = ''; $('pile').innerHTML = ''; bar('میز آماده است', 'الان حاکم انتخاب می‌شود…');
    mount(); fit();
    await apply(first);
    poll();
    return;
  }
  snap = first; since = g.seq; pileShown = g.phase === 'collect' ? [] : (g.trick || []).map(([i, c]) => [+i, c]);
  renderAll(g, true); mount(); fit();
  if (first.status === 'over') { overShown = true; over(first); return; }
  poll();
}
start();
})();
