package dezhcode.asotas.ui

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.ScrollState
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.defaultMinSize
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.layout.layout
import androidx.compose.ui.layout.onGloballyPositioned
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import dezhcode.asotas.AppViewModel
import dezhcode.asotas.Sheet
import dezhcode.asotas.Tab
import dezhcode.asotas.ThemeMode
import dezhcode.asotas.core.AccountKind
import dezhcode.asotas.core.Ledger
import dezhcode.asotas.core.Me
import dezhcode.asotas.core.StyleItem
import dezhcode.asotas.fa
import dezhcode.asotas.fd
import dezhcode.asotas.game
import kotlinx.coroutines.launch

@Composable
private fun SecHead(title: String, aside: String? = null, onAside: (() -> Unit)? = null) {
    Row(Modifier.fillMaxWidth().padding(bottom = 12.dp), verticalAlignment = Alignment.Bottom) {
        Text(title, style = rokh(17f, 26f), color = Aso.c.ink, modifier = Modifier.weight(1f))
        if (aside != null) {
            Text(aside, style = peyda(13f, 20f, 800), color = Aso.c.accDeep,
                modifier = if (onAside != null) Modifier.press(onClick = onAside) else Modifier)
        }
    }
}

// =====================================================================
// فروشگاه (shop.html): کیف سکه، جایزهٔ روزانه، خرید سکه، میز و ورق حکم، تاریخچه، قانون سکه
// =====================================================================
@Composable
fun ShopScreen(vm: AppViewModel, bottom: Dp) {
    val c = Aso.c
    val me = vm.me
    val scroll = rememberScrollState()
    val scope = rememberCoroutineScope()
    var yDaily by remember { mutableIntStateOf(0) }
    var yPacks by remember { mutableIntStateOf(0) }
    var yHist by remember { mutableIntStateOf(0) }
    val go = { y: Int -> scope.launch { scroll.animateScrollTo(y) }; Unit }
    Column(Modifier.fillMaxSize()) {
        Row(
            Modifier.fillMaxWidth().background(c.ground.copy(alpha = .92f)).padding(horizontal = 16.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text("فروشگاه", style = rokh(24f, 32f), color = c.ink, modifier = Modifier.weight(1f))
            IconBtn("help", onClick = { vm.soon("راهنما") })
        }
        Column(
            Modifier.fillMaxSize().verticalScroll(scroll).padding(PaddingValues(start = 16.dp, end = 16.dp, top = 8.dp, bottom = bottom + 24.dp)),
            verticalArrangement = Arrangement.spacedBy(24.dp),
        ) {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                WalletCard(me?.coins)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    WAct("gift", "جایزهٔ روزانه", gold = true, Modifier.weight(1f)) { go(yDaily) }
                    WAct("plus", "خرید سکه", gold = false, Modifier.weight(1f)) { go(yPacks) }
                    WAct("clock", "تاریخچه", gold = false, Modifier.weight(1f)) { go(yHist) }
                }
            }
            if (me != null) Box(Modifier.onGloballyPositioned { yDaily = it.positionInParentY() }) { DailyCard(me.daily, vm.busy, vm::claimDaily) }
            Column(Modifier.onGloballyPositioned { yPacks = it.positionInParentY() }) {
                SecHead("خرید سکه")
                listOf(50L, 120L, 250L, 600L).chunked(2).forEach { row ->
                    Row(Modifier.padding(bottom = 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        row.forEach { n -> Pack(n, Modifier.weight(1f)) }
                    }
                }
                Text("خرید سکه از خود برنامه با پرداخت درون‌برنامه‌ای مایکت به‌زودی باز می‌شه", style = peyda(12f, 18f), color = c.ink,
                    textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth())
            }
            val st = vm.shop.styles
            Column {
                SecHead("میز حکم")
                SkinGrid(st?.items.orEmpty().filter { it.kind == "table" }, st?.table ?: "a", st?.cards ?: "a", vm)
            }
            Column {
                SecHead("ورق حکم")
                SkinGrid(st?.items.orEmpty().filter { it.kind == "cards" }, st?.table ?: "a", st?.cards ?: "a", vm)
                Text("با سکه بخر و یه بار که بخری برای همیشه مال خودته و سر بازی همون میز و ورقی رو می‌بینی که خودت انتخاب کردی",
                    style = peyda(12f, 18f), color = c.ink, textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth().padding(top = 8.dp))
            }
            Column(Modifier.onGloballyPositioned { yHist = it.positionInParentY() }) {
                SecHead("تاریخچهٔ سکه")
                History(me?.history.orEmpty())
            }
            Rules()
        }
    }
}

