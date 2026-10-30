/* آموزش بار اول هر بازی، روی خود صفحهٔ بازی (مثل بازی های حرفه ای):
   - کارت خوش آمد با تصویر بازی: «یادم بده» یا «بلدم، بریم».
   - هر قدم یک تکهٔ واقعی صفحه را روشن می کند (بقیه تاریک)، کارت توضیح کنارش می آید و یک دست
     متحرک حرکت لازم را نشان می دهد: ضربه (tap)، نگه داشتن (hold)، کشیدن (drag).
   - شمارهٔ قدم، نوار پیشرفت، «قبلی»، «بعدی» و «رد کن»؛ لمس هر جای تاریک = قدم بعد.
   - وقت نوبت را نمی سوزاند: وقتی نوبت خودت است و وقتت کم شده (pauseAt)، آموزش کنار می رود و
     یک دکمهٔ کوچک «ادامهٔ آموزش» می ماند؛ نوبتت که تمام شد، خودش برمی گردد. برگهٔ باز (sheet) هم آن را نگه می دارد.
   - یک بار برای هر بازی (store: tour_<id>)؛ از دکمهٔ راهنمای خود بازی دوباره پخش می شود.
   استفاده: GCTour.auto({ id, name, color, steps, turn, ready, help }) یا GCTour.start(همان) برای پخش دوباره.
   قدم: { el: انتخابگر | () => عنصر | () => {x, y, w, h}، title، text (یا تابع)، hand: 'tap' | 'hold' | {type: 'drag', from: [0.5, 0.5], to: [0.5, 0.1]}،
          at: [fx, fy] جای دست روی هدف، pad، round، before: () => void (آماده کردن صفحه)، when: () => bool } */
