package dezhcode.asotas.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
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
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Shadow
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import dezhcode.asotas.AppViewModel
import dezhcode.asotas.GAMES
import dezhcode.asotas.Game
import dezhcode.asotas.HomeState
import dezhcode.asotas.Tab
import dezhcode.asotas.core.Daily
import dezhcode.asotas.core.Friends
import dezhcode.asotas.core.Me
import dezhcode.asotas.core.TableInfo
import dezhcode.asotas.fd
import dezhcode.asotas.game

/** خانه (game_club/webapp/index.html): سربرگ، یوزرنیم تازه، جایزهٔ روزانه، «چی بازی کنیم؟»، میزای دیگه‌ت،
 *  کارهای سریع و کارت دوستان */
@Composable
fun HomeScreen(vm: AppViewModel, bottom: Dp) {
    when (val s = vm.home) {
        HomeState.Loading -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { CircularProgressIndicator(color = Aso.c.acc) }
        is HomeState.Failed -> Failed(s.message, vm::refresh)
        is HomeState.Ready -> Home(s.me, vm, bottom)
    }
}

@Composable
fun Failed(message: String, retry: () -> Unit) {
    Column(Modifier.fillMaxSize().padding(24.dp), verticalArrangement = Arrangement.Center, horizontalAlignment = Alignment.CenterHorizontally) {
        Text("😵", style = peyda(48f, 56f))
        Spacer(Modifier.height(12.dp))
        Text(message, textAlign = TextAlign.Center, color = Aso.c.ink)
        Spacer(Modifier.height(16.dp))
        Btn("دوباره امتحان کن", retry)
    }
}

@Composable
private fun Home(me: Me, vm: AppViewModel, bottom: Dp) {
    Column(Modifier.fillMaxSize()) {
        Header(me, vm)
        Column(
            Modifier.fillMaxSize().verticalScroll(rememberScrollState())
                .padding(PaddingValues(start = 16.dp, end = 16.dp, top = 8.dp, bottom = bottom + 24.dp)),
            verticalArrangement = Arrangement.spacedBy(20.dp),
        ) {
            if (me.maintenance) NoteBar("داریم آپدیت می‌کنیم بعضی میزها چند دقیقه دیگه باز می‌شن", bad = false)
            if (me.notice.isNotBlank()) NoteBar(me.notice, bad = false)
            if (me.banned) NoteBar("شرمنده داش حسابت تو AsoTas بسته شده", bad = true)
            if (me.nameHint) NameHint(me.name, ok = vm::hideNameHint, edit = vm::openNameEdit)
            if (vm.showDaily) DailyCard(me.daily, vm.busy, vm::claimDaily)
            Column {
                Text("چی بازی کنیم؟", style = rokh(28f, 36f), color = Aso.c.ink, modifier = Modifier.padding(top = 4.dp))
                Bento(vm)
            }
            if (me.tables.isNotEmpty()) Tables(me.tables, vm)
            Quick(vm)
            FriendsCard(vm.friends, onClick = { vm.selectTab(Tab.FRIENDS) })
        }
    }
}

// ---------- سربرگ: عکس و نام و سطح، زنگ، موجودی ----------
@Composable
private fun Header(me: Me, vm: AppViewModel) {
    val c = Aso.c
    Row(
        Modifier.fillMaxWidth().background(c.ground.copy(alpha = .92f)).padding(horizontal = 16.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Row(
            Modifier.weight(1f).press(.98f) { vm.selectTab(Tab.PROFILE) },
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Face(me.name, me.av, me.pic, Modifier.lined(CircleShape))
            Column(Modifier.weight(1f, fill = false)) {
                Text(me.name, style = peyda(16f, 22f, 800), color = c.ink, maxLines = 1, overflow = TextOverflow.Ellipsis)
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text("سطح ${me.level.lv.fd()}", style = peyda(11.5f, 17f), color = c.inkMuted)
                    Box(Modifier.width(52.dp).height(5.dp).clip(RoundedCornerShape(3.dp)).background(c.line)) {
                        Box(Modifier.fillMaxWidth(me.level.frac.toFloat().coerceIn(0f, 1f)).height(5.dp).clip(RoundedCornerShape(3.dp)).background(c.acc))
                    }
                }
            }
        }
        IconBtn("bell", onClick = { vm.openSheet(dezhcode.asotas.Sheet.Notifications) }, badge = alertCount(me) + vm.inboxUnread)
        CoinPill(me.coins, onClick = { vm.selectTab(Tab.SHOP) })
    }
}

