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

/* ---------- SDK مینی اپ تلگرام ----------
   داخل تلگرام: initData هست، همه چیز از سرور. بیرون (مرورگر، پیش نمایش):
   حالت نمایشی با demo.js. قواعد تمام صفحه: محتوا زیر نوار وضعیت گوشی
   (safeAreaInset) و دکمه های شناور تلگرام (contentSafeAreaInset) نمی رود. */
const tg = (window.Telegram && window.Telegram.WebApp) || null;
const live = !!(tg && tg.initData);
const root = document.documentElement;
root.classList.toggle('tg', live);
const MOBILE = ['android', 'ios'];
function applyInsets() {
  if (!tg) return;
  const sa = tg.safeAreaInset || {}, ca = tg.contentSafeAreaInset || {};
  const px = v => (Number(v) > 0 ? Math.round(Number(v)) : 0) + 'px';
  root.style.setProperty('--sa-t', px(sa.top)); root.style.setProperty('--sa-b', px(sa.bottom));
  root.style.setProperty('--sa-l', px(sa.left)); root.style.setProperty('--sa-r', px(sa.right));
  root.style.setProperty('--csa-t', px(ca.top)); root.style.setProperty('--csa-b', px(ca.bottom));
  root.classList.toggle('is-fs', !!tg.isFullscreen);
}
const ver = v => !!(tg && tg.isVersionAtLeast && tg.isVersionAtLeast(v));
if (live) {
  try { tg.ready(); tg.expand(); } catch (e) {}
  // رنگ نوار تلگرام با زمینه صفحه یکی است تا درز دیده نشود؛ صفحه بازی منچ تیره است
  const dark = document.body && document.body.classList.contains('game');
  try { tg.setHeaderColor(dark ? '#3A3350' : '#F5F6FB'); tg.setBackgroundColor(dark ? '#3A3350' : '#F5F6FB'); } catch (e) {}
  try { ver('7.10') && tg.setBottomBarColor(dark ? '#3A3350' : '#FFFFFF'); } catch (e) {}
  // کشیدن عمودی (مثلا هنگام بازی) نباید مینی اپ را ببندد
  try { ver('7.7') && tg.disableVerticalSwipes(); } catch (e) {}
  ['safeAreaChanged', 'contentSafeAreaChanged', 'fullscreenChanged', 'viewportChanged', 'fullscreenFailed']
    .forEach(ev => { try { tg.onEvent(ev, applyInsets); } catch (e) {} });
  applyInsets();
  if (MOBILE.includes(tg.platform) && ver('8.0') && !tg.isFullscreen) { try { tg.requestFullscreen(); } catch (e) {} }
}
/* فقط پیش نمایش بیرون از تلگرام: #fs ظاهر تمام صفحه تلگرام را شبیه سازی می کند
   (نوار وضعیت ۴۴ و نوار دکمه های تلگرام ۴۶ پیکسل)، #nofs خاموشش می کند */
