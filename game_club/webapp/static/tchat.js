/* گفتگوی میز مثل پلاتو؛ یکی برای همهٔ بازی ها (حکم، منچ، فوتبال، بیلیارد).
   - نوار پایین: آیکن گفتگو، «یه چیزی بگو…»، پیام سریع و فلش آبی فرستادن (هنگام نوشتن).
     در بیلیارد همیشه پیداست؛ در بقیه با دکمهٔ گفتگوی خود بازی باز می شود و با زدن بیرونش بسته.
   - پیام ها روی خود بازی شناور می آیند، بالای نوار: پیام بقیه سمت چپ (عکس، نام بالای حباب خاکستری)،
     پیام خودم سمت راست (حباب آبی، نام با ✓ و عکس). چند ثانیه می مانند و محو می شوند؛ وقتی نوار باز است
     چند پیام آخر سر جایشان می مانند.
   استفاده: const chat = TChat.init({ bar, btn, badge, quick, face, send, canSend, onNew, rest }) */
const TChat = (() => {
  const ICON = {
    chat: '<svg viewBox="0 0 32 32" fill="none" stroke="#3fbf6a" stroke-width="2.4" stroke-linejoin="round"><path d="M5 6h22v16H12l-7 5z"/><path d="M10 12h12M10 17h8" stroke-linecap="round"/></svg>',
    sticker: '<svg viewBox="0 0 32 32" fill="none" stroke="#bdbdbd" stroke-width="2.4" stroke-linejoin="round"><path d="M7 4h18a3 3 0 0 1 3 3v12l-9 9H7a3 3 0 0 1-3-3V7a3 3 0 0 1 3-3z"/><path d="M28 19h-6a3 3 0 0 0-3 3v6"/></svg>',
    send: '<svg viewBox="0 0 32 32"><path d="M4 4.5 29 16 4 27.5l3.6-11.5z" fill="#2E8BFF"/><path d="M7.6 16H17" stroke="#141414" stroke-width="2.2" stroke-linecap="round"/></svg>',
  };
  const esc = t => String(t == null ? '' : t).replace(/[&<>"']/g, x => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[x]));
  const life = t => Math.min(9000, Math.max(5000, 3600 + String(t).length * 90));
  const KEEP = 5;

  function init(o) {
    let last = 0, log = [], unread = 0, sending = false, open = false;
    const persistent = !!o.bar;
    const live = new Map();   // id -> {el, timer}

    // ---------- نوار ----------
    const bar = o.bar || document.createElement('form');
    bar.classList.add('tc-bar'); if (!persistent) bar.classList.add('tc-float');
    bar.innerHTML = `<button type="button" class="tc-ic" aria-label="گفتگو">${ICON.chat}${persistent && o.badge == null ? '<span class="badge" hidden></span>' : ''}</button>
      <input class="tc-in" maxlength="140" placeholder="یه چیزی بگو…" autocomplete="off" enterkeyhint="send" aria-label="پیام" dir="auto">
      <button type="button" class="tc-q" aria-label="پیام سریع">${ICON.sticker}</button>
      <button type="submit" class="tc-send" aria-label="فرستادن">${ICON.send}</button>`;
    if (!o.bar) document.body.appendChild(bar);
    const input = bar.querySelector('.tc-in');
    const badgeEl = o.badge || bar.querySelector('.badge');

    const feed = document.createElement('div');
    feed.className = 'tc-feed'; feed.setAttribute('aria-live', 'polite');
    document.body.appendChild(feed);

    const pop = document.createElement('div');
    pop.className = 'tc-quick'; pop.hidden = true;
    pop.innerHTML = (o.quick || []).map(q => `<button type="button" data-q>${esc(q)}</button>`).join('');
    document.body.appendChild(pop);

    // پس زمینهٔ تیره پشت نوار و پیام ها وقتی گفتگو باز است (مثل پلاتو)؛ لمسش گفتگو را می بندد
    const dim = document.createElement('div');
    dim.className = 'tc-dim';
    if (persistent) bar.parentNode.insertBefore(dim, bar); else document.body.appendChild(dim);
    dim.addEventListener('pointerdown', e => { e.preventDefault(); e.stopPropagation(); input.blur(); setOpen(false); });
    const dimSync = () => { const on = persistent ? document.activeElement === input : open; dim.classList.toggle('on', on); document.body.classList.toggle('tc-dim-on', on); };
    const typing = () => { bar.classList.toggle('typing', document.activeElement === input || !!input.value.trim()); dimSync(); };
    input.addEventListener('focus', typing); input.addEventListener('blur', () => setTimeout(typing, 120)); input.addEventListener('input', typing);
    input.addEventListener('keydown', e => e.stopPropagation());
    bar.querySelector('.tc-ic').onclick = () => input.focus();
    bar.querySelector('.tc-q').onclick = e => { e.stopPropagation(); pop.hidden = !pop.hidden; place(); };
    pop.querySelectorAll('[data-q]').forEach(b => { b.onclick = () => { pop.hidden = true; send(b.textContent); }; });
    // مثل پلاتو بعد از فرستادن کیبورد باز می ماند تا پیام بعدی نوشته شود
    const submit = async e => {
      if (e) e.preventDefault();
      const kept = document.activeElement === input;
      if (await send(input.value)) { input.value = ''; if (open || kept) input.focus(); typing(); }
    };
    if (bar.tagName === 'FORM') bar.addEventListener('submit', submit);
    else { bar.querySelector('.tc-send').onclick = submit; input.addEventListener('keydown', e => { if (e.key === 'Enter') submit(e); }); }
    // لمس دکمهٔ فرستادن فوکوس را از ورودی نمی گیرد؛ وگرنه کیبورد بسته و بعد از فرستادن دوباره باز می شود
    const sendBtn = bar.querySelector('.tc-send');
    sendBtn.addEventListener('mousedown', e => e.preventDefault());
    sendBtn.addEventListener('touchstart', e => { if (document.activeElement === input) { e.preventDefault(); sendBtn._tap = true; } }, { passive: false });
    sendBtn.addEventListener('touchend', e => { if (!sendBtn._tap) return; sendBtn._tap = false; e.preventDefault(); sendBtn.click(); });

    // ---------- نوار همیشگی (بیلیارد، فوتبال) هنگام نوشتن ----------
    // صفحهٔ بازی با کیبورد کوتاه نمی شود (GC: --app-h)؛ پس نوار هنگام نوشتن فقط خودش (با transform،
    // بی آن که چیدمان صفحه تکان بخورد) بالای کیبورد می رود
    function lift(on) {
      if (!persistent || on === bar.classList.contains('tc-kb')) return;
      bar.classList.toggle('tc-kb', on);
      if (!on) bar.style.transform = '';
      place();
    }
    if (persistent) {
      input.addEventListener('focus', () => lift(true));
      input.addEventListener('blur', () => setTimeout(() => { if (document.activeElement !== input) lift(false); }, 120));
    }

    // ---------- جای نوار و پیام ها (کیبورد) ----------
    function place() {
      const vv = window.visualViewport;
      const kb = vv ? Math.max(0, innerHeight - vv.height - vv.offsetTop) : 0;
      if (!persistent) bar.style.bottom = kb + 'px';
      else if (bar.classList.contains('tc-kb')) {
        bar.style.transform = '';
        const up = Math.max(0, bar.getBoundingClientRect().bottom - (vv ? vv.offsetTop + vv.height : innerHeight));
        bar.style.transform = up ? `translateY(${-up}px)` : '';
      }
      const shown = persistent ? !bar.hidden : open;
      // نوار شناور هنگام باز شدن هنوز در حال لغزیدن است؛ جایش از اندازهٔ خودش حساب می شود
      const top = !shown ? innerHeight - (o.rest ? o.rest() : 120) : persistent ? bar.getBoundingClientRect().top : innerHeight - kb - bar.offsetHeight;
      const quickH = pop.hidden ? 0 : pop.offsetHeight + 8;
      pop.style.bottom = (innerHeight - top + 8) + 'px';
      feed.style.bottom = (innerHeight - top + 10 + quickH) + 'px';
    }
    addEventListener('resize', place);
    if (window.visualViewport) { visualViewport.addEventListener('resize', place); visualViewport.addEventListener('scroll', place); }

    function setOpen(v) {
      if (persistent || open === v) return;
      open = v; bar.classList.toggle('on', v); document.body.classList.toggle('tc-open', v); dimSync();
      if (v) { unread = 0; badge(); input.focus(); } else { pop.hidden = true; input.blur(); }
      place(); render();
    }
    if (o.btn) o.btn.onclick = () => setOpen(!open);
    document.addEventListener('pointerdown', e => {
      if (e.target.closest('.tc-bar,.tc-quick') || (o.btn && o.btn.contains(e.target))) return;
      if (!pop.hidden) { pop.hidden = true; place(); }
      if (open && !input.value.trim()) setOpen(false);
    }, true);
    document.addEventListener('keydown', e => { if (e.key === 'Escape') setOpen(false); });

    // ---------- پیام ها ----------
    function badge() {
      if (!badgeEl) return;
      badgeEl.hidden = !unread; badgeEl.textContent = unread > 9 ? '+9' : String(unread);
    }
    function row(m) {
      const el = document.createElement('div');
      el.className = 'tc-m' + (m.me ? ' me' : '');
      el.innerHTML = `${o.face ? o.face(m) : ''}<div class="tc-c"><b class="tc-n" dir="auto">${esc(m.name || '')}${m.me ? '<i class="tc-ok">✓</i>' : ''}</b><div class="tc-b" dir="auto">${esc(m.text)}</div></div>`;
      return el;
    }
    // نوار باز: چند پیام آخر ثابت؛ بسته: فقط پیام هایی که هنوز عمرشان تمام نشده
    function render() {
      const now = Date.now();
      const want = (open || (persistent && document.activeElement === input)) ? log.slice(-KEEP) : log.filter(m => m.until > now).slice(-KEEP);
      const ids = new Set(want.map(m => m.id));
      for (const [id, x] of live) if (!ids.has(id)) { live.delete(id); x.el.classList.add('out'); setTimeout(() => x.el.remove(), 260); }
      for (const m of want) if (!live.has(m.id)) { const el = row(m); feed.appendChild(el); live.set(m.id, { el }); }
      place();
    }
    let tick = null;
    function schedule() {
      clearTimeout(tick);
      const next = Math.min(...log.map(m => m.until).filter(t => t > Date.now()));
      if (isFinite(next)) tick = setTimeout(() => { render(); schedule(); }, next - Date.now() + 30);
    }
    input.addEventListener('focus', render); input.addEventListener('blur', () => setTimeout(render, 150));

    function add(list, quiet) {
      if (!list || !list.length) return;
      let fresh = false;
      for (const m of list) {
        if (m.id <= last) continue;
        last = m.id;
        log.push(Object.assign({}, m, { until: quiet ? 0 : Date.now() + life(m.text) }));
        if (quiet) continue;
        fresh = true;
        if (!m.me && !open && !(persistent && document.activeElement === input)) { unread++; if (o.onNew) o.onNew(m); }
      }
      log = log.slice(-40); badge();
      if (fresh) { render(); schedule(); }
    }
    async function send(text) {
      text = String(text || '').trim();
      if (!text || sending || (o.canSend && !o.canSend())) return false;
      sending = true;
      try { add(await o.send(text)); return true; }
      catch (e) { if (o.onError) o.onError(e); return false; }
      finally { sending = false; }
    }
    function end() {
      setOpen(false); log = []; unread = 0; badge(); render();
      if (persistent) bar.hidden = true;
    }
    place();
    return { add, end, send, last: () => last, place, open: () => setOpen(true), close: () => setOpen(false) };
  }
  return { init };
})();
