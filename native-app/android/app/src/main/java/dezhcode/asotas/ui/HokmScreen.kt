package dezhcode.asotas.ui

import android.content.Context
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import androidx.activity.compose.BackHandler
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.LinearEasing
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
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.Stable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.runtime.snapshotFlow
import androidx.compose.runtime.withFrameNanos
import androidx.compose.ui.AbsoluteAlignment
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.draw.drawWithContent
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Rect
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ColorFilter
import androidx.compose.ui.graphics.ColorMatrix
import androidx.compose.ui.graphics.TransformOrigin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.boundsInRoot
import androidx.compose.ui.layout.onGloballyPositioned
import androidx.compose.ui.layout.positionInRoot
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.zIndex
import androidx.lifecycle.repeatOnLifecycle
import dezhcode.asotas.AppViewModel
import dezhcode.asotas.TableModel
import dezhcode.asotas.core.HokmEvent
import dezhcode.asotas.core.HokmGame
import dezhcode.asotas.core.HokmPlayer
import dezhcode.asotas.core.MatchView
import dezhcode.asotas.fd
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.filterNotNull
import kotlinx.coroutines.launch
import kotlin.math.abs
import kotlin.math.cos
import kotlin.math.exp
import kotlin.math.hypot
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sin
import kotlin.random.Random

// ---------- حکم (hokm.html، hokm.css، hokm.js): میز سبز، ورق واقعی، دست بادبزنی و میز زنده ----------

/** پیام های سریع گفتگوی میز حکم (hokm.js: QUICK) */
private val HOKM_QUICK = listOf("سلام!", "خوش‌بازی!", "آفرین یار", "حکم خوبی بود", "زود باش", "یه دست دیگه؟")
val SUIT_FA = listOf("پیک", "دل", "خشت", "گشنیز")
private val GOLD = Color(0xFFF5C451)
private val GOLD_INK = Color(0xFF3A2A00)
private val SUIT_RED = Color(0xFFD62839)
private val SUIT_BLACK = Color(0xFF1C2230)
private const val R2D = (180 / Math.PI).toFloat()

/** خال ها برای نشان حکم (hokm.js: SP) */
private val HSP = listOf(
    "M12 2.4c-2.6 3.3-8.6 7-8.6 11.3 0 2.6 2 4.5 4.4 4.5 1.4 0 2.6-.6 3.4-1.6-.3 2-1 3.5-2.2 4.9h6c-1.2-1.4-1.9-2.9-2.2-4.9.8 1 2 1.6 3.4 1.6 2.4 0 4.4-1.9 4.4-4.5 0-4.3-6-8-8.6-11.3z",
    "M12 21.2C9.1 18.9 2.5 14.1 2.5 8.9 2.5 6 4.7 3.8 7.4 3.8c1.9 0 3.6 1 4.6 2.6 1-1.6 2.7-2.6 4.6-2.6 2.7 0 4.9 2.2 4.9 5.1 0 5.2-6.6 10-9.5 12.3z",
    "M12 2.2l7.6 9.8L12 21.8 4.4 12z",
    "M12 2.6a4.3 4.3 0 0 0-3.6 6.6A4.3 4.3 0 1 0 10.7 17c-.3 1.6-1 2.9-2 4h6.6c-1-1.1-1.7-2.4-2-4a4.3 4.3 0 1 0 2.3-7.8A4.3 4.3 0 0 0 12 2.6z",
).map { androidx.compose.ui.graphics.vector.PathParser().parsePathString(it).toPath() }
private val CROWN = androidx.compose.ui.graphics.vector.PathParser().parsePathString("M3 7.5l4.6 4.2L12 4.5l4.4 7.2L21 7.5l-1.7 9H4.7zM4.7 18h14.6v2H4.7z").toPath()

private fun isRed(s: Int) = s == 1 || s == 2

@Composable
private fun SuitIcon(s: Int, size: Dp, color: Color = if (isRed(s)) SUIT_RED else SUIT_BLACK, modifier: Modifier = Modifier) {
    Canvas(modifier.size(size)) {
        val k = this.size.width / 24f
        drawContext.transform.scale(k, k, Offset.Zero)
        drawPath(HSP[s], color)
    }
}

@Composable
private fun CrownIcon(size: Dp, color: Color = GOLD_INK) {
    Canvas(Modifier.size(size)) {
        val k = this.size.width / 24f
        drawContext.transform.scale(k, k, Offset.Zero)
        drawPath(CROWN, color)
    }
}

// ---------- جای برگ ها روی میز ----------
/** جای هر برگ در تودهٔ وسط میز: کمی به سمت کسی که انداخته (بالا یار، راست نفر بعد، چپ نفر قبل، پایین خودم) */
private val SLOT = mapOf(2 to floatArrayOf(71f, 26f, -5f), 3 to floatArrayOf(36f, 64f, -13f), 1 to floatArrayOf(106f, 60f, 13f), 0 to floatArrayOf(72f, 104f, 4f))

/** عدد شبه تصادفی ثابت از روی برگ و بازیکن (همه همان را می بینند) */
private fun hash01(a: Int, b: Int): Float {
    var h = a * 374761393 + b * 668265263
    h = (h xor (h ushr 13)) * 1274126177
    return ((h xor (h ushr 16)).toLong() and 0xffffffffL).toFloat() / 4294967296f
}

private fun rel(seat: Int, me: Int) = (seat - me + 4) % 4

private fun slotOf(seat: Int, card: Int, me: Int): FloatArray {
    val s = SLOT.getValue(rel(seat, me))
    val k = seat * 53 + card
    return floatArrayOf(s[0] + (hash01(k, 1) * 2 - 1) * 24, s[1] + (hash01(k, 2) * 2 - 1) * 20, s[2] + (hash01(k, 3) * 2 - 1) * 24)
}

private fun winnerOf(trick: List<Pair<Int, Int>>, tr: Int): Int {
    var (bi, b) = trick[0]
    for ((i, c) in trick.drop(1)) {
        if (c / 13 == b / 13) { if (c % 13 > b % 13) { bi = i; b = c } } else if (c / 13 == tr) { bi = i; b = c }
    }
    return bi
}

/** دست: حکم اول، بعد بقیه خال ها یکی سیاه یکی قرمز؛ داخل هر خال از بزرگ به کوچک */
private fun handOrder(cards: List<Int>, tr: Int?): List<Int> {
    val base = listOf(0, 1, 3, 2)
    val seq = if (tr == null) base else listOf(tr) + base.filter { it != tr }
    return cards.sortedWith(compareBy<Int> { seq.indexOf(it / 13) }.thenByDescending { it % 13 })
}

// ---------- میز زنده: جاذبه، حسگر گوشی، انگشت (hokm.js: motion) ----------
@Stable
private class TableMotion {
    val env = CardPhysics.Env()
    val bodies = LinkedHashMap<Int, CardPhysics.Body>()
    var order: List<CardPhysics.Body> = emptyList()
    private val landed = HashMap<Int, CardPhysics.Flight>()
    /** میدان بازی در مختصات توده (بین بازیکن ها، زیر یار، بالای نوار من) */
    var box: CardPhysics.Box? = null
    var tick by mutableIntStateOf(0)
    /** برق ورق: جای نوار (sp) و پیدایی اش (so) */
    var sp by mutableFloatStateOf(0f)
    var so by mutableFloatStateOf(0f)
    private val kicks = Channel<Unit>(Channel.CONFLATED)
    private var heldC: Int? = null
    private var heldStart = Offset.Zero
    var moved = false

    fun kick() { kicks.trySend(Unit) }

