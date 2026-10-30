package dezhcode.asotas.ui

import androidx.activity.compose.BackHandler
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
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
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
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
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.draw.scale
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.rotate
import androidx.compose.ui.graphics.drawscope.translate
import androidx.compose.ui.graphics.vector.PathParser
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import dezhcode.asotas.AppViewModel
import dezhcode.asotas.TableModel
import dezhcode.asotas.core.LudoGame
import dezhcode.asotas.fa
import dezhcode.asotas.fd
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlin.math.cos
import kotlin.math.sin

// ---------- هندسهٔ منچ (gc.js: LUDO) ----------
private val TRACK = listOf(1 to 6, 2 to 6, 3 to 6, 4 to 6, 5 to 6, 6 to 5, 6 to 4, 6 to 3, 6 to 2, 6 to 1, 6 to 0, 7 to 0, 8 to 0, 8 to 1, 8 to 2,
    8 to 3, 8 to 4, 8 to 5, 9 to 6, 10 to 6, 11 to 6, 12 to 6, 13 to 6, 14 to 6, 14 to 7, 14 to 8, 13 to 8, 12 to 8, 11 to 8, 10 to 8, 9 to 8,
    8 to 9, 8 to 10, 8 to 11, 8 to 12, 8 to 13, 8 to 14, 7 to 14, 6 to 14, 6 to 13, 6 to 12, 6 to 11, 6 to 10, 6 to 9, 5 to 8, 4 to 8, 3 to 8,
    2 to 8, 1 to 8, 0 to 8, 0 to 7, 0 to 6)

private class SeatGeo(val start: Int, val lane: List<Pair<Int, Int>>, val yard: Pair<Int, Int>, val fin: Pair<Float, Float>, val arrow: Float)

private val SEAT = mapOf(
    "blue" to SeatGeo(0, listOf(1 to 7, 2 to 7, 3 to 7, 4 to 7, 5 to 7), 0 to 0, 6.75f to 7.5f, 0f),
    "red" to SeatGeo(13, listOf(7 to 1, 7 to 2, 7 to 3, 7 to 4, 7 to 5), 9 to 0, 7.5f to 6.75f, 90f),
    "green" to SeatGeo(26, listOf(13 to 7, 12 to 7, 11 to 7, 10 to 7, 9 to 7), 9 to 9, 8.25f to 7.5f, 180f),
    "yellow" to SeatGeo(39, listOf(7 to 13, 7 to 12, 7 to 11, 7 to 10, 7 to 9), 0 to 9, 7.5f to 8.25f, 270f),
)
private val ORDER = listOf("blue", "red", "green", "yellow")
private val SAFE = setOf(0, 8, 13, 21, 26, 34, 39, 47)
private val SOCKETS = listOf(2.1f to 2.1f, 3.9f to 2.1f, 2.1f to 3.9f, 3.9f to 3.9f)
private val ROT = mapOf("yellow" to 0f, "green" to 90f, "red" to 180f, "blue" to 270f)
private val BASE = mapOf("blue" to 0, "red" to 1, "green" to 2, "yellow" to 3)

/** رنگ هر بازیکن (gc.js: COL) */
private val HEX = mapOf("blue" to Color(0xFF4C8DFF), "red" to Color(0xFFFF5A6A), "green" to Color(0xFF2FC584), "yellow" to Color(0xFFFFC531))
private val DEEP = mapOf("blue" to Color(0xFF2B62D6), "red" to Color(0xFFC93447), "green" to Color(0xFF1E8A5E), "yellow" to Color(0xFFC98A00))
private val FA = mapOf("blue" to "آبی", "red" to "قرمز", "green" to "سبز", "yellow" to "زرد")

/** جای مهره به واحد خانه (۰ تا ۱۵) */
private fun posOf(c: String, p: Long, k: Int): Pair<Float, Float> {
    val s = SEAT.getValue(c)
    return when {
        p < 0 -> (s.yard.first + SOCKETS[k % 4].first) to (s.yard.second + SOCKETS[k % 4].second)
        p <= 50 -> TRACK[((s.start + p) % 52).toInt()].let { (x, y) -> x + .5f to y + .5f }
        p <= 55 -> s.lane[(p - 51).toInt()].let { (x, y) -> x + .5f to y + .5f }
        else -> s.fin
    }
}

