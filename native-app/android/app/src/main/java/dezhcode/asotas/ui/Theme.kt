package dezhcode.asotas.ui

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.unit.LayoutDirection

// رنگ های AsoTas (game_club/design/tokens.json)
object Palette {
    val Ground = Color(0xFFF5F6FB)
    val GroundDeep = Color(0xFFE9ECF6)
    val Night = Color(0xFF1E2235)
    val Muted = Color(0xFF5B6178)
    val Sky = Color(0xFF2B6EF2)
    val SkyDeep = Color(0xFF1F55C4)
    val SkyTint = Color(0xFFEAF1FF)
    val Violet = Color(0xFF7C66F2)
    val Coin = Color(0xFFFFC93C)
    val CoinInk = Color(0xFF5A3D00)
    val Success = Color(0xFF1A9A4A)
    val SuccessTint = Color(0xFFE3F8EE)
    val Danger = Color(0xFFD92D20)
    val Telegram = Color(0xFF229ED9)
}

private val Colors = lightColorScheme(
    primary = Palette.Sky,
    onPrimary = Color.White,
    secondary = Palette.Violet,
    background = Palette.Ground,
    onBackground = Palette.Night,
    surface = Color.White,
    onSurface = Palette.Night,
    surfaceVariant = Palette.GroundDeep,
    onSurfaceVariant = Palette.Muted,
    error = Palette.Danger,
)

/** کل برنامه فارسی و راست به چپ است، هر زبانی که گوشی داشته باشد */
@Composable
fun AsoTasTheme(content: @Composable () -> Unit) {
    CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Rtl) {
        MaterialTheme(colorScheme = Colors, content = content)
    }
}
