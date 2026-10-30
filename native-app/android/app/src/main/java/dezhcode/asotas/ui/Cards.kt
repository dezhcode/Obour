package dezhcode.asotas.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.size
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.RoundRect
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.clipPath
import androidx.compose.ui.graphics.drawscope.rotate
import androidx.compose.ui.graphics.drawscope.withTransform
import androidx.compose.ui.graphics.vector.PathParser
import androidx.compose.ui.text.TextMeasurer
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.drawText
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.unit.Dp
import kotlin.math.abs
import kotlin.math.cos
import kotlin.math.sin

// ورق واقعی حکم (static/cards.js و cards.css): خال چینی چاپی ۲ تا ۱۰، آس، سرباز و بی بی و شاه دوسر،
// پشت ورق؛ طرح ها: a کلاسیک، b کافه شب، c AsoTas، m مدرن (درشت خوان)، d رنگ تمام.
// همه چیز به واحد em (عرض ورق) کشیده می شود؛ ورق ۱ در ۱.۴۰۶ em است.

private fun p(d: String) = PathParser().parsePathString(d).toPath()
/** خال ها (۲۴×۲۴): پیک، دل، خشت، گشنیز */
private val SP = listOf(
    p("M12 2C9 6.6 4 9.3 4 13.5c0 2.6 2 4.4 4.3 4.4 1.3 0 2.5-.6 3.1-1.5-.3 2-1.1 3.6-2.6 5.1h6.4c-1.5-1.5-2.3-3.1-2.6-5.1.6.9 1.8 1.5 3.1 1.5 2.3 0 4.3-1.8 4.3-4.4C20 9.3 15 6.6 12 2z"),
    p("M12 21.3C7.3 17.5 2.8 14 2.8 9.1 2.8 6.1 5.1 3.8 8 3.8c1.7 0 3.1.8 4 2.2.9-1.4 2.3-2.2 4-2.2 2.9 0 5.2 2.3 5.2 5.3 0 4.9-4.5 8.4-9.2 12.2z"),
    p("M12 1.8 19.6 12 12 22.2 4.4 12z"),
    p("M12 2.6a4.4 4.4 0 0 0-4.3 5.4A4.4 4.4 0 1 0 9.5 16.4c.9 0 1.7-.3 2.2-.7-.3 2.1-1.1 3.8-2.6 5.3h5.8c-1.5-1.5-2.3-3.2-2.6-5.3.5.4 1.3.7 2.2.7a4.4 4.4 0 1 0 1.8-8.4A4.4 4.4 0 0 0 12 2.6z"),
)
private val ACE_RING = p("M12 1.2a10.8 10.8 0 1 0 0 21.6 10.8 10.8 0 1 0 0-21.6zm0 1.4a9.4 9.4 0 1 1 0 18.8 9.4 9.4 0 1 1 0-18.8z")
private val EMB = mapOf(
    11 to p("M3 7.5l4.6 4.2L12 4.5l4.4 7.2L21 7.5l-1.7 9H4.7zM4.7 18h14.6v2H4.7z"),
    10 to p("M12 3.6a1.7 1.7 0 1 1 0 3.4 1.7 1.7 0 0 1 0-3.4zM5.2 6.6a1.5 1.5 0 1 1 0 3 1.5 1.5 0 0 1 0-3zm13.6 0a1.5 1.5 0 1 1 0 3 1.5 1.5 0 0 1 0-3zM5.6 16.5l-.6-5.4 3.9 2.9L12 8.6l3.1 5.4 3.9-2.9-.6 5.4zM5.6 18h12.8v2H5.6z"),
    9 to p("M12 3l7 3v5c0 4.6-3 8.3-7 10-4-1.7-7-5.4-7-10V6z"),
)
val CARD_RANKS = listOf("2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A")