if (!live) {
  try {
    if (location.hash === '#fs') localStorage.setItem('gclub_fs_sim', '1');
    if (location.hash === '#nofs') localStorage.removeItem('gclub_fs_sim');
    if (localStorage.getItem('gclub_fs_sim')) {
      root.style.setProperty('--sa-t', '44px'); root.style.setProperty('--csa-t', '46px'); root.style.setProperty('--sa-b', '24px');
      root.classList.add('is-fs', 'fs-sim');
      document.addEventListener('DOMContentLoaded', () => {
        const bar = document.createElement('div'); bar.className = 'tg-sim'; bar.setAttribute('aria-hidden', 'true');
        bar.innerHTML = '<span class="tg-sim-sb"><b>9:41</b><b>5G</b></span><span class="tg-sim-btn l">✕ بستن</span><span class="tg-sim-btn r">•••</span>';
        document.body.appendChild(bar);
      });
    }
  } catch (e) {}
}
/* دکمه برگشت بومی تلگرام؛ دکمه برگشت داخل صفحه فقط بیرون از تلگرام دیده می شود */
function back(href) {
  if (!live || !ver('6.1')) return;
  try {
    if (!href) { tg.BackButton.hide(); return; }
    tg.BackButton.show();
    tg.BackButton.onClick(() => { typeof href === 'function' ? href() : (location.href = href); });
  } catch (e) {}
}
function haptic(kind) {
  if (!live || !ver('6.1')) return;
  try {
    const H = tg.HapticFeedback;
    if (['success', 'error', 'warning'].includes(kind)) H.notificationOccurred(kind);
    else if (kind === 'select') H.selectionChanged();
    else H.impactOccurred(kind || 'light');
  } catch (e) {}
}
function guardClose(on) { if (!live || !ver('6.2')) return; try { on ? tg.enableClosingConfirmation() : tg.disableClosingConfirmation(); } catch (e) {} }
function portrait(on) { if (!live || !ver('8.0')) return; try { on ? tg.lockOrientation() : tg.unlockOrientation(); } catch (e) {} }
function openLink(url) {
  if (live && /^https:\/\/t\.me\//.test(url)) { try { tg.openTelegramLink(url); return; } catch (e) {} }
  if (live) { try { tg.openLink(url); return; } catch (e) {} }
  window.open(url, '_blank', 'noopener');
}
function startParam() { try { return (tg && tg.initDataUnsafe && tg.initDataUnsafe.start_param) || ''; } catch (e) { return ''; } }

/* ---------- API سرور ---------- */
const ERR = {
  insufficient: 'امتیاز کافی نیست؛ اول کیف را شارژ کن', obour_insufficient: 'موجودی کیف پول عبور کافی نیست',
  no_obour: 'اول یک بار ربات عبور را استارت کن', busy: 'یک لحظه بعد دوباره امتحان کن', stake_off: 'بازی با امتیاز فعلا خاموش است',
  bad_invite: 'این لینک دعوت معتبر نیست', started: 'این میز شروع شده', full: 'این میز پر است', in_match: 'تو الان سر یک میز دیگر هستی',
  need_players: 'بازی امتیازی بدون حریف واقعی شروع نمی‌شود', not_host: 'فقط سازندهٔ میز می‌تواند شروع کند',
  plan_unavailable: 'این پلن الان فروخته نمی‌شود', auth: 'نشست منقضی شده؛ مینی‌اپ را ببند و دوباره باز کن',
  rate: 'درخواست‌ها زیاد شد؛ چند ثانیه صبر کن', network: 'اتصال برقرار نشد؛ اینترنتت را بررسی کن', server: 'خطای سرور؛ دوباره امتحان کن',
  not_your_turn: 'الان نوبت تو نیست', empty: 'اول یک چیزی بنویس', chat_slow: 'کمی آهسته‌تر؛ چند ثانیه صبر کن', illegal_move: 'این مهره نمی‌تواند حرکت کند', not_found: 'این میز پیدا نشد', bad_pack: 'این بسته در دسترس نیست',
};
const errText = e => ERR[e && e.code] || ERR.server;
async function api(name, { body, q } = {}) {
  let r;
  try {
    r = await fetch('api/' + name + (q ? '?' + new URLSearchParams(q) : ''), {
      method: body ? 'POST' : 'GET', cache: 'no-store',
      headers: { 'X-Init-Data': tg ? tg.initData : '', 'Content-Type': 'application/json' },
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch (e) { const x = new Error('network'); x.code = 'network'; throw x; }
  let j = {}; try { j = await r.json(); } catch (e) {}
  if (!r.ok) { const x = new Error(j.error || 'server'); x.code = j.error || 'server'; x.data = j; throw x; }
  return j;
}
const idem = () => Date.now().toString(36) + Math.random().toString(36).slice(2, 10);
const liveData = {
  me: () => api('me'),
  charge: points => api('wallet/charge', { body: { points, idem: idem() } }),
  notify: game => api('notify', { body: { game } }),
  setFlag: (f, v) => api('settings', { body: { [f]: v ? 1 : 0 } }),
  leaderboard: (kind, period) => api('leaderboard', { q: { kind, period } }),
  shop: () => api('shop'),
  buy: plan_id => api('shop/buy', { body: { plan_id, idem: idem() } }),
  transfer: points => api('shop/transfer', { body: { points, idem: idem() } }),
};
const liveLudo = {
  queueJoin: cfg => api('ludo/queue', { body: { cfg } }),
  queueStatus: () => api('ludo/queue'),
  queueLeave: () => api('ludo/queue/leave', { body: {} }),
  invite: cfg => api('ludo/invite', { body: { cfg } }),
  join: code => api('ludo/join', { body: { code } }),
  start: match => api('ludo/start', { body: { match } }),
  match: (id, since = 0, chat = null) => api('ludo/match', { q: Object.assign(id ? { id, since } : { since }, chat == null ? {} : { chat }) }),
  chat: (match, text) => api('ludo/chat', { body: { match, text } }),
  roll: (match, since) => api('ludo/roll', { body: { match, since } }),
  move: (match, k, since) => api('ludo/move', { body: { match, k, since } }),
  leave: match => api('ludo/leave', { body: { match } }),
};
/* موجودی که سربرگ ها نشان می دهند */
let points = null;
async function refreshMe() {
  const me = await GC.data.me();
  points = me.player.points; mount();
  return me;
}

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
  up: '<path d="M12 19V5M5.5 11.5L12 5l6.5 6.5"/>',
  exit: '<path d="M14 4h3.5A2.5 2.5 0 0 1 20 6.5v11a2.5 2.5 0 0 1-2.5 2.5H14"/><path d="M10 16.5L5.5 12 10 7.5M5.5 12H15"/>',
  table: '<rect x="3" y="7" width="18" height="10" rx="5"/><path d="M8 17v3M16 17v3"/>',
  chat: '<path d="M4 5.5A2.5 2.5 0 0 1 6.5 3h11A2.5 2.5 0 0 1 20 5.5v8a2.5 2.5 0 0 1-2.5 2.5H10l-4.5 4v-4h0A2.5 2.5 0 0 1 4 13.5z"/><path d="M8.5 9.5h.01M12 9.5h.01M15.5 9.5h.01"/>',
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

/* ---------- عکس پروفایل تلگرام ----------
   p: {name, av, pic, bot}. pic آدرس عکس است (photo_url تلگرام یا pic/<key> که سرور
   از ربات می گیرد). اگر عکس نبود یا باز نشد، حرف اول نام روی رنگ ثابت آن بازیکن. */
const FACE_BG = ['#8E7CF8', '#4DA8FF', '#FF7A85', '#3DD08E', '#FFA552', '#3FC7D9', '#F07CC4'];
const escAttr = v => String(v || '').replace(/[&"'<>]/g, ch => ({ '&': '&amp;', '"': '&quot;', "'": '&#39;', '<': '&lt;', '>': '&gt;' }[ch]));
function initial(name) { const m = String(name || '').trim().match(/[\p{L}\p{N}]/u); return m ? m[0] : '؟'; }
function face(p, ring, extra = '') {
  p = p || {};
  const seed = Math.abs(+p.av || 1);
  const base = p.bot ? avatar(seed) : `<span class="ini" style="background:${FACE_BG[seed % FACE_BG.length]}">${escAttr(initial(p.name))}</span>`;
  const img = p.pic && !p.bot ? `<img src="${escAttr(p.pic)}" alt="" loading="lazy" decoding="async" referrerpolicy="no-referrer" data-face>` : '';
  return `<span class="avatar ${extra}" style="--ring:${ring || 'var(--surface)'}"><span>${base}${img}</span></span>`;
}
// عکسی که باز نشد (پنهان، حذف شده، بدون اینترنت تلگرام) کنار می رود تا حرف اول دیده شود
document.addEventListener('error', e => { const t = e.target; if (t && t.tagName === 'IMG' && t.hasAttribute('data-face')) t.remove(); }, true);

/* ---------- مهره منچ ---------- */
const COL = {
  blue: { hex: '#4C8DFF', deep: '#2B62D6', fa: 'آبی' }, red: { hex: '#FF5A6A', deep: '#C93447', fa: 'قرمز' },
  green: { hex: '#2FC584', deep: '#1E8A5E', fa: 'سبز' }, yellow: { hex: '#FFC531', deep: '#C98A00', fa: 'زرد' },
};
/* مهره: دیسک گرد براق (بدون چشم). مرکز دیسک نزدیک ۸۲٪ ارتفاع است، همان نقطه ای
   که مهره روی خانه می نشیند؛ بالای آن جای تاج برنده است. */
function pawn(c, crown) {
  const { hex, deep } = COL[c];
  return `<svg viewBox="0 0 40 50" aria-hidden="true"><ellipse cx="20" cy="47" rx="13" ry="3" fill="rgba(0,0,0,.3)"/>
    <circle cx="20" cy="40" r="14" fill="${deep}"/><circle cx="20" cy="37" r="14" fill="${hex}" stroke="#fff" stroke-width="3"/>
    <circle cx="20" cy="37" r="7.5" fill="none" stroke="rgba(255,255,255,.55)" stroke-width="2.4"/>
    <ellipse cx="14.5" cy="31" rx="4.6" ry="3" fill="rgba(255,255,255,.5)" transform="rotate(-28 14.5 31)"/>
    ${crown ? '<path d="M8 21l4.5 4 7.5-11 7.5 11 4.5-4-1.5 7.5h-21z" fill="#FFC93C" stroke="#C98A00" stroke-width="1.4" stroke-linejoin="round"/>' : ''}</svg>`;
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
  n.innerHTML = `<div class="nav-in">${NAV.map(([id, href, label, ic]) => `<a href="${href}" aria-label="${label}"${id === active ? ' aria-current="page"' : ''}>${icon(ic)}<span class="sr">${label}</span></a>`).join('')}</div>`;
  document.body.appendChild(n);
}
function mount(root = document) {
  root.querySelectorAll('[data-ic]').forEach(el => { el.innerHTML = icon(el.dataset.ic); });
  root.querySelectorAll('[data-coin]').forEach(el => { el.innerHTML = COIN; el.classList.add('coin'); });
  root.querySelectorAll('[data-bal]').forEach(el => { el.textContent = points == null ? (live ? '…' : fa(S.bal)) : fa(points); });
}
document.addEventListener('click', e => { if (e.target.closest('.btn,.chip,.seg button,.choice,.nav a,.icon-btn')) { sfx.tap(); haptic('select'); } }, true);

/* ---------- آموزش بار اول منچ (قبل از نشستن سر میز، تا وقت نوبت نسوزد) ---------- */
function coach(me = 'yellow') {
  return new Promise(res => {
    const body = s => s.replace(/^<svg[^>]*>|<\/svg>$/g, '');
    const SL = [
      ['رنگ تو پایین چپ است', 'هر بازیکن صفحه را از سمت خودش می‌بیند. مهره‌هایت را دور صفحه ببر و به مرکز برسان.', `<svg viewBox="0 0 100 100"><rect x="6" y="6" width="88" height="88" rx="18" fill="${COL[me].hex}"/><rect x="22" y="22" width="56" height="56" rx="12" fill="#F4F2FA"/><g transform="translate(30 20)">${body(pawn(me))}</g></svg>`],
      ['روی تاس بزن', 'تاس پایین صفحه است. با ۶ یک مهره وارد بازی می‌شود و یک نوبت دیگر داری.', `<svg viewBox="0 0 100 100"><rect x="18" y="18" width="64" height="64" rx="16" fill="${COL[me].hex}"/><g fill="#fff"><circle cx="35" cy="35" r="6"/><circle cx="65" cy="35" r="6"/><circle cx="35" cy="50" r="6"/><circle cx="65" cy="50" r="6"/><circle cx="35" cy="65" r="6"/><circle cx="65" cy="65" r="6"/></g></svg>`],
      ['مهره را انتخاب کن', 'مهره‌ای که بالا و پایین می‌پرد قابل حرکت است. دایرهٔ خط‌چین نشان می‌دهد کجا می‌رود.', `<svg viewBox="0 0 100 100"><rect x="8" y="58" width="24" height="24" rx="6" fill="#F4F2FA" stroke="#CFC9E3" stroke-width="2"/><rect x="38" y="58" width="24" height="24" rx="6" fill="#F4F2FA" stroke="#CFC9E3" stroke-width="2"/><rect x="68" y="58" width="24" height="24" rx="6" fill="#F4F2FA" stroke="#CFC9E3" stroke-width="2"/><circle cx="80" cy="70" r="9" fill="rgba(255,255,255,.8)" stroke="${COL[me].hex}" stroke-width="3" stroke-dasharray="4 3"/><g transform="translate(6 18) scale(.7)">${body(pawn(me))}</g><path d="M34 40c14-12 34-12 44 14" fill="none" stroke="#1E2235" stroke-width="2.5" stroke-dasharray="4 4"/></svg>`],
    ];
    let i = 0;
    const draw = () => {
      const [t, d, svg] = SL[i];
      const sh = sheet(`<div class="coach"><div class="pic">${svg}</div><h2>${t}</h2><p class="muted">${d}</p><div class="dots">${SL.map((_, j) => `<i class="${j === i ? 'on' : ''}"></i>`).join('')}</div></div>
        <button class="btn btn-block" id="nx">${i < SL.length - 1 ? 'بعدی' : 'فهمیدم، شروع'}</button>
        <button class="btn btn-light btn-block" id="sk">رد کردن آموزش</button>`, { center: true, dismiss: false });
      const end = () => { S.tutorial = true; save(); GC.close(); res(); };
      sh.querySelector('#nx').onclick = () => { if (++i < SL.length) draw(); else end(); };
      sh.querySelector('#sk').onclick = end;
    };
    draw();
  });
}

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
  let g = '<rect x="-.5" y="-.5" width="16" height="16" rx="1.4" fill="#2B2540"/>';
  for (const c of L.ORDER) {
    const [x, y] = L.SEAT[c].yard;
    g += `<rect x="${x + .1}" y="${y + .1}" width="5.8" height="5.8" rx=".8" fill="${COL[c].hex}"/><rect x="${x + .95}" y="${y + .95}" width="4.1" height="4.1" rx=".8" fill="#F4F2FA"/>`;
    for (const [sx, sy] of L.SOCKETS) g += `<circle cx="${x + sx}" cy="${y + sy}" r=".55" fill="${COL[c].hex}"/>`;
  }
  L.TRACK.forEach(([x, y], i) => { const c = startOf[i]; g += `<rect x="${x + .07}" y="${y + .07}" width=".86" height=".86" rx=".2" fill="${c ? COL[c].hex : '#F4F2FA'}"/>`; });
  for (const c of L.ORDER) for (const [x, y] of L.SEAT[c].lane) g += `<rect x="${x + .07}" y="${y + .07}" width=".86" height=".86" rx=".2" fill="${COL[c].hex}"/>`;
  g += '<path d="M6 6L7.5 7.5L6 9z" fill="#4C8DFF"/><path d="M6 6L9 6L7.5 7.5z" fill="#FF5A6A"/><path d="M9 6L9 9L7.5 7.5z" fill="#2FC584"/><path d="M6 9L9 9L7.5 7.5z" fill="#FFC531"/>';
  return `<svg viewBox="-.5 -.5 16 16" aria-hidden="true">${g}</svg>`;
}
const RATE = 100; // هر امتیاز چند تومان (نمونه)
document.documentElement.lang = 'fa'; document.documentElement.dir = 'rtl';

window.GC = { coach, tg, live, back, haptic, guardClose, portrait, openLink, startParam, api, errText, idem, refreshMe,
  get data() { return live ? liveData : GC.demo.data; }, get ludo() { return live ? liveLudo : GC.demo.ludo; },
  get points() { return points == null ? S.bal : points; }, set points(v) { points = v; mount(); },
  PEOPLE, LB, SHOP, RATE, LUDO, boardArt, FD, fa, rand, sleep, store, S, save, ledger, icon, COIN, coin, amount, avatar, avatarEl, face, initial, COL, pawn, pips, toast, sheet, close, sheetHead, sfx, setSound, nav, mount };
document.addEventListener('DOMContentLoaded', () => mount());
})();
