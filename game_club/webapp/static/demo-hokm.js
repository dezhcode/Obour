/* حکم نمایشی: بیرون از تلگرام (پیش نمایش در مرورگر) همان API سرور را با همان
   قواعد game_club/hokm.py در خود مرورگر شبیه سازی می کند. میز در localStorage
   می ماند تا بین لابی و میز از دست نرود. داخل تلگرام این فایل استفاده نمی شود. */
(() => {
const S = GC.S, save = GC.save, store = GC.store;
const SEATS = ['0', '1', '2', '3'];
const BOTS = ['سارا', 'امیر', 'نگار', 'رضا', 'مهسا', 'علی', 'پریا', 'کیان', 'هستی', 'سینا', 'آرش', 'یاسمن'];
const GRACE = 2.5, HAKEM = 2.2, DEAL = 1.8, TRUMP_THINK = 2.4, DEAL2 = 4.0, THINK = .9, COLLECT = 1.5, HANDOVER = 3.6, TURN = 20;
const suit = c => Math.floor(c / 13), rank = c => c % 13, team = i => i % 2, nxt = i => (i + 1) % 4;
const now = () => Date.now() / 1000;
const err = code => { const e = new Error(code); e.code = code; return e; };

function ev(st, e) { e.seq = ++st.seq; st.events.push(e); if (st.events.length > 60) st.events = st.events.slice(-60); }
function sortCards(cs, tr) { return cs.slice().sort((a, b) => ((tr != null && suit(a) === tr ? 0 : 1) - (tr != null && suit(b) === tr ? 0 : 1)) || suit(a) - suit(b) || rank(b) - rank(a)); }
function wait(st, t, d) { st.turn_id = st.seq; st.next_at = t + d; st.deadline = t + d + TURN; }
const drawTime = n => { const step = n > 14 ? .17 : n > 8 ? .23 : .30; return .7 + n * step + 2.8; };
function drawHakem() {
  const deck = [...Array(52).keys()];
  for (let i = 51; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [deck[i], deck[j]] = [deck[j], deck[i]]; }
  let i = Math.floor(Math.random() * 4); const draw = [];
  for (const c of deck) { draw.push([SEATS[i], c]); if (rank(c) === 12) return [i, draw]; i = nxt(i); }
  return [i, draw];
}
function startHand(st, t, lead = HAKEM, draw = null) {
  const deck = [...Array(52).keys()];
  for (let i = 51; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [deck[i], deck[j]] = [deck[j], deck[i]]; }
  SEATS.forEach((s, k) => { const p = deck.slice(k * 13, k * 13 + 13); st.hands[s] = sortCards(p.slice(0, 5)); st.rest[s] = p.slice(5); });
  Object.assign(st, { trump: null, phase: 'trump', tricks: [0, 0], trick: [], led: null, played: [], last_trick: null, turn: st.hakem });
  st.stats[SEATS[st.hakem]].hakem++;
  ev(st, { t: 'hakem', c: SEATS[st.hakem], hand: st.hand_no, draw, prev: st.prev_hakem != null ? SEATS[st.prev_hakem] : null });
  ev(st, { t: 'deal', hakem: String(st.hakem), hand: st.hand_no }); wait(st, t, lead + DEAL + (auto(st, st.hakem) ? TRUMP_THINK : 0));
}
function newState(seats, target) {
  const t = now(), players = {};
  seats.forEach(s => { players[s.color] = { name: s.name, av: s.av, pic: '', bot: !!s.bot, out: false, misses: 0 }; });
  const [hk, draw] = drawHakem();
  const st = { game: 'hokm', players, target, score: [0, 0], hand_no: 0, hakem: hk, prev_hakem: null, hands: {}, rest: {},
    events: [], seq: 0, over: false, winner: null, started: t, stats: Object.fromEntries(SEATS.map(s => [s, { tricks: 0, hakem: 0 }])) };
  startHand(st, t, GRACE + drawTime(draw.length), draw); return st;
}
const auto = (st, i) => st.players[SEATS[i]].bot || st.players[SEATS[i]].out;
function legal(st, i) {
  const h = st.hands[SEATS[i]]; if (st.phase !== 'play' || st.turn !== i) return [];
  if (st.led != null) { const f = h.filter(c => suit(c) === st.led); if (f.length) return f; }
  return h.slice();
}
function winnerOf(trick, tr) {
  let [bi, b] = trick[0];
  for (const [i, c] of trick.slice(1)) { if (suit(c) === suit(b)) { if (rank(c) > rank(b)) [bi, b] = [i, c]; } else if (suit(c) === tr) [bi, b] = [i, c]; }
  return bi;
}
function trump(st, i, s, t, autoP) {
  if (st.over) return 'over'; if (st.phase !== 'trump') return 'not_trump_phase'; if (st.hakem !== i) return 'not_your_turn'; if (!(s >= 0 && s < 4)) return 'bad_suit';
  st.trump = s; SEATS.forEach(k => { st.hands[k] = sortCards(st.hands[k].concat(st.rest[k]), s); st.rest[k] = []; });
  st.phase = 'play'; st.turn = st.hakem; ev(st, { t: 'trump', c: SEATS[i], suit: s, auto: !!autoP }); wait(st, t, DEAL2); return null;
}
function play(st, i, c, t, autoP) {
  if (st.over) return 'over'; if (st.phase !== 'play') return 'not_play_phase'; if (st.turn !== i) return 'not_your_turn';
  if (!legal(st, i).includes(c)) return 'illegal_card';
  const h = st.hands[SEATS[i]]; h.splice(h.indexOf(c), 1);
  if (!st.trick.length) st.led = suit(c);
  st.trick.push([i, c]); st.played.push(c); ev(st, { t: 'play', c: SEATS[i], card: c, auto: !!autoP });
  if (st.trick.length < 4) { st.turn = nxt(i); wait(st, t, auto(st, st.turn) ? THINK : .35); return null; }
  const w = winnerOf(st.trick, st.trump); st.tricks[team(w)]++; st.stats[SEATS[w]].tricks++;
  st.phase = 'collect'; st.turn = w; ev(st, { t: 'trick', c: SEATS[w], tricks: st.tricks.slice() }); st.next_at = st.deadline = t + COLLECT; return null;
}
function afterCollect(st, t) {
  st.last_trick = { cards: st.trick, winner: SEATS[st.turn] }; st.trick = []; st.led = null;
  const w = [0, 1].find(x => st.tricks[x] >= 7);
  if (w == null) { st.phase = 'play'; wait(st, t, auto(st, st.turn) ? THINK : .2); return; }
  const lose = 1 - w, ht = team(st.hakem), kot = st.tricks[lose] === 0, pts = kot ? (lose === ht ? 3 : 2) : 1;
  st.score[w] += pts; ev(st, { t: 'hand', team: w, pts, kot, tricks: st.tricks.slice(), score: st.score.slice(), hakem: String(st.hakem) });
  if (st.score[w] >= st.target) { st.over = true; st.winner = w; st.phase = 'over'; ev(st, { t: 'win', team: w }); return; }
  st.prev_hakem = st.hakem; if (w !== ht) st.hakem = nxt(st.hakem);
  st.hand_no++; st.phase = 'handover'; st.next_at = st.deadline = t + HANDOVER;
}
function botTrump(st, i) {
  const h = st.hands[SEATS[i]];
  const sc = s => { const cs = h.filter(c => suit(c) === s).map(rank); return cs.length * 10 + cs.filter(r => r >= 9).reduce((a, r) => a + (r - 7) * 3, 0) + Math.random(); };
  return [0, 1, 2, 3].sort((a, b) => sc(b) - sc(a))[0];
}
function boss(st, c, mine) { const gone = new Set(st.played.concat(mine)); for (let x = c + 1; x < (suit(c) + 1) * 13; x++) if (!gone.has(x)) return false; return true; }
function botCard(st, i) {
  const h = st.hands[SEATS[i]], ok = legal(st, i), tr = st.trump;
  const low = cs => cs.reduce((a, b) => rank(b) < rank(a) ? b : a), high = cs => cs.reduce((a, b) => rank(b) > rank(a) ? b : a);
  if (!st.trick.length) {
    const plain = ok.filter(c => suit(c) !== tr), bs = plain.filter(c => boss(st, c, h));
    if (bs.length) return high(bs);
    if (plain.length) { const by = {}; plain.forEach(c => (by[suit(c)] = by[suit(c)] || []).push(c)); return low(Object.values(by).sort((a, b) => b.length - a.length)[0]); }
    return low(ok);
  }
  const w = winnerOf(st.trick, tr), wc = st.trick.find(([j]) => j === w)[1], partner = team(w) === team(i), last = st.trick.length === 3;
  const beats = c => winnerOf(st.trick.concat([[i, c]]), tr) === i;
  if (suit(ok[0]) === st.led) {
    const win = ok.filter(beats), bw = win.filter(c => boss(st, c, h));
    if (partner) return last || boss(st, wc, h) || rank(wc) >= 10 || !bw.length ? low(ok) : high(bw);
    if (win.length) return last || !bw.length ? low(win) : high(bw);
    return low(ok);
  }
  const plain = ok.filter(c => suit(c) !== tr);
  if (partner) return plain.length ? low(plain) : low(ok);
  const win = ok.filter(c => suit(c) === tr && beats(c));
  if (win.length) return low(win);
  return plain.length ? low(plain) : low(ok);
}
function tick(st, t) {
  for (let n = 0; n < 12 && !st.over; n++) {
    if (st.phase === 'collect') { if (t < st.next_at) break; afterCollect(st, t); continue; }
    if (st.phase === 'handover') { if (t < st.next_at) break; startHand(st, t); continue; }
    const i = st.phase === 'trump' ? st.hakem : st.turn, s = SEATS[i], p = st.players[s];
    if (auto(st, i)) { if (t < st.next_at) break; }
    else { if (t < st.deadline) break; p.misses++; ev(st, { t: 'timeout', c: s, n: p.misses }); }
    if (st.phase === 'trump') trump(st, i, botTrump(st, i), t, !p.bot); else play(st, i, botCard(st, i), t, !p.bot);
  }
}
function view(st, me, since) {
  const t = now(), ph = st.phase, act = ph === 'trump' ? st.hakem : st.turn, waiting = (ph === 'trump' || ph === 'play') && !st.over;
  return { order: SEATS, players: Object.fromEntries(SEATS.map(s => [s, Object.assign({}, st.players[s], { me: s === me, team: +s % 2, count: st.hands[s].length })])),
    me, hand: st.hands[me].slice(), phase: ph, turn: waiting ? SEATS[act] : null, hakem: SEATS[st.hakem], trump: st.trump, trick: st.trick, led: st.led,
    last_trick: st.last_trick, tricks: st.tricks, score: st.score, target: st.target, hand_no: st.hand_no,
    legal: waiting && ph === 'play' ? legal(st, +me) : [], deadline_ms: !waiting || auto(st, act) ? 0 : Math.max(0, Math.round((st.deadline - t) * 1000)),
    turn_ms: TURN * 1000, events: st.events.filter(e => e.seq > since), seq: st.seq, over: st.over, winner: st.winner, stats: st.stats[me], started: st.started };
}

/* ---------- API نمایشی (هم شکل liveHokm در gc.js) ---------- */
const loadM = () => store.get('demo_hokm', null), saveM = m => store.set('demo_hokm', m);
function makeMatch(cfg, guest) {
  const names = [...BOTS].sort(() => Math.random() - .5);
  const seats = SEATS.map(s => s === '0' ? { color: s, name: 'شما', av: 7 } : guest && s === '2' ? { color: s, name: 'دوست شما', av: 11, bot: true }
    : { color: s, name: names.pop(), av: 1 + Math.floor(Math.random() * 22), bot: true });
  const st = newState(seats, cfg.target); st.pot = cfg.mode === 'stake' ? cfg.entry * 4 : 0; st.stake = cfg.mode === 'stake';
  return { id: 'hk' + Date.now().toString(36), status: 'playing', cfg: Object.assign({ game: 'hokm', players: 4 }, cfg), state: st, settled: false };
}
function settle(m) {
  if (m.settled || m.status !== 'over') return; m.settled = true; m.chat = [];
  const won = m.state.winner === 0; S.games++;
  if (won) { S.wins++; if (m.cfg.mode === 'stake') { const p = m.state.pot / 2; S.bal += p; S.won += p; GC.ledger('جایزهٔ حکم', p, 'prize'); } }
  save();
}
const QUIPS = ['سلام!', 'خوش‌بازی!', 'آفرین', 'حکم خوبی بود', 'زود باش', 'یار، حواست باشه', 'یک دست دیگه؟'];
function botTalk(m) {
  if (m.status !== 'playing') return;
  m.chat = m.chat || []; m.chatAt = m.chatAt || Date.now();
  if (Date.now() - m.chatAt < 12000 || Math.random() > .15) return;
  const bots = SEATS.filter(c => m.state.players[c].bot); if (!bots.length) return;
  const c = bots[Math.floor(Math.random() * bots.length)], p = m.state.players[c];
  m.chatAt = Date.now();
  m.chat.push({ id: (m.chat.length ? m.chat[m.chat.length - 1].id : 0) + 1, color: c, name: p.name, av: p.av, pic: '', bot: true, text: QUIPS[Math.floor(Math.random() * QUIPS.length)], at: Math.round(Date.now() / 1000), me: false });
}
function out(m, since, chat) {
  const o = { id: m.id, status: m.status, cfg: m.cfg, me: '0' };
  if (chat != null) o.chat = (m.chat || []).filter(x => x.id > chat).slice(-40);
  if (m.status === 'lobby') { o.lobby = { seats: m.seats, code: m.code, host: true, link: 'https://t.me/your_gameclub_bot?start=hokm_' + m.code }; return o; }
  o.game = view(m.state, '0', since); o.pot = m.state.pot || 0;
  if (m.status === 'over') { const won = m.state.winner === 0; o.result = { won, prize: won ? o.pot / 2 : 0, lost: won ? 0 : m.cfg.entry }; }
  return o;
}
function payEntry(cfg) {
  if (cfg.mode !== 'stake') return;
  if (S.bal < cfg.entry) throw err('insufficient');
  S.bal -= cfg.entry; S.spent += cfg.entry; GC.ledger('ورودی حکم', -cfg.entry, 'entry'); save();
}
const hokm = {
  async queueJoin(cfg) {
    if (cfg.solo) { const mm = makeMatch(Object.assign({}, cfg, { mode: 'free', entry: 0 })); saveM(mm); return { state: 'matched', match: mm.id }; }
    payEntry(cfg); store.set('demo_hq', { cfg, t0: Date.now() }); return hokm.queueStatus();
  },
  async queueStatus() {
    const q = store.get('demo_hq', null), m = loadM();
    if (!q) return m && m.status === 'playing' ? { state: 'matched', match: m.id } : { state: 'none' };
    const waited = (Date.now() - q.t0) / 1000;
    if (waited > 4) { const mm = makeMatch(q.cfg); saveM(mm); store.set('demo_hq', null); return { state: 'matched', match: mm.id }; }
    return { state: 'waiting', waited: Math.floor(waited), cfg: Object.assign({ players: 4 }, q.cfg), found: 1 + Math.min(3, Math.floor(waited / 1.2)), need: 4, bots_in: null, can_bots: q.cfg.mode !== 'stake' };
  },
  async queueBots() {
    const q = store.get('demo_hq', null); if (!q) return hokm.queueStatus();
    const mm = makeMatch(q.cfg); saveM(mm); store.set('demo_hq', null); return { state: 'matched', match: mm.id };
  },
  async queueLeave() {
    const q = store.get('demo_hq', null); store.set('demo_hq', null);
    if (q && q.cfg.mode === 'stake') { S.bal += q.cfg.entry; S.spent -= q.cfg.entry; GC.ledger('انصراف از صف حکم', q.cfg.entry, 'refund'); save(); }
    return { state: 'none' };
  },
  async invite(cfg) {
    payEntry(cfg);
    const code = Math.random().toString(36).slice(2, 8).toUpperCase();
    const m = { id: 'hk' + Date.now().toString(36), status: 'lobby', cfg: Object.assign({ game: 'hokm', players: 4 }, cfg), code, t0: Date.now(), seats: [{ color: '0', name: 'شما', av: 7, me: true }] };
    saveM(m); return { match: m.id, code, link: 'https://t.me/your_gameclub_bot?start=hokm_' + code };
  },
  async join() { throw err('bad_invite'); },
  async start(id) { const m = loadM(); if (!m || m.id !== id) throw err('not_found'); const mm = makeMatch(m.cfg, m.seats.length > 1); mm.id = m.id; saveM(mm); return { ok: true }; },
  async match(id, since = 0, chat = null) {
    let m = loadM(); if (!m || (id && m.id !== id)) throw err('not_found');
    if (m.status === 'lobby') {
      if (m.seats.length === 1 && Date.now() - m.t0 > 5000) { m.seats.push({ color: '2', name: 'دوست شما', av: 11, me: false }); saveM(m); }
      return out(m, since);
    }
    if (m.status === 'playing') { tick(m.state, now()); if (m.state.over) { m.status = 'over'; settle(m); } botTalk(m); saveM(m); }
    return out(m, since, chat);
  },
  async act(id, kind, k, since) {
    const m = loadM(); if (!m || m.id !== id) throw err('not_found');
    if (m.status !== 'playing') return out(m, since);
    const t = now(); tick(m.state, t);
    const e = kind === 'trump' ? trump(m.state, 0, k, t) : kind === 'play' ? play(m.state, 0, k, t)
      : (m.state.players['0'].out = true, ev(m.state, { t: 'leave', c: '0', why: 'left' }), m.state.over = true, m.state.winner = null, m.state.phase = 'over', null);
    if (!e) m.state.players['0'].misses = 0;
    if (m.state.over) { m.status = 'over'; settle(m); }
    saveM(m); if (e && e !== 'over') throw err(e);
    return out(m, since);
  },
  async trump(id, k, since) { return hokm.act(id, 'trump', k, since); },
  async play(id, k, since) { return hokm.act(id, 'play', k, since); },
  async leave(id) {
    const m = loadM();
    if (m && m.status === 'lobby') { saveM(null); if (m.cfg.mode === 'stake') { S.bal += m.cfg.entry; GC.ledger('لغو میز حکم', m.cfg.entry, 'refund'); save(); } return { left: true }; }
    if (m && m.status === 'playing') return hokm.act(id, 'leave', null, 0);
    return { left: true };
  },
  async chat(id, text) {
    const m = loadM(); if (!m || m.id !== id || m.status !== 'playing') throw err('not_found');
    text = String(text || '').replace(/\s+/g, ' ').trim().slice(0, 140); if (!text) throw err('empty');
    m.chat = m.chat || []; const lastMine = m.chat.filter(x => x.me).pop();
    if (lastMine && Date.now() / 1000 - lastMine.at < 1.5) throw err('chat_slow');
    const id2 = (m.chat.length ? m.chat[m.chat.length - 1].id : 0) + 1;
    m.chat.push({ id: id2, color: '0', name: 'شما', av: 7, pic: '', text, at: Math.round(Date.now() / 1000), me: true });
    m.chatAt = Date.now() - 9000; saveM(m); return { ok: true, id: id2 };
  },
};
GC.demo = Object.assign(GC.demo || {}, { hokm });
})();