/** چرخش نقطه دور مرکز صفحه به اندازهٔ چرخش صفحه (ساعتگرد) */
private fun turn(p: Pair<Float, Float>, deg: Float): Pair<Float, Float> {
    val r = Math.toRadians(deg.toDouble())
    val dx = p.first - 7.5f
    val dy = p.second - 7.5f
    return (7.5f + dx * cos(r).toFloat() - dy * sin(r).toFloat()) to (7.5f + dx * sin(r).toFloat() + dy * cos(r).toFloat())
}

/** رنگ های «سالن شب» صفحهٔ بازی (gc.css: body.game) */
internal fun gameColors(base: AsoColors) = base.copy(
    dark = true, ground = Color(0xFF0C1915), groundDeep = Color(0xFF08120F), surface = Color(0xFF17302A), surfaceSunk = Color(0xFF11251F),
    line = Color(0x1AFFFFFF), ink = Color(0xFFF3F1E8), inkMuted = Color(0xFF9DB0A8), night = Color(0xFF07110E),
    acc = Color(0xFFF5C451), accDeep = Color(0xFFF7CF6A), accInk = Color(0xFF3A2A00), accTint = Color(0x26F5C451),
    coinTint = Color(0x24FFC93C), coinText = Color(0xFFFFD25E), success = Color(0xFF3DD68C), danger = Color(0xFFFF6B7A),
)

private val STAR_PATH = PathParser().parsePathString("M12 2.5l2.9 6 6.6.9-4.8 4.6 1.2 6.5L12 17.4l-5.9 3.1 1.2-6.5L2.5 9.4l6.6-.9z").toPath()
private val PAWN_STAR = PathParser().parsePathString("M20 30.2l2 4.1 4.5.6-3.3 3.1.8 4.5-4-2.2-4 2.2.8-4.5-3.3-3.1 4.5-.6z").toPath()

