package dezhcode.asotas.ui

import androidx.activity.compose.BackHandler
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.EaseIn
import androidx.compose.animation.core.EaseOut
import androidx.compose.animation.core.MutableTransitionState
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.scaleIn
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
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
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Shadow
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.withTransform
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.vector.PathParser
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextDirection
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp
import dezhcode.asotas.ChatLine
import dezhcode.asotas.TableModel
import dezhcode.asotas.core.TableChat
import dezhcode.asotas.fd
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

// گفتگوی سر میز مثل مینی اپ (tchat.js و gc.css: tc-*)، یکی برای همهٔ بازی ها:
// نوار تیرهٔ پایین (آیکن گفتگو، «یه چیزی بگو…»، پیام سریع، فلش آبی فرستادن) که با دکمهٔ چت بازی بالا می آید،
// و پیام هایی که روی خود بازی شناور می شوند: بقیه چپ (حباب روشن)، خودم راست (حباب آبی با ✓).

private fun icon(d: String) = PathParser().parsePathString(d).toPath()
private val CHAT_A = icon("M5 6h22v16H12l-7 5z")
private val CHAT_B = icon("M10 12h12M10 17h8")
private val STICKER_A = icon("M7 4h18a3 3 0 0 1 3 3v12l-9 9H7a3 3 0 0 1-3-3V7a3 3 0 0 1 3-3z")
private val STICKER_B = icon("M28 19h-6a3 3 0 0 0-3 3v6")
private val SEND_A = icon("M4 4.5 29 16 4 27.5l3.6-11.5z")
private val SEND_B = icon("M7.6 16H17")

/** چند پیام آخر که وقتی گفتگو باز است سر جایشان می مانند */
private const val KEEP = 5
private val BAR = Color(0xFF141414)

/** آیکن های ۳۲×۳۲ نوار گفتگو */
@Composable
private fun BarIcon(kind: String, label: String, onClick: () -> Unit) {
    Canvas(
        Modifier.size(28.dp).clickable(interactionSource = null, indication = null, onClick = onClick).semantics { contentDescription = label },
    ) {
        val k = size.width / 32f
        withTransform({ scale(k, k, Offset.Zero) }) {
            when (kind) {
                "chat" -> {
                    drawPath(CHAT_A, Color(0xFF3FBF6A), style = Stroke(2.4f, join = StrokeJoin.Round))
                    drawPath(CHAT_B, Color(0xFF3FBF6A), style = Stroke(2.4f, cap = StrokeCap.Round, join = StrokeJoin.Round))
                }
                "sticker" -> {
                    drawPath(STICKER_A, Color(0xFFBDBDBD), style = Stroke(2.4f, join = StrokeJoin.Round))
                    drawPath(STICKER_B, Color(0xFFBDBDBD), style = Stroke(2.4f, join = StrokeJoin.Round))
                }
                else -> {
                    drawPath(SEND_A, Color(0xFF2E8BFF))
                    drawPath(SEND_B, BAR, style = Stroke(2.2f, cap = StrokeCap.Round))
                }
            }
        }
    }
}

/** نشان قرمز تعداد پیام های نخوانده روی دکمهٔ چت بازی (chat-btn .badge) */
@Composable
fun ChatBadge(n: Int, modifier: Modifier = Modifier, ring: Color = Color(0xFF12291F)) {
    if (n <= 0) return
    Box(modifier.offset(x = 2.dp, y = (-2).dp).background(ring, CircleShape).padding(2.dp)) {
        Text(
            if (n > 9) "+۹" else n.fd(),
            Modifier.height(20.dp).widthIn(min = 20.dp).background(Color(0xFFFF6B7A), RoundedCornerShape(10.dp)).padding(horizontal = 5.dp),
            style = peyda(11f, 20f, 800), color = Color.White, textAlign = TextAlign.Center,
        )
    }
}

