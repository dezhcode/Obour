/* تم های میز دیوار: همه رایگان. انتخاب روی همین دستگاه می ماند (GC.store) و فقط ظاهر صفحهٔ خود بازیکن را عوض می کند.
   لابی (تب «میز») و صفحهٔ بازی (دکمهٔ میز بالای صفحه) هر دو از همین جا می خوانند. */
(function () {
const LIST = [
  { id: 'felt', name: 'نمد شب', sub: 'نمد سبز و مهرهٔ نقره‌ای' },
  { id: 'neon', name: 'نئون شب', sub: 'خطوط نوری و گوی نورانی' },
  { id: 'marble', name: 'مرمر و طلا', sub: 'مرمر سفید و قاب طلایی' },
  { id: 'ice', name: 'یخ و بلور', sub: 'یخ آبی و نگین تراش‌خورده' },
  { id: 'paper', name: 'دفتر شطرنجی', sub: 'کاغذ شطرنجی و خط ماژیک' },
];
const KEY = 'dvTheme';
const get = () => { const t = GC.store.get(KEY, 'felt'); return LIST.some(x => x.id === t) ? t : 'felt'; };
function apply(el, id) {
  for (const x of LIST) el.classList.remove('dvt-' + x.id);
  if (id && id !== 'felt') el.classList.add('dvt-' + id);
}
function set(id) { GC.store.set(KEY, id); }
// پیش نمایش کوچک: ۴×۴ خانه، دو دیوار و دو مهره با همان قواعد CSS خود بازی
function mini(id) {
  const n = 4, pad = 6, gap = 4, cell = (100 - 2 * pad - (n - 1) * gap) / n, at = i => pad + i * (cell + gap);
  let h = '';
  for (let r = 0; r < n; r++) for (let c = 0; c < n; c++) h += `<i class="dv-cell" style="left:${at(c)}%;top:${at(r)}%;width:${cell}%;height:${cell}%"></i>`;
  const th = gap * .8, len = 2 * cell + gap;
  h += `<i class="dv-wall h" style="--wc:#FF5A6A;left:${at(1)}%;top:${at(1) + cell + gap / 2 - th / 2}%;width:${len}%;height:${th}%"></i>`;
  h += `<i class="dv-wall v" style="--wc:#4C8DFF;top:${at(2)}%;left:${at(0) + cell + gap / 2 - th / 2}%;height:${len}%;width:${th}%"></i>`;
  const ps = cell * .8, pawn = (r, c, pc, pd) => `<i class="dv-pawn" style="--pc:${pc};--pd:${pd};left:${at(c) + (cell - ps) / 2}%;top:${at(r) + (cell - ps) / 2}%;width:${ps}%;height:${ps}%"><b></b></i>`;
  h += pawn(3, 2, '#4C8DFF', '#2B62D6') + pawn(0, 1, '#FF5A6A', '#C93447');
  return `<span class="dv-mini ${id === 'felt' ? '' : 'dvt-' + id}"><span class="dv-board">${h}</span></span>`;
}
window.DVThemes = { LIST, get, set, apply, mini };
})();