/** صفحهٔ بازی منچ (ludo.html و ludo.js) */
@Composable
fun LudoScreen(vm: AppViewModel, matchId: String) {
    val model = remember(matchId) { vm.table("ludo", matchId) }
    val scope = rememberCoroutineScope()
    var leaving by remember { mutableStateOf(false) }
    BackHandler { leaving = true }
    LaunchedEffect(model) {
        while (true) {
            model.poll()
            val v = model.view
            if (model.failed != null || v?.status == "over" || v?.status == "cancelled") break
            delay(900)
        }
    }
    CompositionLocalProvider(LocalAso provides gameColors(Aso.c)) {
        val c = Aso.c
        Box(Modifier.fillMaxSize().background(Brush.verticalGradient(listOf(Color(0xFF0F201B), Color(0xFF0B1714), Color(0xFF09130F))))) {
            val v = model.view
            val g = v?.ludo
            when {
                model.failed != null -> Column(Modifier.align(Alignment.Center).padding(24.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                    Text(model.failed.orEmpty(), style = peyda(15f, 24f, 700), color = c.ink, textAlign = TextAlign.Center)
                    Spacer(Modifier.height(12.dp))
                    Btn("برگشت", vm.play::closeGame)
                }
                g == null -> CircularProgressIndicator(Modifier.align(Alignment.Center), color = c.acc)
                else -> Table(vm, model, g, v!!.me ?: "yellow", onLeave = { leaving = true })
            }
            val r = v?.result
            if (v != null && g != null && (v.status == "over" || g.over)) {
                ResultDialog(g, v.me ?: "yellow", r?.won ?: (g.winner == v.me), r?.coins ?: 0, r?.cups ?: 0,
                    again = { vm.play.closeGame(); vm.play.openLobby("ludo") }, home = vm.play::closeGame)
            }
        }
        if (leaving) {
            Dialog(onDismissRequest = { leaving = false }) {
                Column(Modifier.clip(RoundedCornerShape(28.dp)).background(c.surface).padding(20.dp),
                    horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Box(Modifier.size(64.dp).clip(CircleShape).background(c.danger.copy(alpha = .16f)), contentAlignment = Alignment.Center) { Ic("exit", size = 30.dp, tint = c.danger) }
                    Text("از بازی بری بیرون؟", style = rokh(21f, 30f), color = c.ink)
                    Text("اگه بری ربات جات بازی می‌کنه و این دست باخت حساب می‌شه", style = peyda(14f, 24f), color = c.inkMuted, textAlign = TextAlign.Center)
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

@Composable
private fun Table(vm: AppViewModel, model: TableModel, g: LudoGame, me: String, onLeave: () -> Unit) {
    val c = Aso.c
    val scope = rememberCoroutineScope()
    val rot = ROT[me] ?: 0f
    val cur = g.turn
    val mine = cur == me
    val canRoll = mine && g.phase == "roll" && !model.acting
    val canMove = mine && g.phase == "move" && !model.acting
    // زمان باقی مانده از نوبت: از لحظهٔ گرفتن میز شمرده می شود
    var got by remember { mutableLongStateOf(System.currentTimeMillis()) }
    var now by remember { mutableLongStateOf(System.currentTimeMillis()) }
    LaunchedEffect(g.seq, g.deadlineMs) { got = System.currentTimeMillis() }
    LaunchedEffect(Unit) { while (true) { now = System.currentTimeMillis(); delay(200) } }
    val left = (g.deadlineMs - (now - got)).coerceAtLeast(0)
    val frac = if (g.turnMs > 0 && g.deadlineMs > 0) left.toFloat() / g.turnMs else 0f

    Column(Modifier.fillMaxSize().statusBarsPadding().navigationBarsPadding()) {
        // ---------- سربرگ: برگشت، نوبت و زمان، صدا، راهنما ----------
        Row(Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 8.dp), verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            GameIcon("back", onLeave)
            Row(Modifier.weight(1f).height(44.dp).clip(CircleShape).background(c.surface).padding(horizontal = 12.dp),
                verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Box(Modifier.size(24.dp).clip(CircleShape).background(HEX[cur] ?: c.inkMuted))
                Text(if (cur == null) "بازی تموم شد" else if (mine) "نوبت توئه" else "نوبت ${nameOf(g, cur)}",
                    style = peyda(14f, 20f, 800), color = c.ink, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
                if (g.deadlineMs > 0) {
                    Box(Modifier.width(48.dp).height(6.dp).clip(CircleShape).background(c.line)) {
                        Box(Modifier.fillMaxWidth(frac.coerceIn(0f, 1f)).height(6.dp).clip(CircleShape).background(if (frac < .25f) c.danger else c.acc))
                    }
                }
            }
            GameIcon(if (vm.me?.sound != false) "soundOn" else "soundOff") { vm.toggleSound() }
            GameIcon("help") { vm.openHelp("hLudo") }
        }
        // ---------- صندلی های بالا، صفحه، صندلی های پایین ----------
        val corner = { col: String -> ((BASE[col] ?: 0) + (rot / 90).toInt()) % 4 }
        SeatRow(g, me, cur, frac, g.order.filter { corner(it) <= 1 }, top = true, corner)
        BoxWithConstraints(Modifier.fillMaxWidth().padding(horizontal = 6.dp).aspectRatio(1f), contentAlignment = AbsoluteAlignment.TopLeft) {
            val side = maxWidth
            val u = side / 15.8f
            Canvas(Modifier.fillMaxSize().clip(RoundedCornerShape(22.dp))) { drawBoard(rot) }
            // مهره ها بیرون از صفحهٔ چرخیده تا سرپا بمانند
            val groups = mutableMapOf<String, MutableList<Triple<String, Int, Pair<Float, Float>>>>()
            for (col in g.order) {
                g.pawns[col].orEmpty().forEachIndexed { k, p ->
                    val pos = turn(posOf(col, p, k), rot)
                    groups.getOrPut("%.2f,%.2f".format(pos.first, pos.second)) { mutableListOf() }.add(Triple(col, k, pos))
                }
            }
            groups.values.forEach { list ->
                list.forEachIndexed { i, (col, k, pos) ->
                    val n = list.size
                    val off = if (n > 1) (i - (n - 1) / 2f) * .36f else 0f
                    val movable = canMove && col == me && k.toLong() in g.movable
                    key(col, k) {
                        Pawn(col, pos.first + off, pos.second + (if (n > 1) .12f else 0f), u, if (n > 1) .8f else 1f, movable) {
                            scope.launch { model.act("move", k.toLong()) }
                        }
                    }
                }
            }
        }
        SeatRow(g, me, cur, frac, g.order.filter { corner(it) >= 2 }, top = false, corner)
        Spacer(Modifier.weight(1f))
        // ---------- داک: چت، وضعیت، تاس ----------
        val shape = RoundedCornerShape(24.dp)
        Row(Modifier.fillMaxWidth().padding(12.dp).clip(shape).background(c.surface).padding(12.dp),
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Box(Modifier.size(56.dp).clip(CircleShape).background(c.acc).press { vm.soon("چت سر میز") }, contentAlignment = Alignment.Center) {
                Ic("chat", size = 24.dp, tint = c.accInk)
            }
            Column(Modifier.weight(1f)) {
                val (t, s) = when {
                    cur == null -> "بازی تموم شد" to ""
                    canRoll -> "نوبت توئه" to "بزن رو تاس تا بریزه"
                    mine && g.phase == "move" -> "یه مهره رو انتخاب کن" to "مهره‌هایی که می‌تونن برن می‌درخشن"
                    mine -> "نوبت توئه" to "یه لحظه…"
                    else -> "نوبت ${nameOf(g, cur)}" to "صبر کن تا تاسشو بریزه"
                }
                Text(t, style = rokh(17f, 24f), color = c.ink)
                if (s.isNotEmpty()) Text(s, style = peyda(12.5f, 18f), color = c.inkMuted)
            }
            val face = g.dice ?: cur?.let { g.last[it] }
            Die(face?.toInt() ?: 0, HEX[cur ?: me] ?: c.acc, DEEP[cur ?: me] ?: c.accDeep, rolling = model.acting && g.phase == "roll", enabled = canRoll) {
                scope.launch { model.act("roll") }
            }
        }
    }
}

private fun nameOf(g: LudoGame, col: String): String = g.players[col]?.let { if (it.me) "تو" else it.name } ?: FA[col].orEmpty()

@Composable
internal fun GameIcon(icon: String, onClick: () -> Unit) {
    Box(Modifier.size(44.dp).clip(CircleShape).background(Aso.c.surface).press(.94f, onClick = onClick), contentAlignment = Alignment.Center) {
        Ic(icon, size = 22.dp, tint = Aso.c.ink)
    }
}

/** صندلی های یک ردیف (بالا یا پایین صفحه)؛ چپ و راست بر اساس گوشهٔ لانهٔ همان رنگ */
@Composable
private fun SeatRow(g: LudoGame, me: String, cur: String?, frac: Float, cols: List<String>, top: Boolean, corner: (String) -> Int) {
    Box(Modifier.fillMaxWidth().height(68.dp).padding(horizontal = 6.dp, vertical = 6.dp)) {
        cols.forEach { col ->
            val left = if (top) corner(col) == 0 else corner(col) == 3
            Box(Modifier.align(if (left) AbsoluteAlignment.CenterLeft else AbsoluteAlignment.CenterRight)) { SeatChip(g, col, col == cur, frac) }
        }
    }
}

@Composable
private fun SeatChip(g: LudoGame, col: String, active: Boolean, frac: Float) {
    val c = Aso.c
    val p = g.players[col] ?: return
    val hex = HEX.getValue(col)
    val n = g.pawns[col].orEmpty().size
    val done = (g.done[col] ?: 0L).toInt()
    val shape = CircleShape
    Row(
        Modifier.clip(shape).background(if (active) hex.copy(alpha = .18f) else c.surface).border(2.dp, if (active) hex else Color.Transparent, shape)
            .padding(start = 4.dp, end = 12.dp, top = 4.dp, bottom = 4.dp).then(if (p.out) Modifier.scale(.96f) else Modifier),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Box(contentAlignment = Alignment.Center) {
            if (active && frac > 0f) {
                Canvas(Modifier.size(48.dp)) { drawArc(hex, -90f, 360f * frac.coerceIn(0f, 1f), useCenter = false, style = Stroke(3.dp.toPx())) }
            }
            Face(if (p.me) "تو" else p.name, p.av, if (p.bot) null else p.pic, size = 42.dp, ring = hex)
        }
        Column {
            Text(if (p.me) "خودت" else p.name, style = peyda(13f, 18f, 800), color = if (p.out) c.inkMuted else c.ink, maxLines = 1,
                overflow = TextOverflow.Ellipsis, modifier = Modifier.width(84.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(3.dp), verticalAlignment = Alignment.CenterVertically) {
                repeat(n) { i -> Box(Modifier.size(7.dp).clip(CircleShape).background(if (i < done) hex else c.line)) }
            }
        }
        val last = g.last[col]
        Box(Modifier.size(30.dp).clip(RoundedCornerShape(9.dp)).background(if (last != null) hex else c.surfaceSunk), contentAlignment = Alignment.Center) {
            if (last != null) Pips(last.toInt(), 30.dp, Color.White)
        }
    }
}

/** مهرهٔ منچ (gc.js: pawn): دیسک سه بعدی با لبهٔ سفید و ستاره؛ نقطهٔ نشستن ۷۴٪ ارتفاع */
@Composable
private fun Pawn(col: String, x: Float, y: Float, u: Dp, scale: Float, movable: Boolean, onClick: () -> Unit) {
    val ax by animateFloatAsState(x, tween(380), label = "px")
    val ay by animateFloatAsState(y, tween(380), label = "py")
    val w = u * .92f * scale
    val h = w * 1.25f
    val pulse = rememberInfiniteTransition(label = "can")
    val hop by pulse.animateFloat(0f, if (movable) 1f else 0f, infiniteRepeatable(tween(520), RepeatMode.Reverse), label = "hop")
    val hex = HEX.getValue(col)
    val deep = DEEP.getValue(col)
    Box(
        Modifier.absoluteOffset(u * (ax + .4f) - w / 2, u * (ay + .4f) - h * .74f - u * .18f * hop)
            .size(w, h)
            .then(if (movable) Modifier.press(.9f, onClick = onClick) else Modifier),
    ) {
        Canvas(Modifier.fillMaxSize()) {
            val k = size.width / 40f
            if (movable) drawCircle(Color.White.copy(alpha = .55f + .3f * hop), radius = 16.5f * k, center = Offset(20f * k, 37f * k), style = Stroke(2.5f * k))
            drawOval(Color.Black.copy(alpha = .35f), Offset(7f * k, 44.9f * k), Size(26f * k, 5.2f * k))
            drawCircle(deep, 14f * k, Offset(20f * k, 40f * k))
            drawCircle(Color.White, 14f * k, Offset(20f * k, 37f * k))
            drawCircle(hex, 11f * k, Offset(20f * k, 37f * k))
            scaleTo(k) { drawPath(PAWN_STAR, Color.White.copy(alpha = .92f)) }
        }
    }
}

private inline fun DrawScope.scaleTo(k: Float, block: DrawScope.() -> Unit) {
    drawContext.transform.scale(k, k, Offset.Zero)
    block()
    drawContext.transform.scale(1 / k, 1 / k, Offset.Zero)
}

/** صفحهٔ ۱۵×۱۵ (boardArt و buildBoard در gc.js و ludo.js) با چرخش رنگ من به پایین چپ */
private fun DrawScope.drawBoard(rot: Float) {
    val u = size.width / 15.8f
    drawRect(Color(0xFF0A1914))
    rotate(rot) {
        translate(.4f * u, .4f * u) {
            fun cell(x: Float, y: Float, color: Color, inset: Float = .07f) =
                drawRoundRect(color, Offset((x + inset) * u, (y + inset) * u), Size((1 - 2 * inset) * u, (1 - 2 * inset) * u), CornerRadius(.2f * u))
            // لانه ها
            for (col in ORDER) {
                val (x, y) = SEAT.getValue(col).yard
                drawRoundRect(HEX.getValue(col), Offset((x + .25f) * u, (y + .25f) * u), Size(5.5f * u, 5.5f * u), CornerRadius(1.1f * u))
                drawRoundRect(Color.Black.copy(alpha = .14f), Offset((x + .25f) * u, (y + 5.25f) * u), Size(5.5f * u, .5f * u), CornerRadius(.3f * u))
                SOCKETS.forEach { (sx, sy) -> drawCircle(Color.Black.copy(alpha = .2f), .72f * u, Offset((x + sx) * u, (y + sy) * u)) }
            }
            // مسیر، شروع هر رنگ با فلش، خانه های امن با ستاره
            val startOf = ORDER.associateBy { SEAT.getValue(it).start }
            TRACK.forEachIndexed { i, (x, y) ->
                val col = startOf[i]
                cell(x.toFloat(), y.toFloat(), if (col != null) HEX.getValue(col) else Color(0xFFF4F2FA))
                if (col != null) {
                    rotate(SEAT.getValue(col).arrow, Offset((x + .5f) * u, (y + .5f) * u)) {
                        val p = Path().apply {
                            moveTo((x + .36f) * u, (y + .28f) * u); lineTo((x + .74f) * u, (y + .5f) * u); lineTo((x + .36f) * u, (y + .72f) * u); close()
                        }
                        drawPath(p, Color.White)
                    }
                } else if (i in SAFE) {
                    translate((x + .2f) * u, (y + .2f) * u) { scaleTo(.6f * u / 24f) { drawPath(STAR_PATH, Color(0xFFB9B4CC)) } }
                }
            }
            // راهروی هر رنگ
            for (col in ORDER) SEAT.getValue(col).lane.forEach { (x, y) -> cell(x.toFloat(), y.toFloat(), HEX.getValue(col)) }
            // خانهٔ وسط: چهار مثلث رنگی و جام
            fun tri(a: Offset, b: Offset, col: String) = drawPath(Path().apply {
                moveTo(a.x * u, a.y * u); lineTo(b.x * u, b.y * u); lineTo(7.5f * u, 7.5f * u); close()
            }, HEX.getValue(col))
            tri(Offset(6f, 6f), Offset(6f, 9f), "blue")
            tri(Offset(6f, 6f), Offset(9f, 6f), "red")
            tri(Offset(9f, 6f), Offset(9f, 9f), "green")
            tri(Offset(6f, 9f), Offset(9f, 9f), "yellow")
            drawCircle(Color(0xFF0A1914), .55f * u, Offset(7.5f * u, 7.5f * u))
            drawCircle(Color(0xFFF5C451), .32f * u, Offset(7.5f * u, 7.5f * u))
        }
    }
}

/** خال های تاس */
@Composable
private fun Pips(n: Int, size: Dp, color: Color) {
    val on = when (n) {
        1 -> setOf(4); 2 -> setOf(0, 8); 3 -> setOf(0, 4, 8); 4 -> setOf(0, 2, 6, 8); 5 -> setOf(0, 2, 4, 6, 8); 6 -> setOf(0, 2, 3, 5, 6, 8)
        else -> emptySet()
    }
    Canvas(Modifier.size(size).padding(size * .2f)) {
        val step = this.size.width / 3f
        for (i in on) drawCircle(color, step * .32f, Offset(step * (i % 3 + .5f), step * (i / 3 + .5f)))
    }
}

/** تاس بزرگ داک: رنگ بازیکن نوبت؛ لمس = ریختن */
@Composable
private fun Die(n: Int, color: Color, deep: Color, rolling: Boolean, enabled: Boolean, onClick: () -> Unit) {
    val spin = rememberInfiniteTransition(label = "die")
    val a by spin.animateFloat(0f, 360f, infiniteRepeatable(tween(420)), label = "spin")
    val pulse by spin.animateFloat(1f, if (enabled) 1.07f else 1f, infiniteRepeatable(tween(600), RepeatMode.Reverse), label = "pulse")
    var shown by remember { mutableStateOf(n) }
    LaunchedEffect(rolling) { while (rolling) { shown = (1..6).random(); delay(90) } }
    LaunchedEffect(n, rolling) { if (!rolling) shown = n }
    val shape = RoundedCornerShape(16.dp)
    Box(
        Modifier.size(64.dp).scale(pulse).rotate(if (rolling) a else -6f).shadow(8.dp, shape).clip(shape).background(deep)
            .padding(bottom = 5.dp).clip(shape).background(color).then(if (enabled) Modifier.press(.92f, onClick = onClick) else Modifier),
        contentAlignment = Alignment.Center,
    ) {
        if (shown > 0) Pips(shown, 56.dp, Color.White) else Ic("dice", size = 30.dp, tint = Color.White)
    }
}

@Composable
private fun ResultDialog(g: LudoGame, me: String, won: Boolean, coins: Long, cups: Long, again: () -> Unit, home: () -> Unit) {
    val c = Aso.c
    Dialog(onDismissRequest = home) {
        Column(Modifier.clip(RoundedCornerShape(28.dp)).background(c.surface).padding(22.dp),
            horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text(if (won) "🏆" else "🎲", style = peyda(52f, 60f))
            Text(if (won) "بردی! ایول 🎉" else "این دست مال ${g.winner?.let { nameOf(g, it) } ?: "حریف"} شد", style = rokh(22f, 30f), color = c.ink, textAlign = TextAlign.Center)
            Text(if (won) "همهٔ مهره‌هاتو زودتر از بقیه رسوندی خونه" else "فدای سرت دست بعد جبران کن", style = peyda(14f, 22f), color = c.inkMuted, textAlign = TextAlign.Center)
            if (cups != 0L || coins > 0) {
                Row(horizontalArrangement = Arrangement.spacedBy(14.dp), verticalAlignment = Alignment.CenterVertically) {
                    if (cups != 0L) Text("${if (cups > 0) "+" else "−"}${kotlin.math.abs(cups).fa()} جام", style = peyda(18f, 26f, 800), color = if (cups > 0) c.coinText else c.inkMuted)
                    if (coins > 0) Amount(coins, size = 18f)
                }
            }
            Btn("یه دست دیگه", again, Modifier.fillMaxWidth(), kind = BtnKind.Gold)
            Btn("برگشت به خانه", home, Modifier.fillMaxWidth(), kind = BtnKind.Light)
        }
    }
}