window.GCTour = (() => {
  const FD = n => (window.GC ? GC.FD(n) : String(n));
  const store = {
    get: k => { try { return window.GC ? GC.store.get(k, false) : JSON.parse(localStorage.getItem(k) || 'false'); } catch (e) { return false; } },
    set: (k, v) => { try { window.GC ? GC.store.set(k, v) : localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} },
  };
  const HAND = '<svg viewBox="0 0 48 60" aria-hidden="true"><path d="M15 4c2.8 0 5 2.2 5 5v17.5l2.2-.9c1.9-.8 4 .2 4.8 2l.3.7 1.3-.5c1.9-.7 4 .2 4.8 2.1l.2.5 1-.3c2.1-.6 4.3.7 4.8 2.8l2.6 10.6c1.4 5.8-1.3 11.8-6.5 14.6l-1.3.7c-2.1 1.1-4.4 1.7-6.8 1.7h-5.3c-4.1 0-7.9-2-10.2-5.4L4.2 37.3c-1.3-1.9-.9-4.5 1-5.9 1.8-1.3 4.3-1.1 5.8.6L10 32V9c0-2.8 2.2-5 5-5z" fill="#fff" stroke="#1C2235" stroke-width="2.4" stroke-linejoin="round"/><path d="M20 26.5V34M27.3 28.4V35M33.6 30.7V36" stroke="#1C2235" stroke-width="2" stroke-linecap="round" opacity=".35"/></svg>';
  const CSS = `
.gt-root{position:fixed;inset:0;z-index:9000;font-family:var(--font-peyda,inherit);direction:rtl;-webkit-tap-highlight-color:transparent;--acc:#FFC531;--acc-ink:#1C2235}
.gt-root[hidden],.gt-pill[hidden]{display:none}
.gt-hole{position:fixed;border-radius:18px;box-shadow:0 0 0 200vmax rgba(9,11,20,.76);pointer-events:none;
  transition:left .45s cubic-bezier(.3,.9,.3,1),top .45s cubic-bezier(.3,.9,.3,1),width .45s cubic-bezier(.3,.9,.3,1),height .45s cubic-bezier(.3,.9,.3,1),border-radius .45s,box-shadow .3s}
.gt-hole::after{content:"";position:absolute;inset:-4px;border-radius:inherit;border:2.5px solid var(--acc);box-shadow:0 0 18px var(--acc);animation:gt-glow 1.6s ease-in-out infinite}
.gt-hole.none::after{display:none}
@keyframes gt-glow{50%{opacity:.35;inset:-9px}}
.gt-card{position:fixed;width:min(344px,calc(100vw - 24px));box-sizing:border-box;background:#fff;color:#1C2235;border-radius:22px;padding:14px 16px 12px;
  box-shadow:0 18px 48px rgba(0,0,0,.45);transition:left .35s,top .35s;animation:gt-pop .38s cubic-bezier(.3,1.4,.5,1)}
.gt-card.mid{left:50%!important;top:50%!important;transform:translate(-50%,-50%);transition:none;animation:gt-popc .42s cubic-bezier(.3,1.4,.5,1)}
@keyframes gt-pop{from{opacity:0;transform:translateY(10px) scale(.94)}}
@keyframes gt-popc{from{opacity:0;transform:translate(-50%,-46%) scale(.92)}}
.gt-arrow{position:absolute;width:16px;height:16px;background:#fff;transform:rotate(45deg);border-radius:3px}
.gt-card.below .gt-arrow{top:-7px}.gt-card.above .gt-arrow{bottom:-7px}.gt-card.mid .gt-arrow{display:none}
.gt-top{display:flex;align-items:center;gap:8px;margin-bottom:6px}
.gt-step{font-size:12px;font-weight:800;color:#5B6178;background:#F1F2F7;border-radius:999px;padding:2px 10px;font-variant-numeric:tabular-nums}
.gt-skip{margin-inline-start:auto;border:0;background:none;font:inherit;font-size:13px;font-weight:800;color:#7A8096;padding:6px 2px;cursor:pointer}
.gt-card h3{margin:0 0 4px;font-family:var(--font-rokh,inherit);font-weight:900;font-size:19px;line-height:27px}
.gt-card p{margin:0;font-size:13.5px;line-height:23px;color:#424862}
.gt-card p b{color:#1C2235}
.gt-turn{margin-top:8px;display:flex;align-items:center;gap:6px;font-size:12.5px;font-weight:800;color:#B3261E;background:#FFF0EE;border-radius:12px;padding:6px 10px}
.gt-turn button{margin-inline-start:auto;border:0;background:#B3261E;color:#fff;font:inherit;font-size:12px;font-weight:800;border-radius:999px;padding:4px 10px;cursor:pointer}
.gt-foot{display:flex;align-items:center;gap:8px;margin-top:12px}
.gt-bar{flex:1;height:5px;border-radius:3px;background:#ECEDF3;overflow:hidden}
.gt-bar i{display:block;height:100%;border-radius:3px;background:var(--acc);transition:width .4s}
.gt-btn{height:40px;border:0;border-radius:14px;font:inherit;font-weight:900;font-size:14.5px;padding:0 16px;cursor:pointer;box-shadow:0 3px 0 rgba(0,0,0,.18)}
.gt-btn:active{transform:translateY(2px);box-shadow:none}
.gt-next{background:var(--acc);color:var(--acc-ink)}
.gt-back{background:#F1F2F7;color:#424862;box-shadow:none;padding:0 12px}
.gt-intro{text-align:center;padding:20px 18px 16px}
.gt-art{width:92px;height:92px;margin:-62px auto 8px;border-radius:28px;overflow:hidden;box-shadow:0 10px 26px rgba(0,0,0,.35),0 0 0 5px #fff;background:#fff}
.gt-art>*{width:100%!important;height:100%!important;border-radius:0!important}
.gt-kick{display:inline-block;font-size:12px;font-weight:800;color:#5B6178;background:#F1F2F7;border-radius:999px;padding:3px 12px;margin-bottom:6px}
.gt-intro h3{font-size:23px;line-height:32px}
.gt-intro .gt-foot{flex-direction:column;align-items:stretch;gap:6px}
.gt-intro .gt-btn{height:46px;font-size:16px}
.gt-ghost{background:none;box-shadow:none;color:#5B6178;font-weight:800;font-size:14px;height:36px}
.gt-done{width:64px;height:64px;margin:0 auto 8px;border-radius:50%;background:var(--acc);display:grid;place-items:center;color:var(--acc-ink);
  box-shadow:0 0 0 8px color-mix(in srgb,var(--acc) 25%,transparent);animation:gt-burst .6s cubic-bezier(.3,1.6,.5,1)}
.gt-done svg{width:34px;height:34px}
@keyframes gt-burst{from{transform:scale(.3);opacity:0}}
.gt-link{display:block;margin-top:2px;font-size:13px;font-weight:800;color:#1668D9;text-decoration:none}
.gt-hand{position:fixed;width:46px;height:58px;pointer-events:none;z-index:2;filter:drop-shadow(0 6px 8px rgba(0,0,0,.45));transform-origin:15px 4px}
.gt-hand svg{width:100%;height:100%;display:block}
.gt-rip{position:fixed;width:56px;height:56px;margin:-28px 0 0 -28px;border-radius:50%;border:3px solid #fff;pointer-events:none;opacity:0}
.gt-hand.tap{animation:gt-tap 1.5s ease-in-out infinite}
.gt-rip.tap{animation:gt-rip 1.5s ease-out infinite}
@keyframes gt-tap{0%,100%{transform:translate(10px,14px)}40%{transform:translate(0,0) scale(.92)}55%{transform:translate(0,0) scale(.92)}75%{transform:translate(10px,14px)}}
@keyframes gt-rip{0%,38%{opacity:0;transform:scale(.3)}45%{opacity:.9}90%,100%{opacity:0;transform:scale(1.5)}}
.gt-hand.hold{animation:gt-hold 2.2s ease-in-out infinite}
.gt-rip.hold{border-color:var(--acc);animation:gt-holdr 2.2s ease-out infinite}
@keyframes gt-hold{0%,100%{transform:translate(10px,14px)}18%,78%{transform:translate(0,0) scale(.9)}}
@keyframes gt-holdr{0%,18%{opacity:0;transform:scale(1.4)}25%{opacity:.95}75%{opacity:.95;transform:scale(.55)}85%,100%{opacity:0;transform:scale(.55)}}
.gt-hand.drag{animation:gt-drag 2.2s cubic-bezier(.45,0,.3,1) infinite}
@keyframes gt-drag{0%{transform:translate(10px,14px);opacity:0}12%{transform:translate(0,0) scale(.92);opacity:1}22%{transform:translate(0,0) scale(.92)}72%{transform:translate(var(--dx),var(--dy)) scale(.92);opacity:1}86%{transform:translate(var(--dx),var(--dy));opacity:0}100%{opacity:0}}
.gt-trail{position:fixed;left:0;top:0;width:100vw;height:100vh;pointer-events:none;overflow:visible}
.gt-trail path{fill:none;stroke:#fff;stroke-width:3.5;stroke-linecap:round;stroke-dasharray:2 9;opacity:.85}
.gt-trail circle{fill:#fff;opacity:.9}
.gt-pill{position:fixed;z-index:8999;left:50%;transform:translateX(-50%);top:calc(var(--sa-t,0px) + var(--csa-t,0px) + 64px);display:flex;align-items:center;gap:6px;
  border:0;border-radius:999px;background:#1C2235;color:#fff;font:inherit;font-family:var(--font-peyda,inherit);font-size:13px;font-weight:800;padding:8px 8px 8px 14px;
  box-shadow:0 8px 22px rgba(0,0,0,.4);cursor:pointer;animation:gt-pop .3s;direction:rtl;white-space:nowrap;max-width:calc(100vw - 24px)}
.gt-pill span{overflow:hidden;text-overflow:ellipsis}
.gt-pill b{background:var(--acc,#FFC531);color:var(--acc-ink,#1C2235);border-radius:999px;padding:3px 10px}
.gt-pill i{font-style:normal;opacity:.6;padding:0 6px}
@media (prefers-reduced-motion:reduce){.gt-hand,.gt-rip,.gt-hole::after,.gt-card,.gt-done{animation:none!important}.gt-rip{opacity:.8}}`;

  let st = null;
  const seen = id => !!store.get('tour_' + id);
  const mark = id => store.set('tour_' + id, true);
  const esc = s => String(s == null ? '' : s);

  function rectOf(step) {
    let t = typeof step.el === 'function' ? step.el() : step.el ? document.querySelector(step.el) : null;
    if (!t) return null;
    if (t.getBoundingClientRect) {
      if (t.hidden || t.closest('[hidden]')) return null;
      const r = t.getBoundingClientRect();
      t = { x: r.left, y: r.top, w: r.width, h: r.height };
    }
    if (!(t.w > 2 && t.h > 2)) return null;
    // فقط قسمت پیدا (داخل صفحه)
    const x = Math.max(4, t.x), y = Math.max(4, t.y), r2 = Math.min(innerWidth - 4, t.x + t.w), b = Math.min(innerHeight - 4, t.y + t.h);
    return r2 - x > 2 && b - y > 2 ? { x, y, w: r2 - x, h: b - y } : null;
  }

  function build(cfg) {
    if (!document.getElementById('gtCss')) { const s = document.createElement('style'); s.id = 'gtCss'; s.textContent = CSS; document.head.appendChild(s); }
    const root = document.createElement('div');
    root.className = 'gt-root'; root.setAttribute('role', 'dialog'); root.setAttribute('aria-modal', 'true'); root.setAttribute('aria-labelledby', 'gtT');
    root.style.setProperty('--acc', cfg.color || '#FFC531');
    if (cfg.ink) root.style.setProperty('--acc-ink', cfg.ink);
    root.innerHTML = '<div class="gt-hole none"></div><svg class="gt-trail" aria-hidden="true"></svg><span class="gt-rip"></span><div class="gt-hand" hidden>' + HAND + '</div><div class="gt-card"></div>';
    document.body.appendChild(root);
    const pill = document.createElement('button');
    pill.className = 'gt-pill'; pill.hidden = true; pill.style.setProperty('--acc', cfg.color || '#FFC531');
    if (cfg.ink) pill.style.setProperty('--acc-ink', cfg.ink);
    document.body.appendChild(pill);
    return { root, pill, hole: root.querySelector('.gt-hole'), card: root.querySelector('.gt-card'), hand: root.querySelector('.gt-hand'), rip: root.querySelector('.gt-rip'), trail: root.querySelector('.gt-trail') };
  }

  // قدم هایی که هدفشان نیست (مثلا دکمهٔ گفتگو در تماشا) فقط وقتی هدف ندارند و center نخواسته اند حذف می شوند
  // before (مثلا باز کردن تب مداد) پیش از سنجیدن هدف اجرا می شود تا هدفش ساخته شده باشد
  const usable = s => { if (s.when && !s.when()) return false; if (s.before) try { s.before(); } catch (e) {} return s.center || !s.el || !!rectOf(s); };

  function render() {
    const { cfg, ui } = st;
    const i = st.i, steps = st.steps;
    ui.hand.hidden = true; ui.rip.className = 'gt-rip'; ui.trail.innerHTML = '';
    if (i < 0 || i >= steps.length) { // خوش آمد یا پایان
      ui.hole.classList.add('none');
      Object.assign(ui.hole.style, { left: innerWidth / 2 + 'px', top: innerHeight / 2 + 'px', width: '0px', height: '0px' });
      const done = i >= steps.length;
      const aid = cfg.artId || cfg.id;
      const art = cfg.art || (window.GC && GC.GAME_ART && GC.GAME_ART[aid] ? `<span class="g-art ${(GC.GAMES.find(g => g.id === aid) || {}).tint || ''}">${GC.GAME_ART[aid]()}</span>` : '');
      ui.card.className = 'gt-card mid gt-intro';
      ui.card.innerHTML = done
        ? `<div class="gt-done">${window.GC ? GC.icon('check', 3) : '✓'}</div><h3 id="gtT">${esc(cfg.outroTitle || 'آماده‌ای! 🎉')}</h3>
           <p>${esc(cfg.outro || 'همه چی رو بلدی هر وقت خواستی از دکمهٔ راهنمای بالای صفحه دوباره این آموزشو ببین')}</p>
           <div class="gt-foot"><button class="gt-btn gt-next" data-a="end">${esc(cfg.endLabel || 'بزن بریم!')}</button>${cfg.help ? `<a class="gt-link" href="${cfg.help}">قانونای کامل ${esc(cfg.name || '')}</a>` : ''}</div>`
        : `${art ? `<div class="gt-art">${art}</div>` : ''}<span class="gt-kick">آموزش سریع · ${FD(steps.length)} قدم</span>
           <h3 id="gtT">${esc(cfg.introTitle || `به ${cfg.name} خوش اومدی!`)}</h3><p>${esc(cfg.intro || 'یه دور سریع با هم ببینیم چطوری بازی می‌شه و چطوری می‌بری')}</p>
           <div class="gt-foot"><button class="gt-btn gt-next" data-a="next">یادم بده</button><button class="gt-btn gt-ghost" data-a="skip">بلدم بزن بریم</button></div>`;
      bind(); focus(); return;
    }
    const s = steps[i];
    ui.card.className = 'gt-card';
    ui.card.innerHTML = `<span class="gt-arrow"></span><div class="gt-top"><span class="gt-step">${FD(i + 1)} از ${FD(steps.length)}</span><button class="gt-skip" data-a="skip">رد کن</button></div>
      <h3 id="gtT">${esc(s.title)}</h3><p>${typeof s.text === 'function' ? s.text() : s.text}</p><div class="gt-turn" hidden></div>
      <div class="gt-foot">${i > 0 ? '<button class="gt-btn gt-back" data-a="back">قبلی</button>' : ''}<span class="gt-bar"><i style="width:${Math.round((i + 1) * 100 / steps.length)}%"></i></span>
        <button class="gt-btn gt-next" data-a="next">${i === steps.length - 1 ? 'تموم' : 'بعدی'}</button></div>`;
    bind(); turnLine(); place(true); focus();
  }

  function place(fresh) {
    const { ui } = st, s = st.steps[st.i];
    if (!s) return;
    const r = s.el ? rectOf(s) : null, pad = s.pad == null ? 8 : s.pad;
    const key = (r ? [r.x, r.y, r.w, r.h].map(Math.round).join() : 'none') + ':' + ui.card.offsetHeight;
    if (!fresh && key === st.key) return;
    st.key = key;
    const sat = (parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--sa-t')) || 0) + (parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--csa-t')) || 0);
    if (!r) {
      ui.hole.classList.add('none');
      Object.assign(ui.hole.style, { left: innerWidth / 2 + 'px', top: innerHeight / 2 + 'px', width: '0px', height: '0px', borderRadius: '18px' });
      ui.card.classList.add('mid');
      return;
    }
    ui.hole.classList.remove('none');
    const h = { x: r.x - pad, y: r.y - pad, w: r.w + 2 * pad, h: r.h + 2 * pad };
    Object.assign(ui.hole.style, { left: h.x + 'px', top: h.y + 'px', width: h.w + 'px', height: h.h + 'px', borderRadius: (s.round != null ? s.round : Math.min(22, h.h / 2)) + 'px' });
    // کارت: زیر هدف اگر جا هست، وگرنه بالا، وگرنه پایین صفحه روی هدف
    const c = ui.card, cw = c.offsetWidth, ch = c.offsetHeight, m = 12;
    const below = innerHeight - (h.y + h.h) - m, above = h.y - m - sat;
    let top, side;
    if (below >= ch + 10 && (below >= above || above < ch + 10)) { top = h.y + h.h + 12; side = 'below'; }
    else if (above >= ch + 10) { top = h.y - 12 - ch; side = 'above'; }
    else { top = innerHeight - ch - m; side = 'over'; }
    const cx = h.x + h.w / 2, left = Math.max(m, Math.min(innerWidth - cw - m, cx - cw / 2));
    c.classList.remove('mid', 'below', 'above'); if (side !== 'over') c.classList.add(side);
    c.style.left = left + 'px'; c.style.top = top + 'px';
    const ar = c.querySelector('.gt-arrow'); if (ar) { ar.style.left = Math.max(18, Math.min(cw - 34, cx - left - 8)) + 'px'; ar.hidden = side === 'over'; }
    hand(s, r);
  }

  function hand(s, r) {
    const { ui } = st;
    if (!s.hand) { ui.hand.hidden = true; return; }
    const H = typeof s.hand === 'string' ? { type: s.hand } : s.hand;
    const at = H.from || s.at || [0.5, 0.5];
    const x = r.x + r.w * at[0], y = r.y + r.h * at[1];
    ui.hand.hidden = false; ui.hand.className = 'gt-hand ' + H.type;
    ui.hand.style.left = x - 15 + 'px'; ui.hand.style.top = y - 4 + 'px';
    ui.rip.style.left = x + 'px'; ui.rip.style.top = y + 'px';
    ui.rip.className = 'gt-rip' + (H.type === 'drag' ? '' : ' ' + H.type);
    ui.trail.innerHTML = '';
    if (H.type === 'drag') {
      const to = H.to || [0.5, 0.1], tx = r.x + r.w * to[0], ty = r.y + r.h * to[1];
      ui.hand.style.setProperty('--dx', tx - x + 'px'); ui.hand.style.setProperty('--dy', ty - y + 'px');
      ui.trail.innerHTML = `<path d="M${x} ${y}L${tx} ${ty}"/><circle cx="${x}" cy="${y}" r="5"/><circle cx="${tx}" cy="${ty}" r="7" style="fill:none;stroke:#fff;stroke-width:3"/>`;
    }
  }

  function bind() {
    st.ui.card.querySelectorAll('[data-a]').forEach(b => b.addEventListener('click', e => { e.stopPropagation(); act(b.dataset.a); }));
  }
  // فوکوس روی «بعدی» فقط برای کسی که با صفحه کلید کار می کند (لمس، حلقهٔ فوکوس نمی خواهد)
