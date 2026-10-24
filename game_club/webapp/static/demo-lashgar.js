/* نمایش لشگر کاغذی بیرون از تلگرام: یک جنگ با حریف ساختگی، با همان شکل جواب سرور (game_club/lashgar.py view)
   و همان قاعده ها (شکل نیروها برای خوردن، تا شدن کج و لرزش دست). حریف اسم می گذارد، نیروهایش را می چیند،
   کمی نقاشی می کند، آماده می شود و نوبتش نشانه می گیرد. فقط برای پیش نمایش است؛ در تلگرام همه چیز از سرور می آید. */
window.LgDemo = (() => {
  const W = 1000, H = 700, UNIT_S = 2.8, MARK_R = 12, EDGE = 0.6, SPREAD = 0.62, FOLD_MAX = 8, FOLD_K = 0.5, JITTER = 5;
  const TURN_S = 60, MISS_MAX = 3, INTRO = 3, SHOT_PAUSE = 3.2, TIMEOUT_PAUSE = 1;
  const ARMY = { sol: 6, tank: 2, gun: 1, heli: 1, flag: 1 };
  // همان SHAPES سرور (واحد شکل، مرکز نیرو صفر)
  const SHAPES = {
    sol: [['c', 0, -9, 3.7], ['s', 0, -6, 0, 4, 1.7], ['s', -5, -2, 4, -3, 1.5], ['s', 0, 4, -4, 11, 1.5], ['s', 0, 4, 4, 11, 1.5], ['s', 3, -3, 8, -9, 1.4]],
    tank: [['p', [[-21, 3], [21, 3], [18, 11.6], [-18, 11.6]]], ['p', [[-16.6, 3], [-13.4, -3.6], [12.4, -3.6], [16.6, 3]]],
      ['p', [[-7.6, -3], [-6.6, -9.4], [1, -10.7], [7.6, -9.4], [8.6, -3]]], ['s', 6, -7, 23, -13, 1.6]],
    gun: [['c', -6, 6, 5.7], ['c', 6, 6, 5.7], ['s', -7.5, 2.5, 16, -9, 2.7]],
    heli: [['e', 0, 0, 12.7, 7.7], ['s', 11, -1, 29, -1, 2.3], ['s', 29, -7, 29, 5, 1.3], ['s', -17, -11, 17, -11, 1.4], ['s', 0, -11, 0, -7, 1.1],
      ['s', -8, 10, 8, 10, 1.3], ['s', -5, 7, -5, 10, 1.1], ['s', 5, 7, 5, 10, 1.1]],
    flag: [['s', 0, 12, 0, -16, 1.3], ['p', [[0, -16.7], [17.7, -16.7], [17.7, -3.3], [0, -3.3]]]],
  };
  const REACH = {};
  for (const [k, ps] of Object.entries(SHAPES)) {
    let r = 0;
    for (const p of ps) {
      if (p[0] === 'c') r = Math.max(r, Math.hypot(p[1], p[2]) + p[3]);
      else if (p[0] === 's') r = Math.max(r, Math.hypot(p[1], p[2]) + p[5], Math.hypot(p[3], p[4]) + p[5]);
      else if (p[0] === 'p') r = Math.max(r, ...p[1].map(([x, y]) => Math.hypot(x, y)));
      else r = Math.max(r, Math.hypot(p[1], p[2]) + Math.max(p[3], p[4]));
    }
    REACH[k] = r * UNIT_S;
  }
  const P = { 0: { name: 'tu_demo', av: 7 }, 1: { name: 'negar_gm', av: 5 } };
  const FOE_ARMY = 'گردان زنگ تفریح';
  const SAY = {
    hitMe: ['زدمش! 💥', 'اینم از این 😎', 'دیدی گفتم؟'], missMe: ['ای بابا…', 'دفعهٔ بعد حتما!', 'دستم لرزید 😅'],
    hitFoe: ['آخ! 😖', 'خوش‌شانس بودی', 'باشه، نوبت منه'], missFoe: ['ها ها، خطا 😄', 'نزدیک بود!', 'برگه رو صاف تا کن 😄'],
  };
  const now = () => Date.now() / 1000;
  const pick = a => a[Math.floor(Math.random() * a.length)];
  const gauss = () => { let u = 0, v = 0; while (!u) u = Math.random(); while (!v) v = Math.random(); return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v); };
  const total = () => Object.values(ARMY).reduce((a, b) => a + b, 0);
  let st = null, ink = [], inkId = 0, chat = [], sayAt = 0;

  /* ---------- هندسه (همان lashgar.py) ---------- */
  function segD(px, py, x1, y1, x2, y2) {
    const dx = x2 - x1, dy = y2 - y1, L = dx * dx + dy * dy;
    const t = L === 0 ? 0 : Math.max(0, Math.min(1, ((px - x1) * dx + (py - y1) * dy) / L));
    return Math.hypot(px - (x1 + t * dx), py - (y1 + t * dy));
  }
  function inPoly(px, py, pts) {
    let inside = false;
    for (let i = 0; i < pts.length; i++) {
      const [x1, y1] = pts[i], [x2, y2] = pts[(i + 1) % pts.length];
      if ((y1 > py) !== (y2 > py) && px < (x2 - x1) * (py - y1) / (y2 - y1) + x1) inside = !inside;
    }
    return inside;
  }
  function touches(u, mx, my, r = MARK_R) {
    const dx = mx - u.x, dy = my - u.y;
    if (Math.hypot(dx, dy) > REACH[u.k] + r) return false;
    const a = -(u.r || 0) * Math.PI / 180;
    const lx = (dx * Math.cos(a) - dy * Math.sin(a)) / UNIT_S, ly = (dx * Math.sin(a) + dy * Math.cos(a)) / UNIT_S, rr = r / UNIT_S;
    for (const p of SHAPES[u.k]) {
      if (p[0] === 'c' && Math.hypot(lx - p[1], ly - p[2]) <= p[3] + rr) return true;
      if (p[0] === 's' && segD(lx, ly, p[1], p[2], p[3], p[4]) <= p[5] + rr) return true;
      if (p[0] === 'p') {
        const pts = p[1];
        if (inPoly(lx, ly, pts) || pts.some((q, i) => segD(lx, ly, q[0], q[1], pts[(i + 1) % pts.length][0], pts[(i + 1) % pts.length][1]) <= rr)) return true;
      }
      if (p[0] === 'e' && ((lx - p[1]) / (p[3] + rr)) ** 2 + ((ly - p[2]) / (p[4] + rr)) ** 2 <= 1) return true;
    }
    return false;
  }
  function landing(x, y, a) {
    const th = Math.max(-FOLD_MAX, Math.min(FOLD_MAX, a)) * FOLD_K * Math.PI / 180;
    const ux = x - W / 2, uy = -y, c2 = Math.cos(2 * th), s2 = Math.sin(2 * th), lim = JITTER * 2.5;
    let px = W / 2 + ux * c2 - uy * s2, py = ux * s2 + uy * c2;
    px += Math.max(-lim, Math.min(lim, gauss() * JITTER));
    py += Math.max(-lim, Math.min(lim, gauss() * JITTER));
    return [W - px, -py];
  }
  function checkUnits(list) {
    if (!Array.isArray(list) || list.length > total()) return [null, 'bad_units'];
    const left = Object.assign({}, ARMY), out = [];
    for (const u of list) {
      if (!u || !(u.k in left)) return [null, 'bad_units'];
      const x = +u.x, y = +u.y, r = +(u.r || 0);
      if (![x, y, r].every(Number.isFinite)) return [null, 'bad_units'];
      if (left[u.k] <= 0) return [null, 'too_many'];
      left[u.k]--;
      const m = REACH[u.k] * EDGE;
      if (!(m <= x && x <= W - m && m <= y && y <= H - m)) return [null, 'unit_out'];
      out.push({ k: u.k, x: Math.round(x * 10) / 10, y: Math.round(y * 10) / 10, r: ((Math.round(r) % 360) + 360) % 360 });
    }
    for (let i = 0; i < out.length; i++) for (let j = 0; j < i; j++) {
      if (Math.hypot(out[i].x - out[j].x, out[i].y - out[j].y) < (REACH[out[i].k] + REACH[out[j].k]) * SPREAD) return [null, 'unit_overlap'];
    }
    return [out, null];
  }
  // نیروهای حریف: بزرگ ها اول، جای خالی تصادفی (دور از لبهٔ دور برگه که نقاشی دارد)
  function autoUnits(maxY = H) {
    const out = [];
    const need = Object.entries(ARMY).flatMap(([k, n]) => Array(n).fill(k)).sort((a, b) => REACH[b] - REACH[a]);
    for (const k of need) {
      const m = REACH[k] * EDGE;
      let u = null;
      for (let i = 0; i < 500; i++) {
        u = { k, x: Math.round((m + Math.random() * (W - 2 * m)) * 10) / 10, y: Math.round((m + Math.random() * (Math.min(maxY, H - m) - m)) * 10) / 10, r: Math.random() < .3 ? pick([315, 45, 180]) : 0 };
        if (out.every(v => Math.hypot(u.x - v.x, u.y - v.y) >= (REACH[k] + REACH[v.k]) * SPREAD)) break;
      }
      out.push(u);
    }
    return out;
  }
  // نقاشی حریف (مختصات خودش): خورشید، چمن و یک درخت کنار لبهٔ دور برگه
  function foeInk() {
    const out = [], ring = (cx, cy, r, n = 22) => Array.from({ length: n + 1 }, (_, i) => [cx + r * Math.cos(i / n * 2 * Math.PI), cy + r * Math.sin(i / n * 2 * Math.PI)]).flat().map(Math.round);
    out.push({ c: 3, w: 1, e: 0, p: ring(880, 610, 42) });
    for (let i = 0; i < 8; i++) { const a = i / 8 * 2 * Math.PI; out.push({ c: 3, w: 0, e: 0, p: [880 + 56 * Math.cos(a), 610 + 56 * Math.sin(a), 880 + 76 * Math.cos(a), 610 + 76 * Math.sin(a)].map(Math.round) }); }
    const grass = []; for (let x = 30; x <= 700; x += 18) grass.push(x, x % 36 ? 668 : 650);
    out.push({ c: 4, w: 1, e: 0, p: grass });
    out.push({ c: 6, w: 2, e: 0, p: [120, 668, 120, 600] });
    out.push({ c: 4, w: 2, e: 0, p: ring(120, 572, 34, 18) });
    return out;
  }

  /* ---------- وضعیت ---------- */
  function reset() {
    const t = now();
    st = { order: ['0', '1'], phase: 'draw', turn: 0, shots: [], next_at: t, deadline: 0, seq: 0, events: [], over: false, winner: null, why: '',
      started: t, battle_at: 0, botDelay: 4, foeAt: { army: t + 3, place: t + 5, ready: t + 21 },
      players: { 0: { army: '', units: [], ready: false, out: false, misses: 0, shots: 0, hits: 0 },
        1: { army: '', units: autoUnits(560), ready: false, out: false, misses: 0, shots: 0, hits: 0 } } };
    ink = []; inkId = 0; chat = []; sayAt = 0;
    for (const s of foeInk()) ink.push({ id: ++inkId, color: '1', s, gone: false });
    ev({ t: 'draw' });
  }
  const ev = e => { st.seq++; st.events.push(Object.assign({ seq: st.seq }, e)); st.events = st.events.slice(-40); };
  const cur = () => (st.phase === 'battle' && !st.over ? st.order[st.turn] : null);
  const alive = p => p.units.filter(u => !u.dead).length;
  const placed = c => (c === '1' ? Math.max(0, Math.min(total(), Math.floor((now() - st.foeAt.place) / 1.3))) : st.players[c].units.length);
  function say(c, list, p = 0.45) {
    if (Math.random() > p || now() - sayAt < 6) return;
    sayAt = now();
    setTimeout(() => chat.push({ id: chat.length + 1, color: c, name: P[c].name, av: P[c].av, pic: '', bot: false, text: pick(list), at: Math.round(now()), me: false }), 1600);
  }
  function wait(pause) { st.next_at = now() + pause; st.deadline = st.next_at + TURN_S; st.botDelay = 3.5 + Math.random() * 5; }
  function battle() {
    st.phase = 'battle'; st.battle_at = now();
    for (const c of st.order) for (const u of st.players[c].units) u.dead = false;
    st.turn = Math.random() < .5 ? 0 : 1;
    ev({ t: 'battle', first: st.order[st.turn] });
    wait(INTRO);
  }
  function next(pause = SHOT_PAUSE) { st.turn = 1 - st.turn; ev({ t: 'turn', c: st.order[st.turn] }); wait(pause); }
  function finish(w, why) { st.over = true; st.winner = w; st.why = why; st.phase = 'over'; ev({ t: w != null ? 'win' : 'end', c: w, why }); }
  function shoot(c, x, y, a) {
    const [tx, ty] = landing(x, y, a), foe = c === '0' ? '1' : '0', fp = st.players[foe], me = st.players[c];
    const on = tx >= 0 && tx <= W && ty >= 0 && ty <= H;
    const hit = on ? fp.units.map((u, i) => (!u.dead && touches(u, tx, ty) ? i : -1)).filter(i => i >= 0) : [];
    for (const i of hit) fp.units[i].dead = true;
    me.shots++; me.hits += hit.length; me.misses = 0;
    const shot = { n: st.shots.length + 1, by: c, x: Math.round(tx * 10) / 10, y: Math.round(ty * 10) / 10, hit, a: Math.round(a * 10) / 10, off: !on, ax: Math.round(x * 10) / 10, ay: Math.round(y * 10) / 10 };
    st.shots.push(shot); ev(Object.assign({ t: 'shot' }, shot));
    say('1', c === '1' ? (hit.length ? SAY.hitMe : SAY.missMe) : (hit.length ? SAY.hitFoe : SAY.missFoe));
    if (hit.some(i => fp.units[i].k === 'flag')) finish(c, 'flag');
    else if (fp.units.filter(u => u.k !== 'flag').every(u => u.dead)) finish(c, 'army');
    else next();
  }
  // حریف نشانه می گیرد: یک نیروی سالم (گاهی پرچم) با کمی خطا؛ نقطه روی نیمهٔ خودش = قرینهٔ هدف
  function botShot() {
    const mine = st.players[0].units.filter(u => !u.dead), flag = mine.find(u => u.k === 'flag');
    const u = flag && st.shots.length > 4 && Math.random() < .12 ? flag : pick(mine.filter(v => v.k !== 'flag')) || flag;
    const err = u === flag ? 34 : 24, tx = u.x + gauss() * err, ty = u.y + gauss() * err;
    shoot('1', Math.max(0, Math.min(W, W - tx)), Math.max(0, Math.min(H, ty)), Math.max(-FOLD_MAX, Math.min(FOLD_MAX, gauss() * 2.5)));
  }
  function tick() {
    const t = now(), f = st.players[1];
    if (st.over) return;
    if (st.phase === 'draw') {
      if (!f.army && t >= st.foeAt.army) { f.army = FOE_ARMY === st.players[0].army ? 'تیپ نیمکت آخر' : FOE_ARMY; ev({ t: 'army', c: '1' }); }
      if (!f.ready && t >= st.foeAt.ready) { f.ready = true; ev({ t: 'ready', c: '1' }); }
      if (f.ready && st.players[0].ready) battle();
      return;
    }
    for (let i = 0; i < 4 && !st.over && t >= st.deadline; i++) {
      const c = cur(), p = st.players[c];
      p.misses++; ev({ t: 'timeout', c, n: p.misses });
      if (p.misses >= MISS_MAX) { p.out = true; ev({ t: 'leave', c, why: 'timeout' }); finish(c === '0' ? '1' : '0', 'timeout'); break; }
      next(TIMEOUT_PAUSE);
    }
    if (!st.over && cur() === '1' && t >= st.next_at + st.botDelay) botShot();
  }
  function view(since) {
    const t = now(), reveal = st.phase !== 'draw', c0 = cur();
    const players = {};
    for (const c of st.order) {
      const p = st.players[c], mine = c === '0';
      players[c] = { name: P[c].name, av: P[c].av, pic: '', bot: false, out: p.out, me: mine, army: p.army, ready: p.ready, placed: placed(c),
        alive: alive(p), shots: p.shots, hits: p.hits, misses: p.misses, units: mine || reveal ? p.units.map(u => Object.assign({}, u)) : null };
    }
    return { order: st.order.slice(), players, me: '0', size: 11, army: Object.assign({}, ARMY), w: W, h: H, unit_s: UNIT_S, mark_r: MARK_R,
      phase: st.phase, turn: c0, ready_ms: c0 ? Math.max(0, Math.round((st.next_at - t) * 1000)) : 0,
      deadline_ms: c0 ? Math.max(0, Math.round((st.deadline - t) * 1000)) : 0, turn_ms: TURN_S * 1000,
      shots: reveal ? st.shots.slice() : [], events: st.events.filter(e => e.seq > since), seq: st.seq,
      over: st.over, winner: st.winner, why: st.why, started: st.started, battle_at: st.battle_at };
  }
  const out = (since, chatSince) => {
    const o = { id: 'demo', status: st.over ? 'over' : 'playing', cfg: { game: 'lashgar', mode: 'free', entry: 0, players: 2, army: 11 }, me: '0', game: view(since || 0) };
    if (chatSince != null) o.chat = chat.filter(x => x.id > chatSince).slice(-40);
    return o;
  };
  const fail = code => { const e = new Error(code); e.code = code; throw e; };
  const drawing = () => { if (st.over) fail('over'); if (st.phase !== 'draw') fail('not_draw'); if (st.players[0].ready) fail('is_ready'); };
  return {
    async join() { if (!st || st.over) reset(); return { id: 'demo', status: 'playing' }; },
    async match(id, since = 0, chatSince = null) { if (!st) reset(); tick(); return out(since, chatSince); },
    async chat(id, text) {
      const last = chat.filter(x => x.me).pop();
      if (last && now() - last.at < 1.5) fail('chat_slow');
      chat.push({ id: chat.length + 1, color: '0', name: P[0].name, av: P[0].av, pic: '', bot: false, text: String(text).slice(0, 140), at: now(), me: true });
      say('1', ['😄', 'حالا می‌بینیم!', 'دمت گرم'], 0.5);
      return { ok: true };
    },
    async army(id, name, since) {
      if (st.over) fail('over');
      if (st.phase !== 'draw') fail('not_draw');
      const n = String(name || '').replace(/\s+/g, ' ').trim();
      if (n.length < 2) fail('army_short');
      if (n.length > 20) fail('army_long');
      if (/https?|www\.|t\.me|\.com|\.ir|@/i.test(n) || !/^[\p{L}\p{N}]+(?:[ \u200c][\p{L}\p{N}]+)*$/u.test(n)) fail('army_chars');
      if (n === st.players[1].army) fail('army_taken');
      st.players[0].army = n; ev({ t: 'army', c: '0' }); tick();
      return out(since);
    },
    async units(id, list) {
      drawing();
      const [ok, err] = checkUnits(list);
      if (err) fail(err);
      st.players[0].units = ok;
      return { ok: true };
    },
    async ready(id, since) {
      drawing();
      if (!st.players[0].army) fail('need_army');
      if (st.players[0].units.length !== total()) fail('need_units');
      st.players[0].ready = true; ev({ t: 'ready', c: '0' });
      // حریف اگر هنوز نقاشی می کند، کمی بعد آماده می شود
      st.foeAt.ready = Math.min(st.foeAt.ready, now() + 4);
      tick();
      return out(since);
    },
    async unready(id, since) {
      if (st.over || st.phase !== 'draw') fail('not_draw');
      if (st.players[0].ready) { st.players[0].ready = false; ev({ t: 'unready', c: '0' }); }
      return out(since);
    },
    async shoot(id, x, y, a, since) {
      tick();
      if (st.over) fail('over');
      if (st.phase !== 'battle') fail('not_battle');
      if (cur() !== '0') fail('not_your_turn');
      if (now() < st.next_at - 0.3) fail('not_ready');
      if (![x, y].every(Number.isFinite) || x < 0 || x > W || y < 0 || y > H) fail('bad_shot');
      shoot('0', +x, +y, Number.isFinite(+a) ? Math.max(-FOLD_MAX, Math.min(FOLD_MAX, +a)) : 0);
      return out(since);
    },
    async ink(id, ops) {
      drawing();
      if (!Array.isArray(ops) || !ops.length || ops.length > 24) fail('bad_ink');
      const ids = [];
      for (const o of ops) {
        if (o.op === 's') { const s = o.s || {}; if (!Array.isArray(s.p) || s.p.length < 2 || s.p.length % 2 || s.p.length > 800) fail('bad_ink'); ink.push({ id: ++inkId, color: '0', s: { c: s.c | 0, w: s.w | 0, e: s.e ? 1 : 0, p: s.p.map(Math.round) }, gone: false }); ids.push(inkId); }
        else if (o.op === 'u') { const l = ink.filter(r => r.color === '0' && !r.gone).pop(); if (l) l.gone = true; ids.push(++inkId); }
        else if (o.op === 'c') { ink.forEach(r => { if (r.color === '0') r.gone = true; }); ids.push(++inkId); }
        else fail('bad_ink');
      }
      return { ok: true, ids, v: inkId };
    },
    async inkGet(id, since = 0) {
      const draw = st.phase === 'draw';
      const rows = ink.filter(r => r.id > since && !r.gone && (!draw || r.color === '0'));
      return { ops: rows.map(r => ({ id: r.id, c: r.color, op: 's', s: Object.assign({}, r.s) })), v: Math.max(since, inkId), more: false };
    },
    async leave() { if (st && !st.over) { st.players[0].out = true; ev({ t: 'leave', c: '0', why: 'left' }); finish('1', 'left'); } st = null; return { left: true }; },
  };
})();
