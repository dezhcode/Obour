package dezhcode.asotas.ui

import androidx.activity.compose.BackHandler
import androidx.compose.animation.core.animateDpAsState
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.scaleIn
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.absoluteOffset
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.AbsoluteAlignment
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import dezhcode.asotas.AppViewModel
import dezhcode.asotas.TableModel
import dezhcode.asotas.core.HokmGame
import dezhcode.asotas.fd
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlin.math.abs

// ---------- برگ ها: ۰ تا ۵۱؛ خال = برگ / ۱۳ (۰ پیک، ۱ دل، ۲ خشت، ۳ گشنیز)، ارزش = برگ ٪ ۱۳ (۰ = ۲ ... ۱۲ = آس) ----------
/** پیام های سریع گفتگوی میز حکم (hokm.js: QUICK) */
private val HOKM_QUICK = listOf("سلام!", "خوش‌بازی!", "آفرین یار", "حکم خوبی بود", "زود باش", "یه دست دیگه؟")
private val RANKS = listOf("2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A")
private val SUITS = listOf("♠", "♥", "♦", "♣")
val SUIT_FA = listOf("پیک", "دل", "خشت", "گشنیز")
private fun suitOf(c: Long) = (c / 13).toInt()
private fun isRed(s: Int) = s == 1 || s == 2

@Composable
private fun Card(c: Long, w: Dp, look: String, modifier: Modifier = Modifier) {
    val s = suitOf(c)
    CardFace(RANKS[(c % 13).toInt()], SUITS[s], isRed(s), w, look, modifier)
}

/** صفحهٔ بازی حکم (hokm.html و hokm.js): من پایین، یار بالا، حریف ها چپ و راست */
@Composable
fun HokmScreen(vm: AppViewModel, matchId: String) {
    val model = remember(matchId) { vm.table("hokm", matchId) }
    val scope = rememberCoroutineScope()
    var leaving by remember { mutableStateOf(false) }
    BackHandler { leaving = true }
    LaunchedEffect(Unit) { if (vm.shop.styles == null) vm.shop.load() }
    LaunchedEffect(model) {
        while (true) {
            model.poll()
            val v = model.view
            if (model.failed != null || v?.status == "over" || v?.status == "cancelled") break
            delay(900)
        }
    }
    val table = vm.shop.styles?.table ?: "a"
    val look = vm.shop.styles?.cards ?: "a"
    CompositionLocalProvider(LocalAso provides gameColors(Aso.c)) {
        val c = Aso.c
        Felt(table, Modifier.fillMaxSize()) {
            val v = model.view
            val g = v?.hokm
            when {
                model.failed != null -> Column(Modifier.align(Alignment.Center).padding(24.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                    Text(model.failed.orEmpty(), style = peyda(15f, 24f, 700), color = c.ink, textAlign = TextAlign.Center)
                    Spacer(Modifier.height(12.dp))
                    Btn("برگشت", vm.play::closeGame)
                }
                g == null -> CircularProgressIndicator(Modifier.align(Alignment.Center), color = c.acc)
                else -> HokmTable(vm, model, g, look, onLeave = { leaving = true })
            }
            // گفتگوی سر میز: پیام ها بالای نوار وضعیت شناور می شوند (hokm.js: rest = meBar)
            TableChatLayer(model, HOKM_QUICK, rest = 204.dp, enabled = v?.status == "playing" && g?.over == false)
            if (v != null && g != null && (v.status == "over" || g.over)) {
                val myTeam = (g.me?.toIntOrNull() ?: 0) % 2
                val won = v.result?.won ?: (g.winner?.toInt() == myTeam)
                HokmResult(g, myTeam, won, v.result?.coins ?: 0, v.result?.cups ?: 0,
                    again = { vm.play.closeGame(); vm.play.openLobby("hokm") }, home = vm.play::closeGame)
            }
        }
        if (leaving) {
            Dialog(onDismissRequest = { leaving = false }) {
                Column(Modifier.clip(RoundedCornerShape(28.dp)).background(c.surface).padding(20.dp),
                    horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Box(Modifier.size(64.dp).clip(CircleShape).background(c.danger.copy(alpha = .16f)), contentAlignment = Alignment.Center) { Ic("exit", size = 30.dp, tint = c.danger) }
                    Text("از میز بری بیرون؟", style = rokh(21f, 30f), color = c.ink)
                    Text("اگه بری ربات جات بازی می‌کنه و یارت تنها نمی‌مونه ولی این بازی باخت حساب می‌شه", style = peyda(14f, 24f), color = c.inkMuted, textAlign = TextAlign.Center)
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Btn("می‌مونم", { leaving = false }, Modifier.weight(1f))
                        Btn("خروج", { leaving = false; scope.launch { model.leave(); vm.play.closeGame() } }, Modifier.weight(1f), kind = BtnKind.DangerSoft)
                    }
                    Btn("بعداً برمی‌گردم", { leaving = false; vm.play.closeGame() }, Modifier.fillMaxWidth(), kind = BtnKind.Light)
                }
            }
        }
    }
}

