/* ورق واقعی برای حکم و پیش نمایش فروشگاه: خال چینی چاپی ۲ تا ۱۰، آس، سرباز و بی بی و شاه
   دوسر (طراحی خود Game Club)، پشت ورق. ظاهر هر طرح (A، B، C) فقط با کلاس cards-a/b/c روی
   یک والد عوض می شود (static/cards.css)؛ اندازه با font-size خود ورق (پیش فرض ۶۴px). */
(function () {
const SP = [
  'M12 2C9 6.6 4 9.3 4 13.5c0 2.6 2 4.4 4.3 4.4 1.3 0 2.5-.6 3.1-1.5-.3 2-1.1 3.6-2.6 5.1h6.4c-1.5-1.5-2.3-3.1-2.6-5.1.6.9 1.8 1.5 3.1 1.5 2.3 0 4.3-1.8 4.3-4.4C20 9.3 15 6.6 12 2z',
  'M12 21.3C7.3 17.5 2.8 14 2.8 9.1 2.8 6.1 5.1 3.8 8 3.8c1.7 0 3.1.8 4 2.2.9-1.4 2.3-2.2 4-2.2 2.9 0 5.2 2.3 5.2 5.3 0 4.9-4.5 8.4-9.2 12.2z',
  'M12 1.8 19.6 12 12 22.2 4.4 12z',
  'M12 2.6a4.4 4.4 0 0 0-4.3 5.4A4.4 4.4 0 1 0 9.5 16.4c.9 0 1.7-.3 2.2-.7-.3 2.1-1.1 3.8-2.6 5.3h5.8c-1.5-1.5-2.3-3.2-2.6-5.3.5.4 1.3.7 2.2.7a4.4 4.4 0 1 0 1.8-8.4A4.4 4.4 0 0 0 12 2.6z',
];
const RANKS = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A'];
const SUIT_FA = ['پیک', 'دل', 'خشت', 'گشنیز'];
const RANK_FA = ['۲', '۳', '۴', '۵', '۶', '۷', '۸', '۹', '۱۰', 'سرباز', 'بی‌بی', 'شاه', 'آس'];
// جای خال ها روی ورق (ستون ۰ تا ۲، ردیف ۰ تا ۴ از بالا)؛ نیمه پایین وارونه چاپ می شود
const LAY = [
  [[1, 0], [1, 4]], [[1, 0], [1, 2], [1, 4]], [[0, 0], [2, 0], [0, 4], [2, 4]],
  [[0, 0], [2, 0], [1, 2], [0, 4], [2, 4]], [[0, 0], [2, 0], [0, 2], [2, 2], [0, 4], [2, 4]],
  [[0, 0], [2, 0], [1, 1], [0, 2], [2, 2], [0, 4], [2, 4]], [[0, 0], [2, 0], [1, 1], [0, 2], [2, 2], [1, 3], [0, 4], [2, 4]],
  [[0, 0], [2, 0], [0, 1.5], [2, 1.5], [1, 2], [0, 2.5], [2, 2.5], [0, 4], [2, 4]],
  [[0, 0], [2, 0], [1, .75], [0, 1.5], [2, 1.5], [0, 2.5], [2, 2.5], [1, 3.25], [0, 4], [2, 4]],
];
const COLX = [28, 50, 72];
const suit = c => Math.floor(c / 13), rank = c => c % 13, red = s => s === 1 || s === 2;
const svg = (d, cls = '') => `<svg viewBox="0 0 24 24" aria-hidden="true"${cls ? ` class="${cls}"` : ''}><path d="${d}"/></svg>`;

// تصویر دوسر سرباز (۹)، بی بی (۱۰) و شاه (۱۱): نیم تنه، کلاه، و چیزی در دست؛ نیمه پایین قرینه
const HAT = {
  9: 'M36 23C37 14 63 14 64 23Z M61 17C68 9 74 11 71 18 69 15 66 15 63 19Z',
  10: 'M38 22C40 14 60 14 62 22Z M50 9a3 3 0 1 0 .01 0Z M42 15a1.8 1.8 0 1 0 .01 0Z M58 15a1.8 1.8 0 1 0 .01 0Z',
  11: 'M37 23L39 9 44.5 16 50 7 55.5 16 61 9 63 23Z',
};
const HAIR = {
  9: 'M39 29C39 20 61 20 61 29 58 24 42 24 39 29Z',
  10: 'M38 31C36 18 64 18 62 31 64 40 60 46 58 47 59 38 58 30 57 27 52 25 48 25 43 27 42 30 41 38 42 47 40 46 36 40 38 31Z',
  11: 'M39 32C40 45 60 45 61 32 57 38 43 38 39 32Z M39 28C39 21 61 21 61 28 58 24 42 24 39 28Z',
};
const ITEM = {
  9: 'M23 14h1.8v46H23Z M23.9 10l6 5-6 5Z',
  10: 'M75.1 34h1.8v26h-1.8Z M76 22a5 5 0 1 0 .01 0Z',
  11: 'M23.1 18h1.8v42h-1.8Z M19 23h10v2.2H19Z M23.1 12l.9-4 .9 4Z',
};
const courtCache = {};
function court(r, s) {
  const k = r + ':' + s;
  if (courtCache[k]) return courtCache[k];
  const half = `<path class="k" d="M16 70C18 53 33 46 50 46 67 46 82 53 84 70Z"/><path class="r2" d="M24 70C26 60 34 54 44 52L50 70Z"/>
    <path class="gs" d="M43 47 50 66 57 47"/><circle class="g" cx="50" cy="56" r="2.4"/><rect class="nk" x="46" y="39" width="8" height="9"/>
    <circle class="sk" cx="50" cy="30" r="11"/><path class="hr" d="${HAIR[r]}"/><circle class="ey" cx="46" cy="29.5" r="1.3"/><circle class="ey" cx="54" cy="29.5" r="1.3"/>
    <path class="mo" d="M47.5 35Q50 36.6 52.5 35"/><path class="${r === 9 ? 'ht2' : 'g'}" d="${HAT[r]}"/><path class="${r === 10 ? 'it2' : 'it'}" d="${ITEM[r]}"/>`;
  courtCache[k] = `<span class="ct"><svg viewBox="0 0 100 140" aria-hidden="true"><rect class="cb" x="3" y="3" width="94" height="134" rx="5"/>
    <g>${half}</g><g transform="rotate(180 50 70)">${half}</g><path class="gl2" d="M8 70H92"/>
    <svg x="74" y="8" width="16" height="16" viewBox="0 0 24 24"><path class="k" d="${SP[s]}"/></svg>
    <svg x="10" y="116" width="16" height="16" viewBox="0 0 24 24"><path class="k" d="${SP[s]}"/></svg></svg></span>`;
  return courtCache[k];
}
function body(c) {
  const s = suit(c), r = rank(c);
  if (r >= 9 && r <= 11) return court(r, s);
  if (r === 12) return `<span class="pp">${s === 0 ? '<svg viewBox="0 0 24 24" class="ring" aria-hidden="true"><path d="M12 1.2a10.8 10.8 0 1 0 0 21.6 10.8 10.8 0 1 0 0-21.6zm0 1.4a9.4 9.4 0 1 1 0 18.8 9.4 9.4 0 1 1 0-18.8z"/></svg>' : ''}${svg(SP[s], 'ace' + (s === 0 ? ' sp' : ''))}</span>`;
  return `<span class="pp">${LAY[r].map(([cx, cy]) => {
    const y = 16 + cy * 17;
    return `<svg viewBox="0 0 24 24" aria-hidden="true" class="${y > 50.5 ? 'f' : ''}" style="left:${COLX[cx]}%;top:${y}%"><path d="${SP[s]}"/></svg>`;
  }).join('')}</span>`;
}
// طرح «مدرن» (درشت خوان): شاخص بزرگ، نماد کم رنگ خال در گوشه و نشان سرباز/بی بی/شاه؛
// فقط با کلاس cards-m دیده می شود (بقیه طرح ها این لایه را پنهان می کنند)
const EMB = {
  11: 'M3 7.5l4.6 4.2L12 4.5l4.4 7.2L21 7.5l-1.7 9H4.7zM4.7 18h14.6v2H4.7z',
  10: 'M12 3.6a1.7 1.7 0 1 1 0 3.4 1.7 1.7 0 0 1 0-3.4zM5.2 6.6a1.5 1.5 0 1 1 0 3 1.5 1.5 0 0 1 0-3zm13.6 0a1.5 1.5 0 1 1 0 3 1.5 1.5 0 0 1 0-3zM5.6 16.5l-.6-5.4 3.9 2.9L12 8.6l3.1 5.4 3.9-2.9-.6 5.4zM5.6 18h12.8v2H5.6z',
  9: 'M12 3l7 3v5c0 4.6-3 8.3-7 10-4-1.7-7-5.4-7-10V6z',
};
const jumbo = (s, r) => `<span class="jm"><span class="jx"><b${r === 8 ? ' class="w"' : ''}>${RANKS[r]}</b>${svg(SP[s])}</span>${EMB[r] ? `<span class="em">${svg(EMB[r])}</span>` : `<span class="wm">${svg(SP[s])}</span>`}</span>`;
// روی ورق c (۰ تا ۵۱: خال * ۱۳ + ارزش، ارزش ۱۲ = آس)
function face(c, cls = '', style = '') {
  const s = suit(c), r = rank(c), ix = `<b>${RANKS[r]}</b>${svg(SP[s])}`;
  return `<div class="hk-card${red(s) ? ' red' : ''}${cls ? ' ' + cls : ''}" data-card="${c}" style="${style}" role="img" aria-label="${RANK_FA[r]} ${SUIT_FA[s]}">`
    + `<span class="ix tl">${ix}</span><span class="ix br">${ix}</span>${body(c)}${jumbo(s, r)}<i class="gloss"></i></div>`;
}
const back = (cls = '', style = '') => `<div class="hk-back${cls ? ' ' + cls : ''}" style="${style}"><i></i></div>`;
const suitSvg = s => `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="${SP[s]}" fill="${red(s) ? '#D62839' : '#1C2230'}"/></svg>`;

window.GCCards = { face, back, suitSvg, SP, RANKS, SUIT_FA, suit, rank, red };
})();
