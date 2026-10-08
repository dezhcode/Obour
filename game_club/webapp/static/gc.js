/* Game Club — ابزار مشترک همه صفحه ها.
   نسخه پیش نمایش: وضعیت (موجودی، آمار، تنظیمات) فقط در مرورگر ذخیره می شود. */
(() => {
const FD = s => String(s).replace(/\d/g, d => '۰۱۲۳۴۵۶۷۸۹'[d]);
const fa = n => FD(Math.round(n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, '٬'));
const rand = n => Math.floor(Math.random() * n);
const sleep = ms => new Promise(r => setTimeout(r, ms));
const store = {
  get(k, d) { try { const v = localStorage.getItem('gclub_' + k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem('gclub_' + k, JSON.stringify(v)); } catch (e) {} },
};
const S = Object.assign({
  bal: 1250, wins: 0, games: 0, won: 0, spent: 0, mode: 'free', notify: {}, sound: true, tutorial: false, showSpend: false,
  ledger: [{ t: 'هدیهٔ شروع Game Club', a: 1250, k: 'gift', at: Date.now() - 864e5 }],
}, store.get('state', {}));
const save = () => store.set('state', S);
function ledger(t, a, k) { S.ledger.unshift({ t, a, k, at: Date.now() }); S.ledger = S.ledger.slice(0, 40); }

/* ---------- آیکون ها (خطی، ۲۴×۲۴، currentColor) ---------- */
const P = {
  home: '<path d="M3 11l9-7 9 7v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z"/>',
  trophy: '<path d="M8 4h8v5a4 4 0 0 1-8 0zM8 6H4.5v1.5A3.5 3.5 0 0 0 8 11M16 6h3.5v1.5A3.5 3.5 0 0 1 16 11M12 13v4M8 20h8M9.5 17h5"/>',
  wallet: '<path d="M4 7.5A2.5 2.5 0 0 1 6.5 5H18v3"/><rect x="4" y="8" width="16" height="11" rx="2.5"/><path d="M16 13.5h.01"/>',
  bag: '<path d="M4.5 8h15l-1.3 11.2a2 2 0 0 1-2 1.8H7.8a2 2 0 0 1-2-1.8z"/><path d="M9 8V6.5a3 3 0 0 1 6 0V8"/>',
  help: '<circle cx="12" cy="12" r="9"/><path d="M9.6 9.3a2.5 2.5 0 0 1 4.8.9c0 1.7-2.4 2.2-2.4 3.8M12 17h.01"/>',
  back: '<path d="M9 5l7 7-7 7"/>',
  close: '<path d="M6 6l12 12M18 6L6 18"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  soundOn: '<path d="M4 9.5h3.5L12 6v12l-4.5-3.5H4z"/><path d="M15.5 9a4.5 4.5 0 0 1 0 6M18 6.5a8 8 0 0 1 0 11"/>',
  soundOff: '<path d="M4 9.5h3.5L12 6v12l-4.5-3.5H4z"/><path d="M16 10l5 5M21 10l-5 5"/>',
  users: '<circle cx="9" cy="8.5" r="3.5"/><path d="M3 20c.6-3.6 3-5.5 6-5.5s5.4 1.9 6 5.5"/><path d="M16 5.2a3.5 3.5 0 0 1 0 6.6M18 14.8c1.7.7 2.8 2.4 3 5.2"/>',
  link: '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
  bot: '<rect x="5" y="8" width="14" height="11" rx="3"/><path d="M12 4v4M9 13h.01M15 13h.01M9.5 16.5h5"/>',
  globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c3 3.2 3 14.8 0 18M12 3c-3 3.2-3 14.8 0 18"/>',
  bolt: '<path d="M13 3L5 13.5h6L10 21l8-10.5h-6z"/>',
  clock: '<circle cx="12" cy="13" r="8"/><path d="M12 9v4l3 2M9 2.5h6"/>',
  spark: '<path d="M12 3l1.9 5.6L19.5 10.5l-5.6 1.9L12 18l-1.9-5.6L4.5 10.5l5.6-1.9z"/>',
  shield: '<path d="M12 3l8 3v6c0 4.6-3.4 8.2-8 9-4.6-.8-8-4.4-8-9V6z"/><path d="M8.5 12l2.5 2.5 4.5-5"/>',
  card: '<rect x="3" y="6" width="18" height="13" rx="2.5"/><path d="M3 10.5h18M7 15h4"/>',
  check: '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
  copy: '<rect x="8" y="8" width="12" height="12" rx="2.5"/><path d="M16 8V6.5A2.5 2.5 0 0 0 13.5 4h-7A2.5 2.5 0 0 0 4 6.5v7A2.5 2.5 0 0 0 6.5 16H8"/>',
  send: '<path d="M21 4L10 14M21 4l-6.5 17-4.5-7-7-4.5z"/>',
  bell: '<path d="M6 10a6 6 0 0 1 12 0c0 5 2 6.5 2 6.5H4S6 15 6 10zM10 20a2 2 0 0 0 4 0"/>',
  dice: '<rect x="4" y="4" width="16" height="16" rx="4"/><path d="M8.5 8.5h.01M15.5 15.5h.01M12 12h.01M15.5 8.5h.01M8.5 15.5h.01"/>',
  arrowUp: '<path d="M7 14l5-5 5 5"/>',
};
const icon = (n, w = 2.2) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="${w}" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${P[n] || ''}</svg>`;
const COIN = '<svg viewBox="0 0 32 32" aria-hidden="true"><circle cx="16" cy="17.5" r="13" fill="#E09A00"/><circle cx="16" cy="15" r="13" fill="#FFC43B"/><circle cx="16" cy="15" r="9.4" fill="none" stroke="#E09A00" stroke-width="2"/><path d="M16 9.3l1.75 3.6 3.95.55-2.86 2.73.68 3.92L16 18.2l-3.52 1.9.68-3.92-2.86-2.73 3.95-.55z" fill="#FFF3C4"/></svg>';
const coin = () => `<span class="coin">${COIN}</span>`;
const amount = (n, cls = '') => `<span class="amount ${cls}">${coin()}<span>${fa(n)}</span></span>`;

/* ---------- آواتار ساده کارتونی (بدون عکس) ---------- */
function avatar(seed) {
  const skin = ['#F6C9A0', '#E8B48A', '#D49A6A', '#F2D3B3'][seed % 4];
  const hair = ['#3B2A20', '#1E1A18', '#8A5A2B', '#B9B9B9'][(seed >> 2) % 4];
  const shirt = ['#2F7BF6', '#EF4136', '#2FB24C', '#FFC226', '#7C5CE0'][seed % 5];
  const st = seed % 3;
  const h = st === 0 ? `<path d="M17 29c0-10 7-16 15-16s15 6 15 16c-3-5-8-8-15-8s-12 3-15 8z" fill="${hair}"/>`
    : st === 1 ? `<path d="M15 32c0-12 7-19 17-19s17 7 17 19v12c-3 0-5-3-5-7 0-8-2-12-12-13-10 1-12 5-12 13 0 4-2 7-5 7z" fill="${hair}"/>`
    : `<path d="M15 28c0-9 8-15 17-15s17 6 17 15z" fill="${shirt}"/><rect x="30" y="24" width="24" height="5.5" rx="2.7" fill="${shirt}"/><rect x="15" y="26" width="34" height="3" fill="rgba(0,0,0,.15)"/>`;
  return `<svg viewBox="0 0 64 64" aria-hidden="true"><rect width="64" height="64" fill="#CFE9FF"/><path d="M8 64c2-12 12-19 24-19s22 7 24 19z" fill="${shirt}"/><circle cx="32" cy="31" r="15" fill="${skin}"/>${h}<circle cx="26.5" cy="31" r="2.1" fill="#222"/><circle cx="37.5" cy="31" r="2.1" fill="#222"/><path d="M26 37c3 3 9 3 12 0" stroke="#7A3B2A" stroke-width="2.2" fill="none" stroke-linecap="round"/><circle cx="22" cy="35" r="2.4" fill="rgba(239,65,54,.22)"/><circle cx="42" cy="35" r="2.4" fill="rgba(239,65,54,.22)"/></svg>`;
}
const avatarEl = (seed, ring, extra = '') => `<span class="avatar ${extra}" style="--ring:${ring || 'var(--surface)'}"><span>${avatar(seed)}</span></span>`;

/* ---------- مهره منچ ---------- */
const COL = {
  blue: { hex: '#2F7BF6', deep: '#1A4FB0', fa: 'آبی' }, red: { hex: '#EF4136', deep: '#A8241B', fa: 'قرمز' },
  green: { hex: '#2FB24C', deep: '#1B7A33', fa: 'سبز' }, yellow: { hex: '#FFC226', deep: '#B57B00', fa: 'زرد' },
};
function pawn(c, crown) {
  const { hex, deep } = COL[c];
  return `<svg viewBox="0 0 40 50" aria-hidden="true"><ellipse cx="20" cy="46.5" rx="12" ry="3" fill="rgba(0,0,0,.28)"/>
    <path d="M20 3c7.5 0 10.5 6.5 9 12-.6 2.4-2.2 3.8-3.4 4.6C32 22.5 36 30 36 37.5c0 6-7 8.5-16 8.5S4 43.5 4 37.5C4 30 8 22.5 14.4 19.6 13.2 18.8 11.6 17.4 11 15c-1.5-5.5 1.5-12 9-12z" fill="${hex}" stroke="${deep}" stroke-width="1.8"/>
    <ellipse cx="13" cy="9.5" rx="2.6" ry="4" fill="rgba(255,255,255,.5)" transform="rotate(-25 13 9.5)"/><ellipse cx="11" cy="31" rx="2.8" ry="6.5" fill="rgba(255,255,255,.3)" transform="rotate(14 11 31)"/>
    <ellipse cx="16" cy="11.5" rx="3.7" ry="4.3" fill="#fff" stroke="#1d1d1d" stroke-width=".8"/><ellipse cx="24" cy="11.5" rx="3.7" ry="4.3" fill="#fff" stroke="#1d1d1d" stroke-width=".8"/>
    <circle cx="16.9" cy="12.4" r="1.9" fill="#111"/><circle cx="24.9" cy="12.4" r="1.9" fill="#111"/>
    ${crown ? '<path d="M10 4l3.5 3.5L20-2l6.5 9.5L30 4l-1.5 7.5h-17z" fill="#FFC43B" stroke="#B57B00" stroke-width="1.2" stroke-linejoin="round"/>' : ''}</svg>`;
}
const PIPS = { 1: [4], 2: [0, 8], 3: [0, 4, 8], 4: [0, 2, 6, 8], 5: [0, 2, 4, 6, 8], 6: [0, 2, 3, 5, 6, 8] };
const pips = v => Array.from({ length: 9 }, (_, i) => `<i class="${v && PIPS[v].includes(i) ? 'on' : ''}"></i>`).join('');

/* ---------- اعلان و برگه ---------- */
function toast(t) {
  document.querySelectorAll('.toast').forEach(x => x.remove());
  const el = document.createElement('div'); el.className = 'toast'; el.setAttribute('role', 'status'); el.textContent = t;
  document.body.appendChild(el); setTimeout(() => el.remove(), 2600);
}
let layer;
function sheet(html, { center = false, dismiss = true, onClose } = {}) {
  if (!layer) { layer = document.createElement('div'); document.body.appendChild(layer); }
  layer.innerHTML = `<div class="scrim${center ? ' center' : ''}"><div class="sheet" role="dialog" aria-modal="true">${center ? '' : '<span class="grab"></span>'}${html}</div></div>`;
  const sc = layer.firstChild, sh = sc.firstChild;
  sc.addEventListener('click', e => { if (e.target === sc && dismiss) { close(); onClose && onClose(); } });
  sh.querySelectorAll('[data-close]').forEach(b => b.addEventListener('click', () => { close(); onClose && onClose(); }));
  const f = sh.querySelector('button,a'); if (f) setTimeout(() => f.focus({ preventScroll: true }), 50);
  return sh;
}
function close() { if (layer) layer.innerHTML = ''; }
const sheetHead = t => `<div class="sheet-head"><h2>${t}</h2><button class="close" data-close aria-label="بستن">${icon('close', 2.6)}</button></div>`;

/* ---------- صدا: همه با Web Audio ساخته می شوند، بدون فایل ---------- */
let ac = null, master = null;
function ctx() {
  if (!S.sound) return null;
  try {
    if (!ac) { ac = new (window.AudioContext || window.webkitAudioContext)(); master = ac.createGain(); master.gain.value = .55; master.connect(ac.destination); }
    if (ac.state === 'suspended') ac.resume();
  } catch (e) { return null; }
  return ac;
}
function tone(f, d, { type = 'sine', g = .3, to, at = 0, attack = .005 } = {}) {
  const a = ctx(); if (!a) return;
  const t = a.currentTime + at, o = a.createOscillator(), v = a.createGain();
  o.type = type; o.frequency.setValueAtTime(f, t); if (to) o.frequency.exponentialRampToValueAtTime(to, t + d);
  v.gain.setValueAtTime(0, t); v.gain.linearRampToValueAtTime(g, t + attack); v.gain.exponentialRampToValueAtTime(.0008, t + d);
  o.connect(v); v.connect(master); o.start(t); o.stop(t + d + .02);
}
function noise(d, { g = .25, f = 2000, q = 1, at = 0, type = 'bandpass' } = {}) {
  const a = ctx(); if (!a) return;
  const t = a.currentTime + at, len = Math.ceil(a.sampleRate * d), b = a.createBuffer(1, len, a.sampleRate), ch = b.getChannelData(0);
  for (let i = 0; i < len; i++) ch[i] = (Math.random() * 2 - 1) * (1 - i / len);
  const s = a.createBufferSource(), fl = a.createBiquadFilter(), v = a.createGain();
  s.buffer = b; fl.type = type; fl.frequency.value = f; fl.Q.value = q; v.gain.value = g;
  s.connect(fl); fl.connect(v); v.connect(master); s.start(t);
}
const sfx = {
  tap() { tone(1400, .04, { type: 'triangle', g: .12 }); },
  coin() { tone(1320, .09, { type: 'square', g: .08 }); tone(1980, .22, { type: 'square', g: .08, at: .07 }); },
  dice() { for (let i = 0; i < 7; i++) noise(.035, { g: .35, f: 1800 + Math.random() * 2200, q: 2.5, at: i * .055 + Math.random() * .02 }); noise(.08, { g: .4, f: 500, q: .8, at: .42 }); tone(140, .09, { g: .25, at: .42 }); },
  step(i = 0) { tone(520 + i * 40, .07, { type: 'triangle', g: .2, to: 700 + i * 40 }); },
  enter() { [523, 659, 784].forEach((f, i) => tone(f, .14, { type: 'triangle', g: .2, at: i * .07 })); },
  capture() { tone(420, .32, { type: 'square', g: .12, to: 70 }); noise(.18, { g: .3, f: 900, q: .7, at: .02 }); tone(90, .2, { g: .35, at: .05 }); },
  home() { tone(880, .35, { g: .2 }); tone(1320, .45, { g: .16, at: .1 }); tone(1760, .5, { g: .1, at: .2 }); },
  six() { [988, 1319, 1568].forEach((f, i) => tone(f, .12, { type: 'triangle', g: .14, at: i * .05 })); },
  turn() { tone(740, .12, { type: 'sine', g: .22 }); tone(988, .22, { type: 'sine', g: .22, at: .11 }); },
  nomove() { tone(180, .22, { type: 'sawtooth', g: .08, to: 140 }); },
  tick() { tone(1000, .03, { type: 'square', g: .05 }); },
  win() { [523, 659, 784, 1047, 784, 1047].forEach((f, i) => tone(f, i === 5 ? .6 : .16, { type: 'triangle', g: .22, at: i * .13 })); },
  lose() { [392, 349, 311, 262].forEach((f, i) => tone(f, .28, { type: 'triangle', g: .18, at: i * .2 })); },
  error() { tone(220, .14, { type: 'square', g: .08 }); tone(180, .2, { type: 'square', g: .08, at: .12 }); },
};
function setSound(on) { S.sound = on; save(); if (on) { ctx(); sfx.tap(); } }

/* ---------- ناوبری پایین (چهار بخش اصلی) ---------- */
const NAV = [['home', 'index.html', 'خانه', 'home'], ['leaderboard', 'leaderboard.html', 'رده‌بندی', 'trophy'], ['wallet', 'wallet.html', 'کیف امتیاز', 'wallet'], ['shop', 'shop.html', 'خدمات عبور', 'bag']];
function nav(active) {
  const n = document.createElement('nav'); n.className = 'nav'; n.setAttribute('aria-label', 'بخش‌های Game Club');
  n.innerHTML = `<div class="nav-in">${NAV.map(([id, href, label, ic]) => `<a href="${href}"${id === active ? ' aria-current="page"' : ''}>${icon(ic)}${label}</a>`).join('')}</div>`;
  document.body.appendChild(n);
}
function mount(root = document) {
  root.querySelectorAll('[data-ic]').forEach(el => { el.innerHTML = icon(el.dataset.ic); });
  root.querySelectorAll('[data-coin]').forEach(el => { el.innerHTML = COIN; el.classList.add('coin'); });
  root.querySelectorAll('[data-bal]').forEach(el => { el.textContent = fa(S.bal); });
}
document.addEventListener('click', e => { if (e.target.closest('.btn,.chip,.seg button,.choice,.nav a,.icon-btn')) sfx.tap(); }, true);

/* ---------- داده نمونه (تا وقتی API Game Club ساخته شود) ---------- */
const PEOPLE = [['کیان ر.', 3], ['مهسا ک.', 5], ['امیرعلی م.', 2], ['نگار س.', 9], ['رضا ت.', 12], ['پریا ن.', 13], ['سینا ح.', 6], ['هستی ا.', 17], ['آرش د.', 10], ['یاسمن ف.', 21]];
const LB = {
  top: [[0, 48, 12400], [1, 41, 9850], [2, 37, 8200], [3, 33, 6900], [4, 29, 5750], [5, 26, 4300], [6, 22, 3950], [7, 19, 3100], [8, 17, 2650], [9, 15, 2200]],
  spend: [[2, 0, 24500], [6, 0, 18200], [0, 0, 15900], [7, 0, 11300], [1, 0, 9600], [4, 0, 7400], [3, 0, 5200], [5, 0, 3900], [9, 0, 2800], [8, 0, 1900]],
};
const SHOP = [
  { id: 'cfg10', cat: 'net', ic: 'globe', t: 'کانفیگ ۱۰ گیگ یک‌ماهه', s: 'اینترنت آزاد عبور، تحویل فوری', p: 950 },
  { id: 'cfg30', cat: 'net', ic: 'globe', t: 'کانفیگ ۳۰ گیگ یک‌ماهه', s: 'برای مصرف زیاد', p: 2200 },
  { id: 'gb5', cat: 'extra', ic: 'bolt', t: '۵ گیگ حجم اضافه', s: 'روی سرویس فعلی‌ات در عبور', p: 400 },
  { id: 'ren7', cat: 'extra', ic: 'clock', t: 'تمدید ۷ روزه', s: 'روی سرویس فعلی‌ات در عبور', p: 350 },
  { id: 'ai1', cat: 'ai', ic: 'spark', t: 'اشتراک هوش مصنوعی یک‌ماهه', s: 'از فروشگاه هوش مصنوعی عبور', p: 3800 },
];
/* ---------- هندسه منچ (۱۵×۱۵): مسیر ۵۲ خانه، شروع هر رنگ، راهروی خانه ---------- */
const LUDO = {
  TRACK: [[1,6],[2,6],[3,6],[4,6],[5,6],[6,5],[6,4],[6,3],[6,2],[6,1],[6,0],[7,0],[8,0],[8,1],[8,2],[8,3],[8,4],[8,5],[9,6],[10,6],[11,6],[12,6],[13,6],[14,6],[14,7],[14,8],[13,8],[12,8],[11,8],[10,8],[9,8],[8,9],[8,10],[8,11],[8,12],[8,13],[8,14],[7,14],[6,14],[6,13],[6,12],[6,11],[6,10],[6,9],[5,8],[4,8],[3,8],[2,8],[1,8],[0,8],[0,7],[0,6]],
  SEAT: {
    blue:   { start: 0,  lane: [[1,7],[2,7],[3,7],[4,7],[5,7]], yard: [0,0], fin: [6.75,7.5], arrow: 0 },
    red:    { start: 13, lane: [[7,1],[7,2],[7,3],[7,4],[7,5]], yard: [9,0], fin: [7.5,6.75], arrow: 90 },
    green:  { start: 26, lane: [[13,7],[12,7],[11,7],[10,7],[9,7]], yard: [9,9], fin: [8.25,7.5], arrow: 180 },
    yellow: { start: 39, lane: [[7,13],[7,12],[7,11],[7,10],[7,9]], yard: [0,9], fin: [7.5,8.25], arrow: 270 },
  },
  ORDER: ['blue', 'red', 'green', 'yellow'],
  SAFE: [0, 8, 13, 21, 26, 34, 39, 47],
  SOCKETS: [[2.1,2.1],[3.9,2.1],[2.1,3.9],[3.9,3.9]],
};
function boardArt() {
  const L = LUDO, startOf = {};
  for (const c of L.ORDER) startOf[L.SEAT[c].start] = c;
  let g = '<rect x="-.5" y="-.5" width="16" height="16" rx="1.2" fill="#3F9E27"/><rect x="0" y="0" width="15" height="15" rx=".8" fill="#46BDEB"/>';
  for (const c of L.ORDER) {
    const [x, y] = L.SEAT[c].yard;
    g += `<rect x="${x + .1}" y="${y + .1}" width="5.8" height="5.8" rx=".8" fill="${COL[c].hex}"/><rect x="${x + .95}" y="${y + .95}" width="4.1" height="4.1" rx=".8" fill="#FFFDF6"/>`;
    for (const [sx, sy] of L.SOCKETS) g += `<circle cx="${x + sx}" cy="${y + sy}" r=".55" fill="${COL[c].hex}"/>`;
  }
  L.TRACK.forEach(([x, y], i) => { const c = startOf[i]; g += `<rect x="${x + .07}" y="${y + .07}" width=".86" height=".86" rx=".2" fill="${c ? COL[c].hex : '#FFFDF6'}"/>`; });
  for (const c of L.ORDER) for (const [x, y] of L.SEAT[c].lane) g += `<rect x="${x + .07}" y="${y + .07}" width=".86" height=".86" rx=".2" fill="${COL[c].hex}"/>`;
  g += '<path d="M6 6L7.5 7.5L6 9z" fill="#2F7BF6"/><path d="M6 6L9 6L7.5 7.5z" fill="#EF4136"/><path d="M9 6L9 9L7.5 7.5z" fill="#2FB24C"/><path d="M6 9L9 9L7.5 7.5z" fill="#FFC226"/>';
  return `<svg viewBox="-.5 -.5 16 16" aria-hidden="true">${g}</svg>`;
}
const RATE = 100; // هر امتیاز چند تومان (نمونه)
document.documentElement.lang = 'fa'; document.documentElement.dir = 'rtl';

window.GC = { PEOPLE, LB, SHOP, RATE, LUDO, boardArt, FD, fa, rand, sleep, store, S, save, ledger, icon, COIN, coin, amount, avatar, avatarEl, COL, pawn, pips, toast, sheet, close, sheetHead, sfx, setSound, nav, mount };
document.addEventListener('DOMContentLoaded', () => mount());
})();