/** جای نسبی هر صندلی نسبت به من: ۰ پایین (خودم)، ۱ راست، ۲ بالا (یار)، ۳ چپ؛ نوبت خلاف عقربه های ساعت */
private fun rel(seat: String, me: String): Int = ((seat.toIntOrNull() ?: 0) - (me.toIntOrNull() ?: 0) + 4) % 4

private fun seatAt(me: String, r: Int): String = (((me.toIntOrNull() ?: 0) + r) % 4).toString()

private fun nameOf(g: HokmGame, s: String): String = g.players[s]?.let { if (it.me) "تو" else it.name } ?: "؟"

@Composable
private fun HokmTable(vm: AppViewModel, model: TableModel, g: HokmGame, look: String, onLeave: () -> Unit) {
    val c = Aso.c
    val scope = rememberCoroutineScope()
    val me = g.me ?: "0"
    val myTeam = (me.toIntOrNull() ?: 0) % 2
    val cur = g.turn
    val mine = cur == me
    val choosing = g.phase == "trump" && g.hakem == me
    val canPlay = mine && g.phase == "play" && !model.acting
    var got by remember { mutableLongStateOf(System.currentTimeMillis()) }
    var now by remember { mutableLongStateOf(System.currentTimeMillis()) }
    LaunchedEffect(g.seq, g.deadlineMs) { got = System.currentTimeMillis() }
    LaunchedEffect(Unit) { while (true) { now = System.currentTimeMillis(); delay(200) } }
    val frac = if (g.turnMs > 0 && g.deadlineMs > 0) (g.deadlineMs - (now - got)).coerceAtLeast(0).toFloat() / g.turnMs else 0f

    // اعلان های کوتاه وسط میز: حکم انتخاب شد، نتیجهٔ دست
    var banner by remember { mutableStateOf<String?>(null) }
    var seen by remember { mutableLongStateOf(g.seq) }
    LaunchedEffect(g.seq) {
        val fresh = g.events.filter { it.seq > seen }
        seen = g.seq
        fresh.lastOrNull { it.t == "trump" || it.t == "hand" }?.let { e ->
            banner = if (e.t == "trump") "حکم ${SUIT_FA.getOrElse((e.suit ?: 0).toInt()) { "" }} شد ${SUITS.getOrElse((e.suit ?: 0).toInt()) { "" }}"
            else {
                val ours = e.team?.toInt() == myTeam
                (if (ours) "این دست مال ما شد" else "این دست مال حریف شد") + if (e.kot) " · کُت! (${e.pts.fd()} امتیاز)" else ""
            }
            delay(2600)
            banner = null
        }
    }

    Column(Modifier.fillMaxSize().statusBarsPadding().navigationBarsPadding()) {
        // ---------- سربرگ: خروج، امتیاز و حکم، راهنما، صدا ----------
        Row(Modifier.fillMaxWidth().padding(horizontal = 10.dp, vertical = 8.dp), verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            GameIcon("exit", onLeave)
            ScorePill(g, myTeam, Modifier.weight(1f))
            GameIcon("help") { vm.openHelp("hHokm") }
            GameIcon(if (vm.me?.sound != false) "soundOn" else "soundOff") { vm.toggleSound() }
        }
        // ---------- میز: یار بالا، حریف ها دو طرف، برگ های وسط ----------
        BoxWithConstraints(Modifier.fillMaxWidth().weight(1f)) {
            val w = maxWidth
            val h = maxHeight
            Seat(g, seatAt(me, 2), cur, frac, look, Modifier.align(Alignment.TopCenter).padding(top = 6.dp), side = 2)
            Seat(g, seatAt(me, 1), cur, frac, look, Modifier.align(AbsoluteAlignment.CenterRight).padding(end = 8.dp), side = 1)
            Seat(g, seatAt(me, 3), cur, frac, look, Modifier.align(AbsoluteAlignment.CenterLeft).padding(start = 8.dp), side = 3)
            // برگ های این دور: هر کدام سمت کسی که انداخته
            val trick = if (g.trick.isNotEmpty()) g.trick else if (g.phase == "collect") g.lastTrick else emptyList()
            trick.forEach { p ->
                val r = rel(p.seat, me)
                val dx = when (r) { 1 -> 50.dp; 3 -> (-50).dp; else -> 0.dp }
                val dy = when (r) { 0 -> 46.dp; 2 -> (-46).dp; else -> 0.dp }
                key(p.seat, p.card) {
                    val ox by animateDpAsState(dx, label = "tx")
                    val oy by animateDpAsState(dy, label = "ty")
                    Card(p.card, 56.dp, look, Modifier.align(Alignment.Center).offset(ox, oy).rotate(((p.card % 7) - 3) * 3f))
                }
            }
            // نام کامل: وگرنه ColumnScope.AnimatedVisibility ستون بیرونی انتخاب می‌شود و کامپایل نمی‌شود
            androidx.compose.animation.AnimatedVisibility(banner != null, Modifier.align(Alignment.Center), enter = fadeIn() + scaleIn(initialScale = .9f), exit = fadeOut()) {
                Text(banner.orEmpty(), style = peyda(15f, 22f, 800), color = c.ink, textAlign = TextAlign.Center,
                    modifier = Modifier.clip(RoundedCornerShape(16.dp)).background(Color.Black.copy(alpha = .55f)).padding(horizontal = 16.dp, vertical = 10.dp))
            }
            if (choosing) TrumpPicker(Modifier.align(Alignment.BottomCenter).padding(bottom = 8.dp)) { s -> scope.launch { model.act("trump", s.toLong()) } }
            Spacer(Modifier.size(w, h))
        }
        // ---------- وضعیت و چت ----------
        Row(Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 6.dp), verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(Modifier.weight(1f).clip(CircleShape).background(Color.Black.copy(alpha = .35f)).padding(start = 4.dp, end = 14.dp, top = 4.dp, bottom = 4.dp),
                verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                val who = if (g.phase == "trump") g.hakem else cur
                val p = who?.let { g.players[it] }
                if (p != null) Face(if (p.me) "تو" else p.name, p.av, if (p.bot) null else p.pic, size = 36.dp, bot = p.bot)
                Column(Modifier.weight(1f)) {
                    val (t, s) = when {
                        g.over -> "بازی تموم شد" to ""
                        g.phase == "trump" && choosing -> "تو حاکمی" to "از رو این پنج برگ حکمو انتخاب کن"
                        g.phase == "trump" -> "حاکم: ${nameOf(g, g.hakem)}" to "داره حکم انتخاب می‌کنه…"
                        g.phase == "collect" -> "این دور مال ${g.lastWinner?.let { nameOf(g, it) } ?: ""}" to ""
                        g.phase == "handover" -> "دست بعدی" to "برگا دارن پخش می‌شن…"
                        canPlay -> "نوبت توئه" to "یه برگ بنداز"
                        cur != null -> "نوبت ${nameOf(g, cur)}" to (if (g.players[cur]?.bot == true) "ربات داره فکر می‌کنه…" else "صبر کن…")
                        else -> "" to ""
                    }
                    Text(t, style = peyda(14f, 20f, 800), color = c.ink, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    if (s.isNotEmpty()) Text(s, style = peyda(11.5f, 16f), color = c.inkMuted, maxLines = 1, overflow = TextOverflow.Ellipsis)
                }
            }
            Box {
                Row(Modifier.height(44.dp).clip(CircleShape).background(c.acc).press { model.openChat(true) }.padding(horizontal = 14.dp),
                    verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    Ic("chat", size = 20.dp, tint = c.accInk)
                    Text("چت کن", style = peyda(14f, 20f, 800), color = c.accInk)
                }
                ChatBadge(model.unread, Modifier.align(Alignment.TopEnd), ring = Color(0xFF0C1915))
            }
        }
        // ---------- دست من ----------
        Hand(g.hand, if (canPlay) g.legal else emptyList(), canPlay, look) { card -> scope.launch { model.act("play", card) } }
    }
}

