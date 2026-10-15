/* صفحهٔ هر بازی (حکم، منچ، فوتبال): بنر با پیش نمایش زندهٔ بازی و سطح تو در همان بازی، و چهار تب
   «بازی · فروشگاه · رده‌بندی · آموزش». تب بازی: ساخت میز خصوصی و صف های آماده؛ هر صف فقط یک دکمه است.
   منطق صف، دعوت و شروع در خود صفحهٔ لابی می ماند (opt.play)؛ اینجا فقط چیدمان و انتخاب است. */
(function () {
const { fa, FD, icon, face, toast, errText, sheet, sheetHead, close, sfx, haptic, mount } = GC;
const LV_TITLE = lv => lv < 3 ? 'تازه‌کار' : lv < 6 ? 'آشنا' : lv < 10 ? 'حرفه‌ای' : 'استاد';
const STAR = 'M12 1.8 15 8l6.8.8-5 4.7 1.3 6.8L12 17l-6.1 3.3 1.3-6.8-5-4.7L9 8z';
const TABS = [['play', 'بازی'], ['shop', 'فروشگاه'], ['board', 'رده‌بندی'], ['rules', 'آموزش']];

function build(opt) {
  const root = document.getElementById('gp');
  let tab = 'play', period = 'week', settings = { stake: true, entries: [50, 100, 250, 500] }, style = { table: 'a', cards: 'a' };
  let stats = { games: 0, wins: 0 }, rank = 0, board = null, sty = null;
  const tabs = TABS.filter(([id]) => id !== 'shop' || opt.shop);
  root.innerHTML = `<section class="gp-banner" id="gpBanner" aria-label="پیشرفت تو در ${opt.title}"></section>
    <div class="gp-tabs" role="tablist" id="gpTabs">${tabs.map(([id, l]) => `<button role="tab" data-t="${id}">${l}</button>`).join('')}</div>
    <div class="gp-panel" id="gpPanel" role="tabpanel"></div>`;
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

  /* ---------- تب بازی ---------- */
  function play() {
    const pts = GC.points, rows = opt.queues(settings);
    return `<button class="gp-private" id="gpPriv"><span class="ic"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 8l4.5 3.5L12 5l4.5 6.5L21 8l-2 10H5z"/></svg></span>
        <span class="t"><b>ساخت میز خصوصی</b><small>${opt.privateSub || 'دوستانت را دعوت کن و با هم بازی کنید'}</small></span><span class="go">${icon('fwd')}</span></button>
      <h2 class="gp-h">صف‌های بازی</h2>
      <ul class="gp-q">${rows.map((q, i) => {
        const short = q.cfg.mode === 'stake' && pts < q.cfg.entry;
        return `<li><span class="ic${q.coin ? ' coin' : ''}">${q.ic}</span>
          <span class="t"><b>${q.title}${q.hot ? '<span class="hot">محبوب</span>' : ''}</b><small>${q.sub}</small></span>
          <button class="gp-join${q.hot ? ' hot' : ''}" data-q="${i}"${short ? ' disabled' : ''}>${short ? 'امتیاز کم' : q.how === 'bot' ? 'شروع' : 'بپیوند'}</button></li>`;
      }).join('')}</ul>`;
  }
  function privateSheet() {
    const f = Object.assign({ mode: 'free', entry: settings.entries[0] }, opt.privateDefaults());
    if (!settings.stake) f.mode = 'free';
    const sh = sheet(`${sheetHead('میز خصوصی')}<p class="gp-lead">میز را بساز و لینکش را برای دوستانت بفرست.</p>
      <div id="gpPf" class="stack"></div><button class="btn btn-block" id="gpMake">${icon('link')}ساختن میز و دعوت</button>`);
    const box = sh.querySelector('#gpPf');
    const seg = (key, opts) => `<div class="seg" data-f="${key}">${opts.map(([v, l, s]) => `<button data-v="${v}" aria-pressed="${String(f[key]) === String(v)}">${l}${s ? `<small>${s}</small>` : ''}</button>`).join('')}</div>`;
    const draw = () => {
      box.innerHTML = `${settings.stake ? `<div class="gp-f"><span>نوع بازی</span>${seg('mode', [['free', 'آزاد', 'بدون امتیاز'], ['stake', 'با امتیاز', 'برنده جایزه می‌برد']])}</div>` : ''}
        ${f.mode === 'stake' ? `<div class="gp-f"><span>ورودی هر نفر</span><div class="chips" data-f="entry">${settings.entries.map(v => `<button class="chip" data-v="${v}" aria-pressed="${f.entry === v}"${GC.points < v ? ' disabled' : ''}>${GC.coin()}${fa(v)}</button>`).join('')}</div></div>` : ''}
        ${opt.privateFields.map(x => `<div class="gp-f"><span>${x.label}</span>${seg(x.key, x.opts)}</div>`).join('')}`;
      mount(box);
    };
    box.onclick = e => {
      const g = e.target.closest('[data-f]'), b = e.target.closest('[data-v]'); if (!g || !b || b.disabled) return;
      const v = b.dataset.v; f[g.dataset.f] = isNaN(+v) ? v : +v; sfx.tap(); draw();
    };
    sh.querySelector('#gpMake').onclick = () => {
      const cfg = Object.assign({}, f, { entry: f.mode === 'stake' ? f.entry : 0 });
      if (cfg.mode === 'stake' && GC.points < cfg.entry) { sfx.error(); toast(errText({ code: 'insufficient' })); return; }
      close(); opt.play('invite', cfg);
    };
    draw();
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
    $('gpPanel').innerHTML = tab === 'play' ? play() : tab === 'shop' ? shop() : tab === 'board' ? boardHtml() : rules();
    mount($('gpPanel'));
  }
  $('gpTabs').onclick = e => {
    const b = e.target.closest('[data-t]'); if (!b || b.dataset.t === tab) return;
    tab = b.dataset.t; sfx.tap(); draw();
    if (tab === 'board' && !board) loadBoard();
    if (tab === 'shop' && !sty) GC.data.style().then(r => { sty = r; if (tab === 'shop') draw(); }).catch(e => toast(errText(e)));
  };
  $('gpPanel').onclick = e => {
    if (e.target.closest('#gpPriv')) { privateSheet(); return; }
    const j = e.target.closest('[data-q]');
    if (j && !j.disabled) { const q = opt.queues(settings)[+j.dataset.q]; opt.play(q.how, Object.assign({}, q.cfg), j); return; }
    const it = e.target.closest('[data-item]'); if (it) { pickItem(it.dataset.item); return; }
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
