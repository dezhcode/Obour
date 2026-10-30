package dezhcode.asotas

import dezhcode.asotas.core.ApiException
import org.json.JSONObject

// متن فارسی کدهای خطای سرور؛ همان ERR و LOGIN_ERR در game_club/webapp/static/gc.js
private val ERR = mapOf(
    "auth" to "نشستت تموم شده داش برنامه رو ببند و دوباره باز کن",
    "rate" to "یواش‌تر داش چند ثانیه صبر کن",
    "network" to "وصل نشد داش اینترنتتو یه نگاه بنداز",
    "server" to "سرور یه لحظه گیج زد دوباره امتحان کن",
    "banned" to "شرمنده داش حسابت تو AsoTas بسته شده",
    "maintenance" to "داریم آپدیت می‌کنیم چند دقیقه دیگه دوباره سر بزن",
    "insufficient" to "سکه‌ت کمه داش با جایزهٔ روزانه و برد رتبه‌ای جمعش کن",
    "daily_done" to "جایزهٔ امروزتو گرفتی فردا دوباره سر بزن 😉",
    "busy" to "یه لحظه دیگه دوباره امتحان کن",
    "not_found" to "این میز پیدا نشد داش",
    "chat_slow" to "یواش‌تر داش چند ثانیه صبر کن",
    "empty" to "اول یه چیزی بنویس",
    "in_match" to "داش تو الان سر یه میز دیگه‌ای",
    "name_short" to "یوزرنیم حداقل ۳ تا حرف باشه", "name_long" to "یوزرنیم حداکثر ۱۶ تا حرفه",
    "name_start" to "یوزرنیم باید با حرف انگلیسی شروع بشه", "name_chars" to "فقط حرف انگلیسی و عدد و _ قبوله",
    "name_reserved" to "این یوزرنیمو نمی‌شه برداشت", "name_taken" to "این یوزرنیمو یکی دیگه زودتر برداشته",
)

/** خطای یوزرنیم (کد سرور، name_wait:<روز> هم) */
fun nameErrorText(code: String): String =
    if (code.startsWith("name_wait:")) "یوزرنیمو ${code.substringAfter(':').toLongOrNull()?.fd() ?: ""} روز دیگه می‌تونی عوض کنی"
    else ERR[code] ?: ERR.getValue("server")

private val LOGIN_ERR = mapOf(
    "bad_email" to "این ایمیل درست نیست یه نگاه بهش بنداز",
    "email_off" to "ورود با ایمیل فعلاً بسته‌ست با تلگرام بیا",
    "tg_off" to "ورود با تلگرام فعلاً بسته‌ست با ایمیل بیا",
    "email_limit" to "زیادی کد خواستی یه ساعت دیگه دوباره امتحان کن",
    "send_fail" to "ایمیل نرفت یه دقیقه دیگه دوباره امتحان کن",
    "code_tries" to "زیادی اشتباه زدی یه کد تازه بگیر",
    "code_expired" to "وقت این کد تموم شده یه کد تازه بگیر",
)

fun errorText(e: Throwable): String = when (e) {
    is ApiException.Network -> ERR.getValue("network")
    is ApiException.Auth -> ERR.getValue("auth")
    is ApiException.Rate -> ERR.getValue("rate")
    is ApiException.Server -> if (e.code.startsWith("name_")) nameErrorText(e.code) else ERR[e.code] ?: ERR.getValue("server")
    else -> ERR.getValue("server")
}

fun loginErrorText(e: Throwable): String {
    if (e is ApiException.Server) {
        val extra = runCatching { JSONObject(e.extraJson) }.getOrNull()
        when (e.code) {
            "email_wait" -> return "یه کم صبر کن ${(extra?.optLong("wait", 60) ?: 60L).fa()} ثانیه دیگه دوباره بفرست"
            "code_bad" -> return "کد اشتباهه ${(extra?.optLong("left") ?: 0L).fa()} بار دیگه می‌تونی بزنی"
        }
        LOGIN_ERR[e.code]?.let { return it }
    }
    return errorText(e)
}
