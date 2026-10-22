/* Game Club — service worker: فایل های بازی روی خود گوشی می مانند تا بازی ها بی معطلی باز شوند.
   - فایل های نسخه دار (?v=<هش>؛ همهٔ css و js صفحه ها): از حافظهٔ گوشی، بی پرسش از سرور؛
     با آمدن نسخهٔ تازهٔ یک فایل، نسخهٔ قبلی همان فایل پاک می شود.
   - بقیهٔ فایل های ثابت (عکس، صدا، فونت): همان لحظه از حافظه، و در پس زمینه از سرور تازه می شوند.
   - صفحه ها: همیشه اول از سرور (تازه)؛ فقط اگر اینترنت قطع بود، آخرین نسخهٔ ذخیره شده.
   - API، عکس پروفایل و هر چیز دیگر دست نمی خورد.
   با تغییر رفتار همین فایل، CACHE را عوض کن تا حافظهٔ قبلی پاک شود. */
const CACHE = 'gc-1';
const SCOPE = new URL(self.registration.scope).pathname;

self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', e => e.waitUntil((async () => {
  for (const k of await caches.keys()) if (k !== CACHE) await caches.delete(k);
  await self.clients.claim();
})()));

self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET' || req.headers.has('range')) return;
  const u = new URL(req.url);
  if (u.origin !== location.origin || !u.pathname.startsWith(SCOPE)) return;
  const rest = u.pathname.slice(SCOPE.length);
  if (rest.startsWith('static/')) e.respondWith(u.searchParams.has('v') ? versioned(req, u) : fresh(req, e));
  else if (req.mode === 'navigate') e.respondWith(page(req, u));
});

const keep = (c, key, res) => { if (res.status === 200) c.put(key, res.clone()).catch(() => {}); };

async function versioned(req, u) {
  const c = await caches.open(CACHE), hit = await c.match(req);
  if (hit) return hit;
  const res = await fetch(req);
  if (res.status === 200) {
    const base = u.origin + u.pathname + '?';
    for (const k of await c.keys()) if (k.url.startsWith(base) && k.url !== req.url) c.delete(k);
    keep(c, req, res);
  }
  return res;
}

async function fresh(req, e) {
  const c = await caches.open(CACHE), hit = await c.match(req);
  const net = fetch(req).then(res => { keep(c, req, res); return res; });
  if (hit) { e.waitUntil(net.catch(() => {})); return hit; }
  return net;
}

async function page(req, u) {
  const c = await caches.open(CACHE);
  try {
    const res = await fetch(req);
    keep(c, u.pathname, res);
    return res;
  } catch (err) {
    return (await c.match(u.pathname)) || Response.error();
  }
}
