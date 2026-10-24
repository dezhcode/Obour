/* مار و پلهٔ نمایشی: بیرون از تلگرام (پیش نمایش در مرورگر) همان API سرور را با همان قواعد
   game_club/snakes.py در خود مرورگر شبیه سازی می کند. میز در localStorage می ماند. داخل تلگرام استفاده نمی شود. */
(() => {
const S = GC.S, save = GC.save, store = GC.store;
const SN = SNBoard.SN, LD = SNBoard.LD, GOAL = 100;
const BOTS = ['lucky_falcon', 'brave_tiger', 'swift_panda', 'calm_otter', 'jolly_ace', 'witty_fox', 'royal_queen', 'cosmic_ninja', 'misty_raven', 'golden_comet', 'keen_hawk', 'sunny_mango'];
const INTRO = 1.6, BOT_THINK = .9, DICE_T = .75, STEP_T = .17, SLIDE_T = .95, PAUSE = .35, MAX_BONUS = 2, TURN_S = 15;
const SEATS = ['0', '1', '2', '3'];
const now = () => Date.now() / 1000;
const err = code => { const e = new Error(code); e.code = code; return e; };
const pick = a => a[Math.floor(Math.random() * a.length)];

function ev(st, e) { e.seq = ++st.seq; st.events.push(e); if (st.events.length > 40) st.events = st.events.slice(-40); }
const auto = (st, i) => st.players[st.order[i]].bot || st.players[st.order[i]].out;
function wait(st, t, d) { if (auto(st, st.turn)) d += BOT_THINK; st.turn_id = st.seq; st.next_at = t + d; st.deadline = t + d + st.turn_s; }
const current = st => st.phase === 'play' && !st.over ? st.order[st.turn] : null;

function newState(seats, n) {
  const order = SEATS.slice(0, n), players = {};
  for (const s of seats) players[s.color] = { name: s.name, av: s.av || 1, bot: !!s.bot, out: false, misses: 0, pos: 1 };
  const t = now();
  const st = { game: 'snakes', order, n, players, turn: 0, phase: 'play', next_at: t + INTRO, deadline: t + INTRO + TURN_S, turn_s: TURN_S,
    bonus: 0, last: null, events: [], seq: 0, turn_id: 0, winner: null, over: false, started: t,
    stats: Object.fromEntries(order.map(s => [s, { rolls: 0, sixes: 0, ladders: 0, snakes: 0 }])) };
  ev(st, { t: 'start', turn: order[0] });
  wait(st, t, INTRO);
  return st;
}
function finish(st, w, why = '') { st.over = true; st.winner = w; st.phase = 'over'; ev(st, { t: w == null ? 'end' : 'win', c: w, why }); }
function roll(st, i, t, isAuto) {
  if (st.over) return 'over'; if (st.turn !== i) return 'not_your_turn'; if (!isAuto && t < st.next_at - .25) return 'not_ready';
  const s = st.order[i], p = st.players[s], d = 1 + Math.floor(Math.random() * 6), frm = p.pos;
  const mid = frm + d <= GOAL ? frm + d : frm, to = SN[mid] || LD[mid] || mid, via = LD[mid] ? 'ladder' : SN[mid] ? 'snake' : null;
  p.pos = to; const sx = st.stats[s]; sx.rolls++; if (d === 6) sx.sixes++; if (via) sx[via === 'ladder' ? 'ladders' : 'snakes']++;
  const bonus = d === 6 && to !== GOAL && st.bonus < MAX_BONUS;
  st.last = { c: s, v: d };
  ev(st, { t: 'roll', c: s, v: d, frm, mid, to, via, stay: mid === frm, bonus, auto: !!isAuto });
  if (to === GOAL) { finish(st, s); return null; }
  const anim = DICE_T + (mid - frm) * STEP_T + (via ? SLIDE_T : 0) + PAUSE;
  if (bonus) { st.bonus++; wait(st, t, anim); }
  else { st.bonus = 0; st.turn = (st.turn + 1) % st.n; ev(st, { t: 'turn', c: st.order[st.turn] }); wait(st, t, anim); }
  return null;
}
function tick(st, t) {
  for (let k = 0; k < 8 && !st.over; k++) {
    const i = st.turn, s = st.order[i], p = st.players[s];
    // زمان موعد نه لحظهٔ poll (مثل _due سرور)؛ اگر مدت زیادی گذشته از همین لحظه
    if (auto(st, i)) { if (t < st.next_at) break; roll(st, i, t - st.next_at <= 2 ? st.next_at : t, true); continue; }
    if (t < st.deadline) break;
    p.misses++; ev(st, { t: 'timeout', c: s, n: p.misses });
    roll(st, i, Math.max(t, st.next_at), true);
  }
}
function view(st, me, since) {
  const t = now(), cur = current(st), au = cur != null && auto(st, st.order.indexOf(cur));
  const rank = st.over ? [...st.order].sort((a, b) => (a !== st.winner) - (b !== st.winner) || st.players[b].pos - st.players[a].pos) : null;
  return { order: st.order, n: st.n, me, phase: st.phase, turn: cur, can_roll: cur != null && cur === me, bonus: st.bonus, last: st.last, snakes: SN, ladders: LD,
    players: Object.fromEntries(st.order.map(s => { const p = st.players[s]; return [s, { name: p.name, av: p.av, pic: '', bot: p.bot, out: p.out, me: s === me, pos: p.pos }]; })),
    ready_ms: cur != null ? Math.max(0, Math.round((st.next_at - t) * 1000)) : 0,
    deadline_ms: cur == null || au ? 0 : Math.max(0, Math.round((st.deadline - t) * 1000)), turn_ms: st.turn_s * 1000,
    events: st.events.filter(e => e.seq > since), seq: st.seq, over: st.over, winner: st.winner, ranking: rank, stats: st.stats[me], started: st.started };
}

/* ---------- API نمایشی (هم شکل liveSnakes در gc.js) ---------- */
const loadM = () => store.get('demo_snakes', null), saveM = m => store.set('demo_snakes', m);
function makeMatch(cfg, guest) {
  const n = [2, 3, 4].includes(cfg.players) ? cfg.players : 2, names = [...BOTS].sort(() => Math.random() - .5);
  const seats = SEATS.slice(0, n).map((c, k) => k === 0 ? { color: c, name: 'شما', av: 7 } : (guest && k === 1 ? { color: c, name: 'دوست شما', av: 11, bot: true } : { color: c, name: names.pop(), av: 1 + Math.floor(Math.random() * 22), bot: true }));
  const st = newState(seats, n); st.pot = cfg.mode === 'stake' ? cfg.entry * n : 0; st.stake = cfg.mode === 'stake';
  return { id: 'sn' + Date.now().toString(36), status: 'playing', cfg: Object.assign({ game: 'snakes', players: n }, cfg), state: st, settled: false };
}
function settle(m) {
  if (m.settled || m.status !== 'over') return; m.settled = true; m.chat = [];
  const won = m.state.winner === '0'; S.games++;
  if (won) { S.wins++; if (m.cfg.mode === 'stake') { const share = m.state.pot; S.bal += share; S.won += share; GC.ledger('جایزهٔ مار و پله', share, 'prize'); } }
  save();
}
const QUIPS = ['سلام!', 'خوش‌بازی!', 'اون مار مال من بود 😅', 'نردبون رو دیدی؟', 'زود باش', 'یک دست دیگه؟', 'شیش بیا!'];
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
  if (m.status === 'lobby') { o.lobby = { seats: m.seats, code: m.code, host: true, link: 'https://t.me/your_gameclub_bot?start=snakes_' + m.code }; return o; }
  o.game = view(m.state, '0', since); o.pot = m.state.pot || 0;
  if (m.status === 'over') { const won = m.state.winner === '0'; o.result = { won, prize: won && m.cfg.mode === 'stake' ? o.pot : 0, lost: won ? 0 : m.cfg.entry }; }
  return o;
}
function payEntry(cfg) {
  if (cfg.mode !== 'stake') return;
  if (S.bal < cfg.entry) throw err('insufficient');
  S.bal -= cfg.entry; S.spent += cfg.entry; GC.ledger('ورودی مار و پله', -cfg.entry, 'entry'); save();
}
const snakes = {
  async queueJoin(cfg) {
    if (cfg.solo) { const mm = makeMatch(Object.assign({}, cfg, { mode: 'free', entry: 0 })); saveM(mm); return { state: 'matched', match: mm.id }; }
    payEntry(cfg); store.set('demo_sq', { cfg, t0: Date.now() }); return snakes.queueStatus();
  },
  async queueStatus() {
    const q = store.get('demo_sq', null), m = loadM();
    if (!q) return m && m.status === 'playing' ? { state: 'matched', match: m.id } : { state: 'none' };
    const waited = (Date.now() - q.t0) / 1000, need = q.cfg.players || 2;
    if (waited > 3) { const mm = makeMatch(q.cfg); saveM(mm); store.set('demo_sq', null); return { state: 'matched', match: mm.id }; }
    return { state: 'waiting', waited: Math.floor(waited), cfg: Object.assign({ players: need }, q.cfg), found: 1, need, bots_in: null, can_bots: q.cfg.mode !== 'stake' };
  },
  async queueBots() { const q = store.get('demo_sq', null); if (!q) return snakes.queueStatus(); const mm = makeMatch(q.cfg); saveM(mm); store.set('demo_sq', null); return { state: 'matched', match: mm.id }; },
  async queueLeave() {
    const q = store.get('demo_sq', null); store.set('demo_sq', null);
    if (q && q.cfg.mode === 'stake') { S.bal += q.cfg.entry; S.spent -= q.cfg.entry; GC.ledger('انصراف از صف مار و پله', q.cfg.entry, 'refund'); save(); }
    return { state: 'none' };
  },
  async invite(cfg) {
    payEntry(cfg);
    const code = Math.random().toString(36).slice(2, 8).toUpperCase();
    const m = { id: 'sn' + Date.now().toString(36), status: 'lobby', cfg: Object.assign({ game: 'snakes', players: 2 }, cfg), code, t0: Date.now(), seats: [{ color: '0', name: 'شما', av: 7, me: true }] };
    saveM(m); return { match: m.id, code, link: 'https://t.me/your_gameclub_bot?start=snakes_' + code };
  },
  async join() { throw err('bad_invite'); },
  async start(id) { const m = loadM(); if (!m || m.id !== id) throw err('not_found'); const mm = makeMatch(m.cfg, m.seats.length > 1); mm.id = m.id; saveM(mm); return { ok: true }; },
  async match(id, since = 0, chat = null) {
    let m = loadM(); if (!m || (id && m.id !== id)) throw err('not_found');
    if (m.status === 'lobby') {
      if (m.seats.length === 1 && Date.now() - m.t0 > 5000) { m.seats.push({ color: '1', name: 'دوست شما', av: 11, me: false }); saveM(m); }
      if (m.seats.length === m.cfg.players) { await snakes.start(m.id); m = loadM(); }
      return out(m, since);
    }
    if (m.status === 'playing') { tick(m.state, now()); if (m.state.over) { m.status = 'over'; settle(m); } botTalk(m); saveM(m); }
    return out(m, since, chat);
  },
  async roll(id, since) {
    const m = loadM(); if (!m || m.id !== id) throw err('not_found');
    if (m.status !== 'playing') return out(m, since);
    const t = now(); tick(m.state, t);
    const e = roll(m.state, 0, t, false);
    if (!e) m.state.players['0'].misses = 0;
    if (m.state.over) { m.status = 'over'; settle(m); }
    saveM(m); if (e && e !== 'over') throw err(e);
    return out(m, since);
  },
  async leave(id) {
    const m = loadM();
    if (m && m.status === 'lobby') { saveM(null); if (m.cfg.mode === 'stake') { S.bal += m.cfg.entry; GC.ledger('لغو میز مار و پله', m.cfg.entry, 'refund'); save(); } return { left: true }; }
    if (m && m.status === 'playing') {
      const st = m.state; st.players['0'].out = true; ev(st, { t: 'leave', c: '0', why: 'left' });
      finish(st, st.n === 2 ? st.order.find(s => s !== '0') : null, st.n === 2 ? 'left' : 'empty'); m.status = 'over'; settle(m); saveM(m); return out(m, 0);
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
GC.demo = Object.assign(GC.demo || {}, { snakes });
})();
