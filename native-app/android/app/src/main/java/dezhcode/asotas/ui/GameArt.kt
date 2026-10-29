package dezhcode.asotas.ui

import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxScope
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.absoluteOffset
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.AbsoluteAlignment
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.graphics.vector.rememberVectorPainter
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import dezhcode.asotas.R

/** سایهٔ رنگی زیر هر کاشی (--sh) */
val GAME_SHADOW = mapOf(
    "hokm" to Color(0xBF0F3F1D), "football" to Color(0xCC1D5A25), "ludo" to Color(0xCC0B241C), "billiard" to Color(0xCC4A2A18),
    "divar" to Color(0xCC0A2A1C), "esmfamil" to Color(0xCC3E2912), "lashgar" to Color(0xCC4E3016), "snakes" to Color(0xCC070D1C),
)

private fun radial(vararg stops: Pair<Float, Color>, cx: Float = .5f, cy: Float = .4f) = object : androidx.compose.ui.graphics.ShaderBrush() {
    override fun createShader(size: androidx.compose.ui.geometry.Size) = androidx.compose.ui.graphics.RadialGradientShader(
        center = Offset(size.width * cx, size.height * cy),
        radius = maxOf(size.width, size.height) * .75f,
        colors = stops.map { it.second }, colorStops = stops.map { it.first },
    )
}

/** دنیای هر بازی پشت کاشی (ماهوت حکم، زمین فوتبال، میز بیلیارد، ...) */
@Composable
fun BoxScope.GameBackground(id: String) {
    val full = Modifier.matchParentSize()
    when (id) {
        "hokm" -> Box(full.background(radial(0f to Color(0xFF2F8F4E), .6f to Color(0xFF1E6B3A), 1f to Color(0xFF0F3F1D), cy = .35f)))
        "football" -> Image(painterResource(R.drawable.pv_fb_pitch), null, full, contentScale = ContentScale.Crop, alignment = Alignment.TopCenter)
        "billiard" -> Image(painterResource(R.drawable.pv_bl_table), null, full, contentScale = ContentScale.Crop)
        "snakes" -> Image(painterResource(R.drawable.pv_sn_board), null, full, contentScale = ContentScale.Crop)
        "ludo" -> Box(full.background(radial(0f to Color(0xFF1F4A37), 1f to Color(0xFF0F2A22), cy = .35f)))
        "divar" -> {
            Box(full.background(radial(0f to Color(0xFF1D5A3F), 1f to Color(0xFF0B231A))))
            Thumb(R.drawable.thumb_divar, 120.dp, AbsoluteAlignment.CenterLeft, x = 8.dp, rotate = -6f, alpha = .9f)
        }
        "esmfamil" -> {
            Box(full.background(radial(0f to Color(0xFFF6EEDC), .85f to Color(0xFFE2D3B0), 1f to Color(0xFFE2D3B0))))
            Thumb(R.drawable.thumb_esmfamil, 120.dp, AbsoluteAlignment.CenterLeft, x = 12.dp, rotate = 6f, alpha = .95f)
        }
        "lashgar" -> {
            Box(full.background(Brush.linearGradient(listOf(Color(0xFF8E5F38), Color(0xFF9A6A40), Color(0xFF865933), Color(0xFF976640)))))
            Thumb(R.drawable.thumb_lashgar, 120.dp, AbsoluteAlignment.CenterLeft, x = 10.dp, rotate = -5f, alpha = .95f)
        }
    }
}

@Composable
private fun BoxScope.Thumb(res: Int, size: Dp, at: Alignment, x: Dp = 0.dp, y: Dp = 0.dp, rotate: Float = 0f, alpha: Float = 1f) {
    Image(
        painterResource(res), null,
        Modifier.align(at).absoluteOffset(x, y).size(size).rotate(rotate).clip(RoundedCornerShape(18.dp)),
        alpha = alpha,
    )
}

