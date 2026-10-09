/* حالت نمایشی: وقتی صفحه بیرون از تلگرام باز شود (initData نیست)، همان
   API سرور اینجا در مرورگر شبیه سازی می شود. موتور منچ نسخه دوقلوی
   game_club/ludo.py است تا رفتار پیش نمایش و سرور یکی باشد.
   هیچ چیز این فایل در حالت واقعی (داخل تلگرام) استفاده نمی شود. */
(() => {
const { TRACK, ORDER } = GC.LUDO;
const START = { blue: 0, red: 13, green: 26, yellow: 39 }, SAFE = new Set(GC.LUDO.SAFE), FIN = 56, YARD = -1;
const SEATS = { 2: ['yellow', 'red'], 4: ['blue', 'red', 'green', 'yellow'] };
const BOTS = ['سارا', 'امیر', 'نگار', 'رضا', 'مهسا', 'علی', 'پریا', 'کیان', 'هستی', 'سینا', 'آرش', 'یاسمن'];
const now = () => Date.now() / 1000;
const die = () => 1 + Math.floor(Math.random() * 6);
const ti = (c, p) => p >= 0 && p <= 50 ? (START[c] + p) % 52 : -1;
const cur = st => st.order[st.turn];
const active = st => st.order.filter(c => !st.players[c].out);
function ev(st, e) { st.seq++; e.seq = st.seq; st.events.push(e); if (st.events.length > 40) st.events = st.events.slice(-40); }
const legal = (st, c, d) => st.pawns[c].map((p, k) => ((p === YARD && d === 6) || (p >= 0 && p + d <= FIN)) ? k : -1).filter(k => k >= 0);

function newState(seats, n, stake, first) {
  const order = ORDER.filter(c => seats.some(s => s.color === c)), players = {};
  seats.forEach(s => { players[s.color] = { name: s.name, av: s.av, bot: !!s.bot, out: false, misses: 0 }; });
  const t = now();
  return { order, players, pawns: Object.fromEntries(order.map(c => [c, Array(n).fill(YARD)])), turn: Math.max(0, order.indexOf(first)),
    phase: 'roll', dice: null, movable: [], sixes: 0, next_at: t + 1.5, deadline: t + 21.5, turn_s: 20, stake,
    last: {}, events: [], seq: 0, winner: null, over: false, started: t, stats: Object.fromEntries(order.map(c => [c, { caps: 0, sixes: 0 }])) };
}
function danger(st, c, t) {
  for (const o of active(st)) if (o !== c) for (const q of st.pawns[o]) { const oi = ti(o, q); if (oi >= 0) { const d = ((t - oi) % 52 + 52) % 52; if (d >= 1 && d <= 6) return true; } }
  return false;
}
function best(st, c, d, moves) {
  let b = moves[0], bs = -1e9;
  for (const k of moves) {
    const p = st.pawns[c][k], np = p === YARD ? 0 : p + d, t = ti(c, np), cu = ti(c, p);
    let s = np / 8 + Math.random() * 3;
    if (p === YARD) s += 50; if (np === FIN) s += 80; if (p <= 50 && np > 50) s += 35;
    if (t >= 0) { if (SAFE.has(t)) s += 15; else { if (active(st).some(o => o !== c && st.pawns[o].some(q => ti(o, q) === t))) s += 100; if (danger(st, c, t)) s -= 40; } }
    if (cu >= 0 && !SAFE.has(cu) && danger(st, c, cu)) s += 25;
    if (s > bs) { bs = s; b = k; }
  }
  return b;
}
function nextTurn(st) { for (let i = 0; i < st.order.length; i++) { st.turn = (st.turn + 1) % st.order.length; if (!st.players[cur(st)].out) return; } }
function begin(st, t, wait) { st.phase = 'roll'; st.dice = null; st.movable = []; st.next_at = t + wait; st.deadline = t + wait + st.turn_s; }
function finish(st, w) { st.over = true; st.winner = w; st.phase = 'over'; st.movable = []; ev(st, { t: w ? 'win' : 'end', c: w }); }
function roll(st, c, t, v, auto) {
  if (st.over) return 'over'; if (cur(st) !== c) return 'not_your_turn'; if (st.phase !== 'roll') return 'not_roll_phase';
  const d = v || die(); st.dice = d; st.last[c] = d; if (d === 6) st.stats[c].sixes++;
  ev(st, { t: 'roll', c, v: d, auto: !!auto });
  const moves = legal(st, c, d);
  if (!moves.length) { ev(st, { t: 'nomove', c, v: d }); st.sixes = 0; nextTurn(st); begin(st, t, 1.6); return null; }
  st.phase = 'move'; st.movable = moves; st.next_at = t + .9; st.deadline = t + .9 + st.turn_s;
  if (moves.length === 1 || moves.every(k => st.pawns[c][k] === YARD)) return move(st, c, moves[0], t + .9, true, true);
  return null;
}
function move(st, c, k, t, auto, forced) {
  if (st.over) return 'over'; if (cur(st) !== c) return 'not_your_turn'; if (st.phase !== 'move') return 'not_move_phase';
  if (!st.movable.includes(k)) return 'illegal_move';
  const d = st.dice, pw = st.pawns[c], frm = pw[k], to = frm === YARD ? 0 : frm + d; pw[k] = to;
  const cap = [], t2 = ti(c, to);
  if (t2 >= 0 && !SAFE.has(t2)) for (const o of active(st)) if (o !== c) st.pawns[o].forEach((q, j) => { if (ti(o, q) === t2) { st.pawns[o][j] = YARD; cap.push([o, j]); } });
  const fin = to === FIN; st.stats[c].caps += cap.length;
  ev(st, { t: 'move', c, k, frm, to, cap, fin, auto: !!auto && !forced });
  const anim = .35 + (frm === YARD ? 1 : d) * .17 + (cap.length ? .7 : 0) + (fin ? .4 : 0);
  if (pw.every(p => p === FIN)) { finish(st, c); return null; }
  const extra = d === 6 || cap.length > 0 || fin;
  st.sixes = d === 6 ? st.sixes + 1 : 0;
  if (st.sixes >= 3) { ev(st, { t: 'six3', c }); st.sixes = 0; nextTurn(st); }
  else if (!extra) { st.sixes = 0; nextTurn(st); }
  begin(st, t, anim + .4); return null;
}
function leave(st, c, t, why) {
  const p = st.players[c]; if (!p || p.out || st.over) return;
  const was = cur(st) === c; p.out = true; st.pawns[c] = []; ev(st, { t: 'leave', c, why });
  const alive = active(st), humans = alive.filter(x => !st.players[x].bot);
  if (!humans.length) return finish(st, alive.length === 1 && st.stake ? alive[0] : null);
  if (alive.length === 1) return finish(st, alive[0]);
  if (was) { st.sixes = 0; nextTurn(st); begin(st, t, .8); }
}
function tick(st, t) {
  for (let i = 0; i < 8 && !st.over; i++) {
    const c = cur(st), p = st.players[c];
    if (p.bot) { if (t < st.next_at) break; st.phase === 'roll' ? roll(st, c, t, die()) : move(st, c, best(st, c, st.dice, st.movable), t); continue; }
    if (t < st.deadline) break;
    p.misses++; ev(st, { t: 'timeout', c, n: p.misses });
    if (st.stake && p.misses >= 3) leave(st, c, t, 'timeout');
    else if (st.phase === 'roll') roll(st, c, t, die(), true);
    else move(st, c, best(st, c, st.dice, st.movable), t, true);
  }
}
function view(st, me, since) {
  const c = cur(st), cp = st.players[c], t = now();
  return { order: st.order, players: Object.fromEntries(Object.entries(st.players).map(([k, p]) => [k, { name: p.name, av: p.av, bot: p.bot, out: p.out, me: k === me }])),
    pawns: st.pawns, turn: st.over ? null : c, phase: st.phase, dice: st.dice, movable: c === me && st.phase === 'move' ? st.movable : [],
    deadline_ms: st.over || cp.bot ? 0 : Math.max(0, Math.round((st.deadline - t) * 1000)), turn_ms: st.turn_s * 1000, last: st.last,
    done: Object.fromEntries(st.order.map(k => [k, st.pawns[k].filter(p => p === FIN).length])), events: st.events.filter(e => e.seq > since),
    seq: st.seq, over: st.over, winner: st.winner, stats: st.stats[me], started: st.started };
}

/* ---------- سرور نمایشی منچ (میز در localStorage تا بین صفحه ها بماند) ---------- */
const S = GC.S, save = GC.save, store = GC.store;
const err = code => { const e = new Error(code); e.code = code; return e; };
const loadM = () => store.get('demo_match', null), saveM = m => store.set('demo_match', m);
function makeMatch(cfg, guest) {
  const colors = SEATS[cfg.players], names = [...BOTS].sort(() => Math.random() - .5);
  const seats = colors.map(c => c === 'yellow' ? { color: c, name: 'شما', av: 7 } : guest && c === 'red' ? { color: c, name: 'دوست شما', av: 11, bot: true } : { color: c, name: 'ربات ' + names.pop(), av: 1 + Math.floor(Math.random() * 22), bot: true });
  const st = newState(seats, cfg.pawns, cfg.mode === 'stake', 'yellow');
  st.pot = cfg.mode === 'stake' ? cfg.entry * colors.length : 0;
  return { id: 'demo' + Date.now().toString(36), status: 'playing', cfg, state: st, settled: false };
}
function settle(m) {
  if (m.settled || m.status !== 'over') return; m.settled = true; m.chat = [];
  const won = m.state.winner === 'yellow'; S.games++;
  if (won) { S.wins++; if (m.cfg.mode === 'stake') { S.bal += m.state.pot; S.won += m.state.pot; GC.ledger('جایزهٔ منچ', m.state.pot, 'prize'); } }
  save();
}
/* گفتگوی نمایشی: ربات ها گاهی جواب کوتاه می دهند */
const QUIPS = ['سلام!', 'خوش‌بازی!', 'آفرین', 'شانسی بود', 'زود باش', 'این دفعه می‌برم', 'یک دست دیگه؟'];
function botTalk(m) {
  if (m.status !== 'playing') return;
  m.chat = m.chat || []; m.chatAt = m.chatAt || Date.now();
  if (Date.now() - m.chatAt < 9000 || Math.random() > .2) return;
  const bots = m.state.order.filter(c => m.state.players[c].bot && !m.state.players[c].out); if (!bots.length) return;
  const c = bots[Math.floor(Math.random() * bots.length)], p = m.state.players[c];
  m.chatAt = Date.now();
  m.chat.push({ id: (m.chat.length ? m.chat[m.chat.length - 1].id : 0) + 1, color: c, name: p.name, av: p.av, pic: '', bot: true, text: QUIPS[Math.floor(Math.random() * QUIPS.length)], at: Math.round(Date.now() / 1000), me: false });
}
function out(m, since, chat) {
  const o = { id: m.id, status: m.status, cfg: m.cfg, me: 'yellow' };
  if (chat != null) o.chat = (m.chat || []).filter(x => x.id > chat).slice(-40);
  if (m.status === 'lobby') { o.lobby = { seats: m.seats, code: m.code, host: true, link: 'https://t.me/your_gameclub_bot?start=ludo_' + m.code }; return o; }
  o.game = view(m.state, 'yellow', since); o.pot = m.state.pot || 0;
  if (m.status === 'over') o.result = { won: m.state.winner === 'yellow', prize: m.state.winner === 'yellow' ? o.pot : 0, lost: m.state.winner === 'yellow' ? 0 : m.cfg.entry };
  return o;
}
function payEntry(cfg) {
  if (cfg.mode !== 'stake') return;
  if (S.bal < cfg.entry) throw err('insufficient');
  S.bal -= cfg.entry; S.spent += cfg.entry; GC.ledger('ورودی منچ', -cfg.entry, 'entry'); save();
}
const ludo = {
  async queueJoin(cfg) {
    if (cfg.solo) { const mm = makeMatch(Object.assign({}, cfg, { mode: 'free', entry: 0 })); saveM(mm); return { state: 'matched', match: mm.id }; }
    payEntry(cfg); store.set('demo_q', { cfg, t0: Date.now() }); return ludo.queueStatus();
  },
  async queueStatus() {
    const q = store.get('demo_q', null), m = loadM();
    if (!q) return m && m.status === 'playing' ? { state: 'matched', match: m.id } : { state: 'none' };
    const waited = (Date.now() - q.t0) / 1000;
    if (waited > 3.2) { const mm = makeMatch(q.cfg); saveM(mm); store.set('demo_q', null); return { state: 'matched', match: mm.id }; }
    return { state: 'waiting', waited: Math.floor(waited), cfg: q.cfg, found: 1 + Math.min(q.cfg.players - 1, Math.floor(waited / 1.1)), need: q.cfg.players, bots_in: null, can_bots: q.cfg.mode !== 'stake' };
  },
  async queueBots() {
    const q = store.get('demo_q', null); if (!q) return ludo.queueStatus();
    const mm = makeMatch(q.cfg); saveM(mm); store.set('demo_q', null); return { state: 'matched', match: mm.id };
  },
  async queueLeave() {
    const q = store.get('demo_q', null); store.set('demo_q', null);
    if (q && q.cfg.mode === 'stake') { S.bal += q.cfg.entry; S.spent -= q.cfg.entry; GC.ledger('انصراف از صف منچ', q.cfg.entry, 'refund'); save(); }
    return { state: 'none' };
  },
  async invite(cfg) {
    payEntry(cfg);
    const code = Math.random().toString(36).slice(2, 8).toUpperCase();
    const m = { id: 'demo' + Date.now().toString(36), status: 'lobby', cfg, code, t0: Date.now(), seats: [{ color: SEATS[cfg.players][0], name: 'شما', av: 7, me: true }] };
    saveM(m); return { match: m.id, code, link: 'https://t.me/your_gameclub_bot?start=ludo_' + code };
  },
  async join() { throw err('bad_invite'); },
  async start(id) { const m = loadM(); if (!m || m.id !== id) throw err('not_found'); const mm = makeMatch(m.cfg, m.seats.length > 1); mm.id = m.id; saveM(mm); return { ok: true }; },
  async match(id, since = 0, chat = null) {
    let m = loadM(); if (!m || (id && m.id !== id)) throw err('not_found');
    if (m.status === 'lobby') {
      if (m.seats.length === 1 && Date.now() - m.t0 > 5000) { m.seats.push({ color: SEATS[m.cfg.players][1], name: 'دوست شما', av: 11, me: false }); saveM(m); }
      if (m.seats.length === m.cfg.players) { await ludo.start(m.id); m = loadM(); }
      return out(m, since);
    }
    if (m.status === 'playing') { tick(m.state, now()); if (m.state.over) { m.status = 'over'; settle(m); } botTalk(m); saveM(m); }
    return out(m, since, chat);
  },
  async act(id, action, k, since) {
    const m = loadM(); if (!m || m.id !== id) throw err('not_found');
    if (m.status !== 'playing') return out(m, since);
    const t = now(); tick(m.state, t);
    const e = action === 'roll' ? roll(m.state, 'yellow', t) : action === 'move' ? move(m.state, 'yellow', k, t) : (leave(m.state, 'yellow', t, 'left'), null);
    if (!e) m.state.players.yellow.misses = 0;
    if (m.state.over) { m.status = 'over'; settle(m); }
    saveM(m); if (e && e !== 'over') throw err(e);
    return out(m, since);
  },
  async roll(id, since) { return ludo.act(id, 'roll', null, since); },
  async move(id, k, since) { return ludo.act(id, 'move', k, since); },
  async leave(id) { const m = loadM(); if (m && m.status === 'lobby') { saveM(null); if (m.cfg.mode === 'stake') { S.bal += m.cfg.entry; GC.ledger('لغو میز منچ', m.cfg.entry, 'refund'); save(); } return { left: true }; } if (m && m.status === 'playing') { S.games++; save(); return ludo.act(id, 'leave', null, 0); } return { left: true }; },
  async chat(id, text) {
    const m = loadM(); if (!m || m.id !== id || m.status !== 'playing') throw err('not_found');
    text = String(text || '').replace(/\s+/g, ' ').trim().slice(0, 140); if (!text) throw err('empty');
    m.chat = m.chat || []; const last = m.chat.filter(x => x.me).pop();
    if (last && Date.now() / 1000 - last.at < 1.5) throw err('chat_slow');
    const id2 = (m.chat.length ? m.chat[m.chat.length - 1].id : 0) + 1;
    m.chat.push({ id: id2, color: 'yellow', name: 'شما', av: 7, pic: '', text, at: Math.round(Date.now() / 1000), me: true });
    m.chatAt = Date.now() - 7000; saveM(m); return { ok: true, id: id2 };
  },
  async active() { const m = loadM(); return m && (m.status === 'playing' || m.status === 'lobby') ? m.id : null; },
};

/* میزهای باز برای صفحهٔ خانه (منچ و حکم نمایشی) */
function demoTables() {
  const out = [];
  for (const [key, game, mine] of [['demo_football', 'football', '0'], ['demo_hokm', 'hokm', '0'], ['demo_match', 'ludo', 'yellow']]) {
    const m = store.get(key, null); if (!m) continue;
    if (m.status === 'lobby') out.push({ kind: 'lobby', id: m.id, game, cfg: m.cfg, found: m.seats.length, need: m.cfg.players || 4, host: true, players: m.seats });
    else if (m.status === 'playing' && !m.state.over) {
      const st = m.state, t = { kind: 'playing', id: m.id, game, cfg: m.cfg, players: (st.order || Object.keys(st.players)).map(c => Object.assign({}, st.players[c], { me: String(c) === mine })) };
      if (game === 'football') { t.score = [st.score[0], st.score[1]]; t.target = st.target; t.my_turn = st.phase === 'play' && st.turn === 0; }
      else if (game === 'hokm') { t.score = [st.score[0], st.score[1]]; t.target = st.target; t.my_turn = (st.phase === 'trump' || st.phase === 'play') && String(st.phase === 'trump' ? st.hakem : st.turn) === '0'; }
      else t.my_turn = st.order[st.turn] === 'yellow';
      out.push(t);
    }
  }
  for (const [key, game] of [['demo_fq', 'football'], ['demo_hq', 'hokm'], ['demo_q', 'ludo']]) { const q = store.get(key, null); if (q) out.push({ kind: 'queue', game, cfg: q.cfg, found: 1, need: q.cfg.players || 4 }); }
  return out;
}

/* ---------- داده نمایشی بقیه صفحه ها ---------- */
const data = {
  async me() {
    return { player: { name: 'بازیکن', av: 7, points: S.bal, games: S.games, wins: S.wins, show_spend: S.showSpend ? 1 : 0 },
      history: S.ledger.map(l => ({ kind: l.k, amount: l.a, note: l.t, created_at: Math.round(l.at / 1000) })),
      notify: Object.keys(S.notify).filter(k => S.notify[k]), obour: { linked: true, balance: 240000 }, active_match: await ludo.active(), tables: demoTables(),
      settings: { stake: true, shop: false, entries: [50, 100, 250, 500], packs: [250, 500, 1000, 2500], rate: GC.RATE, turn_s: 20, rake: 0, bot: '', obour_bot: '' } };
  },
  async charge(points) { S.bal += points; GC.ledger('شارژ از کیف پول عبور', points, 'charge'); save(); return { ok: true, points }; },
  async notify(game) { S.notify[game] = !S.notify[game]; save(); return { on: S.notify[game] }; },
  async setFlag(f, v) { if (f === 'show_spend') { S.showSpend = !!v; save(); } return { ok: true }; },
  async leaderboard(kind, period) {
    const K = { week: 1, month: 3.8, all: 9.5 }[period] || 1;
    const rows = GC.LB[kind].map(([p, w, v]) => ({ name: GC.PEOPLE[p][0], av: GC.PEOPLE[p][1], wins: Math.round(w * K), value: Math.round(v * K / 50) * 50, me: false }));
    return { kind, period, rows, sample: true, mine: { value: kind === 'top' ? S.won : S.spent, wins: S.wins, games: S.games, visible: kind === 'top' || !!S.showSpend } };
  },
  async shop() { if (!S.shopOn) throw err('shop_off'); return { plans: GC.SHOP.filter(s => s.cat === 'net').map((s, i) => ({ id: i + 1, title: s.t, gb: [10, 30][i], days: 30, price: s.p * GC.RATE, points: s.p })), rate: GC.RATE, obour: { linked: true, balance: 240000 }, sample: true }; },
  async buy(planId) { if (!S.shopOn) throw err('shop_off'); const p = (await data.shop()).plans.find(x => x.id === planId); if (S.bal < p.points) throw err('insufficient'); S.bal -= p.points; S.spent += p.points; GC.ledger('خرید: ' + p.title, -p.points, 'shop'); save(); return { ok: true, title: p.title }; },
  async transfer(points) { if (!S.shopOn) throw err('shop_off'); if (S.bal < points) throw err('insufficient'); S.bal -= points; S.spent += points; GC.ledger('انتقال به کیف پول عبور', -points, 'transfer'); save(); return { ok: true, points, toman: points * GC.RATE }; },
};
GC.demo = { ludo, data };
})();
