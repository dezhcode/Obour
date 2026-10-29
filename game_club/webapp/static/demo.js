/* حالت نمایشی: وقتی صفحه بیرون از تلگرام باز شود (initData نیست)، همان
   API سرور اینجا در مرورگر شبیه سازی می شود. موتور منچ نسخه دوقلوی
   game_club/ludo.py است تا رفتار پیش نمایش و سرور یکی باشد.
   هیچ چیز این فایل در حالت واقعی (داخل تلگرام) استفاده نمی شود. */
(() => {
const { TRACK, ORDER } = GC.LUDO;
const START = { blue: 0, red: 13, green: 26, yellow: 39 }, SAFE = new Set(GC.LUDO.SAFE), FIN = 56, YARD = -1;
const SEATS = { 2: ['yellow', 'red'], 4: ['blue', 'red', 'green', 'yellow'] };
const BOTS = ['lucky_falcon', 'brave_tiger', 'swift_panda', 'calm_otter', 'jolly_ace', 'witty_fox', 'royal_queen', 'cosmic_ninja', 'misty_raven', 'golden_comet', 'keen_hawk', 'sunny_mango'];
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
  const seats = colors.map(c => c === 'yellow' ? { color: c, name: 'خودت', av: 7 } : guest && c === 'red' ? { color: c, name: 'رفیقت', av: 11, bot: true } : { color: c, name: names.pop(), av: 1 + Math.floor(Math.random() * 22), bot: true });
  const st = newState(seats, cfg.pawns, cfg.mode !== 'free', 'yellow');
  return { id: 'demo' + Date.now().toString(36), status: 'playing', cfg, state: st, settled: false };
}
function settle(m) {
  if (m.settled || m.status !== 'over') return; m.settled = true; m.chat = [];
  const won = m.state.winner === 'yellow'; S.games++;
  if (won) S.wins++;
  if (m.cfg.mode === 'ranked') m.rank = GC.demo.rank('ludo', won);
  save();
}
/* گفتگوی نمایشی: ربات ها گاهی جواب کوتاه می دهند */
const QUIPS = ['سلام!', 'خوش‌بازی!', 'آفرین', 'شانسی بود', 'زود باش', 'این دفعه می‌برم', 'یه دست دیگه؟'];
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
  o.game = view(m.state, 'yellow', since);
  if (m.status === 'over') o.result = Object.assign({ won: m.state.winner === 'yellow', coins: 0, cups: 0 }, m.rank);
  return o;
}
const ludo = {
  async queueJoin(cfg) {
    if (cfg.solo) { const mm = makeMatch(Object.assign({}, cfg, { mode: 'free', entry: 0 })); saveM(mm); return { state: 'matched', match: mm.id }; }
    store.set('demo_q', { cfg, t0: Date.now() }); return ludo.queueStatus();
  },
  async queueStatus() {
    const q = store.get('demo_q', null), m = loadM();
    if (!q) return m && m.status === 'playing' ? { state: 'matched', match: m.id } : { state: 'none' };
    const waited = (Date.now() - q.t0) / 1000;
    if (waited > 3.2) { const mm = makeMatch(q.cfg); saveM(mm); store.set('demo_q', null); return { state: 'matched', match: mm.id }; }
    return { state: 'waiting', waited: Math.floor(waited), cfg: q.cfg, found: 1 + Math.min(q.cfg.players - 1, Math.floor(waited / 1.1)), need: q.cfg.players, bots_in: null, can_bots: q.cfg.mode === 'free' };
  },
  async queueBots() {
    const q = store.get('demo_q', null); if (!q) return ludo.queueStatus();
    const mm = makeMatch(q.cfg); saveM(mm); store.set('demo_q', null); return { state: 'matched', match: mm.id };
  },
  async queueLeave() {
    const q = store.get('demo_q', null); store.set('demo_q', null);
    return { state: 'none' };
  },
  async invite(cfg) {
    
    const code = Math.random().toString(36).slice(2, 8).toUpperCase();
    const m = { id: 'demo' + Date.now().toString(36), status: 'lobby', cfg, code, t0: Date.now(), seats: [{ color: SEATS[cfg.players][0], name: 'خودت', av: 7, me: true }] };
    saveM(m); return { match: m.id, code, link: 'https://t.me/your_gameclub_bot?start=ludo_' + code };
  },
  async join() { throw err('bad_invite'); },
  async start(id) { const m = loadM(); if (!m || m.id !== id) throw err('not_found'); const mm = makeMatch(m.cfg, m.seats.length > 1); mm.id = m.id; saveM(mm); return { ok: true }; },
  async match(id, since = 0, chat = null) {
    let m = loadM(); if (!m || (id && m.id !== id)) throw err('not_found');
    if (m.status === 'lobby') {
      if (m.seats.length === 1 && Date.now() - m.t0 > 5000) { m.seats.push({ color: SEATS[m.cfg.players][1], name: 'رفیقت', av: 11, me: false }); saveM(m); }
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
  async leave(id) { const m = loadM(); if (m && m.status === 'lobby') { saveM(null); return { left: true }; } if (m && m.status === 'playing') { S.games++; save(); return ludo.act(id, 'leave', null, 0); } return { left: true }; },
  async chat(id, text) {
    const m = loadM(); if (!m || m.id !== id || m.status !== 'playing') throw err('not_found');
    text = String(text || '').replace(/\s+/g, ' ').trim().slice(0, 140); if (!text) throw err('empty');
    m.chat = m.chat || []; const last = m.chat.filter(x => x.me).pop();
    if (last && Date.now() / 1000 - last.at < 1.5) throw err('chat_slow');
    const id2 = (m.chat.length ? m.chat[m.chat.length - 1].id : 0) + 1;
    m.chat.push({ id: id2, color: 'yellow', name: 'خودت', av: 7, pic: '', text, at: Math.round(Date.now() / 1000), me: true });
    m.chatAt = Date.now() - 7000; saveM(m); return { ok: true, id: id2 };
  },
  async active() { const m = loadM(); return m && (m.status === 'playing' || m.status === 'lobby') ? m.id : null; },
};

/* میزهای باز برای صفحهٔ خانه (منچ و حکم نمایشی) */
function demoTables() {
  const out = [];
  for (const [key, game, mine] of [['demo_football', 'football', '0'], ['demo_hokm', 'hokm', '0'], ['demo_match', 'ludo', 'yellow'], ['demo_billiard', 'billiard', '0'], ['demo_divar', 'divar', '0'], ['demo_snakes', 'snakes', '0']]) {
    const m = store.get(key, null); if (!m) continue;
    if (m.status === 'lobby') out.push({ kind: 'lobby', id: m.id, game, cfg: m.cfg, found: m.seats.length, need: m.cfg.players || 4, host: true, players: m.seats });
    else if (m.status === 'playing' && !m.state.over) {
      const st = m.state, t = { kind: 'playing', id: m.id, game, cfg: m.cfg, players: (st.order || Object.keys(st.players)).map(c => Object.assign({}, st.players[c], { me: String(c) === mine })) };
      if (game === 'football') { t.score = [st.score[0], st.score[1]]; t.target = st.target; t.my_turn = st.phase === 'play' && st.turn === 0; }
      else if (game === 'hokm') { t.score = [st.score[0], st.score[1]]; t.target = st.target; t.my_turn = (st.phase === 'trump' || st.phase === 'play') && String(st.phase === 'trump' ? st.hakem : st.turn) === '0'; }
      else if (game === 'billiard') { t.score = [0, 1].map(tm => st.solids < 0 ? 0 : 7 - [0, 1, 2, 3, 4, 5, 6].filter(i => st.balls[(st.solids === tm ? 1 : 9) + i]).length); t.target = 7; t.my_turn = st.turn === 0; }
      else if (game === 'divar') { t.my_turn = st.turn === 0; t.left = typeof DVEngine !== 'undefined' ? DVEngine.dist(st, '0') : null; }
      else if (game === 'snakes') { t.my_turn = st.turn === 0; t.pos = st.players['0'].pos; }
      else t.my_turn = st.order[st.turn] === 'yellow';
      out.push(t);
    }
  }
  for (const [key, game] of [['demo_fq', 'football'], ['demo_hq', 'hokm'], ['demo_q', 'ludo'], ['demo_bq', 'billiard'], ['demo_dq', 'divar'], ['demo_sq', 'snakes']]) { const q = store.get(key, null); if (q) out.push({ kind: 'queue', game, cfg: q.cfg, found: 1, need: q.cfg.players || 4 }); }
  return out;
}

/* ---------- دوستان نمونه ---------- */
const PPL = {
  d_sara: { name: 'sara_m', av: 5, online: true, bio: 'عاشق منچ و دست‌های آخر', games: 142, wins: 81 },
  d_kian: { name: 'kian_r', av: 3, online: true, playing: 'hokm', games: 210, wins: 120 },
  d_negar: { name: 'negar_x', av: 9, online: true, games: 64, wins: 30 },
  d_reza: { name: 'reza_gm', av: 12, ago: 7200, games: 88, wins: 40 },
  d_mahsa: { name: 'mahsa', av: 13, ago: 90000, games: 31, wins: 12 },
  d_arash: { name: 'arash_dev', av: 10, online: true, games: 12, wins: 4 },
  d_leila: { name: 'leila_m', av: 21, ago: 3000, games: 57, wins: 33 },
  d_pouya: { name: 'pouya_k', av: 6, ago: 600, games: 9, wins: 2 },
};
function fr() {
  if (!S.fr) { S.fr = { friends: ['d_sara', 'd_kian', 'd_negar', 'd_reza', 'd_mahsa'], incoming: ['d_arash', 'd_leila'], outgoing: [], blocked: [],
    dms: { d_sara: [{ id: 1, me: false, kind: 'text', text: 'سلام! یه دست منچ بزنیم؟', at: Math.round(Date.now() / 1000) - 600 }] }, read: {} }; save(); }
  return S.fr;
}
/* ---------- داده نمایشی بقیه صفحه ها ---------- */
const DAILY = [1, 1, 2, 2, 3, 3, 5];
const today = () => Math.floor((Date.now() / 1000 + 12600) / 86400);
function daily() {
  const d = S.daily || { day: 0, streak: 0 }, t = today(), claimed = d.day === t, cont = d.day === t - 1;
  const streak = claimed || cont ? d.streak : 0, next = claimed ? streak : streak % DAILY.length + 1;
  return { plan: DAILY, day: claimed ? streak : streak % DAILY.length, next, claimed };
}
const LEAGUES = [[1000, 'قهرمان'], [600, 'الماسی'], [300, 'طلایی'], [100, 'نقره‌ای'], [0, 'برنزی']];
const league = c => LEAGUES.find(([f]) => c >= f)[1];
function ranks() {
  const R = S.ranks || {};
  return Object.fromEntries(Object.entries(R).map(([g, r]) => [g, Object.assign({}, r, { league: league(r.cups) })]));
}
// آخر بازی رتبه ای نمونه: +۲۰ جام و ۲ سکه برای برد، −۱۰ جام برای باخت (کمتر از صفر نه)
function rank(game, won) {
  S.ranks = S.ranks || {}; const r = S.ranks[game] = S.ranks[game] || { cups: 0, games: 0, wins: 0 };
  const cups = won ? 20 : -Math.min(10, r.cups), coins = won ? 2 : 0;
  r.cups += cups; r.games++; if (won) r.wins++;
  if (coins) { S.bal += coins; GC.ledger('جایزهٔ بازی رتبه‌ای', coins, 'reward'); }
  save();
  return { cups, coins, rank: Object.assign({}, r, { league: league(r.cups) }) };
}
const STYLE = [['table:a', 'table', 'a', 'میز کلاسیک', 0], ['table:b', 'table', 'b', 'میز کافه شب', 80], ['table:c', 'table', 'c', 'میز AsoTas', 80],
  ['cards:m', 'cards', 'm', 'ورق مدرن', 0], ['cards:a', 'cards', 'a', 'ورق کلاسیک', 0], ['cards:b', 'cards', 'b', 'ورق کافه شب', 50], ['cards:c', 'cards', 'c', 'ورق AsoTas', 50], ['cards:d', 'cards', 'd', 'ورق رنگ تمام', 50]];
const data = {
  async me() {
    const F = fr(), unread = Object.keys(F.dms).reduce((a, u) => a + F.dms[u].filter(m => !m.me && m.id > (F.read[u] || 0)).length, 0);
    return { social: { requests: F.incoming.length, unread }, covers: [{ id: 'gc', name: 'AsoTas' }], player: { bio: S.bio || '', cover: S.cover || 'gc', name: S.uname || 'lucky_falcon', name_next: S.unameAt ? S.unameAt + 30 * 86400 : 0, name_hint: !S.unameSeen && !S.unameAt,
        joined: Math.round(Date.now() / 1000) - 42 * 86400, av: 7, points: S.bal, games: S.games, wins: S.wins, show_spend: 0 },
      history: S.ledger.map(l => ({ kind: l.k, amount: l.a, note: l.t, created_at: Math.round(l.at / 1000) })),
      notify: Object.keys(S.notify).filter(k => S.notify[k]), active_match: await ludo.active(), tables: demoTables(),
      daily: daily(), ranks: ranks(), account: { kind: 'telegram' },
      style: Object.assign({ table: 'a', cards: 'a' }, S.style || {}),
      settings: { ranked: true, rate: GC.RATE, turn_s: 20, bot: '', rank: { win: 20, lose: 10, coins: 2, day: 10 } } };
  },
  // فروشگاه ظاهر (همان کاتالوگ service.STYLE_ITEMS)
  async style() {
    const own = S.owned || [], cur = Object.assign({ table: 'a', cards: 'a' }, S.style || {});
    return { items: STYLE.map(([id, kind, look, name, price]) => ({ id, kind, look, name, price, owned: !price || own.includes(id), on: cur[kind] === look })), ...cur, points: S.bal, sample: true };
  },
  async styleBuy(id) {
    const it = STYLE.find(x => x[0] === id); if (!it) throw err('not_found');
    const [, kind, look, name, price] = it; S.owned = S.owned || [];
    if (price && !S.owned.includes(id)) { if (S.bal < price) throw err('insufficient'); S.bal -= price; GC.ledger('خرید ' + name, -price, 'style'); S.owned.push(id); }
    S.style = Object.assign({ table: 'a', cards: 'a' }, S.style || {}, { [kind]: look }); save(); return data.style();
  },
  async styleUse(id) {
    const it = STYLE.find(x => x[0] === id); if (!it) throw err('not_found');
    const [, kind, look, , price] = it; if (price && !(S.owned || []).includes(id)) throw err('not_owned');
    S.style = Object.assign({ table: 'a', cards: 'a' }, S.style || {}, { [kind]: look }); save(); return data.style();
  },
  // پروفایل نمونه بیرون از تلگرام (کارنامهٔ واقعی هر بازی از سرور می آید)
  async profile() {
    const t = Date.now() / 1000;
    return { sample: true, games: [{ game: 'hokm', games: 14, wins: 9, prize: 12 }, { game: 'football', games: 6, wins: 2, prize: 0 }, { game: 'ludo', games: Math.max(3, S.games), wins: Math.max(1, S.wins), prize: 0 }],
      recent: [{ game: 'hokm', won: true, prize: 2, cups: 20, at: t - 3600, mode: 'ranked' }, { game: 'football', won: false, prize: 0, cups: 0, at: t - 7200, mode: 'free' },
        { game: 'hokm', won: true, prize: 0, cups: 0, at: t - 90000, mode: 'free' }, { game: 'ludo', won: false, prize: 0, cups: -10, at: t - 100000, mode: 'ranked' }] };
  },
  // یوزرنیم نمونه: همان قاعده ها؛ چند اسم «گرفته شده» برای دیدن پیام و پیشنهادها
  async nameCheck(n) {
    n = GC.normName(n); const bad = GC.nameProblem(n), TAKEN = ['sara_m', 'kian_r', 'negar_x', 'admin', 'obour', 'gameclub'];
    if (bad) return { name: n, ok: false, error: bad };
    if (TAKEN.includes(n) && n !== (S.uname || 'lucky_falcon')) return { name: n, ok: false, error: 'name_taken', suggest: [n + '_gc', 'the_' + n, n + '_play'].filter(x => x.length <= 16) };
    return { name: n, ok: true };
  },
  async setName(n) {
    const r = await data.nameCheck(n); if (!r.ok) throw err(r.error);
    const now = Math.round(Date.now() / 1000);
    if (S.unameAt && now < S.unameAt + 30 * 86400) throw err('name_wait:' + Math.ceil((S.unameAt + 30 * 86400 - now) / 86400));
    S.uname = r.name; S.unameAt = now; S.unameSeen = true; save();
    return { name: S.uname, name_next: now + 30 * 86400, name_hint: false };
  },
  async saveProfile(b) { if ('bio' in b) S.bio = String(b.bio || '').replace(/[<>&"'`\\]/g, '').trim().slice(0, 80); if ('cover' in b) S.cover = b.cover; save(); return { ok: true, bio: S.bio || '', cover: S.cover || 'gc' }; },
  async nameSeen() { S.unameSeen = true; save(); return { ok: true }; },
  // جایزهٔ روزانه نمونه (همان قاعدهٔ service.daily_claim)
  async daily() {
    const d = daily(); if (d.claimed) throw err('daily_done');
    const coins = d.plan[d.next - 1]; S.daily = { day: today(), streak: d.next }; S.bal += coins; GC.ledger('جایزهٔ روزانه · روز ' + d.next, coins, 'daily'); save();
    return { coins, points: S.bal, daily: daily() };
  },
  async notify(game) { S.notify[game] = !S.notify[game]; save(); return { on: S.notify[game] }; },
  async setFlag() { return { ok: true }; },
  async leaderboard(kind, period) {
    const K = { week: 1, month: 3.8, all: 9.5 }[period] || 1;
    const rows = GC.LB[kind].map(([p, w, v]) => ({ name: GC.PEOPLE[p][0], av: GC.PEOPLE[p][1], wins: Math.round(w * K), value: Math.round(v * K / 50) * 50, me: false }));
    return { kind, period, rows, sample: true, mine: { value: 0, wins: S.wins, games: S.games, visible: kind === 'top' } };
  },
  // ---------- دوستان و پیام خصوصی (نمونه بیرون از تلگرام) ----------
  async friends() {
    const F = fr(), now = Date.now() / 1000, unread = u => (F.dms[u] || []).filter(m => !m.me && m.id > (F.read[u] || 0)).length;
    const pub = u => { const p = PPL[u]; return { uid: u, name: p.name, av: p.av, pic: '', bio: p.bio || '' }; };
    const friends = F.friends.map(u => ({ ...pub(u), online: !!PPL[u].online, playing: PPL[u].playing || null, seen: PPL[u].online ? now : now - (PPL[u].ago || 7200), unread: unread(u) }))
      .sort((a, b) => (b.online - a.online) || (b.unread - a.unread) || a.name.localeCompare(b.name));
    return { friends, incoming: F.incoming.map(u => ({ ...pub(u), at: now - 900 })), outgoing: F.outgoing.map(pub), blocked: F.blocked.map(pub), sample: true };
  },
  async friendFind(n) {
    n = GC.normName(n); const F = fr();
    if (n === (S.uname || 'lucky_falcon')) return { user: { uid: 'me', name: n, av: 7, pic: '', bio: S.bio || '', games: S.games, wins: S.wins }, relation: 'self' };
    const u = Object.keys(PPL).find(k => PPL[k].name === n); if (!u) throw err('not_found');
    const rel = F.friends.includes(u) ? 'friend' : F.outgoing.includes(u) ? 'outgoing' : F.incoming.includes(u) ? 'incoming' : F.blocked.includes(u) ? 'blocked' : 'none';
    return { user: { uid: u, name: PPL[u].name, av: PPL[u].av, pic: '', bio: PPL[u].bio || '', games: PPL[u].games || 40, wins: PPL[u].wins || 21 }, relation: rel };
  },
  async friendUser(u) {
    const F = fr(), p = PPL[u]; if (!p) throw err('not_found');
    const rel = F.friends.includes(u) ? 'friend' : F.outgoing.includes(u) ? 'outgoing' : F.incoming.includes(u) ? 'incoming' : F.blocked.includes(u) ? 'blocked' : 'none';
    return { user: { uid: u, name: p.name, av: p.av, pic: '', bio: p.bio || '', games: p.games || 40, wins: p.wins || 21, joined: Date.now() / 1000 - 90 * 86400, cover: 'gc', online: !!p.online, playing: p.playing || null, seen: Date.now() / 1000 - (p.ago || 0) }, relation: rel };
  },
  async friendReq(u) { const F = fr(); if (F.incoming.includes(u)) return data.friendAccept(u); if (!F.friends.includes(u) && !F.outgoing.includes(u)) F.outgoing.push(u); F.blocked = F.blocked.filter(x => x !== u); save(); return { relation: F.friends.includes(u) ? 'friend' : 'outgoing' }; },
  async friendAccept(u) { const F = fr(); if (!F.incoming.includes(u)) throw err('no_request'); F.incoming = F.incoming.filter(x => x !== u); F.friends.push(u); save(); return { relation: 'friend' }; },
  async friendDrop(u) { const F = fr(); ['friends', 'incoming', 'outgoing'].forEach(k => { F[k] = F[k].filter(x => x !== u); }); save(); return { relation: 'none' }; },
  async friendBlock(u, on) { const F = fr(); await data.friendDrop(u); F.blocked = F.blocked.filter(x => x !== u); if (on) F.blocked.push(u); save(); return { relation: on ? 'blocked' : 'none' }; },
  async dm(u, since = 0) {
    const F = fr(), p = PPL[u]; if (!p) throw err('not_found');
    const list = F.dms[u] || [], last = list.filter(m => !m.me).pop();
    if (last) { F.read[u] = Math.max(F.read[u] || 0, last.id); save(); }
    return { user: { uid: u, name: p.name, av: p.av, pic: '', bio: p.bio || '', online: !!p.online, playing: p.playing || null, seen: Date.now() / 1000 - (p.ago || 0) },
      relation: F.friends.includes(u) ? 'friend' : 'none', messages: list.filter(m => m.id > since) };
  },
  async dmSend(u, text) {
    const F = fr(); if (!F.friends.includes(u)) throw err('not_friends');
    text = String(text || '').replace(/\s+/g, ' ').trim().slice(0, 300); if (!text) throw err('empty');
    const L = F.dms[u] = F.dms[u] || [], id = (L.length ? L[L.length - 1].id : 0) + 1;
    L.push({ id, me: true, kind: 'text', text, at: Math.round(Date.now() / 1000) }); save();
    if (PPL[u].online) setTimeout(() => { const M = fr().dms[u]; M.push({ id: M[M.length - 1].id + 1, me: false, kind: 'text', text: ['باشه بزن بریم!', 'الان میام', 'عالی بود', 'یه دست دیگه؟'][Math.floor(Math.random() * 4)], at: Math.round(Date.now() / 1000) }); save(); }, 1800);
    return { id };
  },
  async dmInvite(u, game) {
    const F = fr(); if (!F.friends.includes(u)) throw err('not_friends');
    const L = F.dms[u] = F.dms[u] || [], id = (L.length ? L[L.length - 1].id : 0) + 1, name = { hokm: 'حکم', ludo: 'منچ', football: 'فوتبال', billiard: 'بیلیارد', divar: 'دیوار', snakes: 'مار و پله' }[game];
    L.push({ id, me: true, kind: 'invite', text: 'دعوت به ' + name, meta: { game, code: 'DEMO42' }, at: Math.round(Date.now() / 1000) }); save();
    return { match: 'demo', code: 'DEMO42', game, demo: true };
  },
  async groupShare(game) { return { demo: true, game }; },
  // رده بندی هر بازی (نمونه): برنده های این بازی با یوزرنیم
  async gameBoard(game, period) {
    const K = { week: 1, month: 3.5, all: 9 }[period] || 1, base = { hokm: 41, ludo: 33, football: 26, billiard: 22, divar: 18, snakes: 20 }[game] || 30;
    const names = ['kian_r', 'sara_m', 'amirali', 'negar_x', 'reza_gm', 'mahsa', 'pouya_k', 'leila_m', 'arash_dev', 'sina_h'];
    const rows = names.map((n, i) => ({ name: n, av: (i * 5) % 23 + 1, wins: Math.max(1, Math.round((base - i * 3.4) * K)), games: Math.round((base - i * 3.4) * K * 1.7) + 3, value: 0, me: false }));
    const mine = game === 'hokm' ? { wins: Math.round(9 * K), games: Math.round(14 * K), value: 0, rank: 12 } : game === 'football' ? { wins: 2, games: 6, value: 0, rank: 23 } : { wins: 0, games: 0, value: 0, rank: 0 };
    if (period === 'cup') {
      const r = ranks()[game] || { cups: 0 }, cupRows = names.map((n, i) => { const c = Math.max(20, Math.round((base - i * 3.4) * 24)); return { name: n, av: (i * 5) % 23 + 1, cups: c, league: league(c), wins: 0, games: 0, me: false }; });
      return { game, period, rows: cupRows, mine: { cups: r.cups, league: league(r.cups), rank: r.cups ? cupRows.filter(x => x.cups > r.cups).length + 1 : 0 }, sample: true };
    }
    return { game, period, rows, mine, sample: true };
  },
};
GC.demo = { ludo, data, rank };
})();
