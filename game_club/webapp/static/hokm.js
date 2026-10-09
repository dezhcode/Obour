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
function cardHtml(c, cls = '', style = '') {
  const s = suit(c), r = rank(c), fc = r >= 9 && r <= 11;
  return `<div class="hk-card${red(s) ? ' red' : ''}${cls ? ' ' + cls : ''}" data-card="${c}" style="${style}" role="img" aria-label="${RANKS[r]} ${SUIT_FA[s]}">`
    + `<span class="ix"><b>${RANKS[r]}</b>${svgP(SP[s])}</span>${fc ? `<span class="em">${svgP(EMB[r])}</span>` : `<span class="wm">${svgP(SP[s])}</span>`}</div>`;
}
function winnerOf(trick, tr) {
  let [bi, b] = trick[0];
  for (const [i, c] of trick.slice(1)) { if (suit(c) === suit(b)) { if (rank(c) > rank(b)) [bi, b] = [i, c]; } else if (suit(c) === tr) [bi, b] = [i, c]; }
  return bi;
}

let mid = store.get('hmid', null), me = '0', snap = null, since = 0, busy = false, acting = false, pollT = null, overShown = false;
let deadlineAt = 0, turnMs = 20000, warned = false, pick = null, selfPlayed = null, pileShown = [], handShown = [];
const rel = s => (+s - +me + 4) % 4;
const teamUs = () => +me % 2;
const P = () => (snap && snap.game ? snap.game.players : {});
const nameOf = s => s === me ? 'تو' : (P()[s] ? P()[s].name : 'بازیکن');
const seatEl = s => s === me ? document.querySelector('#meBar .avatar') : document.querySelector(`.hk-seat[data-rel="${rel(s)}"] .avatar`);
// جای هر برگ در توده وسط میز: کمی به سمت کسی که انداخته (بالا یار، راست نفر بعد، چپ نفر قبل، پایین خودم)
const SLOT = { 2: [71, 26, -5], 3: [36, 64, -13], 1: [106, 60, 13], 0: [72, 104, 4] };
const slotOf = (s, c) => { const [x, y, r] = SLOT[rel(String(s))]; return [x, y, r + ((c * 37) % 7) - 3]; };

