/* برنامهٔ اندروید Game Club (Capacitor). فقط وقتی بار می شود که صفحه ها از داخل برنامه باز شوند؛
   appbundle.py این اسکریپت را به جای SDK تلگرام در هر صفحه می گذارد و app-config.js (GC_APP) را پیش از آن.
   - حساب مهمان: بار اول از سرور یک حساب و توکن نشست می گیرد (یوزرنیم تصادفی، مثل مینی اپ)؛
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
  const STORE = 'myket://details?id=obour.gameclub.app';
  const STORE_WEB = 'https://myket.ir/app/obour.gameclub.app';

  // safe area گوشی (لبه تا لبه): همان متغیرهایی که در تلگرام از safeAreaInset پر می شوند
  const css = document.createElement('style');
  css.textContent = ':root{--sa-t:max(env(safe-area-inset-top,0px),var(--safe-area-inset-top,0px));'
    + '--sa-b:max(env(safe-area-inset-bottom,0px),var(--safe-area-inset-bottom,0px));'
    + '--sa-l:max(env(safe-area-inset-left,0px),var(--safe-area-inset-left,0px));'
    + '--sa-r:max(env(safe-area-inset-right,0px),var(--safe-area-inset-right,0px))}';
  document.head.appendChild(css);
  document.documentElement.classList.add('app');

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
  // آدرس هایی که سرور می دهد (عکس پروفایل، عکس پیام پاپ آپ) نسبی اند؛ داخل برنامه باید از سرور بیایند
  const srv = u => (u && /^(pic|media)\//.test(u)) ? cfg.base + u : u;

  // ---------- نوار وضعیت و ناوبری گوشی ----------
  function bars(bg) {
    const h = String(bg || '').replace('#', '');
    if (h.length !== 6) return;
    const [r, g, b] = [0, 2, 4].map(i => parseInt(h.slice(i, i + 2), 16));
    const dark = (0.299 * r + 0.587 * g + 0.114 * b) < 150;
    call('SystemBars', 'setStyle', { style: dark ? 'DARK' : 'LIGHT' }).catch(() => {});
  }

  // ---------- نسخهٔ تازهٔ برنامه از مایکت ----------
  function storeBar() {
    if (document.getElementById('gcStore')) return;
    const el = document.createElement('div');
    el.id = 'gcStore';
    el.setAttribute('role', 'status');
    el.style.cssText = 'position:fixed;left:12px;right:12px;bottom:calc(var(--sa-b,0px) + 84px);z-index:99999;display:flex;gap:10px;align-items:center;'
      + 'padding:12px 14px;border-radius:16px;background:#1B2340;color:#fff;font:600 14px/1.5 Peyda,system-ui,sans-serif;box-shadow:0 10px 30px rgba(0,0,0,.35);direction:rtl';
    el.innerHTML = '<span style="flex:1">نسخهٔ تازهٔ Game Club آمده؛ از مایکت به‌روزش کن.</span>'
      + '<button type="button" style="border:0;border-radius:12px;padding:8px 14px;background:#FFC93C;color:#1B2340;font:inherit">به‌روزرسانی</button>'
      + '<button type="button" aria-label="بستن" style="border:0;background:none;color:#fff;font:inherit;padding:4px 6px">✕</button>';
    const [go, x] = el.querySelectorAll('button');
    go.onclick = () => { try { window.open(STORE, '_blank'); } catch (e) { window.open(STORE_WEB, '_blank'); } };
    x.onclick = () => el.remove();
    document.body.appendChild(el);
  }

  // ---------- آپدیت خودکار صفحه ها و بازی ها ----------
  const OTA_EVERY = 20 * 60e3;
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

  window.GCApp = { base: cfg.base, bundle: cfg.bundle, native, call, token, srv, bars };
})();