/** امتیاز دو تیم و خال حکم وسطش */
@Composable
private fun ScorePill(g: HokmGame, myTeam: Int, modifier: Modifier) {
    val c = Aso.c
    Row(modifier.height(52.dp).clip(RoundedCornerShape(18.dp)).background(Color.Black.copy(alpha = .35f)).padding(horizontal = 10.dp),
        verticalAlignment = Alignment.CenterVertically) {
        TeamCol(g, "خودت", myTeam, true, Modifier.weight(1f))
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            val s = g.trump?.toInt()
            Box(Modifier.size(32.dp).clip(CircleShape).background(if (s != null) Color.White else Color.Transparent)
                .then(if (s == null) Modifier.border(1.5.dp, c.inkMuted, CircleShape) else Modifier), contentAlignment = Alignment.Center) {
                Text(if (s != null) SUITS[s] else "؟", style = peyda(17f, 20f, 800), color = if (s != null && isRed(s)) Color(0xFFD7263D) else if (s != null) Color(0xFF1C2235) else c.inkMuted)
            }
            Text(if (s != null) "حکم ${SUIT_FA[s]}" else "حکم", style = peyda(10f, 14f, 700), color = c.inkMuted)
        }
        TeamCol(g, "حریف", 1 - myTeam, false, Modifier.weight(1f))
    }
}