    /** برگ های توده: برگ تازه با جای خودش (یا همان جا که پرتاب ایستاد) */
    fun sync(pile: List<Pair<Int, Int>>, me: Int) {
        val seen = HashSet<Int>()
        pile.forEachIndexed { i, (s, c) ->
            seen += c
            if (c !in bodies) {
                val (x, y, r) = slotOf(s, c, me).let { Triple(it[0], it[1], it[2]) }
                val b = CardPhysics.Body(c, x + 32, y + 45, r / R2D, z = (i + 1).toFloat())
                landed.remove(c)?.let { f -> b.x = f.x; b.y = f.y; b.a = f.a; b.vx = f.vx; b.vy = f.vy; b.w = f.w }
                b.box = zoneOf(b)
                bodies[c] = b
            }
        }
        bodies.keys.retainAll(seen)
        order = bodies.values.sortedBy { it.z }
        if (heldC != null && heldC !in bodies) heldC = null
        tick++
        kick()
    }

    fun land(c: Int, f: CardPhysics.Flight) { landed[c] = f }

    /** میدان هر برگ جای خود آن برگ را هم دارد (روی صفحهٔ باریک برگ سر جای خودش می ماند) */
    fun zoneOf(b: CardPhysics.Body): CardPhysics.Box? {
        val z = box ?: return null
        val c = cos(b.a)
        val s = sin(b.a)
        var l = z.l
        var r = z.r
        var t = z.t
        var bt = z.b
        for ((px, py) in listOf(-32f to -45f, 32f to -45f, 32f to 45f, -32f to 45f)) {
            val X = b.x + px * c - py * s
            val Y = b.y + px * s + py * c
            l = min(l, X - 1); r = max(r, X + 1); t = min(t, Y - 1); bt = max(bt, Y + 1)
        }
        return CardPhysics.Box(l, t, r, bt)
    }

    fun setBox(b: CardPhysics.Box) {
        box = b
        for (o in order) o.box = null
        kick()
    }

    /** حلقهٔ فیزیک: فقط وقتی چیزی تکان می خورد فریم می گیرد */
    suspend fun run() {
        while (true) {
            kicks.receive()
            var prev = 0L
            while (true) {
                val moving = withFrameNanos { t ->
                    if (order.isEmpty()) return@withFrameNanos false
                    val dt = if (prev != 0L) min(.05f, (t - prev) / 1e9f) else 1 / 60f
                    prev = t
                    for (b in order) if (b.box == null) b.box = zoneOf(b)
                    val n = max(1, kotlin.math.ceil(dt * 240).toInt())
                    val h = dt / n
                    var mv = false
                    repeat(n) { mv = CardPhysics.step(order, env, h, box, null) }
                    tick++
                    mv || heldC != null
                }
                if (!moving) break
            }
        }
    }

    // ---- انگشت: برگ را از همان نقطه که گرفته شده هل می دهد؛ رها کردن با سرعت انگشت پرتش می کند
    fun down(x: Float, y: Float): Boolean {
        val b = order.lastOrNull { CardPhysics.on(it, x, y) } ?: return false
        val c = cos(b.a)
        val s = sin(b.a)
        val dx = x - b.x
        val dy = y - b.y
        b.pin = CardPhysics.Pin(x, y, dx * c + dy * s, dy * c - dx * s)
        b.held = true; b.vx = 0f; b.vy = 0f; b.w = 0f
        heldC = b.c; heldStart = Offset(x, y); moved = false
        kick()
        return true
    }

    fun move(x: Float, y: Float) {
        val b = heldC?.let { bodies[it] } ?: return
        val bx = b.box ?: zoneOf(b) ?: return
        b.pin?.let { it.x = x.coerceIn(bx.l + 6, bx.r - 6); it.y = y.coerceIn(bx.t + 6, bx.b - 6) }
        if (!moved && hypot(x - heldStart.x, y - heldStart.y) > 6) moved = true
        kick()
    }

    fun up() {
        val b = heldC?.let { bodies[it] }
        heldC = null
        if (b != null) {
            b.held = false; b.pin = null
            val v = hypot(b.vx, b.vy)
            if (v > 2600) { b.vx *= 2600 / v; b.vy *= 2600 / v }
        }
        kick()
    }

    // ---- حسگر: بردار «پایین» در محورهای گوشی (x راست، y بالا، z بیرون صفحه)، مثل feed در hokm.js
    private var cal = ArrayList<FloatArray>()
    private var sign = 0f
    private var unit = 1f
    private var F: FloatArray? = null
    private var Gv: FloatArray? = null
    private var ref: FloatArray? = null
    private var lastT = 0L
    private val TILT = .8f
    private val SHAKE = .3f

    private fun dot(p: FloatArray, q: FloatArray) = p[0] * q[0] + p[1] * q[1] + p[2] * q[2]
    private fun unitv(v: FloatArray): FloatArray {
        val m = kotlin.math.sqrt(dot(v, v)).takeIf { it > 0f } ?: 1f
        return floatArrayOf(v[0] / m, v[1] / m, v[2] / m)
    }

    fun resetSensor() { cal = ArrayList(); sign = 0f; F = null; Gv = null; ref = null; lastT = 0L; env.ax = 0f; env.ay = 0f; env.gn = CardPhysics.G * CardPhysics.PX; so = 0f }

    /** شتاب سنج اندروید: نیروی تکیه گاه یا جاذبه؛ جهت و واحد از چند نمونهٔ اول شناخته می شود */
    fun accel(x: Float, y: Float, z: Float) {
        if (sign == 0f) {
            cal.add(floatArrayOf(x, y, z)); if (cal.size < 6) return
            val M = FloatArray(3) { i -> cal.sumOf { it[i].toDouble() }.toFloat() / cal.size }
            val m = kotlin.math.sqrt(dot(M, M))
            cal = ArrayList()
            if (m < .5f) return
            unit = if (m <= 1.6f) CardPhysics.G else 1f
            sign = if (M[1] + M[2] > 0) -1f else 1f
        }
        feed(floatArrayOf(x * sign * unit, y * sign * unit, z * sign * unit))
    }

    private fun feed(A: FloatArray) {
        val now = System.nanoTime()
        val dt = if (lastT != 0L) min(.5f, (now - lastT) / 1e9f) else 0f
        lastT = now
        fun lp(v: FloatArray?, to: FloatArray, tau: Float): FloatArray = v?.let { FloatArray(3) { i -> it[i] + (to[i] - it[i]) * (1 - exp(-dt / tau)) } } ?: to.copyOf()
        F = lp(F, A, .06f)
        Gv = lp(Gv, F!!, .15f)
        val G = Gv!!
        val m = kotlin.math.sqrt(dot(G, G))
        if (m < 2) return
        val u = floatArrayOf(G[0] / m, G[1] / m, G[2] / m)
        ref = ref?.let { r -> unitv(FloatArray(3) { i -> r[i] + (u[i] - r[i]) * (1 - exp(-dt / (if (bodies.isNotEmpty()) 6f else .5f))) }) } ?: u
        val rf = ref!!
        val X = unitv(floatArrayOf(1 - rf[0] * rf[0], -rf[0] * rf[1], -rf[0] * rf[2]))
        if (abs(rf[0]) > .95f) return
        val Y = floatArrayOf(X[1] * rf[2] - X[2] * rf[1], X[2] * rf[0] - X[0] * rf[2], X[0] * rf[1] - X[1] * rf[0])
        val f = F!!
        val L = floatArrayOf(f[0] - G[0], f[1] - G[1], f[2] - G[2])
        env.ax = (dot(G, X) * TILT + dot(L, X) * SHAKE) * CardPhysics.PX
        env.ay = -(dot(G, Y) * TILT + dot(L, Y) * SHAKE) * CardPhysics.PX
        env.gn = max(.2f * CardPhysics.G, dot(G, rf)) * CardPhysics.PX
        if (bodies.isNotEmpty() && hypot(env.ax, env.ay) > CardPhysics.CARD.s * env.gn * .9f) kick()
        sheen(dot(G, X) / m, -dot(G, Y) / m)
    }

    private var shP = 9f
    private var shAt = 0L
    /** برق ورق ها: با کج کردن گوشی نواری از نور روی برگ ها رد می شود (حداکثر ۲۰ بار در ثانیه) */
    private fun sheen(x: Float, y: Float) {
        val p = ((x * .906f + y * .423f) * 3).coerceIn(-1.2f, 1.2f)
        val now = System.nanoTime()
        if (abs(p - shP) < .03f || now - shAt < 50_000_000L) return
        shP = p; shAt = now
        sp = p; so = min(1f, abs(p) * 3)
    }
}