/** جای خال ها (ستون ۰ تا ۲، ردیف ۰ تا ۴ از بالا) برای ۲ تا ۱۰ */
private val LAY = listOf(
    listOf(1f to 0f, 1f to 4f), listOf(1f to 0f, 1f to 2f, 1f to 4f), listOf(0f to 0f, 2f to 0f, 0f to 4f, 2f to 4f),
    listOf(0f to 0f, 2f to 0f, 1f to 2f, 0f to 4f, 2f to 4f), listOf(0f to 0f, 2f to 0f, 0f to 2f, 2f to 2f, 0f to 4f, 2f to 4f),
    listOf(0f to 0f, 2f to 0f, 1f to 1f, 0f to 2f, 2f to 2f, 0f to 4f, 2f to 4f),
    listOf(0f to 0f, 2f to 0f, 1f to 1f, 0f to 2f, 2f to 2f, 1f to 3f, 0f to 4f, 2f to 4f),
    listOf(0f to 0f, 2f to 0f, 0f to 1.5f, 2f to 1.5f, 1f to 2f, 0f to 2.5f, 2f to 2.5f, 0f to 4f, 2f to 4f),
    listOf(0f to 0f, 2f to 0f, 1f to .75f, 0f to 1.5f, 2f to 1.5f, 0f to 2.5f, 2f to 2.5f, 1f to 3.25f, 0f to 4f, 2f to 4f),
)
private val COLX = floatArrayOf(.28f, .50f, .72f)

// ---------- سرباز (۹)، بی بی (۱۰) و شاه (۱۱): نیم تنه در قاب ۱۰۰×۱۴۰، نیمهٔ پایین قرینه ----------
private val HAT = mapOf(
    9 to p("M36 23C37 14 63 14 64 23Z M61 17C68 9 74 11 71 18 69 15 66 15 63 19Z"),
    10 to p("M38 22C40 14 60 14 62 22Z M50 9a3 3 0 1 0 .01 0Z M42 15a1.8 1.8 0 1 0 .01 0Z M58 15a1.8 1.8 0 1 0 .01 0Z"),
    11 to p("M37 23L39 9 44.5 16 50 7 55.5 16 61 9 63 23Z"),
)
private val HAIR = mapOf(
    9 to p("M39 29C39 20 61 20 61 29 58 24 42 24 39 29Z"),
    10 to p("M38 31C36 18 64 18 62 31 64 40 60 46 58 47 59 38 58 30 57 27 52 25 48 25 43 27 42 30 41 38 42 47 40 46 36 40 38 31Z"),
    11 to p("M39 32C40 45 60 45 61 32 57 38 43 38 39 32Z M39 28C39 21 61 21 61 28 58 24 42 24 39 28Z"),
)
private val ITEM = mapOf(
    9 to p("M23 14h1.8v46H23Z M23.9 10l6 5-6 5Z"),
    10 to p("M75.1 34h1.8v26h-1.8Z M76 22a5 5 0 1 0 .01 0Z"),
    11 to p("M23.1 18h1.8v42h-1.8Z M19 23h10v2.2H19Z M23.1 12l.9-4 .9 4Z"),
)
private val C_BODY = p("M16 70C18 53 33 46 50 46 67 46 82 53 84 70Z")
private val C_ROBE = p("M24 70C26 60 34 54 44 52L50 70Z")
private val C_GS = p("M43 47 50 66 57 47")
private val C_MOUTH = p("M47.5 35Q50 36.6 52.5 35")

/** رنگ های هر طرح (cards.css) */
private class Look(
    val paper: Color, val edge: Color, val k: Color, val rd: Color, val gold: Color,
    val serif: Boolean, val ixs: Float, val pip: Float, val gloss: Float, val radius: Float,
)
private val LOOKS = mapOf(
    "a" to Look(Color(0xFFFBF7EE), Color(0xFFD9D1BF), Color(0xFF17191F), Color(0xFFC21F32), Color(0xFFB8912F), true, .17f, .17f, .42f, .075f),
    "b" to Look(Color(0xFFF7EEDB), Color(0xFFCDBF9C), Color(0xFF2B1C12), Color(0xFFA51A2C), Color(0xFFB08A2E), true, .16f, .17f, .42f, .075f),
    "c" to Look(Color.White, Color(0xFFD6DCE5), Color(0xFF141A26), Color(0xFFE0263E), Color(0xFFE8A400), false, .23f, .2f, .28f, .075f),
)

