package dezhcode.asotas.ui

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.net.Uri
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.absoluteOffset
import androidx.compose.foundation.layout.defaultMinSize
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.AbsoluteAlignment
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.graphics.vector.PathParser
import androidx.compose.ui.graphics.vector.rememberVectorPainter
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import dezhcode.asotas.AppViewModel
import dezhcode.asotas.Waiting
import dezhcode.asotas.Who
import dezhcode.asotas.fd
import dezhcode.asotas.game
import dezhcode.asotas.core.level
import org.json.JSONObject

/** یک حالت بازی در لابی (opt.modes در لابی هر بازی) */
data class Mode(val v: String, val label: String, val icon: String, val desc: String, val short: String, val cfg: Map<String, Any>)

/** ویژگی لابی هر بازی: حالت ها، قانون ها و رنگ تأکید */
data class LobbySpec(val game: String, val modes: List<Mode>, val rules: List<Pair<String, String>>, val privateSub: String, val edge: Color, val acc: Color, val accDark: Color)

val LOBBIES = mapOf(
    "ludo" to LobbySpec(
        "ludo",
        listOf(
            Mode("l22", "سریع ۲ نفره", "bolt", "رو در رو با ۲ مهره و هر کی زودتر هر دو مهره‌شو برسونه خونه برده · حدود ۵ دقیقه", "۲ مهره · حدود ۵ دقیقه", mapOf("players" to 2, "pawns" to 2)),
            Mode("l44", "کلاسیک ۴ نفره", "users", "منچ کامل چهار نفره با ۴ مهره · شلوغ و پرهیجان · حدود ۱۵ دقیقه", "۴ مهره · حدود ۱۵ دقیقه", mapOf("players" to 4, "pawns" to 4)),
            Mode("l42", "سریع ۴ نفره", "dice", "چهار نفره با ۲ مهره · شلوغ ولی کوتاه", "۲ مهره · حدود ۸ دقیقه", mapOf("players" to 4, "pawns" to 2)),
            Mode("l24", "کلاسیک ۲ نفره", "user", "رو در رو با ۴ مهره · کامل و حساب‌شده", "۴ مهره · حدود ۱۲ دقیقه", mapOf("players" to 2, "pawns" to 4)),
        ),
        listOf(
            "رنگ تو زرده" to "و پایین سمت چپ می‌شینی و هر کی صفحه رو از سمت خودش می‌بینه",
            "با ۶" to "مهره از خونه میاد بیرون و یه تاس دیگه هم می‌ریزی",
            "مهره‌ها" to "تو جهت فلش‌ها دور صفحه می‌چرخن و از راهروی رنگ خودت می‌رسن وسط",
            "اگه رو مهرهٔ حریف بشینی" to "اون مهره برمی‌گرده خونه‌ش ولی خونه‌های ستاره‌دار امنن",
            "هر کی" to "زودتر همهٔ مهره‌هاشو برسونه وسط برده",
        ),
        "لینک بفرست و با رفقات منچ بزن", Color(0xFF0B241C), Color(0xFF2B62D6), Color(0xFF3D74E6),
    ),
)

private val HELP_ID = mapOf("ludo" to "hLudo", "hokm" to "hHokm", "football" to "hFootball", "billiard" to "hBilliard", "divar" to "hDivar", "snakes" to "hSnakes")

private fun levelTitle(lv: Long) = when { lv < 3 -> "تازه‌کار"; lv < 6 -> "آشنا"; lv < 10 -> "حرفه‌ای"; else -> "استاد" }

private val StarVector: ImageVector by lazy {
    ImageVector.Builder("star", 24.dp, 24.dp, 24f, 24f).apply {
        addPath(PathParser().parsePathString("M12 1.8 15 8l6.8.8-5 4.7 1.3 6.8L12 17l-6.1 3.3 1.3-6.8-5-4.7L9 8z").toNodes(),
            fill = SolidColor(Color(0xFFF5C451)), stroke = SolidColor(Color(0xFFC99A2E)), strokeLineWidth = .8f)
    }.build()
}

