package dezhcode.asotas.ui

import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.size
import androidx.compose.material3.Icon
import androidx.compose.material3.LocalContentColor
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.graphics.vector.PathNode
import androidx.compose.ui.graphics.vector.PathParser
import androidx.compose.ui.graphics.vector.group
import androidx.compose.ui.graphics.vector.rememberVectorPainter
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp

private fun nodes(d: String): List<PathNode> = PathParser().parsePathString(d).toNodes()

private fun ImageVector.Builder.stroke(d: String, w: Float) = addPath(
    pathData = nodes(d), fill = null, stroke = SolidColor(Color.Black), strokeLineWidth = w,
    strokeLineCap = StrokeCap.Round, strokeLineJoin = StrokeJoin.Round,
)

private fun ImageVector.Builder.fill(d: String, color: Long) = addPath(pathData = nodes(d), fill = SolidColor(Color(color)))

/** دایره به شکل مسیر SVG */
internal fun circle(cx: Float, cy: Float, r: Float) = "M${cx - r} ${cy}a$r $r 0 1 0 ${2 * r} 0a$r $r 0 1 0 ${-2 * r} 0z"

private fun iconVector(name: String, w: Float): ImageVector {
    val b = ImageVector.Builder(name, 24.dp, 24.dp, 24f, 24f)
    if (name == "navGames") {
        // static/icons/nav-games.svg (دکمهٔ «بازی‌ها»)
        listOf("M9.57 12.46L6.52 15.51", "M6.55 12.49L9.6 15.54",
            "M9 22H15C20 22 22 20 22 15V13C22 8 20 6 15 6H9C4 6 2 8 2 13V15C2 20 4 22 9 22Z",
            "M13.01 2L13 3.01C12.99 3.56 12.55 4 12 4H11.97C11.42 4 10.98 4.45 10.98 5C10.98 5.55 11.43 6 11.98 6H12.98",
        ).forEach { b.stroke(it, 1.5f) }
        listOf("M13.53 14H13.54", "M17.47 14H17.48", "M15.5 15.98V15.96", "M15.5 12.04V12.02").forEach { b.stroke(it, 2f) }
        return b.build()
    }
    ICON_PATHS[name].orEmpty().forEach { p ->
        if (p.rotate != 0f) b.group(rotate = p.rotate, pivotX = p.px, pivotY = p.py) { stroke(p.d, w) } else b.stroke(p.d, w)
    }
    return b.build()
}

/** آیکن خطی مینی اپ (icon() در gc.js): اسم همان کلید P، ضخامت خط پیش فرض ۲٫۲ */
@Composable
fun Ic(name: String, modifier: Modifier = Modifier, size: Dp = 24.dp, tint: Color = LocalContentColor.current, stroke: Float = 2.2f) {
    val v = remember(name, stroke) { iconVector(name, stroke) }
    Icon(rememberVectorPainter(v), contentDescription = null, modifier = modifier.size(size), tint = tint)
}

/** سکهٔ طلایی (COIN در gc.js) */
private val CoinVector: ImageVector by lazy {
    ImageVector.Builder("coin", 32.dp, 32.dp, 32f, 32f).apply {
        fill(circle(16f, 17.5f, 13f), 0xFFE09A00)
        fill(circle(16f, 15f, 13f), 0xFFFFC43B)
        addPath(nodes(circle(16f, 15f, 9.4f)), fill = null, stroke = SolidColor(Color(0xFFE09A00)), strokeLineWidth = 2f)
        fill("M16 9.3l1.75 3.6 3.95.55-2.86 2.73.68 3.92L16 18.2l-3.52 1.9.68-3.92-2.86-2.73 3.95-.55z", 0xFFFFF3C4)
    }.build()
}

@Composable
fun Coin(size: Dp = 20.dp, modifier: Modifier = Modifier) {
    Image(rememberVectorPainter(CoinVector), contentDescription = null, modifier = modifier.size(size))
}

// ---------- اجزای کوچکی که از کاشی بازی ها بیرون زده اند (index.html و games.html) ----------
/** خودکار قرمز داور اسم‌فامیل (۱۲۰×۲۰) */
val PenVector: ImageVector by lazy {
    ImageVector.Builder("pen", 120.dp, 20.dp, 120f, 20f).apply {
        fill("M19 5h82a5 5 0 0 1 0 10H19a5 5 0 0 1 0-10z", 0xFFC8323C)
        fill("M88 5h14a4 4 0 0 1 4 4v2a4 4 0 0 1-4 4H88z", 0xFF8E1B26)
        fill("M14 5L1 10l13 5z", 0xFFF2D8B0)
        fill("M5 8.4L1 10l4 1.6z", 0xFF2A2F3A)
        fill("M41.5 3a1.5 1.5 0 0 1 1.5 1.5v11a1.5 1.5 0 0 1-3 0v-11A1.5 1.5 0 0 1 41.5 3z", 0xFFE8C76A)
    }.build()
}

/** مداد آبی لشگر کاغذی (۱۲۰×۲۰) */
val PencilVector: ImageVector by lazy {
    ImageVector.Builder("pencil", 120.dp, 20.dp, 120f, 20f).apply {
        fill("M2 10L22 3.5V16.5Z", 0xFFE9C9A0)
        fill("M2 10L8.6 7.9V12.1Z", 0xFF1A4FB0)
        fill("M22 3.5h88v13H22z", 0xFF1F5FC8)
        fill("M22 5.5h88v3H22z", 0x3DFFFFFF)
        fill("M106 3.5h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2h-8z", 0xFFE8B4B8)
        fill("M100 3.5h4v13h-4z", 0xFFC9A15A)
    }.build()
}

/** مهرهٔ زرد مار و پله (۴۰×۴۰) */
val YellowPawnVector: ImageVector by lazy {
    ImageVector.Builder("pawn", 40.dp, 40.dp, 40f, 40f).apply {
        fill("M7 36a13 4 0 1 0 26 0a13 4 0 1 0 -26 0z", 0x66000000)
        fill("M8 34Q8 20 20 20T32 34Z", 0xFFE0A800)
        fill("M10 33Q10 22 20 22T30 33Z", 0xFFFFC531)
        addPath(nodes(circle(20f, 13f, 9f)), fill = SolidColor(Color(0xFFFFC531)), stroke = SolidColor(Color.White), strokeLineWidth = 1.6f)
        addPath(nodes(circle(17f, 10f, 3.2f)), fill = SolidColor(Color.White), fillAlpha = .75f)
    }.build()
}

/** مهرهٔ منچ به رنگ دلخواه (۴۰×۴۰) */
fun pawnVector(main: Long, deep: Long): ImageVector = ImageVector.Builder("pawn", 40.dp, 40.dp, 40f, 40f).apply {
    fill("M7 36a13 4 0 1 0 26 0a13 4 0 1 0 -26 0z", 0x66000000)
    fill("M8 34Q8 20 20 20T32 34Z", deep)
    fill("M10 33Q10 22 20 22T30 33Z", main)
    addPath(nodes(circle(20f, 13f, 9f)), fill = SolidColor(Color(main)), stroke = SolidColor(Color.White), strokeLineWidth = 1.6f)
    addPath(nodes(circle(17f, 10f, 3.2f)), fill = SolidColor(Color.White), fillAlpha = .75f)
}.build()
