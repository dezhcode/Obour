package dezhcode.asotas.ui

import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.LocalContentColor
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ProvideTextStyle
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.ReadOnlyComposable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.text.PlatformTextStyle
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.LineHeightStyle
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.sp
import dezhcode.asotas.R

/** رنگ های مینی اپ (game_club/webapp/static/gc.css: پوستهٔ روشن :root و تیره data-theme=dark) */
@Immutable
data class AsoColors(
    val dark: Boolean,
    val ground: Color, val groundDeep: Color, val surface: Color, val surfaceSunk: Color, val line: Color,
    val ink: Color, val inkMuted: Color, val night: Color,
    val sky: Color, val skyDeep: Color, val skyTint: Color, val violet: Color, val violetTint: Color,
    val gold: Color, val goldInk: Color,
    val acc: Color, val accDeep: Color, val accInk: Color, val accTint: Color,
    val coin: Color, val coinDeep: Color, val coinInk: Color, val coinTint: Color, val coinText: Color,
    val success: Color, val successTint: Color, val danger: Color, val scrim: Color,
    val onFill: Color = Color.White,
)

private fun rgba(r: Int, g: Int, b: Int, a: Float) = Color(r, g, b, (a * 255).toInt())

val LightColors = AsoColors(
    dark = false,
    ground = Color(0xFFF4F5F8), groundDeep = Color(0xFFE9ECF2), surface = Color.White, surfaceSunk = Color(0xFFEEF0F5),
    line = Color(0xFFE3E6EE), ink = Color(0xFF161922), inkMuted = Color(0xFF6B7080), night = Color(0xFF161922),
    sky = Color(0xFF2F6FEB), skyDeep = Color(0xFF1F55C4), skyTint = Color(0xFFE9F0FE), violet = Color(0xFF7C66F2),
    violetTint = Color(0xFFEFEBFF), gold = Color(0xFFF5C451), goldInk = Color(0xFF3A2A00),
    acc = Color(0xFF2F6FEB), accDeep = Color(0xFF1F55C4), accInk = Color.White, accTint = Color(0xFFE9F0FE),
    coin = Color(0xFFFFC93C), coinDeep = Color(0xFFE39A00), coinInk = Color(0xFF4A3400), coinTint = Color(0xFFFFF4D6),
    coinText = Color(0xFF8A6200), success = Color(0xFF1E8A5E), successTint = Color(0xFFE1F5EA), danger = Color(0xFFD63447),
    scrim = rgba(14, 18, 26, .5f),
)

val DarkColors = AsoColors(
    dark = true,
    ground = Color(0xFF0F1218), groundDeep = Color(0xFF0A0C11), surface = Color(0xFF181C24), surfaceSunk = Color(0xFF20252F),
    line = Color(0xFF2A303C), ink = Color(0xFFECEFF5), inkMuted = Color(0xFF9098A8), night = Color(0xFF0A0C11),
    sky = Color(0xFF4C8DFF), skyDeep = Color(0xFF8DB4FF), skyTint = rgba(76, 141, 255, .16f), violet = Color(0xFF7C66F2),
    violetTint = rgba(124, 102, 242, .2f), gold = Color(0xFFF5C451), goldInk = Color(0xFF3A2A00),
    acc = Color(0xFF3D7EF5), accDeep = Color(0xFF8DB4FF), accInk = Color.White, accTint = rgba(61, 126, 245, .18f),
    coin = Color(0xFFFFC93C), coinDeep = Color(0xFFE39A00), coinInk = Color(0xFF4A3400), coinTint = rgba(245, 196, 81, .14f),
    coinText = Color(0xFFF5C451), success = Color(0xFF3DD68C), successTint = rgba(61, 214, 140, .15f), danger = Color(0xFFFF6B7A),
    scrim = rgba(0, 0, 0, .62f),
)

val LocalAso = staticCompositionLocalOf { LightColors }

object Aso {
    val c: AsoColors
        @Composable @ReadOnlyComposable get() = LocalAso.current
}

// ---------- فونت ها: رخ برای عنوان ها، پیدا برای بقیه (tokens.css) ----------
val Rokh = FontFamily(
    Font(R.font.rokh_400, FontWeight.Normal), Font(R.font.rokh_500, FontWeight.Medium),
    Font(R.font.rokh_700, FontWeight.Bold), Font(R.font.rokh_800, FontWeight.ExtraBold), Font(R.font.rokh_900, FontWeight.Black),
)
val Peyda = FontFamily(
    Font(R.font.peyda_400, FontWeight.Normal), Font(R.font.peyda_600, FontWeight.SemiBold),
    Font(R.font.peyda_700, FontWeight.Bold), Font(R.font.peyda_800, FontWeight.ExtraBold),
)

private val CssLine = LineHeightStyle(LineHeightStyle.Alignment.Center, LineHeightStyle.Trim.None)

/** متن با فونت پیدا: اندازه و ارتفاع خط به پیکسل CSS (همان dp) */
fun peyda(size: Float, line: Float = size * 1.5f, weight: Int = 400) = TextStyle(
    fontFamily = Peyda, fontSize = size.sp, lineHeight = line.sp, fontWeight = FontWeight(weight),
    platformStyle = PlatformTextStyle(includeFontPadding = false), lineHeightStyle = CssLine,
)

/** عنوان با فونت رخ */
fun rokh(size: Float, line: Float = size * 1.3f, weight: Int = 900) = TextStyle(
    fontFamily = Rokh, fontSize = size.sp, lineHeight = line.sp, fontWeight = FontWeight(weight),
    platformStyle = PlatformTextStyle(includeFontPadding = false), lineHeightStyle = CssLine,
)

val Body = peyda(14.5f, 24f)

/** آیدی ها (نام بازیکن ها) همیشه با فونت پیدا، حتی وسط عنوانی که با رخ نوشته شده */
fun withIds(text: String, ids: List<String>): AnnotatedString = buildAnnotatedString {
    append(text)
    for (id in ids.filter { it.isNotBlank() }.distinct()) {
        var i = text.indexOf(id)
        while (i >= 0) {
            addStyle(SpanStyle(fontFamily = Peyda, fontWeight = FontWeight.ExtraBold), i, i + id.length)
            i = text.indexOf(id, i + id.length)
        }
    }
}

/** کل برنامه فارسی و راست به چپ؛ پوسته مثل مینی اپ «خودکار» (مثل گوشی) است مگر کاربر عوضش کند */
@Composable
fun AsoTasTheme(dark: Boolean = isSystemInDarkTheme(), content: @Composable () -> Unit) {
    val c = if (dark) DarkColors else LightColors
    val scheme = if (dark) {
        darkColorScheme(primary = c.acc, onPrimary = c.accInk, background = c.ground, onBackground = c.ink,
            surface = c.surface, onSurface = c.ink, surfaceVariant = c.surfaceSunk, onSurfaceVariant = c.inkMuted,
            surfaceContainerLow = c.surface, error = c.danger, outline = c.line)
    } else {
        lightColorScheme(primary = c.acc, onPrimary = c.accInk, background = c.ground, onBackground = c.ink,
            surface = c.surface, onSurface = c.ink, surfaceVariant = c.surfaceSunk, onSurfaceVariant = c.inkMuted,
            surfaceContainerLow = c.surface, error = c.danger, outline = c.line)
    }
    CompositionLocalProvider(LocalAso provides c, LocalLayoutDirection provides LayoutDirection.Rtl) {
        MaterialTheme(colorScheme = scheme) {
            CompositionLocalProvider(LocalContentColor provides c.ink) {
                ProvideTextStyle(Body, content)
            }
        }
    }
}