private fun isRedSuit(s: Int) = s == 1 || s == 2

/** گرادیان خطی با زاویهٔ CSS (۰ = رو به بالا، ۹۰ = رو به راست) روی جعبهٔ w×h */
private fun cssLinear(deg: Float, w: Float, h: Float, vararg stops: Pair<Float, Color>, ox: Float = 0f, oy: Float = 0f): Brush {
    val a = Math.toRadians(deg.toDouble())
    val dx = sin(a).toFloat()
    val dy = -cos(a).toFloat()
    val len = abs(w * dx) + abs(h * dy)
    val c = Offset(ox + w / 2, oy + h / 2)
    return Brush.linearGradient(*stops, start = c - Offset(dx, dy) * (len / 2), end = c + Offset(dx, dy) * (len / 2))
}

/** سایهٔ ورق روی میز (لایه های box-shadow) */
private fun DrawScope.cardShadow(w: Float, h: Float, r: Float, edge: Color?, modern: Boolean) {
    val d = density
    if (modern) {
        for (i in 1..4) drawRoundRect(Color.Black.copy(alpha = .075f), Offset(-i * d, 3 * d - i * d * .5f), Size(w + 2 * i * d, h + 2 * i * d), CornerRadius(r + i * d))
        return
    }
    for (i in 1..4) drawRoundRect(Color.Black.copy(alpha = .04f), Offset(-i * d, 5 * d - i * d), Size(w + 2 * i * d, h + 2 * i * d), CornerRadius(r + i * d))
    drawRoundRect(Color.Black.copy(alpha = .2f), Offset(0f, 2 * d), Size(w, h), CornerRadius(r))
    drawRoundRect(Color.Black.copy(alpha = .16f), Offset(0f, 2 * d), Size(w, h), CornerRadius(r))
    if (edge != null) drawRoundRect(edge, Offset(0f, d), Size(w, h), CornerRadius(r))
}

private fun DrawScope.svg(path: Path, x: Float, y: Float, s: Float, color: Color, from: Float = 24f) {
    withTransform({ translate(x, y); scale(s / from, s / from, Offset.Zero) }) { drawPath(path, color) }
}

/**
 * روی ورق c (۰ تا ۵۱: خال × ۱۳ + ارزش، ارزش ۱۲ = آس) در جعبهٔ همین DrawScope.
 * sp و so: برق ورق (نوار نوری که با کج کردن گوشی روی ورق می لغزد؛ .gloss::after).
 */