/** لابی هر بازی (gamepage.js): جعبهٔ بازی، سطح تو، تب ها و نوار شروع */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun LobbyScreen(vm: AppViewModel, gameId: String) {
    val spec = LOBBIES[gameId] ?: return
    val g = game(gameId) ?: return
    val base = Aso.c
    // رنگ تأکید لابی همان رنگ بازی است (body.lobby-<بازی>)
    val c = base.copy(acc = if (base.dark) spec.accDark else spec.acc, accDeep = if (base.dark) Color(0xFF9BBBFF) else spec.acc,
        accTint = if (base.dark) spec.accDark.copy(alpha = .22f) else Color(0xFFE7EEFC))
    BackHandler { vm.play.closeLobby() }
    LaunchedEffect(gameId) { vm.profile.load() }
    var tab by rememberSaveable { mutableStateOf("play") }
    var mode by rememberSaveable { mutableStateOf(spec.modes.first().v) }
    var who by rememberSaveable { mutableStateOf(Who.ONLINE) }
    var ranked by rememberSaveable { mutableStateOf(false) }
    val m = spec.modes.first { it.v == mode }
    val rankedOn = vm.me?.rankedEnabled != false
    val rankable = rankedOn && who == Who.ONLINE
    val isRanked = rankable && ranked

    androidx.compose.runtime.CompositionLocalProvider(LocalAso provides c) {
        Box(Modifier.fillMaxSize().background(c.ground)) {
            Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(bottom = 110.dp)) {
                // ---------- در جعبه: دنیای بازی و برچسب نام ----------
                Box(Modifier.fillMaxWidth().height(272.dp).background(Color(0xFF0F2A22))) {
                    Box(Modifier.fillMaxSize().background(ellipseBrush(.3f, .4f, .9f, 0f to Color(0xFF1F4A37), 1f to Color(0xFF0F2A22))))
                    Image(androidx.compose.ui.res.painterResource(g.thumb), null,
                        Modifier.align(AbsoluteAlignment.CenterLeft).absoluteOffset(x = 18.dp, y = 12.dp).size(190.dp).rotate(-6f).shadow(14.dp, RoundedCornerShape(22.dp)).clip(RoundedCornerShape(22.dp)))
                    Box(Modifier.fillMaxWidth().height(110.dp).background(Brush.verticalGradient(listOf(Color(0x57000000), Color.Transparent))))
                    Row(Modifier.fillMaxWidth().statusBarsPadding().padding(horizontal = 16.dp, vertical = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                        IconBtn("back", onClick = { vm.play.closeLobby() })
                        Spacer(Modifier.weight(1f))
                        CoinPill(vm.balance, onClick = {}, plus = false)
                    }
                    if (g.tag != null) {
                        Text(g.tag, style = peyda(11f, 22f, 800), color = if (g.tag == "محبوب") c.goldInk else Color(0xFF161922),
                            modifier = Modifier.align(Alignment.BottomStart).padding(start = 16.dp, bottom = 92.dp).clip(RoundedCornerShape(8.dp))
                                .background(if (g.tag == "محبوب") c.gold else Color.White.copy(alpha = .94f)).padding(horizontal = 8.dp))
                    }
                    Column(Modifier.align(Alignment.BottomStart).padding(16.dp).shadow(8.dp, RoundedCornerShape(14.dp)).clip(RoundedCornerShape(14.dp))
                        .background(c.surface).padding(start = 14.dp, end = 14.dp, top = 8.dp, bottom = 10.dp)) {
                        Text(g.title, style = rokh(28f, 36f), color = c.ink)
                        Text(g.sub, style = peyda(12f, 18f), color = c.inkMuted)
                    }
                }
                // لبهٔ جعبه به رنگ بازی
                Box(Modifier.fillMaxWidth().padding(horizontal = 6.dp).height(12.dp).clip(RoundedCornerShape(bottomStart = 16.dp, bottomEnd = 16.dp)).background(spec.edge))
                Column(Modifier.padding(horizontal = 16.dp)) {
                    LevelCard(vm, gameId, g.title)
                    // ---------- تب ها ----------
                    Row(Modifier.fillMaxWidth().padding(top = 10.dp).height(50.dp)) {
                        listOf("play" to "بازی", "board" to "رده‌بندی", "rules" to "آموزش").forEach { (id, label) ->
                            val on = id == tab
                            Box(Modifier.weight(1f).fillMaxSize().press(.98f) { tab = id }, contentAlignment = Alignment.Center) {
                                Text(label, style = peyda(14.5f, 22f, if (on) 800 else 700), color = if (on) c.ink else c.inkMuted)
                                if (on) Box(Modifier.align(Alignment.BottomCenter).fillMaxWidth(.56f).height(3.dp).clip(RoundedCornerShape(topStart = 3.dp, topEnd = 3.dp)).background(c.acc))
                            }
                        }
                    }
                    Box(Modifier.fillMaxWidth().height(1.dp).background(c.line))
                    Spacer(Modifier.height(16.dp))
                    when (tab) {
                        "play" -> Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                            Head("حالت بازی")
                            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                                spec.modes.forEach { x -> Chip(x.label, x.icon, x.v == mode) { mode = x.v } }
                            }
                            Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(16.dp)).background(c.surfaceSunk).padding(12.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                Ic("info", size = 18.dp, tint = c.inkMuted, modifier = Modifier.padding(top = 2.dp))
                                Text("${m.label}: ${m.desc}", style = peyda(13f, 21f), color = c.ink)
                            }
                            Head("حریف")
                            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                                Who.entries.forEach { w -> Chip(w.label, w.icon, w == who) { who = w } }
                            }
                            Text(if (who == Who.FRIENDS) spec.privateSub else who.desc, style = peyda(12.5f, 20f), color = c.inkMuted)
                            if (rankable) {
                                Head("نوع بازی")
                                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                    Chip("دوستانه", "users", !ranked) { ranked = false }
                                    Chip("رتبه‌ای", "trophy", ranked) { ranked = true }
                                }
                                Text(if (ranked) "برد ۲۰ جام و چند سکه · باخت ۱۰ جام · فقط با بازیکن واقعی" else "بی‌جام و فقط واسه حال کردن",
                                    style = peyda(12.5f, 20f), color = c.inkMuted)
                            }
                        }
                        "rules" -> Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                            Btn("راهنمای کامل", { vm.openHelp(HELP_ID[gameId] ?: "") }, Modifier.fillMaxWidth(), kind = BtnKind.Light, icon = "help")
                            spec.rules.forEachIndexed { i, (b, s) ->
                                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                                    Box(Modifier.size(26.dp).clip(CircleShape).background(c.accTint), contentAlignment = Alignment.Center) {
                                        Text((i + 1).fd(), style = peyda(13f, 18f, 800), color = c.accDeep)
                                    }
                                    Text("$b $s", style = peyda(14f, 23f), color = c.ink, modifier = Modifier.weight(1f))
                                }
                            }
                        }
                        else -> Board(gameId)
                    }
                }
            }
            // ---------- نوار شناور شروع ----------
            if (tab == "play") {
                Row(
                    Modifier.align(Alignment.BottomCenter).navigationBarsPadding().padding(12.dp).fillMaxWidth()
                        .shadow(18.dp, RoundedCornerShape(18.dp)).clip(RoundedCornerShape(18.dp)).background(c.surface.copy(alpha = .96f)).lined(RoundedCornerShape(18.dp))
                        .padding(start = 14.dp, end = 8.dp, top = 8.dp, bottom = 8.dp),
                    verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    Column(Modifier.weight(1f)) {
                        Text("${m.label} · ${who.label} · ${if (isRanked) "رتبه‌ای 🏆" else "دوستانه"}", style = peyda(13f, 18f, 800), color = c.ink,
                            maxLines = 1, overflow = TextOverflow.Ellipsis)
                        Text(m.short, style = peyda(11.5f, 16f), color = c.inkMuted, maxLines = 1)
                    }
                    Btn(who.go, { vm.play.start(gameId, who, m.cfg, isRanked) }, enabled = !vm.play.busy, icon = who.goIcon)
                }
            }
        }
    }
}