let kb = false;
addEventListener('keydown', () => { kb = true; }, true); addEventListener('pointerdown', () => { kb = false; }, true);
function focus() { const b = st.ui.card.querySelector('.gt-next'); if (b && kb) setTimeout(() => b.focus({ preventScroll: true }), 60); }
  function act(a) {
    if (!st) return;
    if (window.GC) { GC.sfx.tap(); GC.haptic('select'); }
    if (a === 'skip' || a === 'end') return finish();
    if (a === 'pause') return pause(true);
    st.dir = a === 'back' ? -1 : 1;
    let i = st.i + st.dir;
    while (i >= 0 && i < st.steps.length && !usable(st.steps[i])) i += st.dir;
    st.i = Math.max(-1, i); st.shownAt = performance.now();
    render();
  }
  function finish() {
    if (!st) return;
    const s = st; st = null;
    clearInterval(s.timer); removeEventListener('resize', s.onResize); removeEventListener('keydown', s.onKey, true);
    s.ui.root.remove(); s.ui.pill.remove();
    mark(s.cfg.id);
    if (s.cfg.after) try { s.cfg.after(); } catch (e) {}
    s.resolve();
  }

  // ---------- وقت نوبت و برگه های باز ----------
  function pause(byUser, why) {
    if (!st || st.paused) return;
    st.paused = byUser ? 'user' : why || 'turn';
    st.ui.root.hidden = true;
    st.ui.pill.hidden = st.paused === 'sheet';
    st.ui.pill.innerHTML = `<span>${esc(st.cfg.pauseText || 'نوبت توئه! آموزش صبر می‌کنه تا بازیتو بکنی')}</span><b>ادامهٔ آموزش</b><i aria-label="بستن آموزش">✕</i>`;
  }
  function resume() {
    if (!st || !st.paused) return;
    st.paused = null; st.ui.pill.hidden = true; st.ui.root.hidden = false; st.key = ''; render();
  }
  function turnLine() {
    if (!st || !st.cfg.turn) return;
    const t = st.cfg.turn(), el = st.ui.card.querySelector('.gt-turn');
    if (!el) return;
    const on = !!(t && t.mine);
    el.hidden = !on;
    if (on) el.innerHTML = `⏱ نوبت توئه${t.left != null && isFinite(t.left) ? ` · ${FD(Math.max(0, Math.ceil(t.left / 1000)))} ثانیه` : ''}<button data-a="pause">اول بازی کنم</button>`, el.querySelector('button').onclick = e => { e.stopPropagation(); act('pause'); };
  }
  function tick() {
    if (!st) return;
    const { cfg } = st, t = cfg.turn ? cfg.turn() : null, mine = !!(t && t.mine);
    const sheetOpen = !!document.querySelector('.scrim');
    const low = mine && (cfg.pauseAt === Infinity || (t.left != null && t.left <= (cfg.pauseAt || 10000)));
    if (!st.paused && (low || sheetOpen)) pause(false, sheetOpen ? 'sheet' : 'turn');
    else if (st.paused === 'sheet' && !sheetOpen) resume();
    else if (st.paused === 'turn' && !mine) setTimeout(() => { if (st && st.paused === 'turn' && !(cfg.turn && cfg.turn() && cfg.turn().mine)) resume(); }, 900);
    else if (st.paused === 'user' && !mine && st.wasMine) resume();
    if (st) st.wasMine = mine;
    if (st && !st.paused) { turnLine(); place(false); }
  }

  function start(cfg) {
    if (st) finish();
    return new Promise(resolve => {
      const ui = build(cfg);
      st = { cfg, ui, resolve, steps: cfg.steps.slice(), i: -1, key: '', paused: null, shownAt: performance.now(), dir: 1 };
      // لمس جای تاریک = قدم بعد (کمی بعد از آمدن کارت، تا لمس قبلی حساب نشود)
      ui.root.addEventListener('click', e => { if (!e.target.closest('.gt-card') && st && performance.now() - st.shownAt > 500 && st.i >= 0 && st.i < st.steps.length) act('next'); });
      ui.root.addEventListener('pointerdown', e => e.stopPropagation());
      ui.pill.addEventListener('click', e => { if (e.target.tagName === 'I') finish(); else resume(); });
      st.onResize = () => { if (st) { st.key = ''; place(true); } };
      st.onKey = e => {
        if (!st || st.paused) return;
        if (e.key === 'Escape') { e.preventDefault(); finish(); }
        else if (e.key === 'ArrowLeft' || e.key === 'Enter') { e.preventDefault(); act(st.i >= st.steps.length ? 'end' : 'next'); }
        else if (e.key === 'ArrowRight' && st.i > 0) { e.preventDefault(); act('back'); }
      };
      addEventListener('resize', st.onResize); addEventListener('keydown', st.onKey, true);
      st.timer = setInterval(tick, 300);
      if (cfg.skipIntro) act('next'); else render();
    });
  }
  // بار اول: وقتی صفحهٔ بازی آماده شد (ready) و برگه ای باز نبود
  function auto(cfg) {
    if (seen(cfg.id) || cfg.off) return Promise.resolve();
    return new Promise(resolve => {
      const t0 = Date.now();
      const iv = setInterval(() => {
        if (seen(cfg.id)) { clearInterval(iv); return resolve(); }
        if (Date.now() - t0 < (cfg.delay == null ? 900 : cfg.delay)) return;
        if (st || document.querySelector('.scrim') || (cfg.ready && !cfg.ready())) return;   // یک آموزش در هر لحظه
        const t = cfg.turn && cfg.turn();
        if (t && t.mine && (cfg.pauseAt === Infinity || (t.left != null && t.left < (cfg.pauseAt || 10000) + 6000))) return;
        clearInterval(iv); start(cfg).then(resolve);
      }, 400);
    });
  }
  return { start, auto, seen, active: () => !!st, reset: id => store.set('tour_' + id, false) };
})();