/* ---------- نمایش ---------- */
function renderScore(g) {
  const us = teamUs(), tr = g.trump;
  $('score').innerHTML = `
    <div class="tm us"><span>ما</span><b>${FD(g.score[us])}<small> / ${FD(g.target)}</small></b><em>${FD(g.tricks[us])} برگ</em></div>
    <div class="hk-trump"><span class="disc${tr == null ? ' unset' : ''}" id="trumpDisc">${tr == null ? '؟' : suitSvg(tr)}</span><small>${tr == null ? 'حکم' : 'حکم ' + SUIT_FA[tr]}</small></div>
    <div class="tm"><span>حریف</span><b>${FD(g.score[1 - us])}<small> / ${FD(g.target)}</small></b><em>${FD(g.tricks[1 - us])} برگ</em></div>`;
}
function renderSeats(g) {
  for (const s of g.order) {
    if (s === me) continue;
    const p = g.players[s], el = document.querySelector(`.hk-seat[data-rel="${rel(s)}"]`);
    const partner = p.team === teamUs(), hk = g.hakem === s, turn = g.turn === s;
    el.dataset.seat = s;
    el.classList.toggle('out', !!p.out);
    el.innerHTML = `${hk ? `<span class="hk-crown" title="حاکم">${svgP(CROWN, '#3A2A00')}</span>` : ''}${face(p, turn ? 'var(--gold)' : partner ? '#9BE3B8' : '#FFFFFF', turn ? 'timer' : '')}
      <b>${p.name}</b><em class="${hk ? 'hk' : ''}">${[partner ? 'یار تو' : '', hk ? 'حاکم' : '', p.out ? 'ربات جایش' : FD(p.count) + ' برگ'].filter(Boolean).join('، ')}</em>`;
  }
  for (const s of Object.keys(bubbles)) showBubble(s);
}
function renderPile(g) {
  const pile = $('pile');
  if (g && g.phase === 'trump' && !g.over) return renderPick(g);
  const tr = g ? g.trump : null;
  const w = pileShown.length >= 2 && tr != null ? winnerOf(pileShown, tr) : null;
  let tip = '';
  if (w != null && pileShown.length < 4) tip = `<span class="hk-tip">فعلا برگ ${nameOf(String(w))} بالاست</span>`;
  pile.innerHTML = tip + pileShown.map(([i, c], k) => {
    const [x, y, r] = slotOf(i, c), win = w === i;
    return cardHtml(c, win ? 'win' : '', `left:${x}px;top:${y}px;z-index:${k + 1};transform:rotate(${r}deg)`).replace('</div>', win ? `<span class="crown">${svgP(CROWN, '#3A2A00')}</span></div>` : '</div>');
  }).join('');
}
function renderPick(g) {
  const pile = $('pile');
  if (g.hakem !== me) {
    pile.innerHTML = `<div class="hk-wait" style="position:absolute;inset:0;justify-content:center"><span class="spinner"></span><span>${nameOf(g.hakem)} حاکم است<br>و دارد حکم را انتخاب می‌کند…</span></div>`;
    return;
  }
  if (pile.querySelector('.hk-pick')) { pile.querySelectorAll('[data-suit]').forEach(b => b.setAttribute('aria-pressed', String(+b.dataset.suit === pick))); syncPickBtn(); return; }
  pile.innerHTML = `<section class="hk-pick" aria-labelledby="pickT" style="position:absolute;left:1px;top:0">
    <h2 id="pickT">حکم را انتخاب کن</h2><p>تو حاکمی؛ به پنج برگ اولت نگاه کن</p>
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
  const cards = order(g.hand || [], g.trump), n = cards.length;
  const mine = g.turn === me && g.phase === 'play', ok = new Set(mine ? g.legal : []);
  // کل بادبزن حدود ۳۱ درجه تا با ۱۳ برگ هم در عرض گوشی جا شود
  const step = n > 1 ? Math.min(6.5, 31 / (n - 1)) : 0;
  const fresh = anim ? cards.filter(c => !handShown.includes(c)) : [];
  hand.innerHTML = cards.map((c, i) => {
    const a = ((n - 1) / 2 - i) * step;
    const cls = [mine ? (ok.has(c) ? 'ok' : 'no') : '', fresh.includes(c) ? 'in' : ''].filter(Boolean).join(' ');
    return cardHtml(c, cls, `--a:${a.toFixed(2)}deg;z-index:${i + 1};animation-delay:${fresh.indexOf(c) * 45}ms`);
  }).join('');
  hand.querySelectorAll('.hk-card').forEach(el => { el.setAttribute('role', 'button'); el.tabIndex = el.classList.contains('ok') ? 0 : -1; });
  handShown = cards;
}
function renderMe(g) {
  const p = g.players[me], mine = g.turn === me;
  let t, sub = '';
  if (g.over) t = 'بازی تمام شد';
  else if (g.phase === 'trump') { t = g.hakem === me ? 'تو حاکمی' : 'حاکم: ' + nameOf(g.hakem); sub = g.hakem === me ? 'حکم را انتخاب کن' : 'منتظر انتخاب حکم'; }
  else if (g.phase === 'play' && mine) {
    t = 'نوبت توست';
    if (g.led == null) sub = 'دور را تو شروع کن';
    else { const has = (g.hand || []).some(c => suit(c) === g.led); sub = `${SUIT_FA[g.led]} بازی شده؛ ` + (has ? `باید ${SUIT_FA[g.led]} بیاوری` : `${SUIT_FA[g.led]} نداری؛ حکم یا هر برگی`); }
  } else if (g.phase === 'play') { const q = g.players[g.turn] || {}; t = 'نوبت ' + nameOf(g.turn); sub = q.bot || q.out ? 'ربات فکر می‌کند…' : 'منتظر بازی…'; }
  else if (g.phase === 'collect') { t = 'دور تمام شد'; }
  else { t = 'دست بعد…'; sub = 'ورق‌ها بُر می‌خورد'; }
  const timer = (mine && g.phase === 'play') || (g.phase === 'trump' && g.hakem === me);
  $('meBar').innerHTML = `<div class="pill${timer ? ' mine' : ''}">${face(Object.assign({}, p, { name: p.name }), timer ? 'var(--gold)' : '#9BE3B8', timer ? 'timer' : '')}
    <span class="txt"><b>${t}${timer && g.deadline_ms ? '<span class="clock" id="clock"></span>' : ''}</b>${sub ? `<span>${sub}</span>` : ''}</span></div>`;
  deadlineAt = g.deadline_ms ? Date.now() + g.deadline_ms : 0; turnMs = g.turn_ms || 20000; warned = false;
}
function renderAll(g, anim = false) {
  renderScore(g); renderSeats(g); renderPile(g); renderHand(g, anim); renderMe(g); mount($('meBar'));
}

/* ---------- تایمر نوبت ---------- */
setInterval(() => {
  if (!snap || !snap.game) return;
  const g = snap.game, left = deadlineAt ? Math.max(0, deadlineAt - Date.now()) : 0;
  const frac = deadlineAt ? Math.min(1, left / turnMs) : 1;
  document.querySelectorAll('.hk-seat .avatar, #meBar .avatar').forEach(a => a.style.setProperty('--t', a.classList.contains('timer') ? frac : 1));
  const ck = $('clock'); if (ck) ck.textContent = FD(Math.ceil(left / 1000)) + ' ثانیه';
  const mineNow = (g.turn === me && g.phase === 'play') || (g.phase === 'trump' && g.hakem === me);
  if (mineNow && deadlineAt && frac < .25 && !warned) { warned = true; sfx.tick(); haptic('warning'); }
}, 200);

/* ---------- انیمیشن ها ---------- */
function center(el) { const r = el.getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; }
function pileScale() { return parseFloat(getComputedStyle($('pile')).getPropertyValue('--pile')) || 1; }
function pilePoint(x, y) {
  const r = $('pile').getBoundingClientRect(), k = pileScale();
  return [r.left + (x + 32) * k, r.top + (y + 45) * k];
}
async function throwCard(s, c, from) {
  const [x, y, r] = slotOf(s, c), k = pileScale();
  const [tx, ty] = pilePoint(x, y);
  const [ox, oy] = from ? center(from) : [tx, ty + 200];
  const wrap = document.createElement('div'); wrap.innerHTML = cardHtml(c);
  const el = wrap.firstElementChild; el.style.left = (tx - 32) + 'px'; el.style.top = (ty - 45) + 'px';
  $('fly').appendChild(el);
  sfx.card.throw();
  const r0 = s === me ? 0 : (rel(s) === 1 ? 70 : rel(s) === 3 ? -70 : 160);
  const anim = el.animate([
    { transform: `translate(${ox - tx}px,${oy - ty}px) rotate(${r0}deg) scale(${s === me ? 1 : .45})` },
    { transform: `translate(0,0) rotate(${r + (r - r0) * -.08}deg) scale(${k * 1.06})`, offset: .82 },
    { transform: `translate(0,0) rotate(${r}deg) scale(${k})` },
  ], { duration: 420, easing: 'cubic-bezier(.18,.7,.3,1)' });
  setTimeout(() => { sfx.card.place(); if (s === me) haptic('light'); }, 330);
  await anim.finished.catch(() => {});
  pileShown.push([+s, c]);
  renderPile(snap && snap.game);
  el.remove();
}
async function collectTrick(w) {
  renderPile(Object.assign({}, snap.game, { phase: 'play' }));
  await sleep(650);
  const target = seatEl(w);
  const [wx, wy] = target ? center(target) : [innerWidth / 2, innerHeight];
  const cards = [...$('pile').querySelectorAll('.hk-card')];
  sfx.card.collect();
  const anims = cards.map(card => {
    const r = card.getBoundingClientRect(), clone = card.cloneNode(true);
    clone.style.left = (r.left + r.width / 2 - 32) + 'px'; clone.style.top = (r.top + r.height / 2 - 45) + 'px';
    const [cx, cy] = [r.left + r.width / 2, r.top + r.height / 2];
    const rot = (card.style.transform.match(/-?[\d.]+/) || [0])[0];
    clone.style.transform = `rotate(${rot}deg) scale(${pileScale()})`;
    $('fly').appendChild(clone);
    return clone.animate([{ transform: `rotate(${rot}deg) scale(${pileScale()})`, opacity: 1 },
      { transform: `translate(${wx - cx}px,${wy - cy}px) rotate(${+rot * 2}deg) scale(.35)`, opacity: 0 }],
    { duration: 420, easing: 'cubic-bezier(.5,0,.7,1)' }).finished.catch(() => {}).then(() => clone.remove());
  });
  pileShown = []; renderPile(null);
  await Promise.all(anims);
}
async function dealAnim(rounds, first) {
  if (first) { sfx.card.shuffle(); await sleep(650); }
  const [cx, cy] = center($('pile'));
  const order4 = ['0', '1', '2', '3'];
  for (let r = 0; r < rounds; r++) {
    for (const s of order4) {
      const t = s === me ? $('hand') : seatEl(s);
      if (!t) continue;
      const [tx, ty] = center(t);
      const b = document.createElement('div'); b.className = 'hk-back';
      b.style.left = (cx - 32) + 'px'; b.style.top = (cy - 45) + 'px';
      $('fly').appendChild(b);
      sfx.card.flick();
      b.animate([{ transform: 'scale(.7) rotate(0deg)', opacity: 1 }, { transform: `translate(${tx - cx}px,${ty - cy}px) scale(${s === me ? .9 : .45}) rotate(${(+s * 90) + 20}deg)`, opacity: .2 }],
        { duration: 260, easing: 'cubic-bezier(.3,.6,.4,1)' }).finished.catch(() => {}).then(() => b.remove());
      await sleep(48);
    }
  }
  await sleep(220);
}
async function trumpReveal(s) {
  const pile = $('pile');
  pile.innerHTML = `<div class="hk-wait" style="position:absolute;inset:0;justify-content:center"><span class="hk-trump"><span class="disc pop" style="width:84px;height:84px">${suitSvg(s).replace('<svg', '<svg style="width:48px;height:48px"')}</span></span><b style="font-size:18px">حکم ${SUIT_FA[s]}</b></div>`;
  sfx.card.trump();
  await sleep(950);
}

/* ---------- پخش رویدادها ---------- */
async function play(e) {
  const g = snap.game;
  if (e.t === 'deal') {
    pileShown = []; handShown = [];
    $('hand').innerHTML = ''; $('pile').innerHTML = '';
    renderSeats(Object.assign({}, g, { hakem: e.hakem, turn: null }));
    toast(e.hakem === me ? 'تو حاکم این دستی' : `حاکم این دست: ${nameOf(e.hakem)}`);
    await dealAnim(5, true);
    return;
  }
  if (e.t === 'trump') {
    await trumpReveal(e.suit);
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
    await collectTrick(e.c);
    const us = teamUs();
    $('score').querySelectorAll('.tm em')[0].textContent = FD(e.tricks[us]) + ' برگ';
    $('score').querySelectorAll('.tm em')[1].textContent = FD(e.tricks[1 - us]) + ' برگ';
    return;
  }
  if (e.t === 'hand') { if (e.score[e.team] < g.target) await handResult(e); return; }
  if (e.t === 'timeout' && e.c === me && snap.cfg.mode === 'stake' && e.n >= 2) { toast(e.n >= 3 ? 'سه نوبت غایب بودی؛ ربات جایت بازی می‌کند' : 'یک نوبت دیگر غیبت = بیرون رفتن از بازی'); return; }
  if (e.t === 'leave' && e.c !== me) { toast(`${nameOf(e.c)} ${e.why === 'timeout' ? 'غایب بود' : 'رفت'}؛ ربات جایش بازی می‌کند`); return; }
}
function bars(score, target) {
  const us = teamUs(), seg = (n, cls) => `<div class="hk-bar ${cls}"><span>${cls === 'us' ? 'ما' : 'حریف'}</span><span class="seg7" style="grid-template-columns:repeat(${target},minmax(0,1fr))">${Array.from({ length: target }, (_, i) => `<i class="${i < n ? 'on' : ''}"></i>`).join('')}</span><b>${FD(n)}</b></div>`;
  return `<div class="hk-bars">${seg(score[us], 'us')}${seg(score[1 - us], 'them')}</div>`;
}
async function handResult(e) {
  const us = teamUs(), won = e.team === us, g = snap.game;
  const nh = e.team === +e.hakem % 2 ? e.hakem : String((+e.hakem + 1) % 4);
  won ? (sfx.coin(), haptic('success')) : (sfx.nomove(), haptic('warning'));
  const kot = e.kot ? `<span class="kot">${e.pts === 3 ? 'حاکم کوت شد! ۳ امتیاز' : 'کوت! ۲ امتیاز'}</span>` : `<p>${won ? 'یک امتیاز برای شما' : 'یک امتیاز برای حریف'}</p>`;
  sheet(`<div class="hk-res" role="status">
      <span class="ic${won ? '' : ' lost'}">${svgP(CROWN)}</span>
      <h2>${won ? 'این دست مال شما شد' : 'این دست را باختید'}</h2>${kot}
      <div class="hk-tricks"><div><b>${FD(e.tricks[us])}</b><span>برگ ما</span></div><div><b>${FD(e.tricks[1 - us])}</b><span>برگ حریف</span></div></div>
      ${bars(e.score, g.target)}
      <p>حاکم دست بعد: <b>${nameOf(nh)}</b></p></div>`, { center: true, dismiss: false });
  await sleep(3000);
  GC.close();
}

/* ---------- گفتگوی سر میز ---------- */
const QUICK = ['سلام!', 'خوش‌بازی!', 'آفرین یار', 'حکم خوبی بود', 'زود باش', 'یک دست دیگه؟'];
const esc = t => String(t == null ? '' : t).replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
let chatId = 0, chatLog = [], unread = 0, chatSheet = null, sending = false;
const bubbles = {};
function showBubble(s) {
  const b = bubbles[s], seat = s === me ? $('meBar') : document.querySelector(`.hk-seat[data-seat="${s}"]`);
  if (!b || !seat) return;
  if (Date.now() > b.until) { delete bubbles[s]; return; }
  seat.querySelectorAll('.bubble').forEach(x => x.remove());
  const el = document.createElement('div'); el.className = 'bubble'; el.textContent = b.text; el.setAttribute('aria-hidden', 'true');
  el.style.cssText = s === me ? 'bottom:calc(100% + 6px);inset-inline-start:auto;left:50%;transform:translateX(-50%)' : 'top:calc(100% + 4px);inset-inline-start:auto;left:50%;transform:translateX(-50%)';
  seat.style.position = 'relative'; seat.appendChild(el);
}
function bubble(m) {
  bubbles[m.color] = { text: m.text, until: Date.now() + 4200 };
  showBubble(m.color);
  setTimeout(() => { if (bubbles[m.color] && Date.now() >= bubbles[m.color].until) { delete bubbles[m.color]; document.querySelectorAll('.bubble').forEach(x => x.remove()); } }, 4300);
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
  log.innerHTML = chatLog.length ? chatLog.map(m => `<div class="msg${m.me ? ' mine' : ''}">${m.me ? '' : face(m)}<div class="bub">${m.me ? '' : `<b>${esc(m.name)}</b>`}<span>${esc(m.text)}</span></div></div>`).join('')
    : '<p class="hint">هنوز کسی چیزی نگفته. سلام کن!</p>';
  log.scrollTop = log.scrollHeight;
}
async function send(text) {
  text = String(text || '').trim();
  if (!text || sending || !mid) return false;
  sending = true;
  try { await GC.hokm.chat(mid, text); chatIn((await GC.hokm.match(mid, since, chatId)).chat); return true; }
  catch (e) { sfx.error(); toast(errText(e)); return false; }
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
function endChat() {
  chatLog = []; unread = 0; chatSheet = null;
  for (const s of Object.keys(bubbles)) delete bubbles[s];
  document.querySelectorAll('.bubble').forEach(x => x.remove());
  $('chatBtn').hidden = true;
}

/* ---------- همگام سازی با سرور ---------- */
async function apply(next, anim = true) {
  if (next && next.chat && !overShown && next.status !== 'over' && next.status !== 'cancelled') chatIn(next.chat);
  if (next && next.status === 'cancelled') return cancelled();
  if (!next || !next.game) return;
  busy = true;
  try {
    snap = Object.assign({}, snap || {}, next);
    const g = next.game, evs = (g.events || []).filter(e => e.seq > since).sort((a, b) => a.seq - b.seq);
    const dealt = evs.some(e => e.t === 'deal' || e.t === 'trump');
    for (const e of evs) { if (anim) await play(e); since = e.seq; }
    since = Math.max(since, g.seq);
    pileShown = (g.trick || []).map(([i, c]) => [+i, c]);
    renderAll(g, dealt);
    if (next.status === 'over' && !overShown) { overShown = true; over(next); }
  } finally { busy = false; }
}
async function poll() {
  clearTimeout(pollT);
  if (document.hidden || overShown) { pollT = setTimeout(poll, POLL_MS); return; }
  if (!busy && !acting) {
    try { await apply(await GC.hokm.match(mid, since, chatId)); }
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
    if (snap && snap.game) renderAll(snap.game);
  } finally { acting = false; }
}
$('hand').addEventListener('click', e => {
  const el = e.target.closest('.hk-card.ok'); if (!el || acting || busy || !snap) return;
  const g = snap.game, c = +el.dataset.card;
  if (g.turn !== me || g.phase !== 'play' || !g.legal.includes(c)) return;
  selfPlayed = c;
  $('hand').querySelectorAll('.hk-card').forEach(x => x.classList.remove('ok', 'no'));
  const r = el.getBoundingClientRect(), ghost = document.createElement('span');
  ghost.style.cssText = `position:fixed;left:${r.left}px;top:${r.top}px;width:${r.width}px;height:${r.height}px`;
  $('fly').appendChild(ghost); el.remove(); setTimeout(() => ghost.remove(), 700);
  act(() => GC.hokm.play(mid, c, since), () => throwCard(me, c, ghost));
});
$('hand').addEventListener('keydown', e => { if ((e.key === 'Enter' || e.key === ' ') && e.target.classList.contains('ok')) { e.preventDefault(); e.target.click(); } });
document.addEventListener('visibilitychange', () => { if (!document.hidden) poll(); });

/* ---------- پایان، خروج ---------- */
function over(v) {
  endChat();
  const g = v.game, r = v.result || {}, won = !!r.won, us = teamUs();
  GC.guardClose(false); store.set('hmid', null);
  won ? (sfx.win(), haptic('success')) : (sfx.lose(), haptic('warning'));
  const secs = Math.max(0, Math.round(Date.now() / 1000 - g.started)), st = g.stats || { tricks: 0, hakem: 0 };
  const stake = v.cfg.mode === 'stake', ended = g.winner == null;
  sheet(`<div class="hk-res">
      <span class="ic${won ? '' : ' lost'}">${svgP(CROWN)}</span>
      <h2>${ended ? 'بازی تمام شد' : won ? 'بردید!' : 'این بازی را باختید'}</h2>
      <div class="hk-tricks"><div><b>${FD(g.score[us])}</b><span>دست ما</span></div><div><b>${FD(g.score[1 - us])}</b><span>دست حریف</span></div></div>
      ${stake ? (won ? `<div class="prize">${amount(r.prize || 0, 'lg')}</div><p>سهم تو از جایزه به کیف امتیازت اضافه شد.</p>` : ended ? '<p>ورودی‌ها برگشت.</p>' : `<p>ورودی این بازی (${fa(r.lost || v.cfg.entry)} امتیاز) را باختی.</p>`)
        : `<p>${won ? 'بازی آزاد بود و جایزه نداشت.' : 'بازی آزاد بود؛ چیزی از دست ندادی.'}</p>`}
      <div class="facts"><div><b>${FD(st.tricks)}</b><span>دور بردی</span></div><div><b>${FD(st.hakem)}</b><span>بار حاکم شدی</span></div><div><b>${FD(Math.floor(secs / 60))}:${FD(String(secs % 60).padStart(2, '0'))}</b><span>مدت بازی</span></div></div>
    </div>
    <a class="btn btn-block" href="hokm-lobby.html">یک بازی دیگر</a>
    <a class="btn btn-light btn-block" href="index.html">خانه</a>`, { center: true, dismiss: false });
  GC.refreshMe().catch(() => {});
}
function cancelled() {
  if (overShown) return;
  overShown = true; endChat(); GC.guardClose(false); store.set('hmid', null); GC.refreshMe().catch(() => {});
  sheet(`<div class="dlg" role="alertdialog" aria-labelledby="dT" aria-describedby="dD"><span class="dlg-ic">${icon('table')}</span>
      <h2 id="dT">این میز بسته شد</h2><p id="dD">پشتیبانی این میز را بست و ورودی همه به کیف امتیازشان برگشت.</p>
      <div class="dlg-acts"><a class="btn" href="hokm-lobby.html">میز تازه</a><a class="btn btn-light" href="index.html">خانه</a></div></div>`, { center: true, dismiss: false });
}
function noMatch() {
  store.set('hmid', null);
  sheet(`<div class="dlg" role="alertdialog" aria-labelledby="dT" aria-describedby="dD"><span class="dlg-ic">${icon('table')}</span>
      <h2 id="dT">میزی پیدا نشد</h2><p id="dD">این بازی تمام شده یا هنوز سر میزی ننشسته‌ای.</p>
      <div class="dlg-acts"><a class="btn" href="hokm-lobby.html">یک میز بساز</a><a class="btn btn-light" href="index.html">خانه</a></div></div>`, { center: true, dismiss: false });
}
function askExit() {
  if (!snap || snap.status === 'over') { location.href = 'index.html'; return; }
  const stake = snap.cfg.mode === 'stake';
  const sh = sheet(`<div class="dlg" role="alertdialog" aria-labelledby="dT" aria-describedby="dD">
      <span class="dlg-ic warn">${icon('exit')}</span>
      <h2 id="dT">از بازی بیرون می‌روی؟</h2>
      <p id="dD">ربات جای تو کنار یارت بازی می‌کند${stake ? '؛ اگر تیمتان ببرد سهمی به تو نمی‌رسد' : ''}.</p>
      <div class="dlg-note">${stake ? `ورودی ${amount(snap.cfg.entry)} برنمی‌گردد` : 'بازی آزاد است؛ امتیازی از دست نمی‌دهی'}</div>
      <div class="dlg-acts"><button class="btn" data-close>ادامهٔ بازی</button><button class="btn btn-danger-soft" id="leave">${icon('exit')}خروج</button></div>
    </div>`, { center: true });
  sh.querySelector('#leave').onclick = async () => {
    try { await GC.hokm.leave(mid); } catch (e) {}
    GC.guardClose(false); store.set('hmid', null); location.href = 'index.html';
  };
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
}
window.addEventListener('resize', fit);
try { Telegram.WebApp.onEvent('viewportChanged', fit); Telegram.WebApp.onEvent('fullscreenChanged', () => setTimeout(fit, 50)); } catch (e) {}

/* ---------- شروع ---------- */
async function start() {
  GC.portrait(true);
  $('meBar').innerHTML = '<div class="pill"><span class="txt"><b>در حال وصل شدن…</b></span></div>';
  fit();
  let first;
  try { first = await GC.hokm.match(mid, 0, 0); }
  catch (e) { return e.code === 'not_found' ? noMatch() : (toast(errText(e)), setTimeout(start, 2500)); }
  if (first.status === 'lobby') { location.href = 'hokm-lobby.html'; return; }
  if (first.status === 'cancelled') return cancelled();
  mid = first.id; store.set('hmid', mid); me = first.me;
  if (first.cfg.mode === 'stake' && first.status === 'playing') GC.guardClose(true);
  chatIn(first.chat, true);
  const g = first.game;
  snap = first; since = g.seq; pileShown = (g.trick || []).map(([i, c]) => [+i, c]);
  renderAll(g, true); mount(); fit();
  if (first.status === 'over') { overShown = true; over(first); return; }
  poll();
}
start();
})();