@Composable
private fun Head(t: String) = Text(t, style = peyda(15f, 22f, 800), color = Aso.c.ink, modifier = Modifier.padding(top = 6.dp))

@Composable
private fun Chip(label: String, icon: String, on: Boolean, onClick: () -> Unit) {
    val c = Aso.c
    Row(
        Modifier.defaultMinSize(minHeight = 40.dp).clip(CircleShape).background(if (on) c.acc else c.surfaceSunk).press(onClick = onClick).padding(horizontal = 12.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        Ic(icon, size = 18.dp, tint = if (on) c.accInk else c.inkMuted)
        Text(label, style = peyda(14f, 20f, 800), color = if (on) c.accInk else c.ink)
    }
}

@Composable
private fun LevelCard(vm: AppViewModel, gameId: String, title: String) {
    val c = Aso.c
    val s = vm.profile.data?.games?.firstOrNull { it.game == gameId }
    val l = level(s?.games ?: 0L, s?.wins ?: 0L)
    val shape = RoundedCornerShape(18.dp)
    Row(Modifier.fillMaxWidth().padding(top = 12.dp).clip(shape).background(c.surface).lined(shape).padding(horizontal = 12.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        Box(Modifier.size(42.dp), contentAlignment = Alignment.Center) {
            Image(rememberVectorPainter(StarVector), null, Modifier.fillMaxSize())
            Text(l.lv.fd(), style = peyda(14f, 18f, 800), color = c.goldInk, modifier = Modifier.padding(top = 2.dp))
        }
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Row {
                Text("${levelTitle(l.lv)} · سطح ${l.lv.fd()} در $title", style = peyda(13f, 18f, 800), color = c.ink, modifier = Modifier.weight(1f), maxLines = 1)
                Text(if ((s?.games ?: 0L) > 0L) "${s!!.games.fd()} بازی · ${s.wins.fd()} برد" else "اولین بازیتو شروع کن", style = peyda(11.5f, 18f), color = c.inkMuted)
            }
            Box(Modifier.fillMaxWidth().height(6.dp).clip(RoundedCornerShape(3.dp)).background(c.line)) {
                Box(Modifier.fillMaxWidth(l.frac.toFloat().coerceIn(0f, 1f)).height(6.dp).clip(RoundedCornerShape(3.dp)).background(c.acc))
            }
        }
    }
}

/** رده بندی همین بازی (leaderboard?game=...&period=...) */
@Composable
private fun Board(gameId: String) {
    val c = Aso.c
    val vm = androidx.lifecycle.viewmodel.compose.viewModel<AppViewModel>()
    var period by rememberSaveable { mutableStateOf("cup") }
    var data by remember { mutableStateOf<JSONObject?>(null) }
    LaunchedEffect(period) { data = null; data = vm.leaderboard(gameId, period) }
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            listOf("cup" to "🏆 جام", "week" to "این هفته", "month" to "این ماه", "all" to "همیشه").forEach { (v, l) ->
                val on = v == period
                Text(l, style = peyda(12.5f, 36f, 800), color = if (on) c.accInk else c.ink,
                    modifier = Modifier.clip(CircleShape).background(if (on) c.acc else c.surfaceSunk).press { period = v }.padding(horizontal = 12.dp))
            }
        }
        val d = data
        if (d == null) {
            repeat(3) { Box(Modifier.fillMaxWidth().height(56.dp).clip(RoundedCornerShape(18.dp)).background(c.surfaceSunk)) }
            return@Column
        }
        val rows = d.optJSONArray("rows")
        val medal = listOf(Color(0xFFF5C451), Color(0xFFC9D3DC), Color(0xFFD98B52))
        if (rows == null || rows.length() == 0) {
            Empty("trophy", if (period == "cup") "هنوز کسی جام نگرفته" else "هنوز کسی تو این بازه نبرده", "اولین برنده تو باش داش")
        } else {
            for (i in 0 until rows.length()) {
                val r = rows.getJSONObject(i)
                val me = r.optBoolean("me")
                val shape = RoundedCornerShape(18.dp)
                Row(Modifier.fillMaxWidth().clip(shape).background(if (me) c.accTint else c.surfaceSunk).padding(horizontal = 12.dp, vertical = 8.dp),
                    verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    Text((i + 1).fd(), style = peyda(15f, 22f, 800), color = medal.getOrElse(i) { c.inkMuted }, modifier = Modifier.width(24.dp), textAlign = TextAlign.Center)
                    Face(r.optString("name"), r.optLong("av", 1), r.optString("pic").takeIf { it.isNotEmpty() }?.let { vm.absolute(it) }, size = 40.dp)
                    Text(r.optString("name"), style = peyda(14.5f, 22f, 800), color = c.ink, modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Text(if (period == "cup") "${r.optLong("cups").fd()} جام" else "${r.optLong("wins").fd()} برد", style = peyda(13f, 20f, 800), color = c.inkMuted)
                }
            }
        }
    }
}

