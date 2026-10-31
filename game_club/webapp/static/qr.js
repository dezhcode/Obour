/* QR کد کوچک برای لینک اتاق (بدون کتابخانهٔ بیرونی): حالت بایت، سطح تصحیح M، نسخهٔ ۱ تا ۶
   (تا ۱۰۶ بایت؛ لینک اتاق حدود ۴۰ بایت است). خروجی: GCQR.svg(text, {dark, light}) یک <svg> مربعی.
   روش همان استاندارد ISO 18004: رید-سولومون روی GF(256)، چیدمان زیگزاگ، بهترین ماسک از ۸ ماسک. */
(() => {
  // [کدواژهٔ تصحیح هر بلوک، تعداد بلوک، کدواژهٔ داده هر بلوک]؛ سطح M
  const M = [null, [10, 1, 16], [16, 1, 28], [26, 1, 44], [18, 2, 32], [24, 2, 43], [16, 4, 27]];

  const mul = (x, y) => { let z = 0; for (let i = 7; i >= 0; i--) { z = (z << 1) ^ ((z >>> 7) * 0x11D); z ^= ((y >>> i) & 1) * x; } return z; };
  function divisor(deg) {
    const r = new Array(deg - 1).fill(0).concat([1]);
    let root = 1;
    for (let i = 0; i < deg; i++) {
      for (let j = 0; j < r.length; j++) { r[j] = mul(r[j], root); if (j + 1 < r.length) r[j] ^= r[j + 1]; }
      root = mul(root, 2);
    }
    return r;
  }
  function remainder(data, div) {
    const r = div.map(() => 0);
    for (const b of data) {
      const f = b ^ r.shift(); r.push(0);
      div.forEach((c, i) => { r[i] ^= mul(c, f); });
    }
    return r;
  }

  function encode(text) {
    const bytes = Array.from(new TextEncoder().encode(text));
    let v = 1;
    while (v <= 6 && 4 + 8 + bytes.length * 8 > M[v][1] * M[v][2] * 8) v++;
    if (v > 6) throw new Error('qr_long');
    const [ec, nb, nd] = M[v], cap = nb * nd * 8;
    const bits = [];
    const put = (val, n) => { for (let i = n - 1; i >= 0; i--) bits.push((val >>> i) & 1); };
    put(4, 4); put(bytes.length, 8); bytes.forEach(b => put(b, 8));
    put(0, Math.min(4, cap - bits.length));
    put(0, (8 - bits.length % 8) % 8);
    for (let p = 0xEC; bits.length < cap; p ^= 0xEC ^ 0x11) put(p, 8);
    const data = [];
    for (let i = 0; i < bits.length; i += 8) data.push(bits.slice(i, i + 8).reduce((a, b) => a << 1 | b, 0));
    // بلوک ها و کدواژه های تصحیح، بعد درهم کردن
    const div = divisor(ec), blocks = [];
    for (let b = 0; b < nb; b++) { const d = data.slice(b * nd, (b + 1) * nd); blocks.push([d, remainder(d, div)]); }
    const out = [];
    for (let i = 0; i < nd; i++) blocks.forEach(([d]) => out.push(d[i]));
    for (let i = 0; i < ec; i++) blocks.forEach(([, e]) => out.push(e[i]));
    return { v, words: out };
  }

  function matrix(text) {
    const { v, words } = encode(text), n = v * 4 + 17;
    const mod = Array.from({ length: n }, () => new Array(n).fill(false));
    const fn = Array.from({ length: n }, () => new Array(n).fill(false));
    const set = (x, y, d) => { mod[y][x] = d; fn[y][x] = true; };
    for (let i = 0; i < n; i++) { set(6, i, i % 2 === 0); set(i, 6, i % 2 === 0); }
    const finder = (cx, cy) => {
      for (let dy = -4; dy <= 4; dy++) for (let dx = -4; dx <= 4; dx++) {
        const x = cx + dx, y = cy + dy, d = Math.max(Math.abs(dx), Math.abs(dy));
        if (x >= 0 && x < n && y >= 0 && y < n) set(x, y, d !== 2 && d !== 4);
      }
    };
    finder(3, 3); finder(n - 4, 3); finder(3, n - 4);
    if (v > 1) {
      const c = n - 7;
      for (let dy = -2; dy <= 2; dy++) for (let dx = -2; dx <= 2; dx++) set(c + dx, c + dy, Math.max(Math.abs(dx), Math.abs(dy)) !== 1);
    }
    const format = mask => {
      const d = mask;   // سطح M: دو بیت 00
      let r = d;
      for (let i = 0; i < 10; i++) r = (r << 1) ^ ((r >>> 9) * 0x537);
      const b = ((d << 10) | r) ^ 0x5412, bit = i => ((b >>> i) & 1) === 1;
      for (let i = 0; i <= 5; i++) set(8, i, bit(i));
      set(8, 7, bit(6)); set(8, 8, bit(7)); set(7, 8, bit(8));
      for (let i = 9; i < 15; i++) set(14 - i, 8, bit(i));
      for (let i = 0; i < 8; i++) set(n - 1 - i, 8, bit(i));
      for (let i = 8; i < 15; i++) set(8, n - 15 + i, bit(i));
      set(8, n - 8, true);
    };
    format(0);
    // چیدن داده: ستون های دوتایی از راست، بالا و پایین به نوبت، ستون ۶ رد می شود
    let k = 0;
    for (let right = n - 1; right >= 1; right -= 2) {
      if (right === 6) right = 5;
      for (let vert = 0; vert < n; vert++) for (let j = 0; j < 2; j++) {
        const x = right - j, up = ((right + 1) & 2) === 0, y = up ? n - 1 - vert : vert;
        if (!fn[y][x] && k < words.length * 8) { mod[y][x] = ((words[k >>> 3] >>> (7 - (k & 7))) & 1) === 1; k++; }
      }
    }
    const MASKS = [(x, y) => (x + y) % 2 === 0, (x, y) => y % 2 === 0, x => x % 3 === 0, (x, y) => (x + y) % 3 === 0,
      (x, y) => (Math.floor(x / 3) + Math.floor(y / 2)) % 2 === 0, (x, y) => x * y % 2 + x * y % 3 === 0,
      (x, y) => (x * y % 2 + x * y % 3) % 2 === 0, (x, y) => ((x + y) % 2 + x * y % 3) % 2 === 0];
    const apply = m => { for (let y = 0; y < n; y++) for (let x = 0; x < n; x++) if (!fn[y][x] && MASKS[m](x, y)) mod[y][x] = !mod[y][x]; };
    const penalty = () => {
      let p = 0, dark = 0;
      const line = get => {
        let run = 1;
        for (let i = 1; i <= n; i++) {
          if (i < n && get(i) === get(i - 1)) run++;
          else { if (run >= 5) p += run - 2; run = 1; }
        }
        const s = Array.from({ length: n }, (_, i) => get(i) ? 1 : 0).join('');
        for (const pat of ['10111010000', '00001011101']) for (let i = s.indexOf(pat); i >= 0; i = s.indexOf(pat, i + 1)) p += 40;
      };
      for (let i = 0; i < n; i++) { line(x => mod[i][x]); line(y => mod[y][i]); }
      for (let y = 0; y < n - 1; y++) for (let x = 0; x < n - 1; x++) {
        const c = mod[y][x];
        if (c === mod[y][x + 1] && c === mod[y + 1][x] && c === mod[y + 1][x + 1]) p += 3;
      }
      for (const row of mod) for (const c of row) if (c) dark++;
      return p + Math.floor(Math.abs(dark * 20 - n * n * 10) / (n * n)) * 10;
    };
    let best = 0, bestP = Infinity;
    for (let m = 0; m < 8; m++) { apply(m); format(m); const p = penalty(); if (p < bestP) { bestP = p; best = m; } apply(m); }
    apply(best); format(best);
    return mod;
  }

  function svg(text, { dark = '#14213D', light = '#FFFFFF', label = 'QR' } = {}) {
    const m = matrix(text), n = m.length, q = 4;
    let d = '';
    m.forEach((row, y) => row.forEach((c, x) => { if (c) d += `M${x + q} ${y + q}h1v1h-1z`; }));
    return `<svg viewBox="0 0 ${n + q * 2} ${n + q * 2}" role="img" aria-label="${label}" shape-rendering="crispEdges"><rect width="100%" height="100%" fill="${light}"/><path d="${d}" fill="${dark}"/></svg>`;
  }

  window.GCQR = { matrix, svg };
})();
