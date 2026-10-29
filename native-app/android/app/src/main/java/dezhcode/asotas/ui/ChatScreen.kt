package dezhcode.asotas.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import dezhcode.asotas.AppViewModel
import dezhcode.asotas.ChatState
import dezhcode.asotas.Sheet
import dezhcode.asotas.core.DmMessage
import dezhcode.asotas.core.Person
import dezhcode.asotas.fd
import dezhcode.asotas.game
import kotlinx.coroutines.delay
import java.util.Calendar

private fun cal(t: Long) = Calendar.getInstance().apply { timeInMillis = t * 1000 }

/** ساعت پیام با رقم فارسی (۱۴:۰۵) */
fun clock(t: Long): String {
    val c = cal(t)
    return c.get(Calendar.HOUR_OF_DAY).toLong().fd().padStart(2, '۰') + ":" + c.get(Calendar.MINUTE).toLong().fd().padStart(2, '۰')
}

private val MONTHS = listOf("ژانویه", "فوریه", "مارس", "آوریل", "مه", "ژوئن", "ژوئیه", "اوت", "سپتامبر", "اکتبر", "نوامبر", "دسامبر")

/** امروز، دیروز یا روز و ماه */
fun dayOf(t: Long): String {
    val d = cal(t)
    val now = Calendar.getInstance()
    fun same(a: Calendar, b: Calendar) = a.get(Calendar.YEAR) == b.get(Calendar.YEAR) && a.get(Calendar.DAY_OF_YEAR) == b.get(Calendar.DAY_OF_YEAR)
    if (same(d, now)) return "امروز"
    now.add(Calendar.DAY_OF_YEAR, -1)
    if (same(d, now)) return "دیروز"
    return "${d.get(Calendar.DAY_OF_MONTH).toLong().fd()} ${MONTHS[d.get(Calendar.MONTH)]}"
}

private val QUICK = listOf("بزن بریم!", "یه دست دیگه؟", "۵ دقیقه دیگه", "بازی خوبی بود")

/** چت خصوصی با یک دوست (chat.html)؛ هر ۲٫۵ ثانیه پیام تازه */
@Composable
fun ChatScreen(vm: AppViewModel, c: ChatState) {
    val col = Aso.c
    BackHandler { vm.social.closeChat() }
    LaunchedEffect(c) {
        vm.social.pull(c, first = true)
        while (c.failed == null) {
            delay(2500)
            vm.social.pull(c, first = false)
        }
    }
    val list = rememberLazyListState()
    LaunchedEffect(c.messages.size) { if (c.messages.isNotEmpty()) list.animateScrollToItem(list.layoutInfo.totalItemsCount.coerceAtLeast(1) - 1) }
    var input by remember { mutableStateOf("") }
    val user = c.user
    val (st, kind) = user?.let { statusOf(it.online, it.playing, it.seen) } ?: ("" to "")
    val can = c.relation == "friend" && c.failed == null

    Column(Modifier.fillMaxSize().background(col.ground).statusBarsPadding().imePadding()) {
        // ---------- سربرگ: برگشت، طرف گفتگو، دعوت ----------
        Row(
            Modifier.fillMaxWidth().background(col.ground.copy(alpha = .92f)).padding(horizontal = 16.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            IconBtn("back", onClick = vm.social::closeChat)
            Row(
                Modifier.weight(1f).press(.98f) { if (user != null && can) vm.openSheet(Sheet.FriendCard(user, fromChat = true)) },
                verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                if (user != null) FriendFace(user.person, kind, 42.dp)
                Column(Modifier.weight(1f)) {
                    Text(user?.person?.name ?: "…", style = peyda(15.5f, 22f, 800), color = col.ink, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    if (st.isNotEmpty()) Text(st, style = peyda(12f, 16f), color = statusColor(kind))
                }
            }
            if (can && user != null) RoundIc("pad", gold = true, size = 44.dp) { vm.openSheet(Sheet.Invite(user.person)) }
        }
        // ---------- پیام ها ----------
        Box(Modifier.weight(1f).fillMaxWidth()) {
            when {
                c.failed != null -> Column(Modifier.align(Alignment.TopCenter).padding(top = 40.dp, start = 24.dp, end = 24.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                    Text("این گفتگو دیگه در دسترس نیست", style = peyda(16f, 24f, 800), color = col.ink)
                    Text(c.failed.orEmpty(), style = peyda(13.5f, 22f), color = col.inkMuted, textAlign = TextAlign.Center)
                }
                c.messages.isEmpty() && user != null -> Column(
                    Modifier.align(Alignment.TopCenter).padding(top = 40.dp).widthIn(max = 260.dp),
                    horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    Face(user.person.name, user.person.av, user.person.pic, size = 72.dp)
                    Text(user.person.name, style = peyda(16f, 24f, 800), color = col.ink)
                    Text("اولین پیامو بفرست یا دعوتش کن به یه بازی", style = peyda(13.5f, 22f), color = col.inkMuted, textAlign = TextAlign.Center)
                }
                else -> LazyColumn(
                    state = list, modifier = Modifier.fillMaxSize(), verticalArrangement = Arrangement.spacedBy(6.dp),
                    contentPadding = androidx.compose.foundation.layout.PaddingValues(14.dp),
                ) {
                    var day = ""
                    val rows = c.messages.flatMap { m ->
                        val d = dayOf(m.at)
                        val head = if (d != day) { day = d; listOf<Any>(d) } else emptyList()
                        head + m
                    }
                    items(rows, key = { r -> if (r is DmMessage) "m${r.id}" else "d$r" }) { r ->
                        if (r is String) DayChip(r) else Bubble(r as DmMessage, user?.person, vm)
                    }
                }
            }
        }
        // ---------- نوشتن ----------
        Column(
            Modifier.fillMaxWidth().background(col.surface.copy(alpha = .97f))
                .drawBehind { drawLine(col.line, Offset(0f, 0f), Offset(size.width, 0f), 1.dp.toPx()) }
                .navigationBarsPadding().padding(start = 12.dp, end = 12.dp, top = 8.dp, bottom = 10.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            if (!can) {
                if (c.failed == null) {
                    Text(if (c.relation == "blocked") "این بنده خدا رو بلاک کردی" else "دیگه رفیق نیستید و پیام نمی‌ره",
                        style = peyda(13.5f, 20f), color = col.inkMuted, textAlign = TextAlign.Center,
                        modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(16.dp)).background(col.surface).padding(12.dp))
                }
            } else {
                Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    QUICK.forEach { t ->
                        Text(t, style = peyda(13f, 20f, 800), color = col.accDeep,
                            modifier = Modifier.height(36.dp).clip(CircleShape).background(col.accTint).press { vm.social.send(c, t) {} }
                                .padding(horizontal = 12.dp, vertical = 8.dp))
                    }
                }
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Box(Modifier.weight(1f).height(48.dp).clip(CircleShape).background(col.surfaceSunk).padding(horizontal = 16.dp), contentAlignment = Alignment.CenterStart) {
                        if (input.isEmpty()) Text("پیام بنویس…", style = peyda(14.5f, 22f), color = col.inkMuted)
                        BasicTextField(
                            input, { input = it.take(300) }, singleLine = true, textStyle = peyda(14.5f, 22f).copy(color = col.ink),
                            cursorBrush = SolidColor(col.acc), modifier = Modifier.fillMaxWidth(),
                            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send),
                            keyboardActions = KeyboardActions(onSend = { vm.social.send(c, input) { input = "" } }),
                        )
                    }
                    Box(Modifier.size(48.dp).clip(CircleShape).background(col.acc).press(.94f) { vm.social.send(c, input) { input = "" } }, contentAlignment = Alignment.Center) {
                        Ic("send", size = 22.dp, tint = col.accInk)
                    }
                }
            }
        }
    }
}

