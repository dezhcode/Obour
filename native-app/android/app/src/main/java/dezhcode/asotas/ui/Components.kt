package dezhcode.asotas.ui

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.defaultMinSize
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.composed
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Shape
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import coil.compose.AsyncImage
import dezhcode.asotas.fa
import dezhcode.asotas.fd
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlin.math.abs

/** لمس مثل مینی اپ: بی موج، فقط کمی کوچک شدن (.btn:active scale .97) */
fun Modifier.press(scale: Float = .97f, enabled: Boolean = true, onClick: () -> Unit): Modifier = composed {
    val src = remember { MutableInteractionSource() }
    val down by src.collectIsPressedAsState()
    this
        .graphicsLayer { val s = if (down && enabled) scale else 1f; scaleX = s; scaleY = s }
        .clickable(interactionSource = src, indication = null, enabled = enabled, onClick = onClick)
}

/** خط نازک دور سطح ها (box-shadow: 0 0 0 1px var(--line)) */
@Composable
fun Modifier.lined(shape: Shape, width: Dp = 1.dp, color: Color = Aso.c.line): Modifier = border(width, color, shape)

enum class BtnKind { Primary, Gold, Light, Soft, Success, Violet, Danger, DangerSoft }

/** دکمهٔ گرد مینی اپ (.btn و گونه هایش) */
@Composable
fun Btn(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    kind: BtnKind = BtnKind.Primary,
    small: Boolean = false,
    enabled: Boolean = true,
    icon: String? = null,
) {
    val c = Aso.c
    val (bg, fg) = when {
        !enabled -> c.surfaceSunk to c.inkMuted
        kind == BtnKind.Gold -> c.coin to c.coinInk
        kind == BtnKind.Light -> c.surface to c.ink
        kind == BtnKind.Soft -> c.accTint to c.accDeep
        kind == BtnKind.Success -> c.success to c.onFill
        kind == BtnKind.Violet -> c.violet to c.onFill
        kind == BtnKind.Danger -> c.danger to c.onFill
        kind == BtnKind.DangerSoft -> c.danger.copy(alpha = .16f) to c.danger
        else -> c.acc to c.accInk
    }
    val shape = CircleShape
    Row(
        modifier
            .defaultMinSize(minHeight = if (small) 38.dp else 52.dp)
            .clip(shape)
            .background(bg)
            .then(if (kind == BtnKind.Light && enabled) Modifier.lined(shape) else Modifier)
            .press(enabled = enabled, onClick = onClick)
            .padding(horizontal = if (small) 16.dp else 20.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp, Alignment.CenterHorizontally),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        if (icon != null) Ic(icon, size = 20.dp, tint = fg)
        Text(text, style = peyda(if (small) 14f else 16f, 24f, 800), color = fg, textAlign = TextAlign.Center)
    }
}

/** دکمهٔ گرد آیکن دار سربرگ (.icon-btn) با نشان قرمز اختیاری */
@Composable
fun IconBtn(icon: String, onClick: () -> Unit, modifier: Modifier = Modifier, badge: Int = 0) {
    Box(modifier.size(44.dp)) {
        Box(
            Modifier.fillMaxSize().clip(CircleShape).background(Aso.c.surface).lined(CircleShape).press(.94f, onClick = onClick),
            contentAlignment = Alignment.Center,
        ) { Ic(icon, size = 22.dp, tint = Aso.c.ink) }
        if (badge > 0) Badge(badge, Modifier.align(Alignment.TopEnd).offset(x = 3.dp, y = (-3).dp))
    }
}

/** نشان شمارهٔ قرمز (اعلان، درخواست دوستی) */
@Composable
fun Badge(n: Int, modifier: Modifier = Modifier) {
    Box(
        modifier
            .defaultMinSize(minWidth = 17.dp)
            .clip(CircleShape)
            .background(Aso.c.surface)
            .padding(2.dp)
            .clip(CircleShape)
            .background(Color(0xFFF0465B))
            .padding(horizontal = 4.dp),
        contentAlignment = Alignment.Center,
    ) { Text(n.coerceAtMost(99).fd(), style = peyda(10.5f, 15f, 800), color = Color.White) }
}

