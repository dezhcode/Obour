/* پیش نمایش زندهٔ هر بازی با همان اجزای خود بازی (ورق و ماهوت حکم، صفحه و مهرهٔ منچ، زمین و مهرهٔ فلزی
   فوتبال) و یک حرکت کوتاه تکراری تا کاربر ببیند قرار است چه بازی کند.
   فقط transform و opacity جابه جا می شوند؛ حرکت فقط وقتی پیش نمایش روی صفحه دیده می شود اجرا می شود
   (IntersectionObserver) و با «کاهش حرکت» گوشی اصلا اجرا نمی شود (preview.css). */
(function () {
const C = () => window.GCCards;
let uid = 0;
const STAR = 'M16 7.5l2.5 5.2 5.7.8-4.1 4 1 5.6-5.1-2.7-5.1 2.7 1-5.6-4.1-4 5.7-.8z';
const EMBLEM = {
  eagles: () => { const id = 'pve' + (++uid); return `<svg viewBox="0 0 32 32" aria-hidden="true"><defs><pattern id="${id}" width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(35)"><rect width="4" height="8" fill="#1E5BD8"/><rect x="4" width="4" height="8" fill="#5AA2FF"/></pattern></defs><circle cx="16" cy="16" r="16" fill="url(#${id})"/><path d="${STAR}" fill="#fff"/></svg>`; },
  lions: () => '<svg viewBox="0 0 32 32" aria-hidden="true"><circle cx="16" cy="16" r="16" fill="#D7263D"/><rect x="0" y="12" width="32" height="8" fill="#F5C451"/><path d="M9 20l7-6 7 6" fill="none" stroke="#fff" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></svg>',
};
const BALL = '<svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="9.3" fill="#fff" stroke="#1c1f2a" stroke-width=".8"/><path d="M10 6.2l3.6 2.6-1.4 4.2H7.8L6.4 8.8z" fill="#1c1f2a"/><path d="M10 .9v2.6M18.6 7.6l-2.5.8M15.4 18l-1.5-2.1M4.6 18l1.5-2.1M1.4 7.6l2.5.8" stroke="#1c1f2a" stroke-width="1.6"/></svg>';
const disc = (team, cls) => `<span class="pv-disc ${cls}"><span class="in">${EMBLEM[team]()}</span></span>`;
// خانهٔ (x, y) صفحهٔ منچ به درصد (صفحه ۱۶ واحد است با نیم واحد حاشیه)
const cell = (x, y) => `left:${((x + 1) / 16 * 100).toFixed(2)}%;top:${((y + 1) / 16 * 100).toFixed(2)}%`;

const ART = {
  // دست خودت پایین میز؛ یک برگ از دستت و یک برگ از حریف روبه رو وسط میز می نشیند
  hokm(o) {
    const s = Object.assign({ table: 'a', cards: 'a' }, o.style || {}), f = C().face;
    const hand = [51, 49, 23, 35, 10].map((c, i) => f(c, 'pv-hand', `left:${30 + i * 8}%;--r:${-16 + i * 8}deg`)).join('');
    return `<div class="pv pv-hokm felt tbl-${s.table} cards-${s.cards}" aria-hidden="true">
      ${f(37, 'pv-pile', 'left:30%;top:24%;--r:-18deg')}${f(24, 'pv-pile', 'left:52%;top:18%;--r:10deg')}
      ${hand}
      ${f(51, 'pv-fly pv-fly-a', 'left:40%;top:30%;--r:-6deg')}${f(12, 'pv-fly pv-fly-b', 'left:47%;top:26%;--r:14deg')}</div>`;
  },
  // تاس می چرخد و مهرهٔ آبی چهار خانه جلو می رود
  ludo() {
    const P = window.GC.pawn, hop = [[1, 6]];
    return `<div class="pv pv-ludo" aria-hidden="true"><div class="pv-board">${window.GC.boardArt()}
      <span class="pv-pawn" style="${cell(8, 2)}">${P('red')}</span><span class="pv-pawn" style="${cell(12, 8)}">${P('green')}</span>
      <span class="pv-layer pv-hop"><span class="pv-pawn" style="${cell(...hop[0])}">${P('blue')}</span></span></div>
      <span class="pv-dice"><span class="f f2"><i></i><i></i></span><span class="f f4"><i></i><i></i><i></i><i></i></span></span></div>`;
  },
  // مهرهٔ تو به توپ می خورد و توپ به دروازه می رود
  football() {
    return `<div class="pv pv-fb" aria-hidden="true"><span class="pv-goal"></span><span class="pv-line"></span><span class="pv-circle"></span>
      ${disc('lions', 'pv-d2')}<span class="pv-layer pv-kick">${disc('eagles', 'pv-d1')}</span><span class="pv-layer pv-shot"><span class="pv-ball">${BALL}</span></span></div>`;
  },
  // توپ سفید به توپ زرد می خورد و زرد به سمت جیب می رود
  billiard() {
    const b = (c, cls, st, stripe) => `<span class="pv-pb${stripe ? ' st' : ''} ${cls}" style="--c:${c};${st}"></span>`;
    return `<div class="pv pv-bl" aria-hidden="true"><span class="pv-pk" style="left:3%;top:6%"></span><span class="pv-pk" style="right:3%;top:6%"></span>
      ${b('#1F45B5', '', 'left:56%;top:30%', true)}${b('#121212', '', 'left:64%;top:46%')}${b('#D9262C', '', 'left:30%;top:52%', true)}
      <span class="pv-layer pv-bl-pot">${b('#F2B90C', '', 'left:44%;top:36%')}</span><span class="pv-layer pv-bl-cue">${b('#F4F1E8', '', 'left:40%;top:72%')}</span></div>`;
  },
  esm() {
    return '<div class="pv pv-esm" aria-hidden="true"><span style="--d:0s;--r:-8deg">الف</span><span style="--d:.25s;--r:5deg">ب</span><span style="--d:.5s;--r:-3deg">م</span></div>';
  },
};

let io = null;
function watch(root) {
  const els = (root || document).querySelectorAll('.pv:not([data-pv])');
  if (!els.length) return;
  if (!('IntersectionObserver' in window)) { els.forEach(e => { e.dataset.pv = '1'; e.classList.add('on'); }); return; }
  io = io || new IntersectionObserver(es => es.forEach(e => e.target.classList.toggle('on', e.isIntersecting)), { threshold: .2 });
  els.forEach(e => { e.dataset.pv = '1'; io.observe(e); });
}
// وقتی برنامه پشت صحنه است هیچ چیز حرکت نمی کند
document.addEventListener('visibilitychange', () => document.documentElement.classList.toggle('pv-hidden', document.hidden));

window.GCPreview = { html: (game, o = {}) => (ART[game] || ART.esm)(o), watch };
})();
