/* دیوار نمایشی: بیرون از تلگرام (پیش نمایش در مرورگر) همان API سرور را با همان قواعد
   game_club/divar.py (static/divar-engine.js) در خود مرورگر شبیه سازی می کند.
   میز در localStorage می ماند. داخل تلگرام استفاده نمی شود. */
(() => {
const S = GC.S, save = GC.save, store = GC.store, E = DVEngine;
const BOTS = ['lucky_falcon', 'brave_tiger', 'swift_panda', 'calm_otter', 'jolly_ace', 'witty_fox', 'royal_queen', 'cosmic_ninja', 'misty_raven', 'golden_comet', 'keen_hawk', 'sunny_mango'];
const INTRO = 1.6, STEP_PAUSE = .35, BOT_THINK = 1.1, TURN_S = 25;
const now = () => Date.now() / 1000;
const err = code => { const e = new Error(code); e.code = code; return e; };
const pick = a => a[Math.floor(Math.random() * a.length)];

function ev(st, e) { e.seq = ++st.seq; st.events.push(e); if (st.events.length > 40) st.events = st.events.slice(-40); }
const auto = (st, i) => st.players[st.order[i]].bot || st.players[st.order[i]].out;
function wait(st, t, d) { if (auto(st, st.turn)) d += BOT_THINK; st.turn_id = st.seq; st.next_at = t + d; st.deadline = t + d + st.turn_s; }
const current = st => st.phase === 'play' && !st.over ? st.order[st.turn] : null;

function newState(seats, n, variant) {
  const order = E.seatsOf(n), star = n === 4 && variant === 'star', size = E.sizeOf(star ? 'star' : 'classic');
  const walls = E.WALLS[`${order.length}:${star ? 'star' : 'classic'}`], players = {};
  for (const s of seats) players[s.color] = { name: s.name, av: s.av || 1, bot: !!s.bot, out: false, misses: 0, walls, pos: E.startOf(s.color, size) };
  const t = now();
  const st = { game: 'divar', order, n: order.length, size, star, variant: star ? 'star' : 'classic', players, walls: [], turn: 0, phase: 'play',
    next_at: t + INTRO, deadline: t + INTRO + TURN_S, turn_s: TURN_S, events: [], seq: 0, turn_id: 0, winner: null, over: false, started: t,
    stats: Object.fromEntries(order.map(s => [s, { moves: 0, walls: 0 }])) };
  ev(st, { t: 'start', turn: order[0] });
  wait(st, t, INTRO);
  return st;
}
function next(st, t) { st.turn = (st.turn + 1) % st.n; ev(st, { t: 'turn', c: st.order[st.turn] }); wait(st, t, STEP_PAUSE); }
function check(st, i, t, isAuto) { if (st.over) return 'over'; if (st.turn !== i) return 'not_your_turn'; if (!isAuto && t < st.next_at - .25) return 'not_ready'; return null; }
function move(st, i, r, c, t, isAuto) {
  const e = check(st, i, t, isAuto); if (e) return e;
  const s = st.order[i]; if (!E.moves(st, s).some(m => m[0] === r && m[1] === c)) return 'illegal_move';
  const p = st.players[s], frm = p.pos; p.pos = [r, c]; st.stats[s].moves++;
  ev(st, { t: 'move', c: s, frm, to: [r, c], jump: Math.abs(r - frm[0]) + Math.abs(c - frm[1]) > 1 });
  if (E.atGoal(st, s, r, c)) { finish(st, s); return null; }
  next(st, t); return null;
}
function wall(st, i, o, r, c, t, isAuto) {
  const e = check(st, i, t, isAuto); if (e) return e;
  const s = st.order[i], p = st.players[s]; if (p.walls <= 0) return 'no_walls';
  const we = E.wallError(st, o, r, c); if (we) return we;
  st.walls.push([o, r, c, s]); p.walls--; st.stats[s].walls++;
  ev(st, { t: 'wall', c: s, w: [o, r, c] }); next(st, t); return null;
}
function finish(st, w, why = '') { st.over = true; st.winner = w; st.phase = 'over'; ev(st, { t: w == null ? 'end' : 'win', c: w, why }); }
function tick(st, t) {
  for (let g = 0; g < 4 && !st.over; g++) {
    const i = st.turn, s = st.order[i], p = st.players[s];
    if (auto(st, i)) {
      if (t < st.next_at) break;
      const a = E.botTurn(st, i);
      if (a[0] === 'wall') wall(st, i, a[1], a[2], a[3], t, true); else if (a[0] === 'move') move(st, i, a[1], a[2], t, true); else next(st, t);
      continue;
    }
    if (t < st.deadline) break;
    p.misses++; ev(st, { t: 'timeout', c: s, n: p.misses });
    const m = E.step(st, s); if (m) move(st, i, m[0], m[1], Math.max(t, st.next_at), true); else next(st, t);
  }
}
function view(st, me, since) {
  const t = now(), cur = current(st), au = cur != null && auto(st, st.order.indexOf(cur)), W = E.wallSet(st);
  return { order: st.order, n: st.n, size: st.size, star: st.star, variant: st.variant, me, phase: st.phase, turn: cur, walls: st.walls,
    players: Object.fromEntries(st.order.map(s => { const p = st.players[s]; return [s, { name: p.name, av: p.av, pic: '', bot: p.bot, out: p.out, me: s === me, walls: p.walls, pos: p.pos, left: E.dist(st, s, W) }]; })),
    moves: cur != null && cur === me ? E.moves(st, me) : [],
    ready_ms: cur != null ? Math.max(0, Math.round((st.next_at - t) * 1000)) : 0,
    deadline_ms: cur == null || au ? 0 : Math.max(0, Math.round((st.deadline - t) * 1000)), turn_ms: st.turn_s * 1000,
    events: st.events.filter(e => e.seq > since), seq: st.seq, over: st.over, winner: st.winner, stats: st.stats[me], started: st.started };
}

/* ---------- API نمایشی (هم شکل liveDivar در gc.js) ---------- */
const loadM = () => store.get('demo_divar', null), saveM = m => store.set('demo_divar', m);
function makeMatch(cfg, guest) {
  const n = cfg.players === 4 ? 4 : 2, names = [...BOTS].sort(() => Math.random() - .5), order = E.seatsOf(n);
  const seats = order.map((c, k) => k === 0 ? { color: c, name: 'شما', av: 7 } : (guest && k === (n === 4 ? 2 : 1) ? { color: c, name: 'دوست شما', av: 11, bot: true } : { color: c, name: names.pop(), av: 1 + Math.floor(Math.random() * 22), bot: true }));
  const st = newState(seats, n, cfg.variant); st.stake = cfg.mode !== 'free';
  return { id: 'dv' + Date.now().toString(36), status: 'playing', cfg: Object.assign({ game: 'divar', players: n, variant: st.variant }, cfg), state: st, settled: false };
}
function settle(m) {
  if (m.settled || m.status !== 'over') return; m.settled = true; m.chat = [];
  const won = m.state.winner === '0'; S.games++;
  if (won) S.wins++;
  if (m.cfg.mode === 'ranked') m.rank = GC.demo.rank('divar', won);
  save();
}
const QUIPS = ['سلام!', 'خوش‌بازی!', 'عجب دیواری!', 'راهمو بستی 😅', 'زود باش', 'یک دست دیگه؟'];
function botTalk(m) {
  if (m.status !== 'playing') return;
  m.chat = m.chat || []; m.chatAt = m.chatAt || Date.now();
  if (Date.now() - m.chatAt < 14000 || Math.random() > .15) return;
  const c = pick(m.state.order.slice(1)), p = m.state.players[c]; if (!p.bot) return;
  m.chatAt = Date.now();
  m.chat.push({ id: (m.chat.length ? m.chat[m.chat.length - 1].id : 0) + 1, color: c, name: p.name, av: p.av, pic: '', bot: true, text: pick(QUIPS), at: Math.round(Date.now() / 1000), me: false });
}
function out(m, since, chat) {
  const o = { id: m.id, status: m.status, cfg: m.cfg, me: '0' };
  if (chat != null) o.chat = (m.chat || []).filter(x => x.id > chat).slice(-40);
  if (m.status === 'lobby') { o.lobby = { seats: m.seats, code: m.code, host: true, link: 'https://t.me/your_gameclub_bot?start=divar_' + m.code }; return o; }
  o.game = view(m.state, '0', since);
  if (m.status === 'over') { const won = m.state.winner === '0'; o.result = Object.assign({ won, coins: 0, cups: 0 }, m.rank); }
  return o;
}
async function act(id, since, fn) {
  const m = loadM(); if (!m || m.id !== id) throw err('not_found');
  if (m.status !== 'playing') return out(m, since);
  const t = now(); tick(m.state, t);
  const e = fn(m.state, t);
  if (!e) m.state.players['0'].misses = 0;
  if (m.state.over) { m.status = 'over'; settle(m); }
  saveM(m); if (e && e !== 'over') throw err(e);
  return out(m, since);
}
const divar = {
  async queueJoin(cfg) {
    if (cfg.solo) { const mm = makeMatch(Object.assign({}, cfg, { mode: 'free', entry: 0 })); saveM(mm); return { state: 'matched', match: mm.id }; }
    store.set('demo_dq', { cfg, t0: Date.now() }); return divar.queueStatus();
  },
  async queueStatus() {
    const q = store.get('demo_dq', null), m = loadM();
    if (!q) return m && m.status === 'playing' ? { state: 'matched', match: m.id } : { state: 'none' };
    const waited = (Date.now() - q.t0) / 1000, need = q.cfg.players === 4 ? 4 : 2;
    if (waited > 3) { const mm = makeMatch(q.cfg); saveM(mm); store.set('demo_dq', null); return { state: 'matched', match: mm.id }; }
    return { state: 'waiting', waited: Math.floor(waited), cfg: Object.assign({ players: need }, q.cfg), found: 1, need, bots_in: null, can_bots: q.cfg.mode === 'free' };
  },
  async queueBots() { const q = store.get('demo_dq', null); if (!q) return divar.queueStatus(); const mm = makeMatch(q.cfg); saveM(mm); store.set('demo_dq', null); return { state: 'matched', match: mm.id }; },
  async queueLeave() {
    const q = store.get('demo_dq', null); store.set('demo_dq', null);
    return { state: 'none' };
  },
  async invite(cfg) {
    
    const code = Math.random().toString(36).slice(2, 8).toUpperCase(), n = cfg.players === 4 ? 4 : 2;
    const m = { id: 'dv' + Date.now().toString(36), status: 'lobby', cfg: Object.assign({ game: 'divar', players: n }, cfg), code, t0: Date.now(), seats: [{ color: '0', name: 'شما', av: 7, me: true }] };
    saveM(m); return { match: m.id, code, link: 'https://t.me/your_gameclub_bot?start=divar_' + code };
  },
  async join() { throw err('bad_invite'); },
  async start(id) { const m = loadM(); if (!m || m.id !== id) throw err('not_found'); const mm = makeMatch(m.cfg, m.seats.length > 1); mm.id = m.id; saveM(mm); return { ok: true }; },
  async match(id, since = 0, chat = null) {
    let m = loadM(); if (!m || (id && m.id !== id)) throw err('not_found');
    if (m.status === 'lobby') {
      if (m.seats.length === 1 && Date.now() - m.t0 > 5000) { m.seats.push({ color: '2', name: 'دوست شما', av: 11, me: false }); saveM(m); }
      if (m.seats.length === 2 && m.cfg.players === 2) { await divar.start(m.id); m = loadM(); }
      return out(m, since);
    }
    if (m.status === 'playing') { tick(m.state, now()); if (m.state.over) { m.status = 'over'; settle(m); } botTalk(m); saveM(m); }
    return out(m, since, chat);
  },
  move: (id, r, c, since) => act(id, since, (st, t) => move(st, 0, r, c, t, false)),
  wall: (id, o, r, c, since) => act(id, since, (st, t) => wall(st, 0, o, r, c, t, false)),
  async leave(id) {
    const m = loadM();
    if (m && m.status === 'lobby') { saveM(null); return { left: true }; }
    if (m && m.status === 'playing') {
      const st = m.state; st.players['0'].out = true; ev(st, { t: 'leave', c: '0', why: 'left' });
      finish(st, st.order.find(s => s !== '0'), 'left'); m.status = 'over'; settle(m); saveM(m); return out(m, 0);
    }
    return { left: true };
  },
  async chat(id, text) {
    const m = loadM(); if (!m || m.id !== id || m.status !== 'playing') throw err('not_found');
    text = String(text || '').replace(/\s+/g, ' ').trim().slice(0, 140); if (!text) throw err('empty');
    m.chat = m.chat || []; const lastMine = m.chat.filter(x => x.me).pop();
    if (lastMine && Date.now() / 1000 - lastMine.at < 1.5) throw err('chat_slow');
    const id2 = (m.chat.length ? m.chat[m.chat.length - 1].id : 0) + 1;
    m.chat.push({ id: id2, color: '0', name: 'شما', av: 7, pic: '', text, at: Math.round(Date.now() / 1000), me: true });
    m.chatAt = Date.now() - 11000; saveM(m); return { ok: true, id: id2 };
  },
};
GC.demo = Object.assign(GC.demo || {}, { divar });
})();
