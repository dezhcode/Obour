package dezhcode.asotas

import androidx.annotation.DrawableRes

/** یک واقعیت کوتاه روی کارت بازی (آیکن و متن) */
data class Fact(val icon: String, val text: String)

/** بازی های AsoTas؛ متن ها همان GAMES در gc.js و INFO در games.html */
data class Game(
    val id: String,
    val title: String,
    val sub: String,
    val cat: String,
    val tag: String?,
    val desc: String,
    val facts: List<Fact>,
    @DrawableRes val thumb: Int,
)

val GAMES = listOf(
    Game("hokm", "حکم", "۴ نفره · با یار و ناشناس یا ربات", "card", "محبوب", "با یارت جلوی دو تا حریف",
        listOf(Fact("users", "۴ نفره"), Fact("clock", "۱۰ تا ۲۵ دقیقه")), R.drawable.thumb_hokm),
    Game("football", "فوتبال", "۲ نفره · نوبتی", "sport", "تازه", "نوبتی شوت بزن و گل بزن ⚽",
        listOf(Fact("users", "۲ نفره"), Fact("ball", "تا دو یا سه یا پنج گل")), R.drawable.thumb_football),
    Game("ludo", "منچ", "۲ یا ۴ نفره", "board", null, "مهره‌هاتو دور صفحه ببر و برسون خونه",
        listOf(Fact("users", "۲ یا ۴ نفره"), Fact("clock", "۵ تا ۱۵ دقیقه")), R.drawable.thumb_ludo),
    Game("billiard", "بیلیارد", "۲ نفره یا ۴ نفره یاری", "sport", "تازه", "توپاتو بنداز و آخر از همه توپ ۸",
        listOf(Fact("users", "۲ یا ۴ نفره"), Fact("spark", "۸ توپ")), R.drawable.thumb_billiard),
    Game("divar", "دیوار", "۲ یا ۴ نفره · راهو ببند", "board", "تازه", "راه حریفو ببند و زودتر برس",
        listOf(Fact("users", "۲ یا ۴ نفره"), Fact("grid", "۹×۹ یا ۱۱×۱۱")), R.drawable.thumb_divar),
    Game("esmfamil", "اسم‌فامیل", "۲ تا ۱۰ نفر · گروه یا کانال", "word", "تازه", "یه حرف و نُه تا ستون با داور هوش مصنوعی",
        listOf(Fact("users", "۲ تا ۱۰ نفر"), Fact("send", "گروه یا کانال")), R.drawable.thumb_esmfamil),
    Game("lashgar", "لشگر کاغذی", "۲ نفره · گروه یا کانال", "board", "تازه", "ارتشتو بکش و برگه رو تا کن و شلیک کن",
        listOf(Fact("users", "۲ نفره"), Fact("send", "گروه یا کانال")), R.drawable.thumb_lashgar),
    Game("snakes", "مار و پله", "۲ تا ۴ نفره · با ربات و رفقا یا تو گروه", "board", "تازه", "تاس بریز و از نردبون برو بالا و از مار فرار کن",
        listOf(Fact("users", "۲ تا ۴ نفره"), Fact("dice", "دقیقاً تا ۱۰۰")), R.drawable.thumb_snakes),
)

fun game(id: String): Game? = GAMES.firstOrNull { it.id == id }
