package dezhcode.asotas.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxScope
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.absoluteOffset
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.AbsoluteAlignment
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.RadialGradientShader
import androidx.compose.ui.graphics.ShaderBrush
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.withTransform
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.graphics.vector.PathParser
import androidx.compose.ui.graphics.vector.rememberVectorPainter
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp

/** گرادیان شعاعی بیضی (radial-gradient(ellipse w h at x y, ...)) */
fun ellipseBrush(cx: Float, cy: Float, rx: Float, vararg stops: Pair<Float, Color>) = object : ShaderBrush() {
    override fun createShader(size: Size) = RadialGradientShader(
        center = Offset(size.width * cx, size.height * cy), radius = size.width * rx,
        colors = stops.map { it.second }, colorStops = stops.map { it.first },
    )
}

// ---------- ماهوت میز حکم (cards.css: tbl-a/b/c و .felt) ----------
private val FELT = mapOf(
    "a" to listOf(Color(0xFF2F8F4E), Color(0xFF1E6B3A), Color(0xFF0F3F1D)),
    "b" to listOf(Color(0xFF7E2737), Color(0xFF5A1A25), Color(0xFF2A0A10)),
    "c" to listOf(Color(0xFF157888), Color(0xFF0E5563), Color(0xFF062A33)),
)

@Composable
fun Felt(look: String, modifier: Modifier = Modifier, content: @Composable BoxScope.() -> Unit = {}) {
    val f = FELT[look] ?: FELT.getValue("a")
    Box(
        modifier
            .background(ellipseBrush(.5f, .46f, .85f, 0f to f[0], .55f to f[1], 1f to f[2]))
            .background(ellipseBrush(.5f, .47f, .62f, 0f to Color(0x29FFECBE), .72f to Color.Transparent))
            .then(
                if (look == "b") Modifier.border(7.dp, Color(0xFF4A2C1A)).padding(7.dp).border(2.dp, Color(0xFF2B170C)).padding(2.dp).border(1.dp, Color(0x8CD6B254))
                else Modifier.border(1.5.dp, Color.White.copy(alpha = .12f)),
            ),
        content = content,
    )
}

// ---------- ورق (رو و پشت) به طرح هر ست (cards.css) ----------
private fun paperOf(look: String) = if (look == "b") Color(0xFFF7EEDB) else Color.White
private fun redOf(look: String) = when (look) { "b" -> Color(0xFFA51A2C); "c" -> Color(0xFFE0263E); "m" -> Color(0xFFD62839); else -> Color(0xFFD7263D) }
private fun inkOf(look: String) = when (look) { "b" -> Color(0xFF2B1C12); "c" -> Color(0xFF141A26); else -> Color(0xFF1C2235) }

/** روی ورق: ارزش و خال گوشه و خال بزرگ وسط */
@Composable
fun CardFace(rank: String, suit: String, red: Boolean, w: Dp, look: String = "a", modifier: Modifier = Modifier) {
    val ink = if (red) redOf(look) else inkOf(look)
    val shape = RoundedCornerShape(w * .1f)
    Box(modifier.size(w, w * 1.406f).shadow(4.dp, shape).clip(shape).background(paperOf(look))
        .then(if (look == "b") Modifier.padding(w * .05f).border(1.dp, Color(0xFFC9A54A), RoundedCornerShape(w * .045f)) else Modifier)) {
        Column(Modifier.align(AbsoluteAlignment.TopLeft).padding(w * .07f), horizontalAlignment = Alignment.CenterHorizontally) {
            Text(rank, style = rokh(w.value * .3f, w.value * .32f), color = ink)
            Text(suit, style = peyda(w.value * .24f, w.value * .26f, 700), color = ink)
        }
        Text(suit, style = peyda(w.value * .6f, w.value * .64f, 700), color = ink, modifier = Modifier.align(Alignment.Center))
    }
}