@Composable
private fun TeamCol(g: HokmGame, label: String, t: Int, gold: Boolean, m: Modifier) {
    val c = Aso.c
    Column(m, horizontalAlignment = Alignment.CenterHorizontally) {
        Text(label, style = peyda(11f, 14f, 800), color = if (gold) c.acc else c.inkMuted)
        Text("${g.score.getOrElse(t) { 0L }.fd()}/${g.target.fd()}", style = rokh(15f, 20f), color = c.ink)
        Text("${g.tricks.getOrElse(t) { 0L }.fd()} دست", style = peyda(10f, 13f), color = c.inkMuted)
    }
}

/** بازیکن دیگر سر میز: عکس با حلقهٔ زمان نوبت، تاج حاکم، اسم و تعداد برگ و پشت برگ ها */
@Composable
private fun Seat(g: HokmGame, s: String, cur: String?, frac: Float, look: String, modifier: Modifier, side: Int) {
    val c = Aso.c
    val p = g.players[s] ?: return
    val active = s == cur || (g.phase == "trump" && s == g.hakem)
    Column(modifier, horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(3.dp)) {
        Box(contentAlignment = Alignment.Center) {
            if (active && frac > 0f) Canvas(Modifier.size(62.dp)) { drawArc(c.acc, -90f, 360f * frac.coerceIn(0f, 1f), false, style = Stroke(3.dp.toPx())) }
            Face(p.name, p.av, if (p.bot) null else p.pic, size = 54.dp, ring = if (active) c.acc else Color.White.copy(alpha = .85f), bot = p.bot)
            if (s == g.hakem) {
                Box(Modifier.align(Alignment.TopEnd).size(22.dp).clip(CircleShape).background(c.gold), contentAlignment = Alignment.Center) {
                    Text("👑", style = peyda(11f, 14f))
                }
            }
        }
        Text(p.name, style = peyda(12.5f, 18f, 800), color = if (p.out) c.inkMuted else c.ink, maxLines = 1, overflow = TextOverflow.Ellipsis,
            modifier = Modifier.width(90.dp), textAlign = TextAlign.Center)
        Text(
            (if (side == 2) "یارتو · " else if (s == g.hakem) "حاکم · " else "") + "${p.count.fd()} برگ",
            style = peyda(11f, 15f, 700), color = if (s == g.hakem) c.acc else c.inkMuted,
        )
        // پشت برگ ها: بالا افقی، دو طرف عمودی
        val n = p.count.toInt().coerceAtMost(13)
        if (n > 0) {
            Box(Modifier.size(if (side == 2) (26 + (n - 1) * 6).dp else 30.dp, if (side == 2) 38.dp else (38 + (n - 1) * 3).dp)) {
                repeat(n) { i ->
                    CardBack(look, 26.dp, Modifier.align(AbsoluteAlignment.TopLeft).absoluteOffset(if (side == 2) (i * 6).dp else 2.dp, if (side == 2) 0.dp else (i * 3).dp))
                }
            }
        }
    }
}

