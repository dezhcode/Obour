/* بیلیارد نمایشی: بیرون از تلگرام (پیش نمایش در مرورگر) همان API سرور را با همان
   فیزیک و قواعد game_club/billiard.py (static/billiard-engine.js) در خود مرورگر شبیه سازی
   می کند. میز در localStorage می ماند. داخل تلگرام استفاده نمی شود. */
(() => {
const S = GC.S, save = GC.save, store = GC.store, E = BLEngine;
const BOTS = ['lucky_falcon', 'brave_tiger', 'swift_panda', 'calm_otter', 'jolly_ace', 'witty_fox', 'royal_queen', 'cosmic_ninja', 'misty_raven', 'golden_comet', 'keen_hawk', 'sunny_mango'];
const SHOT_PAUSE = .6, INTRO = 2.6, BOT_THINK = 2.4, TURN_S = 30, AIM_MIN_S = .25;
const now = () => Date.now() / 1000;
const err = code => { const e = new Error(code); e.code = code; return e; };
const pick = a => a[Math.floor(Math.random() * a.length)];
const team = i => i % 2;
const seatsOf = n => n === 4 ? ['0', '1', '2', '3'] : ['0', '1'];

function ev(st, e) { e.seq = ++st.seq; st.events.push(e); if (st.events.length > 40) st.events = st.events.slice(-40); }
const auto = (st, i) => st.players[st.order[i]].bot || st.players[st.order[i]].out;
function wait(st, t, d) { if (auto(st, st.turn)) d += BOT_THINK; st.turn_id = st.seq; st.next_at = t + d; st.deadline = t + d + st.turn_s; }
const current = st => st.phase === 'play' && !st.over ? st.order[st.turn] : null;
const nxt = (st, i) => (i + 1) % st.n;
const solidsOf = (st, i) => st.solids < 0 ? null : st.solids === team(i);
const groupLeft = (st, sol) => { const b = sol ? 1 : 9; let n = 0; for (let k = b; k < b + 7; k++) if (st.balls[k]) n++; return n; };
function targets(st, i) {
  const b = st.balls, sol = solidsOf(st, i);
  if (sol == null) return [...Array(15).keys()].map(k => k + 1).filter(k => k !== 8 && b[k]);
  const base = sol ? 1 : 9, out = []; for (let k = base; k < base + 7; k++) if (b[k]) out.push(k);
  return out.length ? out : (b[8] ? [8] : []);
}
function score(st) { if (st.solids < 0) return [0, 0]; return [0, 1].map(tm => 7 - groupLeft(st, st.solids === tm)); }

function newState(seats, n) {
  const order = seatsOf(n), players = {};
  for (const s of seats) players[s.color] = { name: s.name, av: s.av || 1, bot: !!s.bot, out: false, misses: 0 };
  const t = now();
  const st = { game: 'billiard', order, n: order.length, players, balls: E.rack(), solids: -1, turn: 0, bih: true, breaking: true, msg: 'break', phase: 'play',
    next_at: t + INTRO, deadline: t + INTRO + TURN_S, turn_s: TURN_S, events: [], seq: 0, turn_id: 0, winner: null, over: false, started: t,
    stats: Object.fromEntries(order.map(s => [s, { shots: 0, pots: 0, fouls: 0 }])) };
  ev(st, { t: 'start', balls: st.balls, turn: order[0] });
  wait(st, t, INTRO);
  return st;
}
function shot(st, i, angle, power, sx, sy, cx, cy, t, isAuto) {
  if (st.over) return 'over';
  if (st.turn !== i) return 'not_your_turn';
  if (!isAuto && t < st.next_at - .3) return 'not_ready';
  if (cx != null) { if (!st.bih || !E.validPlace(st.balls, st.breaking, cx, cy)) return 'bad_place'; st.balls[0] = [cx, cy]; }
  power = Math.min(1, Math.max(E.MIN_POWER, power));
  const sl = Math.hypot(sx, sy); if (sl > 1) { sx /= sl; sy /= sl; }
  const s = st.order[i], breaking = st.breaking;
  if (breaking && power > E.BREAK_MIN) { power *= E.BREAK_BONUS + Math.random() * E.BREAK_RAND; angle += Math.random() * E.BREAK_JIT * 2 - E.BREAK_JIT; }
  const pos0 = st.balls.map(p => p ? p.slice() : null), need = targets(st, i);
  const res = E.simulate(pos0, angle, power, [sx, sy], breaking);
  for (const e of st.events) if (e.t === 'shot') delete e.frames;
  st.stats[s].shots++;
  ev(st, { t: 'shot', c: s, a: +angle.toFixed(4), p: +power.toFixed(3), cue: pos0[0], ids: res.ids, frames: res.frames, dur: res.dur, pots: res.pots, hits: res.hits, auto: !!isAuto });
  st.balls = res.pos; delete st.live;
  resolve(st, i, res, need, t);
  return null;
}
function resolve(st, i, res, need, t) {
  const s = st.order[i], b = st.balls, potted = res.pots.map(p => p[0]), ballsIn = potted.filter(n => n !== 0);
  const cueIn = potted.includes(0), eightIn = potted.includes(8), first = res.first, rails = res.rails, tm = team(i);
  st.stats[s].pots += ballsIn.filter(n => n !== 8).length;
  const pause = res.dur + SHOT_PAUSE;
  let foul = null;
  if (st.breaking) {
    if (eightIn || (rails.length < 4 && !ballsIn.length)) {
      st.balls = E.rack(); st.bih = true; st.msg = eightIn ? 'break_8' : 'break_illegal';
      ev(st, { t: 'rack', c: s, balls: st.balls, why: st.msg }); wait(st, t, pause + 1); return;
    }
    st.breaking = false;
    if (cueIn) foul = 'scratch';
    else { const kept = assign(st, i, ballsIn); st.msg = st.solids < 0 ? 'open' : (solidsOf(st, i) ? 'solids' : 'stripes'); respot(st); after(st, i, kept, null, pause, t); return; }
  } else {
    const sol = solidsOf(st, i);
    if (sol != null && need.length === 1 && need[0] === 8) { if (first !== 8) foul = 'hit_8_first'; }
    else if (first === -1) foul = 'no_hit';
    else if (first === 8 || (sol != null && (first < 8) !== sol)) foul = 'wrong_first';
    if (cueIn) foul = 'scratch';
    if (foul == null && !rails.length && !ballsIn.length) foul = 'no_rail';
    if (foul == null && b.slice(1).some(p => p && !(p[0] >= 0 && p[0] <= E.W && p[1] >= 0 && p[1] <= E.H))) foul = 'jump';
  }
  if (eightIn) {
    const sol = solidsOf(st, i), cleared = sol != null && groupLeft(st, sol) === 0;
    if (cleared && foul == null) { st.msg = 'won'; finish(st, tm, 'pot8'); } else { st.msg = 'lost8'; finish(st, 1 - tm, cleared ? 'foul8' : 'early8'); }
    return;
  }
  respot(st);
  if (foul != null) { st.stats[s].fouls++; st.msg = foul; after(st, i, false, foul, pause, t); return; }
  const kept = assign(st, i, ballsIn), sol = solidsOf(st, i), good = ballsIn.filter(n => sol == null || (n < 8) === sol);
  st.msg = !ballsIn.length ? '' : !good.length ? 'wrong_pot' : (sol != null && targets(st, i).join() === '8') ? 'on_8' : 'potted';
  after(st, i, kept || good.length > 0, null, pause, t);
}
function assign(st, i, ballsIn) {
  if (st.solids >= 0) return false;
  const first = ballsIn.find(n => n !== 8); if (first == null) return false;
  st.solids = first < 8 ? team(i) : 1 - team(i); ev(st, { t: 'groups', solids: st.solids, c: st.order[i] }); return true;
}
function respot(st) {
  for (let n = 1; n < 16; n++) { const p = st.balls[n]; if (p && !(p[0] >= 0 && p[0] <= E.W && p[1] >= 0 && p[1] <= E.H)) { st.balls[n] = null; st.balls[n] = E.spot(st.balls, n); ev(st, { t: 'spot', k: n, at: st.balls[n] }); } }
}
function after(st, i, keep, foul, pause, t) {
  const b = st.balls;
  if (!b[0] || !(b[0][0] >= 0 && b[0][0] <= E.W && b[0][1] >= 0 && b[0][1] <= E.H)) { b[0] = null; b[0] = E.cueSpot(b, false); }
  const n = keep && foul == null ? i : nxt(st, i);
  st.turn = n; st.bih = foul != null;
  ev(st, { t: 'turn', c: st.order[n], bih: st.bih, foul, msg: st.msg, balls: b, solids: st.solids });
  wait(st, t, pause);
}
function finish(st, w, why) { st.over = true; st.winner = w; st.phase = 'over'; ev(st, { t: w == null ? 'end' : 'win', team: w, why, balls: st.balls }); }

/* ---------- ربات ---------- */
function segClear(pos, ax, ay, bx, by, skip) {
  const ex = bx - ax, ey = by - ay, l2 = ex * ex + ey * ey || 1;
  for (let n = 0; n < 16; n++) {
    const p = pos[n]; if (!p || skip.includes(n)) continue;
    const t = ((p[0] - ax) * ex + (p[1] - ay) * ey) / l2; if (t <= 0 || t >= 1) continue;
    if ((p[0] - ax - ex * t) ** 2 + (p[1] - ay - ey * t) ** 2 < E.D * E.D) return false;
  }
  return true;
}
function plans(st, i, cue) {
  const pos = st.balls, out = [];
  for (const k of targets(st, i)) {
    const [bx, by] = pos[k];
    for (const p of E.POCKETS) {
      let ux = p[3] - bx, uy = p[4] - by; const dl = Math.hypot(ux, uy) || 1; ux /= dl; uy /= dl;
      const gx = bx - ux * E.D, gy = by - uy * E.D, cxv = gx - cue[0], cyv = gy - cue[1], cl = Math.hypot(cxv, cyv);
      if (cl < 1) continue;
      const cut = (cxv * ux + cyv * uy) / cl;
      if (cut < .25 || !segClear(pos, cue[0], cue[1], gx, gy, [0, k]) || !segClear(pos, bx, by, p[3], p[4], [0, k])) continue;
      out.push([cut * 3 - dl / 900 - cl / 1400, Math.atan2(cyv, cxv), Math.min(.85, Math.max(.14, .08 + (cl + dl * 1.3) / (2600 * Math.max(.45, cut))))]);
    }
  }
  return out.sort((a, b) => b[0] - a[0]);
}
function botShot(st, i) {
  let place = null;
  if (st.bih) {
    if (st.breaking) { const x = E.W / 2 - 5 + (Math.random() - .5) * 160; place = E.validPlace(st.balls, true, x, E.BREAK_MIN_Y + 10) ? [x, E.BREAK_MIN_Y + 10] : E.CUE_START.slice(); }
    else place = E.cueSpot(st.balls, false);
  }
  const cue = place || st.balls[0];
  if (st.breaking) {
    let apex = null; for (let n = 1; n < 16; n++) if (st.balls[n] && (!apex || st.balls[n][1] < apex[1])) apex = st.balls[n];
    return [Math.atan2(apex[1] - cue[1], apex[0] - cue[0]) + (Math.random() - .5) * .02, .92 + Math.random() * .08, 0, 0, place];
  }
  const old = st.balls[0]; if (place) st.balls[0] = place;
  const ps = plans(st, i, cue); st.balls[0] = old;
  if (ps.length) { const p = ps[Math.min(ps.length - 1, Math.floor(Math.random() ** 3 * 2))]; return [p[1] + (Math.random() - .5) * .022, Math.min(1, p[2] * (.95 + Math.random() * .15)), 0, (Math.random() - .5) * .4, place]; }
  const tg = targets(st, i); const k = tg.sort((a, b) => Math.hypot(st.balls[a][0] - cue[0], st.balls[a][1] - cue[1]) - Math.hypot(st.balls[b][0] - cue[0], st.balls[b][1] - cue[1]))[0];
  return [Math.atan2(st.balls[k][1] - cue[1], st.balls[k][0] - cue[0]), .5, 0, 0, place];
}
function tick(st, t) {
  for (let g = 0; g < 3 && !st.over; g++) {
    const i = st.turn, s = st.order[i], p = st.players[s];
    if (auto(st, i)) {
      // ربات هم مثل بازیکن نشانه می گیرد (نشانه گیری زنده): اول نزدیک هدف، کمی پیش از ضربه دقیق با قدرت
      let plan = st.plan;
      if (!plan || plan.id !== st.turn_id) {
        const v = botShot(st, i);
        plan = st.plan = { id: st.turn_id, v, k: 0 };
        st.live = { id: st.turn_id, c: s, a: +(v[0] + (Math.random() - .5) * .45).toFixed(4), p: 0, cue: v[4] ? v[4].map(q => +q.toFixed(1)) : null, t };
      }
      if (t < st.next_at) {
        if (plan.k === 0 && t >= st.next_at - 1) { plan.k = 1; st.live = Object.assign({}, st.live, { a: +plan.v[0].toFixed(4), p: +plan.v[1].toFixed(3), t }); }
        break;
      }
      const [a, pw, sx, sy, place] = plan.v; delete st.plan;
      shot(st, i, a, pw, sx, sy, place ? place[0] : null, place ? place[1] : null, t, true); continue;
    }
    if (t < st.deadline) break;
    p.misses++; ev(st, { t: 'timeout', c: s, n: p.misses }); st.msg = 'timeout';
    if (st.breaking) { st.turn = nxt(st, i); st.bih = true; ev(st, { t: 'turn', c: st.order[st.turn], bih: true, foul: 'timeout', msg: 'timeout', balls: st.balls, solids: st.solids }); wait(st, t, .4); }
    else after(st, i, false, 'timeout', .4, t);
  }
}
// نشانه گیری زنده (مثل aim در billiard.py)
function aim(st, i, a, p, cx, cy, t) {
  if (st.over || st.phase !== 'play') return 'over';
  if (st.turn !== i) return 'not_your_turn';
  if (!isFinite(a) || !isFinite(p)) return 'bad_shot';
  const cue = st.bih && cx != null && cy != null && E.validPlace(st.balls, st.breaking, cx, cy) ? [+cx.toFixed(1), +cy.toFixed(1)] : null;
  const old = st.live; if (old && old.id === st.turn_id && t - old.t < AIM_MIN_S) return 'same';
  st.live = { id: st.turn_id, c: st.order[i], a: +Math.atan2(Math.sin(a), Math.cos(a)).toFixed(4), p: +Math.min(1, Math.max(0, p)).toFixed(3), cue, t };
  return null;
}
function view(st, me, since) {
  const t = now(), cur = current(st), mi = st.order.indexOf(me), au = cur != null && auto(st, st.order.indexOf(cur));
  const lv = st.live && cur != null && st.live.id === st.turn_id && st.live.c === cur ? { c: st.live.c, a: st.live.a, p: st.live.p, cue: st.live.cue } : null;
  return { order: st.order, n: st.n, me, phase: st.phase, turn: cur, balls: st.balls, solids: st.solids, bih: st.bih, breaking: st.breaking, msg: st.msg,
    players: Object.fromEntries(st.order.map((s, k) => { const p = st.players[s]; return [s, { name: p.name, av: p.av, pic: '', bot: p.bot, out: p.out, me: s === me, team: team(k), group: st.solids < 0 ? null : (st.solids === team(k) ? 'solids' : 'stripes') }]; })),
    targets: cur != null ? targets(st, st.turn) : [], mine: mi >= 0 && !st.over ? targets(st, mi) : [], score: score(st),
    ready_ms: cur != null ? Math.max(0, Math.round((st.next_at - t) * 1000)) : 0,
    deadline_ms: cur == null || au ? 0 : Math.max(0, Math.round((st.deadline - t) * 1000)), turn_ms: st.turn_s * 1000,
    live: lv, events: st.events.filter(e => e.seq > since), seq: st.seq, over: st.over, winner: st.winner, stats: st.stats[me], started: st.started };
}

/* ---------- API نمایشی (هم شکل liveBilliard در gc.js) ---------- */
const loadM = () => store.get('demo_billiard', null), saveM = m => store.set('demo_billiard', m);
function makeMatch(cfg, guest) {
  const n = cfg.players === 4 ? 4 : 2, names = [...BOTS].sort(() => Math.random() - .5), order = seatsOf(n);
  const seats = order.map((c, k) => k === 0 ? { color: c, name: 'شما', av: 7 } : (guest && k === (n === 4 ? 2 : 1) ? { color: c, name: 'دوست شما', av: 11, bot: true } : { color: c, name: names.pop(), av: 1 + Math.floor(Math.random() * 22), bot: true }));
  const st = newState(seats, n); st.pot = cfg.mode === 'stake' ? cfg.entry * n : 0; st.stake = cfg.mode === 'stake';
  return { id: 'bl' + Date.now().toString(36), status: 'playing', cfg: Object.assign({ game: 'billiard', players: n }, cfg), state: st, settled: false };
}
function settle(m) {
  if (m.settled || m.status !== 'over') return; m.settled = true; m.chat = [];
  const won = m.state.winner === 0; S.games++;
  if (won) { S.wins++; if (m.cfg.mode === 'stake') { const share = Math.floor(m.state.pot / (m.cfg.players === 4 ? 2 : 1)); S.bal += share; S.won += share; GC.ledger('جایزهٔ بیلیارد', share, 'prize'); } }
  save();
}
const QUIPS = ['سلام!', 'خوش‌بازی!', 'عجب ضربه‌ای!', 'شانس آوردی', 'زود باش', 'یک دست دیگه؟'];
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
  if (m.status === 'lobby') { o.lobby = { seats: m.seats, code: m.code, host: true, link: 'https://t.me/your_gameclub_bot?start=billiard_' + m.code }; return o; }
  o.game = view(m.state, '0', since); o.pot = m.state.pot || 0;
  if (m.status === 'over') { const won = m.state.winner === 0; o.result = { won, prize: won && m.cfg.mode === 'stake' ? Math.floor(o.pot / (m.cfg.players === 4 ? 2 : 1)) : 0, lost: won ? 0 : m.cfg.entry }; }
  return o;
}
function payEntry(cfg) {
  if (cfg.mode !== 'stake') return;
  if (S.bal < cfg.entry) throw err('insufficient');
  S.bal -= cfg.entry; S.spent += cfg.entry; GC.ledger('ورودی بیلیارد', -cfg.entry, 'entry'); save();
}
const billiard = {
  async queueJoin(cfg) {
    if (cfg.solo) { const mm = makeMatch(Object.assign({}, cfg, { mode: 'free', entry: 0 })); saveM(mm); return { state: 'matched', match: mm.id }; }
    payEntry(cfg); store.set('demo_bq', { cfg, t0: Date.now() }); return billiard.queueStatus();
  },
  async queueStatus() {
    const q = store.get('demo_bq', null), m = loadM();
    if (!q) return m && m.status === 'playing' ? { state: 'matched', match: m.id } : { state: 'none' };
    const waited = (Date.now() - q.t0) / 1000, need = q.cfg.players === 4 ? 4 : 2;
    if (waited > 3) { const mm = makeMatch(q.cfg); saveM(mm); store.set('demo_bq', null); return { state: 'matched', match: mm.id }; }
    return { state: 'waiting', waited: Math.floor(waited), cfg: Object.assign({ players: need }, q.cfg), found: 1, need, bots_in: null, can_bots: q.cfg.mode !== 'stake' };
  },
  async queueBots() { const q = store.get('demo_bq', null); if (!q) return billiard.queueStatus(); const mm = makeMatch(q.cfg); saveM(mm); store.set('demo_bq', null); return { state: 'matched', match: mm.id }; },
  async queueLeave() {
    const q = store.get('demo_bq', null); store.set('demo_bq', null);
    if (q && q.cfg.mode === 'stake') { S.bal += q.cfg.entry; S.spent -= q.cfg.entry; GC.ledger('انصراف از صف بیلیارد', q.cfg.entry, 'refund'); save(); }
    return { state: 'none' };
  },
  async invite(cfg) {
    payEntry(cfg);
    const code = Math.random().toString(36).slice(2, 8).toUpperCase(), n = cfg.players === 4 ? 4 : 2;
    const m = { id: 'bl' + Date.now().toString(36), status: 'lobby', cfg: Object.assign({ game: 'billiard', players: n }, cfg), code, t0: Date.now(), seats: [{ color: '0', name: 'شما', av: 7, me: true }] };
    saveM(m); return { match: m.id, code, link: 'https://t.me/your_gameclub_bot?start=billiard_' + code };
  },
  async join() { throw err('bad_invite'); },
  async start(id) { const m = loadM(); if (!m || m.id !== id) throw err('not_found'); const mm = makeMatch(m.cfg, m.seats.length > 1); mm.id = m.id; saveM(mm); return { ok: true }; },
  async match(id, since = 0, chat = null) {
    let m = loadM(); if (!m || (id && m.id !== id)) throw err('not_found');
    if (m.status === 'lobby') {
      if (m.seats.length === 1 && Date.now() - m.t0 > 5000) { m.seats.push({ color: m.cfg.players === 4 ? '2' : '1', name: 'دوست شما', av: 11, me: false }); saveM(m); }
      if (m.seats.length === 2 && m.cfg.players === 2) { await billiard.start(m.id); m = loadM(); }
      return out(m, since);
    }
    if (m.status === 'playing') { tick(m.state, now()); if (m.state.over) { m.status = 'over'; settle(m); } botTalk(m); saveM(m); }
    return out(m, since, chat);
  },
  async shot(id, a, p, sx, sy, cx, cy, since) {
    const m = loadM(); if (!m || m.id !== id) throw err('not_found');
    if (m.status !== 'playing') return out(m, since);
    const t = now(); tick(m.state, t);
    const e = shot(m.state, 0, a, p, sx || 0, sy || 0, cx, cy, t, false);
    if (!e) m.state.players['0'].misses = 0;
    if (m.state.over) { m.status = 'over'; settle(m); }
    saveM(m); if (e && e !== 'over') throw err(e);
    return out(m, since);
  },
  async aim(id, a, p, cx, cy) {
    const m = loadM(); if (!m || m.id !== id) throw err('not_found');
    if (m.status !== 'playing') return { ok: true };
    const e = aim(m.state, 0, +a, +(p || 0), cx == null ? null : +cx, cy == null ? null : +cy, now());
    if (!e) saveM(m); else if (e !== 'same' && e !== 'over') throw err(e);
    return { ok: true };
  },
  async leave(id) {
    const m = loadM();
    if (m && m.status === 'lobby') { saveM(null); if (m.cfg.mode === 'stake') { S.bal += m.cfg.entry; GC.ledger('لغو میز بیلیارد', m.cfg.entry, 'refund'); save(); } return { left: true }; }
    if (m && m.status === 'playing') {
      const st = m.state; st.players['0'].out = true; ev(st, { t: 'leave', c: '0', why: 'left' });
      finish(st, 1, 'left'); m.status = 'over'; settle(m); saveM(m); return out(m, 0);
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
GC.demo = Object.assign(GC.demo || {}, { billiard });
})();
