package dezhcode.asotas.ui

import androidx.activity.compose.BackHandler
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.EaseInOut
import androidx.compose.animation.core.EaseOut
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateDpAsState
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.absoluteOffset
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.Stable
import androidx.compose.runtime.State
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.runtime.snapshotFlow
import androidx.compose.ui.AbsoluteAlignment
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Rect
import androidx.compose.ui.geometry.RoundRect
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.ClipOp
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ColorFilter
import androidx.compose.ui.graphics.ColorMatrix
import androidx.compose.ui.graphics.Paint
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.RadialGradientShader
import androidx.compose.ui.graphics.Shader
import androidx.compose.ui.graphics.ShaderBrush
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.TransformOrigin
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.clipPath
import androidx.compose.ui.graphics.drawscope.drawIntoCanvas
import androidx.compose.ui.graphics.drawscope.rotate
import androidx.compose.ui.graphics.drawscope.withTransform
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.lerp
import androidx.compose.ui.graphics.vector.PathParser
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp
import androidx.compose.ui.zIndex
import dezhcode.asotas.AppViewModel
import dezhcode.asotas.TableModel
import dezhcode.asotas.core.LudoEvent
import dezhcode.asotas.core.LudoGame
import dezhcode.asotas.core.LudoPlayer
import dezhcode.asotas.core.MatchResult
import dezhcode.asotas.core.MatchView
import dezhcode.asotas.fa
import dezhcode.asotas.fd
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.filterNotNull
import kotlinx.coroutines.launch
import kotlin.math.abs
import kotlin.math.cos
import kotlin.math.floor
import kotlin.math.roundToInt
import kotlin.math.sin
import kotlin.random.Random

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
/** هر بازیکن رنگ خودش را پایین چپ می بیند: صفحه به اندازهٔ رنگ او می چرخد (ludo.js: ROT) */
private val ROT = mapOf("yellow" to 0f, "green" to 90f, "red" to 180f, "blue" to 270f)
private val BASE = mapOf("blue" to 0, "red" to 1, "green" to 2, "yellow" to 3)
private val PIPS = mapOf(1 to setOf(4), 2 to setOf(0, 8), 3 to setOf(0, 4, 8), 4 to setOf(0, 2, 6, 8), 5 to setOf(0, 2, 4, 6, 8), 6 to setOf(0, 2, 3, 5, 6, 8))

/** پیام های سریع گفتگوی میز منچ (ludo.js: QUICK) */
private val QUICK = listOf("سلام!", "خوش‌بازی!", "آفرین", "شانسی بود", "زود باش", "یه دست دیگه؟")

/** رنگ هر بازیکن (gc.js: COL) */
private val HEX = mapOf("blue" to Color(0xFF4C8DFF), "red" to Color(0xFFFF5A6A), "green" to Color(0xFF2FC584), "yellow" to Color(0xFFFFC531))
private val DEEP = mapOf("blue" to Color(0xFF2B62D6), "red" to Color(0xFFC93447), "green" to Color(0xFF1E8A5E), "yellow" to Color(0xFFC98A00))

// ---------- رنگ های «سالن شب» صفحهٔ بازی (tokens.css و gc.css: body.game) ----------
private val GLASS = Color(0x14FFFFFF)
private val GAME_BG = Color(0xFF12291F)
private val GAME_DEEP = Color(0xFF0A1914)
private val GAME_INK = Color(0xFFD3E2DA)
private val SURFACE = Color(0xFF17302A)
private val PATH_FILL = Color(0xFFF4F2FA)
private val PATH_EDGE = Color(0xFFCFC9E3)
private val COIN_DEEP = Color(0xFFE39A00)
private val ON_FILL = Color.White

/** زمینهٔ میز: radial-gradient(120% 70% at 50% 42%, #1F4A37, game-bg 60%, #0B1714) */
private val TableBg = object : ShaderBrush() {
    override fun createShader(size: Size): Shader {
        val c = Offset(size.width * .5f, size.height * .42f)
        val rx = size.width * 1.2f
        val ry = size.height * .7f
        return RadialGradientShader(c, rx, listOf(Color(0xFF1F4A37), GAME_BG, Color(0xFF0B1714)), listOf(0f, .6f, 1f)).apply {
            setLocalMatrix(android.graphics.Matrix().apply { setScale(1f, ry / rx, c.x, c.y) })
        }
    }
}

/** رنگ های «سالن شب» صفحهٔ بازی (gc.css: body.game) */
internal fun gameColors(base: AsoColors) = base.copy(
    dark = true, ground = Color(0xFF0C1915), groundDeep = Color(0xFF08120F), surface = Color(0xFF17302A), surfaceSunk = Color(0xFF11251F),
    line = Color(0x1AFFFFFF), ink = Color(0xFFF3F1E8), inkMuted = Color(0xFF9DB0A8), night = Color(0xFF07110E),
    acc = Color(0xFFF5C451), accDeep = Color(0xFFF7CF6A), accInk = Color(0xFF3A2A00), accTint = Color(0x26F5C451),
    coinTint = Color(0x24FFC93C), coinText = Color(0xFFFFD25E), success = Color(0xFF3DD68C), danger = Color(0xFFFF6B7A),
)

private fun svgPath(d: String) = PathParser().parsePathString(d).toPath()
private val STAR_PATH = svgPath("M12 2.5l2.9 6 6.6.9-4.8 4.6 1.2 6.5L12 17.4l-5.9 3.1 1.2-6.5L2.5 9.4l6.6-.9z")
private val ARROW_PATH = svgPath("M8 5l11 7-11 7z")
private val PAWN_STAR = svgPath("M20 30.2l2 4.1 4.5.6-3.3 3.1.8 4.5-4-2.2-4 2.2.8-4.5-3.3-3.1 4.5-.6z")
private val PAWN_GLINT = svgPath("M11.5 33a9.5 9.5 0 0 1 7-6")
private val CROWN_PATH = svgPath("M8 21l4.5 4 7.5-11 7.5 11 4.5-4-1.5 7.5h-21z")

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

/** واحد خانه به فاصله در لایهٔ مهره ها؛ فاصلهٔ بین خانه ها (۱dp) هم حساب می شود تا مهره درست وسط کاشی بنشیند (ludo.js: pct) */
private fun at(v: Float, layer: Dp): Dp {
    val i = floor(v).toInt().coerceIn(0, 14)
    val p = v / 15f
    return layer * p + 1.dp * (i - p * 14)
}

/** مقدار یک انیمیشن چند مرحله ای CSS در لحظهٔ t (۰ تا ۱)؛ شروع و پایان صفر */
private fun keyf(t: Float, vararg pts: Pair<Float, Float>): Float {
    var prev = 0f to 0f
    for (p in listOf(*pts) + (1f to 0f)) {
        if (t <= p.first) {
            val f = if (p.first > prev.first) (t - prev.first) / (p.first - prev.first) else 1f
            return prev.second + (p.second - prev.second) * EaseInOut.transform(f)
        }
        prev = p
    }
    return 0f
}

// ---------- پخش رویدادهای میز به ترتیب (ludo.js: apply و play) ----------
private class Feed(val id: Int, val color: String, val text: String)
private class Fx(val id: Int, val color: String, val x: Float, val y: Float)
private class Shake(val id: Int, val color: String)
private class Blocked(val id: Int, val color: String, val v: Int, val allYard: Boolean)

@Stable
private class LudoPlay {
    var me by mutableStateOf("yellow")
    var view by mutableStateOf<MatchView?>(null)
    /** آخرین وضعیت پخش شده: صندلی ها، نوبت و داک از این خوانده می شوند */
    var game by mutableStateOf<LudoGame?>(null)
    var busy by mutableStateOf(false)
    private var since = 0L
    private var n = 0
    /** جای مهره ها همان طور که روی صفحه دیده می شوند (قدم به قدم جلو می روند) */
    val shown = mutableStateMapOf<String, List<Long>>()
    val face = mutableStateMapOf<String, Int>()
    var myFace by mutableIntStateOf(0)
    var rolling by mutableStateOf<String?>(null)
    var rollFace by mutableIntStateOf(1)
    val hops = mutableStateMapOf<String, Int>()
    var feed by mutableStateOf<Feed?>(null)
    var flash by mutableStateOf<Fx?>(null)
    var nope by mutableStateOf<Shake?>(null)
    var blocked by mutableStateOf<Blocked?>(null)
    var deadlineAt by mutableLongStateOf(0L)
    var turnMs = 20000L
    var picked by mutableStateOf(false)
    var over by mutableStateOf(false)
    var cancelled by mutableStateOf(false)

