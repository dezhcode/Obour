/* فوتبال نمایشی: بیرون از تلگرام (پیش نمایش در مرورگر) همان API سرور را با همان
   فیزیک و قواعد game_club/football.py در خود مرورگر شبیه سازی می کند. میز در
   localStorage می ماند تا بین لابی و میز از دست نرود. داخل تلگرام استفاده نمی شود. */
(() => {
const S = GC.S, save = GC.save, store = GC.store;
const SEATS = ['0', '1'];
const BOTS = ['lucky_falcon', 'brave_tiger', 'swift_panda', 'calm_otter', 'jolly_ace', 'witty_fox', 'royal_queen', 'cosmic_ninja', 'misty_raven', 'golden_comet', 'keen_hawk', 'sunny_mango'];
const FB = FBPhysics, W = FB.W, H = FB.H, GOAL_H = FB.GOAL_H, BALL_R = FB.BALL_R, BALL = FB.BALL, N = FB.N, CONTROL_RADIUS = FB.CONTROL_RADIUS;
const SETUP_S = 20, INTRO = 3.4, SHOT_PAUSE = .35, GOAL_PAUSE = 3, BOT_THINK = 1.1, TURN_S = 20, MIN_POWER = .02;
const TEAMS = ['eagles', 'lions', 'cheetahs', 'mountain', 'storm', 'sea'], FORMS = ['132', '123', '141', '1212'];
const FORM_NAME = { 132: '1-3-2', 123: '1-2-3', 141: '1-4-1', 1212: '1-2-1-2' };
// چیدمان های بازی پلاتو (کسر عرض و ارتفاع؛ ارتفاع از دروازهٔ خودی؛ اولی دروازه بان)
const FORM = {
  '1-3-2': [[.5, null], [.22, .22], [.5, .2], [.78, .22], [.4, .38], [.6, .38]], 'd:1-3-2': [[.5, null], [.26, .12], [.5, .17], [.74, .12], [.36, .24], [.64, .24]],
  '1-2-3': [[.5, null], [.4, .2], [.6, .2], [.22, .33], [.78, .33], [.5, .35]], 'd:1-2-3': [[.5, null], [.4, .11], [.6, .11], [.22, .25], [.78, .25], [.5, .26]],
  '1-4-1': [[.5, null], [.17, .25], [.39, .21], [.61, .21], [.83, .25], [.5, .35]], 'd:1-4-1': [[.5, null], [.25, .14], [.42, .12], [.58, .12], [.75, .14], [.5, .35]],
  '1-2-1-2': [[.5, null], [.35, .18], [.65, .18], [.5, .3], [.35, .38], [.65, .38]], 'd:1-2-1-2': [[.5, null], [.35, .12], [.65, .12], [.5, .21], [.35, .3], [.65, .3]],
};
const now = () => Date.now() / 1000;
const err = code => { const e = new Error(code); e.code = code; return e; };
const pick = a => a[Math.floor(Math.random() * a.length)];
const rd2 = FB.rd2, disp = () => Math.random() * 8 - 4;

function turnTime(base, chain, misses) {
  const t = chain <= 0 ? base * 1.5 : Math.max(Math.min(8, base), base - 3 * (chain - 1));
  return misses >= 2 ? Math.min(t, 10) : t;
}
function formation(seat, form, attack) {
  const name = FORM_NAME[form] || '1-3-2';
  return FORM[attack ? name : 'd:' + name].map(([fx, fy]) => { const y = fy == null ? GOAL_H : fy * H; return [fx * W, seat === 0 ? H - y : y]; });
}
function kickoffPos(st) {
  let pos = [];
  SEATS.forEach((s, i) => { const p = st.players[s]; pos = pos.concat(formation(i, i === st.kick ? p.fa : p.fd, i === st.kick)); });
  pos.push([W / 2, H / 2]);
  return pos.map(([x, y]) => [rd2(x + disp()), rd2(y + disp())]);
}
function ev(st, e) { e.seq = ++st.seq; st.events.push(e); if (st.events.length > 40) st.events = st.events.slice(-40); }
const auto = (st, i) => st.players[SEATS[i]].bot || st.players[SEATS[i]].out;
function wait(st, t, d) {
  const i = st.turn; if (auto(st, i)) d += BOT_THINK;
  st.turn_id = st.seq; st.next_at = t + d; st.deadline = t + d + turnTime(st.turn_s, st.chain, st.players[SEATS[i]].misses);
}
const current = st => st.phase === 'play' && !st.over ? SEATS[st.turn] : null;

function newState(seats, target, passes) {
  const t = now(), players = {}, taken = [];
  seats.forEach(s => {
    const team = s.bot ? pick(TEAMS.filter(x => !taken.includes(x))) : null; if (team) taken.push(team);
    players[s.color] = { name: s.name, av: s.av, pic: '', bot: !!s.bot, out: false, misses: 0, team, kit: 'home',
      fa: s.bot ? pick(FORMS) : '132', fd: s.bot ? pick(FORMS) : '132', ready: !!s.bot };
  });
  const st = { game: 'football', players, target: [2, 3, 5].includes(target) ? target : 3, passes: [0, 3, 6].includes(passes) ? passes : 0, score: [0, 0], phase: 'setup',
    turn: 0, kick: Math.floor(Math.random() * 2), pos: [], next_at: t + SETUP_S, deadline: t + SETUP_S, turn_s: TURN_S, events: [], seq: 0, over: false, winner: null,
    started: t, stats: { 0: { shots: 0, goals: 0, passes: 0 }, 1: { shots: 0, goals: 0, passes: 0 } }, chain: 0, new_ko: true, turn_id: 0 };
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
  st.phase = 'play'; st.turn = st.kick; st.chain = 0; st.new_ko = true; st.pos = kickoffPos(st);
  ev(st, { t: 'start', teams: Object.fromEntries(SEATS.map(s => [s, { team: st.players[s].team, kit: st.players[s].kit }])), pos: st.pos, kick: SEATS[st.kick] });
  wait(st, t, INTRO);
}
const roundPos = pos => pos.map(p => [rd2(p[0]), rd2(p[1])]);
function passDone(res) {
  const s = res.shooter, r = res.receiver;
  if (s == null || r == null || s === r || res.goal != null) return false;
  const [bx, by] = res.pos[BALL]; return Math.hypot(res.pos[r][0] - bx, res.pos[r][1] - by) <= CONTROL_RADIUS;
}
function freeSpot(pos, d, x, y) {
  const r = FB.radiusOf(d);
  if (x - r < 0 || x + r > W || y - r < 0 || y + r > H) return false;
  if ((x - r < FB.BOX_W || x + r > W - FB.BOX_W) && (y - r < GOAL_H || y + r > H - GOAL_H)) return false;
  for (let q = 0; q < N; q++) { if (q === d) continue; const rq = FB.radiusOf(q); if (Math.abs(pos[q][0] - x) < r + rq && Math.abs(pos[q][1] - y) < r + rq) return false; }
  return true;
}
function removeFromGoal(pos, exempt) {
  const moved = [];
  for (let d = 0; d < 12; d++) {
    if (d % 6 === 0 || d === exempt) continue;
    const y = pos[d][1];
    const [line, limit, e] = d < 6 ? [H - GOAL_H, H - GOAL_H * .8, -1] : [GOAL_H, GOAL_H * .8, 1];
    if (!(d < 6 ? y > limit : y < limit)) continue;
    const r = FB.radiusOf(d), s = r * .1, a = Math.floor((W - r * 2) / s);
    let px = pos[d][0], py = line + r * 1.1 * e; const u = px > W ? 1 : -1;
    let hc = 0, lc = 0, c = 1000;
    while (!freeSpot(pos, d, px, py) && c > 0) {
      if (hc < 6) { hc++; py += s * e; }
      else { hc = 0; lc++; if (lc >= a) lc = 0; else { c--; if ((1000 - c) % a !== 0) py -= s * e * 6; px += s * u; if (px < r) px = W - r - 1; else if (px > W - r) px = r + 1; } }
    }
    pos[d] = [rd2(px), rd2(py)]; moved.push(d);
  }
  return moved;
}
function shot(st, i, k, dx, dy, power, t, autoP) {
  if (st.over) return 'over'; if (st.phase !== 'play') return 'not_play_phase'; if (st.turn !== i) return 'not_your_turn';
  if (!autoP && t < st.next_at - .3) return 'not_ready';
  if (!(k >= 0 && k < 6) || !isFinite(dx + dy + power)) return 'bad_shot';
  const imp = FB.impulse(dx, dy, power); if (!imp) return 'bad_shot';
  const token = i * 6 + k, passOk = st.passes === 0 || st.chain < st.passes;
  const res = FB.runShot(st.pos, token, imp[0], imp[1], i, passOk);
  st.events.forEach(e => { if (e.t === 'shot' || e.t === 'pass') delete e.frames; });
  const pos = roundPos(res.pos); st.stats[i].shots++;
  const kickShot = st.new_ko, g = res.goal;
  ev(st, { t: 'shot', c: SEATS[i], k, ids: res.ids, frames: res.frames, dur: res.dur, pos, hits: res.hits.slice(0, 24).map(h => [h[0], h[1], Math.round(Math.min(1, h[2] / 2000) * 100) / 100]), goal: g == null ? null : SEATS[g], auto: !!autoP, kick: kickShot });
  let base = res.dur + SHOT_PAUSE;
  if (g != null) return goal(st, i, g, pos, kickShot, base, t);
  st.new_ko = false;
  const passed = passDone(res);
  if (!(pos[BALL][0] > 0 && pos[BALL][0] < W && pos[BALL][1] > 0 && pos[BALL][1] < H)) pos[BALL] = [W / 2, H / 2];
  const moved = removeFromGoal(pos, passed ? res.receiver : null);
  if (moved.length) { const mv = moved.slice().sort((a, b) => a - b); ev(st, { t: 'settle', ids: mv, pos: mv.map(q => pos[q]) }); base += .4; }
  st.pos = pos;
  if (passed) {
    st.chain++; st.stats[i].passes++;
    const ctl = FB.runControl(pos, res.receiver, i);
    if (ctl.moved) st.pos = roundPos(ctl.pos);
    ev(st, { t: 'pass', c: SEATS[i], d: res.receiver, n: st.chain, left: st.passes ? st.passes - st.chain : null, ids: ctl.ids, frames: ctl.frames, dur: ctl.dur, pos: st.pos });
    wait(st, t, base + ctl.dur + .5); return null;
  }
  st.chain = 0; st.turn = 1 - i; ev(st, { t: 'lose', c: SEATS[i], to: SEATS[st.turn] });
  wait(st, t, base); return null;
}
function goal(st, i, g, pos, kickShot, base, t) {
  const foul = kickShot;
  if (!foul) { st.score[g]++; if (g === i) st.stats[g].goals++; }
  ev(st, { t: 'goal', c: SEATS[g], by: SEATS[i], own: g !== i, score: st.score.slice(), foul });
  if (!foul && st.score[g] >= st.target) { st.pos = pos; st.over = true; st.winner = g; st.phase = 'over'; ev(st, { t: 'win', c: SEATS[g], score: st.score.slice() }); return null; }
  st.chain = 0; st.kick = g === i ? 1 - i : i; st.turn = st.kick; st.new_ko = true; st.pos = kickoffPos(st);
  ev(st, { t: 'reset', pos: st.pos, kick: SEATS[st.kick], foul });
  wait(st, t, base + GOAL_PAUSE); return null;
}
// ---------- ربات: چند شوت امتحانی با همان فیزیک، بهترین نتیجه ----------
const goalOf = i => i === 0 ? [W / 2, 0] : [W / 2, H];
const rateOf = k => k % 6 === 0 ? 4.54 : 6.8;
function rate(st, i, res) {
  if (res.goal != null) return st.new_ko ? -400 : (res.goal === i ? 100000 : -100000);
  const [bx, by] = res.pos[BALL], [gx, gy] = goalOf(i), [ox, oy] = goalOf(1 - i);
  let v = -Math.hypot(bx - gx, by - gy) * .7 + Math.min(Math.hypot(bx - ox, by - oy), 900) * .5;
  if (passDone(res)) v += 420 + (Math.hypot(bx - gx, by - gy) < 700 ? 300 : 0);
  const near = lo => Math.min(...res.pos.slice(lo, lo + 6).map(p => Math.hypot(p[0] - bx, p[1] - by)));
  return v + (Math.min(near((1 - i) * 6), 500) - Math.min(near(i * 6), 500)) * .25;
}
function botShot(st, i) {
  const pos = st.pos, [bx, by] = pos[BALL], [gx, gy] = goalOf(i); let ux = gx - bx, uy = gy - by; const ul = Math.hypot(ux, uy) || 1; ux /= ul; uy /= ul;
  const cands = [];
  for (let k = 0; k < 6; k++) {
    const d = i * 6 + k, [tx, ty] = pos[d], rk = FB.radiusOf(d);
    let ax = bx - ux * (rk + BALL_R - 3) - tx, ay = by - uy * (rk + BALL_R - 3) - ty, dist = Math.hypot(ax, ay) || 1;
    const align = (ax / dist) * ux + (ay / dist) * uy;
    cands.push([align * 600 - dist * .2, k, ax / dist, ay / dist, Math.min(1, (dist + 90) / rateOf(k) / 250)]);
    const cx = bx - tx, cy = by - ty, cd = Math.hypot(cx, cy) || 1;
    cands.push([align * 200 - cd * .2, k, cx / cd, cy / cd, Math.min(1, (cd + 150) / rateOf(k) / 250)]);
    for (let j = 0; j < 6; j++) {
      if (j === k) continue;
      const [mx, my] = pos[i * 6 + j], px = mx - bx, py = my - by, pl = Math.hypot(px, py) || 1;
      if (pl < 160) continue;
      ax = bx - px / pl * (rk + BALL_R - 3) - tx; ay = by - py / pl * (rk + BALL_R - 3) - ty; dist = Math.hypot(ax, ay) || 1;
      const line = (ax / dist) * (px / pl) + (ay / dist) * (py / pl);
      if (line < .3) continue;
      cands.push([line * 350 + 120 - dist * .2, k, ax / dist, ay / dist, Math.min(1, (dist + pl * .5) / rateOf(k) / 250)]);
    }
  }
  cands.sort((a, b) => b[0] - a[0]);
  const passOk = st.passes === 0 || st.chain < st.passes;
  let best = null, bv = -1e18;
  for (const [, k, ax, ay, p] of cands.slice(0, 7)) {
    const a = (Math.random() - .5) * .05, dx = ax * Math.cos(a) - ay * Math.sin(a), dy = ax * Math.sin(a) + ay * Math.cos(a);
    const pw = Math.min(1, Math.max(.12, p * (.95 + Math.random() * .1))), imp = FB.impulse(dx, dy, pw);
    const v = rate(st, i, FB.runShot(pos, i * 6 + k, imp[0], imp[1], i, passOk)) + Math.random() * 25;
    if (v > bv) { bv = v; best = [k, dx, dy, pw]; }
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
    st.turn = 1 - i; st.chain = 0; ev(st, { t: 'lose', c: s, to: SEATS[st.turn], miss: true }); wait(st, t, SHOT_PAUSE);
  }
}
function view(st, me, since) {
  const t = now(), cur = current(st), au = cur != null && auto(st, +cur);
  return { order: SEATS, players: Object.fromEntries(SEATS.map(s => { const p = st.players[s]; return [s, Object.assign({ name: p.name, av: p.av, pic: '', bot: p.bot, out: p.out, me: s === me, team: p.team, kit: p.kit, ready: p.ready }, s === me ? { fa: p.fa, fd: p.fd } : {})]; })),
    me, phase: st.phase, turn: cur, kick: SEATS[st.kick], pos: st.pos, score: st.score, target: st.target, passes: st.passes, chain: st.chain, kickoff: st.new_ko,
    setup_ms: st.phase === 'setup' ? Math.max(0, Math.round((st.next_at - t) * 1000)) : 0,
    ready_ms: cur != null ? Math.max(0, Math.round((st.next_at - t) * 1000)) : 0,
    deadline_ms: cur == null || au ? 0 : Math.max(0, Math.round((st.deadline - t) * 1000)), turn_ms: Math.round(turnTime(st.turn_s, st.chain, st.players[SEATS[st.turn]].misses) * 1000),
    events: st.events.filter(e => e.seq > since), seq: st.seq, over: st.over, winner: st.winner == null ? null : SEATS[st.winner], stats: st.stats[me], started: st.started };
}

/* ---------- API نمایشی (هم شکل liveFootball در gc.js) ---------- */
const loadM = () => store.get('demo_football', null), saveM = m => store.set('demo_football', m);
function makeMatch(cfg, guest) {
  const names = [...BOTS].sort(() => Math.random() - .5);
  const seats = [{ color: '0', name: 'شما', av: 7 }, guest ? { color: '1', name: 'دوست شما', av: 11, bot: true } : { color: '1', name: names.pop(), av: 1 + Math.floor(Math.random() * 22), bot: true }];
  const st = newState(seats, cfg.target || 3, cfg.passes || 0); st.stake = cfg.mode !== 'free';
  return { id: 'fb' + Date.now().toString(36), status: 'playing', cfg: Object.assign({ game: 'football', players: 2 }, cfg), state: st, settled: false };
}
function settle(m) {
  if (m.settled || m.status !== 'over') return; m.settled = true; m.chat = [];
  const won = m.state.winner === 0; S.games++;
  if (won) S.wins++;
  if (m.cfg.mode === 'ranked') m.rank = GC.demo.rank('football', won);
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
  o.game = view(m.state, '0', since);
  if (m.status === 'over') { const won = m.state.winner === 0; o.result = Object.assign({ won, coins: 0, cups: 0 }, m.rank); }
  return o;
}
const football = {
  async queueJoin(cfg) {
    if (cfg.solo) { const mm = makeMatch(Object.assign({}, cfg, { mode: 'free', entry: 0 })); saveM(mm); return { state: 'matched', match: mm.id }; }
    store.set('demo_fq', { cfg, t0: Date.now() }); return football.queueStatus();
  },
  async queueStatus() {
    const q = store.get('demo_fq', null), m = loadM();
    if (!q) return m && m.status === 'playing' ? { state: 'matched', match: m.id } : { state: 'none' };
    const waited = (Date.now() - q.t0) / 1000;
    if (waited > 3) { const mm = makeMatch(q.cfg); saveM(mm); store.set('demo_fq', null); return { state: 'matched', match: mm.id }; }
    return { state: 'waiting', waited: Math.floor(waited), cfg: Object.assign({ players: 2 }, q.cfg), found: 1, need: 2, bots_in: null, can_bots: q.cfg.mode === 'free' };
  },
  async queueBots() { const q = store.get('demo_fq', null); if (!q) return football.queueStatus(); const mm = makeMatch(q.cfg); saveM(mm); store.set('demo_fq', null); return { state: 'matched', match: mm.id }; },
  async queueLeave() {
    const q = store.get('demo_fq', null); store.set('demo_fq', null);
    return { state: 'none' };
  },
  async invite(cfg) {
    
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
    if (m && m.status === 'lobby') { saveM(null); return { left: true }; }
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