/**
 * لایهٔ گفتگوی میز روی صفحهٔ بازی. rest = فاصلهٔ پیام های شناور از پایین وقتی گفتگو بسته است
 * (بالای داک یا نوار خود بازی). enabled = false بعد از پایان یا بسته شدن میز.
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun TableChatLayer(model: TableModel, quick: List<String>, rest: Dp, enabled: Boolean = true) {
    val open = model.chatOpen && enabled
    val scope = rememberCoroutineScope()
    var text by remember { mutableStateOf("") }
    var focused by remember { mutableStateOf(false) }
    var quickOpen by remember { mutableStateOf(false) }
    val focus = remember { FocusRequester() }
    val keyboard = LocalSoftwareKeyboardController.current
    val focusManager = LocalFocusManager.current
    val typing = focused || text.isNotBlank()

    // هر پیام چند ثانیه می ماند و بعد محو می شود
    var now by remember { mutableLongStateOf(System.currentTimeMillis()) }
    LaunchedEffect(model.chat.size, open) {
        while (true) {
            now = System.currentTimeMillis()
            val next = model.chat.map { it.until }.filter { it > now }.minOrNull() ?: break
            delay(next - now + 30)
        }
    }
    fun close() {
        quickOpen = false
        focusManager.clearFocus()
        keyboard?.hide()
        model.openChat(false)
    }
    fun submit() {
        val t = text
        if (t.isBlank()) return
        scope.launch { if (model.say(t)) text = "" }
    }
    BackHandler(enabled = open) { close() }
    LaunchedEffect(open) {
        if (open) {
            delay(60)
            runCatching { focus.requestFocus() }
            keyboard?.show()
        }
    }
    LaunchedEffect(enabled) { if (!enabled && model.chatOpen) close() }

    val dim by animateFloatAsState(if (open) 1f else 0f, tween(200), label = "dim")
    Box(Modifier.fillMaxSize()) {
        // پس زمینهٔ تیره پشت نوار و پیام ها؛ لمسش گفتگو را می بندد
        if (dim > 0f) {
            Box(
                Modifier.fillMaxSize().graphicsLayer { alpha = dim }.background(Color(0x88000000))
                    .clickable(interactionSource = null, indication = null, enabled = open) { close() },
            )
        }
        Column(Modifier.align(Alignment.BottomCenter).fillMaxWidth().imePadding()) {
            // ---------- پیام های شناور ----------
            val lines = model.chat
            val want = (if (open) lines.toList() else lines.filter { it.until > now }).takeLast(KEEP).map { it.m.id }.toSet()
            CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
                Column(
                    Modifier.fillMaxWidth().padding(horizontal = 10.dp)
                        .then(if (open) Modifier.padding(bottom = 10.dp) else Modifier.navigationBarsPadding().padding(bottom = rest)),
                    verticalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    lines.takeLast(12).forEach { line ->
                        key(line.m.id) { ChatItem(line, line.m.id in want) }
                    }
                }
            }
            // ---------- پیام سریع ----------
            if (open && quickOpen) {
                FlowRow(
                    Modifier.padding(start = 10.dp, end = 10.dp, bottom = 8.dp).fillMaxWidth()
                        .shadow(12.dp, RoundedCornerShape(18.dp)).background(Color(0xF0141414), RoundedCornerShape(18.dp)).padding(10.dp),
                    horizontalArrangement = Arrangement.spacedBy(8.dp, Alignment.CenterHorizontally),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    quick.forEach { q ->
                        Text(
                            q,
                            Modifier.background(Color(0xFF2B2B2F), CircleShape)
                                .clickable(interactionSource = null, indication = null) { quickOpen = false; scope.launch { model.say(q) } }
                                .padding(horizontal = 14.dp, vertical = 8.dp),
                            style = peyda(14f, 20f, 700), color = Color.White,
                        )
                    }
                }
            }
            // ---------- نوار پایین ----------
            AnimatedVisibility(
                open,
                enter = slideInVertically(tween(180, easing = EaseOut)) { it },
                exit = slideOutVertically(tween(180, easing = EaseIn)) { it },
            ) {
                CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
                    Row(
                        Modifier.fillMaxWidth().shadow(14.dp).background(BAR).navigationBarsPadding()
                            .height(60.dp).padding(start = 18.dp, end = 14.dp),
                        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(14.dp),
                    ) {
                        if (!typing) BarIcon("chat", "گفتگو") { runCatching { focus.requestFocus() } }
                        CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Rtl) {
                            BasicTextField(
                                text,
                                { if (it.length <= 140) text = it },
                                Modifier.weight(1f).focusRequester(focus).onFocusChanged { focused = it.isFocused }
                                    .semantics { contentDescription = "پیام" },
                                singleLine = true,
                                textStyle = peyda(17f, 24f).copy(color = Color(0xFFEEEEEE), textDirection = TextDirection.Content),
                                cursorBrush = SolidColor(Color(0xFF2E8BFF)),
                                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send),
                                keyboardActions = KeyboardActions(onSend = { submit() }),
                                decorationBox = { inner ->
                                    Box(contentAlignment = Alignment.CenterStart) {
                                        if (text.isEmpty()) Text("یه چیزی بگو…", style = peyda(17f, 24f), color = Color(0xFF8B8B8B))
                                        inner()
                                    }
                                },
                            )
                        }
                        BarIcon("sticker", "پیام سریع") { quickOpen = !quickOpen }
                        if (typing) BarIcon("send", "فرستادن") { submit() }
                    }
                }
            }
        }
    }
}

/** یک پیام شناور: با کمی بالا آمدن ظاهر و با محو شدن کنار می رود */
@Composable
private fun ChatItem(line: ChatLine, shown: Boolean) {
    val st = remember { MutableTransitionState(false) }
    LaunchedEffect(shown) { st.targetState = shown }
    AnimatedVisibility(
        st,
        enter = fadeIn(tween(220, easing = EaseOut)) + slideInVertically(tween(220, easing = EaseOut)) { it / 4 } + scaleIn(tween(220), initialScale = .96f),
        exit = fadeOut(tween(250, easing = EaseIn)) + slideOutVertically(tween(250, easing = EaseIn)) { -it / 8 },
    ) {
        ChatRow(line.m)
    }
}