/** انتخاب حکم (فقط حاکم، با دیدن پنج برگ اول) */
@Composable
private fun TrumpPicker(modifier: Modifier, pick: (Int) -> Unit) {
    val c = Aso.c
    Column(modifier.clip(RoundedCornerShape(22.dp)).background(c.surface).padding(14.dp), horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Text("حکمو انتخاب کن", style = rokh(17f, 24f), color = c.ink)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            SUITS.forEachIndexed { i, sym ->
                Column(Modifier.width(64.dp).clip(RoundedCornerShape(16.dp)).background(Color.White).press(.92f) { pick(i) }.padding(vertical = 8.dp),
                    horizontalAlignment = Alignment.CenterHorizontally) {
                    Text(sym, style = peyda(30f, 34f, 800), color = if (isRed(i)) Color(0xFFD7263D) else Color(0xFF1C2235))
                    Text(SUIT_FA[i], style = peyda(12f, 16f, 800), color = Color(0xFF1C2235))
                }
            }
        }
    }
}

/** دست من: برگ ها روی هم با کمی قوس؛ برگ های مجاز بالاتر، بقیه کم رنگ؛ لمس = انداختن */
@Composable
private fun Hand(hand: List<Long>, legal: List<Long>, canPlay: Boolean, look: String, play: (Long) -> Unit) {
    BoxWithConstraints(Modifier.fillMaxWidth().height(130.dp).padding(horizontal = 8.dp), contentAlignment = AbsoluteAlignment.TopLeft) {
        val n = hand.size
        if (n == 0) return@BoxWithConstraints
        val cw = 62.dp
        val step = if (n > 1) minOf(cw * .72f, (maxWidth - cw) / (n - 1)) else 0.dp
        val total = cw + step * (n - 1)
        val start = (maxWidth - total) / 2
        hand.forEachIndexed { i, card ->
            val mid = (n - 1) / 2f
            val ok = card in legal
            key(card) {
                val lift by animateDpAsState(if (canPlay && ok) (-14).dp else 0.dp, label = "lift")
                Card(card, cw, look,
                    Modifier.absoluteOffset(start + step * i, 22.dp + (abs(i - mid) * abs(i - mid) * .9f).dp + lift)
                        .rotate((i - mid) * 3f)
                        .alpha(if (canPlay && !ok) .55f else 1f)
                        .then(if (canPlay && ok) Modifier.press(.95f) { play(card) } else Modifier))
            }
        }
    }
}

@Composable
private fun HokmResult(g: HokmGame, myTeam: Int, won: Boolean, coins: Long, cups: Long, again: () -> Unit, home: () -> Unit) {
    val c = Aso.c
    Dialog(onDismissRequest = home) {
        Column(Modifier.clip(RoundedCornerShape(28.dp)).background(c.surface).padding(22.dp),
            horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text(if (won) "🏆" else "🃏", style = peyda(52f, 60f))
            Text(if (won) "بردیم! دمت گرم 🎉" else "این بازی مال حریف شد", style = rokh(22f, 30f), color = c.ink, textAlign = TextAlign.Center)
            Text("${g.score.getOrElse(myTeam) { 0L }.fd()} – ${g.score.getOrElse(1 - myTeam) { 0L }.fd()} · تا ${g.target.fd()} دست",
                style = peyda(15f, 22f, 800), color = c.inkMuted)
            if (cups != 0L || coins > 0) {
                Row(horizontalArrangement = Arrangement.spacedBy(14.dp), verticalAlignment = Alignment.CenterVertically) {
                    if (cups != 0L) Text("${if (cups > 0) "+" else "−"}${abs(cups).fd()} جام", style = peyda(18f, 26f, 800), color = if (cups > 0) c.coinText else c.inkMuted)
                    if (coins > 0) Amount(coins, size = 18f)
                }
            }
            Btn("یه دست دیگه", again, Modifier.fillMaxWidth(), kind = BtnKind.Gold)
            Btn("برگشت به خانه", home, Modifier.fillMaxWidth(), kind = BtnKind.Light)
        }
    }
}
