/* ساختن تصویرهای پیش نمایش بازی ها از خودِ بازی ها (کاشی های خانه و بنر لابی ها).
   میز و توپ و چوب بیلیارد، زمین و مهره و توپ فوتبال عیناً از رندر واقعی بازی بریده می شوند تا
   پیش نمایش با تم بازی یکی باشد. خروجی PNG در پوشهٔ داده شده؛ make_previews.py آن ها را webp می کند.

   اجرا (از ریشهٔ مخزن):
     (cd game_club/webapp && python3 -m http.server 8765) &
     NODE_PATH=$(npm root -g) node game_club/tools/make_previews.js /tmp/pv
     python3 game_club/tools/make_previews.py /tmp/pv game_club/webapp/static/previews
*/
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const OUT = process.argv[2] || '/tmp/pv';
const BASE = process.env.GC_URL || 'http://localhost:8765/';
fs.mkdirSync(OUT, { recursive: true });
const save = (name, dataUrl) => fs.writeFileSync(path.join(OUT, name), Buffer.from(dataUrl.split(',')[1], 'base64'));

// بازی نمونه (demo) را بدون لابی شروع کن
const seed = g => `(async()=>{})();try{const o=GC.demo.${g};const m=o.match.bind(o);let s=0;o.match=async(...a)=>{if(!s){s=1;try{await o.queueJoin({mode:'free',entry:0,players:2,pawns:2,target:3});await o.queueBots();}catch(e){}}a[0]=null;return m(...a);};}catch(e){}\n`;

async function billiard(b) {
  const p = await b.newPage({ viewport: { width: 1200, height: 2560 }, deviceScaleFactor: 2.5 });
  await p.route('**/static/billiard.js', async r => {
    const res = await r.fetch();
    let t = await res.text();
    t = t.replace('function aimAt(x, y) {', 'window.__BL = { balls, toS, cv, ART, AT, R, W, H, get s() { return s; }, get dpr() { return dpr; } };\nfunction aimAt(x, y) {');
    r.fulfill({ response: res, body: seed('billiard') + t, headers: { 'content-type': 'application/javascript' } });
  });
  await p.goto(BASE + 'billiard.html');
  await p.waitForFunction(() => window.__BL && window.__BL.ART.ui && window.__BL.ART.table, null, { timeout: 20000 });
  await p.waitForTimeout(2500);
  // بازی هر ثانیه وضعیت را دوباره می گذارد؛ پس چیدن و بریدن در همان دو فریم انجام می شود
  const raf2 = 'await new Promise(ok => requestAnimationFrame(() => requestAnimationFrame(ok)));';
  // میز خالی (بی توپ، بی چوب و خط)
  save('bl-table.png', await p.evaluate(new Function(`return (async () => {
    for (const x of window.__BL.balls) x.on = false; ${raf2}
    const B = window.__BL, k = B.dpr, [x0, y0] = B.toS(0, 0), [x1, y1] = B.toS(B.W, B.H);
    const c = document.createElement('canvas'); c.width = Math.round((x1 - x0) * k); c.height = Math.round((y1 - y0) * k);
    c.getContext('2d').drawImage(B.cv, x0 * k, y0 * k, c.width, c.height, 0, 0, c.width, c.height);
    return c.toDataURL('image/png');
  })()`)));
  // توپ ها یکی یکی وسط میز، شماره رو به بیننده
  for (const k of [0, 1, 2, 3, 8, 9, 10, 11, 13]) {
    save(`bl-ball-${k}.png`, await p.evaluate(new Function('n', `return (async () => {
      const B = window.__BL; for (const x of B.balls) x.on = false; const o = B.balls[n];
      o.on = true; o.sink = null; o.x = B.W / 2; o.y = B.H / 2; o.q = [0, 0, 1, 0]; o._rc = null; o._pc = null; ${raf2}
      const k = B.dpr, [cx, cy] = B.toS(B.W / 2, B.H / 2), r = B.R * B.s * k * 1.02;
      const c = document.createElement('canvas'); c.width = c.height = Math.ceil(r * 2); const g = c.getContext('2d');
      g.beginPath(); g.arc(r, r, r, 0, Math.PI * 2); g.clip();
      g.drawImage(B.cv, cx * k - r, cy * k - r, r * 2, r * 2, 0, 0, r * 2, r * 2);
      return c.toDataURL('image/png');
    })()`), k));
  }
  // چوب: همان اسپرایت اطلس پلاتو
  save('bl-cue.png', await p.evaluate(() => {
    const B = window.__BL, [x, y, w, h] = B.AT.cs_basic;
    const c = document.createElement('canvas'); c.width = w; c.height = h;
    c.getContext('2d').drawImage(B.ART.ui, x, y, w, h, 0, 0, w, h);
    return c.toDataURL('image/png');
  }));
  await p.close();
}

