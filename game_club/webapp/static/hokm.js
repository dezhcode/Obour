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
const cardHtml = (c, cls = '', style = '') => C.face(c, cls, style);
const backHtml = (cls = '', style = '') => C.back(cls, style);
// صدای ورق هر بازیکن از سمت خودش: چپ، راست، روبه رو (وسط)
const panOf = s => { const r = rel(String(s)); return r === 1 ? .55 : r === 3 ? -.55 : 0; };
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
// عدد شبه تصادفی ثابت از روی برگ و بازیکن (همه همان را می بینند، با هر بار رسم هم عوض نمی شود)
const hash01 = (a, b) => { let h = (a * 374761393 + b * 668265263) | 0; h = Math.imul(h ^ (h >>> 13), 1274126177); return ((h ^ (h >>> 16)) >>> 0) / 4294967296; };
const slotOf = (s, c) => {
  const [x, y, r] = SLOT[rel(String(s))], k = +s * 53 + c;
  return [x + (hash01(k, 1) * 2 - 1) * 24, y + (hash01(k, 2) * 2 - 1) * 20, r + (hash01(k, 3) * 2 - 1) * 24];
};

/* ---------- نمایش ---------- */
function renderScore(g) {
  const us = teamUs(), tr = g.trump;
  $('score').innerHTML = `
    <div class="tm us"><span>شما</span><b>${FD(g.score[us])}<small> / ${FD(g.target)}</small></b><em>${FD(g.tricks[us])} دست</em></div>
    <div class="hk-trump"><span class="disc${tr == null ? ' unset' : ''}" id="trumpDisc">${tr == null ? '؟' : suitSvg(tr)}</span><small>${tr == null ? 'حکم' : 'حکم ' + SUIT_FA[tr]}</small></div>
    <div class="tm"><span>حریف</span><b>${FD(g.score[1 - us])}<small> / ${FD(g.target)}</small></b><em>${FD(g.tricks[1 - us])} دست</em></div>`;
}
function renderSeats(g) {
  for (const s of g.order) {
    if (s === me) continue;
    const p = g.players[s], el = document.querySelector(`.hk-seat[data-rel="${rel(s)}"]`);
    const partner = p.team === teamUs(), hk = g.hakem === s, turn = g.turn === s;
    el.dataset.seat = s;
    el.classList.toggle('out', !!p.out);
    el.innerHTML = `${hk ? `<span class="hk-crown" title="حاکم">${svgP(CROWN, '#3A2A00')}</span>` : ''}${face(p, turn ? 'var(--gold)' : partner ? '#9BE3B8' : '#FFFFFF', turn ? 'timer' : '')}
      <b>${p.name}</b><em class="${hk ? 'hk' : ''}">${[partner ? 'یار تو' : '', hk ? 'حاکم' : '', p.out ? 'ربات جایش' : FD(p.count) + ' برگ'].filter(Boolean).join('، ')}</em>${fanHtml(p.count)}`;
  }
  for (const s of Object.keys(bubbles)) showBubble(s);
}
function fanHtml(n) {
  n = Math.min(6, n || 0); if (!n) return '';
  const mid = (n - 1) / 2;
  return `<span class="hk-fan" aria-hidden="true">${Array.from({ length: n }, (_, i) => backHtml('', `transform:translate(${((i - mid) * 5).toFixed(1)}px,0) rotate(${((i - mid) * 9).toFixed(1)}deg)`)).join('')}</span>`;
}
// دسته برگ های برده شده هر تیم: ضربدری روی هم، با شمار
function renderStacks(tricks, drop = -1) {
  const us = teamUs();
  [[$('stackUs'), tricks ? tricks[us] : 0, drop === us], [$('stackThem'), tricks ? tricks[1 - us] : 0, drop === 1 - us]].forEach(([el, n, d]) => {
    if (!el) return;
    el.innerHTML = Array.from({ length: n }, (_, i) => backHtml(d && i === n - 1 ? 'drop' : '',
      `transform:translate(${(i * .8).toFixed(1)}px,${(-i * 1.4).toFixed(1)}px) rotate(${(i % 2 ? 90 : 0) + ((i * 37) % 9) - 4}deg);z-index:${i + 1}`)).join('')
      + (n ? `<span class="n">${FD(n)} دست</span>` : '');
  });
}
function renderPile(g) {
  const pile = $('pile');
  if (g && g.phase === 'trump' && !g.over) return renderPick(g);
  const tr = g ? g.trump : null;
  const w = pileShown.length >= 2 && tr != null ? winnerOf(pileShown, tr) : null;
  let tip = '';
  if (w != null && pileShown.length < 4) tip = `<span class="hk-tip">فعلا برگ ${nameOf(String(w))} بالاست</span>`;
  pile.innerHTML = tip + pileShown.map(([i, c], k) => {
    const [x, y, r] = slotOf(i, c);
    return cardHtml(c, '', `left:${x}px;top:${y}px;z-index:${k + 1};transform:rotate(${r}deg)`);
  }).join('');
}
function renderPick(g) {
  const pile = $('pile');
  if (g.hakem !== me) {
    if (pile.querySelector(`.hk-choosing[data-h="${g.hakem}"]`)) return;
    const hp = g.players[g.hakem] || {};
    pile.innerHTML = `<div class="hk-choosing" data-h="${g.hakem}" role="status">
      <div class="hk-orbit"><span class="ring">${[0, 1, 2, 3].map(k => `<span class="o${k}">${suitSvg(k)}</span>`).join('')}</span>
        <span class="who">${face(hp, '#F5C451')}<i class="cr">${svgP(CROWN, '#3A2A00')}</i></span></div>
      <b>${nameOf(g.hakem)} دارد حکم می‌کند<span class="hk-dots"></span></b>
      <small>${hp.team === teamUs() ? 'یارت' : 'حریف'} از روی پنج برگ اولش خال حکم را انتخاب می‌کند</small></div>`;
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
  const cards = order(g.hand || [], g.trump), n = cards.length;
  const mine = g.turn === me && g.phase === 'play', ok = new Set(mine ? g.legal : []);
  // نوبت من: برگ هایی که می شود انداخت جدا از بقیه (با فاصله) و بالاتر؛ بقیه پایین تر و کم رنگ
  const split = mine && ok.size > 0 && ok.size < n, GAP = 1.8;
  let acc = 0, gaps = 0;
  const pos = cards.map((c, i) => { if (i && split && ok.has(c) !== ok.has(cards[i - 1])) { acc += GAP; gaps++; } return acc++; });
  const total = n > 1 ? pos[n - 1] : 0;
  // کل بادبزن حدود ۳۱ درجه تا با ۱۳ برگ هم در عرض گوشی جا شود (با فاصله گروه ها کمی بازتر)
  const step = total ? Math.min(6.5, (30 + gaps * 3) / total) : 0;
  const fresh = anim ? cards.filter(c => !handShown.includes(c)) : [];
  hand.innerHTML = cards.map((c, i) => {
    // دست آدم دقیق نمی چیند: هر برگ کمی کج تر یا جابه جا (ثابت برای هر برگ تا با هر رسم نلرزد)
    const a = (total / 2 - pos[i]) * step + (hash01(c, 21) * 2 - 1) * 1.4;
    const jx = (hash01(c, 22) * 2 - 1) * 2.5, jy = (hash01(c, 23) * 2 - 1) * 3.5;
    const cls = [mine ? (ok.has(c) ? 'ok' : 'no') : '', fresh.includes(c) ? 'in' : ''].filter(Boolean).join(' ');
    return cardHtml(c, cls, `--a:${a.toFixed(2)}deg;--jx:${jx.toFixed(1)}px;--jy:${jy.toFixed(1)}px;z-index:${n - i};animation-delay:${fresh.indexOf(c) * 45}ms`);
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
  setDeadline(g.deadline_ms); turnMs = g.turn_ms || 20000;
}
function renderAll(g, anim = false) {
  renderScore(g); renderSeats(g); renderPile(g); renderHand(g, anim); renderMe(g); renderStacks(g.tricks); mount($('meBar')); tickTimer();
}

/* ---------- تایمر نوبت ---------- */
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
  const g = snap.game, left = deadlineAt ? Math.max(0, deadlineAt - Date.now()) : 0;
  const frac = deadlineAt ? Math.min(1, left / turnMs) : 1;
  document.querySelectorAll('.hk-seat .avatar, #meBar .avatar').forEach(a => a.style.setProperty('--t', a.classList.contains('timer') ? frac : 1));
  const ck = $('clock'); if (ck) ck.textContent = FD(Math.ceil(left / 1000)) + ' ثانیه';
  const mineNow = (g.turn === me && g.phase === 'play') || (g.phase === 'trump' && g.hakem === me);
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
/* پرتاب برگ: در هوا کج است و می چرخد و با مقاومت هوا آرام می شود؛ کمی جلوتر روی ماهوت
   می خورد، اگر محکم بود یک جهش کوچک می کند و بعد تا جای خودش سُر می خورد (روی برگ دیگر کمتر).
   هر چه محکم تر: سریع تر، چرخش و سُر بیشتر، صدای تیزتر و بلندتر. جای نهایی برای همه یکی است. */
async function throwCard(s, c, from) {
  const [x, y, r] = slotOf(s, c), k = pileScale();
  const [tx, ty] = pilePoint(x, y);
  const [ox, oy] = from ? center(from) : [tx, ty + 200];
  const R = rel(String(s)), pan = panOf(s), mine = String(s) === me, P = throwPower(s, c);
  const el = document.createElement('div'); el.className = 'hk-thrown';
  el.style.left = (tx - 32) + 'px'; el.style.top = (ty - 45) + 'px';
  el.innerHTML = '<i class="air"></i>' + cardHtml(c);
  $('fly').appendChild(el);
  const dx = ox - tx, dy = oy - ty, dist = Math.hypot(dx, dy) || 1, ux = dx / dist, uy = dy / dist;
  const dur = Math.max(400, Math.min(720, (330 + dist * .6) * (1.18 - .42 * P)));
  const onCard = pileShown.some(([i2, c2]) => { const [x2, y2] = slotOf(i2, c2); return Math.abs(x2 - x) < 52 && Math.abs(y2 - y) < 72; });
  const slide = (onCard ? 7 + 9 * P : 11 + 17 * P) * (.8 + Math.random() * .4);
  // کمی کج از مسیر مستقیم سُر می خورد (پیچ دست)
  const side = (Math.random() * 2 - 1) * .35;
  const sx = (ux - uy * side) * slide, sy = (uy + ux * side) * slide;
  const spin = (mine ? 10 : 0) + 30 * P * (Math.random() < .5 ? -1 : 1);
  const r0 = (mine ? r - 10 : R === 1 ? 78 : R === 3 ? -78 : 172) + spin;
  const tilt = 16 + 22 * P;
  const rx = R === 0 ? tilt : R === 2 ? -tilt : 0, ry = R === 1 ? -tilt : R === 3 ? tilt : 0;
  const hop = P > .45 || Math.random() < .35 ? (1.5 + 6 * P) * (.7 + Math.random() * .6) : 0;
  const T = (tx_, ty_, rot, ax, ay, sc) => `perspective(700px) translate(${tx_.toFixed(1)}px,${ty_.toFixed(1)}px) rotate(${rot.toFixed(1)}deg) rotateX(${ax.toFixed(1)}deg) rotateY(${ay.toFixed(1)}deg) scale(${sc.toFixed(3)})`;
  const land = .55, rl = r + (r0 - r) * .1;
  const frames = [{ transform: T(dx, dy, r0, rx, ry, mine ? 1.04 : .5) },
    { transform: T(sx, sy, rl, rx * .15, ry * .15, k * 1.04), offset: land, easing: 'cubic-bezier(.3,.6,.4,1)' }];
  if (hop) {
    frames.push({ transform: T(sx * .72, sy * .72 - hop, rl + (r - rl) * .35, rx * .12 * P, ry * .12 * P, k * (1 + .035 * P)), offset: land + .08 });
    frames.push({ transform: T(sx * .5, sy * .5, rl + (r - rl) * .6, 0, 0, k), offset: land + .17, easing: 'cubic-bezier(.2,.7,.3,1)' });
  } else frames.push({ transform: T(sx * .45, sy * .45, rl + (r - rl) * .55, 0, 0, k), offset: land + .14, easing: 'cubic-bezier(.2,.7,.3,1)' });
  frames.push({ transform: T(0, 0, r, 0, 0, k) });
  const ease = 'cubic-bezier(.2,.65,.35,1)';
  sfx.card.throw(pan);
  const anim = el.animate(frames, { duration: dur, easing: 'linear' });
  el.firstChild.animate([
    { opacity: .32 + .2 * P, transform: `translate(${14 + 10 * P}px,${26 + 16 * P}px) scale(1.06)` }, { opacity: .2, transform: 'translate(4px,8px)', offset: land }, { opacity: hop ? .12 : 0, transform: 'translate(2px,4px)', offset: land + .08 }, { opacity: 0, transform: 'none', offset: land + .17 }, { opacity: 0 },
  ], { duration: dur, easing: ease });
  const tLand = dur * land;
  setTimeout(() => { sfx.card.place(P, pan); if (mine) haptic(P > .7 ? 'medium' : 'light'); }, tLand);
  if (hop) setTimeout(() => sfx.card.place(P * .3, pan), tLand + dur * .17);
  sfx.card.slide(P * (onCard ? .7 : 1), pan, (tLand + dur * (hop ? .17 : .05)) / 1000);
  if (P > .85 && R !== 0) setTimeout(() => jolt(), tLand);
  await anim.finished.catch(() => {});
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
    const rot = +((card.style.transform.match(/-?[\d.]+/) || [0])[0]), jit = (i - 1.5) * 3;
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
  $('meBar').innerHTML = `<div class="pill">${face(p, '#9BE3B8')}<span class="txt"><b>${t}</b>${sub ? `<span>${sub}</span>` : ''}</span></div>`;
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
    const us = teamUs();
    $('score').querySelectorAll('.tm em')[0].textContent = FD(e.tricks[us]) + ' دست';
    $('score').querySelectorAll('.tm em')[1].textContent = FD(e.tricks[1 - us]) + ' دست';
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
      <div class="hk-tricks"><div><b>${FD(e.tricks[us])}</b><span>دست ما</span></div><div><b>${FD(e.tricks[1 - us])}</b><span>دست حریف</span></div></div>
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
function playCard(el) {
  if (!el || acting || busy || !snap) return;
  const g = snap.game, c = +el.dataset.card;
  if (g.turn !== me || g.phase !== 'play' || !g.legal.includes(c)) { el.style.translate = ''; el.classList.remove('drag'); return; }
  selfPlayed = c;
  $('hand').querySelectorAll('.hk-card').forEach(x => x.classList.remove('ok', 'no'));
  const r = el.getBoundingClientRect(), ghost = document.createElement('span');
  ghost.style.cssText = `position:fixed;left:${r.left}px;top:${r.top}px;width:${r.width}px;height:${r.height}px`;
  $('fly').appendChild(ghost); el.remove(); setTimeout(() => ghost.remove(), 700);
  act(() => GC.hokm.play(mid, c, since), () => throwCard(me, c, ghost));
}
// برگ را بزن، یا بگیر و رو به میز بکش و رها کن (کشیدن کوتاه = برگشت سر جایش)
let drag = null, dragged = false;
$('hand').addEventListener('click', e => { if (dragged) { dragged = false; return; } playCard(e.target.closest('.hk-card.ok')); });
$('hand').addEventListener('pointerdown', e => {
  const el = e.target.closest('.hk-card.ok'); if (!el || acting || busy) return;
  drag = { el, x: e.clientX, y: e.clientY, id: e.pointerId, moved: false };
});
$('hand').addEventListener('pointermove', e => {
  if (!drag || e.pointerId !== drag.id) return;
  const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
  if (!drag.moved && Math.hypot(dx, dy) < 8) return;
  if (!drag.moved) { drag.moved = true; drag.el.classList.add('drag'); try { drag.el.setPointerCapture(drag.id); } catch (err) {} }
  drag.el.style.translate = `${dx.toFixed(0)}px ${Math.min(12, dy).toFixed(0)}px`;
});
const endDrag = e => {
  if (!drag || (e && e.pointerId !== drag.id)) return;
  const d = drag; drag = null;
  if (!d.moved) return;
  dragged = true; setTimeout(() => { dragged = false; }, 60);
  const dy = e ? e.clientY - d.y : 0;
  if (dy < -55) playCard(d.el);
  else { d.el.classList.remove('drag'); d.el.style.translate = ''; }
};
$('hand').addEventListener('pointerup', endDrag);
$('hand').addEventListener('pointercancel', () => { if (drag) { drag.el.classList.remove('drag'); drag.el.style.translate = ''; drag = null; } });
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
      <div class="facts"><div><b>${FD(st.tricks)}</b><span>دست بردی</span></div><div><b>${FD(st.hakem)}</b><span>بار حاکم شدی</span></div><div><b>${FD(Math.floor(secs / 60))}:${FD(String(secs % 60).padStart(2, '0'))}</b><span>مدت بازی</span></div></div>
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
      <button class="btn btn-light btn-block dlg-home" id="home">${icon('home')}فقط برو خانه؛ سر میز می‌مانم</button>
      <p class="dlg-fine">میز در صفحهٔ خانه می‌ماند و با یک لمس برمی‌گردی. تا نیستی، نوبت‌هایت خودکار بازی می‌شود${stake ? '؛ در بازی امتیازی سه نوبت غیبت پشت‌سرهم یعنی بیرون رفتن از بازی' : ''}.</p>
    </div>`, { center: true });
  sh.querySelector('#home').onclick = () => { GC.guardClose(false); location.href = 'index.html'; };
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
function applyStyle(st) {
  if (!st) return;
  const b = document.body;
  b.className = b.className.replace(/\b(tbl|cards)-[a-z]\b/g, '').trim();
  b.classList.add('tbl-' + (st.table || 'a'), 'cards-' + (st.cards || 'a'));
}
async function start() {
  GC.portrait(true);
  GC.data.me().then(m => applyStyle(m && m.style)).catch(() => {});
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
  snap = first; since = g.seq; pileShown = (g.trick || []).map(([i, c]) => [+i, c]);
  renderAll(g, true); mount(); fit();
  if (first.status === 'over') { overShown = true; over(first); return; }
  poll();
}
start();
})();
