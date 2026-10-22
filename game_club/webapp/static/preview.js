/* پیش نمایش زندهٔ هر بازی با همان اجزای خود بازی (ورق و ماهوت حکم، صفحه و مهرهٔ منچ؛ زمین، مهره و توپ
   فوتبال و میز و توپ و چوب بیلیارد عیناً از رندر خود بازی در static/previews) و یک حرکت کوتاه تکراری.
   فقط transform و opacity جابه جا می شوند؛ حرکت فقط وقتی پیش نمایش روی صفحه دیده می شود اجرا می شود
   (IntersectionObserver) و با «کاهش حرکت» گوشی اصلا اجرا نمی شود (preview.css). */
(function () {
const C = () => window.GCCards;
let uid = 0;
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
  // زمین، مهره ها و توپ واقعی خود بازی (static/previews از make_previews.js): مهرهٔ تو به توپ می زند و توپ به دروازه می رود
  football() {
    const im = (n, cls, st) => `<img class="${cls}" src="static/previews/${n}.webp" alt="" draggable="false" style="${st}">`;
    return `<div class="pv pv-fb" aria-hidden="true"><div class="pv-fb-in">
      ${im('fb-disc-lions', 'pv-fd', 'left:63%;top:5.6%')}
      <span class="pv-layer pv-kick">${im('fb-disc-eagles', 'pv-fd', 'left:38%;top:14.6%')}</span>
      <span class="pv-layer pv-shot">${im('fb-ball', 'pv-fbb', 'left:49%;top:10.6%')}</span></div></div>`;
  },
  // میز، توپ ها و چوب واقعی بیلیارد (پلاتو): چوب به توپ سفید می زند، سفید به یک می خورد و یک به جیب وسط می رود
  billiard() {
    const ball = (k, x, y) => `<img class="pv-bb" src="static/previews/bl-ball-${k}.webp" alt="" draggable="false" style="left:${x}%;top:${y}%">`;
    return `<div class="pv pv-bl" aria-hidden="true"><div class="pv-bl-in">
      ${ball(8, 37, 21)}${ball(10, 63, 27)}${ball(3, 41, 35)}${ball(13, 61, 11)}${ball(9, 29, 9)}
      <span class="pv-layer pv-bl-pot">${ball(1, 50, 16.5)}</span>
      <span class="pv-layer pv-bl-cb">${ball(0, 50, 33)}</span>
      <span class="pv-layer pv-bl-stick"><img class="pv-cue" src="static/previews/bl-cue.webp" alt="" draggable="false"></span></div></div>`;
  },
  // صفحهٔ نمد دیوار: مهرهٔ آبی (تو) یک خانه بالا می رود و یک دیوار طلایی جلوی مهرهٔ قرمز فرود می آید
  divar() {
    const X = i => (3 + i * 10.63).toFixed(2), S = 8.93;
    const cells = Array.from({ length: 81 }, (_, k) => `<i style="left:${X(k % 9)}%;top:${X(Math.floor(k / 9))}%"></i>`).join('');
    const pawn = (r, c, col) => `<b class="pv-dvp" style="left:${(+X(c) + S * .13).toFixed(2)}%;top:${(+X(r) + S * .13).toFixed(2)}%;--pc:${col}"></b>`;
    const wall = (o, r, c, cls = '') => o === 'h'
      ? `<s class="pv-dvw h ${cls}" style="left:${X(c)}%;top:${(+X(r + 1) - .85 - .9).toFixed(2)}%"></s>`
      : `<s class="pv-dvw v ${cls}" style="top:${X(r)}%;left:${(+X(c + 1) - .85 - .9).toFixed(2)}%"></s>`;
    return `<div class="pv pv-dv" aria-hidden="true"><div class="pv-dv-in">
      <span class="pv-dve pv-dve-t"></span><span class="pv-dve pv-dve-b"></span>${cells}
      ${wall('h', 3, 1)}${wall('v', 3, 6)}${wall('h', 5, 6)}${pawn(2, 4, '#FF5A6A')}
      <span class="pv-layer pv-dv-wall">${wall('h', 2, 4)}</span>
      <span class="pv-layer pv-dv-step">${pawn(6, 4, '#4C8DFF')}</span></div></div>`;
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