fun DrawScope.drawCardFace(c: Int, look: String, tm: TextMeasurer, sp: Float = 0f, so: Float = 0f, shadow: Boolean = true) {
    val s = c / 13
    val r = c % 13
    val red = isRedSuit(s)
    val e = size.width
    val h = size.height
    if (look == "m" || look == "d") return drawJumbo(s, r, look, tm, sp, so, shadow)
    val L = LOOKS[look] ?: LOOKS.getValue("a")
    val ink = if (red) L.rd else L.k
    val rad = L.radius * e
    if (shadow) cardShadow(e, h, rad, L.edge, false)
    val shape = Path().apply { addRoundRect(RoundRect(0f, 0f, e, h, CornerRadius(rad))) }
    clipPath(shape) {
        drawRect(L.paper)
        if (L.serif) {
            // بافت کاغذ: نقطه های ریز
            val st = 3 * density
            var y = 0f
            while (y < h) {
                var x = 0f
                while (x < e) { drawCircle(Color(0x0F5A461E), .6f * density, Offset(x, y)); x += st }
                y += st
            }
        }
        if (look == "b") drawRoundRect(Color(0xFFC9A54A), Offset(.05f * e, .05f * e), Size(e - .1f * e, h - .1f * e), CornerRadius(.045f * e), style = Stroke(1.5f * density))
        // شاخص بالا چپ و پایین راست (وارونه)
        val ix = L.ixs * e
        val style = TextStyle(
            fontFamily = if (L.serif) FontFamily.Serif else Peyda, fontWeight = if (L.serif) FontWeight.Bold else FontWeight.Black,
            fontSize = ix.toSp(), lineHeight = ix.toSp(), color = ink,
        )
        val m = tm.measure(CARD_RANKS[r], style)
        val boxW = 1.15f * ix
        val drawIx = {
            val x0 = .035f * e
            val y0 = .034f * h
            drawText(m, topLeft = Offset(x0 + (boxW - m.size.width) / 2, y0 - (m.size.height - ix) / 2))
            svg(SP[s], x0 + (boxW - .8f * ix) / 2, y0 + ix + .1f * ix, .8f * ix, ink)
        }
        drawIx()
        rotate(180f, Offset(e / 2, h / 2)) { drawIx() }
        // وسط ورق
        when {
            r in 9..11 -> drawCourt(r, s, red, L, ink)
            r == 12 -> {
                if (s == 0) {
                    val rs = .74f * e
                    svg(ACE_RING, e / 2 - rs / 2, h / 2 - rs / 2, rs, L.gold.copy(alpha = .55f))
                }
                val sz = (if (s == 0) .5f else .4f) * e
                svg(SP[s], e / 2 - sz / 2, h / 2 - sz / 2 + density, sz, Color.Black.copy(alpha = .18f))
                svg(SP[s], e / 2 - sz / 2, h / 2 - sz / 2, sz, ink)
            }
            else -> {
                val ax = .14f * e
                val aw = .72f * e
                val ay = .09f * h
                val ah = .82f * h
                val ps = L.pip * e
                for ((cx, cy) in LAY[r]) {
                    val yp = .16f + cy * .17f
                    val px = ax + COLX[cx.toInt()] * aw
                    val py = ay + yp * ah
                    if (yp > .505f) rotate(180f, Offset(px, py)) { svg(SP[s], px - ps / 2, py - ps / 2, ps, ink) }
                    else svg(SP[s], px - ps / 2, py - ps / 2, ps, ink)
                }
            }
        }
        // براقی کاغذ و لبهٔ نازک
        drawRect(cssLinear(118f, e, h, 0f to Color.White.copy(alpha = L.gloss), .32f to Color.Transparent, .7f to Color.Transparent,
            1f to Color.Black.copy(alpha = if (look == "c") .04f else .05f)))
        sheen(r in 9..11, sp, so)
    }
    drawRoundRect(Color.Black.copy(alpha = .14f), cornerRadius = CornerRadius(rad), style = Stroke(.5f * density))
}

/** نوار نور برق ورق (hokm.css: .gloss::after)؛ روی سرباز و بی بی و شاه رنگین کمانی */
private fun DrawScope.sheen(court: Boolean, sp: Float, so: Float) {
    if (so <= .01f) return
    val e = size.width
    val h = size.height
    val bw = e * 2.2f
    val bh = h * 2.2f
    val ox = -e * .6f + sp * .4f * bw
    val oy = -h * .6f + sp * .19f * bh
    val base = Color(0xFF182034).copy(alpha = .07f)
    val brush = if (court) cssLinear(115f, bw, bh, 0f to base, .32f to base, .40f to Color(0xFFFF5CAA).copy(alpha = .26f), .46f to Color(0xFFFFE278).copy(alpha = .34f),
        .5f to Color.White.copy(alpha = .42f), .55f to Color(0xFF6EE6FF).copy(alpha = .32f), .6f to Color(0xFF9678FF).copy(alpha = .26f), .68f to base, 1f to base, ox = ox, oy = oy)
    else cssLinear(115f, bw, bh, 0f to base, .39f to base, .5f to Color.White.copy(alpha = .4f), .61f to base, 1f to base, ox = ox, oy = oy)
    drawRect(brush, alpha = so.coerceIn(0f, 1f))
}