// ---------- پخش رویدادها (hokm.js: apply و play) ----------
private class Throwing(val c: Int, val run: CardPhysics.Flight, val tx: Float, val ty: Float, val rx0: Float, val ry0: Float,
                       val mine: Boolean, val T1: Float, val done: CompletableDeferred<Unit>) {
    var t0 = 0L
}

@Stable
private class HokmPlay {
    var me by mutableIntStateOf(0)
    var view by mutableStateOf<MatchView?>(null)
    var game by mutableStateOf<HokmGame?>(null)
    var busy by mutableStateOf(false)
    private var since = 0L
    val pile = mutableStateListOf<Pair<Int, Int>>()
    val flying = mutableStateListOf<Throwing>()
    var selfPlayed: Int? = null
    var banner by mutableStateOf<String?>(null)
    var collecting by mutableStateOf<Int?>(null)
    var deadlineAt by mutableLongStateOf(0L)
    var turnMs = 20000L
    /** جای هر چیز روی صفحه برای پرتاب و جمع کردن (مختصات ریشه) */
    val seatRect = mutableStateMapOf<Int, Rect>()
    val handRect = HashMap<Int, Rect>()
    var pileOrigin = Offset.Zero
    var pileK = 1f
    var stackUs = Offset.Zero
    var stackThem = Offset.Zero
    lateinit var motion: TableMotion
    var density = 1f

    suspend fun apply(v: MatchView) {
        val g = v.hokm ?: return
        val arrived = System.currentTimeMillis()
        busy = true
        try {
            if (game == null) {
                me = g.me?.toIntOrNull() ?: 0
                since = g.seq
            } else {
                for (e in g.events.filter { it.seq > since }.sortedBy { it.seq }) { play(e, g); since = e.seq }
            }
            since = max(since, g.seq)
            val now = if (g.phase == "collect") emptyList() else g.trick.map { (it.seat.toIntOrNull() ?: 0) to it.card.toInt() }
            if (pile.toList() != now) { pile.clear(); pile.addAll(now) }
            motion.sync(pile, me)
            turnMs = g.turnMs.takeIf { it > 0 } ?: 20000L
            val dl = if (g.deadlineMs > 0) arrived + g.deadlineMs else 0L
            if (dl == 0L) deadlineAt = 0L else if (deadlineAt == 0L || abs(dl - deadlineAt) > 700) deadlineAt = dl
            game = g
            view = v
        } finally {
            busy = false
        }
    }

    private fun name(g: HokmGame, s: String) = if (s.toIntOrNull() == me) "تو" else g.players[s]?.name ?: "بازیکن"

    private suspend fun play(e: HokmEvent, g: HokmGame) {
        val seat = e.c.toIntOrNull() ?: 0
        when (e.t) {
            "deal" -> { pile.clear(); motion.sync(pile, me); banner = "ورقا دارن پخش می‌شن…"; delay(900); banner = null }
            "trump" -> {
                val s = (e.suit ?: 0).toInt()
                banner = "حکم ${SUIT_FA.getOrElse(s) { "" }} · " + (if (seat == me) "تو حکم کردی" else "${name(g, e.c)} حکم کرد")
                delay(1500); banner = null
            }
            "play" -> {
                val c = (e.card ?: return).toInt()
                if (seat == me && selfPlayed == c) { selfPlayed = null; return }
                throwCard(seat, c, null, null)
            }
            "trick" -> collect((e.team?.toInt() ?: (seat % 2)))
            "hand" -> {
                val ours = e.team?.toInt() == me % 2
                banner = (if (ours) "این دست مال ما شد" else "این دست مال حریف شد") + if (e.kot) " · کُت! (${e.pts.fd()} امتیاز)" else ""
                delay(2200); banner = null
            }
        }
    }

    /** قدرت پرتاب (۰ آرام تا ۱ محکم): برگی که حکم می زند همیشه محکم، برگی که سر می شود اغلب محکم */
    private fun strength(s: Int, c: Int): Float {
        var p = .28f + Random.nextFloat() * .5f
        val tr = game?.trump?.toInt()
        if (pile.isNotEmpty() && tr != null) {
            val led = pile[0].second / 13
            val cut = c / 13 == tr && led != tr
            val tops = winnerOf(pile.toList() + (s to c), tr) == s
            if (cut) p = .86f + Random.nextFloat() * .14f else if (tops && Random.nextFloat() < .65f) p = .74f + Random.nextFloat() * .24f
        }
        return p
    }

    /** پرتاب برگ با فیزیک: از دست بازیکن در هوا می چرخد، به میز می خورد و تا ایستادن سُر می خورد */
    suspend fun throwCard(s: Int, c: Int, power: Float?, dir: Float?) {
        val (x, y, r) = slotOf(s, c, me).let { Triple(it[0], it[1], it[2]) }
        val R = rel(s, me)
        val mine = s == me
        val P = power ?: strength(s, c)
        val from = if (mine) handRect[c]?.center else seatRect[R]?.center
        val k = pileK
        val px = { sx: Float -> (sx - pileOrigin.x) / (k * density) }
        val py = { sy: Float -> (sy - pileOrigin.y) / (k * density) }
        val sx = from?.let { px(it.x) } ?: (x + 32)
        val sy = from?.let { py(it.y) } ?: (y + 45 + 200)
        val D = (Math.PI / 180).toFloat()
        val sg = if (dir != null && abs(dir) > 150) kotlin.math.sign(dir) else if (Random.nextBoolean()) -1f else 1f
        val spin = (if (mine) 10f else 0f) + 30 * P * sg
        val a0 = ((if (mine) r - 10 else if (R == 1) 78f else if (R == 3) -78f else 172f) + spin) * D
        val probe = CardPhysics.Body(-1, x + 32, y + 45, r * D)
        val o = CardPhysics.Throw(sx, sy, if (mine) 30f else 45f, a0, P = P, B = motion.order, box = motion.zoneOf(probe), tx = x + 32, ty = y + 45, a1 = r * D)
        o.T = max(.2f, min(.46f, (.16f + hypot(o.tx - o.sx, o.ty - o.sy) * .0006f) * (1.2f - .45f * P)))
        val A = CardPhysics.aim(o)
        val run = CardPhysics.fly(o, A.lx, A.ly, A.w0, motion.env, true)
        val tilt = 16 + 22 * P
        val rx0 = if (R == 0) tilt else if (R == 2) -tilt else 0f
        val ry0 = if (R == 1) -tilt else if (R == 3) tilt else 0f
        val t = Throwing(c, run, o.tx, o.ty, rx0, ry0, mine, run.lands.firstOrNull()?.t ?: o.T, CompletableDeferred())
        flying += t
        t.done.await()
        flying -= t
        motion.land(c, run)
        pile += s to c
        motion.sync(pile, me)
    }

    /** جمع کردن دور: برگ ها پشت رو به دستهٔ برگ های تیم برنده سُر می خورند */
    private suspend fun collect(team: Int) {
        delay(420)
        collecting = team
        delay(560)
        collecting = null
        pile.clear()
        motion.sync(pile, me)
    }
}

