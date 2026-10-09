/* فوتبال نمایشی: بیرون از تلگرام (پیش نمایش در مرورگر) همان API سرور را با همان
   فیزیک و قواعد game_club/football.py در خود مرورگر شبیه سازی می کند. میز در
   localStorage می ماند تا بین لابی و میز از دست نرود. داخل تلگرام استفاده نمی شود. */
(() => {
const S = GC.S, save = GC.save, store = GC.store;
const SEATS = ['0', '1'];
const BOTS = ['سارا', 'امیر', 'نگار', 'رضا', 'مهسا', 'علی', 'پریا', 'کیان', 'هستی', 'سینا', 'آرش', 'یاسمن'];
const W = 600, H = 1040, MID = H / 2, GOAL_W = 220, GOAL_D = 60, GX0 = (W - GOAL_W) / 2, GX1 = (W + GOAL_W) / 2;
const DISC_R = 36, BALL_R = 18, DISC_M = 1, BALL_M = .3, BALL = 12, N = 13, VMAX = 2200, MIN_POWER = .06;
const DT = 1 / 120, FRAME_EVERY = 4, MAX_SIM = 9, AFTER_GOAL = .5, DRAG = [.9, .55], FRIC = [330, 85];
const E_PAIR = .82, E_DISC_WALL = .5, E_BALL_WALL = .82, STOP = 4;
const SETUP_S = 20, INTRO = 3.4, SHOT_PAUSE = .35, GOAL_PAUSE = 3.6, BOT_THINK = 1.1, TURN_S = 15;
const TEAMS = ['eagles', 'lions', 'cheetahs', 'mountain', 'storm', 'sea'], FORMS = ['132', '123', '141', '1212'];
const ATK = { 132: [[300, 42], [110, 230], [300, 210], [490, 230], [220, 400], [380, 400]], 123: [[300, 42], [200, 220], [400, 220], [110, 410], [300, 430], [490, 410]],
  141: [[300, 42], [90, 280], [230, 250], [370, 250], [510, 280], [300, 430]], 1212: [[300, 42], [200, 200], [400, 200], [300, 320], [210, 430], [390, 430]] };
const DEF = { 132: [[300, 42], [120, 190], [300, 160], [480, 190], [210, 300], [390, 300]], 123: [[300, 42], [210, 160], [390, 160], [110, 300], [300, 320], [490, 300]],
  141: [[300, 42], [90, 180], [230, 160], [370, 160], [510, 180], [300, 320]], 1212: [[300, 42], [210, 150], [390, 150], [300, 240], [200, 340], [400, 340]] };
const SEGS = [[[0, 0], [GX0, 0]], [[GX1, 0], [W, 0]], [[GX0, 0], [GX0, -GOAL_D]], [[GX0, -GOAL_D], [GX1, -GOAL_D]], [[GX1, -GOAL_D], [GX1, 0]],
  [[0, H], [GX0, H]], [[GX1, H], [W, H]], [[GX0, H], [GX0, H + GOAL_D]], [[GX0, H + GOAL_D], [GX1, H + GOAL_D]], [[GX1, H + GOAL_D], [GX1, H]],
  [[0, 0], [0, H]], [[W, 0], [W, H]]];
const now = () => Date.now() / 1000;
const err = code => { const e = new Error(code); e.code = code; return e; };
const pick = a => a[Math.floor(Math.random() * a.length)];
const r1 = v => Math.round(v * 10) / 10;

// فیزیک مشترک با مینی اپ: static/football-physics.js (کپی دقیق سرور)
const simulate = (pos, vel) => FBPhysics.simulate(pos, vel);

function formation(seat, form, attack) {
  const pts = (attack ? ATK : DEF)[form] || ATK[132];
  return pts.map(([px, d]) => seat === 0 ? [px, H - d] : [W - px, d]);
}
function kickoffPos(st) {
  let pos = [];
  SEATS.forEach((s, i) => { const p = st.players[s]; pos = pos.concat(formation(i, i === st.kick ? p.fa : p.fd, i === st.kick)); });
  return pos.concat([[W / 2, MID]]);
}
function ev(st, e) { e.seq = ++st.seq; st.events.push(e); if (st.events.length > 40) st.events = st.events.slice(-40); }
const auto = (st, i) => st.players[SEATS[i]].bot || st.players[SEATS[i]].out;
function wait(st, t, d) { if (auto(st, st.turn)) d += BOT_THINK; st.turn_id = st.seq; st.next_at = t + d; st.deadline = t + d + st.turn_s; }
const current = st => st.phase === 'play' && !st.over ? SEATS[st.turn] : null;

function newState(seats, target) {
  const t = now(), players = {}, taken = [];
  seats.forEach(s => {
    const team = s.bot ? pick(TEAMS.filter(x => !taken.includes(x))) : null; if (team) taken.push(team);
    players[s.color] = { name: s.name, av: s.av, pic: '', bot: !!s.bot, out: false, misses: 0, team, kit: 'home',
      fa: s.bot ? pick(FORMS) : '132', fd: s.bot ? pick(FORMS) : '132', ready: !!s.bot };
  });
  const st = { game: 'football', players, target, score: [0, 0], phase: 'setup', turn: 0, kick: Math.floor(Math.random() * 2), pos: [],
    next_at: t + SETUP_S, deadline: t + SETUP_S, turn_s: TURN_S, events: [], seq: 0, over: false, winner: null, started: t,
    stats: { 0: { shots: 0, goals: 0 }, 1: { shots: 0, goals: 0 } } };
  st.pos = kickoffPos(st); ev(st, { t: 'setup' });
  return st;
}
function setup(st, s, team, fa, fd, t) {
  if (st.over) return 'over'; if (st.phase !== 'setup') return 'not_setup';
  if (!TEAMS.includes(team) || !FORMS.includes(fa) || !FORMS.includes(fd)) return 'bad_setup';
  Object.assign(st.players[s], { team, fa, fd, ready: true }); ev(st, { t: 'ready', c: s });
  if (SEATS.every(k => st.players[k].ready)) start(st, t);
  return null;
}
function start(st, t) {
  const taken = SEATS.map(s => st.players[s].team).filter(Boolean);
  SEATS.forEach(s => { const p = st.players[s]; if (!p.team) { p.team = TEAMS.find(x => !taken.includes(x)); taken.push(p.team); } p.ready = true; });
  const a = st.players[0], b = st.players[1];
  a.kit = 'home'; b.kit = a.team === b.team ? 'away' : 'home';
  st.phase = 'play'; st.turn = st.kick; st.pos = kickoffPos(st);
  ev(st, { t: 'start', teams: Object.fromEntries(SEATS.map(s => [s, { team: st.players[s].team, kit: st.players[s].kit }])), pos: st.pos, kick: SEATS[st.kick] });
  wait(st, t, INTRO);
}
function shot(st, i, k, dx, dy, power, t, autoP) {
  if (st.over) return 'over'; if (st.phase !== 'play') return 'not_play_phase'; if (st.turn !== i) return 'not_your_turn';
  if (!autoP && t < st.next_at - .3) return 'not_ready';
  if (!(k >= 0 && k < 6)) return 'bad_shot';
  const ln = Math.sqrt(dx * dx + dy * dy); if (!(ln > 1e-6)) return 'bad_shot';
  const res = simulate(st.pos, { [i * 6 + k]: FBPhysics.shotVel(dx, dy, power) });
  st.events.forEach(e => { if (e.t === 'shot') delete e.frames; });
  st.pos = res.pos; st.stats[i].shots++;
  const g = res.goal;
  ev(st, { t: 'shot', c: SEATS[i], k, ids: res.ids, frames: res.frames, dur: res.dur, pos: res.pos, hits: res.hits, goal: g == null ? null : SEATS[g], auto: !!autoP });
  if (g == null) { st.turn = 1 - i; wait(st, t, res.dur + SHOT_PAUSE); return null; }
  st.score[g]++; if (g === i) st.stats[g].goals++;
  ev(st, { t: 'goal', c: SEATS[g], by: SEATS[i], own: g !== i, score: st.score.slice() });
  if (st.score[g] >= st.target) { st.over = true; st.winner = g; st.phase = 'over'; ev(st, { t: 'win', c: SEATS[g], score: st.score.slice() }); return null; }
  st.kick = 1 - g; st.turn = st.kick; st.pos = kickoffPos(st);
  ev(st, { t: 'reset', pos: st.pos, kick: SEATS[st.kick] });
  wait(st, t, res.dur + GOAL_PAUSE); return null;
}
function goalOf(i) { return i === 0 ? [W / 2, -GOAL_D / 2] : [W / 2, H + GOAL_D / 2]; }
function rate(i, res) {
  if (res.goal != null) return res.goal === i ? 1000 : -2000;
  const [bx, by] = res.pos[BALL], [gx, gy] = goalOf(i), [ox, oy] = goalOf(1 - i);
  return -Math.hypot(bx - gx, by - gy) * .6 + Math.min(Math.hypot(bx - ox, by - oy), 500) * .4;
}
function botShot(st, i) {
  const pos = st.pos, [bx, by] = pos[BALL], [gx, gy] = goalOf(i), gl = Math.hypot(gx - bx, gy - by) || 1, ux = (gx - bx) / gl, uy = (gy - by) / gl;
  const cands = [];
  for (let k = 0; k < 6; k++) {
    const [dx0, dy0] = pos[i * 6 + k], cx = bx - ux * (DISC_R + BALL_R) * .9, cy = by - uy * (DISC_R + BALL_R) * .9;
    let ax = cx - dx0, ay = cy - dy0, dist = Math.hypot(ax, ay) || 1; ax /= dist; ay /= dist;
    const align = ax * ux + ay * uy;
    if (align < .15) { ax = bx - dx0; ay = by - dy0; dist = Math.hypot(ax, ay) || 1; ax /= dist; ay /= dist; }
    cands.push([align * 2 - dist / 900, k, ax, ay, Math.min(1, Math.max(.5, .42 + dist / 1250))]);
  }
  cands.sort((a, b) => b[0] - a[0]);
  let best = null, bv = -1e9;
  for (const [, k, ax, ay, p] of cands.slice(0, 4)) {
    const a = (Math.random() - .5) * .09, dx = ax * Math.cos(a) - ay * Math.sin(a), dy = ax * Math.sin(a) + ay * Math.cos(a);
    const v = rate(i, simulate(pos, { [i * 6 + k]: [dx * VMAX * p, dy * VMAX * p] })) + Math.random() * 30;
    if (v > bv) { bv = v; best = [k, dx, dy, p]; }
  }
  return best;
}
function tick(st, t) {
  for (let n = 0; n < 4 && !st.over; n++) {
    if (st.phase === 'setup') { if (t < st.next_at) break; start(st, t); continue; }
    const i = st.turn, s = SEATS[i], p = st.players[s];
    if (auto(st, i)) { if (t < st.next_at) break; const [k, dx, dy, pw] = botShot(st, i); shot(st, i, k, dx, dy, pw, t, true); continue; }
    if (t < st.deadline) break;
    p.misses++; ev(st, { t: 'timeout', c: s, n: p.misses });
    st.turn = 1 - i; wait(st, t, SHOT_PAUSE);
  }
}
function view(st, me, since) {
  const t = now(), cur = current(st), au = cur != null && auto(st, +cur);
  return { order: SEATS, players: Object.fromEntries(SEATS.map(s => { const p = st.players[s]; return [s, Object.assign({ name: p.name, av: p.av, pic: '', bot: p.bot, out: p.out, me: s === me, team: p.team, kit: p.kit, ready: p.ready }, s === me ? { fa: p.fa, fd: p.fd } : {})]; })),
    me, phase: st.phase, turn: cur, kick: SEATS[st.kick], pos: st.pos, score: st.score, target: st.target,
    setup_ms: st.phase === 'setup' ? Math.max(0, Math.round((st.next_at - t) * 1000)) : 0,
    ready_ms: cur != null ? Math.max(0, Math.round((st.next_at - t) * 1000)) : 0,
    deadline_ms: cur == null || au ? 0 : Math.max(0, Math.round((st.deadline - t) * 1000)), turn_ms: st.turn_s * 1000,
    events: st.events.filter(e => e.seq > since), seq: st.seq, over: st.over, winner: st.winner == null ? null : SEATS[st.winner], stats: st.stats[me], started: st.started };
}

/* ---------- API نمایشی (هم شکل liveFootball در gc.js) ---------- */
const loadM = () => store.get('demo_football', null), saveM = m => store.set('demo_football', m);
function makeMatch(cfg, guest) {
  const names = [...BOTS].sort(() => Math.random() - .5);
  const seats = [{ color: '0', name: 'شما', av: 7 }, guest ? { color: '1', name: 'دوست شما', av: 11, bot: true } : { color: '1', name: 'ربات ' + names.pop(), av: 1 + Math.floor(Math.random() * 22), bot: true }];
  const st = newState(seats, cfg.target || 3); st.pot = cfg.mode === 'stake' ? cfg.entry * 2 : 0; st.stake = cfg.mode === 'stake';
  return { id: 'fb' + Date.now().toString(36), status: 'playing', cfg: Object.assign({ game: 'football', players: 2 }, cfg), state: st, settled: false };
}
function settle(m) {
  if (m.settled || m.status !== 'over') return; m.settled = true; m.chat = [];
  const won = m.state.winner === 0; S.games++;
  if (won) { S.wins++; if (m.cfg.mode === 'stake') { S.bal += m.state.pot; S.won += m.state.pot; GC.ledger('جایزهٔ فوتبال', m.state.pot, 'prize'); } }
  save();
}
const QUIPS = ['سلام!', 'خوش‌بازی!', 'چه شوتی!', 'شانس آوردی', 'زود باش', 'یک بازی دیگه؟'];
function botTalk(m) {
  if (m.status !== 'playing') return;
  m.chat = m.chat || []; m.chatAt = m.chatAt || Date.now();
  if (Date.now() - m.chatAt < 14000 || Math.random() > .15) return;
  const p = m.state.players['1']; if (!p.bot) return;
  m.chatAt = Date.now();
  m.chat.push({ id: (m.chat.length ? m.chat[m.chat.length - 1].id : 0) + 1, color: '1', name: p.name, av: p.av, pic: '', bot: true, text: pick(QUIPS), at: Math.round(Date.now() / 1000), me: false });
}
function out(m, since, chat) {
  const o = { id: m.id, status: m.status, cfg: m.cfg, me: '0' };
  if (chat != null) o.chat = (m.chat || []).filter(x => x.id > chat).slice(-40);
  if (m.status === 'lobby') { o.lobby = { seats: m.seats, code: m.code, host: true, link: 'https://t.me/your_gameclub_bot?start=football_' + m.code }; return o; }
  o.game = view(m.state, '0', since); o.pot = m.state.pot || 0;
  if (m.status === 'over') { const won = m.state.winner === 0; o.result = { won, prize: won ? o.pot : 0, lost: won ? 0 : m.cfg.entry }; }
  return o;
}
function payEntry(cfg) {
  if (cfg.mode !== 'stake') return;
  if (S.bal < cfg.entry) throw err('insufficient');
  S.bal -= cfg.entry; S.spent += cfg.entry; GC.ledger('ورودی فوتبال', -cfg.entry, 'entry'); save();
}
const football = {
  async queueJoin(cfg) {
    if (cfg.solo) { const mm = makeMatch(Object.assign({}, cfg, { mode: 'free', entry: 0 })); saveM(mm); return { state: 'matched', match: mm.id }; }
    payEntry(cfg); store.set('demo_fq', { cfg, t0: Date.now() }); return football.queueStatus();
  },
  async queueStatus() {
    const q = store.get('demo_fq', null), m = loadM();
    if (!q) return m && m.status === 'playing' ? { state: 'matched', match: m.id } : { state: 'none' };
    const waited = (Date.now() - q.t0) / 1000;
    if (waited > 3) { const mm = makeMatch(q.cfg); saveM(mm); store.set('demo_fq', null); return { state: 'matched', match: mm.id }; }
    return { state: 'waiting', waited: Math.floor(waited), cfg: Object.assign({ players: 2 }, q.cfg), found: 1, need: 2, bots_in: null, can_bots: q.cfg.mode !== 'stake' };
  },
  async queueBots() { const q = store.get('demo_fq', null); if (!q) return football.queueStatus(); const mm = makeMatch(q.cfg); saveM(mm); store.set('demo_fq', null); return { state: 'matched', match: mm.id }; },
  async queueLeave() {
    const q = store.get('demo_fq', null); store.set('demo_fq', null);
    if (q && q.cfg.mode === 'stake') { S.bal += q.cfg.entry; S.spent -= q.cfg.entry; GC.ledger('انصراف از صف فوتبال', q.cfg.entry, 'refund'); save(); }
    return { state: 'none' };
  },
  async invite(cfg) {
    payEntry(cfg);
    const code = Math.random().toString(36).slice(2, 8).toUpperCase();
    const m = { id: 'fb' + Date.now().toString(36), status: 'lobby', cfg: Object.assign({ game: 'football', players: 2 }, cfg), code, t0: Date.now(), seats: [{ color: '0', name: 'شما', av: 7, me: true }] };
    saveM(m); return { match: m.id, code, link: 'https://t.me/your_gameclub_bot?start=football_' + code };
  },
  async join() { throw err('bad_invite'); },
  async start(id) { const m = loadM(); if (!m || m.id !== id) throw err('not_found'); const mm = makeMatch(m.cfg, m.seats.length > 1); mm.id = m.id; saveM(mm); return { ok: true }; },
  async match(id, since = 0, chat = null) {
    let m = loadM(); if (!m || (id && m.id !== id)) throw err('not_found');
    if (m.status === 'lobby') {
      if (m.seats.length === 1 && Date.now() - m.t0 > 5000) { m.seats.push({ color: '1', name: 'دوست شما', av: 11, me: false }); saveM(m); }
      if (m.seats.length === 2) { await football.start(m.id); m = loadM(); }
      return out(m, since);
    }
    if (m.status === 'playing') { tick(m.state, now()); if (m.state.over) { m.status = 'over'; settle(m); } botTalk(m); saveM(m); }
    return out(m, since, chat);
  },
  async act(id, fn, since) {
    const m = loadM(); if (!m || m.id !== id) throw err('not_found');
    if (m.status !== 'playing') return out(m, since);
    const t = now(); tick(m.state, t);
    const e = fn(m.state, t);
    if (!e) m.state.players['0'].misses = 0;
    if (m.state.over) { m.status = 'over'; settle(m); }
    saveM(m); if (e && e !== 'over') throw err(e);
    return out(m, since);
  },
  async setup(id, team, fa, fd, since) { return football.act(id, (st, t) => setup(st, '0', team, fa, fd, t), since); },
  async shot(id, i, dx, dy, p, since) { return football.act(id, (st, t) => shot(st, 0, i, dx, dy, p, t), since); },
  async leave(id) {
    const m = loadM();
    if (m && m.status === 'lobby') { saveM(null); if (m.cfg.mode === 'stake') { S.bal += m.cfg.entry; GC.ledger('لغو میز فوتبال', m.cfg.entry, 'refund'); save(); } return { left: true }; }
    if (m && m.status === 'playing') return football.act(id, st => { st.players['0'].out = true; ev(st, { t: 'leave', c: '0', why: 'left' }); st.over = true; st.winner = 1; st.phase = 'over'; ev(st, { t: 'win', c: '1', score: st.score.slice() }); return null; }, 0);
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
GC.demo = Object.assign(GC.demo || {}, { football });
})();