/** بالا کشیدن و کوتاه کردن جای چیدمان (margin-top منفی CSS) */
private fun Modifier.pullUp(by: Dp): Modifier = layout { m, cs ->
    val p = m.measure(cs)
    val d = by.roundToPx()
    layout(p.width, (p.height - d).coerceAtLeast(0)) { p.place(0, -d) }
}

private fun androidx.compose.ui.layout.LayoutCoordinates.positionInParentY(): Int =
    (parentLayoutCoordinates?.let { it.localPositionOf(this, Offset.Zero).y } ?: 0f).toInt()

/** کارت طلایی موجودی (.wcard) */
@Composable
private fun WalletCard(balance: Long?) {
    val ink = Aso.c.goldInk
    val shape = RoundedCornerShape(24.dp)
    Box(
        Modifier.fillMaxWidth().shadow(16.dp, shape, ambientColor = Color(0xB3B47800), spotColor = Color(0xB3B47800)).clip(shape)
            .background(Brush.linearGradient(listOf(Color(0xFFFFD873), Color(0xFFF5C451), Color(0xFFE8A92B))))
            .drawBehind {
                drawCircle(Color.White.copy(alpha = .2f), radius = 110.dp.toPx() - 13.dp.toPx(), center = Offset(50.dp.toPx(), 30.dp.toPx()), style = Stroke(26.dp.toPx()))
                drawCircle(Color.White.copy(alpha = .13f), radius = 105.dp.toPx() - 9.dp.toPx(), center = Offset(155.dp.toPx(), size.height + 0.dp.toPx()), style = Stroke(18.dp.toPx()))
            }
            .padding(start = 18.dp, end = 18.dp, top = 18.dp, bottom = 20.dp),
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(18.dp)) {
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Text("کیف سکهٔ AsoTas", style = peyda(13f, 20f, 800), color = ink, modifier = Modifier.weight(1f))
                Coin(30.dp)
            }
            Column {
                Text("موجودی", style = peyda(12.5f, 18f, 700), color = ink.copy(alpha = .8f))
                Text(balance?.fa() ?: "…", style = peyda(40f, 50f, 800), color = ink)
                Text("سکه فقط تو بازی خرج می‌شه", style = peyda(12.5f, 18f, 700), color = ink.copy(alpha = .8f))
            }
        }
    }
}

@Composable
private fun WAct(icon: String, label: String, gold: Boolean, modifier: Modifier, onClick: () -> Unit) {
    val c = Aso.c
    val shape = RoundedCornerShape(18.dp)
    Column(modifier.press(onClick = onClick), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Box(Modifier.size(56.dp).clip(shape).background(if (gold) c.gold else c.surface).then(if (gold) Modifier else Modifier.lined(shape)), contentAlignment = Alignment.Center) {
            Ic(icon, size = 24.dp, tint = if (gold) c.goldInk else c.ink)
        }
        Text(label, style = peyda(12.5f, 18f, 800), color = c.ink)
    }
}

@Composable
private fun Pack(n: Long, modifier: Modifier) {
    val c = Aso.c
    val shape = RoundedCornerShape(22.dp)
    Column(modifier.clip(shape).background(c.surface).lined(shape).padding(start = 8.dp, end = 8.dp, top = 14.dp, bottom = 12.dp),
        horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Coin(34.dp)
        Text("${n.fa()} سکه", style = peyda(18f, 26f, 800), color = c.ink)
        Text("به‌زودی از مایکت", style = peyda(12f, 18f, 800), color = c.accDeep, modifier = Modifier.padding(top = 4.dp))
    }
}

@Composable
private fun SkinGrid(items: List<StyleItem>, table: String, cards: String, vm: AppViewModel) {
    if (items.isEmpty()) {
        Text("یه لحظه…", style = peyda(12f, 18f), color = Aso.c.ink, textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth())
        return
    }
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        items.chunked(3).forEach { row ->
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                row.forEach { SkinCard(it, table, cards, vm, Modifier.weight(1f)) }
                repeat(3 - row.size) { Box(Modifier.weight(1f)) }
            }
        }
    }
}