/** صفحهٔ بازی حکم (hokm.html و hokm.js): من پایین، یار بالا، حریف ها چپ و راست */
@Composable
fun HokmScreen(vm: AppViewModel, matchId: String) {
    val model = remember(matchId) { vm.table("hokm", matchId) }
    val play = remember(matchId) { HokmPlay() }
    val motion = remember(matchId) { TableMotion() }
    play.motion = motion
    play.density = LocalDensity.current.density
    val scope = rememberCoroutineScope()
    var leaving by remember { mutableStateOf(false) }
    BackHandler { leaving = true }
    LaunchedEffect(Unit) { if (vm.shop.styles == null) vm.shop.load() }
    // فقط وقتی برنامه جلوی چشم است از سرور می پرسد؛ وگرنه سرور فکر می کند بازیکن سر میز است
    // و نوتیفیکیشن نوبت نمی فرستد
    val life = androidx.lifecycle.compose.LocalLifecycleOwner.current
    LaunchedEffect(model, life) {
        life.repeatOnLifecycle(androidx.lifecycle.Lifecycle.State.STARTED) { while (true) {
            if (!play.busy && !model.acting) model.poll()
            val v = model.view
            if (model.failed != null || v?.status == "over" || v?.status == "cancelled") break
            delay(900)
        } }
    }
    LaunchedEffect(model) { snapshotFlow { model.view }.filterNotNull().collect { play.apply(it) } }
    LaunchedEffect(motion) { motion.run() }
    // حسگر گوشی (تکان برگ ها): با تنظیم «تکان برگ‌ها» در نمایه خاموش می شود
    val ctx = LocalContext.current
    DisposableEffect(vm.tilt, life) {
        val sm = ctx.getSystemService(Context.SENSOR_SERVICE) as? SensorManager
        val acc = sm?.getDefaultSensor(Sensor.TYPE_ACCELEROMETER)
        val l = object : SensorEventListener {
            override fun onSensorChanged(e: SensorEvent) { motion.accel(e.values[0], e.values[1], e.values[2]) }
            override fun onAccuracyChanged(s: Sensor?, a: Int) {}
        }
        val obs = androidx.lifecycle.LifecycleEventObserver { _, ev ->
            when (ev) {
                androidx.lifecycle.Lifecycle.Event.ON_RESUME -> if (vm.tilt && acc != null) { motion.resetSensor(); sm?.registerListener(l, acc, SensorManager.SENSOR_DELAY_GAME) }
                androidx.lifecycle.Lifecycle.Event.ON_PAUSE -> { sm?.unregisterListener(l); motion.resetSensor() }
                else -> {}
            }
        }
        life.lifecycle.addObserver(obs)
        onDispose { life.lifecycle.removeObserver(obs); sm?.unregisterListener(l); motion.resetSensor() }
    }
    val table = vm.shop.styles?.table ?: "a"
    val look = vm.shop.styles?.cards ?: "a"
    val f = FELT[table] ?: FELT.getValue("a")
    CompositionLocalProvider(LocalAso provides gameColors(Aso.c)) {
        val c = Aso.c
        Box(Modifier.fillMaxSize().background(cssEllipse(.5f, .3f, 1.56f, 1.04f, 0f to f[1], .46f to f[2], 1f to Color(0xFF050A07)))) {
            val v = model.view
            val g = play.game
            when {
                model.failed != null && g == null -> Column(Modifier.align(Alignment.Center).padding(24.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                    Text(model.failed.orEmpty(), style = peyda(15f, 24f, 700), color = c.ink, textAlign = TextAlign.Center)
                    Spacer(Modifier.height(12.dp))
                    Btn("برگشت", vm.play::closeGame)
                }
                g == null -> CircularProgressIndicator(Modifier.align(Alignment.Center), color = c.acc)
                else -> HokmTable(vm, model, play, motion, g, table, look, onLeave = { leaving = true })
            }
            // برگ های در حال پرتاب روی همه چیز
            FlyLayer(play, motion, look)
            // گفتگوی سر میز: پیام ها بالای نوار من شناور می شوند (hokm.js: rest = meBar)
            TableChatLayer(model, HOKM_QUICK, rest = 204.dp, enabled = v?.status == "playing" && g?.over == false)
            val vv = play.view
            if (vv != null && g != null && (vv.status == "over" || g.over)) {
                val myTeam = play.me % 2
                val won = vv.result?.won ?: (g.winner?.toInt() == myTeam)
                HokmResult(g, myTeam, won, vv.result?.coins ?: 0, vv.result?.cups ?: 0,
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

/** دکمهٔ گرد شیشه ای سربرگ حکم (hk-ib) */
@Composable
private fun HkBtn(icon: String, onClick: () -> Unit) {
    Box(Modifier.size(44.dp).clip(RoundedCornerShape(14.dp)).background(Color.Black.copy(alpha = .22f)).press(.94f, onClick = onClick),
        contentAlignment = Alignment.Center) { Ic(icon, size = 20.dp, tint = Color.White) }
}

@Composable
private fun HokmTable(vm: AppViewModel, model: TableModel, play: HokmPlay, motion: TableMotion, g: HokmGame, table: String, look: String, onLeave: () -> Unit) {
    val scope = rememberCoroutineScope()
    val me = play.me
    val myTeam = me % 2
    var now by remember { mutableLongStateOf(System.currentTimeMillis()) }
    LaunchedEffect(Unit) { while (true) { now = System.currentTimeMillis(); delay(200) } }
    val left = if (play.deadlineAt > 0) ((play.deadlineAt - now).coerceAtLeast(0L).toFloat() / play.turnMs).coerceAtMost(1f) else 1f
    val secs = if (play.deadlineAt > 0) ((play.deadlineAt - now).coerceAtLeast(0L) + 999) / 1000 else 0L
    val mine = g.turn?.toIntOrNull() == me && g.phase == "play" && !g.over
    val canPlay = mine && !play.busy && !model.acting
    var pick by remember { mutableStateOf<Int?>(null) }

    fun playCard(card: Int, flickP: Float?, flickDx: Float?) {
        if (!canPlay || card.toLong() !in g.legal) return
        play.selfPlayed = card
        val before = model.view
        scope.launch {
            val t = launch { play.throwCard(me, card, flickP, flickDx) }
            model.act("play", card.toLong())
            if (model.view === before) {
                // سرور نپذیرفت: برگ برمی گردد
                t.cancel(); play.selfPlayed = null
                play.flying.removeAll { it.c == card }
                play.pile.removeAll { it.second == card }
                motion.sync(play.pile, me)
            }
        }
    }

    Column(Modifier.fillMaxSize().statusBarsPadding().navigationBarsPadding()) {
        // ---------- سربرگ: خروج، امتیاز و حکم، راهنما، صدا ----------
        Row(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp), verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            HkBtn("exit", onLeave)
            ScoreBar(g, myTeam, Modifier.weight(1f))
            HkBtn("help") { vm.openHelp("hHokm") }
            HkBtn(if (vm.me?.sound != false) "soundOn" else "soundOff") { vm.toggleSound() }
        }
        // ---------- میز ----------
        Column(Modifier.fillMaxWidth().weight(1f).padding(start = 12.dp, end = 12.dp, bottom = 8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Felt(table, Modifier.fillMaxWidth().weight(1f), radius = 28.dp) {
                CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
                    TableBody(vm, model, play, motion, g, look, left, secs, onPick = { s -> pick = s },
                        pick = pick, onTrump = { s -> scope.launch { model.act("trump", s.toLong()) } })
                }
            }
            // ---------- دست من (بادبزن) ----------
            Hand(play, g, look, canPlay, motion) { card, p, dx -> playCard(card, p, dx) }
        }
    }
}

/** امتیاز: ما | حکم | حریف */
@Composable
private fun ScoreBar(g: HokmGame, us: Int, modifier: Modifier) {
    Row(modifier.height(62.dp).clip(RoundedCornerShape(20.dp)).background(Color.Black.copy(alpha = .22f)), verticalAlignment = Alignment.CenterVertically) {
        TeamCol(g, "خودت", us, true, Modifier.weight(1f))
        Column(Modifier.width(62.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(2.dp)) {
            val tr = g.trump?.toInt()
            Box(
                Modifier.size(36.dp).then(
                    if (tr != null) Modifier.border(3.dp, GOLD, CircleShape).padding(0.dp).clip(CircleShape).background(Color.White)
                    else Modifier.drawBehind {
                        drawCircle(Color.White.copy(alpha = .5f), style = Stroke(2.dp.toPx(), pathEffect = androidx.compose.ui.graphics.PathEffect.dashPathEffect(floatArrayOf(6f, 5f))))
                    },
                ),
                contentAlignment = Alignment.Center,
            ) {
                if (tr != null) SuitIcon(tr, 21.dp) else Text("؟", style = peyda(15f, 20f, 800), color = Color.White.copy(alpha = .7f))
            }
            Text(if (tr != null) "حکم ${SUIT_FA[tr]}" else "حکم", style = peyda(10f, 13f, 600), color = Color.White.copy(alpha = .82f))
        }
        TeamCol(g, "حریف", 1 - us, false, Modifier.weight(1f))
    }
}

@Composable
private fun TeamCol(g: HokmGame, label: String, t: Int, gold: Boolean, m: Modifier) {
    Column(m, horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(1.dp)) {
        Text(label, style = peyda(11f, 13f, 600), color = if (gold) GOLD else Color.White.copy(alpha = .8f))
        Row(verticalAlignment = Alignment.Bottom) {
            Text(g.score.getOrElse(t) { 0L }.fd(), style = peyda(21f, 24f, 800), color = Color.White)
            Text(" / ${g.target.fd()}", style = peyda(12f, 18f, 600), color = Color.White.copy(alpha = .6f))
        }
        Text("${g.tricks.getOrElse(t) { 0L }.fd()} دست", style = peyda(10.5f, 13f), color = Color.White.copy(alpha = .72f))
    }
}

/** عکس بازیکن با حلقهٔ رنگی و زمان نوبت (avatar.timer) */
@Composable
private fun RingFace(p: HokmPlayer, ring: Color, t: Float?, size: Dp) {
    val tt by animateFloatAsState((t ?: 1f).coerceIn(0f, 1f), tween(250, easing = LinearEasing), label = "t")
    Box(Modifier.size(size), contentAlignment = Alignment.Center) {
        Canvas(Modifier.fillMaxSize()) {
            if (t != null) {
                drawCircle(Color.White.copy(alpha = .2f))
                drawArc(ring, -90f, 360f * tt, useCenter = true)
            } else drawCircle(ring)
        }
        Face(p.name, p.av, if (p.bot) null else p.pic, size = size, ring = Color.Transparent, bot = p.bot)
    }
}

/** داخل میز: یار بالا، حریف ها دو طرف، تودهٔ وسط، دسته های برده، نوار من و دکمهٔ چت */
@Composable
private fun TableBody(vm: AppViewModel, model: TableModel, play: HokmPlay, motion: TableMotion, g: HokmGame, look: String, left: Float, secs: Long,
                      pick: Int?, onPick: (Int) -> Unit, onTrump: (Int) -> Unit) {
    val me = play.me
    val seatOf = { r: Int -> ((me + r) % 4).toString() }
    val rects = remember { HashMap<String, Rect>() }
    var tableRect by remember { mutableStateOf(Rect.Zero) }
    fun remeasure() {
        val pr = play.pileOrigin
        val k = play.pileK * play.density
        val gap = 6 * play.density
        val wall = 8 * play.density
        val l = max(tableRect.left + wall, (rects["s3"]?.right ?: tableRect.left) + gap)
        val r = min(tableRect.right - wall, (rects["s1"]?.left ?: tableRect.right) - gap)
        val t = max(tableRect.top + wall, (rects["s2"]?.bottom ?: tableRect.top) + gap)
        val b = min(tableRect.bottom - wall, min(rects["me"]?.top ?: tableRect.bottom, rects["chat"]?.top ?: tableRect.bottom) - gap)
        if (r > l && b > t) motion.setBox(CardPhysics.Box((l - pr.x) / k, (t - pr.y) / k, (r - pr.x) / k, (b - pr.y) / k))
    }
    BoxWithConstraints(Modifier.fillMaxSize().onGloballyPositioned { tableRect = it.boundsInRoot(); remeasure() }.padding(horizontal = 8.dp, vertical = 12.dp)) {
        val W = maxWidth
        val H = maxHeight
        // ستون وسط ۲۰۶، دو طرف سهم برابر؛ ردیف ها: یار، وسط، نوار من
        val side = (W - 206.dp - 12.dp) / 2
        // دسته های برده (ضربدری روی هم)
        Stack(g.tricks.getOrElse(me % 2) { 0L }.toInt(), look, Modifier.absoluteOffset(4.dp, H - 76.dp - 60.dp + 12.dp).onGloballyPositioned { play.stackUs = it.boundsInRoot().center })
        Stack(g.tricks.getOrElse(1 - me % 2) { 0L }.toInt(), look, Modifier.absoluteOffset(W - 60.dp - 4.dp, 0.dp).onGloballyPositioned { play.stackThem = it.boundsInRoot().center })
        Column(Modifier.fillMaxSize()) {
            // یار بالا
            Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.TopCenter) {
                SeatView(play, g, seatOf(2), 2, look, left, Modifier.onGloballyPositioned { rects["s2"] = it.boundsInRoot(); play.seatRect[2] = it.boundsInRoot(); remeasure() })
            }
            Spacer(Modifier.height(6.dp))
            Row(Modifier.fillMaxWidth().weight(1f), verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.width(side), contentAlignment = Alignment.Center) {
                    SeatView(play, g, seatOf(3), 3, look, left, Modifier.onGloballyPositioned { rects["s3"] = it.boundsInRoot(); play.seatRect[3] = it.boundsInRoot(); remeasure() })
                }
                Spacer(Modifier.width(6.dp))
                // تودهٔ وسط: ۲۰۶×۲۳۶ با مقیاس هر چه جا باشد (fit)
                BoxWithConstraints(Modifier.width(206.dp).fillMaxSize(), contentAlignment = Alignment.Center) {
                    val k = max(.72f, min(1.12f, min(maxHeight / 236.dp, maxWidth / 206.dp)))
                    play.pileK = k
                    Pile(play, motion, g, look, k, pick, onPick, onTrump,
                        Modifier.size(206.dp * k, 236.dp * k).onGloballyPositioned { play.pileOrigin = it.positionInRoot(); remeasure() })
                }
                Spacer(Modifier.width(6.dp))
                Box(Modifier.width(side), contentAlignment = Alignment.Center) {
                    SeatView(play, g, seatOf(1), 1, look, left, Modifier.onGloballyPositioned { rects["s1"] = it.boundsInRoot(); play.seatRect[1] = it.boundsInRoot(); remeasure() })
                }
            }
            Spacer(Modifier.height(6.dp))
            // نوار من (راست) و دکمهٔ چت (چپ)
            Box(Modifier.fillMaxWidth().heightIn(min = 56.dp).padding(bottom = 4.dp)) {
                CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Rtl) {
                    Box(Modifier.align(AbsoluteAlignment.CenterRight).padding(start = 6.dp + 112.dp + 10.dp, end = 6.dp)
                        .onGloballyPositioned { rects["me"] = it.boundsInRoot(); play.seatRect[0] = it.boundsInRoot(); remeasure() }) {
                        MeBar(play, g, left, secs)
                    }
                    Box(Modifier.align(AbsoluteAlignment.CenterLeft).padding(start = 8.dp).onGloballyPositioned { rects["chat"] = it.boundsInRoot(); remeasure() }) {
                        Box {
                            Row(Modifier.height(44.dp).clip(RoundedCornerShape(22.dp)).background(GOLD).press { model.openChat(true) }
                                .padding(start = 16.dp, end = 12.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                                Ic("chat", size = 20.dp, tint = GOLD_INK)
                                Text("چت کن", style = peyda(13.5f, 20f, 800), color = GOLD_INK)
                            }
                            ChatBadge(model.unread, Modifier.align(Alignment.TopEnd), ring = Color(0xFF1A7A47))
                        }
                    }
                }
            }
        }
        play.banner?.let { b ->
            Text(b, Modifier.align(Alignment.Center).zIndex(80f).clip(RoundedCornerShape(16.dp)).background(Color.Black.copy(alpha = .55f)).padding(horizontal = 16.dp, vertical = 10.dp),
                style = peyda(15f, 22f, 800), color = Color.White, textAlign = TextAlign.Center)
        }
    }
}

/** بازیکن دیگر: عکس با حلقه (نوبت طلایی با زمان، یار سبز روشن، حریف سفید)، تاج حاکم، نام، وضعیت و پشت برگ ها */
@Composable
private fun SeatView(play: HokmPlay, g: HokmGame, s: String, r: Int, look: String, left: Float, modifier: Modifier) {
    val p = g.players[s] ?: return
    val partner = p.team.toInt() == play.me % 2
    val hk = g.hakem == s
    val turn = g.turn == s && !g.over
    Column(modifier.graphicsLayer { alpha = if (p.out) .55f else 1f }, horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(2.dp)) {
        Box {
            RingFace(p, if (turn) GOLD else if (partner) Color(0xFF9BE3B8) else Color.White, if (turn) left else null, 50.dp)
            if (hk) Box(Modifier.align(Alignment.TopEnd).offset(x = 4.dp, y = (-4).dp).size(22.dp).clip(CircleShape).background(GOLD)
                .border(2.dp, Color(0xFF1A7A47), CircleShape), contentAlignment = Alignment.Center) { CrownIcon(13.dp) }
        }
        CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Rtl) {
            Text(p.name, Modifier.widthIn(max = 96.dp), style = peyda(13f, 18f, 800), color = Color.White, maxLines = 1, overflow = TextOverflow.Ellipsis)
            Text(listOfNotNull(if (partner) "یار تو" else null, if (hk) "حاکم" else null, if (p.out) "ربات جاشه" else "${p.count.fd()} برگ").joinToString(" · "),
                style = peyda(11f, 15f), color = if (hk) GOLD else Color.White.copy(alpha = .78f), maxLines = 1)
        }
        Fan(p.count.toInt(), r, look)
    }
}

/** برگ های حریف ها: یار بادبزن افقی زیر اسمش، حریف های چپ و راست ستون برگ خوابیده */
@Composable
private fun Fan(count: Int, r: Int, look: String) {
    val n = min(if (r == 2) 6 else 5, count)
    if (n <= 0) return
    val mid = (n - 1) / 2f
    if (r == 2) {
        Box(Modifier.padding(top = 3.dp).size(96.dp, 46.dp).graphicsLayer { rotationZ = 180f }) {
            repeat(n) { i ->
                PlayingBack(look, 28.dp, Modifier.absoluteOffset(48.dp - 14.dp, 2.dp).graphicsLayer {
                    transformOrigin = TransformOrigin(.5f, 1.2f)
                    translationX = (i - mid) * 11 * density; translationY = abs(i - mid) * 1.6f * density; rotationZ = (i - mid) * 7
                })
            }
        }
    } else {
        val dir = if (r == 3) 1 else -1
        Box(Modifier.padding(top = 4.dp).size(60.dp, 86.dp)) {
            repeat(n) { i ->
                PlayingBack(look, 28.dp, Modifier.absoluteOffset(30.dp - 14.dp, 43.dp - 20.dp).graphicsLayer {
                    translationX = dir * (6 + (i % 2) * 1.5f) * density; translationY = (i - mid) * 9.5f * density; rotationZ = 90 + (i - mid) * 2.2f * dir
                })
            }
        }
    }
}

/** دستهٔ برگ های بردهٔ هر تیم: ضربدری روی هم، با شمار */
@Composable
private fun Stack(n: Int, look: String, modifier: Modifier) {
    Box(modifier.size(60.dp)) {
        repeat(n) { i ->
            PlayingBack(look, 30.dp, Modifier.absoluteOffset(15.dp, 9.dp).zIndex(i + 1f).graphicsLayer {
                translationX = i * .8f * density; translationY = -i * 1.4f * density; rotationZ = (if (i % 2 == 1) 90f else 0f) + ((i * 37) % 9) - 4
            })
        }
        if (n > 0) Text("${n.fd()} دست", Modifier.align(Alignment.BottomCenter).offset(y = 6.dp).zIndex(30f).clip(CircleShape).background(Color.Black.copy(alpha = .55f))
            .padding(horizontal = 7.dp), style = peyda(11f, 18f, 800), color = Color.White)
    }
}

/** تودهٔ وسط: برگ های این دور که با جاذبه سُر می خورند و با انگشت هل داده می شوند؛ یا انتخاب حکم */
@Composable
private fun Pile(play: HokmPlay, motion: TableMotion, g: HokmGame, look: String, k: Float, pick: Int?, onPick: (Int) -> Unit, onTrump: (Int) -> Unit, modifier: Modifier) {
    val me = play.me
    Box(modifier) {
        if (g.phase == "trump" && !g.over) {
            if (g.hakem.toIntOrNull() == me) TrumpPick(pick, onPick, onTrump, Modifier.align(Alignment.Center))
            else Choosing(g, play, Modifier.align(Alignment.Center))
            return@Box
        }
        // راهنما: برگ چه کسی بالاست
        val tr = g.trump?.toInt()
        val pile = play.pile.toList()
        if (pile.size in 2..3 && tr != null) {
            val w = winnerOf(pile, tr)
            val who = if (w == me) "تو" else g.players[w.toString()]?.name ?: ""
            Text("فعلاً برگ $who بالاست", Modifier.align(Alignment.TopCenter).offset(y = (-34).dp).zIndex(50f).clip(CircleShape).background(Color.Black.copy(alpha = .28f))
                .padding(horizontal = 10.dp, vertical = 2.dp), style = peyda(11.5f, 16f, 600), color = Color(0xFFFFE08F), maxLines = 1)
        }
        val collect = play.collecting
        val toward = if (collect == null) null else (if (collect == me % 2) play.stackUs else play.stackThem)
        val cp = remember(collect) { Animatable(0f) }
        LaunchedEffect(collect) { if (collect != null) cp.animateTo(1f, tween(520, easing = androidx.compose.animation.core.CubicBezierEasing(.45f, .05f, .3f, 1f))) }
        val origin = play.pileOrigin
        for (b in motion.order) key(b.c) {
            PlayingCard(b.c, 64.dp * k, look, Modifier.zIndex(b.z).graphicsLayer {
                @Suppress("UNUSED_VARIABLE") val t = motion.tick
                var x = (b.x - 32) * k * density
                var y = (b.y - 45) * k * density
                var rot = b.a * R2D
                var sc = 1f
                if (toward != null) {
                    val q = cp.value
                    val cx = origin.x + x + 32 * k * density
                    val cy = origin.y + y + 45 * k * density
                    x += (toward.x - cx) * q; y += (toward.y - cy) * q
                    rot += ((if (collect == me % 2) 90f else -90f) - rot) * q
                    sc = 1f - .53f * q
                    alpha = 1f - .4f * q
                }
                translationX = x; translationY = y; rotationZ = rot; scaleX = sc; scaleY = sc
            }, sp = motion.sp, so = motion.so)
        }
        // انگشت روی برگ های میز
        Box(Modifier.fillMaxSize().pointerInput(k) {
            awaitPointerEventScope {
                while (true) {
                    val e = awaitPointerEvent()
                    val ch = e.changes.firstOrNull() ?: continue
                    val x = ch.position.x / (k * density)
                    val y = ch.position.y / (k * density)
                    when {
                        ch.pressed && !ch.previousPressed -> if (motion.down(x, y)) ch.consume()
                        ch.pressed -> { motion.move(x, y); ch.consume() }
                        !ch.pressed && ch.previousPressed -> motion.up()
                    }
                }
            }
        })
    }
}

/** انتخاب حکم (فقط حاکم، با دیدن پنج برگ اول) — hk-pick */
@Composable
private fun TrumpPick(pick: Int?, onPick: (Int) -> Unit, onTrump: (Int) -> Unit, modifier: Modifier) {
    val bob = rememberInfiniteTransition(label = "bob").animateFloat(0f, 1f, infiniteRepeatable(tween(1100), RepeatMode.Reverse), label = "b")
    CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Rtl) {
        Column(modifier.width(204.dp).clip(RoundedCornerShape(22.dp)).background(Color.Black.copy(alpha = .4f)).border(1.dp, Color.White.copy(alpha = .12f), RoundedCornerShape(22.dp))
            .padding(horizontal = 12.dp, vertical = 10.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(7.dp)) {
            Box(Modifier.offset(y = 4.dp).graphicsLayer { translationY = -4 * density * bob.value; rotationZ = -6 + 12 * bob.value }
                .size(30.dp).clip(CircleShape).background(GOLD), contentAlignment = Alignment.Center) { CrownIcon(20.dp) }
            Text("تو حاکمی حکم کن!", style = peyda(17f, 24f, 800), color = Color.White)
            Text("از رو پنج برگ اولت خال حکمو بزن", style = peyda(11.5f, 18f), color = Color.White.copy(alpha = .8f), textAlign = TextAlign.Center)
            for (row in listOf(listOf(0, 1), listOf(3, 2))) {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    for (s in row) {
                        val on = pick == s
                        Column(Modifier.weight(1f).height(50.dp).graphicsLayer { if (on) { translationY = -2 * density; scaleX = 1.04f; scaleY = 1.04f } }
                            .then(if (on) Modifier.border(3.dp, GOLD, RoundedCornerShape(14.dp)) else Modifier)
                            .clip(RoundedCornerShape(14.dp)).background(Color.White).press(.95f) { onPick(s) },
                            horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center) {
                            SuitIcon(s, 24.dp)
                            Text(SUIT_FA[s], style = peyda(12.5f, 16f, 800), color = if (isRed(s)) SUIT_RED else SUIT_BLACK)
                        }
                    }
                }
            }
            Btn(if (pick == null) "یه خالو بزن" else "حکم ${SUIT_FA[pick]} باشه", { pick?.let(onTrump) }, Modifier.fillMaxWidth(), kind = BtnKind.Gold, small = true, enabled = pick != null)
        }
    }
}

/** حاکم دیگری در حال انتخاب حکم: چهار خال دور عکسش می چرخند (hk-choosing) */
@Composable
private fun Choosing(g: HokmGame, play: HokmPlay, modifier: Modifier) {
    val hp = g.players[g.hakem] ?: return
    val spin = rememberInfiniteTransition(label = "orbit").animateFloat(0f, 360f, infiniteRepeatable(tween(6000, easing = LinearEasing)), label = "o")
    CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Rtl) {
        Column(modifier, horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Box(Modifier.size(136.dp), contentAlignment = Alignment.Center) {
                Canvas(Modifier.fillMaxSize().padding(14.dp)) {
                    drawCircle(Color.White.copy(alpha = .28f), style = Stroke(1.5f * density, pathEffect = androidx.compose.ui.graphics.PathEffect.dashPathEffect(floatArrayOf(6f, 5f))))
                }
                Box(Modifier.fillMaxSize().graphicsLayer { rotationZ = spin.value }) {
                    for ((i, pos) in listOf(Offset(.5f, .103f), Offset(.897f, .5f), Offset(.5f, .897f), Offset(.103f, .5f)).withIndex()) {
                        Box(Modifier.absoluteOffset(136.dp * pos.x - 18.dp, 136.dp * pos.y - 18.dp).size(36.dp).graphicsLayer { rotationZ = -spin.value }
                            .clip(CircleShape).background(Color.White), contentAlignment = Alignment.Center) { SuitIcon(i, 21.dp) }
                    }
                }
                Box {
                    RingFace(hp, GOLD, null, 56.dp)
                    Box(Modifier.align(Alignment.TopCenter).offset(y = (-15).dp).size(28.dp).clip(CircleShape).background(GOLD), contentAlignment = Alignment.Center) { CrownIcon(16.dp) }
                }
            }
            Text("${hp.name} داره حکم می‌کنه…", style = peyda(14f, 20f, 800), color = Color.White)
            Text((if (hp.team.toInt() == play.me % 2) "یارت" else "حریف") + " از رو پنج برگ اولش خال حکمو انتخاب می‌کنه",
                Modifier.widthIn(max = 196.dp), style = peyda(11.5f, 17f), color = Color.White.copy(alpha = .75f), textAlign = TextAlign.Center)
        }
    }
}

/** نوار من: نوبت، زمان، راهنما (hk-mb) */
@Composable
private fun MeBar(play: HokmPlay, g: HokmGame, left: Float, secs: Long) {
    val me = play.me
    val p = g.players[me.toString()]
    val mine = g.turn?.toIntOrNull() == me
    val hakemMe = g.hakem.toIntOrNull() == me
    val (t, sub) = when {
        g.over -> "بازی تموم شد" to ""
        g.phase == "trump" -> (if (hakemMe) "تو حاکمی" else "حاکم ${g.players[g.hakem]?.name.orEmpty()}") to (if (hakemMe) "حکمو انتخاب کن" else "منتظریم حکمو انتخاب کنه")
        g.phase == "play" && mine -> "نوبت توئه" to run {
            val led = g.led?.toInt()
            if (led == null) "دورو تو شروع کن"
            else {
                val has = g.hand.any { (it / 13).toInt() == led }
                "${SUIT_FA[led]} اومده و " + if (has) "باید ${SUIT_FA[led]} بیاری" else "${SUIT_FA[led]} نداری پس حکم یا هر برگی"
            }
        }
        g.phase == "play" -> {
            val q = g.players[g.turn.orEmpty()]
            "نوبت ${q?.name.orEmpty()}" to (if (q?.bot == true || q?.out == true) "ربات داره فکر می‌کنه…" else "منتظریم بازی کنه…")
        }
        g.phase == "collect" -> "دور تموم شد" to ""
        else -> "دست بعد…" to "ورقا دارن بُر می‌خورن"
    }
    val timer = (mine && g.phase == "play") || (g.phase == "trump" && hakemMe)
    Box {
        Row(
            Modifier.clip(CircleShape).background(Color.Black.copy(alpha = if (timer) .38f else .3f))
                .border(if (timer) 1.5.dp else 1.dp, if (timer) GOLD.copy(alpha = .75f) else Color.White.copy(alpha = .09f), CircleShape)
                .padding(start = 6.dp, end = 18.dp, top = 6.dp, bottom = 6.dp),
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            if (p != null) RingFace(p, if (timer) GOLD else Color(0xFF9BE3B8), if (timer) left else null, 44.dp)
            Column(verticalArrangement = Arrangement.spacedBy(1.dp)) {
                Text(t, style = peyda(14.5f, 20f, 800), color = Color.White, maxLines = 1, overflow = TextOverflow.Ellipsis)
                if (sub.isNotEmpty()) Text(sub, style = peyda(12f, 17f), color = Color.White.copy(alpha = .78f), maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
        }
        if (timer && play.deadlineAt > 0) {
            Text("${secs.fd()} ثانیه", Modifier.align(Alignment.TopEnd).offset(x = (-16).dp, y = (-10).dp).clip(CircleShape).background(GOLD).padding(horizontal = 9.dp),
                style = peyda(11.5f, 20f, 800), color = GOLD_INK)
        }
    }
}

/** دست بادبزنی: برگ های مجاز جدا و بالاتر، بقیه فشرده و کم رنگ؛ زدن یا کشیدن رو به میز = انداختن */
@Composable
private fun Hand(play: HokmPlay, g: HokmGame, look: String, canPlay: Boolean, motion: TableMotion, playCard: (Int, Float?, Float?) -> Unit) {
    val flying = play.flying.map { it.c }.toSet() + listOfNotNull(play.selfPlayed)
    val cards = handOrder(g.hand.map { it.toInt() }, g.trump?.toInt()).filter { it !in flying }
    val n = cards.size
    val mine = g.turn?.toIntOrNull() == play.me && g.phase == "play"
    val ok = if (mine) g.legal.map { it.toInt() }.toSet() else emptySet()
    val split = mine && ok.isNotEmpty() && ok.size < n
    fun wt(c: Int) = if (split) (if (c in ok) 2.2f else .75f) else 1f
    var acc = 0f
    val pos = cards.mapIndexed { i, c ->
        if (i > 0) {
            acc += (wt(c) + wt(cards[i - 1])) / 2
            if (split && (c in ok) != (cards[i - 1] in ok)) acc += 1.1f
        }
        acc
    }
    val total = if (n > 1) pos[n - 1] else 0f
    val step = if (total > 0f) min(if (split) 9f else 6.5f, (if (split) 33f else 31f) / total) else 0f
    CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
        BoxWithConstraints(Modifier.fillMaxWidth().height(150.dp)) {
            val cx = maxWidth / 2 - 32.dp
            cards.forEachIndexed { i, c ->
                key(c) {
                    val a = (total / 2 - pos[i]) * step + (hash01(c, 21) * 2 - 1) * .5f
                    val jx = (hash01(c, 22) * 2 - 1) * 1f
                    val jy = (hash01(c, 23) * 2 - 1) * 1.6f
                    val isOk = mine && c in ok
                    val isNo = mine && c !in ok
                    val ty by animateFloatAsState(if (isOk) -24f else if (isNo) 10f else 0f, tween(240), label = "y")
                    var drag by remember { mutableStateOf(Offset.Zero) }
                    var dragging by remember { mutableStateOf(false) }
                    Box(Modifier.absoluteOffset(cx, 150.dp - 14.dp - 90.dp).size(64.dp, 90.dp).zIndex(if (dragging) 60f else (n - i).toFloat())
                        .onGloballyPositioned { play.handRect[c] = it.boundsInRoot() }
                        .graphicsLayer {
                            transformOrigin = TransformOrigin(.5f, 520f / 90f)
                            rotationZ = a
                            // rotate(a) translate(jx, y+jy): جابه جایی در قاب چرخیده
                            val r = Math.toRadians(a.toDouble())
                            val dx = jx * density
                            val dy = (ty + jy) * density
                            translationX = (dx * cos(r) - dy * sin(r)).toFloat() + drag.x
                            translationY = (dx * sin(r) + dy * cos(r)).toFloat() + drag.y
                        }
                        .then(if (isOk && canPlay) Modifier.pointerInput(c) {
                            awaitPointerEventScope {
                                while (true) {
                                    val down = awaitPointerEvent().changes.firstOrNull { it.pressed } ?: continue
                                    val start = down.position
                                    val hist = ArrayList<Triple<Long, Float, Float>>()
                                    hist += Triple(down.uptimeMillis, start.x, start.y)
                                    var moved = false
                                    var last = start
                                    while (true) {
                                        val ev = awaitPointerEvent()
                                        val ch = ev.changes.firstOrNull { it.id == down.id } ?: break
                                        if (!ch.pressed) break
                                        val d = ch.position - start
                                        hist += Triple(ch.uptimeMillis, ch.position.x, ch.position.y); if (hist.size > 8) hist.removeAt(0)
                                        if (!moved && hypot(d.x, d.y) >= 8 * density) { moved = true; dragging = true }
                                        if (moved) { drag = Offset(d.x, min(12 * density, d.y)); ch.consume() }
                                        last = ch.position
                                    }
                                    if (!moved) { playCard(c, null, null); continue }
                                    val dy = (last.y - start.y) / density
                                    if (dy < -55) {
                                        // سرعت انگشت در ۱۰۰ میلی ثانیهٔ آخر: کشیدن آرام = پرتاب آرام، تند = محکم
                                        val z = hist.last()
                                        val a0 = hist.firstOrNull { z.first - it.first <= 100 } ?: hist.first()
                                        val t = max(16L, z.first - a0.first) / 1000f
                                        val vx = (z.second - a0.second) / density / t
                                        val vy = (z.third - a0.third) / density / t
                                        playCard(c, max(.05f, min(1f, (-vy - 250) / 2200)), vx)
                                    }
                                    drag = Offset.Zero; dragging = false
                                }
                            }
                        } else Modifier)
                    ) {
                        PlayingCard(c, 64.dp, look, Modifier.drawWithContent {
                            drawContent()
                            // نور روی خود برگ: لبهٔ بالا روشن تر، پایین کمی در سایه
                            drawRect(Brush.verticalGradient(0f to Color.White.copy(alpha = .12f), .2f to Color.Transparent, .58f to Color.Transparent, 1f to Color.Black.copy(alpha = .13f)))
                        }.then(if (isNo) Modifier.drawWithContent { drawContent(); drawRect(Color.Black.copy(alpha = .4f)) } else Modifier),
                            sp = motion.sp, so = motion.so)
                    }
                }
            }
        }
    }
}

/** برگ های در حال پرتاب: از پیش حساب شده (CardPhysics.fly) و با فریم های ۱/۶۰ ثانیه پخش می شوند */
@Composable
private fun FlyLayer(play: HokmPlay, motion: TableMotion, look: String) {
    var now by remember { mutableLongStateOf(0L) }
    val active = play.flying.isNotEmpty()
    LaunchedEffect(active) {
        while (play.flying.isNotEmpty()) {
            withFrameNanos { t ->
                now = t
                for (f in play.flying) {
                    if (f.t0 == 0L) f.t0 = t
                    if ((t - f.t0) / 1e9f >= f.run.t && !f.done.isCompleted) f.done.complete(Unit)
                }
            }
        }
    }
    var origin by remember { mutableStateOf(Offset.Zero) }
    Box(Modifier.fillMaxSize().zIndex(90f).onGloballyPositioned { origin = it.positionInRoot() }) {
        val k = play.pileK
        for (f in play.flying) key(f) {
            val el = if (f.t0 == 0L) 0f else (now - f.t0) / 1e9f
            val frames = f.run.frames
            val fr = frames[min(frames.size - 1, max(0, (el * 60).toInt()))]
            val q = fr.t
            val lift = min(1f, fr.h / 25f) * exp(-2.5f * q)
            val grow = if (f.mine) 1.04f - .04f * min(1f, q / f.T1) else .5f + .5f * (1 - (1 - min(1f, q / (f.T1 * .7f))).let { it * it })
            val dens = LocalDensity.current.density
            val baseX = play.pileOrigin.x - origin.x + (f.tx - 32) * k * dens
            val baseY = play.pileOrigin.y - origin.y + (f.ty - 45) * k * dens
            Box(Modifier.absoluteOffset { androidx.compose.ui.unit.IntOffset(baseX.toInt(), baseY.toInt()) }.size(64.dp, 90.dp)
                .graphicsLayer {
                    translationX = (fr.x - f.tx) * k * density
                    translationY = (fr.y - f.ty) * k * density
                    rotationZ = fr.a * R2D
                    rotationX = f.rx0 * lift
                    rotationY = f.ry0 * lift
                    cameraDistance = 12f * density
                    val s = k * grow * (1 + fr.h / 700f)
                    scaleX = s; scaleY = s
                }) {
                // سایهٔ برگ در هوا روی ماهوت
                val sx = fr.h * .3f
                val sy = fr.h * .55f
                val ca = cos(fr.a)
                val sa = sin(fr.a)
                Box(Modifier.fillMaxSize().graphicsLayer {
                    alpha = if (fr.h > .5f) .2f + .25f * min(1f, fr.h / 90f) else 0f
                    translationX = (sx * ca + sy * sa) * density; translationY = (sy * ca - sx * sa) * density
                    val sc = 1 + fr.h / 300f; scaleX = sc; scaleY = sc
                }.drawBehind {
                    drawRoundRect(Brush.radialGradient(0f to Color.Black.copy(alpha = .6f), .45f to Color.Black.copy(alpha = .42f), 1f to Color.Transparent,
                        radius = size.maxDimension * .6f), androidx.compose.ui.geometry.Offset(-7 * density, -7 * density),
                        androidx.compose.ui.geometry.Size(size.width + 14 * density, size.height + 14 * density), androidx.compose.ui.geometry.CornerRadius(16 * density))
                })
                PlayingCard(f.c, 64.dp, look, sp = motion.sp, so = motion.so)
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