/** تصویر دوسر سرباز، بی بی و شاه (court در cards.js) */
private fun DrawScope.drawCourt(r: Int, s: Int, red: Boolean, L: Look, ink: Color) {
    val e = size.width
    val h = size.height
    val robe = if (red) Color(0xFFF6C5C9) else Color(0xFFAFC2DF)
    val cb = if (red) Color(0xFFFCECEA) else Color(0xFFEEF1F6)
    val alt = if (red) Color(0xFF1C3F8C) else Color(0xFFB3262F)
    val aw = .66f * e
    val ah = .76f * h
    val k = minOf(aw / 100f, ah / 140f)
    val ox = .17f * e + (aw - 100 * k) / 2
    val oy = .12f * h + (ah - 140 * k) / 2
    withTransform({ translate(ox, oy); scale(k, k, Offset.Zero) }) {
        drawRoundRect(cb, Offset(3f, 3f), Size(94f, 134f), CornerRadius(5f))
        drawRoundRect(L.gold, Offset(3f, 3f), Size(94f, 134f), CornerRadius(5f), style = Stroke(2.4f))
        val half = {
            drawPath(C_BODY, ink)
            drawPath(C_ROBE, robe.copy(alpha = .55f))
            drawPath(C_GS, L.gold, style = Stroke(2.6f))
            drawCircle(L.gold, 2.4f, Offset(50f, 56f))
            drawRect(Color(0xFFEDC9A2), Offset(46f, 39f), Size(8f, 9f))
            drawCircle(Color(0xFFF2D3B1), 11f, Offset(50f, 30f))
            drawPath(HAIR.getValue(r), Color(0xFF5B3B22))
            drawCircle(Color(0xFF2A1E16), 1.3f, Offset(46f, 29.5f))
            drawCircle(Color(0xFF2A1E16), 1.3f, Offset(54f, 29.5f))
            drawPath(C_MOUTH, Color(0xFF9A4B3A), style = Stroke(1.1f))
            drawPath(HAT.getValue(r), if (r == 9) alt else L.gold)
            drawPath(ITEM.getValue(r), if (r == 10) alt else Color(0xFF8C95A1))
        }
        half()
        rotate(180f, Offset(50f, 70f)) { half() }
        drawLine(L.gold, Offset(8f, 70f), Offset(92f, 70f), 1.2f)
        svg(SP[s], 74f, 8f, 16f, ink)
        svg(SP[s], 10f, 116f, 16f, ink)
    }
}

/** طرح مدرن (m) و رنگ تمام (d): شاخص درشت بالا چپ، نماد کم رنگ خال یا نشان سرباز/بی بی/شاه در گوشه */
private fun DrawScope.drawJumbo(s: Int, r: Int, look: String, tm: TextMeasurer, sp: Float, so: Float, shadow: Boolean) {
    val e = size.width
    val h = size.height
    val red = isRedSuit(s)
    val d = look == "d"
    val rad = (if (d) .157f else .156f) * e
    if (shadow) cardShadow(e, h, rad, null, true)
    val ink = if (d) Color.White else if (red) Color(0xFFD62839) else Color(0xFF1C2230)
    clipPath(Path().apply { addRoundRect(RoundRect(0f, 0f, e, h, CornerRadius(rad))) }) {
        if (d) {
            drawRect(cssLinear(155f, e, h, 0f to (if (red) Color(0xFFFF6E6E) else Color(0xFF323B5E)), 1f to (if (red) Color(0xFFE0304A) else Color(0xFF141A2E))))
            drawOval(Color.White.copy(alpha = .12f), Offset(-.3f * e, -.4f * h), Size(.9f * e, .7f * h))
        } else drawRect(Color.White)
        // شاخص
        val jx = (if (d) .314f else .375f) * e
        val fs = (if (d) (if (r == 8) .27f else .314f) else (if (r == 8) .3f else .36f)) * e
        val m = tm.measure(CARD_RANKS[r], TextStyle(fontFamily = Peyda, fontWeight = FontWeight.ExtraBold, fontSize = fs.toSp(), lineHeight = (fs * .95f).toSp(), color = ink))
        val x0 = (if (d) .1f else .03f) * e
        val y0 = (if (d) .1f else .078f) * e
        drawText(m, topLeft = Offset(x0 + (jx - m.size.width) / 2, y0))
        val ss = (if (d) .2f else .265f) * e
        svg(SP[s], x0 + (jx - ss) / 2, y0 + m.size.height + (if (d) .043f else .047f) * e, ss, ink)
        // گوشهٔ پایین
        val emb = EMB[r]
        if (emb != null) {
            val bs = (if (d) .486f else .5f) * e
            val bx = e - (if (d) .114f else .094f) * e - bs
            val by = h - (if (d) .129f else .094f) * e - bs
            if (d) drawCircle(Color.White.copy(alpha = .2f), bs / 2, Offset(bx + bs / 2, by + bs / 2))
            else drawRoundRect(if (red) Color(0x1AD62839) else Color(0x141C2230), Offset(bx, by), Size(bs, bs), CornerRadius(.156f * e))
            val pad = (if (d) .1f else .08f) * e
            svg(emb, bx + pad, by + pad, bs - 2 * pad, ink)
        } else if (d && r == 12) {
            val ws = .571f * e
            svg(SP[s], e - .114f * e - ws, h - .143f * e - ws, ws, ink)
        } else {
            val ws = (if (d) .857f else .81f) * e
            val wx = e + (if (d) .171f else .125f) * e - ws
            val wy = h + (if (d) .2f else .125f) * e - ws
            svg(SP[s], wx, wy, ws, ink.copy(alpha = if (d) .3f else .13f))
        }
        sheen(r in 9..11, sp, so)
    }
    if (d) drawRoundRect(Color.White.copy(alpha = .9f), cornerRadius = CornerRadius(rad), style = Stroke(.03f * e))
}