@Composable
private fun SkinCard(it: StyleItem, table: String, cards: String, vm: AppViewModel, modifier: Modifier) {
    val c = Aso.c
    val shape = RoundedCornerShape(22.dp)
    Column(
        modifier.clip(shape).background(c.surface).border(2.dp, if (it.on) c.acc else c.line.copy(alpha = if (it.on) 1f else .0f), shape)
            .lined(shape).padding(start = 6.dp, end = 6.dp, top = 6.dp, bottom = 8.dp),
        horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        SkinPreview(it.kind, it.look, table, cards, Modifier.fillMaxWidth().height(98.dp))
        Text(it.name.removePrefix("میز ").removePrefix("ورق "), style = peyda(13f, 18f, 800), color = c.ink, maxLines = 1, overflow = TextOverflow.Ellipsis)
        when {
            it.on -> Text("الان همینه", style = peyda(12f, 40f, 800), color = c.accDeep)
            it.owned -> Btn("انتخابش کن", { vm.shop.use(it.id) }, Modifier.fillMaxWidth().height(40.dp), kind = BtnKind.Light, small = true)
            else -> Row(
                Modifier.fillMaxWidth().height(40.dp).clip(CircleShape).background(c.coin).press { vm.openSheet(Sheet.Buy(it)) },
                horizontalArrangement = Arrangement.spacedBy(4.dp, Alignment.CenterHorizontally), verticalAlignment = Alignment.CenterVertically,
            ) {
                Coin(15.dp)
                Text(it.price.fa(), style = peyda(14f, 20f, 800), color = c.coinInk)
            }
        }
    }
}

private val KIND = mapOf(
    "gift" to Triple("gift", "coin", "هدیه"), "daily" to Triple("gift", "coin", "جایزهٔ روزانه"),
    "reward" to Triple("trophy", "coin", "برد رتبه‌ای"), "style" to Triple("cards", "sky", "خرید میز و ورق"),
    "admin" to Triple("shield", "sky", "پشتیبانی"), "purchase" to Triple("plus", "ok", "خرید سکه"),
)