/** حباب گفتگوی بازی: عکس ۲۷، نام کوچک بالای حباب؛ بقیه خاکستری روشن، خودم آبی */
@Composable
private fun ChatRow(m: TableChat) {
    val shape = RoundedCornerShape(20.dp)
    Row(
        Modifier.fillMaxWidth().padding(start = if (m.me) 50.dp else 0.dp, end = if (m.me) 0.dp else 50.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp, if (m.me) Alignment.End else Alignment.Start),
    ) {
        val face = @Composable {
            Face(m.name, m.av, m.pic, Modifier.padding(top = 17.dp).shadow(3.dp, CircleShape), size = 27.dp, ring = Color.Transparent, pad = 0.dp)
        }
        if (!m.me) face()
        Column(Modifier.weight(1f, fill = false), horizontalAlignment = if (m.me) Alignment.End else Alignment.Start, verticalArrangement = Arrangement.spacedBy(3.dp)) {
            Text(
                buildAnnotatedString {
                    append(m.name)
                    if (m.me) withStyle(SpanStyle(color = Color(0xFF3D9BFF))) { append("  ✓") }
                },
                Modifier.padding(horizontal = 4.dp),
                style = peyda(11f, 14f).copy(textDirection = TextDirection.Content, shadow = Shadow(Color.Black.copy(alpha = .9f), Offset(0f, 2f), 4f)),
                color = Color.White, maxLines = 1, overflow = TextOverflow.Ellipsis,
            )
            CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Rtl) {
                Text(
                    m.text,
                    Modifier.shadow(2.dp, shape).background(if (m.me) Color(0xFF1687EF) else Color(0xFFF2F3F5), shape).padding(horizontal = 15.dp, vertical = 9.dp),
                    style = peyda(16f, 22f).copy(textDirection = TextDirection.Content),
                    color = if (m.me) Color.White else Color(0xFF434343),
                )
            }
        }
        if (m.me) face()
    }
}