@Composable
private fun NoteBar(text: String, bad: Boolean) {
    val c = Aso.c
    Row(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(22.dp))
            .background(if (bad) c.danger.copy(alpha = .12f) else c.accTint).padding(12.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically,
    ) {
        Ic(if (bad) "ban" else "info", size = 20.dp, tint = if (bad) c.danger else c.accDeep)
        Text(text, style = peyda(13.5f, 22f, 800), color = if (bad) c.danger else c.accDeep)
    }
}

// ---------- یوزرنیم تازه ----------
@Composable
private fun NameHint(name: String, ok: () -> Unit, edit: () -> Unit) {
    val c = Aso.c
    val shape = RoundedCornerShape(22.dp)
    Column(Modifier.fillMaxWidth().clip(shape).background(c.surface).lined(shape).padding(14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Box(Modifier.size(44.dp).clip(CircleShape).background(c.accTint), contentAlignment = Alignment.Center) { Ic("user", size = 22.dp, tint = c.acc) }
            Column {
                Text("اسمت تو بازی اینه", style = peyda(12.5f, 18f), color = c.inkMuted)
                Text(name, style = peyda(18f, 26f, 800), color = c.ink, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Btn("همین خوبه", ok, Modifier.weight(1f).height(44.dp), kind = BtnKind.Light, small = true)
            Btn("عوضش کن", edit, Modifier.weight(1f).height(44.dp), small = true)
        }
    }
}

// ---------- جایزهٔ روزانه (dailyHtml در gc.js) ----------
@Composable
fun DailyCard(d: Daily, busy: Boolean, claim: () -> Unit) {
    val c = Aso.c
    val shape = RoundedCornerShape(28.dp)
    Column(Modifier.fillMaxWidth().clip(shape).background(c.surface).lined(shape).padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Column {
            Text("جایزهٔ روزانهٔ تاسی 🎁", style = peyda(16f, 24f, 800), color = c.ink)
            Text(
                if (d.claimed) "امروزو گرفتی فردا دوباره سر بزن تا زنجیره‌ت نشکنه" else "هر روز پشت هم بیای بیشتر می‌گیری و روز آخر یه جایزهٔ درشت داره",
                style = peyda(12.5f, 20f), color = c.inkMuted,
            )
        }
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            d.plan.forEachIndexed { i, n ->
                val k = i + 1L
                val done = k <= d.day
                val today = !d.claimed && k == d.next
                val big = i == d.plan.lastIndex
                val box = RoundedCornerShape(14.dp)
                Box(Modifier.weight(1f)) {
                    Column(
                        Modifier.fillMaxWidth().clip(box)
                            .background(if (today || big) c.coinTint else c.surfaceSunk)
                            .lined(box, if (today) 2.dp else 1.5.dp, if (today) c.gold else c.line)
                            .padding(top = 7.dp, bottom = 6.dp, start = 2.dp, end = 2.dp),
                        horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(2.dp),
                    ) {
                        Text("روز ${k.fd()}", style = peyda(10f, 14f, 700), color = c.inkMuted, maxLines = 1)
                        Coin(20.dp)
                        Text(n.fd(), style = peyda(13f, 18f, 800), color = c.coinText)
                    }
                    if (done) {
                        Box(Modifier.align(Alignment.TopEnd).offset(4.dp, (-6).dp).size(18.dp).clip(CircleShape).background(c.success), contentAlignment = Alignment.Center) {
                            Ic("check", size = 11.dp, tint = Color.White, stroke = 3f)
                        }
                    }
                }
            }
        }
        Btn(
            if (d.claimed) "فردا دوباره بیا 😉" else "بگیرش · ${d.plan.getOrElse((d.next - 1).toInt().coerceAtLeast(0)) { 0L }.fd()} سکه",
            claim, Modifier.fillMaxWidth(), kind = BtnKind.Gold, enabled = !d.claimed && !busy,
        )
    }
}

// ---------- کاشی بازی ها (hm-bento): حکم پهن، منچ بلند، فوتبال و بیلیارد، بقیه پهن ----------
@Composable
private fun Bento(vm: AppViewModel) {
    val g = GAMES.associateBy { it.id }
    Column(Modifier.padding(top = 30.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Tile(g.getValue("hokm"), vm, Modifier.fillMaxWidth().height(116.dp), big = true)
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Tile(g.getValue("football"), vm, Modifier.fillMaxWidth().height(104.dp))
                Tile(g.getValue("billiard"), vm, Modifier.fillMaxWidth().height(104.dp))
            }
            Tile(g.getValue("ludo"), vm, Modifier.weight(1f).height(220.dp))
        }
        for (id in listOf("divar", "esmfamil", "lashgar", "snakes")) {
            Tile(g.getValue(id), vm, Modifier.fillMaxWidth().height(104.dp))
        }
    }
}

