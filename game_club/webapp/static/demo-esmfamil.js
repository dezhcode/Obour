/* نمایش اسم‌فامیل بیرون از تلگرام: یک بازی سه دوره با سه بازیکن ساختگی و داور نمونه، با همان شکل جواب سرور
   (game_club/esmfamil.py view). فقط برای پیش نمایش است؛ در تلگرام همه چیز از سرور می آید. */
window.EsmDemo = (() => {
  const COLS = [['name', 'اسم'], ['family', 'فامیل'], ['city', 'شهر'], ['country', 'کشور'], ['food', 'غذا'], ['animal', 'حیوان'], ['fruit', 'میوه'], ['thing', 'اشیا'], ['color', 'رنگ']];
  const LETTERS = ['ب', 'س', 'م'], LINES = ['حرف «ب»! بزن بریم', 'نوبت «س» شد؛ سریع باش', 'آخرین دور: «م»!'];
  const BANK = {
    ب: { 1: ['بابک', 'برومند', 'بابل', 'بلغارستان', 'باقالی‌پلو', 'بلبل', 'بلوبری', 'بخاری', 'بنفش'], 2: ['بهار', 'بابایی', 'بوشهر', 'بلژیک', 'برنج', 'ببر', 'به', 'بالش', 'بژ'], 3: ['بیژن', 'بهرامی', 'بلوچستان', 'برزیل', 'بریانی', 'بز', '', 'بشقاب', 'بنفش'] },
    س: { 1: ['سارا', 'سلیمانی', 'سمنان', 'سوئد', 'سوپ', 'سنجاب', 'سیب', 'ساعت', 'سبز'], 2: ['سینا', 'سعیدی', 'ساری', 'سنگال', 'سالاد الویه', 'سگ', 'سیب', 'سطل', 'سرمه‌ای'], 3: ['سهیل', '', 'سنندج', 'سوریه', 'سبزی‌پلو', 'سار', 'سیر', 'سشوار', 'سفید'] },
    م: { 1: ['مریم', 'محمدی', 'مشهد', 'مصر', 'میرزاقاسمی', 'مار', 'موز', 'میز', 'مشکی'], 2: ['مهسا', 'مرادی', 'مازندران', 'مالزی', 'ماکارونی', 'میمون', 'موز', 'مداد', 'مسی'], 3: ['مهدی', 'منصوری', 'مراغه', 'مکزیک', 'ماهی', 'مرغ', 'ماست', 'مبل', 'مشکی'] },
  };
  const NO = { برنج: 'مادهٔ خام است، نه غذا', بلوچستان: 'استان است، نه شهر', سیر: 'سبزی است، نه میوه', مازندران: 'استان است، نه شهر', ماهی: 'حیوان است؛ غذا باید پخته باشد', ماست: 'لبنیات است، نه میوه' };
  const P = { 0: { name: 'tu_demo', av: 7 }, 1: { name: 'negar_gm', av: 5 }, 2: { name: 'sara_m', av: 9 }, 3: { name: 'kian_r', av: 13 } };
  const ORDER = ['0', '1', '2', '3'], now = () => Date.now() / 1000;
  const norm = s => String(s || '').replace(/[‌\s]/g, '').replace(/آ/g, 'ا');
  let st = null;

  function reset() {
    st = { phase: 'letter', round: 0, deadline: now() + 3, letterAt: now() + .4, sheets: {}, done: [], stopper: null, ready: [], appeals: {},
      results: [], totals: { 0: 0, 1: 0, 2: 0, 3: 0 }, seq: 1, events: [], over: false, winners: [], botDone: {} };
  }
  const ev = e => { st.seq++; st.events.push(Object.assign({ seq: st.seq }, e)); st.events = st.events.slice(-20); };
  function startWrite() {
    st.phase = 'write'; st.deadline = now() + 180; st.sheets = { 0: {} }; st.done = []; st.stopper = null;
    st.botDone = { 1: now() + 22 + Math.random() * 8, 2: now() + 34 + Math.random() * 10, 3: now() + 48 };
    ev({ t: 'write' });
  }
  function judge() {
    const L = LETTERS[st.round], cells = {};
    for (const c of ORDER) {
      cells[c] = {};
      COLS.forEach(([k], i) => {
        const a = c === '0' ? (st.sheets[0][k] || '') : BANK[L][c][i];
        const fix = a && norm(a)[0] !== norm(L)[0];
        const bad = !a || fix || a in NO || norm(a).length < 2;
        cells[c][k] = { a, ok: !bad, s: 0, why: fix ? `با «${L}» شروع نمی‌شود` : a in NO ? NO[a] || 'غذای آماده نیست' : '', key: norm(a), fix: !!fix };
      });
    }
    const rec = { letter: L, by: 'ai', cells, scores: {} };
    score(rec);
    st.results.push(rec); totals();
    st.phase = 'show'; st.deadline = now() + 25; st.ready = []; st.appeals = {};
    ev({ t: 'scored' });
  }
  function score(rec) {
    for (const c of ORDER) rec.scores[c] = 0;
    for (const [k] of COLS) {
      const n = {};
      for (const c of ORDER) if (rec.cells[c][k].ok) n[rec.cells[c][k].key] = (n[rec.cells[c][k].key] || 0) + 1;
      for (const c of ORDER) { const x = rec.cells[c][k]; x.s = x.ok ? (n[x.key] === 1 ? 10 : 5) : 0; rec.scores[c] += x.s; }
    }
  }
  const totals = () => { for (const c of ORDER) st.totals[c] = st.results.reduce((s, r) => s + (r.scores[c] || 0), 0); };
  function next() {
    for (const [key, ap] of Object.entries(st.appeals)) if (ap.res == null) resolve(key);
    if (st.round + 1 >= LETTERS.length) {
      st.phase = 'over'; st.over = true;
      const best = Math.max(...ORDER.map(c => st.totals[c]));
      st.winners = ORDER.filter(c => st.totals[c] === best); ev({ t: 'win', c: st.winners }); return;
    }
    st.round++; st.phase = 'letter'; st.deadline = now() + 3.5; st.letterAt = now(); ev({ t: 'letter' });
  }
  function resolve(key) {
    const ap = st.appeals[key]; ap.res = ap.yes.length > ap.no.length;
    if (ap.res) { const rec = st.results[st.results.length - 1], x = rec.cells[ap.c][ap.col]; Object.assign(x, { ok: true, why: '', appealed: true, key: norm(x.a) }); score(rec); totals(); }
  }
  function tick() {
    const t = now();
    if (st.phase === 'write' || st.phase === 'stop') {
      for (const c of ['1', '2', '3']) if (!st.done.includes(c) && t >= st.botDone[c]) {
        st.done.push(c);
        if (c === '3' && st.phase === 'write') { st.phase = 'stop'; st.stopper = '3'; st.deadline = Math.min(st.deadline, t + 20); ev({ t: 'stop', c: '3' }); }
      }
      if (t >= st.deadline || st.done.length === 4) { st.phase = 'judge'; st.deadline = t + 3; ev({ t: 'judge' }); }
    } else if (st.phase === 'letter' && t >= st.deadline) startWrite();
    else if (st.phase === 'judge' && t >= st.deadline) judge();
    else if (st.phase === 'show') {
      for (const [key, ap] of Object.entries(st.appeals)) if (ap.res == null && t - ap.at > 3) { ap.yes = ['1', '2']; resolve(key); }
      if (t - (st.deadline - 25) > 5) ['1', '2', '3'].forEach(c => { if (!st.ready.includes(c)) st.ready.push(c); });
      if (t >= st.deadline || (st.ready.length === 4 && !Object.values(st.appeals).some(a => a.res == null))) next();
    }
  }
  function view(since) {
    const t = now(), writing = ['write', 'stop', 'judge'].includes(st.phase);
    const shown = st.phase !== 'letter' || t >= st.letterAt;
    return {
      order: ORDER, me: '0', cols: COLS.map(([k, fa]) => ({ k, fa })), rounds_n: LETTERS.length, round: st.round, secs: 180, phase: st.phase,
      players: Object.fromEntries(ORDER.map(c => [c, { name: P[c].name, av: P[c].av, pic: '', out: false, me: c === '0', total: st.totals[c],
        done: st.done.includes(c), ready: st.ready.includes(c), filled: writing ? (c === '0' ? Object.keys(st.sheets[0] || {}).length : st.done.includes(c) ? COLS.length : Math.min(COLS.length - 1, Math.floor((t % 60) / 6))) : null }])),
      letter: shown ? LETTERS[st.round] : null, line: shown ? LINES[st.round] : '', waiting: [],
      deadline_ms: Math.max(0, (st.deadline - t) * 1000), sheet: writing ? Object.assign({}, st.sheets[0]) : null, submitted: st.done.includes('0'),
      stopper: st.stopper, results: st.results, totals: st.totals, events: st.events.filter(e => e.seq > since), seq: st.seq,
      appeals: Object.fromEntries(Object.entries(st.appeals).map(([k, a]) => [k, { c: a.c, col: a.col, yes: a.yes.length, no: a.no.length, res: a.res, mine: null }])),
      over: st.over, winner: st.winners[0] || null, winners: st.winners,
    };
  }
  const out = since => ({ id: 'demo', status: st.over ? 'over' : 'playing', cfg: { game: 'esmfamil', rounds: 3, secs: 180 }, me: '0', game: view(since || 0) });
  const fail = code => { const e = new Error(code); e.code = code; throw e; };
  const sheetIn = sh => { for (const [k, v] of Object.entries(sh || {})) { if (v) st.sheets[0][k] = String(v).slice(0, 32); else delete st.sheets[0][k]; } };
  return {
    async match(id, since) { if (!st) reset(); tick(); return out(since); },
    async answer(id, sh) { if (!['write', 'stop'].includes(st.phase)) fail('closed'); sheetIn(sh); return { ok: true }; },
    async stop(id, sh, since) {
      sheetIn(sh); if (Object.keys(st.sheets[0]).length < COLS.length) fail('sheet_not_full');
      st.done.push('0'); st.phase = 'stop'; st.stopper = '0'; st.deadline = Math.min(st.deadline, now() + 20); ev({ t: 'stop', c: '0' }); tick(); return out(since);
    },
    async submit(id, sh, since) { sheetIn(sh); if (!st.done.includes('0')) st.done.push('0'); tick(); return out(since); },
    async appeal(id, col, since) { st.appeals[`0:${col}`] = { c: '0', col, yes: [], no: [], res: null, at: now() }; st.deadline = Math.max(st.deadline, now() + 15); return out(since); },
    async vote(id, key, yes, since) { return out(since); },
    async ready(id, since) { if (!st.ready.includes('0')) st.ready.push('0'); tick(); return out(since); },
    async leave() { reset(); return { left: true }; },
  };
})();