/** موجودی سکه با دکمهٔ + (.pill در سربرگ) */
@Composable
fun CoinPill(balance: Long?, onClick: () -> Unit, plus: Boolean = true) {
    val c = Aso.c
    Row(
        Modifier
            .defaultMinSize(minHeight = 44.dp)
            .clip(CircleShape)
            .background(c.surface)
            .lined(CircleShape)
            .press(onClick = onClick)
            .padding(start = if (plus) 6.dp else 12.dp, end = 12.dp, top = 4.dp, bottom = 4.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        if (plus) {
            Box(Modifier.size(30.dp).clip(CircleShape).background(c.acc), contentAlignment = Alignment.Center) {
                Ic("plus", size = 16.dp, tint = c.accInk)
            }
        }
        Text(balance?.fa() ?: "…", style = peyda(15f, 22f, 800), color = c.ink)
        Coin(19.dp)
    }
}

/** کارت سفید (.card) */
@Composable
fun AsoCard(modifier: Modifier = Modifier, radius: Dp = 28.dp, padding: Dp = 16.dp, content: @Composable BoxScope.() -> Unit) {
    val shape = RoundedCornerShape(radius)
    Box(modifier.clip(shape).background(Aso.c.surface).lined(shape).padding(padding), content = content)
}

/** برچسب کوچک (.tag) */
@Composable
fun Tag(text: String, bg: Color = Aso.c.coin, fg: Color = Aso.c.coinInk, modifier: Modifier = Modifier) {
    Text(
        text, style = peyda(12f, 18f, 800), color = fg, maxLines = 1,
        modifier = modifier.clip(CircleShape).background(bg).padding(horizontal = 10.dp, vertical = 1.dp),
    )
}

// ---------- آواتار (face() در gc.js): عکس پروفایل، وگرنه حرف اول اسم روی رنگ ثابت همان بازیکن ----------
private val FACE_BG = listOf(0xFF5B4BC4, 0xFF2563C9, 0xFFC2414E, 0xFF1A7A53, 0xFFA6560F, 0xFF147C8C, 0xFFA8407E)

fun initial(name: String): String = name.trim().firstOrNull { it.isLetterOrDigit() }?.uppercase() ?: "؟"

@Composable
fun Face(name: String, av: Long, pic: String?, modifier: Modifier = Modifier, size: Dp = 44.dp, ring: Color = Aso.c.surface) {
    val fs = with(LocalDensity.current) { (size * .4f).toSp() }
    Box(modifier.size(size).clip(CircleShape).background(ring).padding(3.dp)) {
        Box(
            Modifier.fillMaxSize().clip(CircleShape).background(Color(FACE_BG[(abs(av) % FACE_BG.size).toInt()])),
            contentAlignment = Alignment.Center,
        ) {
            Text(initial(name), style = peyda(0f, 0f, 800).copy(fontSize = fs, lineHeight = fs), color = Color.White)
            if (!pic.isNullOrEmpty()) {
                AsyncImage(model = pic, contentDescription = null, contentScale = ContentScale.Crop, modifier = Modifier.fillMaxSize())
            }
        }
    }
}

/** سربرگ ساده هر بخش: عنوان و موجودی (gc.css: .appbar) */
@Composable
fun TopBar(title: String, balance: Long?, onCoins: () -> Unit, modifier: Modifier = Modifier, lead: (@Composable RowScope.() -> Unit)? = null) {
    Row(
        modifier.background(Aso.c.ground.copy(alpha = .92f)).padding(horizontal = 16.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        lead?.invoke(this)
        Text(title, style = rokh(24f, 32f), color = Aso.c.ink, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
        CoinPill(balance, onCoins, plus = false)
    }
}

/** اعلان کوتاه پایین صفحه (.toast): زمینهٔ شب، متن سفید پررنگ */
@Composable
fun ToastHost(messages: Flow<String>, modifier: Modifier = Modifier) {
    var text by remember { mutableStateOf<String?>(null) }
    var seq by remember { mutableStateOf(0) }
    LaunchedEffect(messages) { messages.collect { text = it; seq++ } }
    LaunchedEffect(seq) { if (seq > 0) { delay(2600); text = null } }
    AnimatedVisibility(
        visible = text != null, modifier = modifier,
        enter = fadeIn() + slideInVertically { it / 2 }, exit = fadeOut() + slideOutVertically { it / 2 },
    ) {
        Text(
            text.orEmpty(), style = peyda(14f, 22f, 800), color = Color.White, textAlign = TextAlign.Center,
            modifier = Modifier.widthIn(max = 420.dp).padding(horizontal = 16.dp).clip(CircleShape)
                .background(Aso.c.night.copy(alpha = if (Aso.c.dark) 1f else .96f)).padding(horizontal = 18.dp, vertical = 10.dp),
        )
    }
}
