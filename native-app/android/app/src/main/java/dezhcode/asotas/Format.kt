package dezhcode.asotas

import java.util.Locale

private fun persianDigits(s: String): String = s.map { c ->
    when (c) {
        in '0'..'9' -> '۰' + (c - '0')
        ',' -> '٬'
        else -> c
    }
}.joinToString("")

/** عدد با رقم فارسی و جداکنندهٔ هزارگان: 1250 → ۱٬۲۵۰ (fa() در gc.js) */
fun Long.fa(): String = persianDigits(String.format(Locale.US, "%,d", this))

fun Int.fa(): String = toLong().fa()

/** فقط رقم فارسی، بی جداکننده: 12 → ۱۲ (FD() در gc.js) */
fun Long.fd(): String = persianDigits(toString())

fun Int.fd(): String = toLong().fd()

/** رقم فارسی و عربی که کاربر تایپ کرده → لاتین (برای کد ۶ رقمی) */
fun String.toLatinDigits(): String = map { c ->
    when (c) {
        in '۰'..'۹' -> '0' + (c - '۰')
        in '٠'..'٩' -> '0' + (c - '٠')
        else -> c
    }
}.joinToString("")