@Composable
private fun History(rows: List<Ledger>) {
    val c = Aso.c
    val list = rows.filter { it.kind in KIND }
    val shape = RoundedCornerShape(28.dp)
    Column(Modifier.fillMaxWidth().clip(shape).background(c.surface).lined(shape).padding(horizontal = 14.dp, vertical = 6.dp)) {
        if (list.isEmpty()) {
            Text("هنوز سکه‌ای جابه‌جا نکردی با جایزهٔ روزانه شروع کن 🎁", style = peyda(12f, 18f), color = c.inkMuted, textAlign = TextAlign.Center,
                modifier = Modifier.fillMaxWidth().padding(vertical = 12.dp))
            return@Column
        }
        var last = ""
        list.forEachIndexed { i, l ->
            val (ic, tone, label) = KIND.getValue(l.kind)
            val day = dayOf(l.at)
            if (day != last) {
                last = day
                Text(day, style = peyda(12f, 18f, 700), color = c.inkMuted, modifier = Modifier.padding(top = 8.dp, bottom = 2.dp, start = 2.dp))
            } else if (i > 0) HorizontalDivider(color = c.line)
            val (bg, fg) = when (tone) { "coin" -> c.coinTint to c.coinText; "sky" -> c.skyTint to c.skyDeep; else -> c.successTint to c.success }
            Row(Modifier.fillMaxWidth().padding(vertical = 10.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Box(Modifier.size(42.dp).clip(RoundedCornerShape(14.dp)).background(bg), contentAlignment = Alignment.Center) { Ic(ic, size = 21.dp, tint = fg) }
                Column(Modifier.weight(1f)) {
                    Text(l.note.ifBlank { label }, style = peyda(14f, 21f, 800), color = c.ink, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Text(clock(l.at) + if (l.status == "pending") " · داره انجام می‌شه" else "", style = peyda(12f, 18f, 500), color = c.inkMuted)
                }
                Text((if (l.amount >= 0) "+" else "−") + kotlin.math.abs(l.amount).fa(), style = peyda(15f, 22f, 800),
                    color = if (l.amount >= 0) c.success else c.danger)
            }
        }
    }
}

@Composable
private fun Rules() {
    val c = Aso.c
    var open by rememberSaveable { mutableStateOf(false) }
    val shape = RoundedCornerShape(28.dp)
    Column(Modifier.fillMaxWidth().clip(shape).background(c.surface).lined(shape).padding(horizontal = 16.dp, vertical = 12.dp)) {
        Row(Modifier.fillMaxWidth().defaultMinSize(minHeight = 40.dp).press(.99f) { open = !open }, verticalAlignment = Alignment.CenterVertically) {
            Text("قانون سکه", style = peyda(14.5f, 22f, 800), color = c.ink, modifier = Modifier.weight(1f))
            Ic("fwd", size = 18.dp, tint = c.ink, modifier = Modifier.rotate(if (open) -90f else 0f))
        }
        AnimatedVisibility(open) {
            Column(Modifier.padding(top = 8.dp, bottom = 4.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                listOf(
                    "سکه پول داخل بازیه و فقط باهاش میز و ورق و آیتم می‌خری",
                    "با جایزهٔ روزانه و برد تو بازی رتبه‌ای جمع می‌شه و داخل برنامه هم می‌شه خریدش",
                    "سکه به پول نقد یا کیف عبور تبدیل نمی‌شه و به کسی هم منتقل نمی‌شه",
                    "بازی‌ها ورودی ندارن و رتبه‌ای فقط جام و چند تا سکه از طرف بازی می‌ده",
                ).forEach { t ->
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Ic("check", size = 18.dp, tint = c.success, modifier = Modifier.padding(top = 2.dp))
                        Text(t, style = peyda(13.5f, 22f), color = c.ink)
                    }
                }
            }
        }
    }
}

// =====================================================================
// پروفایل (profile.html)
// =====================================================================
@Composable
fun ProfileScreen(vm: AppViewModel, bottom: Dp) {
    val c = Aso.c
    val me = vm.me
    val scroll = rememberScrollState()
    val scope = rememberCoroutineScope()
    var ySet by remember { mutableIntStateOf(0) }
    Column(Modifier.fillMaxSize()) {
        Row(Modifier.fillMaxWidth().background(c.ground.copy(alpha = .92f)).padding(horizontal = 16.dp, vertical = 14.dp)) {
            Text("پروفایل", style = rokh(24f, 32f), color = c.ink)
        }
        if (me == null) return@Column
        Column(
            Modifier.fillMaxSize().verticalScroll(scroll).padding(PaddingValues(start = 16.dp, end = 16.dp, top = 8.dp, bottom = bottom + 24.dp)),
            verticalArrangement = Arrangement.spacedBy(24.dp),
        ) {
            MeCard(me, vm) { scope.launch { scroll.animateScrollTo(ySet) } }
            Collection(vm)
            GameStats(vm)
            Recent(vm)
            Badges(me, vm)
            Column(Modifier.onGloballyPositioned { ySet = it.positionInParentY() }) {
                SecHead("تنظیمات")
                Settings(me, vm)
            }
        }
    }
}

@Composable
private fun MeCard(me: Me, vm: AppViewModel, toSettings: () -> Unit) {
    val c = Aso.c
    val shape = RoundedCornerShape(24.dp)
    Column(Modifier.fillMaxWidth().clip(shape).background(c.surface).lined(shape).padding(bottom = 16.dp)) {
        Box(Modifier.fillMaxWidth().height(136.dp)) {
            Cover(me.cover, Modifier.fillMaxSize(), mark = true)
            CoverBtn("sliders", 44.dp, dark = true, Modifier.align(Alignment.TopEnd).padding(8.dp), toSettings)
            CoverBtn("plus", 38.dp, dark = false, Modifier.align(Alignment.BottomEnd).padding(8.dp)) { vm.openSheet(Sheet.Cover) }
        }
        Column(Modifier.fillMaxWidth().pullUp(56.dp).padding(horizontal = 16.dp), horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(6.dp)) {
            // حلقهٔ سطح دور عکس
            Box(Modifier.size(118.dp).clip(CircleShape).background(c.surface).padding(5.dp)) {
                val frac = me.level.frac.toFloat()
                val ring = c.acc
                val track = c.line
                Canvas(Modifier.fillMaxSize()) {
                    drawCircle(track)
                    drawArc(ring, -90f, 360f * frac, useCenter = true, size = Size(size.width, size.height))
                }
                Face(me.name, me.av, me.pic, Modifier.align(Alignment.Center), size = 96.dp)
                Text("سطح ${me.level.lv.fd()}", style = peyda(12.5f, 24f, 800), color = c.accInk,
                    modifier = Modifier.align(Alignment.BottomCenter).offset(y = 13.dp).clip(RoundedCornerShape(12.dp)).background(c.surface).padding(3.dp)
                        .clip(RoundedCornerShape(12.dp)).background(c.acc).padding(horizontal = 11.dp))
            }
            Row(Modifier.padding(top = 10.dp, start = 44.dp), verticalAlignment = Alignment.CenterVertically) {
                Text(me.name, style = rokh(23f, 32f), color = c.ink)
                Box(Modifier.size(44.dp).clip(CircleShape).press(onClick = vm::openNameEdit), contentAlignment = Alignment.Center) { Ic("edit", size = 20.dp, tint = c.acc) }
            }
            Text(me.bio.ifBlank { "یه چیزی درباره خودت بنویس…" }, style = peyda(14f, 22f), color = if (me.bio.isBlank()) c.inkMuted else c.ink,
                textAlign = TextAlign.Center,
                modifier = Modifier.fillMaxWidth().defaultMinSize(minHeight = 48.dp).clip(RoundedCornerShape(16.dp)).background(c.surfaceSunk)
                    .press(.99f) { vm.openSheet(Sheet.Bio) }.padding(horizontal = 14.dp, vertical = 13.dp))
            val days = if (me.joined > 0) maxOf(1L, Math.round((System.currentTimeMillis() / 1000 - me.joined) / 86400.0)) else 0L
            Row(Modifier.fillMaxWidth().padding(top = 8.dp)) {
                StatCell("برد", me.wins.fa(), c.ink, Modifier.weight(1f))
                Box(Modifier.width(1.dp).height(48.dp).background(c.line))
                StatCell("عضویت", if (days > 0) "${days.fd()} روز" else "—", c.ink, Modifier.weight(1f))
                Box(Modifier.width(1.dp).height(48.dp).background(c.line))
                StatCell("سطح", me.level.lv.fd(), c.acc, Modifier.weight(1f))
            }
            Text("${me.level.left.fd()} تجربهٔ دیگه تا سطح ${(me.level.lv + 1).fd()} · هر بازی ۱۰ و هر برد ۱۵", style = peyda(12f, 18f), color = c.inkMuted)
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Coin(26.dp)
                Text(me.coins.fa(), style = peyda(21f, 28f, 800), color = c.ink)
                Box(Modifier.size(44.dp).clip(CircleShape).background(c.gold).press { vm.selectTab(Tab.SHOP) }, contentAlignment = Alignment.Center) {
                    Ic("plus", size = 20.dp, tint = c.goldInk)
                }
                Box(Modifier.size(44.dp).clip(RoundedCornerShape(14.dp)).background(c.surfaceSunk).press { vm.selectTab(Tab.SHOP) }, contentAlignment = Alignment.Center) {
                    Ic("wallet", size = 20.dp, tint = c.ink)
                }
            }
        }
    }
}

@Composable
private fun CoverBtn(icon: String, size: Dp, dark: Boolean, modifier: Modifier, onClick: () -> Unit) {
    val c = Aso.c
    Box(modifier) {
        Box(Modifier.size(size).clip(CircleShape).background(if (dark) Color.Black.copy(alpha = .32f) else c.surface.copy(alpha = .94f)).press(onClick = onClick),
            contentAlignment = Alignment.Center) { Ic(icon, size = 20.dp, tint = if (dark) Color.White else c.ink) }
    }
}

@Composable
private fun StatCell(label: String, value: String, color: Color, modifier: Modifier) {
    Column(modifier, horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(2.dp)) {
        Text(label, style = peyda(12f, 18f, 800), color = Aso.c.inkMuted)
        Text(value, style = rokh(20f, 28f), color = color)
    }
}

// ---------- کلکسیون: کاور و میز و ورق هایی که داری ----------
@Composable
private fun Collection(vm: AppViewModel) {
    val c = Aso.c
    val st = vm.shop.styles
    val owned = st?.items.orEmpty().filter { it.owned }
    val total = st?.items.orEmpty().size + 1
    val own = owned.size + 1
    Column {
        SecHead("کلکسیون من", "همه") { vm.selectTab(Tab.SHOP) }
        Row(Modifier.padding(bottom = 10.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Box(Modifier.weight(1f).height(6.dp).clip(RoundedCornerShape(3.dp)).background(c.line)) {
                Box(Modifier.fillMaxWidth(own.toFloat() / maxOf(1, total)).height(6.dp).clip(RoundedCornerShape(3.dp)).background(c.success))
            }
            Text("${own.fd()} از ${total.fd()}", style = peyda(12.5f, 18f, 800), color = c.inkMuted)
        }
        // اول کاور، بعد طرح های در حال استفاده، بعد بقیه (null یعنی کاور)
        val tiles: List<StyleItem?> = listOf<StyleItem?>(null) + owned.filter { it.on } + owned.filter { !it.on }
        tiles.take(6).chunked(3).forEach { row ->
            Row(Modifier.padding(bottom = 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                row.forEach { i ->
                    if (i == null) ColTile("کاور AsoTas", Modifier.weight(1f)) { Cover("gc", Modifier.fillMaxSize()) }
                    else ColTile(i.name, Modifier.weight(1f)) { SkinPreview(i.kind, i.look, st?.table ?: "a", st?.cards ?: "a", Modifier.fillMaxSize(), frameW = 100.dp) }
                }
                repeat(3 - row.size) { Box(Modifier.weight(1f)) }
            }
        }
    }
}

@Composable
private fun ColTile(name: String, modifier: Modifier, art: @Composable () -> Unit) {
    val c = Aso.c
    val shape = RoundedCornerShape(16.dp)
    Column(modifier.clip(shape).background(c.surface).lined(shape).padding(start = 6.dp, end = 6.dp, top = 8.dp, bottom = 10.dp),
        horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Box(Modifier.fillMaxWidth().height(54.dp).clip(RoundedCornerShape(10.dp))) { art() }
        Text(name, style = peyda(12.5f, 18f, 800), color = c.ink, maxLines = 1, overflow = TextOverflow.Ellipsis)
    }
}

// ---------- کارنامهٔ هر بازی ----------
private val ORDER = listOf("hokm", "football", "ludo", "billiard", "divar", "esmfamil", "lashgar", "snakes")

@Composable
private fun GameStats(vm: AppViewModel) {
    val c = Aso.c
    var tab by rememberSaveable { mutableStateOf("hokm") }
    val s = vm.profile.data?.games?.firstOrNull { it.game == tab }
    val games = s?.games ?: 0L
    val wins = s?.wins ?: 0L
    Column {
        SecHead("کارنامهٔ هر بازی")
        ORDER.chunked(4).forEach { row ->
            Row(Modifier.padding(bottom = 5.dp), horizontalArrangement = Arrangement.spacedBy(5.dp)) {
                row.forEach { id ->
                    val on = id == tab
                    val shape = RoundedCornerShape(16.dp)
                    Column(Modifier.weight(1f).clip(shape).background(c.surface).border(if (on) 2.dp else 1.dp, if (on) c.acc else c.line, shape)
                        .press { tab = id }.padding(top = 8.dp, bottom = 7.dp),
                        horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(5.dp)) {
                        GameThumb(id, 38.dp, 12.dp)
                        Text(game(id)?.title.orEmpty(), style = peyda(11f, 16f, if (on) 800 else 700), color = if (on) c.ink else c.inkMuted, maxLines = 1)
                    }
                }
            }
        }
        Row(Modifier.padding(top = 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Kpi(games.fa(), "بازی", c.ink, Modifier.weight(1f))
            Kpi(wins.fa(), "برد", c.success, Modifier.weight(1f))
            Kpi((games - wins).fa(), "باخت", c.ink, Modifier.weight(1f))
            Kpi(if (games > 0) "${Math.round(wins * 100.0 / games).fd()}٪" else "—", "درصد برد", c.coinText, Modifier.weight(1f))
        }
    }
}

@Composable
private fun Kpi(v: String, label: String, color: Color, modifier: Modifier) {
    val shape = RoundedCornerShape(18.dp)
    Column(modifier.clip(shape).background(Aso.c.surface).lined(shape).padding(horizontal = 4.dp, vertical = 12.dp),
        horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(2.dp)) {
        Text(v, style = rokh(20f, 28f), color = color)
        Text(label, style = peyda(11.5f, 16f), color = Aso.c.inkMuted)
    }
}

// ---------- آخرین بازی ها ----------
private fun ago(t: Long): String {
    val d = Math.round((System.currentTimeMillis() / 1000 - t) / 60.0)
    return when {
        d < 1 -> "همین حالا"
        d < 60 -> "${d.fd()} دقیقه پیش"
        d < 1440 -> "${Math.round(d / 60.0).fd()} ساعت پیش"
        else -> "${Math.round(d / 1440.0).fd()} روز پیش"
    }
}

@Composable
private fun Recent(vm: AppViewModel) {
    val c = Aso.c
    val recent = vm.profile.data?.recent
    val shape = RoundedCornerShape(28.dp)
    Column {
        SecHead("آخرین بازی‌ها")
        Column(Modifier.fillMaxWidth().clip(shape).background(c.surface).lined(shape).padding(horizontal = 14.dp, vertical = 4.dp)) {
            when {
                recent == null -> Text("یه لحظه…", style = peyda(12f, 18f), color = c.inkMuted, textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth().padding(vertical = 12.dp))
                recent.isEmpty() -> Column(Modifier.fillMaxWidth().padding(vertical = 16.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Text("هنوز هیچ بازی‌ای رو تموم نکردی داش", style = peyda(12f, 18f), color = c.inkMuted)
                    Btn("اولین بازیتو شروع کن", { vm.selectTab(Tab.GAMES) }, kind = BtnKind.Gold, small = true)
                }
                else -> recent.forEachIndexed { i, r ->
                    if (i > 0) HorizontalDivider(color = c.line)
                    Row(Modifier.fillMaxWidth().padding(vertical = 10.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        GameThumb(r.game, 44.dp, 13.dp)
                        Column(Modifier.weight(1f)) {
                            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                                Text(game(r.game)?.title.orEmpty(), style = peyda(14f, 21f, 800), color = c.ink)
                                Text(if (r.won) "برد" else "باخت", style = peyda(11.5f, 20f, 800), color = if (r.won) c.success else c.danger,
                                    modifier = Modifier.clip(RoundedCornerShape(10.dp)).background(if (r.won) c.successTint else c.danger.copy(alpha = .14f)).padding(horizontal = 8.dp))
                            }
                            val mode = when (r.mode) {
                                "ranked" -> "رتبه‌ای" + if (r.cups != 0L) " · ${if (r.cups > 0) "+" else "−"}${kotlin.math.abs(r.cups).fa()} جام" else ""
                                "stake" -> "امتیازی قدیمی"
                                else -> "دوستانه"
                            }
                            Text("$mode · ${ago(r.at)}", style = peyda(12f, 18f), color = c.inkMuted)
                        }
                        if (r.prize > 0 && r.mode == "ranked") Amount(r.prize) else Text("—", style = peyda(14f, 20f, 800), color = c.inkMuted)
                    }
                }
            }
        }
    }
}

// ---------- نشان ها (از کارنامهٔ واقعی) ----------
@Composable
private fun Badges(me: Me, vm: AppViewModel) {
    val c = Aso.c
    val played = vm.profile.data?.games.orEmpty().count { it.games > 0 }.toLong()
    val k = me.kots
    data class B(val t: String, val ic: String, val bg: Long, val fg: Long, val on: Boolean, val sub: String)
    val list = listOf(
        B("اولین برد", "trophy", 0xFFF5C451, 0xFF3A2A00, me.wins >= 1, "${minOf(me.wins, 1L).fa()} از ۱"),
        B("۱۰ برد", "bolt", 0xFFFF8A95, 0xFF3A0A10, me.wins >= 10, "${minOf(me.wins, 10L).fa()} از ۱۰"),
        B("۵۰ بازی", "dice", 0xFF7FAEFF, 0xFF0B2251, me.games >= 50, "${minOf(me.games, 50L).fa()} از ۵۰"),
        B("همه‌کاره", "pad", 0xFF5FE39A, 0xFF08331B, played >= 3, "${played.fa()} از ۳ بازی"),
        B("سطح ۵", "spark", 0xFFC9B8FF, 0xFF22124F, me.level.lv >= 5, "سطح ${me.level.lv.fa()}"),
        B("لیگ نقره‌ای", "flag", 0xFFD9DEE8, 0xFF2A3140, me.maxCups >= 100, "${minOf(me.maxCups, 100L).fa()} از ۱۰۰ جام"),
        B("کوت‌کن", "cards", 0xFF7FE0C0, 0xFF06302A, k >= 1, "${minOf(k, 1L).fa()} از ۱ کوت"),
        B("استاد کوت", "cards", 0xFFFFB86B, 0xFF3A1C00, k >= 5, "${minOf(k, 5L).fa()} از ۵ کوت"),
    )
    Column {
        SecHead("نشان‌ها", "${list.count { it.on }.fd()} از ${list.size.fd()}")
        list.chunked(4).forEach { row ->
            Row(Modifier.padding(bottom = 12.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                row.forEach { b ->
                    Column(Modifier.weight(1f), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        Box(Modifier.size(54.dp).clip(RoundedCornerShape(17.dp)).background(if (b.on) Color(b.bg) else c.surfaceSunk), contentAlignment = Alignment.Center) {
                            Ic(if (b.on) b.ic else "shield", size = 24.dp, tint = if (b.on) Color(b.fg) else c.inkMuted)
                        }
                        Text(b.t, style = peyda(11.5f, 16f, 700), color = if (b.on) c.ink else c.inkMuted, textAlign = TextAlign.Center)
                        Text(if (b.on) "گرفتی" else b.sub, style = peyda(11.5f, 16f, 600), color = c.inkMuted, textAlign = TextAlign.Center)
                    }
                }
            }
        }
    }
}

// ---------- تنظیمات ----------
@Composable
private fun Settings(me: Me, vm: AppViewModel) {
    val c = Aso.c
    val shape = RoundedCornerShape(28.dp)
    Column(Modifier.fillMaxWidth().clip(shape).background(c.surface).lined(shape).padding(horizontal = 14.dp, vertical = 4.dp)) {
        SetRow("حساب", when (me.account.kind) {
            AccountKind.GUEST -> "مهمونی · با تلگرام یا ایمیل بیا تو تا چیزی گم نشه"
            AccountKind.TELEGRAM -> "با حساب تلگرامت وارد شدی"
            AccountKind.EMAIL -> me.account.email.orEmpty()
        }, bad = me.account.kind == AccountKind.GUEST) {
            if (me.account.kind == AccountKind.GUEST) Btn("ورود", vm::openLogin, small = true)
            else Btn("خروج", { vm.openSheet(Sheet.Confirm("از حسابت خارج بشی؟", "بعدش یه حساب مهمون تازه ساخته می‌شه و هر وقت خواستی دوباره وارد می‌شی", "خروج", vm::logout)) },
                kind = BtnKind.Light, small = true)
        }
        HorizontalDivider(color = c.line)
        SetRow("پوسته", "خودکار مثل گوشی") {
            Row(Modifier.clip(RoundedCornerShape(22.dp)).background(c.surfaceSunk).padding(3.dp), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                listOf(ThemeMode.AUTO to "خودکار", ThemeMode.LIGHT to "روشن", ThemeMode.DARK to "تیره").forEach { (m, label) ->
                    val on = vm.theme == m
                    val s = RoundedCornerShape(16.dp)
                    Text(label, style = peyda(13f, 18f, 800), color = if (on) c.ink else c.inkMuted,
                        modifier = Modifier.clip(s).background(if (on) c.surface else Color.Transparent).then(if (on) Modifier.lined(s) else Modifier)
                            .press { vm.chooseTheme(m) }.padding(horizontal = 11.dp, vertical = 6.dp))
                }
            }
        }
        HorizontalDivider(color = c.line)
        SetRow("صدای بازی", "صدای ورق و تاس و توپ و تماشاچیا") { Switch(me.sound, vm::toggleSound) }
        HorizontalDivider(color = c.line)
        SetRow("تکون خوردن برگا تو حکم", "گوشی رو کج کنی برگای وسط میز سُر می‌خورن") { Switch(vm.tilt, vm::toggleTilt) }
    }
}

@Composable
private fun SetRow(title: String, sub: String, bad: Boolean = false, end: @Composable () -> Unit) {
    Row(Modifier.fillMaxWidth().defaultMinSize(minHeight = 56.dp).padding(vertical = 6.dp), verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        Column(Modifier.weight(1f)) {
            Text(title, style = peyda(14f, 21f, 800), color = Aso.c.ink)
            Text(sub, style = peyda(12f, 18f), color = if (bad) Aso.c.danger else Aso.c.inkMuted)
        }
        end()
    }
}

/** سوییچ (.switch) */
@Composable
fun Switch(on: Boolean, onClick: () -> Unit) {
    val c = Aso.c
    Box(Modifier.width(48.dp).height(28.dp).clip(CircleShape).background(if (on) c.acc else c.line).press(.95f, onClick = onClick).padding(3.dp),
        contentAlignment = if (on) Alignment.CenterEnd else Alignment.CenterStart) {
        Box(Modifier.size(22.dp).shadow(1.dp, CircleShape).clip(CircleShape).background(Color.White))
    }
}