@Composable
private fun DayChip(text: String) {
    Box(Modifier.fillMaxWidth().padding(top = 8.dp, bottom = 2.dp), contentAlignment = Alignment.Center) {
        Text(text, style = peyda(12f, 26f, 700), color = Aso.c.inkMuted,
            modifier = Modifier.clip(RoundedCornerShape(13.dp)).background(Aso.c.surfaceSunk).padding(horizontal = 12.dp))
    }
}

@Composable
private fun Bubble(m: DmMessage, them: Person?, vm: AppViewModel) {
    val c = Aso.c
    // پیام من سمت راست (ابتدای ردیف) با رنگ اصلی؛ پیام او سمت چپ سفید
    Box(Modifier.fillMaxWidth(), contentAlignment = if (m.me) Alignment.CenterStart else Alignment.CenterEnd) {
        if (m.kind == "invite") {
            val g = game(m.game ?: "hokm")
            val shape = RoundedCornerShape(20.dp)
            Column(Modifier.fillMaxWidth(.78f).clip(shape).background(c.surface).lined(shape).padding(12.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    GameThumb(m.game ?: "hokm", 48.dp, 12.dp)
                    Column {
                        Text("دعوت به ${g?.title.orEmpty()}", style = peyda(14.5f, 22f, 800), color = c.ink)
                        Text(if (m.me) "سر میز منتظر رفیقتی" else "میز آزاد · ${clock(m.at)}", style = peyda(12f, 18f), color = c.inkMuted)
                    }
                }
                Btn(if (m.me) "برو سر میز" else "بشین سر میز", { vm.soon("میز ${g?.title.orEmpty()}") }, Modifier.fillMaxWidth().height(44.dp),
                    kind = if (m.me) BtnKind.Light else BtnKind.Primary, small = true)
            }
        } else {
            // گوشهٔ پایینِ سمت گوینده تیز (border-end-start / border-end-end)
            val shape = if (m.me) RoundedCornerShape(18.dp, 18.dp, 18.dp, 6.dp) else RoundedCornerShape(18.dp, 18.dp, 6.dp, 18.dp)
            Column(Modifier.widthIn(max = 290.dp).clip(shape).background(if (m.me) c.acc else c.surface).padding(start = 12.dp, end = 12.dp, top = 8.dp, bottom = 6.dp)) {
                Text(m.text, style = peyda(14.5f, 23f), color = if (m.me) c.accInk else c.ink)
                Text(clock(m.at), style = peyda(11f, 14f), color = (if (m.me) c.accInk else c.ink).copy(alpha = .7f),
                    modifier = Modifier.align(Alignment.End))
            }
        }
    }
}