async function football(b) {
  const p = await b.newPage({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 3 });
  await p.route('**/static/football.js', async r => {
    const res = await r.fetch();
    let t = await res.text();
    t = t.replace('function drawBall(el) {', 'window.__FB = { discHtml: (...a) => discHtml(...a), ballSvg: () => ballSvg(), drawBall: el => drawBall(el) };\nfunction drawBall(el) {');
    r.fulfill({ response: res, body: seed('football') + t, headers: { 'content-type': 'application/javascript' } });
  });
  await p.goto(BASE + 'football.html');
  await p.waitForFunction(() => window.__FB, null, { timeout: 20000 });
  await p.waitForTimeout(2500);
  // زمین: بی لایه های روی صفحه و بی مهره و توپ
  await p.addStyleTag({ content: '.fb-layer,.fb-setup,.fb-vs,.toast,.sheet,.scrim{display:none!important} #pitch .fd,#pitch .fb-ball,#pitch .fb-halo{visibility:hidden!important}' });
  await p.waitForTimeout(300);
  await p.locator('#pitch').screenshot({ path: path.join(OUT, 'fb-pitch.png') });
  // مهره ها و توپ روی زمینهٔ شفاف
  await p.evaluate(() => {
    document.documentElement.style.background = 'transparent'; document.body.style.background = 'transparent';
    for (const el of document.body.children) el.style.visibility = 'hidden';
    const box = document.createElement('div'); box.id = 'cap'; box.style.cssText = 'position:fixed;left:0;top:0;visibility:visible;display:flex;gap:30px;padding:20px;background:transparent';
    const one = (id, html, size) => `<div id="${id}" style="position:relative;width:${size}px;height:${size}px">${html}</div>`;
    box.innerHTML = one('d1', window.__FB.discHtml('eagles', 'home', 120), 120) + one('d2', window.__FB.discHtml('lions', 'home', 120), 120)
      + one('ball', `<span class="fb-ball" style="width:56px;height:56px"><i class="sh"></i>${window.__FB.ballSvg()}</span>`, 56);
    document.body.appendChild(box);
    window.__FB.drawBall(box.querySelector('.fb-ball'));   // نقش واقعی توپ (پنج ضلعی ها و درزها)
  });
  await p.waitForTimeout(300);
  for (const [id, name] of [['d1', 'fb-disc-eagles'], ['d2', 'fb-disc-lions'], ['ball', 'fb-ball']]) {
    const bb = await p.locator('#' + id).boundingBox();
    const pad = id === 'ball' ? 6 : 12;
    await p.screenshot({ path: path.join(OUT, name + '.png'), omitBackground: true, clip: { x: bb.x - pad / 2, y: bb.y - pad / 2, width: bb.width + pad, height: bb.height + pad } });
  }
  await p.close();
}

(async () => {
  const b = await chromium.launch(process.env.CHROMIUM ? { executablePath: process.env.CHROMIUM } : {});
  await billiard(b);
  await football(b);
  await b.close();
  console.log('ok', fs.readdirSync(OUT).join(' '));
})();