    suspend fun apply(v: MatchView) {
        if (v.status == "cancelled") { cancelled = true; return }
        val g = v.ludo ?: return
        val arrived = System.currentTimeMillis()   // مهلت نوبت از رسیدن پاسخ حساب می شود، نه بعد از انیمیشن
        busy = true
        try {
            if (game == null) {
                // بار اول رویدادهای قبلی پخش نمی شوند؛ میز همان طور که هست چیده می شود
                me = v.me ?: "yellow"
                since = g.seq
                val d = g.dice
                if (g.turn == me && d != null) myFace = d.toInt()
            } else {
                for (e in g.events.filter { it.seq > since }.sortedBy { it.seq }) {
                    play(e, g)
                    since = e.seq
                }
            }
            since = maxOf(since, g.seq)
            shown.clear()
            shown.putAll(g.pawns)
            g.last.forEach { (c, d) -> face[c] = d.toInt() }
            turnMs = g.turnMs.takeIf { it > 0 } ?: 20000L
            val dl = if (g.deadlineMs > 0) arrived + g.deadlineMs else 0L
            if (dl == 0L) deadlineAt = 0L else if (deadlineAt == 0L || abs(dl - deadlineAt) > 700) deadlineAt = dl
            game = g
            view = v
            picked = false
            if (v.status == "over" || g.over) over = true
        } finally {
            busy = false
        }
    }

    private fun name(g: LudoGame, c: String) = g.players[c]?.let { if (it.me) "تو" else it.name }.orEmpty()

    private fun say(c: String, text: String) { feed = Feed(++n, c, text) }

    private fun place(c: String, k: Int, p: Long) {
        val l = shown[c]?.toMutableList() ?: return
        if (k !in l.indices) return
        l[k] = p
        shown[c] = l
    }

    private suspend fun roll(c: String, v: Int) {
        rolling = c
        repeat(7) { rollFace = Random.nextInt(1, 7); delay(60) }
        rolling = null
        face[c] = v
        if (c == me) myFace = v
    }

    private suspend fun play(e: LudoEvent, g: LudoGame) {
        val c = e.c
        when (e.t) {
            "roll" -> {
                roll(c, e.v.toInt())
                if (e.auto && c == me) say(c, "وقتت تموم شد و تاس خودکار ریخته شد")
            }
            "nomove" -> {
                // تاسی که حرکت نمی دهد: تاس «نه» می گوید، مهره ها می لرزند و برچسبی وسط صفحه می آید
                val allYard = shown[c].orEmpty().all { it < 0 }
                nope = Shake(++n, c)
                blocked = Blocked(++n, c, e.v.toInt(), allYard)
                say(c, (if (c == me) "${e.v.fd()} آوردی" else "${name(g, c)} ${e.v.fd()} آورد") + " ولی " +
                    (if (allYard) "واسه اومدن مهره ۶ لازمه" else "حرکتی نبود"))
                delay(1000)
            }
            "move" -> {
                val k = e.k.toInt()
                if (k !in shown[c].orEmpty().indices) return
                if (e.from < 0) {
                    place(c, k, 0)
                    delay(260)
                } else {
                    for (p in e.from + 1..e.to) {
                        place(c, k, p)
                        hops["$c:$k"] = (hops["$c:$k"] ?: 0) + 1
                        delay(150)
                    }
                }
                if (e.caps.isNotEmpty()) {
                    val (x, y) = posOf(c, e.to, k)
                    val victim = e.caps[0].substringBefore(':')
                    flash = Fx(++n, victim, x, y)
                    delay(160)
                    e.caps.forEach { cap -> cap.substringAfter(':').toIntOrNull()?.let { place(cap.substringBefore(':'), it, -1) } }
                    delay(300)
                    say(c, when {
                        c == me -> "مهرهٔ ${name(g, victim)} رو زدی! یه نوبت جایزه"
                        victim == me -> "${name(g, c)} مهره‌تو زد و فرستادش لونه"
                        else -> "${name(g, c)} مهرهٔ ${name(g, victim)} رو زد"
                    })
                } else if (e.fin) {
                    val (x, y) = SEAT.getValue(c).fin
                    flash = Fx(++n, c, x, y)
                    say(c, (if (c == me) "یه مهره رسوندی وسط" else "${name(g, c)} یه مهره رسوند وسط") + "! یه نوبت جایزه")
                } else if (e.from < 0) {
                    say(c, if (c == me) "۶ آوردی و مهره اومد تو" else "${name(g, c)} ۶ آورد و یه مهره آورد تو")
                }
                if (e.auto && c == me) say(c, "وقتت تموم شد و بهترین حرکتو خودمون زدیم")
            }
            "six3" -> say(c, (if (c == me) "سه بار ۶ آوردی" else "${name(g, c)} سه بار ۶ آورد") + " و نوبت سوخت")
            "leave" -> say(c, if (c == me) "از بازی اومدی بیرون" else name(g, c) + if (e.why == "timeout") " به‌خاطر غیبت حذف شد" else " از بازی رفت")
        }
    }
}

/** صفحهٔ بازی منچ (ludo.html و ludo.js) */
@Composable
fun LudoScreen(vm: AppViewModel, matchId: String) {
    val model = remember(matchId) { vm.table("ludo", matchId) }
    val play = remember(matchId) { LudoPlay() }
    val app = Aso.c
    val scope = rememberCoroutineScope()
    var leaving by remember { mutableStateOf(false) }
    val ask: () -> Unit = {
        if (play.game == null || play.over || play.cancelled) {
            vm.play.closeGame()
        } else {
            leaving = true
        }
    }
    BackHandler {
        if (leaving) {
            leaving = false
        } else {
            ask()
        }
    }
    // پرسش هر ۰٫۹ ثانیه؛ تا رویدادها پخش می شوند پرسش تازه ای نمی رود
    LaunchedEffect(model) {
        while (true) {
            if (!play.busy && !model.acting) model.poll()
            val v = model.view
            if (model.failed != null || v?.status == "over" || v?.status == "cancelled") break
            delay(900)
        }
    }
    LaunchedEffect(model) { snapshotFlow { model.view }.filterNotNull().collect { play.apply(it) } }

    Box(Modifier.fillMaxSize().background(TableBg)) {
        CompositionLocalProvider(LocalAso provides gameColors(app)) {
            Table(vm, model, play, onLeave = ask)
        }
        // گفتگوی سر میز: پیام ها بالای داک شناور می شوند
        TableChatLayer(model, QUICK, rest = 114.dp, enabled = play.game != null && !play.over && !play.cancelled)
        // پنجره ها رنگ های خود اپ را دارند (gc.css: gc-ui)
        CompositionLocalProvider(LocalAso provides app) {
            val v = play.view
            val g = play.game
            val home = { vm.play.closeGame() }
            val again = { vm.play.closeGame(); vm.play.openLobby("ludo") }
            when {
                model.failed != null && g == null -> InfoDlg("میز باز نشد", model.failed.orEmpty(), "یه میز بساز", again, home)
                play.cancelled -> InfoDlg("این میز بسته شد", "پشتیبانی این میزو بست و جام کسی کم نشد", "میز تازه", again, home)
                play.over && v != null && g != null -> LudoResult(v, g, play.me, again, home)
                leaving -> ExitDlg(
                    stake = v?.mode != "free",
                    stay = { leaving = false },
                    leave = { leaving = false; scope.launch { model.leave(); vm.play.closeGame() } },
                    home = { leaving = false; vm.play.closeGame() },
                )
            }
        }
    }
}