// ---------- برگه های انتظار و شمارش معکوس ----------
@Composable
fun WaitingHost(vm: AppViewModel) {
    val w = vm.play.waiting
    val n = vm.play.countdown
    if (n != null) {
        Dialog(onDismissRequest = {}, properties = DialogProperties(dismissOnBackPress = false, dismissOnClickOutside = false)) {
            Column(Modifier.clip(RoundedCornerShape(28.dp)).background(Aso.c.surface).padding(horizontal = 40.dp, vertical = 24.dp),
                horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("میز حاضره!", style = rokh(22f, 30f), color = Aso.c.ink)
                Text(n.toLong().fd(), style = rokh(64f, 72f), color = Aso.c.acc)
                Text("الان بازی شروع می‌شه…", style = peyda(12f, 18f), color = Aso.c.inkMuted)
            }
        }
        return
    }
    if (w == null) return
    Dialog(onDismissRequest = {}, properties = DialogProperties(dismissOnBackPress = false, dismissOnClickOutside = false, usePlatformDefaultWidth = false)) {
        Column(Modifier.padding(16.dp).fillMaxWidth().clip(RoundedCornerShape(28.dp)).background(Aso.c.surface).padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp)) {
            when (w) {
                is Waiting.Queue -> QueueWait(vm, w)
                is Waiting.Table -> TableWait(vm, w)
            }
        }
    }
}