// ---------- اجزایی که از قاب بیرون زده اند (موقعیت ها به پیکسل CSS از چپ و بالای کاشی) ----------
@Composable
private fun BoxScope.Out(left: Dp, top: Dp, width: Dp, rotate: Float = 0f, fromBottom: Boolean = false, content: @Composable () -> Unit) {
    Box(
        Modifier.align(if (fromBottom) AbsoluteAlignment.BottomLeft else AbsoluteAlignment.TopLeft)
            .absoluteOffset(left, if (fromBottom) -top else top)
            .width(width)
            .rotate(rotate),
    ) { content() }
}

@Composable
private fun Vec(v: ImageVector, width: Dp, ratio: Float) {
    Image(rememberVectorPainter(v), null, Modifier.size(width, width * ratio))
}

@Composable
private fun Webp(res: Int, width: Dp) {
    Image(painterResource(res), null, Modifier.size(width), contentScale = ContentScale.Fit)
}

/** برگ ورق حکم (ساده: رنگ و خال و ارزش) */
@Composable
private fun PlayingCard(rank: String, suit: String, red: Boolean, w: Dp) {
    val ink = if (red) Color(0xFFD7263D) else Color(0xFF1C2235)
    Box(
        Modifier.size(w, w * 1.4f).shadow(6.dp, RoundedCornerShape(w * .14f)).clip(RoundedCornerShape(w * .14f))
            .background(Color.White).padding(w * .08f),
    ) {
        Column(Modifier.align(AbsoluteAlignment.TopLeft)) {
            Text(rank, style = rokh(w.value * .3f, w.value * .32f), color = ink)
            Text(suit, style = peyda(w.value * .24f, w.value * .26f, 700), color = ink)
        }
        Text(suit, style = peyda(w.value * .62f, w.value * .66f, 700), color = ink, modifier = Modifier.align(Alignment.Center))
    }
}

private val BluePawn by lazy { pawnVector(0xFF4C8DFF, 0xFF2B62D6) }
private val YellowPawn by lazy { pawnVector(0xFFFFC531, 0xFFC98A00) }
private val RedPawn by lazy { pawnVector(0xFFFF5A6A, 0xFFC93447) }

/** تکهٔ دیوار (آبی در خانه، قرمز در صفحهٔ بازی ها) */
@Composable
private fun WallPiece(width: Dp, red: Boolean) {
    val c = if (red) listOf(Color(0xFFFFC9CF), Color(0xFFFF5A6A), Color(0xFFA82B3B)) else listOf(Color(0xFFC9DCFF), Color(0xFF4C8DFF), Color(0xFF2B57A8))
    Box(Modifier.size(width, 9.dp).shadow(3.dp, CircleShape).clip(CircleShape).background(Brush.verticalGradient(c)))
}

@Composable
private fun DivarPawn() {
    Box(Modifier.size(34.dp).clip(CircleShape).background(Brush.sweepGradient(listOf(Color(0xFF8E98A1), Color(0xFFF1F4F7), Color(0xFF848E96), Color(0xFFE2E7EC), Color(0xFF8E98A1)))), contentAlignment = Alignment.Center) {
        Box(Modifier.size(24.dp).clip(CircleShape).background(radial(0f to Color(0xFFFF8A96), .45f to Color(0xFFFF5A6A), 1f to Color(0xFFC93447), cy = .62f)))
    }
}