private val TitleShadow = Shadow(Color(0x4D000000), androidx.compose.ui.geometry.Offset(0f, 2f), 6f)

@Composable
private fun Tile(game: Game, vm: AppViewModel, modifier: Modifier, big: Boolean = false) {
    val shape = RoundedCornerShape(22.dp)
    Box(modifier.press(.98f) { vm.openGame(game) }) {
        Box(Modifier.matchParentSize().shadow(14.dp, shape, ambientColor = GAME_SHADOW[game.id] ?: Color.Black, spotColor = GAME_SHADOW[game.id] ?: Color.Black).clip(shape)) {
            GameBackground(game.id)
            Box(Modifier.matchParentSize().background(Brush.verticalGradient(0f to Color.Transparent, .36f to Color.Transparent, 1f to Color(0x94000000))))
        }
        Column(Modifier.align(Alignment.BottomStart).padding(horizontal = 14.dp, vertical = 12.dp)) {
            Text(game.title, style = rokh(if (big) 30f else 22f, if (big) 38f else 28f).copy(shadow = TitleShadow), color = Color.White)
            Text(game.sub, style = peyda(11.5f, 17f, 600), color = Color.White.copy(alpha = .92f), maxLines = 2)
        }
        if (game.tag != null) {
            val hot = game.tag == "محبوب"
            Text(
                game.tag, style = peyda(11f, 22f, 800), color = if (hot) Aso.c.goldInk else Color(0xFF161922),
                modifier = Modifier.align(Alignment.TopStart).padding(10.dp).clip(RoundedCornerShape(8.dp))
                    .background(if (hot) Aso.c.gold else Color.White.copy(alpha = .94f)).padding(horizontal = 8.dp),
            )
        }
        HomeOuts(game.id)
    }
}

// ---------- میزای دیگه‌ت ----------
@Composable
private fun Tables(tables: List<TableInfo>, vm: AppViewModel) {
    val c = Aso.c
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text("میزای دیگه‌ت", style = rokh(17f, 26f), color = c.ink, modifier = Modifier.padding(bottom = 4.dp))
        tables.forEach { t ->
            val g = game(t.game)
            val shape = RoundedCornerShape(18.dp)
            Row(
                Modifier.fillMaxWidth().clip(shape).background(c.surface).lined(shape).press(.985f) { vm.openTable(t) }
                    .padding(start = 8.dp, end = 12.dp, top = 8.dp, bottom = 8.dp),
                verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                GameThumb(t.game, 48.dp)
                Column(Modifier.weight(1f)) {
                    Text(g?.title ?: t.game, style = rokh(15f, 22f), color = c.ink)
                    Text(tableStatus(t), style = peyda(12f, 18f, 700), color = c.inkMuted, maxLines = 1, overflow = TextOverflow.Ellipsis)
                }
                Text(
                    if (t.kind == "playing") "ادامه" else "برو", style = peyda(13f, 20f, 800), color = c.ink,
                    modifier = Modifier.clip(RoundedCornerShape(12.dp)).background(c.surfaceSunk).padding(horizontal = 12.dp, vertical = 9.dp),
                )
            }
        }
    }
}