/** پشت ورق هر طرح */
fun DrawScope.drawCardBack(look: String, shadow: Boolean = true) {
    val e = size.width
    val h = size.height
    val modern = look == "m" || look == "d"
    val rad = when (look) { "m" -> .156f; "d" -> .157f; else -> .075f } * e
    if (shadow) cardShadow(e, h, rad, if (modern) null else Color(0xFFD9D1BF), modern)
    val shape = Path().apply { addRoundRect(RoundRect(0f, 0f, e, h, CornerRadius(rad))) }
    clipPath(shape) {
        when (look) {
            "m" -> {
                drawRect(Color.White)
                val b = .0625f * e
                clipPath(Path().apply { addRoundRect(RoundRect(b, b, e - b, h - b, CornerRadius(rad - b))) }) {
                    drawRect(cssLinear(135f, e, h, 0f to Color(0xFFF5C451), .5f to Color(0xFFF5C451), .5f to Color(0xFF1A7A47), 1f to Color(0xFF1A7A47)))
                }
            }
            "d" -> {
                drawRect(Color.White)
                val b = .045f * e
                clipPath(Path().apply { addRoundRect(RoundRect(b, b, e - b, h - b, CornerRadius(rad - b))) }) {
                    drawRect(Color(0xFFFFC93C))
                    val st = .14f * e
                    var t = -h
                    while (t < e + h) {
                        drawLine(Color.Black.copy(alpha = .13f), Offset(t, 0f), Offset(t + h, h), .07f * e)
                        t += st
                    }
                }
                drawCircle(Color.White, .2f * e + .03f * e, Offset(e / 2, h / 2))
                drawCircle(Color(0xFF1B2340), .2f * e, Offset(e / 2, h / 2))
            }
            else -> {
                val b = .055f * e
                val bg = when (look) { "b" -> Color(0xFF6A1B28); "c" -> Color(0xFF2B7DF0); else -> Color(0xFF1D3461) }
                drawRect(if (look == "b") Color(0xFFF3E6C8) else Color.White)
                clipPath(Path().apply { addRoundRect(RoundRect(b, b, e - b, h - b, CornerRadius(maxOf(0f, rad - b)))) }) {
                    when (look) {
                        "c" -> {
                            drawRect(cssLinear(160f, e, h, 0f to Color(0xFF2B7DF0), 1f to Color(0xFF0E4FB3)))
                            val st = .07f * e
                            var y = st / 2
                            while (y < h) { var x = st / 2; while (x < e) { drawCircle(Color(0x99FFC43B), .012f * e, Offset(x, y)); x += st }; y += st }
                        }
                        "b" -> {
                            drawRect(bg)
                            val st = .16f * e
                            var y = 0f
                            while (y < h + st) {
                                var x = 0f
                                while (x < e + st) {
                                    val star = Path().apply { moveTo(x, y - st * .22f); lineTo(x + st * .08f, y); lineTo(x, y + st * .22f); lineTo(x - st * .08f, y); close()
                                        moveTo(x - st * .22f, y); lineTo(x, y + st * .08f); lineTo(x + st * .22f, y); lineTo(x, y - st * .08f); close() }
                                    drawPath(star, Color(0x66D6B254))
                                    x += st
                                }
                                y += st
                            }
                        }
                        else -> {
                            drawRect(bg)
                            val st = .05f * e
                            var t = -h
                            while (t < e + h) {
                                drawLine(Color.White.copy(alpha = .17f), Offset(t, 0f), Offset(t + h, h), 1.2f * density)
                                drawLine(Color.White.copy(alpha = .17f), Offset(t + h, 0f), Offset(t, h), 1.2f * density)
                                t += st
                            }
                        }
                    }
                }
                // قاب داخلی و نشان وسط
                val i = .025f * e + b
                drawRoundRect(if (look == "b") Color(0xD9D6B254) else Color.White.copy(alpha = .55f), Offset(i, i), Size(e - 2 * i, h - 2 * i),
                    CornerRadius(.03f * e), style = Stroke((if (look == "b") 1.5f else 1f) * density))
                val cr = .16f * e
                val ctr = Offset(e / 2, h / 2)
                when (look) {
                    "c" -> {
                        val pw = .5f * e
                        val ph = .13f * e
                        drawRoundRect(Color.White.copy(alpha = .9f), Offset(ctr.x - pw / 2 - density, ctr.y - ph / 2 - density), Size(pw + 2 * density, ph + 2 * density), CornerRadius(ph))
                        drawRoundRect(Color(0xFFFFC43B), Offset(ctr.x - pw / 2, ctr.y - ph / 2), Size(pw, ph), CornerRadius(ph))
                    }
                    "b" -> {
                        drawCircle(Color(0xFFD6B254), cr + 1.5f * density, ctr)
                        drawCircle(Color(0xFF6A1B28), cr, ctr)
                        drawCircle(Color(0xFFD6B254), .055f * e, ctr)
                    }
                    else -> {
                        drawCircle(Color.White.copy(alpha = .9f), cr + density, ctr)
                        drawCircle(Color(0xFFFBF7EE), cr, ctr)
                        drawCircle(Color(0xFF1D3461), .06f * e, ctr)
                    }
                }
            }
        }
    }
}