private val COLORS = mapOf("blue" to Color(0xFF4C8DFF), "red" to Color(0xFFFF5A6A), "green" to Color(0xFF2FC584), "yellow" to Color(0xFFFFC531))

@Composable
private fun Seats(list: List<Triple<String, Long, String>?>) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceEvenly) {
        list.forEach { s ->
            Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(4.dp)) {
                if (s == null) {
                    Box(Modifier.size(52.dp).clip(CircleShape).background(Aso.c.surfaceSunk), contentAlignment = Alignment.Center) { Text("؟", style = rokh(20f, 26f), color = Aso.c.inkMuted) }
                    Text("…", style = peyda(12f, 18f), color = Aso.c.inkMuted)
                } else {
                    Face(s.first, s.second, null, size = 52.dp, ring = COLORS[s.third] ?: Aso.c.sky)
                    Text(s.first, style = peyda(12f, 18f, 700), color = Aso.c.ink, maxLines = 1)
                }
            }
        }
    }
}

@Composable
private fun WaitLine(text: String) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp, Alignment.CenterHorizontally), verticalAlignment = Alignment.CenterVertically) {
        CircularProgressIndicator(Modifier.size(18.dp), color = Aso.c.acc, strokeWidth = 2.5.dp)
        Text(text, style = peyda(13.5f, 20f, 700), color = Aso.c.ink)
    }
}