private fun tableStatus(t: TableInfo): String = when (t.kind) {
    "queue" -> "دنبال حریفیم · ${t.found.fd()} از ${t.need.fd()}"
    "lobby" -> "منتظر بازیکنا · ${t.found.fd()} از ${t.need.fd()}"
    else -> "بازی در جریانه"
}

// ---------- کارهای سریع ----------
@Composable
private fun Quick(vm: AppViewModel) {
    val c = Aso.c
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        QuickTile("userAdd", c.accTint, c.acc, "دعوت دوست", "با هم بازی کنیم", Modifier.weight(1f)) { vm.openSheet(dezhcode.asotas.Sheet.AddFriend) }
        QuickTile("cards", if (c.dark) Color(0x2E3DD68C) else Color(0xFFE3F1E8), if (c.dark) Color(0xFF7ED6A1) else Color(0xFF1F6B3B),
            "ورق و میز", "قیافهٔ حکم", Modifier.weight(1f)) { vm.selectTab(Tab.SHOP) }
        QuickTile("help", c.surfaceSunk, c.inkMuted, "راهنما", "قانون بازیا", Modifier.weight(1f)) { vm.openHelp() }
    }
}

@Composable
private fun QuickTile(icon: String, bg: Color, fg: Color, title: String, sub: String, modifier: Modifier, onClick: () -> Unit) {
    val c = Aso.c
    val shape = RoundedCornerShape(18.dp)
    Column(
        modifier.clip(shape).background(c.surface).lined(shape).press(onClick = onClick).padding(top = 12.dp, bottom = 10.dp, start = 6.dp, end = 6.dp),
        horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        Box(Modifier.size(40.dp).clip(RoundedCornerShape(13.dp)).background(bg), contentAlignment = Alignment.Center) { Ic(icon, size = 21.dp, tint = fg) }
        Text(title, style = peyda(12.5f, 18f, 800), color = c.ink)
        Text(sub, style = peyda(11f, 16f), color = c.inkMuted)
    }
}

// ---------- کارت دوستان (rank-card) ----------
@Composable
private fun FriendsCard(f: Friends?, onClick: () -> Unit) {
    val c = Aso.c
    val on = f?.friends.orEmpty().filter { it.online }
    val all = f?.friends.orEmpty()
    val shape = RoundedCornerShape(20.dp)
    Row(
        Modifier.fillMaxWidth().clip(shape).background(c.surface).lined(shape).press(.985f, onClick = onClick).padding(horizontal = 14.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Box(Modifier.size(44.dp).clip(RoundedCornerShape(14.dp)).background(c.accTint), contentAlignment = Alignment.Center) { Ic("users", size = 22.dp, tint = c.acc) }
        Column(Modifier.weight(1f)) {
            Text(if (on.isNotEmpty()) "رفیقای آنلاین" else "دوستان", style = peyda(14f, 21f, 800), color = c.ink)
            Text(
                when {
                    f == null -> "یه لحظه…"
                    on.isNotEmpty() -> "${on.size.fd()} نفر الان آنلاینن"
                    all.isNotEmpty() -> "${all.size.fd()} رفیق داری · الان کسی آنلاین نیست"
                    else -> "رفیقاتو با یوزرنیمشون اضافه کن"
                },
                style = peyda(11.5f, 17f), color = c.inkMuted,
            )
        }
        Row {
            (on.ifEmpty { all }).take(3).forEachIndexed { i, fr ->
                // هم پوشانی ۸ پیکسلی (margin-inline-start:-8px)؛ در راست به چپ رو به ابتدای ردیف
                Face(fr.person.name, fr.person.av, fr.person.pic, Modifier.offset(x = (-8 * i).dp), size = 30.dp)
            }
        }
        Ic("fwd", size = 18.dp, tint = c.inkMuted)
    }
}
