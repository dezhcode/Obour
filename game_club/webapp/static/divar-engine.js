/* قواعد دیوار (کوریدور) در مرورگر؛ همان game_club/divar.py.
   صفحهٔ بازی با آن پیش از فرستادن دیوار، جای مجاز را نشان می دهد (سرور باز هم خودش بررسی می کند)
   و نسخهٔ نمایشی بیرون از تلگرام (demo-divar.js) کل بازی را با آن شبیه سازی می کند.
   مختصات [سطر، ستون]؛ صندلی "0" پایین، "1" چپ، "2" بالا، "3" راست. دیوار [o, r, c]. */
const DVEngine = (() => {
  const DIRS = [[1, 0], [-1, 0], [0, 1], [0, -1]];
  const WALLS = { '2:classic': 10, '4:classic': 5, '4:star': 7 };
  const seatsOf = n => n === 4 ? ['0', '1', '2', '3'] : ['0', '2'];
  const sizeOf = variant => variant === 'star' ? 11 : 9;
  const startOf = (s, n) => { const m = (n - 1) / 2; return { 0: [n - 1, m], 1: [m, 0], 2: [0, m], 3: [m, n - 1] }[s]; };
  function atGoal(st, s, r, c) {
    const n = st.size, m = (n - 1) / 2;
    if (st.star) return r === m && c === m;
    return { 0: r === 0, 1: c === n - 1, 2: r === n - 1, 3: c === 0 }[s];
  }
  const key = (o, r, c) => o + r + ',' + c;
  const wallSet = st => new Set(st.walls.map(w => key(w[0], w[1], w[2])));
  function blocked(W, r, c, dr, dc) {
    if (dr === 1) return W.has(key('h', r, c)) || W.has(key('h', r, c - 1));
    if (dr === -1) return W.has(key('h', r - 1, c)) || W.has(key('h', r - 1, c - 1));
    if (dc === 1) return W.has(key('v', r, c)) || W.has(key('v', r - 1, c));
    return W.has(key('v', r, c - 1)) || W.has(key('v', r - 1, c - 1));
  }
  const inb = (n, r, c) => r >= 0 && c >= 0 && r < n && c < n;
  // کوتاه ترین راه تا مقصد (بی توجه به مهره ها)؛ [] یعنی راهی نیست
  function path(st, s, W, from) {
    W = W || wallSet(st); const n = st.size, [r0, c0] = from || st.players[s].pos, K = (r, c) => r * n + c;
    const prev = new Map([[K(r0, c0), -1]]), q = [[r0, c0]];
    for (let i = 0; i < q.length; i++) {
      const [r, c] = q[i];
      if (atGoal(st, s, r, c)) { const out = []; let k = K(r, c); while (k !== -1) { out.push([Math.floor(k / n), k % n]); k = prev.get(k); } return out.reverse(); }
      for (const [dr, dc] of DIRS) {
        const nr = r + dr, nc = c + dc;
        if (inb(n, nr, nc) && !prev.has(K(nr, nc)) && !blocked(W, r, c, dr, dc)) { prev.set(K(nr, nc), K(r, c)); q.push([nr, nc]); }
      }
    }
    return [];
  }
  const dist = (st, s, W, from) => { const p = path(st, s, W, from); return p.length ? p.length - 1 : 1e6; };
  function wallError(st, o, r, c) {
    const n = st.size;
    if ((o !== 'h' && o !== 'v') || !(r >= 0 && r <= n - 2 && c >= 0 && c <= n - 2)) return 'bad_wall';
    const W = wallSet(st);
    if (W.has(key(o, r, c)) || W.has(key(o === 'h' ? 'v' : 'h', r, c))) return 'wall_taken';
    const near = o === 'h' ? [key('h', r, c - 1), key('h', r, c + 1)] : [key('v', r - 1, c), key('v', r + 1, c)];
    if (near.some(k => W.has(k))) return 'wall_taken';
    W.add(key(o, r, c));
    if (st.order.some(s => !path(st, s, W).length)) return 'wall_blocks';
    return null;
  }
  function moves(st, s) {
    const n = st.size, W = wallSet(st), [r, c] = st.players[s].pos, out = [];
    const occ = new Set(Object.entries(st.players).filter(([k]) => k !== s).map(([, p]) => p.pos[0] * n + p.pos[1]));
    const has = (a, b) => out.some(m => m[0] === a && m[1] === b);
    for (const [dr, dc] of DIRS) {
      const nr = r + dr, nc = c + dc;
      if (!inb(n, nr, nc) || blocked(W, r, c, dr, dc)) continue;
      if (!occ.has(nr * n + nc)) { out.push([nr, nc]); continue; }
      const jr = nr + dr, jc = nc + dc;
      if (inb(n, jr, jc) && !blocked(W, nr, nc, dr, dc) && !occ.has(jr * n + jc)) { out.push([jr, jc]); continue; }
      for (const [pr, pc] of (dr ? [[0, 1], [0, -1]] : [[1, 0], [-1, 0]])) {
        const sr = nr + pr, sc = nc + pc;
        if (inb(n, sr, sc) && !blocked(W, nr, nc, pr, pc) && !occ.has(sr * n + sc) && !has(sr, sc)) out.push([sr, sc]);
      }
    }
    return out;
  }
  // ربات: اگر حریفی جلوتر است دیواری که راه او را بیشتر از راه خودش طولانی کند؛ وگرنه یک قدم
  function step(st, s) {
    const W = wallSet(st); let best = null, bd = Infinity;
    for (const m of moves(st, s)) { const d = dist(st, s, W, m) + Math.random() * .4; if (d < bd) { bd = d; best = m; } }
    return best;
  }
  function botTurn(st, i) {
    const s = st.order[i], p = st.players[s], W = wallSet(st), mine = dist(st, s, W);
    let lead = null, lp = null;
    for (const k of st.order) { if (k === s) continue; const pk = path(st, k, W); if (pk.length && (!lp || pk.length < lp.length)) { lead = k; lp = pk; } }
    if (p.walls > 0 && lp && (lp.length - 1 < mine || lp.length - 1 <= 2) && Math.random() < .8) {
      const theirs = lp.length - 1; let best = null, bs = 0;
      for (let k = 0; k < Math.min(4, lp.length - 1); k++) {
        const [r1, c1] = lp[k], [r2, c2] = lp[k + 1];
        const cands = r1 !== r2 ? [['h', Math.min(r1, r2), c1], ['h', Math.min(r1, r2), c1 - 1]] : [['v', r1, Math.min(c1, c2)], ['v', r1 - 1, Math.min(c1, c2)]];
        for (const [o, r, c] of cands) {
          if (wallError(st, o, r, c)) continue;
          const W2 = new Set(W); W2.add(key(o, r, c));
          const sc = (dist(st, lead, W2) - theirs) - .7 * (dist(st, s, W2) - mine) + Math.random() * .3;
          if (sc > bs) { bs = sc; best = [o, r, c]; }
        }
      }
      if (best && (bs >= 1.5 || theirs <= 2)) return ['wall', ...best];
    }
    const m = step(st, s);
    return m ? ['move', m[0], m[1]] : ['pass'];
  }
  return { seatsOf, sizeOf, startOf, atGoal, wallSet, blocked, path, dist, wallError, moves, step, botTurn, WALLS, key };
})();
