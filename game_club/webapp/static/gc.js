/* AsoTas — ابزار مشترک همه صفحه ها.
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
  bal: 120, wins: 0, games: 0, mode: 'free', notify: {}, sound: true, tutorial: false,
  ledger: [{ t: 'هدیهٔ شروع از طرف تاسی 🎁', a: 120, k: 'gift', at: Date.now() - 864e5 }],
}, store.get('state', {}));
const save = () => store.set('state', S);
function ledger(t, a, k) { S.ledger.unshift({ t, a, k, at: Date.now() }); S.ledger = S.ledger.slice(0, 40); }

/* ---------- SDK مینی اپ تلگرام ----------
   داخل تلگرام: initData هست، همه چیز از سرور. بیرون (مرورگر، پیش نمایش):
   حالت نمایشی با demo.js. قواعد تمام صفحه: محتوا زیر نوار وضعیت گوشی
   (safeAreaInset) و دکمه های شناور تلگرام (contentSafeAreaInset) نمی رود. */
const tg = (window.Telegram && window.Telegram.WebApp) || null;
// داخل تلگرام (initData) یا داخل برنامهٔ اندروید (static/app.js، حساب مهمان)؛ هر دو یعنی همه چیز از سرور
const APP = window.GCApp || null;
const tgLive = !!(tg && tg.initData);
const live = tgLive || !!APP;
const root = document.documentElement;
root.classList.toggle('tg', tgLive);
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
// رنگ نوار تلگرام با زمینه صفحه یکی است تا درز دیده نشود: صفحهٔ خود بازی ها سبز تیره، بقیه پوستهٔ اپ
// (روشن یا تیره؛ theme.js). با عوض شدن پوسته دوباره رنگ می شود.
function paintBars() {
  const game = document.body.matches('.game,.hokm,.divar,.football,.billiard,.snakes'), night = document.documentElement.dataset.theme === 'dark';
  const paper = document.body.matches('.esm');   // اسم‌فامیل: برگ دفتر، همیشه روشن
  const desk = document.body.matches('.lashgar');   // لشگر کاغذی: میز چوبی مدرسه
  const top = desk ? '#8E5F38' : paper ? '#EFE6D2' : game ? '#0C1915' : night ? '#0F1218' : '#F4F5F8';
  const bottom = desk ? '#7E5230' : paper ? '#FFFCF2' : game ? '#08120F' : night ? '#181C24' : '#FFFFFF';
  if (APP) { APP.bars(top); return; }
  try { tg.setHeaderColor(top); tg.setBackgroundColor(top); } catch (e) {}
  try { ver('7.10') && tg.setBottomBarColor(bottom); } catch (e) {}
}
if (APP) {
  paintBars();
  addEventListener('pageshow', e => { if (e.persisted) paintBars(); });
  addEventListener('gc-theme', paintBars);
}
if (tgLive) {
  try { tg.ready(); tg.expand(); } catch (e) {}
  paintBars();
  // برگشت از حافظهٔ مرورگر (bfcache) اسکریپت را دوباره اجرا نمی کند؛ رنگ صفحه ای که برگشته از نو
  addEventListener('pageshow', e => { if (e.persisted) paintBars(); });
  addEventListener('gc-theme', paintBars);
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
/* ---------- ارتفاع پایدار صفحهٔ بازی ----------
   باز شدن کیبورد (نوشتن در گفتگو) صفحه را کوتاه می کند. اگر بازی با آن دوباره چیده شود، میز می پرد و
   بوم ها از نو کشیده می شوند (کند و پر لرزش). صفحهٔ بازی ارتفاعش را از --app-h می گیرد که هنگام نوشتن
   ثابت می ماند (کیبورد روی بازی می آید و نوار گفتگو بالای آن)؛ GC.onFit کار چیدن هر بازی را فقط وقتی
   اندازهٔ واقعی صفحه عوض شد و یک بار در هر فریم صدا می زند. بعد از بستن کیبورد صفحهٔ بازی به بالا
   برمی گردد (آیفون گاهی جابه جا رهایش می کند). */
const editing = () => { const a = document.activeElement; return !!a && (a.tagName === 'INPUT' || a.tagName === 'TEXTAREA' || a.isContentEditable); };
const gameBody = () => !!document.body && document.body.matches('.game,.hokm,.divar,.football,.billiard,.lashgar,.snakes');
let appW = 0, appH = 0, fitRaf = 0, fitForce = false;
const fits = [];
function syncApp() {
  fitRaf = 0;
  const w = innerWidth, h = innerHeight, force = fitForce; fitForce = false;
  if (appH && editing() && w === appW) return;            // کیبورد باز است: چیدمان همان بماند
  if (w === appW && h === appH && !force) return;
  appW = w; appH = h;
  root.style.setProperty('--app-h', h + 'px');
  root.classList.toggle('h700', h <= 700); root.classList.toggle('h640', h <= 640);   // چیدمان فشرده تر صفحه های کوتاه
  for (const fn of fits) { try { fn(); } catch (e) {} }
}
function queueFit(force) { if (force === true) fitForce = true; if (!fitRaf) fitRaf = requestAnimationFrame(syncApp); }
syncApp();
addEventListener('resize', queueFit);
document.addEventListener('focusout', () => setTimeout(() => {
  if (editing()) return;
  if (gameBody() && (scrollX || scrollY)) scrollTo(0, 0);
  queueFit();
}, 80));
if (tg) ['viewportChanged', 'fullscreenChanged', 'safeAreaChanged', 'contentSafeAreaChanged'].forEach(ev => { try { tg.onEvent(ev, () => queueFit(true)); } catch (e) {} });
const onFit = fn => { fits.push(fn); };
const appHeight = () => appH || innerHeight;

// فایل های بازی روی گوشی می مانند (sw.js)؛ بعد از بار شدن صفحه تا با خود صفحه رقابت نکند
// داخل برنامهٔ اندروید فایل ها خودشان روی گوشی اند (و آپدیتشان با static/app.js است)
if (!APP && 'serviceWorker' in navigator && window.isSecureContext && location.protocol !== 'file:') {
  addEventListener('load', () => { navigator.serviceWorker.register('sw.js', { updateViaCache: 'none' }).catch(() => {}); });
}
/* دکمه برگشت بومی تلگرام؛ دکمه برگشت داخل صفحه فقط بیرون از تلگرام دیده می شود.
   هر بار فقط یک کار به دکمه وصل است (کار قبلی جدا می شود)؛ برگشت به یکی از چهار بخش اصلی
   صفحه را دوباره بار نمی کند (پایین: «بخش های اصلی») */
let backFn = null;
function back(href) {
  if (mountingView) { views[mountingView].back = href; return; }
  if (curView && views[curView]) views[curView].back = href;
  applyBack(href);
}
function applyBack(href) {
  if (!tgLive || !ver('6.1')) return;
  try {
    if (backFn) { tg.BackButton.offClick(backFn); backFn = null; }
    if (!href) { tg.BackButton.hide(); return; }
    backFn = () => { typeof href === 'function' ? href() : go(href); };
    tg.BackButton.onClick(backFn); tg.BackButton.show();
  } catch (e) {}
}
function haptic(kind) {
  if (!tgLive || !ver('6.1')) return;
  try {
    const H = tg.HapticFeedback;
    if (['success', 'error', 'warning'].includes(kind)) H.notificationOccurred(kind);
    else if (kind === 'select') H.selectionChanged();
    else H.impactOccurred(kind || 'light');
  } catch (e) {}
}
function guardClose(on) { if (!tgLive || !ver('6.2')) return; try { on ? tg.enableClosingConfirmation() : tg.disableClosingConfirmation(); } catch (e) {} }
function portrait(on) { if (!tgLive || !ver('8.0')) return; try { on ? tg.lockOrientation() : tg.unlockOrientation(); } catch (e) {} }
function openLink(url) {
  if (tgLive && /^https:\/\/t\.me\//.test(url)) { try { tg.openTelegramLink(url); return; } catch (e) {} }
  if (tgLive) { try { tg.openLink(url); return; } catch (e) {} }
  window.open(url, '_blank', 'noopener');   // داخل برنامه: مرورگر یا خود تلگرام گوشی باز می شود
}
function startParam() { try { return (tg && tg.initDataUnsafe && tg.initDataUnsafe.start_param) || ''; } catch (e) { return ''; } }

/* ---------- API سرور ---------- */
const ERR = {
  not_owned: 'اول این طرحو بخر',
  name_short: 'یوزرنیم حداقل ۳ تا حرف باشه', name_long: 'یوزرنیم حداکثر ۱۶ تا حرفه', name_start: 'یوزرنیم باید با حرف انگلیسی شروع بشه',
  not_friends: 'اول باید با هم رفیق بشید', you_blocked: 'این بنده خدا رو بلاک کردی', cant_add: 'این یکی رو نمی‌شه اضافه کرد',
  too_many_friends: 'لیست رفیقات پر شده', slow_requests: 'درخواستا زیاد شد یه کم دیگه دوباره امتحان کن', no_request: 'این درخواست دیگه نیست', bad_game: 'این بازی پیدا نشد',
  name_chars: 'فقط حرف انگلیسی و عدد و _ قبوله', name_reserved: 'این یوزرنیمو نمی‌شه برداشت', name_taken: 'این یوزرنیمو یکی دیگه زودتر برداشته',
  must_join: 'اول عضو کانالای AsoTas شو بعد بزن بریم!',
  banned: 'شرمنده حسابت تو AsoTas بسته شده', maintenance: 'داریم آپدیت می‌کنیم چند دقیقه دیگه دوباره سر بزن',
  insufficient: 'سکه‌ت کمه با جایزهٔ روزانه و برد رتبه‌ای جمعش کن', daily_done: 'جایزهٔ امروزتو گرفتی فردا دوباره سر بزن 😉',
  ranked_off: 'بازی رتبه‌ای فعلاً خاموشه', ranked_online: 'رتبه‌ای فقط با حریف آنلاینه',
  busy: 'یه لحظه دیگه دوباره امتحان کن',
  bad_invite: 'این لینک دعوت به درد نمی‌خوره', started: 'این میز بازیش شروع شده', full: 'این میز پره', in_match: 'تو الان سر یه میز دیگه‌ای',
  need_players: 'هنوز به اندازهٔ کافی بازیکن سر میز نیست', not_host: 'فقط سازندهٔ میز می‌تونه شروعش کنه',
  group_only: 'این بازی فقط توی گروه یا کانال ساخته می‌شه', sheet_not_full: 'واسه استپ باید همهٔ خونه‌ها پر باشه ✍️', closed: 'دیر شد وقتش تموم شده',
  submitted: 'برگتو که تحویل دادی 😄', no_appeal: 'به این خونه نمی‌شه اعتراض کرد', appealed: 'سر این یکی قبلا اعتراض کردی',
  no_vote: 'رو اعتراض خودت که نمی‌تونی رأی بدی 😄', not_playing: 'تو این بازی نیستی', bad_sheet: 'برگت درست ثبت نشد یه بار دیگه بزن',
  army_short: 'اسم لشگر دست‌کم ۲ حرف باشه', army_long: 'اسم لشگر حداکثر ۲۰ حرفه', army_chars: 'فقط حرف و عدد و فاصله بدون لینک و @',
  army_bad: 'این اسمو نمی‌شه گذاشت یه اسم دیگه بذار 😅', army_taken: 'حریفت همین اسمو برداشته یه اسم دیگه بذار', need_army: 'اول یه اسم برای لشگرت بذار',
  need_units: 'اول همهٔ نیروهاتو بچین', bad_units: 'جای نیروها درست ثبت نشد یه بار دیگه بچین', too_many: 'از این نیرو دیگه نداری',
  unit_out: 'نیرو باید کامل روی برگه باشه', unit_overlap: 'نیروها نباید روی هم بیفتن', not_draw: 'وقت چیدن تموم شده', is_ready: 'آماده رو زدی اول «عوضش کنم» رو بزن',
  not_battle: 'هنوز جنگ شروع نشده', bad_ink: 'خط مداد ثبت نشد دوباره بکش', ink_full: 'برگه دیگه جا نداره یه کم پاک کن',
  plan_unavailable: 'این پلن الان فروخته نمی‌شه', auth: 'نشستت تموم شده ببندش و دوباره باز کن',
  rate: 'یواش‌تر چند ثانیه صبر کن', network: 'وصل نشد اینترنتتو یه نگاه بنداز', server: 'سرور یه لحظه گیج زد دوباره امتحان کن',
  not_your_turn: 'صبر کن الان نوبت تو نیست', empty: 'اول یه چیزی بنویس', chat_slow: 'یواش‌تر چند ثانیه صبر کن', illegal_move: 'این مهره نمی‌تونه تکون بخوره', no_walls: 'دیواراتو تموم کردی فقط می‌تونی راه بری', wall_taken: 'اینجا دیوار نمی‌شه گذاشت می‌افته رو یه دیوار دیگه', wall_blocks: 'این دیوار راه یکی رو کامل می‌بنده و قبول نیست', bad_wall: 'جای دیوار درست نیست', illegal_card: 'این برگو نمی‌شه بازی کرد باید از همون خالی که اومده بیاری', not_play_phase: 'یه لحظه صبر کن', not_trump_phase: 'یه لحظه صبر کن', bad_suit: 'یه خال انتخاب کن', not_ready: 'یه لحظه صبر کن مهره‌ها وایسن', bad_shot: 'شوت درست ثبت نشد دوباره بزن', bad_setup: 'یه تیم و یه چیدمان انتخاب کن', not_setup: 'بازی شروع شده', not_found: 'این میز پیدا نشد', bad_place: 'توپ سفیدو یه جای خالی بذار و تو بریک پشت خط سر', bad_pack: 'این بسته فعلاً نیست',
};
const errText = e => {
  const c = String((e && e.code) || '');
  if (c.startsWith('name_wait:')) return `یوزرنیمو ${FD(c.split(':')[1])} روز دیگه می‌تونی عوض کنی`;
  return ERR[c] || ERR.server;
};
async function api(name, { body, q } = {}, again) {
  let r;
  try {
    // داخل برنامه: صفحه ها روی گوشی اند و API روی سرور؛ به جای initData توکن نشست مهمان می رود
    const auth = APP ? { 'X-GC-Token': await APP.token() } : { 'X-Init-Data': tg ? tg.initData : '' };
    r = await fetch((APP ? APP.base : '') + 'api/' + name + (q ? '?' + new URLSearchParams(q) : ''), {
      method: body ? 'POST' : 'GET', cache: 'no-store',
      headers: Object.assign(auth, { 'Content-Type': 'application/json' }),
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch (e) { const x = new Error((e && e.code) || 'network'); x.code = (e && e.code) || 'network'; throw x; }
  // توکن برنامه دیگر کار نمی کند (مثلا نشست بسته شده): یک حساب مهمان تازه و همان درخواست یک بار دیگر
  if (APP && r.status === 401 && !again) { await APP.token(true); return api(name, { body, q }, true); }
  let j = {}; try { j = await r.json(); } catch (e) {}
  if (!r.ok) {
    const x = new Error(j.error || 'server'); x.code = j.error || 'server'; x.data = j;
    if (x.code === 'must_join' && j.chats) showGate(j.chats);   // عضویت اجباری: صفحهٔ «عضو شو»
    throw x;
  }
  return j;
}

/* ---------- عضویت اجباری و پیام پاپ آپ (هر دو از پنل مدیریت؛ با باز شدن هر صفحه یک بار پرسیده می شود) ---------- */
const BOOT_CSS = `
.gk-scrim{position:fixed;inset:0;z-index:9500;background:rgba(10,12,22,.62);display:flex;align-items:center;justify-content:center;padding:20px;
  font-family:var(--font-peyda,inherit);direction:rtl;animation:gk-in .25s ease;-webkit-tap-highlight-color:transparent}
@keyframes gk-in{from{opacity:0}}
.gk-card{position:relative;width:min(380px,100%);max-height:calc(100% - 20px);overflow:auto;background:#fff;color:#1C2235;border-radius:24px;
  box-shadow:0 22px 60px rgba(0,0,0,.45);animation:gk-pop .35s cubic-bezier(.3,1.4,.5,1)}
@keyframes gk-pop{from{transform:translateY(16px) scale(.94);opacity:0}}
.gk-img{display:block;width:100%;max-height:52vh;object-fit:cover;border-radius:24px 24px 0 0;background:#EEF0F5}
.gk-body{padding:18px 18px 16px;display:flex;flex-direction:column;gap:10px}
.gk-body h2{margin:0;font-family:var(--font-rokh,inherit);font-weight:900;font-size:21px;line-height:29px}
.gk-body p{margin:0;font-size:14px;line-height:24px;color:#424862;white-space:pre-line;overflow-wrap:anywhere}
.gk-x{position:absolute;top:10px;left:10px;width:36px;height:36px;border-radius:50%;border:0;background:rgba(0,0,0,.45);color:#fff;font-size:18px;
  display:grid;place-items:center;cursor:pointer;backdrop-filter:blur(4px)}
.gk-x.plain{background:#F1F2F7;color:#424862}
.gk-btn{height:48px;border:0;border-radius:16px;font:inherit;font-weight:900;font-size:16px;cursor:pointer;display:flex;align-items:center;justify-content:center;gap:8px;
  background:#1668D9;color:#fff;box-shadow:0 4px 0 #0F4FAA;text-decoration:none}
.gk-btn:active{transform:translateY(3px);box-shadow:none}
.gk-btn svg{width:22px;height:22px;flex:none}
.gk-btn.ok{background:#1A9A4A;box-shadow:0 4px 0 #11733A}
.gk-btn[disabled]{opacity:.6}
.gk-link{border:0;background:none;font:inherit;font-weight:800;font-size:14px;color:#5B6178;height:38px;cursor:pointer}
.gk-ic{width:64px;height:64px;margin:4px auto 2px;border-radius:20px;background:#E8F0FF;color:#1668D9;display:grid;place-items:center}
.gk-ic svg{width:34px;height:34px}
.gk-head{text-align:center}
.gk-list{display:flex;flex-direction:column;gap:8px;margin:2px 0 4px}
.gk-row{display:flex;align-items:center;gap:10px;padding:10px 12px;border-radius:16px;background:#F4F6FA}
.gk-row .t{flex:1;min-width:0;display:flex;flex-direction:column}
.gk-row b{font-size:14.5px;font-weight:900;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.gk-row small{font-size:12px;color:#6A7088}
.gk-row .av{width:40px;height:40px;flex:none;border-radius:50%;display:grid;place-items:center;background:#1668D9;color:#fff;font-size:18px}
.gk-row .go{height:36px;padding:0 14px;border:0;border-radius:12px;background:#1668D9;color:#fff;font:inherit;font-weight:900;font-size:13.5px;cursor:pointer}
.gk-row.done .go{background:#E3F4EA;color:#1A9A4A}
.gk-err{margin:0;text-align:center;font-size:13px;font-weight:800;color:#C62828;min-height:18px}
.gk-shake{animation:gk-shake .4s}
@keyframes gk-shake{25%{transform:translateX(-8px)}50%{transform:translateX(8px)}75%{transform:translateX(-4px)}}
@media (prefers-reduced-motion:reduce){.gk-scrim,.gk-card,.gk-shake{animation:none}}`;
const escB = t => String(t == null ? '' : t).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
let gateEl = null, bootDone = null;
function bootCss() { if (!document.getElementById('gkCss')) { const st = document.createElement('style'); st.id = 'gkCss'; st.textContent = BOOT_CSS; document.head.appendChild(st); } }
function showGate(chats) {
  bootCss();
  if (!chats || !chats.length) { if (gateEl) { gateEl.remove(); gateEl = null; } return; }
  if (!gateEl) { gateEl = document.createElement('div'); gateEl.className = 'gk-scrim'; gateEl.setAttribute('role', 'dialog'); gateEl.setAttribute('aria-modal', 'true'); gateEl.setAttribute('aria-labelledby', 'gkT'); document.body.appendChild(gateEl); }
  const clicked = new Set(JSON.parse(sessionStorage.getItem('gc_gate_clicked') || '[]'));
  const many = chats.length > 1;
  gateEl.innerHTML = `<div class="gk-card"><div class="gk-body">
    <div class="gk-head"><div class="gk-ic">${icon('bell', 2)}</div><h2 id="gkT">یه قدم تا بازی!</h2>
      <p>واسه بازی تو AsoTas باید عضو ${many ? 'این کانال‌ها و گروه‌ها' : 'این ' + (chats[0].kind === 'group' ? 'گروه' : 'کانال')} باشی عضو که شدی «عضو شدم» رو بزن</p></div>
    <div class="gk-list">${chats.map((c, i) => `<div class="gk-row${clicked.has(c.url) ? ' done' : ''}"><span class="av">${c.kind === 'group' ? '👥' : '📢'}</span>
      <span class="t"><b>${escB(c.title)}</b><small>${c.kind === 'group' ? 'گروه' : 'کانال'}</small></span>
      <button class="go" data-i="${i}">${clicked.has(c.url) ? 'باز کن' : 'عضو شو'}</button></div>`).join('')}</div>
    <p class="gk-err" id="gkErr" role="alert"></p>
    <button class="gk-btn ok" id="gkOk">${icon('check', 2.6)}عضو شدم</button></div></div>`;
  gateEl.querySelectorAll('.go').forEach(b => b.onclick = () => {
    const c = chats[+b.dataset.i]; clicked.add(c.url);
    try { sessionStorage.setItem('gc_gate_clicked', JSON.stringify([...clicked])); } catch (e) {}
    b.closest('.gk-row').classList.add('done'); b.textContent = 'باز کن'; haptic('light');
    if (c.url) openLink(c.url);
  });
  const ok = gateEl.querySelector('#gkOk');
  ok.onclick = async () => {
    ok.disabled = true; sfx.tap();
    try {
      const r = await api('gate/check', { body: {} });
      if (!r.gate.length) { gateEl.remove(); gateEl = null; haptic('success'); toast('دمت گرم عضو شدی بزن بریم سراغ بازی! 🎮'); showPopup(); return; }
      showGate(r.gate);
      const err = gateEl.querySelector('#gkErr'); err.textContent = `هنوز عضو ${r.gate.map(c => '«' + c.title + '»').join(' و ')} نشدی رفیق`;
      const card = gateEl.querySelector('.gk-card'); card.classList.remove('gk-shake'); void card.offsetWidth; card.classList.add('gk-shake'); haptic('error');
    } catch (e) { ok.disabled = false; toast(errText(e)); }
  };
}
let popupData = null;
function showPopup() {
  const p = popupData; popupData = null;
  if (!p || gateEl) return;
  // صفحهٔ بازی وسط بازی شلوغ نمی شود؛ فقط خانه، لابی ها و بقیهٔ صفحه ها
  if (/(ludo|hokm|football|billiard|divar|esmfamil|lashgar|snakes)\.html$|admin\.html$/.test(location.pathname)) return;
  const key = 'gc_popup_' + p.v;
  try {
    if (sessionStorage.getItem(key)) return;
    if (p.mode !== 'always' && localStorage.getItem(key)) return;
    sessionStorage.setItem(key, '1'); localStorage.setItem(key, '1');
  } catch (e) {}
  bootCss();
  const el = document.createElement('div'); el.className = 'gk-scrim'; el.setAttribute('role', 'dialog'); el.setAttribute('aria-modal', 'true');
  if (p.title) el.setAttribute('aria-label', p.title);
  el.innerHTML = `<div class="gk-card">${p.img ? `<img class="gk-img" src="${escB(APP ? APP.srv(p.img) : p.img)}" alt="">` : ''}
    <button class="gk-x${p.img ? '' : ' plain'}" aria-label="بستن">✕</button>
    <div class="gk-body">${p.title ? `<h2>${escB(p.title)}</h2>` : ''}${p.text ? `<p>${escB(p.text)}</p>` : ''}
      ${p.btn && p.url ? `<button class="gk-btn" id="gkGo">${escB(p.btn)}</button>` : ''}
      <button class="gk-link" id="gkClose">بستن</button></div></div>`;
  document.body.appendChild(el);
  const close = () => { el.remove(); };
  el.querySelector('.gk-x').onclick = close; el.querySelector('#gkClose').onclick = close;
  el.addEventListener('click', e => { if (e.target === el) close(); });
  const go = el.querySelector('#gkGo'); if (go) go.onclick = () => { haptic('light'); openLink(p.url); close(); };
}
async function boot() {
  if (!live || /admin\.html$/.test(location.pathname)) return;
  try {
    const r = await api('boot');
    popupData = r.popup || null;
    if (r.gate && r.gate.length) showGate(r.gate); else showPopup();
  } catch (e) {}
}
const idem = () => Date.now().toString(36) + Math.random().toString(36).slice(2, 10);
const liveData = {
  me: () => api('me'),
  daily: () => api('daily', { body: {} }),
  notify: game => api('notify', { body: { game } }),
  setFlag: (f, v) => api('settings', { body: { [f]: v ? 1 : 0 } }),
  leaderboard: (kind, period) => api('leaderboard', { q: { kind, period } }),
  gameBoard: (game, period) => api('leaderboard', { q: { game, period } }),
  style: () => api('style'),
  styleBuy: id => api('style/buy', { body: { id, idem: idem() } }),
  styleUse: id => api('style/use', { body: { id } }),
  profile: () => api('profile'),
  nameCheck: n => api('name/check', { q: { n } }),
  setName: name => api('name', { body: { name } }),
  nameSeen: () => api('name/seen', { body: {} }),
  saveProfile: body => api('settings', { body }),
  friends: () => api('friends'),
  friendFind: n => api('friends/find', { q: { n } }),
  friendUser: u => api('friends/user', { q: { u } }),
  friendReq: uid => api('friends/request', { body: { uid } }),
  friendAccept: uid => api('friends/accept', { body: { uid } }),
  friendDrop: uid => api('friends/drop', { body: { uid } }),
  friendBlock: (uid, on) => api('friends/block', { body: { uid, on } }),
  dm: (u, since = 0) => api('dm', { q: { u, since } }),
  dmSend: (uid, text) => api('dm', { body: { uid, text } }),
  dmInvite: (uid, game) => api('dm/invite', { body: { uid, game } }),
  groupShare: game => api('group/share', { body: { game } }),
};
const liveLudo = {
  queueJoin: cfg => api('ludo/queue', { body: { cfg } }),
  queueStatus: () => api('ludo/queue'),
  queueLeave: () => api('ludo/queue/leave', { body: {} }),
  queueBots: () => api('ludo/queue/bots', { body: {} }),
  invite: cfg => api('ludo/invite', { body: { cfg } }),
  join: code => api('ludo/join', { body: { code } }),
  start: match => api('ludo/start', { body: { match } }),
  match: (id, since = 0, chat = null) => api('ludo/match', { q: Object.assign(id ? { id, since } : { since }, chat == null ? {} : { chat }) }),
  chat: (match, text) => api('ludo/chat', { body: { match, text } }),
  roll: (match, since) => api('ludo/roll', { body: { match, since } }),
  move: (match, k, since) => api('ludo/move', { body: { match, k, since } }),
  leave: match => api('ludo/leave', { body: { match } }),
};
const liveFootball = {
  queueJoin: cfg => api('football/queue', { body: { cfg } }),
  queueStatus: () => api('football/queue'),
  queueLeave: () => api('football/queue/leave', { body: {} }),
  queueBots: () => api('football/queue/bots', { body: {} }),
  invite: cfg => api('football/invite', { body: { cfg } }),
  join: code => api('football/join', { body: { code } }),
  start: match => api('football/start', { body: { match } }),
  match: (id, since = 0, chat = null) => api('football/match', { q: Object.assign(id ? { id, since } : { since }, chat == null ? {} : { chat }) }),
  chat: (match, text) => api('football/chat', { body: { match, text } }),
  setup: (match, team, fa, fd, since) => api('football/setup', { body: { match, team, fa, fd, since } }),
  shot: (match, i, dx, dy, p, since) => api('football/shot', { body: { match, i, dx, dy, p, since } }),
  leave: match => api('football/leave', { body: { match } }),
};
const liveBilliard = {
  queueJoin: cfg => api('billiard/queue', { body: { cfg } }),
  queueStatus: () => api('billiard/queue'),
  queueLeave: () => api('billiard/queue/leave', { body: {} }),
  queueBots: () => api('billiard/queue/bots', { body: {} }),
  invite: cfg => api('billiard/invite', { body: { cfg } }),
  join: code => api('billiard/join', { body: { code } }),
  start: match => api('billiard/start', { body: { match } }),
  match: (id, since = 0, chat = null) => api('billiard/match', { q: Object.assign(id ? { id, since } : { since }, chat == null ? {} : { chat }) }),
  chat: (match, text) => api('billiard/chat', { body: { match, text } }),
  // a زاویه (رادیان، مختصات میز)، p قدرت ۰ تا ۱، sx/sy پیچ، cx/cy جای توپ سفید وقتی توپ در دست است
  shot: (match, a, p, sx, sy, cx, cy, since) => api('billiard/shot', { body: Object.assign({ match, a, p, sx, sy, since }, cx == null ? {} : { cx, cy }) }),
  // نشانه گیری زنده برای دیدن بقیه (چرخش چوب، قدرت، جای توپ در دست) — پاسخ فقط {ok}
  aim: (match, a, p, cx, cy) => api('billiard/aim', { body: Object.assign({ match, a, p }, cx == null ? {} : { cx, cy }) }),
  leave: match => api('billiard/leave', { body: { match } }),
};
const liveDivar = {
  queueJoin: cfg => api('divar/queue', { body: { cfg } }),
  queueStatus: () => api('divar/queue'),
  queueLeave: () => api('divar/queue/leave', { body: {} }),
  queueBots: () => api('divar/queue/bots', { body: {} }),
  invite: cfg => api('divar/invite', { body: { cfg } }),
  join: code => api('divar/join', { body: { code } }),
  start: match => api('divar/start', { body: { match } }),
  match: (id, since = 0, chat = null) => api('divar/match', { q: Object.assign(id ? { id, since } : { since }, chat == null ? {} : { chat }) }),
  chat: (match, text) => api('divar/chat', { body: { match, text } }),
  move: (match, r, c, since) => api('divar/move', { body: { match, r, c, since } }),
  // o: "h" افقی یا "v" عمودی؛ r و c گوشهٔ بالا چپ دیوار دو خانه ای
  wall: (match, o, r, c, since) => api('divar/wall', { body: { match, o, r, c, since } }),
  leave: match => api('divar/leave', { body: { match } }),
};
const liveSnakes = {
  queueJoin: cfg => api('snakes/queue', { body: { cfg } }),
  queueStatus: () => api('snakes/queue'),
  queueLeave: () => api('snakes/queue/leave', { body: {} }),
  queueBots: () => api('snakes/queue/bots', { body: {} }),
  invite: cfg => api('snakes/invite', { body: { cfg } }),
  join: code => api('snakes/join', { body: { code } }),
  start: match => api('snakes/start', { body: { match } }),
  match: (id, since = 0, chat = null) => api('snakes/match', { q: Object.assign(id ? { id, since } : { since }, chat == null ? {} : { chat }) }),
  chat: (match, text) => api('snakes/chat', { body: { match, text } }),
  roll: (match, since) => api('snakes/roll', { body: { match, since } }),
  leave: match => api('snakes/leave', { body: { match } }),
};
// اسم‌فامیل فقط از کارت گروه ساخته می شود: اینجا نشستن (کد میز)، بازی و ترک است، نه صف و دعوت
const liveEsm = {
  join: code => api('esmfamil/join', { body: { code } }),
  start: match => api('esmfamil/start', { body: { match } }),
  match: (id, since = 0) => api('esmfamil/match', { q: id ? { id, since } : { since } }),
  // sheet: {ستون: جواب}؛ ذخیرهٔ خودکار هنگام نوشتن (پاسخ سبک {ok})
  answer: (match, sheet) => api('esmfamil/answer', { body: { match, sheet } }),
  stop: (match, sheet, since) => api('esmfamil/stop', { body: { match, sheet, since } }),
  submit: (match, sheet, since) => api('esmfamil/submit', { body: { match, sheet, since } }),
  appeal: (match, col, since) => api('esmfamil/appeal', { body: { match, col, since } }),
  vote: (match, key, yes, since) => api('esmfamil/vote', { body: { match, key, yes, since } }),
  ready: (match, since) => api('esmfamil/ready', { body: { match, since } }),
  leave: match => api('esmfamil/leave', { body: { match } }),
};
// لشگر کاغذی هم فقط از کارت گروه ساخته می شود: نشستن با کد، بازی، نقاشی (ink جدا) و ترک
const liveLashgar = {
  join: code => api('lashgar/join', { body: { code } }),
  match: (id, since = 0, chat = null) => api('lashgar/match', { q: Object.assign(id ? { id, since } : { since }, chat == null ? {} : { chat }) }),
  chat: (match, text) => api('lashgar/chat', { body: { match, text } }),
  army: (match, name, since) => api('lashgar/army', { body: { match, name, since } }),
  // units: [{k, x, y, r}] نیمهٔ خودم؛ پاسخ سبک {ok}
  units: (match, units) => api('lashgar/units', { body: { match, units } }),
  ready: (match, since) => api('lashgar/ready', { body: { match, since } }),
  unready: (match, since) => api('lashgar/unready', { body: { match, since } }),
  // x و y نقطه روی نیمهٔ خودم، a کجی کشیدن انگشت هنگام تا کردن (درجه)
  shoot: (match, x, y, a, since) => api('lashgar/shoot', { body: { match, x, y, a, since } }),
  // ops: [{op:'s', s:{c, w, e, p}} | {op:'u'} | {op:'c'}]
  ink: (match, ops) => api('lashgar/ink', { body: { match, ops } }),
  inkGet: (match, since, snap) => api('lashgar/ink', { q: { match, since, snap: snap ? 1 : 0 } }),
  leave: match => api('lashgar/leave', { body: { match } }),
};
const liveHokm = {
  queueJoin: cfg => api('hokm/queue', { body: { cfg } }),
  queueStatus: () => api('hokm/queue'),
  queueLeave: () => api('hokm/queue/leave', { body: {} }),
  queueBots: () => api('hokm/queue/bots', { body: {} }),
  invite: cfg => api('hokm/invite', { body: { cfg } }),
  join: code => api('hokm/join', { body: { code } }),
  start: match => api('hokm/start', { body: { match } }),
  match: (id, since = 0, chat = null) => api('hokm/match', { q: Object.assign(id ? { id, since } : { since }, chat == null ? {} : { chat }) }),
  chat: (match, text) => api('hokm/chat', { body: { match, text } }),
  trump: (match, k, since) => api('hokm/trump', { body: { match, k, since } }),
  play: (match, k, since) => api('hokm/play', { body: { match, k, since } }),
  leave: match => api('hokm/leave', { body: { match } }),
};
/* موجودی که سربرگ ها نشان می دهند */
let points = null;
async function refreshMe() {
  const me = await GC.data.me();
  points = me.player.points;
  if (me.social) setNavBadge(me.social);
  mount();
  return me;
}

/* ---------- آیکون ها (خطی، ۲۴×۲۴، currentColor) ---------- */
const P = {
  eye: '<path d="M2 12s3.6-6.5 10-6.5S22 12 22 12s-3.6 6.5-10 6.5S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
  home: '<path d="M3 11l9-7 9 7v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z"/>',
  trophy: '<path d="M8 4h8v5a4 4 0 0 1-8 0zM8 6H4.5v1.5A3.5 3.5 0 0 0 8 11M16 6h3.5v1.5A3.5 3.5 0 0 1 16 11M12 13v4M8 20h8M9.5 17h5"/>',
  wallet: '<path d="M4 7.5A2.5 2.5 0 0 1 6.5 5H18v3"/><rect x="4" y="8" width="16" height="11" rx="2.5"/><path d="M16 13.5h.01"/>',
  bag: '<path d="M4.5 8h15l-1.3 11.2a2 2 0 0 1-2 1.8H7.8a2 2 0 0 1-2-1.8z"/><path d="M9 8V6.5a3 3 0 0 1 6 0V8"/>',
  gift: '<rect x="3.5" y="8" width="17" height="4" rx="1"/><path d="M5 12v7a1.5 1.5 0 0 0 1.5 1.5h11A1.5 1.5 0 0 0 19 19v-7M12 8v12.5"/><path d="M12 8C10.5 4.5 7 4 6.6 6.1 6.3 7.7 8.6 8 12 8zM12 8c1.5-3.5 5-4 5.4-1.9.3 1.6-2 1.9-5.4 1.9z"/>',
  help: '<circle cx="12" cy="12" r="9"/><path d="M9.6 9.3a2.5 2.5 0 0 1 4.8.9c0 1.7-2.4 2.2-2.4 3.8M12 17h.01"/>',
  back: '<path d="M9 5l7 7-7 7"/>',
  fwd: '<path d="M15 5l-7 7 7 7"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 7.5h.01"/>',
  close: '<path d="M6 6l12 12M18 6L6 18"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  soundOn: '<path d="M4 9.5h3.5L12 6v12l-4.5-3.5H4z"/><path d="M15.5 9a4.5 4.5 0 0 1 0 6M18 6.5a8 8 0 0 1 0 11"/>',
  soundOff: '<path d="M4 9.5h3.5L12 6v12l-4.5-3.5H4z"/><path d="M16 10l5 5M21 10l-5 5"/>',
  users: '<circle cx="9" cy="8.5" r="3.5"/><path d="M3 20c.6-3.6 3-5.5 6-5.5s5.4 1.9 6 5.5"/><path d="M16 5.2a3.5 3.5 0 0 1 0 6.6M18 14.8c1.7.7 2.8 2.4 3 5.2"/>',
  link: '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
  bot: '<rect x="5" y="8" width="14" height="11" rx="3"/><path d="M12 4v4M9 13h.01M15 13h.01M9.5 16.5h5"/>',
  globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c3 3.2 3 14.8 0 18M12 3c-3 3.2-3 14.8 0 18"/>',
  play: '<path d="M16.5 5.5 6.5 12l10 6.5z"/>',
  bolt: '<path d="M13 3L5 13.5h6L10 21l8-10.5h-6z"/>',
  clock: '<circle cx="12" cy="13" r="8"/><path d="M12 9v4l3 2M9 2.5h6"/>',
  spark: '<path d="M12 3l1.9 5.6L19.5 10.5l-5.6 1.9L12 18l-1.9-5.6L4.5 10.5l5.6-1.9z"/>',
  shield: '<path d="M12 3l8 3v6c0 4.6-3.4 8.2-8 9-4.6-.8-8-4.4-8-9V6z"/><path d="M8.5 12l2.5 2.5 4.5-5"/>',
  card: '<rect x="3" y="6" width="18" height="13" rx="2.5"/><path d="M3 10.5h18M7 15h4"/>',
  check: '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
  pen: '<path d="M4 20h4L19 9l-4-4L4 16z"/><path d="M13.5 6.5l4 4"/>',
  flag: '<path d="M5 21V4M5 4h11l-2 4 2 4H5"/>',
  userX: '<circle cx="9" cy="8.5" r="3.5"/><path d="M3 20c.6-3.6 3-5.5 6-5.5s5.4 1.9 6 5.5M16 9l5 5M21 9l-5 5"/>',
  ban: '<circle cx="12" cy="12" r="8.5"/><path d="M6 6l12 12"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/>',
  sliders: '<path d="M4 7h10M18 7h2M4 17h4M12 17h8"/><circle cx="16" cy="7" r="2"/><circle cx="10" cy="17" r="2"/>',
  edit: '<path d="M4 20h4L19 9l-4-4L4 16z"/><path d="M13.5 6.5l4 4"/>',
  copy: '<rect x="8" y="8" width="12" height="12" rx="2.5"/><path d="M16 8V6.5A2.5 2.5 0 0 0 13.5 4h-7A2.5 2.5 0 0 0 4 6.5v7A2.5 2.5 0 0 0 6.5 16H8"/>',
  send: '<path d="M21 4L10 14M21 4l-6.5 17-4.5-7-7-4.5z"/>',
  mail: '<rect x="3" y="5" width="18" height="14" rx="3"/><path d="M4 7.5l8 5.5 8-5.5"/>',
  bell: '<path d="M6 10a6 6 0 0 1 12 0c0 5 2 6.5 2 6.5H4S6 15 6 10zM10 20a2 2 0 0 0 4 0"/>',
  ball: '<circle cx="12" cy="12" r="8.5"/><path d="M12 8.2l3.3 2.4-1.3 3.9h-4l-1.3-3.9zM12 3.5v4.7M20.2 9.6l-4.9 1M17 19.3l-3-4.8M7 19.3l3-4.8M3.8 9.6l4.9 1"/>',
  dice: '<rect x="4" y="4" width="16" height="16" rx="4"/><path d="M8.5 8.5h.01M15.5 15.5h.01M12 12h.01M15.5 8.5h.01M8.5 15.5h.01"/>',
  arrowUp: '<path d="M7 14l5-5 5 5"/>',
  up: '<path d="M12 19V5M5.5 11.5L12 5l6.5 6.5"/>',
  spin: '<path d="M19.5 12a7.5 7.5 0 1 1-2.2-5.3"/><path d="M19.5 4.5v4h-4"/>',
  undo: '<path d="M15 7H9.5a5 5 0 0 0 0 10H14"/><path d="M12 4l3 3-3 3"/>',
  exit: '<path d="M14 4h3.5A2.5 2.5 0 0 1 20 6.5v11a2.5 2.5 0 0 1-2.5 2.5H14"/><path d="M10 16.5L5.5 12 10 7.5M5.5 12H15"/>',
  grid: '<rect x="4" y="4" width="16" height="16" rx="3"/><path d="M9.3 4v16M14.7 4v16M4 9.3h16M4 14.7h16"/>',
  table: '<rect x="3" y="7" width="18" height="10" rx="5"/><path d="M8 17v3M16 17v3"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4 20.5c.8-4.2 4-6.5 8-6.5s7.2 2.3 8 6.5"/>',
  pad: '<path d="M7 8h10a5 5 0 0 1 5 5v.5a3.5 3.5 0 0 1-6.3 2.1L14.5 14h-5l-1.2 1.6A3.5 3.5 0 0 1 2 13.5V13a5 5 0 0 1 5-5z"/><path d="M7 11v3M5.5 12.5h3M16.5 11.5h.01M18.5 13.5h.01"/>',
  userAdd: '<circle cx="9" cy="8.5" r="3.5"/><path d="M3 20c.6-3.6 3-5.5 6-5.5s5.4 1.9 6 5.5M18 8v6M15 11h6"/>',
  cards: '<rect x="3.5" y="6" width="10" height="14" rx="2" transform="rotate(-10 8.5 13)"/><rect x="10.5" y="4" width="10" height="14" rx="2" transform="rotate(8 15.5 11)"/>',
  chat: '<path d="M4 5.5A2.5 2.5 0 0 1 6.5 3h11A2.5 2.5 0 0 1 20 5.5v8a2.5 2.5 0 0 1-2.5 2.5H10l-4.5 4v-4h0A2.5 2.5 0 0 1 4 13.5z"/><path d="M8.5 9.5h.01M12 9.5h.01M15.5 9.5h.01"/>',
};
const icon = (n, w = 2.2) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="${w}" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${P[n] || ''}</svg>`;
const COIN = '<svg viewBox="0 0 32 32" aria-hidden="true"><circle cx="16" cy="17.5" r="13" fill="#E09A00"/><circle cx="16" cy="15" r="13" fill="#FFC43B"/><circle cx="16" cy="15" r="9.4" fill="none" stroke="#E09A00" stroke-width="2"/><path d="M16 9.3l1.75 3.6 3.95.55-2.86 2.73.68 3.92L16 18.2l-3.52 1.9.68-3.92-2.86-2.73 3.95-.55z" fill="#FFF3C4"/></svg>';
const coin = () => `<span class="coin">${COIN}</span>`;
const amount = (n, cls = '') => `<span class="amount ${cls}">${coin()}<span>${fa(n)}</span></span>`;
/* نتیجهٔ میز رقابتی تو صفحهٔ آخر بازی: جام و سکهٔ بازی رتبه‌ای (بازی دوستانه چیزی نداره) */
function rankResult(v, ended) {
  const r = v.result || {}, mode = v.cfg.mode;
  if (mode === 'free') return '';
  if (mode !== 'ranked') return `<p>${r.won ? 'این میز از قبل امتیازی بود و جایزه‌ش با امتیازای قدیمیت برمی‌گرده به کیف عبور' : 'این میز از قبل امتیازی بود فدای سرت'}</p>`;
  if (ended) return '<p>بازی بی‌نتیجه بسته شد و جامت دست نخورد</p>';
  const c = r.cups || 0, k = r.coins || 0, rk = r.rank;
  const cup = `<span class="rk-cup${c < 0 ? ' rk-down' : ''}">${icon('trophy')}<b dir="ltr">${c > 0 ? '+' : c < 0 ? '−' : ''}${fa(Math.abs(c))}</b> جام</span>`;
  const note = r.won ? (k ? 'سکه‌ش ریخت تو کیفت 🎉' : 'جامش مال تو دمت گرم') : c ? 'فدای سرت دست بعد جبران کن' : 'جامی نداشتی که کم بشه';
  return `<div class="rk-res"><div class="rk-row">${cup}${k ? `<span class="amount lg">${coin()}<span dir="ltr">+${fa(k)}</span></span>` : ''}</div>
    <p>${note}${rk ? `<br><b>لیگ ${rk.league}</b> · ${fa(rk.cups)} جام` : ''}</p></div>`;
}

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
// رنگ های سیر تا حرف سفید روی آن ها خوانا باشد (کنتراست ≥ ۴.۵)
const FACE_BG = ['#5B4BC4', '#2563C9', '#C2414E', '#1A7A53', '#A6560F', '#147C8C', '#A8407E'];
const escAttr = v => String(v || '').replace(/[&"'<>]/g, ch => ({ '&': '&amp;', '"': '&quot;', "'": '&#39;', '<': '&lt;', '>': '&gt;' }[ch]));
function initial(name) { const m = String(name || '').trim().match(/[\p{L}\p{N}]/u); return m ? m[0].toUpperCase() : '؟'; }
function face(p, ring, extra = '') {
  p = p || {};
  const seed = Math.abs(+p.av || 1);
  const base = p.bot ? avatar(seed) : `<span class="ini" style="background:${FACE_BG[seed % FACE_BG.length]}">${escAttr(initial(p.name))}</span>`;
  const img = p.pic && !p.bot ? `<img src="${escAttr(APP ? APP.srv(p.pic) : p.pic)}" alt="" loading="lazy" decoding="async" referrerpolicy="no-referrer" data-face>` : '';
  // pid: کلید عمومی بازیکن دیگر (لیدربرد، میز بازی، گفتگو)؛ با لمس، کارت پروفایلش باز می شود
  const tap = p.pid && !p.bot ? ` data-pid="${escAttr(p.pid)}" role="button" tabindex="0" aria-label="پروفایل ${escAttr(p.name || '')}"` : '';
  return `<span class="avatar ${extra}${tap ? ' tap' : ''}" style="--ring:${ring || 'var(--surface)'}"${tap}><span>${base}${img}</span></span>`;
}

/* ---------- کارت پروفایل بازیکن (از لیدربرد و صفحهٔ بازی ها) با درخواست دوستی ---------- */
const GAME_FA = { hokm: 'حکم', ludo: 'منچ', football: 'فوتبال', billiard: 'بیلیارد', divar: 'دیوار', esmfamil: 'اسم‌فامیل', lashgar: 'لشگر کاغذی', snakes: 'مار و پله' };
async function userCard(pid) {
  const sh = sheet(`<div class="fr-card"><span class="fr-cover cover cover-gc"></span><div class="gp-skel" style="width:84px;height:84px;border-radius:50%"></div>
    <div class="gp-skel" style="width:60%"></div></div>`);
  let r;
  try { r = await GC.data.friendUser(pid); } catch (e) { close(); toast(e.code === 'not_found' ? 'این پروفایل دیگه در دسترس نیست' : errText(e)); return; }
  const draw = () => {
    const u = r.user, L = level(u);
    const st = u.playing ? ['play', `در حال بازی ${GAME_FA[u.playing] || ''}`] : u.online ? ['on', 'آنلاین'] : ['', u.seen ? 'آفلاین' : ''];
    const btn = {
      none: `<button class="btn btn-block" data-uc="req">${icon('userAdd')}درخواست دوستی</button>`,
      outgoing: `<div class="fr-sent">${icon('check')}درخواست دوستی رفت<button class="btn btn-light btn-sm" data-uc="drop">لغو</button></div>`,
      incoming: `<button class="btn btn-block" data-uc="acc">${icon('check')}قبول درخواست دوستی</button>`,
      friend: `<a class="btn btn-light btn-block" href="chat.html?u=${encodeURIComponent(u.uid)}">${icon('chat')}رفیقید · پیام بده</a>`,
      blocked: `<button class="btn btn-light btn-block" data-uc="unblock">رفع بلاک</button>`,
    }[r.relation] || '';
    sh.innerHTML = `<span class="grab"></span><div class="fr-card"><span class="fr-cover cover cover-${escAttr(u.cover || 'gc')}"></span>
        <span class="fr-av big">${face(u)}<i class="dot ${st[0]}"></i></span>
        <b class="uname">${escAttr(u.name)}</b>${st[1] ? `<small class="fr-st ${st[0]}">${st[1]}</small>` : ''}
        ${u.bio ? `<p class="fr-bio" dir="auto">${escAttr(u.bio)}</p>` : ''}
        <div class="fr-nums"><span><b>${FD(L.lv)}</b>سطح</span><span><b>${fa(u.games)}</b>بازی</span><span><b>${fa(u.wins)}</b>برد</span></div></div>
      <div style="display:grid;gap:8px;margin-top:12px">${btn}<button class="btn btn-light btn-block" data-close>بستن</button></div>`;
    sh.querySelector('[data-close]').onclick = close;
    sh.querySelectorAll('[data-uc]').forEach(b => b.onclick = async () => {
      b.disabled = true;
      try {
        const fn = { req: GC.data.friendReq, acc: GC.data.friendAccept, drop: GC.data.friendDrop, unblock: x => GC.data.friendBlock(x, false) }[b.dataset.uc];
        const out = await fn(u.uid); sfx.tap(); haptic('success');
        if (b.dataset.uc === 'req') toast(out.relation === 'friend' ? 'دمت گرم حالا رفیقید 🤝' : 'درخواست دوستی رفت 🤝');
        r = { user: u, relation: out.relation || (b.dataset.uc === 'unblock' ? 'none' : r.relation) }; draw();
      } catch (e) { sfx.error(); toast(errText(e)); b.disabled = false; }
    });
    mount(sh);
  };
  draw();
}
document.addEventListener('click', e => {
  const a = e.target.closest && e.target.closest('[data-pid]');
  if (!a) return;
  e.preventDefault(); e.stopPropagation(); haptic('select'); userCard(a.dataset.pid);
}, true);
document.addEventListener('keydown', e => { if ((e.key === 'Enter' || e.key === ' ') && e.target.dataset && e.target.dataset.pid) { e.preventDefault(); userCard(e.target.dataset.pid); } });
// عکسی که باز نشد (پنهان، حذف شده، بدون اینترنت تلگرام) کنار می رود تا حرف اول دیده شود
document.addEventListener('error', e => { const t = e.target; if (t && t.tagName === 'IMG' && t.hasAttribute('data-face')) t.remove(); }, true);

/* ---------- مهره منچ ---------- */
const COL = {
  blue: { hex: '#4C8DFF', deep: '#2B62D6', fa: 'آبی' }, red: { hex: '#FF5A6A', deep: '#C93447', fa: 'قرمز' },
  green: { hex: '#2FC584', deep: '#1E8A5E', fa: 'سبز' }, yellow: { hex: '#FFC531', deep: '#C98A00', fa: 'زرد' },
};
/* مهره: سکه گرد سه بعدی با لبه سفید و ستاره سفید وسط. مرکز دیسک نزدیک ۷۴٪ ارتفاع است، همان نقطه ای
   که مهره روی خانه می نشیند؛ بالای آن جای تاج برنده است. */
function pawn(c, crown) {
  const { hex, deep } = COL[c];
  return `<svg viewBox="0 0 40 50" aria-hidden="true"><ellipse cx="20" cy="47.5" rx="13" ry="2.6" fill="rgba(0,0,0,.35)"/>
    <circle cx="20" cy="40" r="14" fill="${deep}"/><circle cx="20" cy="37" r="14" fill="#fff"/><circle cx="20" cy="37" r="11" fill="${hex}"/>
    <path d="M20 30.2l2 4.1 4.5.6-3.3 3.1.8 4.5-4-2.2-4 2.2.8-4.5-3.3-3.1 4.5-.6z" fill="#fff" fill-opacity=".92"/>
    <path d="M11.5 33a9.5 9.5 0 0 1 7-6" fill="none" stroke="#fff" stroke-opacity=".55" stroke-width="2.2" stroke-linecap="round"/>
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
  // gc-ui: برگه ها در صفحهٔ بازی هم رنگ های خود اپ (روشن یا تیره) و رنگ همان بازی را دارند
  layer.innerHTML = `<div class="scrim gc-ui${center ? ' center' : ''}"><div class="sheet" role="dialog" aria-modal="true">${center ? '' : '<span class="grab"></span>'}${html}</div></div>`;
  const sc = layer.firstChild, sh = sc.firstChild;
  sc.addEventListener('click', e => { if (e.target === sc && dismiss) { close(); onClose && onClose(); } });
  sh.querySelectorAll('[data-close]').forEach(b => b.addEventListener('click', () => { close(); onClose && onClose(); }));
  const f = sh.querySelector('button,a'); if (f) setTimeout(() => f.focus({ preventScroll: true }), 50);
  return sh;
}
function close() { if (layer) layer.innerHTML = ''; }
const sheetHead = t => `<div class="sheet-head"><h2>${t}</h2><button class="close" data-close aria-label="بستن">${icon('close', 2.6)}</button></div>`;

/* ---------- یوزرنیم: همان قاعده های names.py ---------- */
const NAME_MIN = 3, NAME_MAX = 16;
function nameProblem(n) {
  if (n.length < NAME_MIN) return 'name_short';
  if (n.length > NAME_MAX) return 'name_long';
  if (!/^[a-z]/.test(n)) return 'name_start';
  if (!/^[a-z][a-z0-9_]+$/.test(n)) return 'name_chars';
  return null;
}
const normName = s => String(s || '').trim().replace(/^@+/, '').toLowerCase();
// برگهٔ تغییر یوزرنیم؛ me = خروجی me().player. done(name) بعد از ثبت
function editName(me, done) {
  const cur = me.name || '', next = +me.name_next || 0, now = Date.now() / 1000;
  const wait = next > now ? Math.ceil((next - now) / 86400) : 0;
  const sh = sheet(`${sheetHead('یوزرنیم')}
    <p class="un-lead">اسمت تو بازیا و رده‌بندی و پیش رفیقات همینه و رفیقات با همین پیدات می‌کنن</p>
    <label class="un-box" dir="ltr"><input id="unIn" value="${cur}" maxlength="${NAME_MAX + 4}" autocomplete="off" autocapitalize="off" spellcheck="false" aria-describedby="unMsg"${wait ? ' disabled' : ''}><span id="unN" class="un-n"></span></label>
    <p class="un-msg" id="unMsg" role="status"></p>
    <div class="un-sug" id="unSug" hidden></div>
    <ul class="un-rules" id="unRules"></ul>
    <button class="btn btn-block" id="unGo" disabled>${wait ? `${FD(wait)} روز دیگه می‌تونی عوضش کنی` : 'ثبت یوزرنیم'}</button>
    <p class="un-note">${me.name_next ? 'هر ۳۰ روز یه بار می‌شه یوزرنیمو عوض کرد' : 'بار اول مجانیه و بعدش هر ۳۰ روز یه بار'}</p>`);
  const inp = sh.querySelector('#unIn'), msg = sh.querySelector('#unMsg'), go = sh.querySelector('#unGo'),
    sug = sh.querySelector('#unSug'), rules = sh.querySelector('#unRules'), cnt = sh.querySelector('#unN');
  let seq = 0, timer = 0, okName = '';
  const RULES = [['len', 'از ۳ تا ۱۶ نویسه'], ['chars', 'اولش حرف انگلیسی و بعدش حرف و عدد و _'], ['free', 'کسی زودتر برش نداشته باشه']];
  function paint(st) {
    rules.innerHTML = RULES.map(([k, txt]) => `<li class="${st[k] === true ? 'ok' : st[k] === false ? 'bad' : ''}"><i>${st[k] === true ? icon('check', 3) : st[k] === false ? icon('close', 3) : ''}</i>${txt}</li>`).join('');
  }
  function check() {
    const n = normName(inp.value);
    if (inp.value !== n && document.activeElement === inp) { const p = inp.selectionStart; inp.value = n; try { inp.setSelectionRange(p, p); } catch (e) {} }
    cnt.textContent = FD(n.length) + '/' + FD(NAME_MAX);
    okName = ''; go.disabled = true; sug.hidden = true;
    const bad = nameProblem(n);
    const st = { len: n.length ? (n.length >= NAME_MIN && n.length <= NAME_MAX) : null,
      chars: n.length ? !(bad === 'name_start' || bad === 'name_chars') : null, free: null };
    sh.classList.remove('un-good', 'un-err');
    if (!n) { msg.textContent = ''; paint(st); return; }
    if (n === cur) { msg.textContent = 'یوزرنیم الانت'; st.free = true; paint(st); return; }
    if (bad) { msg.textContent = ERR[bad]; sh.classList.add('un-err'); paint(st); return; }
    msg.textContent = 'دارم نگاه می‌کنم…'; paint(st);
    const my = ++seq; clearTimeout(timer);
    timer = setTimeout(async () => {
      try {
        const r = await GC.data.nameCheck(n);
        if (my !== seq) return;
        if (r.ok) { okName = n; st.free = true; msg.innerHTML = `<bdi class="uname">${n}</bdi> آزاده`; sh.classList.add('un-good'); go.disabled = !!wait; }
        else {
          st.free = r.error === 'name_taken' ? false : null; msg.textContent = ERR[r.error] || ERR.server; sh.classList.add('un-err');
          if (r.suggest && r.suggest.length) { sug.hidden = false; sug.innerHTML = '<span>پیشنهاد:</span>' + r.suggest.map(s => `<button class="chip sm" data-s="${s}" dir="ltr">${s}</button>`).join(''); }
        }
        paint(st);
      } catch (e) { if (my === seq) msg.textContent = errText(e); }
    }, 350);
  }
  inp.addEventListener('input', check);
  sug.addEventListener('click', e => { const b = e.target.closest('[data-s]'); if (b) { inp.value = b.dataset.s; check(); inp.focus(); } });
  go.addEventListener('click', async () => {
    if (!okName) return;
    go.disabled = true;
    try { const r = await GC.data.setName(okName); close(); haptic('success'); toast('حله یوزرنیمت شد ' + r.name); done && done(r); }
    catch (e) { toast(errText(e)); go.disabled = false; }
  });
  check();
  if (!wait) setTimeout(() => { inp.focus(); inp.select(); }, 80);
}

/* ---------- جایزهٔ ورود روزانه (فروشگاه و خانه)؛ d = me.daily: {claimed, day, next, plan} ---------- */
function dailyHtml(d) {
  const boxes = d.plan.map((n, i) => {
    const k = i + 1, done = k <= d.day, today = !d.claimed && k === d.next;
    return `<li class="dl-d${done ? ' done' : ''}${today ? ' today' : ''}${k === d.plan.length ? ' big' : ''}"><small>روز ${FD(k)}</small>${coin()}<b>${FD(n)}</b>${done ? `<i>${icon('check', 3)}</i>` : ''}</li>`;
  }).join('');
  return `<div class="dl"><div class="dl-h"><b>جایزهٔ روزانهٔ تاسی 🎁</b><small>${d.claimed ? 'امروزو گرفتی فردا دوباره سر بزن تا زنجیره‌ت نشکنه'
    : 'هر روز پشت هم بیای بیشتر می‌گیری و روز آخر یه جایزهٔ درشت داره'}</small></div>
    <ol class="dl-row">${boxes}</ol>
    <button class="btn btn-block btn-gold dl-go"${d.claimed ? ' disabled' : ''}>${d.claimed ? 'فردا دوباره بیا 😉' : `بگیرش · ${FD(d.plan[(d.next || 1) - 1])} سکه`}</button></div>`;
}
// box: جای کارت جایزه؛ done(daily تازه) بعد از گرفتن
function dailyMount(box, d, done) {
  box.innerHTML = dailyHtml(d); mount(box);
  const b = box.querySelector('.dl-go');
  b.onclick = async () => {
    b.disabled = true;
    try {
      const r = await GC.data.daily();
      points = r.points; sfx.coin(); haptic('success'); toast(`+${fa(r.coins)} سکه ریخت تو کیفت 🎉`);
      dailyMount(box, r.daily, done); mount(); if (done) done(r.daily);
    } catch (e) { b.disabled = false; toast(errText(e)); }
  };
}

/* ---------- ورود به حساب (فقط داخل برنامهٔ اندروید): تلگرام یا ایمیل، appauth.py ----------
   ورود موفق: توکن تازه جای توکن این گوشی می نشیند و صفحه از نو بار می شود. */
const LOGIN_ERR = {
  bad_email: 'این ایمیل درست نیست یه نگاه بهش بنداز', email_off: 'ورود با ایمیل فعلاً بسته‌ست با تلگرام بیا',
  tg_off: 'ورود با تلگرام فعلاً بسته‌ست با ایمیل بیا', email_limit: 'زیادی کد خواستی یه ساعت دیگه دوباره امتحان کن',
  send_fail: 'ایمیل نرفت یه دقیقه دیگه دوباره امتحان کن', code_tries: 'زیادی اشتباه زدی یه کد تازه بگیر',
  code_expired: 'وقت این کد تموم شده یه کد تازه بگیر',
};
function loginErr(e) {
  const c = String((e && e.code) || ''), x = (e && e.extra) || {};
  if (c === 'email_wait') return `یه کم صبر کن ${FD(x.wait || 60)} ثانیه دیگه دوباره بفرست`;
  if (c === 'code_bad') return `کد اشتباهه ${FD(x.left)} بار دیگه می‌تونی بزنی`;
  return LOGIN_ERR[c] || errText(e);
}
const toLatin = s => String(s || '').replace(/[۰-۹]/g, d => '۰۱۲۳۴۵۶۷۸۹'.indexOf(d)).replace(/[٠-٩]/g, d => '٠١٢٣٤٥٦٧٨٩'.indexOf(d));
// welcome: بار اول باز شدن برنامه (با «فعلاً مهمون می‌مونم»)؛ guestGames: مهمونی که بازی کرده
function login({ welcome = false, guestGames = 0 } = {}) {
  if (!APP) return;
  const L = APP.login;
  let run = 0;   // هر برگهٔ تازه پرسیدن قبلی را می خواباند
  const done = () => { run++; haptic('success'); toast('حله وارد شدی ✅'); setTimeout(() => location.reload(), 700); };
  function home() {
    run++;
    const sh = sheet(`${welcome ? '' : sheetHead('ورود به حساب')}<div class="acc">
      ${welcome ? `<span class="acc-hi">${icon('dice')}</span><h2 class="acc-t">خوش اومدی 👋</h2>` : ''}
      <p class="acc-lead">با تلگرام یا ایمیل بیا تو تا بازیا و رفیقا و سکه‌هات همیشه بمونن حتی اگه گوشیتو عوض کنی</p>
      <button class="btn btn-block acc-tg" id="accTg">${icon('send')}ورود با تلگرام</button>
      <button class="btn btn-light btn-block" id="accMail">${icon('mail')}ورود با ایمیل</button>
      <p class="acc-note">قبلاً تو ربات تلگرام AsoTas بازی کردی؟ با تلگرام بیا تا همون حساب بیاد${guestGames ? '<br>بازیایی که مهمون بودی فقط با ایمیل همین‌جا می‌مونه' : ''}</p>
      ${welcome ? '<button class="acc-skip" data-close>فعلاً مهمون می‌مونم</button>' : ''}</div>`, { dismiss: !welcome });
    sh.querySelector('#accTg').onclick = tgFlow;
    sh.querySelector('#accMail').onclick = () => mailFlow('');
  }
  async function tgFlow() {
    const b = layer && layer.querySelector('#accTg'); if (b) b.disabled = true;
    let r;
    try { r = await L.tg(); } catch (e) { toast(loginErr(e)); if (b) b.disabled = false; return; }
    L.open(r.link);
    const my = ++run, until = Date.now() + (r.ttl || 600) * 1000;
    const sh = sheet(`${sheetHead('ورود با تلگرام')}<div class="acc">
      <div class="acc-wait" id="accWait"><span class="spinner"></span><b>منتظر تأیید تو تلگرامیم…</b></div>
      <p class="acc-lead">تو ربات AsoTas «آره خودمم» رو بزن و برگرد همین‌جا خودش وارد می‌شی</p>
      <button class="btn btn-block acc-tg" id="accOpen">${icon('send')}باز کردن تلگرام</button>
      <button class="btn btn-light btn-block" id="accBack">برگشت</button>
      <p class="acc-note acc-bad" id="accMsg" role="status"></p></div>`, { onClose: () => { run++; } });
    const open = sh.querySelector('#accOpen'), msg = sh.querySelector('#accMsg');
    open.onclick = () => L.open(r.link);
    sh.querySelector('#accBack').onclick = home;
    const fail = t => {
      run++; msg.textContent = t; sh.querySelector('#accWait').hidden = true;
      open.innerHTML = icon('send') + 'یه بار دیگه'; open.onclick = tgFlow;
    };
    const check = async () => {
      if (my !== run) return;
      try {
        const j = await L.tgCheck(r.poll);
        if (my !== run) return;
        if (j.state === 'ok') done();
        else if (j.state === 'no') fail('ورود رد شد اگه اشتباهی بود یه بار دیگه بزن');
        else if (j.state === 'expired' || Date.now() > until) fail('وقت این لینک تموم شد یه بار دیگه بزن');
      } catch (e) { if (e.code !== 'network' && my === run) msg.textContent = loginErr(e); }
    };
    const back = () => { if (my !== run) document.removeEventListener('visibilitychange', back); else if (!document.hidden) check(); };
    document.addEventListener('visibilitychange', back);
    while (my === run) { await sleep(2000); await check(); }
  }
  function mailFlow(prev) {
    run++;
    const sh = sheet(`${sheetHead('ورود با ایمیل')}<div class="acc">
      <p class="acc-lead">ایمیلتو بزن تا یه کد ۶ رقمی برات بفرستیم</p>
      <label class="un-box" dir="ltr"><input id="accEm" type="email" inputmode="email" autocomplete="email" autocapitalize="off" spellcheck="false" placeholder="you@gmail.com" value="${escAttr(prev)}" aria-describedby="accMsg"></label>
      <p class="un-msg" id="accMsg" role="status"></p>
      <button class="btn btn-block" id="accSend">بفرست کد</button>
      <button class="btn btn-light btn-block" id="accBack">برگشت</button></div>`);
    const inp = sh.querySelector('#accEm'), msg = sh.querySelector('#accMsg'), go = sh.querySelector('#accSend');
    const send = async () => {
      const em = inp.value.trim();
      if (!em) { inp.focus(); return; }
      go.disabled = true; sh.classList.remove('un-err'); msg.textContent = 'داریم می‌فرستیم…';
      try { const r = await L.email(em); codeStep(r.email, r.resend || 60); }
      catch (e) { msg.textContent = loginErr(e); sh.classList.add('un-err'); go.disabled = false; }
    };
    go.onclick = send;
    inp.onkeydown = e => { if (e.key === 'Enter') send(); };
    sh.querySelector('#accBack').onclick = home;
    setTimeout(() => inp.focus(), 80);
  }
  function codeStep(email, resend) {
    const my = ++run;
    const sh = sheet(`${sheetHead('کد ورود')}<div class="acc">
      <p class="acc-lead">کد ۶ رقمی‌ای که به <bdi dir="ltr" class="acc-em">${escB(email)}</bdi> فرستادیم رو بزن</p>
      <label class="un-box acc-code" dir="ltr"><input id="accCode" inputmode="numeric" autocomplete="one-time-code" maxlength="6" placeholder="••••••" aria-describedby="accMsg"></label>
      <p class="un-msg" id="accMsg" role="status"></p>
      <button class="btn btn-block" id="accGo" disabled>بزن بریم</button>
      <div class="acc-row"><button class="acc-link" id="accRe" disabled></button><button class="acc-link" id="accEdit">ایمیلو اشتباه زدی؟</button></div>
      <p class="acc-note">ایمیل نیومد؟ پوشهٔ اسپم رو هم یه نگاه بنداز</p></div>`, { onClose: () => { run++; } });
    const inp = sh.querySelector('#accCode'), msg = sh.querySelector('#accMsg'), go = sh.querySelector('#accGo'), re = sh.querySelector('#accRe');
    let left = resend, busy = false;
    const tick = () => { re.disabled = left > 0; re.textContent = left > 0 ? `دوباره بفرست (${FD(left)})` : 'دوباره بفرست'; };
    tick();
    const timer = setInterval(() => { if (my !== run) return clearInterval(timer); left = Math.max(0, left - 1); tick(); }, 1000);
    const verify = async () => {
      const code = inp.value;
      if (code.length !== 6 || busy) return;
      busy = true; go.disabled = true; sh.classList.remove('un-err'); msg.textContent = 'یه لحظه…';
      try { await L.emailVerify(email, code); clearInterval(timer); done(); }
      catch (e) {
        busy = false; msg.textContent = loginErr(e); sh.classList.add('un-err'); haptic('error');
        inp.value = ''; inp.focus();
        if (e.code === 'code_tries' || e.code === 'code_expired') left = 0, tick();
      }
    };
    inp.oninput = () => {
      const v = toLatin(inp.value).replace(/\D/g, '').slice(0, 6);
      if (v !== inp.value) inp.value = v;
      go.disabled = v.length !== 6;
      if (v.length === 6) verify();
    };
    go.onclick = verify;
    re.onclick = async () => {
      re.disabled = true;
      try { const r = await L.email(email); left = r.resend || 60; tick(); toast('یه کد تازه فرستادیم 📬'); sh.classList.remove('un-err'); msg.textContent = ''; }
      catch (e) { msg.textContent = loginErr(e); sh.classList.add('un-err'); if (e.code === 'email_wait') left = (e.extra && e.extra.wait) || 60; tick(); }
    };
    sh.querySelector('#accEdit').onclick = () => { clearInterval(timer); mailFlow(email); };
    setTimeout(() => inp.focus(), 80);
  }
  home();
}
function logoutSheet() {
  if (!APP) return;
  const sh = sheet(`<div class="dlg" role="alertdialog" aria-labelledby="dT">
      <span class="dlg-ic warn">${icon('exit')}</span>
      <h2 id="dT">از حسابت می‌ری بیرون؟</h2>
      <p>هر وقت خواستی با همون تلگرام یا ایمیل برمی‌گردی و همه‌چی سر جاشه</p>
      <div class="dlg-acts"><button class="btn" data-close>نه می‌مونم</button><button class="btn btn-danger-soft" id="accBye">آره خروج</button></div></div>`, { center: true });
  sh.querySelector("#accBye").onclick = async () => { await APP.login.logout(); location.href = "index.html"; };
}

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
  // مار و پله: بالا رفتن از نردبان (پله پله بالا) و سرخوردن روی مار (پایین)
  ladder() { [523, 587, 659, 784, 880, 1047].forEach((f, i) => tone(f, .12, { type: 'triangle', g: .16, at: i * .12 })); },
  snake() { tone(660, .9, { type: 'sawtooth', g: .07, to: 110 }); noise(.5, { g: .18, f: 2400, q: 1.2, at: .05 }); },
  six() { [988, 1319, 1568].forEach((f, i) => tone(f, .12, { type: 'triangle', g: .14, at: i * .05 })); },
  turn() { tone(740, .12, { type: 'sine', g: .22 }); tone(988, .22, { type: 'sine', g: .22, at: .11 }); },
  nomove() { tone(180, .22, { type: 'sawtooth', g: .08, to: 140 }); },
  tick() { tone(1000, .03, { type: 'square', g: .05 }); },
  win() { [523, 659, 784, 1047, 784, 1047].forEach((f, i) => tone(f, i === 5 ? .6 : .16, { type: 'triangle', g: .22, at: i * .13 })); },
  lose() { [392, 349, 311, 262].forEach((f, i) => tone(f, .28, { type: 'triangle', g: .18, at: i * .2 })); },
  error() { tone(220, .14, { type: 'square', g: .08 }); tone(180, .2, { type: 'square', g: .08, at: .12 }); },
};
/* صدای ورق: فایل های کوچک ساخته شده با game_club/tools/card_sounds.py؛ تا بار نشده اند
   (یا اگر بار نشدند) نسخه ساده با نویز ساخته می شود */
const SAMPLES = {};
let samplesLoading = null;
// صدای واقعی بیلیارد پلاتو (همان فایل های pool_offline/game_assets) — با کلید pl_*
const PLATO_SND = ['ball1', 'ball2', 'ball3', 'ball_soft1', 'ball_soft2', 'ball_soft3', 'rail1', 'rail2', 'rail3', 'rail_soft1', 'rail_soft2', 'rail_soft3', 'pocket1', 'pocket2', 'pocket3', 'sunk1', 'sunk2', 'sunk3', 'cue_hard1', 'cue_hard2', 'cue_soft1', 'rack', 'tap', 'turn_audio'];
function loadSamples() {
  const a = ctx();
  if (!a || samplesLoading) return samplesLoading;
  samplesLoading = Promise.all([
    ...['place1', 'place2', 'place3', 'place_soft1', 'place_soft2', 'place_soft3', 'place_hard1', 'place_hard2', 'place_hard3', 'slide_soft', 'slide_hard', 'slide1', 'slide2', 'square', 'flip', 'throw', 'flick', 'shuffle', 'collect', 'fb_kick', 'fb_clack1', 'fb_clack2', 'fb_clack3', 'fb_ball1', 'fb_ball2', 'fb_wall', 'fb_post', 'fb_whistle', 'fb_goal', 'fb_crowd'].map(async n => {
      try {
        const r = await fetch('static/sfx/' + n + '.mp3');
        const b = await r.arrayBuffer();
        SAMPLES[n] = await new Promise((ok, no) => a.decodeAudioData(b, ok, no));
      } catch (e) {}
    }),
    ...PLATO_SND.map(async n => {
      try {
        const r = await fetch('static/sfx/plato/' + n + '.m4a');
        const b = await r.arrayBuffer();
        SAMPLES['pl_' + n] = await new Promise((ok, no) => a.decodeAudioData(b, ok, no));
      } catch (e) {}
    }),
  ]);
  return samplesLoading;
}
// pan: -۱ چپ تا ۱ راست (صدای ورق هر بازیکن از سمت خودش)
function sample(n, { g = 1, rate = 1, at = 0, loop = false, pan = 0, jitter = true } = {}) {
  const a = ctx(); if (!a) return true;
  const buf = SAMPLES[n];
  if (!buf) { loadSamples(); return false; }
  const s = a.createBufferSource(), v = a.createGain();
  s.buffer = buf; s.loop = loop; s.playbackRate.value = loop ? 1 : rate * (jitter ? (.94 + Math.random() * .12) : 1); v.gain.value = g;
  s.connect(v);
  if (pan && a.createStereoPanner) { const p = a.createStereoPanner(); p.pan.value = Math.max(-1, Math.min(1, pan)); v.connect(p); p.connect(master); }
  else v.connect(master);
  s.start(a.currentTime + at);
  return loop ? { s, v } : true;
}
// ورق: g شدت (سرعت پرتاب)، pan سمت بازیکن. صداها از مدل فیزیکی ساخته شده اند (tools/card_sounds.py)
sfx.card = {
  // g = شدت پرتاب (۰ آرام تا ۱ محکم): صدای آرام و محکم با هم مخلوط می شوند؛ سطح خود فایل ها واقعی است
  place(g = .6, pan = 0, at = 0) {
    g = Math.max(0, Math.min(1, g));
    const n = 1 + Math.floor(Math.random() * 3), rate = .97 + g * .06;
    const ok = sample('place_soft' + n, { g: 1.15 * (1 - g) + .1, rate, pan, at });
    if (g > .25) sample('place_hard' + n, { g: Math.pow((g - .25) / .75, 1.2) * 1.05, rate, pan, at });
    if (!ok) { noise(.05, { g: .2 + .4 * g, f: 1100 + 900 * g, q: .8, at }); tone(150 - 30 * g, .05, { g: .1 + .2 * g, at }); }
  },
  slide(g = .6, pan = 0, at = .01) {
    g = Math.max(0, Math.min(1, g));
    sample('slide_soft', { g: .9 * (1 - g) + .15, pan, at });
    if (g > .35) sample('slide_hard', { g: (g - .35) / .65 * .9, pan, at });
  },
  throw(pan = 0) { sample('throw', { g: .45, pan }) || noise(.16, { g: .15, f: 2400, q: .9 }); },
  flick(at = 0, pan = 0) { sample('flick', { g: .7, at, pan }) || noise(.03, { g: .3, f: 2000, q: 1, at }); },
  shuffle() { if (!sample('shuffle', { g: .95 })) for (let i = 0; i < 18; i++) noise(.02, { g: .2, f: 1800 + Math.random() * 1500, q: 1.5, at: i * .04 }); },
  square(pan = 0) { sample('square', { g: .8, pan }) || noise(.04, { g: .3, f: 900, q: .8 }); },
  collect() { sample('collect', { g: .85 }) || noise(.25, { g: .25, f: 1600, q: .8 }); },
  flip(pan = 0) { sample('flip', { g: .8, pan }) || noise(.08, { g: .2, f: 2200, q: 1 }); },
  // اعلام حکم: برگ برمی گردد و محکم روی میز می خورد، با یک نُت آرام
  trump() { sfx.card.flip(); setTimeout(() => sfx.card.place(1), 150); tone(523, .5, { type: 'sine', g: .05, at: .16 }); },
};
// فوتبال: g شدت برخورد (۰ تا ۱)؛ صدای ضعیف تر برای برخوردهای آرام، با کمی تفاوت هر بار
let crowdLoop = null;
const pickN = (base, n) => base + (1 + Math.floor(Math.random() * n));
sfx.fb = {
  kick(g = 1) { sample('fb_kick', { g: .35 + g * .45 }) || (tone(200, .08, { g: .3, to: 120 }), noise(.02, { g: .3, f: 2600, q: 1.4 })); },
  clack(g = 1, at = 0) { sample(pickN('fb_clack', 3), { g: .15 + g * .85, at, rate: .97 + g * .06 }) || noise(.03, { g: .2 + g * .3, f: 2000, q: 2, at }); },
  ball(g = 1, at = 0) { sample(pickN('fb_ball', 2), { g: .25 + g * .85, at }) || (tone(240, .09, { g: .3, to: 180, at }), noise(.02, { g: .2, f: 900, q: .8, at })); },
  wall(g = 1, at = 0) { sample('fb_wall', { g: .2 + g * .8, at }) || (noise(.08, { g: .25 + g * .3, f: 500, q: .8, at }), tone(118, .08, { g: .2, at })); },
  post(g = 1, at = 0) { sample('fb_post', { g: .35 + g * .65, at }) || tone(1320, .5, { type: 'triangle', g: .12, at }); },
  whistle() { sample('fb_whistle', { g: .4 }) || (tone(3150, .16, { g: .1 }), tone(3150, .55, { g: .1, at: .26 })); },
  goal() { sample('fb_goal', { g: .95 }) || noise(1.6, { g: .3, f: 1000, q: .6 }); },
  // همهمه تماشاگرها در پس زمینه بازی
  crowd(on = true) {
    const a = ctx();
    if (!on || !a) { if (crowdLoop) { try { crowdLoop.v.gain.setTargetAtTime(0, crowdLoop.s.context.currentTime, .3); crowdLoop.s.stop(crowdLoop.s.context.currentTime + 1.5); } catch (e) {} crowdLoop = null; } return; }
    if (crowdLoop) return;
    const r = sample('fb_crowd', { g: 0, loop: true });
    if (r && r.s) { crowdLoop = r; r.v.gain.setTargetAtTime(.2, a.currentTime, .8); }
    else if (!r) setTimeout(() => sfx.fb.crowd(true), 600);
  },
  // پاس به یار: دو نت شاد و تشویق کوتاه جمعیت
  pass() { tone(988, .1, { type: 'triangle', g: .14 }); tone(1480, .2, { type: 'triangle', g: .12, at: .08 }); if (crowdLoop) { const t = crowdLoop.s.context.currentTime, v = crowdLoop.v.gain; v.cancelScheduledValues(t); v.setTargetAtTime(.32, t, .1); v.setTargetAtTime(.2, t + .9, .5); } },
  roar() { if (crowdLoop) { const t = crowdLoop.s.context.currentTime, g = crowdLoop.v.gain; g.cancelScheduledValues(t); g.setTargetAtTime(.5, t, .15); g.setTargetAtTime(.2, t + 2.2, .8); } },
};
// بیلیارد: فایل های واقعی پلاتو (static/sfx/plato/*.m4a) — انتخاب و بلندی عیناً مثل plato_audio.js (بدون جیترِ نرخ)
sfx.bl = {
  // برخوردِ توپ-توپ: بالای .۵ صدای سخت ball* وگرنه ball_soft*
  ball(g = 1, pan = 0) {
    g = Math.max(0, Math.min(1, g));
    const hard = g > .5, v = hard ? Math.min(1, .35 + g * .65) : Math.min(1, .18 + g);
    sample(pickN('pl_' + (hard ? 'ball' : 'ball_soft'), 3), { g: v, pan, jitter: false }) || noise(.02, { g: .15 + g * .35, f: 4200, q: 2 });
  },
  // برخوردِ ریل: بالای .۳۵ صدای سخت rail* وگرنه rail_soft*
  rail(g = 1, pan = 0) {
    g = Math.max(0, Math.min(1, g));
    const hard = g > .35, v = hard ? Math.min(1, .2 + g * .8) : Math.min(1, .15 + g * .85);
    sample(pickN('pl_' + (hard ? 'rail' : 'rail_soft'), 3), { g: v, pan, jitter: false }) || (tone(120, .1, { g: .2 * g, to: 90 }), noise(.05, { g: .15 * g, f: 600, q: .7 }));
  },
  // جیب: مثل پلاتو — k رنکِ توپِ افتاده؛ k>0 صدای pocket* و همیشه sunk*
  pocket(k = 0, pan = 0) {
    const okP = k > 0 ? sample(pickN('pl_pocket', 3), { g: 1, pan, jitter: false }) : false;
    const okS = sample(pickN('pl_sunk', 3), { g: 1, pan, jitter: false });
    if (!okP && !okS) (tone(140, .2, { g: .25, to: 90 }), noise(.3, { g: .12, f: 300, q: .6, at: .1 }));
  },
  // ضربهٔ چوب: بالای .۵ سخت (بالای .۹ محکم تر)؛ بلندی .5+.5g یا .2+g
  cue(g = 1, pan = 0) {
    g = Math.max(0, Math.min(1, g));
    const hard = g > .5, v = hard ? .5 + .5 * g : .2 + g;
    sample('pl_' + (hard ? (g > .9 ? 'cue_hard2' : 'cue_hard1') : 'cue_soft1'), { g: v, pan, jitter: false }) || noise(.03, { g: .3, f: 1500, q: 1 });
  },
  rack() { sample('pl_rack', { g: 1, jitter: false }); },
  tap() { sample('pl_tap', { g: .8, jitter: false }) || sfx.tap(); },
  turn() { sample('pl_turn_audio', { g: .8, jitter: false }) || sfx.turn(); },
};
// لشگر کاغذی: خش خش مداد، تا شدن کاغذ، فشار از پشت و خوردن شلیک
sfx.paper = {
  scratch(g = .5) { noise(.06, { g: .04 + .1 * g, f: 2400 + Math.random() * 1800, q: 1.6 }); },
  fold() { noise(.3, { g: .2, f: 900, q: .5 }); noise(.16, { g: .1, f: 2600, q: .8, at: .12 }); },
  press() { tone(120, .1, { g: .22, to: 70 }); noise(.05, { g: .18, f: 700, q: .7 }); },
  boom() { tone(150, .5, { type: 'sawtooth', g: .12, to: 40 }); noise(.42, { g: .32, f: 520, q: .6, at: .02 }); tone(70, .34, { g: .28, at: .04 }); },
  miss() { tone(520, .12, { type: 'triangle', g: .07, to: 380 }); noise(.05, { g: .08, f: 1600, q: 1 }); },
};
function setSound(on) { if (!on && sfx.fb) sfx.fb.crowd(false); S.sound = on; save(); if (on) { ctx(); sfx.tap(); } }

/* ---------- ناوبری پایین: پنج بخش فقط با آیکون؛ «بازی‌ها» دکمهٔ گرد طلایی وسط است ---------- */
// آیکن های فایلی از static/icons (راهنما: static/icons/README.md). به شکل ماسک کشیده می شوند تا رنگ را از جای خودشان بگیرند
const ICON_FILES = { navGames: 'static/icons/nav-games.svg' };
const fileIcon = key => `<i class="ic-file" aria-hidden="true" style="-webkit-mask-image:url('${ICON_FILES[key]}');mask-image:url('${ICON_FILES[key]}')"></i>`;
const NAV = [['home', 'index.html', 'خانه', 'home'], ['friends', 'friends.html', 'دوستان', 'users'], ['games', 'games.html', 'بازی‌ها', 'pad'],
  ['shop', 'shop.html', 'فروشگاه', 'bag'], ['profile', 'profile.html', 'پروفایل', 'user']];
// عدد روی آیکون دوستان: درخواست های تازه + پیام های نخوانده
let navBadge = 0;
function setNavBadge(s) {
  navBadge = s ? (+s.requests || 0) + (+s.unread || 0) : navBadge;
  const b = navEl && navEl.querySelector('.nav-badge'); if (!b) return;
  b.hidden = !navBadge; b.textContent = navBadge > 9 ? '+۹' : FD(navBadge);
}
let navEl = null;
function nav(active) {
  if (mountingView) return;
  if (navEl) { setActive(active, false); return; }
  const n = navEl = document.createElement('nav'); n.className = 'nav'; n.setAttribute('aria-label', 'بخش‌های AsoTas');
  // نام هر بخش زیر آیکونش؛ «بازی‌ها» وسط یک تاس است که کمی بالاتر از نوار نشسته و با لمس می چرخد
  const die = [1, 0, 1, 0, 1, 0, 1, 0, 1].map(p => `<i${p ? ' class="p"' : ''}></i>`).join('');
  n.innerHTML = `<div class="nav-in"><span class="nav-pill" aria-hidden="true"></span>${NAV.map(([id, href, label, ic]) =>
    `<a href="${href}" data-id="${id}"${id === 'games' ? ' class="nav-play"' : ''}>${id === 'games' ? `<span class="np" aria-hidden="true">${die}</span>` : icon(ic)}<span class="nl">${label}</span>${id === 'friends' ? '<span class="nav-badge" hidden></span>' : ''}</a>`).join('')}</div>`;
  n.addEventListener('pointerdown', e => { const d = e.target.closest('.nav-play'); if (!d || reduced()) return; const np = d.querySelector('.np'); np.classList.remove('roll'); void np.offsetWidth; np.classList.add('roll'); }, { passive: true });
  // دانلود زودهنگام: با لمس دکمه، صفحهٔ آن بخش همان لحظه گرفته می شود
  n.addEventListener('pointerdown', e => { const a = e.target.closest('a[href]'); if (a) fetchPage(a.getAttribute('href')); }, { passive: true });
  document.body.appendChild(n);
  setNavBadge();
  initShell(active);
  setActive(active, false);
  addEventListener('resize', placePill);
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(placePill);
}
const EASE = 'cubic-bezier(.22,.9,.3,1)', NAV_MS = 340;
const reduced = () => { try { return matchMedia('(prefers-reduced-motion: reduce)').matches; } catch (e) { return false; } };
function placePill() {
  if (!navEl) return;
  const pill = navEl.querySelector('.nav-pill'), cur = navEl.querySelector('.nav-in>[aria-current]');
  if (!cur || cur.classList.contains('nav-play')) { pill.style.opacity = '0'; return; }
  pill.style.opacity = '1'; pill.style.left = cur.offsetLeft + 'px'; pill.style.width = cur.offsetWidth + 'px';
}
/* جابه جایی قرص طلایی: فقط transform (روی پردازندهٔ گرافیکی، بدون چیدمان دوباره در هر فریم).
   روش FLIP: جای قبلی هر دکمه و قرص اندازه گرفته می شود، چیدمان تازه یک باره اعمال می شود و بعد
   هر چیز از جای قبلی اش به جای تازه سر می خورد */
function setActive(id, animate) {
  if (!navEl) return;
  const nin = navEl.querySelector('.nav-in'), pill = nin.querySelector('.nav-pill');
  const items = [...nin.querySelectorAll(':scope>a,:scope>button')];
  const anim = animate && !reduced() && nin.querySelector('[aria-current]');
  const first = anim ? items.map(el => el.getBoundingClientRect().left) : null, p0 = anim ? pill.getBoundingClientRect() : null;
  items.forEach(el => el.dataset.id === id ? el.setAttribute('aria-current', 'page') : el.removeAttribute('aria-current'));
  placePill();
  if (!anim) return;
  const opt = { duration: NAV_MS, easing: EASE };
  items.forEach((el, i) => { const dx = first[i] - el.getBoundingClientRect().left; if (Math.abs(dx) > .5) el.animate([{ transform: `translateX(${dx}px)` }, { transform: 'none' }], opt); });
  const p1 = pill.getBoundingClientRect();
  if (p1.width && p0.width && pill.style.opacity !== '0') pill.animate([{ transform: `translateX(${p0.left - p1.left}px) scaleX(${p0.width / p1.width})` }, { transform: 'none' }], opt);
}

/* ---------- بخش های اصلی (خانه، رده بندی، کیف، فروشگاه) در یک صفحه ----------
   هر بخش یک بار ساخته می شود و در حافظه می ماند؛ رفتن بین آنها صفحه را دوباره بار نمی کند،
   فقط بخش تازه نشان داده می شود و داده هایش (موجودی، تاریخچه، رده بندی…) تازه می شود.
   بخشی که هنوز ساخته نشده یک بار گرفته و ساخته می شود (صفحه اش از قبل در پس زمینه گرفته شده). */
const TABS = { 'index.html': 'home', 'friends.html': 'friends', 'games.html': 'games', 'profile.html': 'profile', 'shop.html': 'shop' };
const views = {}, pages = {};
let curView = null, mountingView = null, switching = null, prebuilding = false;
const building = {};
function tabFile(href) {
  try {
    const u = new URL(href, location.href);
    if (u.origin !== location.origin || u.search) return null;
    const f = u.pathname.split('/').pop() || 'index.html';
    return TABS[f] ? f : null;
  } catch (e) { return null; }
}
function fetchPage(href) {
  const f = tabFile(href); if (!f || views[TABS[f]]) return null;
  return pages[f] || (pages[f] = fetch(f, { credentials: 'same-origin' }).then(r => { if (!r.ok) throw new Error('page'); return r.text(); }).catch(e => { delete pages[f]; throw e; }));
}
function initShell(active) {
  const file = Object.keys(TABS).find(f => TABS[f] === active);
  if (!file || curView) return;
  const v = document.createElement('div'); v.className = 'view'; v.dataset.view = active;
  document.querySelectorAll('body>header.appbar,body>main').forEach(el => v.appendChild(el));
  document.body.insertBefore(v, document.body.firstChild);
  views[active] = { el: v, file, back: null, title: document.title, show: [], scroll: 0 };
  curView = active;
  try { history.replaceState({ view: active }, '', location.href); } catch (e) {}
  // بقیهٔ بخش ها وقتی برنامه بیکار است گرفته می شوند (فقط متن صفحه؛ ساختن و داده وقتی لازم شد)
  // بقیهٔ بخش ها وقتی برنامه بیکار است یکی یکی گرفته و ساخته می شوند، بدون گرفتن داده؛
  // داده ها بار اولی که آن بخش دیده شود گرفته می شوند. پس رفتن به هر بخش فقط نشان دادن است
  const later = window.requestIdleCallback ? fn => requestIdleCallback(fn, { timeout: 2500 }) : fn => setTimeout(fn, 900);
  const rest = Object.keys(TABS).filter(f => f !== file);
  const next = () => { const f = rest.shift(); if (!f) return; ensureView(TABS[f], true).catch(() => {}).then(() => later(next)); };
  later(next);
}
function ensureView(name, pre = false) {
  if (views[name]) return Promise.resolve();
  return building[name] || (building[name] = mountView(name, pre).finally(() => { delete building[name]; }));
}
function loadScript(src) {
  return new Promise((ok, bad) => { const s = document.createElement('script'); s.src = src; s.onload = ok; s.onerror = bad; document.head.appendChild(s); });
}
async function mountView(name, pre = false) {
  const file = Object.keys(TABS).find(f => TABS[f] === name);
  const doc = new DOMParser().parseFromString(await (pages[file] || fetchPage(file)), 'text/html');
  for (const l of doc.querySelectorAll('link[rel="stylesheet"]')) {
    const href = l.getAttribute('href');
    if (!document.querySelector(`link[rel="stylesheet"][href="${href}"]`)) await new Promise(ok => { const n = document.createElement('link'); n.rel = 'stylesheet'; n.href = href; n.onload = n.onerror = ok; document.head.appendChild(n); });
  }
  doc.head.querySelectorAll('style').forEach(st => { const n = document.createElement('style'); n.dataset.view = name; n.textContent = st.textContent; document.head.appendChild(n); });
  for (const sc of doc.querySelectorAll('script[src]')) {
    const src = sc.getAttribute('src');
    if (/telegram-web-app|app-config\.js|static\/app\.js|static\/gc\.js|static\/demo\.js/.test(src) || document.querySelector(`script[src="${src}"]`)) continue;
    await loadScript(src);
  }
  const v = document.createElement('div'); v.className = 'view'; v.dataset.view = name; v.hidden = true;
  doc.querySelectorAll('body>header.appbar,body>main').forEach(el => v.appendChild(document.importNode(el, true)));
  document.body.insertBefore(v, navEl);
  views[name] = { el: v, file, back: null, title: doc.title, show: [], scroll: 0 };
  mountingView = name; prebuilding = pre;
  try {
    doc.querySelectorAll('script:not([src])').forEach(sc => { const n = document.createElement('script'); n.textContent = sc.textContent; document.body.appendChild(n); n.remove(); });
  } finally { mountingView = null; prebuilding = false; }
  mount(v);
}
async function showView(name, push = true) {
  if (!views[curView]) return;
  if (name === curView) { scrollTo({ top: 0, behavior: reduced() ? 'auto' : 'smooth' }); return; }
  const prev = views[curView];
  prev.scroll = scrollY;
  setActive(name, true);
  curView = name;
  const my = switching = {};
  // اول قرص راه بیفتد (روی پردازندهٔ گرافیکی)، بعد کار سنگین تر عوض کردن بخش
  await new Promise(r => requestAnimationFrame(() => setTimeout(r, 0)));
  try { if (!views[name]) await ensureView(name); else views[name].show.forEach(fn => { try { fn(); } catch (e) {} }); }
  catch (e) { location.href = Object.keys(TABS).find(f => TABS[f] === name); return; }
  if (switching !== my) return;
  const v = views[name];
  Object.values(views).forEach(x => { x.el.hidden = x !== v; });
  scrollTo(0, v.scroll);
  if (!reduced()) v.el.animate([{ opacity: 0, transform: 'translateY(10px)' }, { opacity: 1, transform: 'none' }], { duration: 240, easing: EASE });
  document.title = v.title;
  applyBack(v.back);
  if (push) try { history.pushState({ view: name }, '', v.file); } catch (e) {}
}
// هش لینک (مثلا shop.html#charge) برای همان بخش نگه داشته می شود تا کار خواسته شده را انجام دهد
const hashOf = href => { try { const h = new URL(href, location.href).hash; return /tgWebApp/.test(h) ? '' : h; } catch (e) { return ''; } };
let wantHash = { v: TABS[location.pathname.split('/').pop() || 'index.html'], h: hashOf(location.href) };
function takeHash() { if (!wantHash || wantHash.v !== (curView || wantHash.v)) return ''; const h = wantHash.h; wantHash = null; return h; }
function go(href) { const f = tabFile(href); wantHash = { v: f && TABS[f], h: hashOf(href) }; if (f && curView) showView(TABS[f]); else location.href = href; }
function onShow(fn) { const k = mountingView || curView; if (k && views[k]) views[k].show.push(fn); }
/* بار دادهٔ هر بخش: همین حالا (اگر بخش دیده می شود) و هر بار که دوباره دیده شود */
function page(load) { onShow(load); if (!prebuilding) load(); }
const isActive = id => !curView || curView === id;
document.addEventListener('click', e => {
  if (!curView || e.defaultPrevented || e.button || e.metaKey || e.ctrlKey || e.shiftKey) return;
  const a = e.target.closest('a[href]'); if (!a || a.target) return;
  const f = tabFile(a.getAttribute('href')); if (!f) return;
  e.preventDefault(); close(); wantHash = { v: TABS[f], h: hashOf(a.getAttribute('href')) }; showView(TABS[f]);
});
addEventListener('popstate', e => { const id = e.state && e.state.view; if (id && curView) showView(id, false); });
/* تصویر کوچک هر بازی (همان اجزای واقعی بازی: ورق، مهره فلزی و زمین، صفحه منچ) */
const GAME_ART = {
  hokm: () => '<svg viewBox="0 0 64 64" aria-hidden="true"><g transform="rotate(-14 22 36)"><rect x="6" y="10" width="30" height="42" rx="6" fill="#fff"/><path d="M21 20c4 5 8 7 8 11a4 4 0 0 1-6.5 3l1.5 5h-6l1.5-5a4 4 0 0 1-6.5-3c0-4 4-6 8-11z" fill="#1E2235"/></g><g transform="rotate(12 44 36)"><rect x="28" y="12" width="30" height="42" rx="6" fill="#fff"/><path d="M43 43c-7-5-10-8-10-11.5a4.5 4.5 0 0 1 10-2 4.5 4.5 0 0 1 10 2c0 3.5-3 6.5-10 11.5z" fill="#F25C6E"/></g></svg>',
  football: () => '<svg viewBox="0 0 64 64" aria-hidden="true"><rect x="6" y="4" width="52" height="56" rx="4" fill="none" stroke="#fff" stroke-width="2.5" opacity=".9"/><path d="M6 32h52" stroke="#fff" stroke-width="2.5" opacity=".9"/><circle cx="32" cy="32" r="8" fill="none" stroke="#fff" stroke-width="2.5" opacity=".9"/><circle cx="20" cy="44" r="7" fill="#DDE3EA"/><circle cx="20" cy="44" r="5" fill="#1E5BD8"/><circle cx="44" cy="20" r="7" fill="#DDE3EA"/><circle cx="44" cy="20" r="5" fill="#D7263D"/><circle cx="33" cy="33" r="4" fill="#fff" stroke="#1c1f2a" stroke-width="1.2"/></svg>',
  ludo: () => boardArt(),
  billiard: () => '<svg viewBox="0 0 64 64" aria-hidden="true"><rect x="9" y="3" width="46" height="58" rx="7" fill="#6B3A1F"/><rect x="14" y="8" width="36" height="48" rx="3" fill="#1E8A4C"/><g fill="#0B0F0D"><circle cx="15" cy="9" r="3.4"/><circle cx="49" cy="9" r="3.4"/><circle cx="15" cy="55" r="3.4"/><circle cx="49" cy="55" r="3.4"/><circle cx="14" cy="32" r="3"/><circle cx="50" cy="32" r="3"/></g><circle cx="32" cy="20" r="4.6" fill="#FEC625"/><circle cx="27.4" cy="26.5" r="4.6" fill="#1937A5"/><circle cx="36.6" cy="26.5" r="4.6" fill="#111"/><circle cx="35.6" cy="25.2" r="1.7" fill="#fff"/><circle cx="32" cy="45" r="4.6" fill="#F4F1E8"/><path d="M33 50L46 63" stroke="#D9B27C" stroke-width="2.6" stroke-linecap="round"/></svg>',
  divar: () => '<svg viewBox="0 0 64 64" aria-hidden="true"><rect x="4" y="4" width="56" height="56" rx="10" fill="#18543a"/><g fill="#3a9d68">' + [10, 22, 34, 46].map(y => [10, 22, 34, 46].map(x => `<rect x="${x}" y="${y}" width="9" height="9" rx="2.4"/>`).join('')).join('') + '</g><rect x="8.5" y="31" width="22" height="3.2" rx="1.6" fill="#F5C451"/><rect x="43.2" y="9" width="3.2" height="22" rx="1.6" fill="#F5C451"/><circle cx="26.5" cy="50.5" r="5.2" fill="#DDE3EA"/><circle cx="26.5" cy="50.5" r="3.6" fill="#4C8DFF"/><circle cx="38.5" cy="14.5" r="5.2" fill="#DDE3EA"/><circle cx="38.5" cy="14.5" r="3.6" fill="#FF5A6A"/></svg>',
  esmfamil: () => '<svg viewBox="0 0 64 64" aria-hidden="true"><g transform="rotate(-6 32 32)"><rect x="9" y="6" width="46" height="54" rx="4" fill="#FFFCF2"/><g stroke="#C9D8EE" stroke-width="1.6"><path d="M9 22h46M9 33h46M9 44h46"/></g><path d="M44 6v54" stroke="#E8A3A8" stroke-width="1.6"/><path d="M15 29c3-3 8-3 12 0M15 40c4-2 10-2 15 0" stroke="#1E3A8A" stroke-width="2.4" fill="none" stroke-linecap="round"/><ellipse cx="34" cy="16" rx="7" ry="6.5" fill="none" stroke="#C8323C" stroke-width="2.2"/><text x="34" y="20.5" text-anchor="middle" font-family="Rokh,sans-serif" font-weight="900" font-size="11" fill="#C8323C">ب</text></g></svg>',
  lashgar: () => '<svg viewBox="0 0 64 64" aria-hidden="true"><g transform="rotate(-5 32 32)"><rect x="9" y="5" width="46" height="55" rx="3" fill="#FCFBF7"/><path d="M9 32.5q4-2.4 8 0t8 0t8 0t8 0t8 0t5 0" fill="none" stroke="#3A3A3A" stroke-width="1.5"/><g fill="none" stroke="#3A3A3A" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M16 49q-2 5 3 5h19q5 0 3-5z"/><path d="M19 49l2.5-4h14l2.5 4"/><path d="M25 45q0-4.5 4-4.5t4 4.5"/><path d="M32 43l11-4"/><g transform="rotate(180 39 18)"><circle cx="39" cy="12" r="2.4"/><path d="M39 14.5v6M35.5 17h7M39 20.5l-3 4.5M39 20.5l3 4.5"/></g></g><circle cx="39" cy="18.5" r="3.2" fill="#C8323C"/><path d="M33 12.5l12 12M45 12.5l-12 12" stroke="#C8323C" stroke-width="2.4" stroke-linecap="round"/><path d="M16 12h7v5h-7z" fill="#EF4136" opacity=".75"/><path d="M23 9v12" stroke="#3A3A3A" stroke-width="1.6" stroke-linecap="round"/></g></svg>',
  // صفحهٔ شب جنگل: خانه های فیروزه ای، نردبان طلایی و مار سبز راه راه
  snakes: () => '<svg viewBox="0 0 64 64" aria-hidden="true"><rect x="3" y="3" width="58" height="58" rx="10" fill="#e9b44c"/><rect x="6" y="6" width="52" height="52" rx="7" fill="#071c22"/>' + [0, 1, 2, 3].map(r => [0, 1, 2, 3].map(c => `<rect x="${7.5 + c * 12.5}" y="${7.5 + r * 12.5}" width="11.5" height="11.5" rx="2.5" fill="${(r + c) % 2 ? '#1f8276' : '#164a5e'}"/>`).join('')).join('') + '<g stroke-linecap="round"><path d="M17 50L41 15M25 54L49 19" stroke="#8a5412" stroke-width="3.2"/><path d="M17 50L41 15M25 54L49 19" stroke="#e9b44c" stroke-width="1.8"/><path d="M22 46.5l7.5 5M27.5 38.5l7.5 5M33 30.5l7.5 5M38.5 22.5l7.5 5" stroke="#c98a2b" stroke-width="2.2"/><path d="M47 47c-8-2-4-10-12-12s-6-10-14-12" fill="none" stroke="#16804c" stroke-width="6.5"/><path d="M47 47c-8-2-4-10-12-12s-6-10-14-12" fill="none" stroke="#2bb673" stroke-width="4.2" stroke-dasharray="4 4"/></g><circle cx="20" cy="23" r="4.6" fill="#2bb673"/><circle cx="18.6" cy="21.6" r="1.3" fill="#fff"/><circle cx="18.5" cy="21.5" r=".6" fill="#111"/><circle cx="44" cy="40" r="3.4" fill="#FFC531" stroke="#fff" stroke-width="1"/></svg>',
  esm: () => '<svg viewBox="0 0 64 64" aria-hidden="true"><g transform="rotate(-10 32 32)"><rect x="4" y="14" width="28" height="32" rx="8" fill="#fff"/><text x="18" y="38" text-anchor="middle" font-family="Rokh,sans-serif" font-weight="900" font-size="20" fill="#E07A1F">ب</text><rect x="32" y="22" width="28" height="32" rx="8" fill="#fff"/><text x="46" y="46" text-anchor="middle" font-family="Rokh,sans-serif" font-weight="900" font-size="20" fill="#E07A1F">م</text></g></svg>',
};
const GAMES = [
  { id: 'hokm', name: 'حکم', sub: '۴ نفره · با یار و ناشناس یا ربات', href: 'hokm-lobby.html', tint: 't-felt', cat: 'card', tag: 'محبوب' },
  { id: 'football', name: 'فوتبال', sub: '۲ نفره · نوبتی', href: 'football-lobby.html', tint: 't-green', cat: 'sport', tag: 'تازه' },
  { id: 'ludo', name: 'منچ', sub: '۲ یا ۴ نفره', href: 'ludo-lobby.html', tint: 't-ludo', cat: 'board' },
  { id: 'billiard', name: 'بیلیارد', sub: '۲ نفره یا ۴ نفره یاری', href: 'billiard-lobby.html', tint: 't-bil', cat: 'sport', tag: 'تازه' },
  { id: 'divar', name: 'دیوار', sub: '۲ یا ۴ نفره · راهو ببند', href: 'divar-lobby.html', tint: 't-dv', cat: 'board', tag: 'تازه' },
  { id: 'esmfamil', name: 'اسم‌فامیل', sub: '۲ تا ۱۰ نفر · گروه یا کانال', href: 'esmfamil-lobby.html', tint: 't-paper', cat: 'word', tag: 'تازه' },
  { id: 'lashgar', name: 'لشگر کاغذی', sub: '۲ نفره · گروه یا کانال', href: 'lashgar-lobby.html', tint: 't-desk', cat: 'board', tag: 'تازه' },
  { id: 'snakes', name: 'مار و پله', sub: '۲ تا ۴ نفره · با ربات و رفقا یا تو گروه', href: 'snakes-lobby.html', tint: 't-sn', cat: 'board', tag: 'تازه' },
];
function quickPlay() {
  sheet(`${sheetHead('بازی‌ها')}<div class="qp">${GAMES.map(g => g.soon
    ? `<div class="soon"><span class="g-art ${g.tint}">${GAME_ART[g.id]()}</span><span><b>${g.name}</b><small>${g.sub}</small></span><span></span></div>`
    : `<a href="${g.href}"><span class="g-art ${g.tint}">${GAME_ART[g.id]()}</span><span><b>${g.name}</b><small>${g.sub}</small></span><span class="go">${icon('fwd')}</span></a>`).join('')}</div>`);
}
/* سطح بازیکن از کارنامهٔ واقعی خودش: هر بازی ۱۰ و هر برد ۱۵ تجربه؛ سطح بعد هر بار ۵۰ تجربه گران تر */
function level(p) {
  const xp = (+(p && p.games) || 0) * 10 + (+(p && p.wins) || 0) * 15;
  let lv = 1, base = 0, need = 100;
  while (xp >= base + need) { base += need; lv++; need = 100 + (lv - 1) * 50; }
  return { lv, xp, left: base + need - xp, frac: (xp - base) / need };
}
function mount(root = document) {
  root.querySelectorAll('[data-ic]').forEach(el => { el.innerHTML = icon(el.dataset.ic); });
  root.querySelectorAll('[data-coin]').forEach(el => { el.innerHTML = COIN; el.classList.add('coin'); });
  root.querySelectorAll('[data-bal]').forEach(el => { el.textContent = points == null ? (live ? '…' : fa(S.bal)) : fa(points); });
}
document.addEventListener('click', e => { if (e.target.closest('.btn,.chip,.seg button,.choice,.nav a,.nav button,.icon-btn')) { sfx.tap(); haptic('select'); } }, true);

/* ---------- داده نمونه (تا وقتی API AsoTas ساخته شود) ---------- */
const PEOPLE = [['کیان ر.', 3], ['مهسا ک.', 5], ['امیرعلی م.', 2], ['نگار س.', 9], ['رضا ت.', 12], ['پریا ن.', 13], ['سینا ح.', 6], ['هستی ا.', 17], ['آرش د.', 10], ['یاسمن ف.', 21]];
const LB = {
  top: [[0, 48, 12400], [1, 41, 9850], [2, 37, 8200], [3, 33, 6900], [4, 29, 5750], [5, 26, 4300], [6, 22, 3950], [7, 19, 3100], [8, 17, 2650], [9, 15, 2200]],
  spend: [[2, 0, 24500], [6, 0, 18200], [0, 0, 15900], [7, 0, 11300], [1, 0, 9600], [4, 0, 7400], [3, 0, 5200], [5, 0, 3900], [9, 0, 2800], [8, 0, 1900]],
};
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
  let g = '<rect x="-.5" y="-.5" width="16" height="16" rx="1.4" fill="#0A1914"/>';
  for (const c of L.ORDER) {
    const [x, y] = L.SEAT[c].yard;
    g += `<rect x="${x + .55}" y="${y + .55}" width="4.9" height="4.9" rx="1.2" fill="${COL[c].hex}"/>`;
    for (const [sx, sy] of L.SOCKETS) g += `<circle cx="${x + sx}" cy="${y + sy}" r=".62" fill="rgba(0,0,0,.2)"/>`;
  }
  L.TRACK.forEach(([x, y], i) => { const c = startOf[i]; g += `<rect x="${x + .07}" y="${y + .07}" width=".86" height=".86" rx=".2" fill="${c ? COL[c].hex : '#F4F2FA'}"/>`; });
  for (const c of L.ORDER) for (const [x, y] of L.SEAT[c].lane) g += `<rect x="${x + .07}" y="${y + .07}" width=".86" height=".86" rx=".2" fill="${COL[c].hex}"/>`;
  g += '<path d="M6 6L7.5 7.5L6 9z" fill="#4C8DFF"/><path d="M6 6L9 6L7.5 7.5z" fill="#FF5A6A"/><path d="M9 6L9 9L7.5 7.5z" fill="#2FC584"/><path d="M6 9L9 9L7.5 7.5z" fill="#FFC531"/>';
  return `<svg viewBox="-.5 -.5 16 16" aria-hidden="true">${g}</svg>`;
}
/* ---------- تماشای بازی: اعضای گروه از کارت میز (?watch=شناسه) بازی را فقط می بینند ---------- */
const watchId = () => { try { return new URL(location.href).searchParams.get('watch') || ''; } catch (e) { return ''; } };
function watchPill() {
  // دکمهٔ چت (که تماشاگر لازمش ندارد) همان جای خودش برچسب «در حال تماشا» می شود
  document.body.classList.add('watching');
  const b = document.getElementById('chatBtn');
  if (!b || b.dataset.watch) return;
  b.dataset.watch = '1'; b.hidden = false; b.disabled = true; b.onclick = null; b.setAttribute('aria-label', 'در حال تماشا');
  b.innerHTML = `${icon('eye')}<span class="lb">در حال تماشا</span><span class="badge" id="chatBadge" hidden></span>`;
}
function watchOver(game, title, line) {
  watchPill();
  sheet(`<div class="dlg" role="alertdialog" aria-labelledby="wT" aria-describedby="wD"><span class="dlg-ic">${icon('eye')}</span>
      <h2 id="wT">${title}</h2><p id="wD">${line}</p>
      <div class="dlg-acts"><a class="btn" href="${game}-lobby.html">خودت بازی کن</a><a class="btn btn-light" href="index.html">خانه</a></div></div>`, { center: true, dismiss: false });
}
const RATE = 500; // هر سکه چند تومان (نمونه)
document.documentElement.lang = 'fa'; document.documentElement.dir = 'rtl';

window.GC = { editName, login, logoutSheet, dailyMount, esc: escB, nameProblem, normName, tg, live, app: APP, back, haptic, guardClose, portrait, openLink, startParam, api, errText, idem, refreshMe,
  get data() { return live ? liveData : GC.demo.data; }, get ludo() { return live ? liveLudo : GC.demo.ludo; },
  get hokm() { return live ? liveHokm : GC.demo.hokm; }, get football() { return live ? liveFootball : GC.demo.football; },
  get billiard() { return live ? liveBilliard : GC.demo.billiard; }, get divar() { return live ? liveDivar : GC.demo.divar; }, get snakes() { return live ? liveSnakes : GC.demo.snakes; }, esm: liveEsm, lashgar: liveLashgar, loadSamples,
  get points() { return points == null ? S.bal : points; }, set points(v) { points = v; mount(); },
  PEOPLE, LB, RATE, LUDO, boardArt, FD, fa, rand, sleep, store, S, save, ledger, icon, COIN, coin, amount, rankResult, avatar, avatarEl, face, initial, COL, pawn, pips, toast, sheet, close, sheetHead, sfx, setSound, nav, mount, GAMES, GAME_ART, quickPlay, level, onShow, page, isActive, go, takeHash, setNavBadge, fileIcon, ICON_FILES, watchId, watchPill, watchOver, onFit, queueFit, appHeight, editing, userCard };
document.addEventListener('DOMContentLoaded', () => { mount(); boot(); });
})();