/** اجزای بیرون زدهٔ کاشی خانه (index.html: TILE) */
@Composable
fun BoxScope.HomeOuts(id: String) {
    when (id) {
        "hokm" -> {
            Out(16.dp, (-30).dp, 44.dp, -14f) { PlayingCard("Q", "♥", true, 44.dp) }
            Out(58.dp, (-40).dp, 44.dp, -1f) { PlayingCard("K", "♦", true, 44.dp) }
            Out(100.dp, (-30).dp, 44.dp, 13f) { PlayingCard("A", "♠", false, 44.dp) }
        }
        "ludo" -> {
            // صفحهٔ منچ داخل قاب کاشی است (بریده می شود)، مهره ها بیرون زده اند
            Box(Modifier.matchParentSize().clip(RoundedCornerShape(22.dp))) {
                Out((-14).dp, 62.dp, 112.dp, -10f, fromBottom = true) {
                    Image(painterResource(R.drawable.thumb_ludo), null, Modifier.size(112.dp).shadow(10.dp, RoundedCornerShape(12.dp)).clip(RoundedCornerShape(12.dp)))
                }
            }
            Box(Modifier.align(AbsoluteAlignment.TopRight).absoluteOffset((-18).dp, (-30).dp)) { Vec(BluePawn, 40.dp, 1f) }
            Box(Modifier.align(AbsoluteAlignment.TopRight).absoluteOffset((-58).dp, (-15).dp)) { Vec(YellowPawn, 29.dp, 1f) }
        }
        "football" -> Out((-12).dp, (-14).dp, 46.dp) { Webp(R.drawable.pv_fb_disc_eagles, 46.dp) }
        "billiard" -> Out((-9).dp, (-11).dp, 30.dp, fromBottom = true) { Webp(R.drawable.pv_bl_ball_8, 30.dp) }
        "divar" -> {
            Out(44.dp, (-6).dp, 108.dp) { WallPiece(108.dp, red = false) }
            Out((-12).dp, (-16).dp, 34.dp) { DivarPawn() }
        }
        "esmfamil" -> Out((-14).dp, (-12).dp, 118.dp, -14f) { Vec(PenVector, 118.dp, 1 / 6f) }
        "lashgar" -> Out((-10).dp, (-12).dp, 112.dp, 12f, fromBottom = true) { Vec(PencilVector, 112.dp, 1 / 6f) }
        "snakes" -> Box(Modifier.align(Alignment.TopCenter).absoluteOffset(y = (-20).dp)) { Vec(YellowPawnVector, 34.dp, 1f) }
    }
}

/** اجزای بیرون زدهٔ کارت صفحهٔ بازی ها (games.html: INFO.out) */
@Composable
fun BoxScope.GamesOuts(id: String) {
    when (id) {
        "hokm" -> {
            Out(10.dp, (-24).dp, 38.dp, -14f) { PlayingCard("Q", "♥", true, 38.dp) }
            Out(46.dp, (-32).dp, 38.dp, -1f) { PlayingCard("K", "♦", true, 38.dp) }
            Out(82.dp, (-24).dp, 38.dp, 13f) { PlayingCard("A", "♠", false, 38.dp) }
        }
        "football" -> Out(20.dp, (-14).dp, 34.dp) { Webp(R.drawable.pv_fb_ball, 34.dp) }
        "ludo" -> {
            Out(12.dp, (-14).dp, 104.dp, -8f) {
                Image(painterResource(R.drawable.thumb_ludo), null, Modifier.size(104.dp).clip(RoundedCornerShape(12.dp)))
            }
            Out(100.dp, (-22).dp, 30.dp) { Vec(RedPawn, 30.dp, 1f) }
        }
        "billiard" -> Out(26.dp, (-14).dp, 32.dp) { Webp(R.drawable.pv_bl_ball_8, 32.dp) }
        "divar" -> Out(18.dp, (-8).dp, 100.dp) { WallPiece(100.dp, red = true) }
        "esmfamil" -> Out((-10).dp, (-10).dp, 100.dp, -14f) { Vec(PenVector, 100.dp, 1 / 6f) }
        "lashgar" -> Out((-10).dp, (-10).dp, 100.dp, 12f, fromBottom = true) { Vec(PencilVector, 100.dp, 1 / 6f) }
        "snakes" -> Box(Modifier.align(Alignment.TopCenter).absoluteOffset(y = (-18).dp)) { Vec(YellowPawnVector, 30.dp, 1f) }
    }
}

/** تصویر کوچک گرد هر بازی (فهرست ها، میزهای باز) */
@Composable
fun GameThumb(id: String, size: Dp, radius: Dp = 14.dp, modifier: Modifier = Modifier) {
    val g = dezhcode.asotas.game(id)
    Box(modifier.size(size).clip(RoundedCornerShape(radius)).background(Aso.c.surfaceSunk)) {
        if (g != null) Image(painterResource(g.thumb), null, Modifier.fillMaxSize(), contentScale = ContentScale.Crop)
    }
}