/** پشت ورق */
@Composable
fun CardBack(look: String, w: Dp, modifier: Modifier = Modifier) {
    val shape = RoundedCornerShape(w * .075f)
    val base = Modifier.size(w, w * 1.406f).shadow(4.dp, shape).clip(shape)
    when (look) {
        "m" -> Box(modifier.then(base).border(w * .0625f, Color.White, shape).background(Brush.linearGradient(0f to Color(0xFFF5C451), .5f to Color(0xFFF5C451), .5f to Color(0xFF1A7A47), 1f to Color(0xFF1A7A47))))
        "c" -> Box(modifier.then(base).background(Brush.linearGradient(listOf(Color(0xFF2B7DF0), Color(0xFF0E4FB3)))).border(w * .055f, Color.White, shape), contentAlignment = Alignment.Center) {
            Text("AsoTas", style = peyda(w.value * .13f, w.value * .17f, 800), color = Color(0xFF3D2600),
                modifier = Modifier.clip(RoundedCornerShape(99.dp)).background(Color(0xFFFFC43B)).padding(horizontal = w * .06f))
        }
        else -> {
            val b = look == "b"
            val bg = if (b) Color(0xFF6A1B28) else Color(0xFF1D3461)
            val line = if (b) Color(0x66D6B254) else Color(0x2BFFFFFF)
            Box(
                modifier.then(base).background(bg).drawBehind {
                    val step = 6.dp.toPx()
                    var x = -size.height
                    while (x < size.width) {
                        drawLine(line, Offset(x, size.height), Offset(x + size.height, 0f), 1.2f)
                        drawLine(line, Offset(x, 0f), Offset(x + size.height, size.height), 1.2f)
                        x += step
                    }
                }.border(w * .055f, if (b) Color(0xFFF3E6C8) else Color.White, shape),
                contentAlignment = Alignment.Center,
            ) {
                Box(Modifier.size(w * .32f).clip(RoundedCornerShape(99.dp)).background(if (b) Color(0xFFD6B254) else Color(0xFFFBF7EE)).padding(w * .1f)
                    .clip(RoundedCornerShape(99.dp)).background(bg))
            }
        }
    }
}

@Composable
private fun BoxScope.At(leftPct: Float, topPct: Float, rot: Float, wFrame: Dp, hFrame: Dp, content: @Composable () -> Unit) {
    Box(Modifier.align(AbsoluteAlignment.TopLeft).absoluteOffset(wFrame * leftPct, hFrame * topPct).rotate(rot)) { content() }
}

/** پیش نمایش میز یا ورق حکم در فروشگاه و کلکسیون (tablePv و cardsPv در shop.html) */
@Composable
fun SkinPreview(kind: String, look: String, table: String, cards: String, modifier: Modifier, big: Boolean = false, frameW: Dp = if (big) 320.dp else 100.dp) {
    val w = if (big) 72.dp else 40.dp
    val h = if (big) 190.dp else 98.dp
    val shape = RoundedCornerShape(if (big) 20.dp else 14.dp)
    Felt(if (kind == "table") look else table, modifier.clip(shape)) {
        if (kind == "table") {
            At(.22f, .14f, -14f, frameW, h) { CardFace("A", "♠", false, w, cards) }
            At(.44f, .18f, 9f, frameW, h) { CardFace("K", "♥", true, w, cards) }
            At(.30f, .36f, -3f, frameW, h) { CardFace("Q", "♦", true, w, cards) }
        } else {
            At(.08f, .16f, -12f, frameW, h) { CardBack(look, w) }
            At(.31f, .12f, -2f, frameW, h) { CardFace("K", "♥", true, w, look) }
            At(.54f, .16f, 10f, frameW, h) { CardFace("A", "♠", false, w, look) }
        }
    }
}

// ---------- کاور پروفایل (gc.css: .cover-gc) و نشان AsoTas ----------
private val MarkVector: ImageVector by lazy {
    val n = { d: String -> PathParser().parsePathString(d).toNodes() }
    ImageVector.Builder("mark", 48.dp, 48.dp, 48f, 48f).apply {
        addPath(n(circle(24f, 24f, 21.5f)), fill = null, stroke = SolidColor(Color.Black), strokeLineWidth = 2.4f)
        addPath(n(circle(24f, 24f, 17f)), fill = null, stroke = SolidColor(Color.Black), strokeLineWidth = 1f, strokeAlpha = .55f)
        addPath(n("M24 13.5C21 18.1 16 20.8 16 25c0 2.6 2 4.4 4.3 4.4 1.3 0 2.5-.6 3.1-1.5-.3 2-1.1 3.6-2.6 5.1h6.4c-1.5-1.5-2.3-3.1-2.6-5.1.6.9 1.8 1.5 3.1 1.5 2.3 0 4.3-1.8 4.3-4.4C32 20.8 27 18.1 24 13.5z"),
            fill = SolidColor(Color.Black))
    }.build()
}