@Composable
private fun Table(vm: AppViewModel, model: TableModel, play: LudoPlay, onLeave: () -> Unit) {
    val scope = rememberCoroutineScope()
    val g = play.game
    val me = play.me
    val rot = ROT[me] ?: 0f
    var now by remember { mutableLongStateOf(System.currentTimeMillis()) }
    LaunchedEffect(Unit) { while (true) { now = System.currentTimeMillis(); delay(200) } }
    val left = if (play.deadlineAt > 0) ((play.deadlineAt - now).coerceAtLeast(0L).toFloat() / play.turnMs).coerceAtMost(1f) else 1f
    val over = g != null && (g.over || play.over)
    val turn = if (g != null && !over) g.turn else null
    val mine = turn != null && turn == me
    val phase = g?.phase
    // حالت داک: roll (تاس بنداز)، pick (مهره رو بزن) یا wait
    val state = when {
        mine && phase == "roll" -> "roll"
        mine && phase == "move" -> "pick"
        else -> "wait"
    }
    val canRoll = state == "roll" && !play.busy && !model.acting && play.rolling == null
    val picking = state == "pick" && !play.picked && !play.busy && !model.acting
    fun nameOf(c: String) = g?.players?.get(c)?.let { if (it.me) "تو" else it.name }.orEmpty()
    fun roll() {
        if (!canRoll) return
        play.rolling = me
        val before = model.view
        scope.launch {
            model.act("roll")
            if (model.view === before) play.rolling = null
        }
    }
    fun move(k: Int) {
        if (!picking) return
        play.picked = true
        val before = model.view
        scope.launch {
            model.act("move", k.toLong())
            if (model.view === before) play.picked = false
        }
    }

    Column(Modifier.fillMaxSize().statusBarsPadding().navigationBarsPadding()) {
        // ---------- نوار بالا: خروج، نوبت و زمان، صدا، راهنما ----------
        Row(Modifier.fillMaxWidth().heightIn(min = 52.dp).padding(start = 16.dp, end = 16.dp, top = 4.dp, bottom = 8.dp),
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            GlassBtn("back", "خروج از بازی", onClick = onLeave)
            val text = when {
                g == null -> "داریم وصل می‌شیم…"
                over -> "بازی تموم شد"
                mine -> "نوبت توئه"
                turn != null -> "نوبت ${nameOf(turn)}"
                else -> ""
            }
            TurnBar(if (over) g?.winner ?: me else turn, text, if (over) 0f else left, Modifier.weight(1f))
            val sound = vm.me?.sound != false
            GlassBtn(if (sound) "soundOn" else "soundOff", "صدا", dim = !sound) { vm.toggleSound() }
            GlassBtn("help", "قوانین بازی") { vm.openHelp("hLudo") }
        }
        // ---------- دو صندلی بالا، صفحه، دو صندلی پایین، خبر، داک تاس ----------
        BoxWithConstraints(Modifier.fillMaxWidth().weight(1f).padding(horizontal = 4.dp, vertical = 8.dp)) {
            // صفحه هر چه ارتفاع جا بدهد بزرگ می شود، بدون اسکرول (ludo.js: fitBoard)
            val side = minOf(maxWidth, maxHeight - 270.dp).coerceAtLeast(240.dp)
            Column(Modifier.fillMaxSize(), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                SeatRow(g, play, rot, top = true, turn, left)
                Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
                    Board(side, g, play, rot, picking) { move(it) }
                }
                SeatRow(g, play, rot, top = false, turn, left)
                Spacer(Modifier.weight(1f))
                FeedLine(play.feed)
                val (title, sub) = when {
                    g == null -> "داریم وصل می‌شیم…" to ""
                    over -> "بازی تموم شد" to ""
                    state == "roll" -> "نوبت توئه" to "بزن رو تاس تا بریزه"
                    state == "pick" -> "${(g.dice ?: 0L).fd()} آوردی" to "مهره‌ای که بالا پایین می‌پره رو بزن و دایرهٔ خط‌چین جاییه که می‌ره"
                    turn != null -> "نوبت ${nameOf(turn)}" to (if (g.players[turn]?.bot == true) "ربات داره فکر می‌کنه…" else "منتظریم حریف بازی کنه…")
                    else -> "" to ""
                }
                Dock(state, me, play, title, sub, model.unread, onRoll = { roll() }, onChat = { model.openChat(true) })
            }
        }
    }
}

/** دکمهٔ گرد شیشه ای نوار بالا (body.game .icon-btn) */
@Composable
private fun GlassBtn(icon: String, label: String, dim: Boolean = false, onClick: () -> Unit) {
    Box(
        Modifier.size(40.dp).alpha(if (dim) .8f else 1f).clip(CircleShape).background(GLASS).press(.94f, onClick = onClick)
            .semantics { contentDescription = label },
        contentAlignment = Alignment.Center,
    ) {
        Ic(icon, size = 22.dp, tint = if (dim) GAME_INK else ON_FILL)
    }
}

@Composable
internal fun GameIcon(icon: String, onClick: () -> Unit) {
    Box(Modifier.size(44.dp).clip(CircleShape).background(Aso.c.surface).press(.94f, onClick = onClick), contentAlignment = Alignment.Center) {
        Ic(icon, size = 22.dp, tint = Aso.c.ink)
    }
}

/** دایرهٔ رنگی با لبهٔ تیره پایینش (box-shadow: inset 0 -Npx 0) */
private fun DrawScope.insetDisc(fill: Color, edge: Color, band: Float) {
    val p = Path().apply { addOval(Rect(Offset.Zero, size)) }
    clipPath(p) {
        drawCircle(edge)
        drawCircle(fill, center = center - Offset(0f, band))
    }
}

/** نوار نوبت: دایرهٔ رنگ نوبت، متن و نوار زمانی که از چپ کوتاه می شود */
@Composable
private fun TurnBar(col: String?, text: String, left: Float, modifier: Modifier) {
    val hex = col?.let { HEX[it] } ?: Color.Transparent
    val deep = col?.let { DEEP[it] } ?: Color.Transparent
    val frac by animateFloatAsState(left.coerceIn(0f, 1f), tween(200, easing = LinearEasing), label = "time")
    Row(
        modifier.clip(CircleShape).background(GLASS).padding(start = 14.dp, end = 10.dp, top = 6.dp, bottom = 6.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Canvas(Modifier.size(26.dp)) { insetDisc(hex, deep, 3.dp.toPx()) }
        Text(text, Modifier.weight(1f), style = peyda(14f, 20f, 800), color = ON_FILL, maxLines = 1, overflow = TextOverflow.Ellipsis)
        Box(Modifier.size(44.dp, 8.dp).clip(RoundedCornerShape(8.dp)).background(Color.White.copy(alpha = .16f))) {
            Box(Modifier.align(AbsoluteAlignment.CenterRight).fillMaxHeight().fillMaxWidth(frac).background(hex))
        }
    }
}

// ---------- صندلی ها ----------
/** دو صندلی یک ردیف؛ جای هر رنگ همان گوشهٔ لانه اش بعد از چرخش صفحه (ludo.js: cornerOf) */
@Composable
private fun SeatRow(g: LudoGame?, play: LudoPlay, rot: Float, top: Boolean, turn: String?, left: Float) {
    fun colorAt(corner: Int): String? =
        if (g == null) null else g.order.firstOrNull { ((BASE[it] ?: 0) + (rot / 90).roundToInt()) % 4 == corner && g.players[it] != null }
    CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            val a = colorAt(if (top) 0 else 3)
            val b = colorAt(if (top) 1 else 2)
            SeatChip(g, a, right = false, turn = a != null && a == turn, left, play, Modifier.weight(1f))
            SeatChip(g, b, right = true, turn = b != null && b == turn, left, play, Modifier.weight(1f))
        }
    }
}

