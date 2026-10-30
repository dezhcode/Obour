/* دوستان: اجزای مشترک صفحهٔ دوستان و چت (وضعیت آنلاین، برگهٔ دوست، افزودن با یوزرنیم، دعوت به بازی). */
(function () {
const { FD, fa, icon, face, toast, errText, sheet, sheetHead, close, sfx, haptic, mount } = GC;
const GAME = { hokm: 'حکم', ludo: 'منچ', football: 'فوتبال', billiard: 'بیلیارد', divar: 'دیوار', esmfamil: 'اسم‌فامیل', lashgar: 'لشگر کاغذی', snakes: 'مار و پله' };
const esc = s => String(s || '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

function lastSeen(t) {
  const m = Math.round((Date.now() / 1000 - t) / 60);
  if (!t) return 'آفلاین';
  return m < 2 ? 'همین الان' : m < 60 ? FD(m) + ' دقیقه پیش' : m < 1440 ? FD(Math.round(m / 60)) + ' ساعت پیش' : m < 2880 ? 'دیروز' : FD(Math.round(m / 1440)) + ' روز پیش';
}
function status(f) {
  if (f.playing) return { cls: 'play', text: `در حال بازی ${GAME[f.playing] || ''}` };
  if (f.online) return { cls: 'on', text: 'آنلاین' };
  return { cls: '', text: lastSeen(f.seen) };
}
const av = (f, extra = '') => `<span class="fr-av${extra}">${face(f)}<i class="dot ${status(f).cls}"></i></span>`;

/* ---------- دعوت به بازی: یک میز آزاد ساخته می شود و کارتش در چت دوست می آید ---------- */
function invite(f, after) {
  const sh = sheet(`${sheetHead('دعوت ' + esc(f.name) + ' به بازی')}<p class="fr-lead">یه میز آزاد ساخته می‌شه و دعوتش تو چت و تلگرام به رفیقت می‌رسه</p>
    <div class="fr-games">${['hokm', 'ludo', 'football', 'billiard', 'divar', 'snakes'].map(g => { const x = GC.GAMES.find(y => y.id === g); return `<button class="fr-game" data-g="${g}"><span class="g-art ${x.tint}">${GC.GAME_ART[g]()}</span><b>${x.name}</b><small>${x.sub.split(' · ')[0]}</small></button>`; }).join('')}</div>`);
  sh.querySelectorAll('[data-g]').forEach(b => b.onclick = async () => {
    sh.querySelectorAll('[data-g]').forEach(x => { x.disabled = true; });
    try {
      const r = await GC.data.dmInvite(f.uid, b.dataset.g);
      sfx.turn(); haptic('success'); close(); toast(`دعوت ${GAME[r.game]} واسه ${f.name} رفت 🎲`);
      if (!r.demo) { location.href = `${r.game}-lobby.html`; return; }
      after && after(r);
    } catch (e) { sfx.error(); toast(errText(e)); sh.querySelectorAll('[data-g]').forEach(x => { x.disabled = false; }); }
  });
}

/* ---------- برگهٔ یک دوست: پروفایل کوچک و کارها ---------- */
function confirm(title, text, ok, run) {
  const sh = sheet(`<h2 style="text-align:center;font-size:20px;font-weight:900">${title}</h2><p class="hint">${text}</p>
    <button class="btn btn-danger btn-block" id="cfOk">${ok}</button><button class="btn btn-light btn-block" data-close>بیخیال</button>`, { center: true });
  sh.querySelector('#cfOk').onclick = async ev => { ev.currentTarget.disabled = true; try { await run(); } catch (e) { toast(errText(e)); } close(); };
}
async function friendSheet(f, onChange, opts = {}) {
  const st = status(f);
  const sh = sheet(`<div class="fr-card"><span class="fr-cover cover cover-gc"></span>${av(f, ' big')}
      <b class="uname">${esc(f.name)}</b><small class="fr-st ${st.cls}">${st.text}</small>
      ${f.bio ? `<p class="fr-bio" dir="auto">${esc(f.bio)}</p>` : ''}<div class="fr-nums" id="frNums"></div></div>
    <div class="fr-acts">
      ${opts.noChat ? '' : `<a class="fr-act" href="chat.html?u=${encodeURIComponent(f.uid)}">${icon('chat')}پیام بده</a>`}
      <button class="fr-act" id="frInv">${icon('pad')}دعوت به بازی</button>
      <button class="fr-act bad" id="frDel">${icon('userX')}حذف از رفیقا</button>
      <button class="fr-act bad" id="frBlk">${icon('ban')}بلاک</button>
    </div>`);
  sh.querySelector('#frInv').onclick = () => invite(f, onChange);
  sh.querySelector('#frDel').onclick = () => confirm('از رفیقات حذفش کنی؟', `${esc(f.name)} از لیست رفیقات حذف می‌شه و دیگه نمی‌تونید به هم پیام بدید`, 'حذف کن',
    async () => { await GC.data.friendDrop(f.uid); toast('از رفیقات حذف شد'); onChange && onChange('removed'); });
  sh.querySelector('#frBlk').onclick = () => confirm('بلاک کنی؟', `${esc(f.name)} دیگه نمی‌تونه پیدات کنه یا درخواست بفرسته یا پیام بده`, 'بلاک کن',
    async () => { await GC.data.friendBlock(f.uid, true); toast('بلاک شد'); onChange && onChange('blocked'); });
  try {
    const r = await GC.data.friendUser(f.uid), u = r.user, L = GC.level(u), n = sh.querySelector('#frNums');
    if (n) n.innerHTML = `<span><b>${FD(L.lv)}</b>سطح</span><span><b>${fa(u.games)}</b>بازی</span><span><b>${fa(u.wins)}</b>برد</span>`;
  } catch (e) {}
}

/* ---------- افزودن دوست با یوزرنیم ---------- */
function addSheet(myName, onChange) {
  const sh = sheet(`${sheetHead('افزودن دوست')}<p class="fr-lead">یوزرنیم رفیقتو بنویس</p>
    <label class="un-box" dir="ltr"><input id="adIn" autocomplete="off" autocapitalize="off" spellcheck="false" maxlength="20" placeholder="username"></label>
    <div id="adRes" class="fr-res" aria-live="polite"></div>
    ${myName ? `<div class="fr-mine"><span>یوزرنیم تو: <b class="uname">${esc(myName)}</b></span><button class="btn btn-light btn-sm" id="adCopy">${icon('copy')}کپی</button></div>` : ''}`);
  const inp = sh.querySelector('#adIn'), res = sh.querySelector('#adRes');
  let seq = 0, timer = 0;
  const cp = sh.querySelector('#adCopy');
  if (cp) cp.onclick = () => { try { navigator.clipboard.writeText(myName).then(() => toast('یوزرنیمت کپی شد'), () => toast('کپی نشد')); } catch (e) { toast('کپی نشد'); } };
  function card(r) {
    const u = r.user, L = GC.level(u);
    const btn = {
      none: `<button class="btn btn-block" data-do="req">${icon('userAdd')}ارسال درخواست دوستی</button>`,
      outgoing: `<div class="fr-sent">${icon('check')}درخواست رفت<button class="btn btn-light btn-sm" data-do="drop">لغو</button></div>`,
      incoming: `<button class="btn btn-block" data-do="acc">${icon('check')}قبول درخواست دوستی</button>`,
      friend: `<a class="btn btn-light btn-block" href="chat.html?u=${encodeURIComponent(u.uid)}">${icon('chat')}رفیقید · پیام بده</a>`,
      blocked: `<button class="btn btn-light btn-block" data-do="unblock">رفع بلاک</button>`,
      self: '<p class="hint">این که یوزرنیم خودته 😄</p>',
    }[r.relation] || '';
    res.innerHTML = `<div class="fr-found">${face(u)}<span class="t"><b class="uname">${esc(u.name)}</b><small>سطح ${FD(L.lv)} · ${fa(u.games)} بازی</small>${u.bio ? `<small dir="auto">${esc(u.bio)}</small>` : ''}</span></div>${btn}`;
    res.querySelectorAll('[data-do]').forEach(b => b.onclick = async () => {
      b.disabled = true;
      try {
        const fn = { req: () => GC.data.friendReq(u.uid), acc: () => GC.data.friendAccept(u.uid), drop: () => GC.data.friendDrop(u.uid), unblock: () => GC.data.friendBlock(u.uid, false) }[b.dataset.do];
        const out = await fn(); sfx.tap(); haptic('success');
        if (b.dataset.do === 'req') toast(out.relation === 'friend' ? 'دمت گرم حالا رفیقید 🤝' : 'درخواست دوستی رفت');
        card({ user: u, relation: out.relation }); onChange && onChange();
      } catch (e) { sfx.error(); toast(errText(e)); b.disabled = false; }
    });
    mount(res);
  }
  inp.addEventListener('input', () => {
    const n = GC.normName(inp.value);
    if (inp.value !== n) inp.value = n;
    const my = ++seq; clearTimeout(timer);
    if (n.length < 3) { res.innerHTML = n ? '<p class="hint">حداقل ۳ تا حرف</p>' : ''; return; }
    res.innerHTML = '<div class="gp-skel"></div>';
    timer = setTimeout(async () => {
      try { const r = await GC.data.friendFind(n); if (my === seq) card(r); }
      catch (e) { if (my === seq) res.innerHTML = `<div class="fr-none">${icon('search')}<b>کسی با این یوزرنیم پیدا نشد</b><small>یه بار دیگه یوزرنیمو چک کن</small></div>`; mount(res); }
    }, 400);
  });
  setTimeout(() => inp.focus(), 80);
}

window.GCSocial = { GAME, esc, status, lastSeen, av, invite, friendSheet, addSheet };
})();
