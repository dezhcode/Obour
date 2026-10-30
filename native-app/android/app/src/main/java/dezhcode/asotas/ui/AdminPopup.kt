package dezhcode.asotas.ui

import androidx.activity.compose.BackHandler
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.CubicBezierEasing
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.offset
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
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.AbsoluteAlignment
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.clipToBounds
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import coil.compose.AsyncImage
import dezhcode.asotas.core.Popup

private val CARD_INK = Color(0xFF1C2235)
private val CARD_TEXT = Color(0xFF424862)

/** پاپ آپ پنل مدیریت (gc.js: showPopup و gk-card): عکس، تیتر، متن، دکمهٔ لینک و «بستن» */
@Composable
fun AdminPopup(p: Popup, openLink: (String) -> Unit, close: () -> Unit) {
    BackHandler(onBack = close)
    val fade = remember { Animatable(0f) }
    val pop = remember { Animatable(0f) }
    LaunchedEffect(Unit) { fade.animateTo(1f, tween(250)) }
    LaunchedEffect(Unit) { pop.animateTo(1f, tween(350, easing = CubicBezierEasing(.3f, 1.4f, .5f, 1f))) }
    val shape = RoundedCornerShape(24.dp)
    val imgMax = (LocalConfiguration.current.screenHeightDp * .52f).dp
    Box(
        Modifier.fillMaxSize().graphicsLayer { alpha = fade.value }.background(Color(0x9E0A0C16))
            .clickable(interactionSource = null, indication = null, onClick = close)
            .statusBarsPadding().navigationBarsPadding().padding(20.dp),
        contentAlignment = Alignment.Center,
    ) {
        Box(
            Modifier.widthIn(max = 380.dp).fillMaxWidth()
                .graphicsLayer {
                    val v = pop.value
                    alpha = v.coerceIn(0f, 1f)
                    translationY = (1f - v) * 16.dp.toPx()
                    val s = .94f + .06f * v
                    scaleX = s
                    scaleY = s
                }
                .shadow(24.dp, shape).background(Color.White)
                .clickable(interactionSource = null, indication = null) {},
        ) {
            Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState())) {
                val img = p.img
                if (img != null) {
                    AsyncImage(
                        model = img, contentDescription = null, contentScale = ContentScale.FillWidth,
                        modifier = Modifier.fillMaxWidth().heightIn(max = imgMax).clipToBounds().background(Color(0xFFEEF0F5)),
                    )
                }
                Column(Modifier.fillMaxWidth().padding(start = 18.dp, end = 18.dp, top = 18.dp, bottom = 16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    if (p.title.isNotBlank()) Text(p.title, style = rokh(21f, 29f), color = CARD_INK)
                    if (p.text.isNotBlank()) Text(p.text, style = peyda(14f, 24f), color = CARD_TEXT)
                    if (p.btn.isNotBlank() && p.url.isNotBlank()) {
                        PopupButton(p.btn) {
                            openLink(p.url)
                            close()
                        }
                    }
                    Text(
                        "بستن",
                        Modifier.fillMaxWidth().height(38.dp).clickable(interactionSource = null, indication = null, onClick = close).padding(top = 8.dp),
                        style = peyda(14f, 22f, 800), color = Color(0xFF5B6178), textAlign = TextAlign.Center,
                    )
                }
            }
            // دکمهٔ ✕ گوشهٔ بالا چپ؛ روی عکس تیره و شیشه ای، بی عکس روشن
            Box(
                Modifier.align(AbsoluteAlignment.TopLeft).padding(10.dp).size(36.dp).clip(CircleShape)
                    .background(if (hasImg(p)) Color(0x73000000) else Color(0xFFF1F2F7))
                    .clickable(onClick = close).semantics { contentDescription = "بستن" },
                contentAlignment = Alignment.Center,
            ) {
                Text("✕", style = peyda(18f, 20f), color = if (hasImg(p)) Color.White else CARD_TEXT)
            }
        }
    }
}

private fun hasImg(p: Popup) = p.img != null

/** دکمهٔ آبی با لبهٔ تیرهٔ پایین که با فشار پایین می رود (gk-btn) */
@Composable
private fun PopupButton(text: String, onClick: () -> Unit) {
    val src = remember { MutableInteractionSource() }
    val pressed by src.collectIsPressedAsState()
    val shape = RoundedCornerShape(16.dp)
    Box(Modifier.fillMaxWidth().height(52.dp).clickable(interactionSource = src, indication = null, onClick = onClick)) {
        if (!pressed) Box(Modifier.fillMaxWidth().height(48.dp).offset(y = 4.dp).clip(shape).background(Color(0xFF0F4FAA)))
        Box(
            Modifier.fillMaxWidth().height(48.dp).offset(y = if (pressed) 3.dp else 0.dp).clip(shape).background(Color(0xFF1668D9)),
            contentAlignment = Alignment.Center,
        ) {
            Text(text, style = peyda(16f, 22f, 800), color = Color.White)
        }
    }
}