/** صندلی بازیکن: عکس با حلقهٔ زمان، نام، مهره های رسیده و تاس آخرش؛ صندلی راست برعکس چیده می شود */
@Composable
private fun SeatChip(g: LudoGame?, col: String?, right: Boolean, turn: Boolean, left: Float, play: LudoPlay, modifier: Modifier) {
    val p = if (g != null && col != null) g.players[col] else null
    if (g == null || col == null || p == null) {
        Spacer(modifier.height(58.dp))
        return
    }
    val hex = HEX.getValue(col)
    val done = (g.done[col] ?: 0L).toInt()
    val total = maxOf(g.pawns[col].orEmpty().size, done)
    val rolling = play.rolling == col && col != play.me
    val die = if (rolling) play.rollFace else play.face[col] ?: 0
    Row(
        modifier.height(58.dp).clip(CircleShape).background(if (turn) hex.copy(alpha = .26f) else GLASS)
            .border(2.dp, if (turn) hex else Color.Transparent, CircleShape)
            .padding(start = if (right) 14.dp else 8.dp, end = if (right) 8.dp else 14.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        val face = @Composable { TimerFace(p, hex, if (turn) left else 1f) }
        val dieView = @Composable {
            DieView(die, col, 30.dp, ghost = die == 0, rolling = rolling, ask = false, nope = play.nope?.takeIf { it.color == col }, rtl = false)
        }
        if (right) dieView() else face()
        Box(Modifier.weight(1f)) {
            CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Rtl) {
                Column(Modifier.fillMaxWidth(), horizontalAlignment = if (right) AbsoluteAlignment.Left else AbsoluteAlignment.Right,
                    verticalArrangement = Arrangement.spacedBy(2.dp)) {
                    Text((if (p.me) "خودت" else p.name) + if (p.out) " (رفت)" else "", style = peyda(13.5f, 18f, 800), color = ON_FILL,
                        maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Row(horizontalArrangement = Arrangement.spacedBy(3.dp)) {
                        repeat(total) { i -> Box(Modifier.size(9.dp).clip(CircleShape).background(if (i < done) hex else Color.White.copy(alpha = .22f))) }
                    }
                }
            }
        }
        if (right) face() else dieView()
    }
}

/** عکس بازیکن با حلقهٔ زمان نوبت (conic-gradient) */
@Composable
private fun TimerFace(p: LudoPlayer, ring: Color, t: Float) {
    val tt by animateFloatAsState(t.coerceIn(0f, 1f), tween(250, easing = LinearEasing), label = "t")
    Box(Modifier.size(44.dp), contentAlignment = Alignment.Center) {
        Canvas(Modifier.fillMaxSize()) {
            drawCircle(Color.White.copy(alpha = .18f))
            drawArc(ring, -90f, 360f * tt, useCenter = true)
        }
        Face(p.name, p.av, if (p.bot) null else p.pic, size = 44.dp, ring = Color.Transparent, bot = p.bot)
    }
}

// ---------- تاس ----------
/** تاس: رنگ بازیکن با خال های تیره؛ ghost کم رنگ؛ rolling تکان، ask بالا و پایین، nope لرزش و حلقهٔ قرمز */
@Composable
private fun DieView(face: Int, col: String, size: Dp, ghost: Boolean, rolling: Boolean, ask: Boolean, nope: Shake?, rtl: Boolean, gray: Boolean = false) {
    val big = size > 40.dp
    var c = if (ghost) Color.White.copy(alpha = .14f) else HEX.getValue(col)
    if (gray) {
        // filter: grayscale(.6) brightness(.9)
        val l = .2126f * c.red + .7152f * c.green + .0722f * c.blue
        c = Color((c.red + (l - c.red) * .6f) * .9f, (c.green + (l - c.green) * .6f) * .9f, (c.blue + (l - c.blue) * .6f) * .9f, c.alpha)
    }
    val shape = RoundedCornerShape(if (big) 16.dp else 9.dp)
    val pad = when {
        size >= 64.dp -> 11.dp
        big -> 9.dp
        else -> 5.dp
    }
    val margin = if (big) 1.5.dp else 1.dp
    val tr = rememberInfiniteTransition(label = "die")
    val spin: State<Float> = if (rolling) tr.animateFloat(0f, 1f, infiniteRepeatable(tween(140, easing = LinearEasing)), label = "roll") else remember { mutableFloatStateOf(0f) }
    val bob: State<Float> = if (ask) tr.animateFloat(0f, 1f, infiniteRepeatable(tween(450, easing = EaseInOut), RepeatMode.Reverse), label = "ask") else remember { mutableFloatStateOf(0f) }
    val shake = remember { Animatable(1f) }
    val ring = remember { Animatable(1f) }
    LaunchedEffect(nope?.id) {
        if (nope != null) {
            launch { shake.snapTo(0f); shake.animateTo(1f, tween(550, easing = LinearEasing)) }
            ring.snapTo(0f)
            ring.animateTo(1f, tween(1100, easing = LinearEasing))
        }
    }
    val danger = Color(0xFFFF6B7A)
    Box(
        Modifier.size(size)
            .graphicsLayer {
                val s = spin.value.let { 1f - abs(2f * it - 1f) }   // die-roll: ۱۶ درجه و ۳px بالا در نیمه
                val k = shake.value
                translationX = keyf(k, .2f to -7f, .4f to 6f, .6f to -4f, .8f to 2f) * density
                translationY = (-3f * s - 5f * bob.value) * density
                rotationZ = 16f * s - 7f * bob.value + keyf(k, .2f to -6f, .4f to 5f, .6f to -3f, .8f to 0f)
            }
            .drawBehind {
                // حلقهٔ قرمز «نه» دور تاس (nope-ring)
                val v = ring.value
                if (v < 1f) {
                    val a = if (v < .2f) v / .2f else 1f - (v - .2f) / .8f
                    val s = if (v < .2f) .8f + v else 1f + .15f * (v - .2f) / .8f
                    val out = 5.dp.toPx()
                    val sw = 3.dp.toPx()
                    val w = (this.size.width + 2 * out) * s
                    val tl = center - Offset(w / 2, w / 2)
                    drawRoundRect(danger.copy(alpha = a.coerceIn(0f, 1f)), tl + Offset(sw / 2, sw / 2), Size(w - sw, w - sw),
                        CornerRadius(20.dp.toPx() * s - sw / 2), style = Stroke(sw))
                }
            }
            .clip(shape).background(c).padding(pad),
    ) {
        Canvas(Modifier.fillMaxSize()) {
            val cell = this.size.width / 3f
            val r = cell / 2f - margin.toPx()
            val pip = if (ghost) Color.White.copy(alpha = .35f) else SURFACE
            val shadow = Color.Black.copy(alpha = if (ghost) .25f * .35f else .25f)
            PIPS[face]?.forEach { i ->
                val x = if (rtl) 2 - i % 3 else i % 3
                val o = Offset(cell * (x + .5f), cell * (i / 3 + .5f))
                drawCircle(pip, r, o)
                // سایهٔ داخلی بالای خال (inset 0 1.5px 1px)
                clipPath(Path().apply { addOval(Rect(o, r)) }) {
                    clipPath(Path().apply { addOval(Rect(o + Offset(0f, 1.5f * density), r)) }, ClipOp.Difference) { drawCircle(shadow, r, o) }
                }
            }
        }
    }
}

// ---------- صفحه ----------
/** اندازه های صفحه به پیکسل: --pad ۳، --gap ۱ و ۱۵ خانه */
private class Geo(width: Float, d: Float) {
    val pad = 3 * d
    val gap = 1 * d
    val cell = (width - 2 * pad - 14 * gap) / 15f
    fun o(i: Int) = pad + i * (cell + gap)
    /** لانه: شش خانه با فاصله ها، منهای حاشیهٔ ۱px */
    val yard = 6 * cell + 5 * gap - 2 * d
}

@Composable
private fun Board(side: Dp, g: LudoGame?, play: LudoPlay, rot: Float, picking: Boolean, onMove: (Int) -> Unit) {
    val shape = RoundedCornerShape(28.dp)
    val layer = side - 6.dp
    val cell = (side - 20.dp) / 15f
    val home = cell * 3 + 2.dp
    Box(
        // بدون برش: مهرهٔ ردیف بالا مثل مینی اپ می تواند از لبهٔ صفحه بیرون بزند
        Modifier.size(side).shadow(18.dp, shape, clip = false, ambientColor = Color.Black, spotColor = Color.Black).background(GAME_DEEP, shape)
            .border(1.dp, Color.White.copy(alpha = .07f), shape),
        contentAlignment = Alignment.Center,
    ) {
        val off = if (g == null) "" else ORDER.filter { g.players[it]?.out != false }.joinToString(",")
        BoardArt(rot, off, Modifier.fillMaxSize())
        val tc = if (g != null && !g.over && !play.over) g.turn else null
        if (tc != null) YardRing(tc, rot, Modifier.fillMaxSize())
        Ic("trophy", size = home * .34f * .7f, tint = COIN_DEEP, stroke = 2.4f)
        if (g != null) PawnLayer(g, play, rot, layer, picking, onMove)
        play.blocked?.let { b -> key(b.id) { BlockedTag(b) } }
    }
}

/** کاشی گرد با لبهٔ تیرهٔ پایینش (inset 0 -2px 0) */
private fun DrawScope.tile(l: Float, t: Float, s: Float, fill: Color, edge: Color, band: Float) {
    val r = CornerRadius(s * .3f)
    clipPath(Path().apply { addRoundRect(RoundRect(l, t, l + s, t + s, r)) }) {
        drawRect(edge, Offset(l, t), Size(s, s))
        drawRoundRect(fill, Offset(l, t - band), Size(s, s), r)
    }
}

private val OFF_PAINT = Paint().apply {
    alpha = .55f
    colorFilter = ColorFilter.colorMatrix(ColorMatrix().apply {
        setToSaturation(.25f)
        timesAssign(ColorMatrix().apply { setToScale(1.1f, 1.1f, 1.1f, 1f) })
    })
}

/** لانهٔ هر رنگ: مربع تک رنگ کوچک تر وسط جایش با چهار جای مهره؛ رنگ بی بازیکن کم رنگ (yard.off) */
private fun DrawScope.yard(g: Geo, col: String, off: Boolean) {
    val d = density
    val (yx, yy) = SEAT.getValue(col).yard
    val x0 = g.o(yx) + d
    val y0 = g.o(yy) + d
    val s = g.yard
    val draw = {
        val bl = x0 + s * .09f
        val bt = y0 + s * .09f
        val bs = s * .82f
        val r = CornerRadius(bs * .24f)
        clipPath(Path().apply { addRoundRect(RoundRect(bl, bt, bl + bs, bt + bs, r)) }) {
            drawRect(DEEP.getValue(col), Offset(bl, bt), Size(bs, bs))
            drawRoundRect(HEX.getValue(col), Offset(bl, bt - 4 * d), Size(bs, bs), r)
            clipPath(Path().apply { addRoundRect(RoundRect(bl, bt + 2 * d, bl + bs, bt + bs + 2 * d, r)) }, ClipOp.Difference) {
                drawRect(Color.White.copy(alpha = .3f), Offset(bl, bt), Size(bs, bs))
            }
        }
        SOCKETS.forEach { (sx, sy) ->
            val c = Offset(x0 + sx / 6f * s, y0 + sy / 6f * s)
            val rr = s * .105f
            clipPath(Path().apply { addOval(Rect(c, rr)) }) {
                drawCircle(Color.Black.copy(alpha = .16f), rr, c)
                clipPath(Path().apply { addOval(Rect(c + Offset(0f, 2 * d), rr)) }, ClipOp.Difference) { drawCircle(Color.Black.copy(alpha = .12f), rr, c) }
            }
        }
    }
    if (off) {
        drawIntoCanvas { it.saveLayer(Rect(x0, y0, x0 + s, y0 + s), OFF_PAINT) }
        draw()
        drawIntoCanvas { it.restore() }
    } else {
        draw()
    }
}

/** خانهٔ وسط: چهار مثلث رنگی و دایرهٔ تیرهٔ جام (جام خودش سرپا جدا کشیده می شود) */
private fun DrawScope.home(g: Geo) {
    val d = density
    val l = g.o(6)
    val s = 3 * g.cell + 2 * g.gap
    fun tri(ax: Float, ay: Float, bx: Float, by: Float, c: Color) = drawPath(Path().apply {
        moveTo(l + ax * s, l + ay * s); lineTo(l + bx * s, l + by * s); lineTo(l + s / 2, l + s / 2); close()
    }, c)
    clipPath(Path().apply { addRoundRect(RoundRect(l, l, l + s, l + s, CornerRadius(8 * d))) }) {
        tri(0f, 0f, 0f, 1f, HEX.getValue("blue"))
        tri(0f, 0f, 1f, 0f, HEX.getValue("red"))
        tri(1f, 0f, 1f, 1f, HEX.getValue("green"))
        tri(0f, 1f, 1f, 1f, HEX.getValue("yellow"))
        val c = Offset(l + s / 2, l + s / 2)
        drawCircle(Color.Black.copy(alpha = .18f), s * .17f, c + Offset(0f, 2 * d))
        drawCircle(SURFACE, s * .17f, c)
    }
}

/** صفحهٔ ۱۵×۱۵ (ludo.js: buildBoard) با چرخش رنگ من به پایین چپ */
@Composable
private fun BoardArt(rot: Float, off: String, modifier: Modifier) {
    Canvas(modifier) {
        val g = Geo(size.width, density)
        val offs = off.split(',')
        val band = 2 * density
        rotate(rot) {
            val startOf = ORDER.associateBy { SEAT.getValue(it).start }
            TRACK.forEachIndexed { i, (x, y) ->
                val col = startOf[i]
                val l = g.o(x)
                val t = g.o(y)
                if (col != null) tile(l, t, g.cell, HEX.getValue(col), DEEP.getValue(col), band) else tile(l, t, g.cell, PATH_FILL, PATH_EDGE, band)
                val icon = g.cell * .64f
                val il = l + (g.cell - icon) / 2
                val iy = t + (g.cell - icon) / 2
                if (col != null) {
                    withTransform({
                        rotate(SEAT.getValue(col).arrow, Offset(l + g.cell / 2, t + g.cell / 2))
                        translate(il, iy)
                        scale(icon / 24f, icon / 24f, Offset.Zero)
                    }) { drawPath(ARROW_PATH, Color.White) }
                } else if (i in SAFE) {
                    withTransform({ translate(il, iy); scale(icon / 24f, icon / 24f, Offset.Zero) }) { drawPath(STAR_PATH, PATH_EDGE) }
                }
            }
            for (col in ORDER) SEAT.getValue(col).lane.forEach { (x, y) -> tile(g.o(x), g.o(y), g.cell, HEX.getValue(col), DEEP.getValue(col), band) }
            for (col in ORDER) yard(g, col, col in offs)
            home(g)
        }
    }
}

/** حلقهٔ سفیدی که دور لانهٔ رنگ نوبت می تپد (yard-ring) */
@Composable
private fun YardRing(col: String, rot: Float, modifier: Modifier) {
    val t = rememberInfiniteTransition(label = "yard").animateFloat(0f, 1f, infiniteRepeatable(tween(550, easing = EaseInOut), RepeatMode.Reverse), label = "ring")
    Canvas(modifier) {
        val v = t.value
        if (v < .02f) return@Canvas
        val g = Geo(size.width, density)
        val (yx, yy) = SEAT.getValue(col).yard
        val bs = g.yard * .82f
        val bl = g.o(yx) + density + g.yard * .09f
        val bt = g.o(yy) + density + g.yard * .09f
        val sp = 3 * density * v
        rotate(rot) {
            drawRoundRect(Color.White.copy(alpha = .85f * v), Offset(bl - sp / 2, bt - sp / 2), Size(bs + sp, bs + sp), CornerRadius(bs * .24f + sp / 2), style = Stroke(sp))
        }
    }
}

// ---------- مهره ها ----------
private class Spot(val col: String, val k: Int, val x: Float, val y: Float, val s: Float)

@Composable
private fun PawnLayer(g: LudoGame, play: LudoPlay, rot: Float, layer: Dp, picking: Boolean, onMove: (Int) -> Unit) {
    val me = play.me
    val movable = if (picking) g.movable.map { it.toInt() } else emptyList()
    Box(Modifier.size(layer), contentAlignment = AbsoluteAlignment.TopLeft) {
        play.flash?.let { f -> key(f.id) { Flash(f, rot, layer) } }
        // جای مقصد هر مهرهٔ قابل حرکت: دایرهٔ خط چین
        val mine = play.shown[me].orEmpty()
        val dice = g.dice ?: 0L
        movable.forEach { k ->
            val p = mine.getOrNull(k) ?: return@forEach
            val np = if (p < 0) 0L else p + dice
            key("dest", k) { Dest(me, turn(posOf(me, np, k), rot), layer, star = np == 56L) { onMove(k) } }
        }
        // مهره های یک خانه کنار هم و کمی کوچک تر (ludo.js: layout)
        val groups = LinkedHashMap<String, MutableList<Triple<String, Int, Pair<Float, Float>>>>()
        for (col in g.order) play.shown[col]?.forEachIndexed { k, p ->
            val pos = posOf(col, p, k)
            groups.getOrPut("${(pos.first * 100).roundToInt()},${(pos.second * 100).roundToInt()}") { mutableListOf() }.add(Triple(col, k, pos))
        }
        val spots = ArrayList<Spot>()
        groups.values.forEach { list ->
            val n = list.size
            list.forEachIndexed { i, (col, k, pos) ->
                val off = if (n > 1) (i - (n - 1) / 2f) * .36f else 0f
                val r = turn((pos.first + off) to (pos.second + if (n > 1) .12f else 0f), rot)
                spots += Spot(col, k, r.first, r.second, if (n > 1) .8f else 1f)
            }
        }
        spots.forEach { s ->
            val can = s.col == me && s.k in movable
            key(s.col, s.k) {
                Pawn(s, layer, can, play.hops["${s.col}:${s.k}"] ?: 0, play.nope?.takeIf { it.color == s.col }?.id) { onMove(s.k) }
            }
        }
    }
}

/** شکل مهره (gc.js: pawn) به واحد viewBox ۴۰×۵۰؛ مرکز دیسک در ۷۴٪ ارتفاع */
private fun DrawScope.pawnArt(k: Float, hex: Color, deep: Color, glow: Boolean = false, crown: Boolean = false) {
    withTransform({ scale(k, k, Offset.Zero) }) {
        if (glow) {
            // drop-shadow(0 0 3px white .8) دور مهرهٔ قابل حرکت
            drawCircle(Brush.radialGradient(0f to Color.White.copy(alpha = .8f), .78f to Color.White.copy(alpha = .8f), 1f to Color.Transparent,
                center = Offset(20f, 38.5f), radius = 19.5f), 19.5f, Offset(20f, 38.5f))
        }
        drawOval(Color.Black.copy(alpha = .35f), Offset(7f, 44.9f), Size(26f, 5.2f))
        drawCircle(deep, 14f, Offset(20f, 40f))
        drawCircle(Color.White, 14f, Offset(20f, 37f))
        drawCircle(hex, 11f, Offset(20f, 37f))
        drawPath(PAWN_STAR, Color.White.copy(alpha = .92f))
        drawPath(PAWN_GLINT, Color.White.copy(alpha = .55f), style = Stroke(2.2f, cap = StrokeCap.Round))
        if (crown) {
            drawPath(CROWN_PATH, Color(0xFFFFC93C))
            drawPath(CROWN_PATH, Color(0xFFC98A00), style = Stroke(1.4f, join = StrokeJoin.Round))
        }
    }
}

/** مهره: قدم به قدم با پرش کوتاه جلو می رود؛ مهرهٔ قابل حرکت بالا و پایین می پرد و زیرش نور است */
@Composable
private fun Pawn(s: Spot, layer: Dp, can: Boolean, hop: Int, stuck: Int?, onClick: () -> Unit) {
    val w = layer * .082f
    val h = layer * .1025f
    val ax by animateDpAsState(at(s.x, layer), tween(140, easing = EaseOut), label = "x")
    val ay by animateDpAsState(at(s.y, layer), tween(140, easing = EaseOut), label = "y")
    val hopA = remember { Animatable(0f) }
    LaunchedEffect(hop) {
        if (hop > 0) {
            hopA.snapTo(0f)
            hopA.animateTo(1f, tween(70, easing = EaseOut))
            hopA.animateTo(0f, tween(70, easing = EaseOut))
        }
    }
    val shake = remember { Animatable(1f) }
    LaunchedEffect(stuck) { if (stuck != null) { shake.snapTo(0f); shake.animateTo(1f, tween(600, easing = LinearEasing)) } }
    val bounce: State<Float> = if (can) {
        rememberInfiniteTransition(label = "can").animateFloat(0f, 1f, infiniteRepeatable(tween(400, easing = EaseInOut), RepeatMode.Reverse), label = "b")
    } else {
        remember { mutableFloatStateOf(0f) }
    }
    val hex = HEX.getValue(s.col)
    val deep = DEEP.getValue(s.col)
    Box(
        Modifier.zIndex((s.y * 10).roundToInt() + if (can) 300f else 0f)
            .absoluteOffset(ax - w / 2, ay - h * .74f)
            .size(w, h)
            .graphicsLayer { scaleX = s.s; scaleY = s.s; transformOrigin = TransformOrigin(.5f, .74f) }
            .then(if (can) Modifier.clickable(interactionSource = null, indication = null, onClick = onClick) else Modifier)
            .semantics { contentDescription = "مهرهٔ ${s.k + 1}" },
    ) {
        if (can) {
            // نور زیر پایهٔ مهره روی خانه: با پرش مهره کوچک و کم رنگ می شود
            val mix = lerp(Color.White, hex, .65f)
            Canvas(Modifier.fillMaxSize().graphicsLayer {
                val b = bounce.value
                scaleX = 1f - .3f * b; scaleY = 1f - .3f * b; alpha = 1f - .5f * b
                transformOrigin = TransformOrigin(.5f, .95f)
            }) {
                val c = Offset(size.width * .5f, size.height * .95f)
                val rx = size.width * .61f
                val ry = size.height * .23f
                withTransform({ scale(1f, ry / rx, c) }) {
                    drawCircle(Brush.radialGradient(0f to Color.White, .5f to mix, 1f to Color.Transparent, center = c, radius = rx), rx, c)
                }
            }
        }
        Canvas(Modifier.fillMaxSize().graphicsLayer {
            translationY = -(.14f * bounce.value + .22f * hopA.value) * size.height
            translationX = keyf(shake.value, .2f to -.14f, .4f to .12f, .6f to -.08f, .8f to .04f) * size.width
        }) { pawnArt(size.width / 40f, hex, deep, glow = can) }
    }
}

/** مقصد مهره: دایرهٔ سفید با خط چین رنگ من؛ لمسش همان مهره را می برد */
@Composable
private fun Dest(col: String, pos: Pair<Float, Float>, layer: Dp, star: Boolean, onClick: () -> Unit) {
    val d = layer * .062f
    val appear = remember { Animatable(.4f) }
    LaunchedEffect(Unit) { appear.animateTo(1f, tween(200, easing = EaseOut)) }
    val hex = HEX.getValue(col)
    Box(
        Modifier.absoluteOffset(at(pos.first, layer) - d / 2, at(pos.second, layer) - d / 2).size(d)
            .graphicsLayer { scaleX = appear.value; scaleY = appear.value }
            .clickable(interactionSource = null, indication = null, onClick = onClick)
            .semantics { contentDescription = "مقصد این مهره" }
            .drawBehind {
                val r = size.minDimension / 2
                val sw = 3.dp.toPx()
                drawCircle(Color.White.copy(alpha = .75f), r)
                drawCircle(hex, r - sw / 2, style = Stroke(sw, pathEffect = PathEffect.dashPathEffect(floatArrayOf(sw * 2f, sw * 1.4f))))
            },
        contentAlignment = Alignment.Center,
    ) {
        if (star) Text("★", style = peyda(11f, 11f, 800), color = Color(0xFFF3F1E8))
    }
}

/** موج رنگی وقتی مهره زده می شود یا به خانه می رسد */
@Composable
private fun Flash(f: Fx, rot: Float, layer: Dp) {
    val t = remember { Animatable(0f) }
    LaunchedEffect(Unit) { t.animateTo(1f, tween(500, easing = EaseOut)) }
    val pos = turn(f.x to f.y, rot)
    val d = layer * .08f
    val hex = HEX[f.color] ?: Color.White
    Canvas(Modifier.absoluteOffset(at(pos.first, layer) - d / 2, at(pos.second, layer) - d / 2).size(d)) {
        val v = t.value
        val sw = 22.dp.toPx() * v
        if (v < 1f && sw > .5f) drawCircle(hex.copy(alpha = 1f - v), size.minDimension / 2 + sw / 2, style = Stroke(sw))
    }
}

/** برچسب وسط صفحه وقتی تاس حرکتی نمی دهد */
@Composable
private fun BlockedTag(b: Blocked) {
    val t = remember { Animatable(0f) }
    LaunchedEffect(Unit) { t.animateTo(1f, tween(1300, easing = LinearEasing)) }
    val hex = HEX.getValue(b.color)
    fun seg(v: Float, a: Float, z: Float, from: Float, to: Float) = from + (to - from) * EaseOut.transform(((v - a) / (z - a)).coerceIn(0f, 1f))
    Row(
        Modifier.zIndex(500f)
            .graphicsLayer {
                val v = t.value
                val sc = when {
                    v < .15f -> seg(v, 0f, .15f, .6f, 1.05f)
                    v < .25f -> seg(v, .15f, .25f, 1.05f, 1f)
                    else -> 1f
                }
                scaleX = sc; scaleY = sc
                alpha = when {
                    v < .15f -> seg(v, 0f, .15f, 0f, 1f)
                    v < .8f -> 1f
                    else -> seg(v, .8f, 1f, 1f, 0f)
                }
                translationY = if (v > .25f) seg(v, .25f, 1f, 0f, -.12f) * size.height else 0f
            }
            .clip(CircleShape).background(Color(0xE01E2235)).border(2.dp, hex, CircleShape)
            .padding(start = 16.dp, end = 8.dp, top = 6.dp, bottom = 6.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        DieView(b.v, b.color, 30.dp, ghost = false, rolling = false, ask = false, nope = null, rtl = true, gray = true)
        Text(if (b.allYard) "واسه اومدن تو ۶ لازمه" else "حرکتی نداری", style = peyda(14f, 20f, 800), color = ON_FILL, maxLines = 1)
    }
}

// ---------- خبر و داک ----------
/** یک خط خبر کوتاه بالای داک (feed1) */
@Composable
private fun FeedLine(f: Feed?) {
    Box(Modifier.fillMaxWidth().heightIn(min = 26.dp), contentAlignment = Alignment.Center) {
        if (f != null) key(f.id) {
            val t = remember { Animatable(0f) }
            LaunchedEffect(Unit) { t.animateTo(1f, tween(200, easing = EaseOut)) }
            Row(Modifier.padding(horizontal = 8.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Box(Modifier.size(9.dp).clip(CircleShape).background(HEX[f.color] ?: Color.Transparent))
                Text(
                    f.text,
                    Modifier.weight(1f, fill = false)
                        .graphicsLayer { alpha = t.value; translationY = (1f - t.value) * 14.dp.toPx(); translationX = -(1f - t.value) * size.width * .5f }
                        .clip(RoundedCornerShape(50)).background(GLASS).padding(horizontal = 12.dp, vertical = 2.dp),
                    style = peyda(12.5f, 20f, 800), color = ON_FILL, textAlign = TextAlign.Center,
                )
            }
        }
    }
}

/** داک پایین: تاس من، وضعیت و دکمهٔ گفتگو */
@Composable
private fun Dock(state: String, me: String, play: LudoPlay, title: String, sub: String, unread: Int, onRoll: () -> Unit, onChat: () -> Unit) {
    val shape = RoundedCornerShape(28.dp)
    Row(
        Modifier.fillMaxWidth().clip(shape).background(Color(0xBD10261E)).border(1.dp, Color.White.copy(alpha = .08f), shape).padding(12.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        val rolling = play.rolling == me
        Box(Modifier.clickable(interactionSource = null, indication = null, enabled = state == "roll", onClick = onRoll).semantics { contentDescription = "ریختن تاس" }) {
            DieView(if (rolling) play.rollFace else play.myFace, me, 64.dp, ghost = state == "wait" && !rolling, rolling = rolling,
                ask = state == "roll" && !rolling, nope = play.nope?.takeIf { it.color == me }, rtl = true)
        }
        Column(Modifier.weight(1f)) {
            Text(title, style = peyda(16f, 24f, 800), color = ON_FILL)
            if (sub.isNotEmpty()) Text(sub, style = peyda(12.5f, 20f), color = GAME_INK)
        }
        Box {
            Box(
                Modifier.size(56.dp).clip(CircleShape).background(Color(0xFFF5C451)).press(onClick = onChat).semantics { contentDescription = "گفتگوی میز" },
                contentAlignment = Alignment.Center,
            ) {
                Ic("chat", size = 24.dp, tint = Color(0xFF3A2A00))
            }
            ChatBadge(unread, Modifier.align(Alignment.TopEnd))
        }
    }
}

// ---------- پنجره ها (رنگ های اپ: gc-ui) ----------
/** پنجرهٔ وسط صفحه روی پرده (scrim center + sheet) */
@Composable
private fun Scrim(onDismiss: (() -> Unit)?, content: @Composable ColumnScope.() -> Unit) {
    val c = Aso.c
    val t = remember { Animatable(0f) }
    LaunchedEffect(Unit) { t.animateTo(1f, tween(220, easing = EaseOut)) }
    val shape = RoundedCornerShape(28.dp)
    Box(
        Modifier.fillMaxSize().background(if (c.dark) Color(0x9E000000) else Color(0x800E121A))
            .clickable(interactionSource = null, indication = null) { onDismiss?.invoke() }
            .statusBarsPadding().navigationBarsPadding().padding(16.dp),
        contentAlignment = Alignment.Center,
    ) {
        Column(
            Modifier.widthIn(max = 360.dp).fillMaxWidth()
                .graphicsLayer { alpha = t.value; val s = .92f + .08f * t.value; scaleX = s; scaleY = s }
                .shadow(16.dp, shape).background(c.surface)
                .clickable(interactionSource = null, indication = null) {}
                .verticalScroll(rememberScrollState())
                .padding(start = 20.dp, end = 20.dp, top = 24.dp, bottom = 20.dp),
            content = content,
        )
    }
}

@Composable
private fun DlgIcon(icon: String, warn: Boolean) {
    val c = Aso.c
    Box(
        Modifier.padding(bottom = 4.dp).size(64.dp).clip(CircleShape).background(if (warn) Color(0x29FF6B7A) else c.accTint),
        contentAlignment = Alignment.Center,
    ) {
        Ic(icon, size = 30.dp, tint = if (warn) c.danger else c.accDeep)
    }
}

/** پنجرهٔ خبر (میز بسته شد، میز باز نشد) */
@Composable
private fun InfoDlg(title: String, text: String, primary: String, onPrimary: () -> Unit, home: () -> Unit) {
    val c = Aso.c
    BackHandler(onBack = home)
    Scrim(null) {
        Column(Modifier.fillMaxWidth(), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(8.dp)) {
            DlgIcon("table", warn = false)
            Text(title, style = rokh(21f, 30f), color = c.ink, textAlign = TextAlign.Center)
            Text(text, Modifier.widthIn(max = 290.dp), style = peyda(14f, 24f), color = c.inkMuted, textAlign = TextAlign.Center)
            Row(Modifier.padding(top = 12.dp).fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Btn(primary, onPrimary, Modifier.weight(1f))
                Btn("خونه", home, Modifier.weight(1f), kind = BtnKind.Light)
            }
        }
    }
}

/** می‌خوای بری؟ (ludo.js: askExit) */
@Composable
private fun ExitDlg(stake: Boolean, stay: () -> Unit, leave: () -> Unit, home: () -> Unit) {
    val c = Aso.c
    Scrim(stay) {
        Column(Modifier.fillMaxWidth(), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(8.dp)) {
            DlgIcon("exit", warn = true)
            Text("می‌خوای بری؟", style = rokh(21f, 30f), color = c.ink, textAlign = TextAlign.Center)
            Text(
                if (stake) "بری یعنی همین دستو باختی و میز بی تو ادامه می‌ده" else "این دست واسه تو تموم می‌شه و بقیه بی تو ادامه می‌دن",
                Modifier.widthIn(max = 290.dp), style = peyda(14f, 24f), color = c.inkMuted, textAlign = TextAlign.Center,
            )
            Text(
                if (stake) "بازی رتبه‌ایه و رفتنت یعنی باخت و کم شدن جام" else "بازی دوستانه‌ست و چیزی از دست نمی‌دی",
                Modifier.padding(top = 4.dp).fillMaxWidth().clip(RoundedCornerShape(16.dp)).background(c.coinTint).padding(horizontal = 12.dp, vertical = 10.dp),
                style = peyda(13.5f, 20f, 700), color = c.coinText, textAlign = TextAlign.Center,
            )
            Row(Modifier.padding(top = 12.dp).fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Btn("ادامهٔ بازی", stay, Modifier.weight(1f))
                Btn("خروج", leave, Modifier.weight(1f), kind = BtnKind.DangerSoft, icon = "exit")
            }
            Btn("فعلاً برو خونه سر میز می‌مونم", home, Modifier.padding(top = 8.dp).fillMaxWidth(), kind = BtnKind.Light, icon = "home")
            Text(
                "میز تو صفحهٔ خونه می‌مونه و با یه لمس برمی‌گردی\nتا نیستی نوبتات خودکار بازی می‌شه" +
                    if (stake) "\nتو بازی رتبه‌ای سه نوبت غیبت پشت‌سرهم یعنی باخت" else "",
                Modifier.padding(top = 8.dp), style = peyda(12f, 19f), color = c.inkMuted, textAlign = TextAlign.Center,
            )
        }
    }
}

/** مهرهٔ برنده با تاج که آرام بالا و پایین می رود */
@Composable
private fun CrownPawn(col: String, crown: Boolean) {
    val b = rememberInfiniteTransition(label = "bob").animateFloat(0f, 1f, infiniteRepeatable(tween(1000, easing = EaseInOut), RepeatMode.Reverse), label = "b")
    Canvas(Modifier.size(104.dp, 132.dp).graphicsLayer { translationY = -6.dp.toPx() * b.value }) {
        val k = minOf(size.width / 40f, size.height / 54f)
        withTransform({ translate((size.width - 40f * k) / 2f, (size.height - 54f * k) / 2f + 4f * k) }) {
            pawnArt(k, HEX[col] ?: Color(0xFFFFC531), DEEP[col] ?: Color(0xFFC98A00), crown = crown)
        }
    }
}

@Composable
private fun RowScope.Fact(v: String, label: String) {
    val c = Aso.c
    Column(Modifier.weight(1f).clip(RoundedCornerShape(16.dp)).background(c.surfaceSunk).padding(8.dp), horizontalAlignment = Alignment.CenterHorizontally) {
        Text(v, style = peyda(18f, 24f, 800), color = c.ink)
        Text(label, style = peyda(12f, 24f), color = c.inkMuted, textAlign = TextAlign.Center)
    }
}

/** جام و سکهٔ بازی رتبه ای (gc.js: rankResult) */
@Composable
private fun RankResult(r: MatchResult?, ended: Boolean) {
    val c = Aso.c
    if (ended) {
        Text("بازی بی‌نتیجه بسته شد و جامت دست نخورد", style = peyda(14.5f, 24f), color = c.ink, textAlign = TextAlign.Center)
        return
    }
    val cups = r?.cups ?: 0L
    val coins = r?.coins ?: 0L
    Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.CenterVertically) {
            val tint = if (cups < 0) c.inkMuted else c.coinText
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                Ic("trophy", size = 24.dp, tint = tint)
                val sign = if (cups > 0) "+" else if (cups < 0) "−" else ""
                Text("⁦$sign${abs(cups).fa()}⁩ جام", style = peyda(22f, 28f, 800), color = tint)
            }
            if (coins > 0) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    Coin(27.dp)
                    Text("⁦+${coins.fa()}⁩", style = peyda(22f, 28f, 800), color = c.coinText)
                }
            }
        }
        val note = if (r?.won == true) {
            if (coins > 0) "سکه‌ش ریخت تو کیفت 🎉" else "جامش مال تو دمت گرم"
        } else if (cups != 0L) "فدای سرت دست بعد جبران کن" else "جامی نداشتی که کم بشه"
        val league = r?.league
        Text(buildAnnotatedString {
            append(note)
            if (r != null && league != null) {
                append("\n")
                withStyle(SpanStyle(fontWeight = FontWeight.ExtraBold)) { append("لیگ $league") }
                append(" · ${r.totalCups.fa()} جام")
            }
        }, style = peyda(14.5f, 24f), color = c.ink, textAlign = TextAlign.Center)
    }
}

