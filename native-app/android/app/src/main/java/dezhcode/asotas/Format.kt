package dezhcode.asotas

import java.util.Locale

/** عدد با رقم فارسی و جداکنندهٔ هزارگان: 1250 → ۱٬۲۵۰ */
fun Long.fa(): String = String.format(Locale.US, "%,d", this).map { c ->
    when (c) {
        in '0'..'9' -> '۰' + (c - '0')
        ',' -> '٬'
        else -> c
    }
}.joinToString("")

fun Int.fa(): String = toLong().fa()

/** رقم فارسی و عربی که کاربر تایپ کرده → لاتین (برای کد ۶ رقمی) */
fun String.toLatinDigits(): String = map { c ->
    when (c) {
        in '۰'..'۹' -> '0' + (c - '۰')
        in '٠'..'٩' -> '0' + (c - '٠')
        else -> c
    }
}.joinToString("")