/** نوشتهٔ AsoTas روی نشان پشت ورق طرح c (جدا چون drawCardBack متن ندارد) */
private fun DrawScope.backLabel(tm: TextMeasurer) {
    val e = size.width
    val m = tm.measure("AsoTas", TextStyle(fontFamily = Peyda, fontWeight = FontWeight.Black, fontSize = (.1f * e).toSp(), color = Color(0xFF3D2600)))
    drawText(m, topLeft = Offset((e - m.size.width) / 2, (size.height - m.size.height) / 2))
}

/** ورق رو (یک برگ) در اندازهٔ عرض w */
@Composable
fun PlayingCard(c: Int, w: Dp, look: String, modifier: Modifier = Modifier, sp: Float = 0f, so: Float = 0f) {
    val tm = rememberTextMeasurer()
    Canvas(modifier.size(w, w * 1.406f)) { drawCardFace(c, look, tm, sp, so) }
}

/** پشت ورق در اندازهٔ عرض w */
@Composable
fun PlayingBack(look: String, w: Dp, modifier: Modifier = Modifier, shadow: Boolean = true) {
    val tm = rememberTextMeasurer()
    Canvas(modifier.size(w, w * 1.406f)) {
        drawCardBack(look, shadow)
        if (look == "c") backLabel(tm)
    }
}

/** برای پیش نمایش فروشگاه: شمارهٔ برگ از روی ارزش و نماد خال */
fun cardIndex(rank: String, suit: String): Int {
    val s = listOf("♠", "♥", "♦", "♣").indexOf(suit).coerceAtLeast(0)
    return s * 13 + CARD_RANKS.indexOf(rank).coerceAtLeast(0)
}