@Composable
fun Cover(id: String, modifier: Modifier = Modifier, mark: Boolean = false) {
    Box(
        modifier
            .background(ellipseBrush(.15f, 0f, 1.3f, 0f to Color(0xFF2C8068), .42f to Color(0xFF185040), 1f to Color(0xFF0D2A21)))
            .background(ellipseBrush(.88f, 0f, .7f, 0f to Color(0x42F5C451), .62f to Color.Transparent)),
    ) {
        if (mark && id == "gc") {
            Row(Modifier.align(Alignment.TopStart).padding(start = 16.dp, top = 14.dp), verticalAlignment = Alignment.CenterVertically) {
                Image(rememberVectorPainter(MarkVector), null, Modifier.size(34.dp), colorFilter = androidx.compose.ui.graphics.ColorFilter.tint(Color(0xFFF5C451)))
                Text("AsoTas", style = rokh(17f, 24f), color = Color(0xFFF7E3AE), modifier = Modifier.padding(start = 8.dp))
            }
        }
    }
}

@Composable
fun FillBox(color: Color, modifier: Modifier) = Box(modifier.fillMaxSize().background(color))

// ---------- آواتار کارتونی ربات ها (gc.js: avatar) ----------
private fun svg(d: String) = PathParser().parsePathString(d).toPath()
private val BOT_BODY = svg("M8 64c2-12 12-19 24-19s22 7 24 19z")
private val BOT_HAIR_SHORT = svg("M17 29c0-10 7-16 15-16s15 6 15 16c-3-5-8-8-15-8s-12 3-15 8z")
private val BOT_HAIR_LONG = svg("M15 32c0-12 7-19 17-19s17 7 17 19v12c-3 0-5-3-5-7 0-8-2-12-12-13-10 1-12 5-12 13 0 4-2 7-5 7z")
private val BOT_CAP = svg("M15 28c0-9 8-15 17-15s17 6 17 15z")
private val BOT_MOUTH = svg("M26 37c3 3 9 3 12 0")
private val BOT_SKIN = longArrayOf(0xFFF6C9A0, 0xFFE8B48A, 0xFFD49A6A, 0xFFF2D3B3)
private val BOT_HAIR = longArrayOf(0xFF3B2A20, 0xFF1E1A18, 0xFF8A5A2B, 0xFFB9B9B9)
private val BOT_SHIRT = longArrayOf(0xFF2F7BF6, 0xFFEF4136, 0xFF2FB24C, 0xFFFFC226, 0xFF7C5CE0)

/** چهرهٔ کارتونی ربات با seed = av بازیکن (همان رنگ و مو و کلاه مینی اپ) */
@Composable
fun BotAvatar(seed: Long, modifier: Modifier = Modifier) {
    Canvas(modifier) {
        val k = size.width / 64f
        val skin = Color(BOT_SKIN[(seed % 4).toInt()])
        val hair = Color(BOT_HAIR[((seed shr 2) % 4).toInt()])
        val shirt = Color(BOT_SHIRT[(seed % 5).toInt()])
        withTransform({ scale(k, k, Offset.Zero) }) {
            drawRect(Color(0xFFCFE9FF), size = Size(64f, 64f))
            drawPath(BOT_BODY, shirt)
            drawCircle(skin, 15f, Offset(32f, 31f))
            when ((seed % 3).toInt()) {
                0 -> drawPath(BOT_HAIR_SHORT, hair)
                1 -> drawPath(BOT_HAIR_LONG, hair)
                else -> {
                    drawPath(BOT_CAP, shirt)
                    drawRoundRect(shirt, Offset(30f, 24f), Size(24f, 5.5f), CornerRadius(2.7f))
                    drawRect(Color.Black.copy(alpha = .15f), Offset(15f, 26f), Size(34f, 3f))
                }
            }
            drawCircle(Color(0xFF222222), 2.1f, Offset(26.5f, 31f))
            drawCircle(Color(0xFF222222), 2.1f, Offset(37.5f, 31f))
            drawPath(BOT_MOUTH, Color(0xFF7A3B2A), style = Stroke(2.2f, cap = StrokeCap.Round))
            drawCircle(Color(0x38EF4136), 2.4f, Offset(22f, 35f))
            drawCircle(Color(0x38EF4136), 2.4f, Offset(42f, 35f))
        }
    }
}
