/* لابی هر بازی مثل جعبهٔ همان بازی: در جعبه پیش نمایش زندهٔ خود بازی با برچسب نام، زیرش لبهٔ جعبه به رنگ
   بازی، بعد سطح تو در همان بازی و تب های «بازی · فروشگاه · رده‌بندی · آموزش». همهٔ دکمه ها و انتخاب ها
   به رنگ همان بازی اند (کلاس lobby-<بازی> روی body؛ رنگ ها در gc.css). تب بازی: چیپ های حالت، حریف و نوع بازی (دوستانه یا
   رتبه ای، فقط آنلاین) و یک نوار شناور با خلاصه و تنها دکمهٔ شروع؛
   انتخاب آخر هر بازی یادش می ماند. منطق صف، دعوت و شروع در خود صفحهٔ لابی می ماند (opt.play)؛ اینجا فقط چیدمان و انتخاب است. */
(function () {
const { fa, FD, icon, face, toast, errText, sheet, sheetHead, close, sfx, haptic, mount, store } = GC;
const LV_TITLE = lv => lv < 3 ? 'تازه‌کار' : lv < 6 ? 'آشنا' : lv < 10 ? 'حرفه‌ای' : 'استاد';
const STAR = 'M12 1.8 15 8l6.8.8-5 4.7 1.3 6.8L12 17l-6.1 3.3 1.3-6.8-5-4.7L9 8z';
const TABS = [['play', 'بازی'], ['shop', 'فروشگاه'], ['looks', 'میز'], ['board', 'رده‌بندی'], ['rules', 'آموزش']];

function build(opt) {
  const root = document.getElementById('gp');
  let tab = 'play', period = 'cup', settings = { ranked: true, rank: { win: 20, lose: 10, coins: 2, day: 10 } }, style = { table: 'a', cards: 'a' };
  let stats = { games: 0, wins: 0 }, rank = 0, cups = null, board = null, sty = null;
  // «میز»: ظاهرهای رایگان بازی (opt.looks.html و opt.looks.click)؛ «فروشگاه»: میز و ورق خریدنی حکم
  const tabs = TABS.filter(([id]) => (id !== 'shop' || opt.shop) && (id !== 'looks' || opt.looks));
  const meta = GC.GAMES.find(g => g.id === opt.game) || {};
  document.body.classList.add('lobby', 'lobby-' + opt.game);
  root.innerHTML = `<section class="gp-lid" id="gpLid" aria-label="${opt.title}"></section><div class="gp-edge" aria-hidden="true"></div>
    <div class="gp-lvl" id="gpLvl" aria-label="پیشرفت تو در ${opt.title}"></div>
    <div class="gp-tabs" role="tablist" id="gpTabs">${tabs.map(([id, l]) => `<button role="tab" data-t="${id}">${l}</button>`).join('')}</div>
    <div class="gp-panel" id="gpPanel" role="tabpanel"></div>
    <div class="gp-dock" id="gpDock" hidden></div>`;
  const $ = id => document.getElementById(id);

  // در جعبه (پیش نمایش زنده + برچسب) فقط وقتی ظاهر میز عوض شود دوباره ساخته می شود؛ کارت سطح با هر داده
  let lidKey = '';
  function banner() {
    const k = JSON.stringify(style);
    if (k !== lidKey) {
      lidKey = k;
      $('gpLid').innerHTML = `${GCPreview.html(opt.game, { style })}
        ${meta.tag ? `<span class="gp-tag${meta.tag === 'تازه' ? ' new' : ''}">${meta.tag}</span>` : ''}
        <div class="gp-label"><b>${opt.title}</b>${meta.sub ? `<small>${meta.sub}</small>` : ''}</div>`;
      GCPreview.watch($('gpLid'));
    }
    const L = GC.level(stats);
    const side = cups && cups.cups ? `🏆 ${FD(cups.cups)} جام · ${cups.league}` : rank ? `رتبهٔ ${FD(rank)} این هفته`
      : stats.games ? `${FD(stats.games)} بازی · ${FD(stats.wins)} برد` : 'اولین بازیتو شروع کن';
    $('gpLvl').innerHTML = `<span class="gp-star"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="${STAR}"/></svg><b>${FD(L.lv)}</b></span>
      <span class="gp-prog"><span class="gp-row"><b>${LV_TITLE(L.lv)} · سطح ${FD(L.lv)} در ${opt.title}</b><span>${side}</span></span>
      <span class="gp-bar"><i style="width:${Math.round(L.frac * 100)}%"></i></span></span>`;
  }
  // وقتی در جعبه از بالای صفحه رد شد، نوار وضعیت گوشی رنگ زمینه می گیرد تا تب ها زیرش خوانا بمانند
  if ('IntersectionObserver' in window) new IntersectionObserver(es => document.body.classList.toggle('lid-off', !es[0].isIntersecting), { rootMargin: '-90px 0px 0px 0px' }).observe($('gpLid'));

  /* ---------- تب بازی: سه ردیف چیپ (حالت، حریف، دوستانه یا رتبه ای) و نوار شناور با خلاصه و یک دکمه ---------- */
  const WHO = [['online', 'آنلاین', 'globe'], ['room', 'اتاق', 'userAdd'], ['friends', 'دوستان', 'link'], ['group', 'گروه', 'users'], ['bot', 'ربات', 'bot']];
  const WHO_DESC = {
    online: 'با بازیکنای واقعی و ناشناس',
    room: 'اتاق می‌سازی، رفیقاتو دعوت می‌کنی یا کدشو می‌فرستی و هر وقت همه اومدن شروع می‌کنی',
    friends: opt.privateSub || 'لینک دعوت می‌سازی و واسه رفیقات می‌فرستی',
    group: 'کارت میزو تو گروه تلگرام می‌فرستی و هر کی بخواد می‌شینه',
    bot: 'تمرین همیشه آزاد و بی‌معطلی',
  };
  const GO = { online: ['پیدا کردن حریف', 'play'], room: ['ساختن اتاق', 'userAdd'], friends: ['ساختن لینک دعوت', 'link'], group: ['فرستادن به گروه', 'send'], bot: ['شروع با ربات', 'play'] };
  // بازی گروهی (اسم‌فامیل، لشگر): opt.who = ['group']؛ «اتاق» (room.html) برای همهٔ بازی ها هست
  // داخل برنامهٔ اندروید کارت میز به گروه تلگرام فرستاده نمی شود (مهمان حساب تلگرامی ندارد)
  const WHOS = WHO.filter(([v]) => (v === 'room' || !opt.who || opt.who.includes(v)) && !(GC.app && v === 'group'));
  const saved = store.get('gp:' + opt.game, {});
  const pick = Object.assign({ mode: opt.modes[0].v, who: WHOS[0][0], rank: 0 }, saved);
  pick.extra = Object.assign({}, ...(opt.extras || []).map(x => ({ [x.key]: x.opts[0][0] })), saved.extra || {});
  if (!opt.modes.some(m => m.v === pick.mode)) pick.mode = opt.modes[0].v;
  if (!WHOS.some(([v]) => v === pick.who)) pick.who = WHOS[0][0];
  const modeOf = () => opt.modes.find(m => m.v === pick.mode);
  // رتبه ای فقط با حریف آنلاین (بازیکن واقعی)؛ رفیقا، گروه و ربات همیشه دوستانه اند. ورودی ندارد:
  // برنده جام و چند سکه از طرف بازی می گیرد و بازنده جام از دست می دهد
  const rankable = () => settings.ranked !== false && pick.who === 'online';
  const ranked = () => rankable() && !!pick.rank;
  const cfgOf = () => Object.assign({}, modeOf().cfg, pick.who === 'friends' ? pick.extra : {}, { mode: ranked() ? 'ranked' : 'free' });
  const chip = (key, v, label, ic, on, extra = '') => `<button class="chip gp-c" data-k="${key}" data-v="${v}" aria-pressed="${on}"${extra}>${ic || ''}${label}</button>`;
  function play() {
    const m = modeOf(), R = settings.rank || {};
    return `<h2 class="gp-h">حالت بازی</h2>
      <div class="chips">${opt.modes.map(x => chip('mode', x.v, x.label, x.ic, x.v === pick.mode)).join('')}</div>
      <p class="gp-desc">${icon('info')}<span><b>${m.label}:</b> ${m.desc}</span></p>
      <h2 class="gp-h">حریف</h2>
      <div class="chips">${WHOS.map(([v, l, ic]) => chip('who', v, l, icon(ic), v === pick.who)).join('')}</div>
      <p class="gp-sub">${pick.who !== 'room' && opt.whoDesc || WHO_DESC[pick.who]}</p>
      ${pick.who === 'friends' ? (opt.extras || []).map(x => `<h2 class="gp-h">${x.label}</h2>
        <div class="chips">${x.opts.map(([v, l, s]) => chip('x:' + x.key, v, l + (s ? ` <small>${s}</small>` : ''), '', String(pick.extra[x.key]) === String(v))).join('')}</div>`).join('') : ''}
      ${rankable() ? `<h2 class="gp-h">نوع بازی</h2>
        <div class="chips">${chip('rank', 0, 'دوستانه', icon('users'), !pick.rank)}${chip('rank', 1, 'رتبه‌ای', icon('trophy'), !!pick.rank)}</div>
        <p class="gp-sub">${pick.rank ? `برد ${FD(R.win || 20)} جام${R.coins ? ` و ${FD(R.coins)} سکه` : ''} · باخت ${FD(R.lose || 10)} جام · فقط با بازیکن واقعی`
          : 'بی‌جام و فقط واسه حال کردن'}</p>` : ''}`;
  }
  function dock() {
    const el = $('gpDock'); el.hidden = tab !== 'play'; if (el.hidden) return;
    const m = modeOf(), [label, ic] = GO[pick.who];
    const who = WHO.find(([v]) => v === pick.who)[1];
    el.innerHTML = `<span class="t"><b>${m.label} · ${who} · ${ranked() ? 'رتبه‌ای 🏆' : 'دوستانه'}</b><small>${m.short || m.desc}</small></span>
      <button class="btn gp-go" id="gpGo">${icon(ic)}${label}</button>`;
  }
  function start(btn) {
    const cfg = cfgOf();
    if (pick.who === 'room') { store.set('room_game', opt.game); location.href = 'room.html'; return; }
    if (pick.who === 'group') { share(btn); return; }
    opt.play(pick.who === 'friends' ? 'invite' : pick.who, cfg, btn);
  }
  /* فرستادن کارت میز به گروه یا چت: تلگرام پنجرهٔ انتخاب چت را باز می کند (WebApp 8.0+)؛
     در تلگرام قدیمی تر حالت اینلاین (@ربات hokm) با انتخاب چت باز می شود */
  async function share(btn) {
    if (GC.app) { toast('این بازی فعلاً تو گروه‌های تلگرام بازی می‌شه و اتاق دوستانه‌ش به‌زودی تو برنامه هم میاد'); return; }
    const w = window.Telegram && Telegram.WebApp, at = v => w && w.isVersionAtLeast && w.isVersionAtLeast(v);
    const chats = opt.who && !opt.who.includes('friends') ? ['groups', 'channels'] : ['groups', 'users', 'channels'];
    const inline = () => { if (at('6.7') && w.switchInlineQuery) { w.switchInlineQuery(opt.game, chats); return true; } return false; };
    btn.disabled = true;
    try {
      const r = await GC.data.groupShare(opt.game);
      if (r.demo) toast('تو تلگرام گروهتو انتخاب می‌کنی و کارت میز همون‌جا می‌ره');
      else if (at('8.0') && w.shareMessage) w.shareMessage(r.id, ok => { if (ok) { sfx.turn(); haptic('success'); toast('کارت میز رفت 🎉'); } });
      else if (!inline()) toast(`تو گروه بنویس /${opt.game}`);
    } catch (e) { if (!inline()) toast(errText(e)); }
    btn.disabled = false;
  }
  /* ---------- تب فروشگاه (ظاهر میز و ورق) ---------- */
  function shop() {
    if (!sty) return '<div class="gp-skel"></div><div class="gp-skel"></div>';
    const C = window.GCCards;
    const tile = i => `<button class="gp-item${i.on ? ' on' : ''}" data-item="${i.id}">
      ${i.kind === 'table' ? `<span class="sw felt tbl-${i.look}"></span>` : `<span class="sw cs cards-${i.look}">${C.back('', 'left:16%;top:14%;transform:rotate(-10deg)')}${C.face(12, '', 'left:46%;top:10%;transform:rotate(8deg)')}</span>`}
      <b>${i.name.replace(/^(میز|ورق) /, '')}</b>${i.on ? '<small class="use">داری استفاده می‌کنی</small>' : i.owned ? '<small>داری · انتخاب کن</small>' : `<small class="price">${GC.coin()}${fa(i.price)}</small>`}</button>`;
    return `<h2 class="gp-h">میز</h2><div class="gp-items r3">${sty.items.filter(i => i.kind === 'table').map(tile).join('')}</div>
      <h2 class="gp-h">ورق</h2><div class="gp-items r3">${sty.items.filter(i => i.kind === 'cards').map(tile).join('')}</div>`;
  }
  async function pickItem(id) {
    const i = sty.items.find(x => x.id === id); if (!i || i.on) return;
    if (i.owned) { try { sty = await GC.data.styleUse(id); style = { table: sty.table, cards: sty.cards }; sfx.tap(); banner(); draw(); } catch (e) { toast(errText(e)); } return; }
    const sh = sheet(`${sheetHead(i.name)}<p class="gp-lead">یه بار بخری برای همیشه مال خودته و سر هر میز حکم همینو می‌بینی</p>
      <button class="btn btn-block" id="gpBuy"${GC.points < i.price ? ' disabled' : ''}>${GC.points < i.price ? fa(i.price - GC.points) + ' سکه کم داری' : `خرید با ${fa(i.price)} سکه`}</button>`);
    sh.querySelector('#gpBuy').onclick = async ev => {
      ev.currentTarget.disabled = true;
      try { sty = await GC.data.styleBuy(id); style = { table: sty.table, cards: sty.cards }; await GC.refreshMe(); sfx.coin(); haptic('success'); close(); banner(); draw(); }
      catch (e) { sfx.error(); toast(errText(e)); ev.currentTarget.disabled = false; }
    };
  }

  /* ---------- تب رده بندی همین بازی: جام (رتبه ای) یا بیشترین برد در یک بازه ---------- */
  function boardHtml() {
    const per = `<div class="chips" id="gpPer">${[['cup', '🏆 جام'], ['week', 'این هفته'], ['month', 'این ماه'], ['all', 'همیشه']].map(([v, l]) => `<button class="chip sm" data-v="${v}" aria-pressed="${period === v}">${l}</button>`).join('')}</div>`;
    if (!board) return per + '<div class="gp-skel"></div><div class="gp-skel"></div><div class="gp-skel"></div>';
    const medal = ['#F5C451', '#C9D3DC', '#D98B52'], cup = period === 'cup';
    const rows = board.rows.map((r, i) => `<li class="${r.me ? 'me' : ''}"><span class="n" style="color:${medal[i] || 'var(--ink-muted)'}">${FD(i + 1)}</span>${face(r)}
      <span class="nm uname">${r.name}</span><span class="w">${cup ? `<b>${FD(r.cups)}</b> جام` : `<b>${FD(r.wins)}</b> برد`}</span></li>`).join('');
    const m = board.mine || {}, inList = board.rows.some(r => r.me);
    const mine = cup ? (m.cups ? `${FD(m.cups)} جام · لیگ ${m.league}` : 'یه بازی رتبه‌ای ببر تا جام بگیری و بیای تو جدول')
      : m.wins ? `${FD(m.wins)} برد از ${FD(m.games)} بازی` : m.games ? `${FD(m.games)} بازی، هنوز بی‌برد` : 'یه بازی ببر تا بیای تو رده‌بندی';
    return `${per}${board.sample ? '<span class="tag tag-sample gp-sample">اینا نمونه‌ان</span>' : ''}
      ${rows ? `<ol class="gp-board">${rows}</ol>` : `<div class="gp-empty">${icon('trophy')}<b>${cup ? 'هنوز کسی جام نگرفته' : 'هنوز کسی تو این بازه نبرده'}</b><small>اولین برنده تو باش داش</small></div>`}
      ${!inList ? `<div class="gp-mine"><span class="n">${m.rank ? FD(m.rank) : '—'}</span><span class="t"><b>جای تو</b><small>${mine}</small></span></div>` : ''}`;
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
      if (me) {
        settings = Object.assign({}, settings, me.settings || {}); style = Object.assign({ table: 'a', cards: 'a' }, me.style || {});
        cups = (me.ranks || {})[opt.game] || null;
      }
      draw(); banner();
      try {
        const [pf, wk] = await Promise.all([GC.data.profile(), GC.data.gameBoard(opt.game, 'week')]);
        stats = (pf.games || []).find(g => g.game === opt.game) || { games: 0, wins: 0 };
        rank = (wk.mine && wk.mine.rank) || 0;
        if (period === 'week') board = wk;
        else if (tab === 'board' && !board) loadBoard();
        banner(); if (tab === 'board') draw();
      } catch (e) {}
    },
    refresh: draw,
  };
}
window.GCGame = { build, LV_TITLE };
})();
