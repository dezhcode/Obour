/* برنامهٔ اندروید AsoTas (Capacitor). فقط وقتی بار می شود که صفحه ها از داخل برنامه باز شوند؛
   appbundle.py این اسکریپت را به جای SDK تلگرام در هر صفحه می گذارد و app-config.js (GC_APP) را پیش از آن.
   - حساب مهمان: بار اول از سرور یک حساب و توکن نشست می گیرد (یوزرنیم تصادفی، مثل مینی اپ)؛
   - ورود با تلگرام (لینک ربات و تأیید در تلگرام) یا ایمیل (کد ۶ رقمی): GCApp.login، برگه اش در gc.js؛
   - آدرس سرور: صفحه ها داخل برنامه اند، API و عکس پروفایل از سرور (GCApp.srv)؛
   - نوار وضعیت گوشی: رنگ آیکن ها با زمینهٔ صفحه (GCApp.bars)؛
   - آپدیت خودکار: نسخهٔ تازهٔ صفحه ها و بازی ها از سرور دانلود و نگه داشته می شود و دفعهٔ بعد که
     برنامه باز شد استفاده می شود؛ اگر نسخهٔ تازه به خود برنامه (کد اندروید) نیاز داشت، کاربر به مایکت می رود. */
(function () {
  const cfg = window.GC_APP;
  if (!cfg || !cfg.base) return;
  const C = window.Capacitor;
  const native = !!(C && C.isNativePlatform && C.isNativePlatform() && C.nativePromise);
  const call = (plugin, method, opt) => native ? C.nativePromise(plugin, method, opt || {}) : Promise.reject(new Error('web'));
  const ls = {
    get(k) { try { return localStorage.getItem(k) || ''; } catch (e) { return ''; } },
    set(k, v) { try { v ? localStorage.setItem(k, String(v)) : localStorage.removeItem(k); } catch (e) {} },
  };
  const STORE = 'myket://details?id=dezhcode.AsoTas.app';
  const STORE_WEB = 'https://myket.ir/app/dezhcode.AsoTas.app';

  // safe area گوشی: همان متغیرهایی که در تلگرام از safeAreaInset پر می شوند. فقط از پلاگین SystemBars
  // (--safe-area-inset-*): وقتی صفحه زیر نوار وضعیت کشیده نمی شود صفر است. env() مرورگر را نه، چون آنجا هم
  // ارتفاع نوار وضعیت را می دهد و فاصلهٔ بالای سربرگ دو برابر می شد
  const css = document.createElement('style');
  css.textContent = ':root{--sa-t:var(--safe-area-inset-top,0px);--sa-b:var(--safe-area-inset-bottom,0px);'
    + '--sa-l:var(--safe-area-inset-left,0px);--sa-r:var(--safe-area-inset-right,0px)}'
    + 'html.app-boxed{--sa-t:0px;--sa-b:0px;--sa-l:0px;--sa-r:0px}';
  document.head.appendChild(css);
  document.documentElement.classList.add('app');
  // صفحه زیر نوار وضعیت و نوار پایین گوشی کشیده شده؟ اگر نه (برنامه بین دو نوار است) فاصلهٔ بالا و پایین صفر،
  // هر چه گوشی گزارش کند. بلندترین ارتفاع دیده شده حساب می شود تا باز شدن کیبورد اشتباهش نیندازد
  let tallest = 0;
  const edge = () => {
    tallest = Math.max(tallest, innerHeight || 0);
    document.documentElement.classList.toggle('app-boxed', !!screen.height && screen.height - tallest > 16);
  };
  edge();
  addEventListener('resize', edge);
  addEventListener('orientationchange', () => { tallest = 0; setTimeout(edge, 300); });
  // نگه داشتن انگشت: منوی کپی و ذخیرهٔ عکس نه (جای نوشتن همان رفتار عادی را دارد)
  addEventListener('contextmenu', e => { if (!e.target.closest('input,textarea,[contenteditable="true"]')) e.preventDefault(); }, true);

  // ---------- حساب مهمان و توکن ----------
  const KEY = 'gc_app_token';
  let pending = null;
  function device() {
    const m = /Android [\d.]+; ([^;)]+)/.exec(navigator.userAgent || '');
    return (m ? m[1] : 'Android').slice(0, 40);
  }
  /* توکن نشست؛ fresh یعنی توکن قبلی دیگر کار نمی کند (مثلا سرور گفت ۴۰۱) و حساب مهمان تازه لازم است */
  function token(fresh) {
    if (fresh) ls.set(KEY, '');
    const t = ls.get(KEY);
    if (t) return Promise.resolve(t);
    if (!pending) {
      pending = fetch(cfg.base + 'app/guest', {
        method: 'POST', cache: 'no-store', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ device: device() }),
      }).then(r => r.ok ? r.json() : Promise.reject(Object.assign(new Error('guest'), { code: r.status === 429 ? 'rate' : 'server' })))
        .then(j => { ls.set(KEY, j.token); return j.token; })
        .finally(() => { pending = null; });
    }
    return pending;
  }
  // ---------- ورود با تلگرام و ایمیل (appauth.py) ----------
  async function post(path, body) {
    let r;
    try {
      r = await fetch(cfg.base + path, {
        method: 'POST', cache: 'no-store', headers: { 'Content-Type': 'application/json', 'X-GC-Token': ls.get(KEY) },
        body: JSON.stringify(body || {}),
      });
    } catch (e) { throw Object.assign(new Error('network'), { code: 'network' }); }
    let j = {};
    try { j = await r.json(); } catch (e) {}
    if (!r.ok) throw Object.assign(new Error(j.error || 'server'), { code: r.status === 429 ? 'rate' : (j.error || 'server'), extra: j });
    return j;
  }
  // توکن تازه جای توکن قبلی این گوشی می نشیند؛ صفحه بعدش از نو بار می شود تا همه چیز مال حساب تازه باشد
  const keep = j => { if (j && j.token) ls.set(KEY, j.token); return j; };
  const login = {
    tg: () => post('app/login/tg', { device: device() }),
    tgCheck: poll => post('app/login/tg/check', { poll }).then(keep),
    email: email => post('app/login/email', { email }),
    emailVerify: (email, code) => post('app/login/email/verify', { email, code, device: device() }).then(keep),
    logout: () => post('app/logout').catch(() => {}).then(() => { ls.set(KEY, ''); }),
    // لینک t.me بیرون از برنامه باز می شود (اپ تلگرام، وگرنه مرورگر)
    open: url => { try { window.open(url, '_blank'); } catch (e) { location.href = url; } },
  };

  // آدرس هایی که سرور می دهد (عکس پروفایل، عکس پیام پاپ آپ) نسبی اند؛ داخل برنامه باید از سرور بیایند
  const srv = u => (u && /^(pic|media)\//.test(u)) ? cfg.base + u : u;

  // ---------- نوار وضعیت و ناوبری گوشی ----------
  function bars(bg) {
    const h = String(bg || '').replace('#', '');
    if (h.length !== 6) return;
    const [r, g, b] = [0, 2, 4].map(i => parseInt(h.slice(i, i + 2), 16));
    const dark = (0.299 * r + 0.587 * g + 0.114 * b) < 150;
    call('SystemBars', 'setStyle', { style: dark ? 'DARK' : 'LIGHT' }).catch(() => {});
    // رنگ پنجره پشت نوار وضعیت و نوار پایین (برنامه از نسخهٔ ۴ به بعد؛ نسخهٔ قدیمی تر این پلاگین را ندارد)
    call('AsoUi', 'background', { color: '#' + h }).catch(() => {});
  }

  // ---------- نسخهٔ تازهٔ برنامه از مایکت ----------
  function storeBar() {
    if (document.getElementById('gcStore')) return;
    const el = document.createElement('div');
    el.id = 'gcStore';
    el.setAttribute('role', 'status');
    el.style.cssText = 'position:fixed;left:12px;right:12px;bottom:calc(var(--sa-b,0px) + 84px);z-index:99999;display:flex;gap:10px;align-items:center;'
      + 'padding:12px 14px;border-radius:16px;background:#1B2340;color:#fff;font:600 14px/1.5 Peyda,system-ui,sans-serif;box-shadow:0 10px 30px rgba(0,0,0,.35);direction:rtl';
    el.innerHTML = '<span style="flex:1">نسخهٔ تازهٔ برنامه اومده داش از مایکت آپدیتش کن</span>'
      + '<button type="button" style="border:0;border-radius:12px;padding:8px 14px;background:#FFC93C;color:#1B2340;font:inherit">آپدیت کن</button>'
      + '<button type="button" aria-label="بستن" style="border:0;background:none;color:#fff;font:inherit;padding:4px 6px">✕</button>';
    const [go, x] = el.querySelectorAll('button');
    go.onclick = () => { try { window.open(STORE, '_blank'); } catch (e) { window.open(STORE_WEB, '_blank'); } };
    x.onclick = () => el.remove();
    document.body.appendChild(el);
  }

  // ---------- خرید سکه از مایکت: پلاگین MyketBilling خود برنامه (از نسخهٔ ۲؛ نسخهٔ قدیمی تر ندارد) ----------
  // key کلید عمومی مایکت از سرور (me.settings.iap.key)؛ خطاها کد دارند: cancelled، owned، unavailable، item، failed
  const iap = {
    ok: () => native && !!(C.isPluginAvailable && C.isPluginAvailable('MyketBilling')),
    buy: (key, sku, payload) => call('MyketBilling', 'purchase', { key, sku, payload }),
    owned: key => call('MyketBilling', 'owned', { key }),
    consume: (key, p) => call('MyketBilling', 'consume', { key, json: p.json, signature: p.signature }),
    update: () => { try { window.open(STORE, '_blank'); } catch (e) { window.open(STORE_WEB, '_blank'); } },
  };

  // ---------- نوتیفیکیشن گوشی: پلاگین AsoPush خود برنامه (فایربیس؛ از نسخهٔ ۳ برنامه) ----------
  // register: اجازه و توکن (quiet = بی پرسیدن اجازه)؛ remind: یادآوری جایزهٔ روزانه؛ onOpen: لمس نوتیفیکیشن
  const push = {
    ok: () => native && !!(C.isPluginAvailable && C.isPluginAvailable('AsoPush')),
    register: quiet => call('AsoPush', 'register', { quiet: !!quiet }),
    remind: (at, title, body) => call('AsoPush', 'remind', { at, title, body }),
    unremind: () => call('AsoPush', 'unremind'),
    // برنامهٔ بسته هم نوتیفیکیشن بگیرد: وضعیت و باز کردن تنظیمات گوشی (برنامه از نسخهٔ ۷)
    status: () => call('AsoPush', 'status'),
    open: what => call('AsoPush', { battery: 'openBattery', autostart: 'openAutostart', notify: 'openNotify' }[what]),
    onOpen(fn) {
      if (!push.ok()) return;
      try {
        const cb = e => fn((e && e.page) || '');
        if (C.addListener) C.addListener('AsoPush', 'open', cb);
        else if (C.Plugins && C.Plugins.AsoPush) C.Plugins.AsoPush.addListener('open', cb);
      } catch (e) {}
    },
  };

  // ---------- لینک اتاق (asotas://room/<کد> از صفحهٔ /r/<کد> سرور) و منوی اشتراک گذاری گوشی ----------
  const roomOf = u => { const m = /^asotas:\/\/room\/([A-Za-z0-9]{4,12})/.exec(String(u || '')); return m ? m[1].toUpperCase() : ''; };
  const links = {
    // fn(کد اتاق): وقتی برنامه با لینک اتاق باز شد یا وقتی باز بود و لینک رسید
    onRoom(fn) {
      if (!native) return;
      call('App', 'getLaunchUrl').then(r => { const c = roomOf(r && r.url); if (c && ls.get('gc_room_seen') !== c) { ls.set('gc_room_seen', c); fn(c); } }).catch(() => {});
      try {
        const cb = e => { const c = roomOf(e && e.url); if (c) { ls.set('gc_room_seen', c); fn(c); } };
        if (C.addListener) C.addListener('App', 'appUrlOpen', cb);
        else if (C.Plugins && C.Plugins.App) C.Plugins.App.addListener('appUrlOpen', cb);
      } catch (e) {}
    },
  };
  const share = o => native && C.isPluginAvailable && C.isPluginAvailable('Share')
    ? call('Share', 'share', { title: o.title || 'AsoTas', text: o.text || '', url: o.url || undefined, dialogTitle: o.title || 'فرستادن' })
    : Promise.reject(new Error('web'));

  // ---------- آپدیت خودکار صفحه ها و بازی ها ----------
  const OTA_EVERY = 5 * 60e3;
  async function ota() {
    if (Date.now() - (+ls.get('gc_ota_at') || 0) < OTA_EVERY) {
      if (ls.get('gc_ota_store')) storeBar();
      return;
    }
    ls.set('gc_ota_at', Date.now());
    const r = await fetch(cfg.base + 'app/manifest', { cache: 'no-store' });
    if (!r.ok) return;
    const m = await r.json();
    ls.set('gc_ota_store', '');
    if (!m.version || m.version === cfg.bundle) return;
    const info = await call('App', 'getInfo').catch(() => ({}));
    if ((+m.min_native || 0) > (+info.build || 0)) { ls.set('gc_ota_store', '1'); storeBar(); return; }
    const list = await call('CapacitorUpdater', 'list').catch(() => ({ bundles: [] }));
    let b = (list.bundles || []).find(x => x.version === m.version && x.status !== 'error');
    if (!b) b = await call('CapacitorUpdater', 'download', { url: cfg.base + m.url, version: m.version, checksum: m.sha256 });
    // دفعهٔ بعد که برنامه باز شد (یا از پس زمینه برگشت) نسخهٔ تازه بالا می آید
    await call('CapacitorUpdater', 'next', { id: b.id });
  }
  if (native) {
    // این نسخه سالم بالا آمد؛ اگر صفحه تا چند ثانیه بالا نیاید، برنامه خودش به نسخهٔ قبلی برمی گردد
    addEventListener('DOMContentLoaded', () => { call('CapacitorUpdater', 'notifyAppReady').catch(() => {}); });
    addEventListener('load', () => { setTimeout(() => ota().catch(() => {}), 1500); });
  }

  window.GCApp = { base: cfg.base, bundle: cfg.bundle, native, call, token, srv, bars, login, iap, push, links, share };
})();
