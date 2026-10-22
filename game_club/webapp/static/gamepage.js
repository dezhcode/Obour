/* صفحهٔ هر بازی (حکم، منچ، فوتبال): بنر با پیش نمایش زندهٔ بازی و سطح تو در همان بازی، و چهار تب
   «بازی · فروشگاه · رده‌بندی · آموزش». تب بازی: چیپ های حالت، حریف و ورودی و یک نوار شناور با خلاصه و تنها دکمهٔ شروع؛
   انتخاب آخر هر بازی یادش می ماند. منطق صف، دعوت و شروع در خود صفحهٔ لابی می ماند (opt.play)؛ اینجا فقط چیدمان و انتخاب است. */
(function () {
const { fa, FD, icon, face, toast, errText, sheet, sheetHead, close, sfx, haptic, mount, store } = GC;
const LV_TITLE = lv => lv < 3 ? 'تازه‌کار' : lv < 6 ? 'آشنا' : lv < 10 ? 'حرفه‌ای' : 'استاد';
const STAR = 'M12 1.8 15 8l6.8.8-5 4.7 1.3 6.8L12 17l-6.1 3.3 1.3-6.8-5-4.7L9 8z';
const TABS = [['play', 'بازی'], ['shop', 'فروشگاه'], ['looks', 'میز'], ['board', 'رده‌بندی'], ['rules', 'آموزش']];

function build(opt) {
  const root = document.getElementById('gp');
  let tab = 'play', period = 'week', settings = { stake: true, entries: [50, 100, 250, 500] }, style = { table: 'a', cards: 'a' };
  let stats = { games: 0, wins: 0 }, rank = 0, board = null, sty = null;
  // «میز»: ظاهرهای رایگان بازی (opt.looks.html و opt.looks.click)؛ «فروشگاه»: میز و ورق خریدنی حکم
  const tabs = TABS.filter(([id]) => (id !== 'shop' || opt.shop) && (id !== 'looks' || opt.looks));
  root.innerHTML = `<section class="gp-banner" id="gpBanner" aria-label="پیشرفت تو در ${opt.title}"></section>
    <div class="gp-tabs" role="tablist" id="gpTabs">${tabs.map(([id, l]) => `<button role="tab" data-t="${id}">${l}</button>`).join('')}</div>
    <div class="gp-panel" id="gpPanel" role="tabpanel"></div>
    <div class="gp-dock" id="gpDock" hidden></div>`;
  const $ = id => document.getElementById(id);

  function banner() {
    const L = GC.level(stats);
    $('gpBanner').innerHTML = `${GCPreview.html(opt.game, { style })}<span class="gp-shade"></span>
      ${rank ? `<span class="gp-rank">رتبهٔ این هفته <b>${FD(rank)}</b></span>` : ''}
      <div class="gp-lv"><span class="gp-star"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="${STAR}"/></svg><b>${FD(L.lv)}</b></span>
        <span class="gp-prog"><span class="gp-bar"><i style="width:${Math.round(L.frac * 100)}%"></i></span>
        <span class="gp-row"><b>${LV_TITLE(L.lv)}</b><span>${stats.games ? `بازی ${FD(stats.games)} · برد ${FD(stats.wins)}` : 'اولین بازی‌ات را شروع کن'}</span></span></span></div>`;
    GCPreview.watch($('gpBanner'));
  }

  /* ---------- تب بازی: سه ردیف چیپ (حالت، حریف، ورودی) و نوار شناور با خلاصه و یک دکمه ---------- */
  const WHO = [['online', 'آنلاین', 'globe'], ['friends', 'دوستان', 'link'], ['group', 'گروه', 'users'], ['bot', 'ربات', 'bot']];
  const WHO_DESC = {
    online: 'با بازیکن‌های واقعی، ناشناس',
    friends: opt.privateSub || 'لینک دعوت می‌سازی و برای دوستانت می‌فرستی',
    group: 'کارت میز را در گروه تلگرام می‌فرستی؛ هر کس بخواهد می‌نشیند',
    bot: 'تمرین، همیشه آزاد و بدون انتظار',
  };
  const GO = { online: ['پیدا کردن حریف', 'play'], friends: ['ساختن لینک دعوت', 'link'], group: ['فرستادن به گروه', 'send'], bot: ['شروع با ربات', 'play'] };
  const saved = store.get('gp:' + opt.game, {});
  const pick = Object.assign({ mode: opt.modes[0].v, who: 'online', entry: 0 }, saved);
  pick.extra = Object.assign({}, ...(opt.extras || []).map(x => ({ [x.key]: x.opts[0][0] })), saved.extra || {});
  if (!opt.modes.some(m => m.v === pick.mode)) pick.mode = opt.modes[0].v;
  if (!WHO.some(([v]) => v === pick.who)) pick.who = 'online';
  const modeOf = () => opt.modes.find(m => m.v === pick.mode);
  // ورودی فقط برای آنلاین و دوستان؛ ربات و گروه همیشه آزادند (گروه تنظیماتش را در خود کارت می پرسد)
  const staked = () => settings.stake && (pick.who === 'online' || pick.who === 'friends');
  const entryOf = () => staked() && settings.entries.includes(pick.entry) ? pick.entry : 0;
  // جایزه: همهٔ ورودی ها به برنده؛ در حالت تیمی (حکم، بیلیارد یاری) بین دو یار تقسیم می شود
  const payout = v => modeOf().team ? v * 2 : v * (modeOf().cfg.players || 2);
  const prize = v => `${modeOf().team ? 'هر برنده' : 'برنده'} ${fa(payout(v))} می‌برد`;
  const cfgOf = () => {
    const e = entryOf();
    return Object.assign({}, modeOf().cfg, pick.who === 'friends' ? pick.extra : {}, { mode: e ? 'stake' : 'free', entry: e });
  };
  const chip = (key, v, label, ic, on, extra = '') => `<button class="chip gp-c" data-k="${key}" data-v="${v}" aria-pressed="${on}"${extra}>${ic || ''}${label}</button>`;
  function play() {
    const m = modeOf(), e = entryOf();
    return `<h2 class="gp-h">حالت بازی</h2>
      <div class="chips">${opt.modes.map(x => chip('mode', x.v, x.label, x.ic, x.v === pick.mode)).join('')}</div>
      <p class="gp-desc">${icon('info')}<span><b>${m.label}:</b> ${m.desc}</span></p>
      <h2 class="gp-h">حریف</h2>
      <div class="chips">${WHO.map(([v, l, ic]) => chip('who', v, l, icon(ic), v === pick.who)).join('')}</div>
      <p class="gp-sub">${WHO_DESC[pick.who]}</p>
      ${pick.who === 'friends' ? (opt.extras || []).map(x => `<h2 class="gp-h">${x.label}</h2>
        <div class="chips">${x.opts.map(([v, l, s]) => chip('x:' + x.key, v, l + (s ? ` <small>${s}</small>` : ''), '', String(pick.extra[x.key]) === String(v))).join('')}</div>`).join('') : ''}
      ${staked() ? `<h2 class="gp-h">ورودی</h2>
        <div class="chips">${chip('entry', 0, 'آزاد', '', !e)}${settings.entries.map(v => chip('entry', v, `${fa(v)} <small>← ${fa(payout(v))}</small>`, GC.coin(), e === v, GC.points < v ? ' disabled' : '')).join('')}</div>
        <p class="gp-sub">${e ? `هر نفر ${fa(e)} امتیاز می‌دهد · ${prize(e)}` : 'بدون امتیاز؛ فقط برای سرگرمی'}</p>` : ''}`;
  }
  function dock() {
    const el = $('gpDock'); el.hidden = tab !== 'play'; if (el.hidden) return;
    const m = modeOf(), e = entryOf(), short = e && GC.points < e, [label, ic] = GO[pick.who];
    const who = WHO.find(([v]) => v === pick.who)[1];
    el.innerHTML = `<span class="t"><b>${m.label} · ${who} · ${e ? `ورودی ${fa(e)}` : 'آزاد'}</b><small>${m.short || m.desc}</small></span>
      <button class="btn gp-go" id="gpGo"${short ? ' disabled' : ''}>${short ? 'امتیاز کم' : `${icon(ic)}${label}`}</button>`;
  }
  function start(btn) {
    const cfg = cfgOf();
    if (pick.who === 'group') { share(btn); return; }
    if (cfg.mode === 'stake' && GC.points < cfg.entry) { sfx.error(); toast(errText({ code: 'insufficient' })); return; }
    opt.play(pick.who === 'friends' ? 'invite' : pick.who, cfg, btn);
  }
  /* فرستادن کارت میز به گروه یا چت: تلگرام پنجرهٔ انتخاب چت را باز می کند (WebApp 8.0+)؛
     در تلگرام قدیمی تر حالت اینلاین (@ربات hokm) با انتخاب چت باز می شود */
  async function share(btn) {
    const w = window.Telegram && Telegram.WebApp, at = v => w && w.isVersionAtLeast && w.isVersionAtLeast(v);
    const inline = () => { if (at('6.7') && w.switchInlineQuery) { w.switchInlineQuery(opt.game, ['groups', 'users']); return true; } return false; };
    btn.disabled = true;
    try {
      const r = await GC.data.groupShare(opt.game);
      if (r.demo) toast('در تلگرام، گروه را انتخاب می‌کنی و کارت میز همان‌جا فرستاده می‌شود');
      else if (at('8.0') && w.shareMessage) w.shareMessage(r.id, ok => { if (ok) { sfx.turn(); haptic('success'); toast('کارت میز فرستاده شد'); } });
      else if (!inline()) toast(`در گروه بنویس /${opt.game}`);
    } catch (e) { if (!inline()) toast(errText(e)); }
    btn.disabled = false;
  }
  /* ---------- تب فروشگاه (ظاهر میز و ورق) ---------- */
  function shop() {
    if (!sty) return '<div class="gp-skel"></div><div class="gp-skel"></div>';
    const C = window.GCCards;
    const tile = i => `<button class="gp-item${i.on ? ' on' : ''}" data-item="${i.id}">
      ${i.kind === 'table' ? `<span class="sw felt tbl-${i.look}"></span>` : `<span class="sw cs cards-${i.look}">${C.back('', 'left:16%;top:14%;transform:rotate(-10deg)')}${C.face(12, '', 'left:46%;top:10%;transform:rotate(8deg)')}</span>`}
      <b>${i.name.replace(/^(میز|ورق) /, '')}</b>${i.on ? '<small class="use">در حال استفاده</small>' : i.owned ? '<small>داری · انتخاب کن</small>' : `<small class="price">${GC.coin()}${fa(i.price)}</small>`}</button>`;
    return `<h2 class="gp-h">میز</h2><div class="gp-items r3">${sty.items.filter(i => i.kind === 'table').map(tile).join('')}</div>
      <h2 class="gp-h">ورق</h2><div class="gp-items r3">${sty.items.filter(i => i.kind === 'cards').map(tile).join('')}</div>`;
  }
  async function pickItem(id) {
    const i = sty.items.find(x => x.id === id); if (!i || i.on) return;
    if (i.owned) { try { sty = await GC.data.styleUse(id); style = { table: sty.table, cards: sty.cards }; sfx.tap(); banner(); draw(); } catch (e) { toast(errText(e)); } return; }
    const sh = sheet(`${sheetHead(i.name)}<p class="gp-lead">یک بار بخری برای همیشه مال توست و سر هر میز حکم همین را می‌بینی.</p>
      <button class="btn btn-block" id="gpBuy"${GC.points < i.price ? ' disabled' : ''}>${GC.points < i.price ? fa(i.price - GC.points) + ' امتیاز کم داری' : `خرید با ${fa(i.price)} امتیاز`}</button>`);
    sh.querySelector('#gpBuy').onclick = async ev => {
      ev.currentTarget.disabled = true;
      try { sty = await GC.data.styleBuy(id); style = { table: sty.table, cards: sty.cards }; await GC.refreshMe(); sfx.coin(); haptic('success'); close(); banner(); draw(); }
      catch (e) { sfx.error(); toast(errText(e)); ev.currentTarget.disabled = false; }
    };
  }

  /* ---------- تب رده بندی همین بازی ---------- */
  function boardHtml() {
    const per = `<div class="chips" id="gpPer">${[['week', 'این هفته'], ['month', 'این ماه'], ['all', 'همیشه']].map(([v, l]) => `<button class="chip sm" data-v="${v}" aria-pressed="${period === v}">${l}</button>`).join('')}</div>`;
    if (!board) return per + '<div class="gp-skel"></div><div class="gp-skel"></div><div class="gp-skel"></div>';
    const medal = ['#F5C451', '#C9D3DC', '#D98B52'];
    const rows = board.rows.map((r, i) => `<li class="${r.me ? 'me' : ''}"><span class="n" style="color:${medal[i] || 'var(--ink-muted)'}">${FD(i + 1)}</span>${face(r)}
      <span class="nm uname">${r.name}</span><span class="w"><b>${FD(r.wins)}</b> برد</span></li>`).join('');
    const m = board.mine || {}, inList = board.rows.some(r => r.me);
    return `${per}${board.sample ? '<span class="tag tag-sample gp-sample">داده‌ها نمونه‌اند</span>' : ''}
      ${rows ? `<ol class="gp-board">${rows}</ol>` : `<div class="gp-empty">${icon('trophy')}<b>هنوز کسی در این بازه نبرده</b><small>اولین برنده تو باش</small></div>`}
      ${!inList ? `<div class="gp-mine"><span class="n">${m.rank ? FD(m.rank) : '—'}</span><span class="t"><b>جایگاه شما</b><small>${m.wins ? `${FD(m.wins)} برد از ${FD(m.games)} بازی` : m.games ? `${FD(m.games)} بازی، هنوز بی‌برد` : 'یک بازی ببر تا در رده‌بندی بیایی'}</small></span></div>` : ''}`;
  }
  async function loadBoard() {
    board = null; if (tab === 'board') draw();
    try { board = await GC.data.gameBoard(opt.game, period); } catch (e) { toast(errText(e)); board = { rows: [], mine: {} }; }
    if (tab === 'board') draw();
  }

  const rules = () => `<ol class="gp-rules">${opt.rules.map(([b, s], i) => `<li><i>${FD(i + 1)}</i><span><b>${b}</b> ${s}</span></li>`).join('')}</ol>
    <a class="gp-more" href="${opt.help || 'help.html'}">${icon('help')}راهنمای کامل</a>`;

  function draw() {
    $('gpTabs').querySelectorAll('[data-t]').forEach(b => b.setAttribute('aria-selected', String(b.dataset.t === tab)));
    $('gpPanel').innerHTML = tab === 'play' ? play() : tab === 'shop' ? shop() : tab === 'looks' ? opt.looks.html() : tab === 'board' ? boardHtml() : rules();
    mount($('gpPanel')); dock(); mount($('gpDock'));
  }
  $('gpDock').onclick = e => { const b = e.target.closest('#gpGo'); if (b && !b.disabled) start(b); };
  $('gpTabs').onclick = e => {
    const b = e.target.closest('[data-t]'); if (!b || b.dataset.t === tab) return;
    tab = b.dataset.t; sfx.tap(); draw();
    if (tab === 'board' && !board) loadBoard();
    if (tab === 'shop' && !sty) GC.data.style().then(r => { sty = r; if (tab === 'shop') draw(); }).catch(e => toast(errText(e)));
  };
  $('gpPanel').onclick = e => {
    const c = e.target.closest('.gp-c');
    if (c && !c.disabled) {
      const k = c.dataset.k, v = isNaN(+c.dataset.v) ? c.dataset.v : +c.dataset.v;
      if (k.startsWith('x:')) pick.extra[k.slice(2)] = v; else pick[k] = v;
      store.set('gp:' + opt.game, pick); sfx.tap(); haptic('light'); draw(); return;
    }
    const it = e.target.closest('[data-item]'); if (it) { pickItem(it.dataset.item); return; }
    if (tab === 'looks' && opt.looks.click(e)) { sfx.tap(); haptic('light'); draw(); return; }
    const p = e.target.closest('#gpPer [data-v]'); if (p && p.dataset.v !== period) { period = p.dataset.v; loadBoard(); }
  };

  banner(); draw();
  return {
    // بعد از گرفتن me: تنظیمات سرور، موجودی و ظاهر میز تازه می شود
    async load(me) {
      if (me) { settings = me.settings || settings; style = Object.assign({ table: 'a', cards: 'a' }, me.style || {}); }
      draw(); banner();
      try {
        const [pf, wk] = await Promise.all([GC.data.profile(), GC.data.gameBoard(opt.game, 'week')]);
        stats = (pf.games || []).find(g => g.game === opt.game) || { games: 0, wins: 0 };
        rank = (wk.mine && wk.mine.rank) || 0;
        if (period === 'week') board = wk;
        banner(); if (tab === 'board') draw();
      } catch (e) {}
    },
    refresh: draw,
  };
}
window.GCGame = { build, LV_TITLE };
})();