@Composable
private fun QueueWait(vm: AppViewModel, w: Waiting.Queue) {
    val q = w.q
    Text("پیدا کردن حریف", style = rokh(22f, 30f), color = Aso.c.ink)
    val colors = listOf("red", "blue", "green")
    Seats(listOf<Triple<String, Long, String>?>(Triple("خودت", 7L, "yellow")) + (1 until q.need.toInt()).map { i ->
        if (i < q.found) Triple("بازیکن", 3L + i, colors[(i - 1) % 3]) else null
    })
    WaitLine("${q.found.fd()} از ${q.need.fd()} نفر · ${q.waited.fd()} ثانیه")
    val bots = q.botsIn
    Text(
        when {
            q.mode != "free" -> "رتبه‌ای 🏆 · فقط با بازیکن واقعی · برد یعنی جام و سکه · ناشناس می‌مونی"
            bots != null && bots > 0 -> "اگه تا ${bots.fd()} ثانیهٔ دیگه کسی نیاد ربات جای خالیو پر می‌کنه · ناشناس می‌مونی"
            else -> "میز که پر شه بازی شروع می‌شه · ناشناس می‌مونی"
        },
        style = peyda(12f, 18f), color = Aso.c.inkMuted, textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth(),
    )
    if (q.canBots) Btn("منتظر نمی‌مونم بذار ربات جای خالیو پر کنه", vm.play::fillWithBots, Modifier.fillMaxWidth())
    Btn("بی‌خیال", vm.play::cancelWaiting, Modifier.fillMaxWidth(), kind = BtnKind.Light)
}

@Composable
private fun TableWait(vm: AppViewModel, w: Waiting.Table) {
    val ctx = LocalContext.current
    val l = w.lobby
    Text(if (l.host) "دعوت رفیقت" else "سر میز رفیقت", style = rokh(22f, 30f), color = Aso.c.ink)
    if (l.host) {
        Text("این لینکو واسه رفیقت بفرست تا با باز کردنش مستقیم بشینه کنارت · یا کد میزو بهش بگو", style = peyda(13.5f, 22f), color = Aso.c.inkMuted)
        Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(Aso.c.surfaceSunk).padding(start = 12.dp, end = 6.dp, top = 6.dp, bottom = 6.dp),
            verticalAlignment = Alignment.CenterVertically) {
            Text(l.link.ifEmpty { "کد میز: ${l.code}" }, style = peyda(12.5f, 18f, 700), color = Aso.c.ink, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
            Btn("کپی", {
                (ctx.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager).setPrimaryClip(ClipData.newPlainText("AsoTas", l.link.ifEmpty { l.code }))
            }, small = true, icon = "copy")
        }
        if (l.link.isNotEmpty()) {
            Btn("بفرست تو تلگرام", {
                val url = "https://t.me/share/url?url=" + Uri.encode(l.link) + "&text=" + Uri.encode("بیا یه دست ${game(w.game)?.title.orEmpty()} بزنیم!")
                runCatching { ctx.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url))) }
            }, Modifier.fillMaxWidth(), icon = "send")
        }
    } else {
        Text("منتظر بقیه‌ایم تا سازندهٔ میز بازیو شروع کنه…", style = peyda(13.5f, 22f), color = Aso.c.inkMuted)
    }
    val seats: List<Triple<String, Long, String>?> = l.seats.map { Triple(if (it.me) "خودت" else it.name, it.av, it.color) } +
        List((w.need - l.seats.size).coerceAtLeast(0)) { null }
    Seats(seats)
    WaitLine("${l.seats.size.fd()} از ${w.need.fd()} نفر نشستن")
    if (l.host && w.mode == "free" && l.seats.size < w.need) Btn("ربات جای خالیو پر کنه و شروع کن", vm.play::fillWithBots, Modifier.fillMaxWidth(), kind = BtnKind.Light)
    Btn(if (l.host) "بستن میز" else "بلند شدن از میز", vm.play::cancelWaiting, Modifier.fillMaxWidth(), kind = BtnKind.Light)
}
