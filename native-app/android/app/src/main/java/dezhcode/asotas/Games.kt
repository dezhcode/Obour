package dezhcode.asotas

import androidx.compose.ui.graphics.Color

/** بازی های AsoTas (همان شناسه های سرور در service.GAMES) */
data class Game(val id: String, val title: String, val emoji: String, val color: Color)

val GAMES = listOf(
    Game("ludo", "منچ", "🎲", Color(0xFF7C66F2)),
    Game("hokm", "حکم", "🃏", Color(0xFFE5484D)),
    Game("billiard", "بیلیارد", "🎱", Color(0xFF1A9A4A)),
    Game("football", "فوتبال", "⚽", Color(0xFF2B6EF2)),
    Game("snakes", "مار و پله", "🐍", Color(0xFFF08C2E)),
    Game("divar", "دیوار", "🧱", Color(0xFF8A5A44)),
    Game("esmfamil", "اسم‌فامیل", "✍️", Color(0xFF0E9AA7)),
    Game("lashgar", "لشگر کاغذی", "🪖", Color(0xFF5B6178)),
)