/** پایان بازی: مهرهٔ تاج دار، برنده، جام و سکه، آمار بازی و دو دکمه (ludo.js: over) */
@Composable
private fun LudoResult(v: MatchView, g: LudoGame, me: String, again: () -> Unit, home: () -> Unit) {
    val c = Aso.c
    val w = g.winner
    val won = w == me
    val secs = remember { (System.currentTimeMillis() / 1000.0 - g.started).toLong().coerceAtLeast(0L) }
    BackHandler(onBack = home)
    Scrim(null) {
        Column(Modifier.fillMaxWidth(), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(12.dp)) {
            CrownPawn(w ?: me, crown = w != null)
            val wn = w?.let { g.players[it]?.let { p -> if (p.me) "تو" else p.name } }.orEmpty()
            Text(withIds(if (won) "بردی!" else if (w != null) "$wn برد" else "بازی تموم شد", listOf(wn)), style = rokh(30f, 38f), color = c.ink, textAlign = TextAlign.Center)
            when (v.mode) {
                "free" -> Text(
                    if (won) "بازی دوستانه بود و جام و سکه نداشت ولی دمت گرم" else "بازی دوستانه بود و چیزی از دست ندادی",
                    style = peyda(14.5f, 24f), color = c.inkMuted, textAlign = TextAlign.Center,
                )
                "ranked" -> RankResult(v.result, ended = w == null)
                else -> Text(
                    if (v.result?.won == true) "این میز از قبل امتیازی بود و جایزه‌ش با امتیازای قدیمیت برمی‌گرده به کیف عبور" else "این میز از قبل امتیازی بود فدای سرت",
                    style = peyda(14.5f, 24f), color = c.ink, textAlign = TextAlign.Center,
                )
            }
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Fact(g.caps.fd(), "مهره زدی")
                Fact(g.sixes.fd(), "بار ۶ آوردی")
                Fact("${(secs / 60).fd()}:${(secs % 60 / 10).fd()}${(secs % 10).fd()}", "مدت بازی")
            }
        }
        Spacer(Modifier.height(20.dp))
        Btn("یه دست دیگه", again, Modifier.fillMaxWidth(), icon = "dice")
        Spacer(Modifier.height(20.dp))
        Btn("خونه", home, Modifier.fillMaxWidth(), kind = BtnKind.Light)
    }
}
