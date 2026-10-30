package dezhcode.asotas.ui

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.defaultMinSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp
import androidx.compose.ui.graphics.Color
import dezhcode.asotas.AppViewModel
import dezhcode.asotas.Sheet
import dezhcode.asotas.core.UserCard
import dezhcode.asotas.fa
import dezhcode.asotas.fd
import dezhcode.asotas.game
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/** برگهٔ باز (vm.sheet) */
@Composable
fun SheetHost(vm: AppViewModel) {
    when (val s = vm.sheet) {
        null -> Unit
        Sheet.AddFriend -> AddFriendSheet(vm)
        is Sheet.FriendCard -> FriendCardSheet(vm, s)
        is Sheet.Invite -> InviteSheet(vm, s)
        is Sheet.Confirm -> ConfirmDialog(vm, s)
        is Sheet.Buy -> BuySheet(vm, s)
        Sheet.Bio -> BioSheet(vm)
        Sheet.Cover -> CoverSheet(vm)
        Sheet.Notifications -> NotificationsSheet(vm)
    }
}

/** برگهٔ پایین با سرتیتر و دکمهٔ بستن (.sheet و .sheet-head) */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AsoSheet(onClose: () -> Unit, title: String? = null, content: @Composable ColumnScope.() -> Unit) {
    val c = Aso.c
    ModalBottomSheet(onDismissRequest = onClose, sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true), containerColor = c.surface) {
        Column(Modifier.fillMaxWidth().padding(horizontal = 20.dp).padding(bottom = 24.dp).navigationBarsPadding(), verticalArrangement = Arrangement.spacedBy(16.dp)) {
            if (title != null) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(title, style = rokh(22f, 30f), color = c.ink, modifier = Modifier.weight(1f))
                    Box(Modifier.size(40.dp).clip(CircleShape).background(c.surfaceSunk).press(onClick = onClose), contentAlignment = Alignment.Center) {
                        Ic("close", size = 18.dp, tint = c.inkMuted)
                    }
                }
            }
            content()
        }
    }
}

// ---------- افزودن دوست با یوزرنیم (addSheet در social.js) ----------
@Composable
private fun AddFriendSheet(vm: AppViewModel) {
    val c = Aso.c
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    var q by remember { mutableStateOf("") }
    var res by remember { mutableStateOf<UserCard?>(null) }
    var state by remember { mutableStateOf("") } // "", short, wait, none, card
    LaunchedEffect(q) {
        res = null
        state = when { q.isEmpty() -> ""; q.length < 3 -> "short"; else -> "wait" }
        if (q.length < 3) return@LaunchedEffect
        delay(400)
        val r = vm.social.find(q)
        res = r
        state = if (r == null) "none" else "card"
    }
    AsoSheet(vm::closeSheet, "افزودن دوست") {
        Text("یوزرنیم رفیقتو بنویس", style = peyda(14f, 23f), color = c.inkMuted)
        CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
            OutlinedTextField(q, { v -> q = v.lowercase().filter { it.isLetterOrDigit() || it == '_' }.take(20) }, singleLine = true,
                placeholder = { Text("username") }, modifier = Modifier.fillMaxWidth(), textStyle = peyda(16f, 24f, 700),
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Ascii, autoCorrectEnabled = false))
        }
        when (state) {
            "short" -> Text("حداقل ۳ تا حرف", style = peyda(12f, 18f), color = c.inkMuted, textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth())
            "wait" -> Box(Modifier.fillMaxWidth().height(80.dp).clip(RoundedCornerShape(18.dp)).background(c.surfaceSunk))
            "none" -> Column(Modifier.fillMaxWidth().padding(vertical = 18.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Ic("search", size = 28.dp, tint = c.inkMuted)
                Text("کسی با این یوزرنیم پیدا نشد", style = peyda(15f, 22f, 800), color = c.ink)
                Text("یه بار دیگه یوزرنیمو چک کن", style = peyda(12.5f, 18f), color = c.inkMuted)
            }
            "card" -> res?.let { u ->
                Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(18.dp)).background(c.surfaceSunk).padding(12.dp),
                    verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    Face(u.person.name, u.person.av, u.person.pic, size = 56.dp)
                    Column {
                        Text(u.person.name, style = peyda(17f, 24f, 800), color = c.ink)
                        Text("سطح ${dezhcode.asotas.core.level(u.games, u.wins).lv.fd()} · ${u.games.fa()} بازی", style = peyda(12.5f, 18f), color = c.inkMuted)
                        if (u.person.bio.isNotBlank()) Text(u.person.bio, style = peyda(12.5f, 18f), color = c.inkMuted)
                    }
                }
                val act = { a: String -> scope.launch { vm.social.act(a, u.person.uid)?.let { rel -> res = u.copy(relation = rel) } }; Unit }
                when (u.relation) {
                    "none" -> Btn("ارسال درخواست دوستی", { act("req") }, Modifier.fillMaxWidth(), icon = "userAdd")
                    "outgoing" -> Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(16.dp)).lined(RoundedCornerShape(16.dp)).padding(start = 14.dp, end = 6.dp, top = 5.dp, bottom = 5.dp),
                        verticalAlignment = Alignment.CenterVertically) {
                        Ic("check", size = 18.dp, tint = c.success)
                        Text("درخواست رفت", style = peyda(14f, 20f, 800), color = c.success, modifier = Modifier.weight(1f).padding(start = 6.dp))
                        Btn("لغو", { act("drop") }, kind = BtnKind.Light, small = true)
                    }
                    "incoming" -> Btn("قبول درخواست دوستی", { act("acc") }, Modifier.fillMaxWidth(), icon = "check")
                    "friend" -> Btn("رفیقید · پیام بده", { vm.closeSheet(); vm.social.openChat(u.person.uid) }, Modifier.fillMaxWidth(), kind = BtnKind.Light, icon = "chat")
                    "blocked" -> Btn("رفع بلاک", { act("unblock") }, Modifier.fillMaxWidth(), kind = BtnKind.Light)
                    "self" -> Text("این که یوزرنیم خودته داش 😄", style = peyda(12f, 18f), color = c.inkMuted, textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth())
                }
            }
        }
        val mine = vm.me?.name
        if (mine != null) {
            Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(16.dp)).background(c.surfaceSunk).padding(horizontal = 12.dp, vertical = 10.dp),
                verticalAlignment = Alignment.CenterVertically) {
                Text("یوزرنیم تو: ", style = peyda(13.5f, 20f), color = c.inkMuted)
                Text(mine, style = peyda(13.5f, 20f, 800), color = c.ink, modifier = Modifier.weight(1f))
                Btn("کپی", {
                    val cm = ctx.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
                    cm.setPrimaryClip(ClipData.newPlainText("AsoTas", mine))
                }, kind = BtnKind.Light, small = true, icon = "copy")
            }
        }
    }
}

// ---------- کارت یک دوست (friendSheet) ----------
@Composable
private fun FriendCardSheet(vm: AppViewModel, s: Sheet.FriendCard) {
    val c = Aso.c
    val f = s.friend
    var card by remember { mutableStateOf<UserCard?>(null) }
    LaunchedEffect(f.person.uid) { card = vm.social.card(f.person.uid) }
    val (st, kind) = statusOf(f.online, f.playing, f.seen)
    AsoSheet(vm::closeSheet) {
        Column(Modifier.fillMaxWidth(), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Box(Modifier.fillMaxWidth().height(128.dp)) {
                Cover("gc", Modifier.fillMaxWidth().height(84.dp).clip(RoundedCornerShape(topStart = 28.dp, topEnd = 28.dp)))
                Box(Modifier.align(Alignment.BottomCenter).clip(CircleShape).background(c.surface).padding(5.dp)) { FriendFace(f.person, kind, 84.dp, big = true) }
            }
            Text(f.person.name, style = peyda(20f, 28f, 800), color = c.ink, modifier = Modifier.padding(top = 6.dp))
            Text(st, style = peyda(12.5f, 18f), color = statusColor(kind))
            if (f.person.bio.isNotBlank()) Text(f.person.bio, style = peyda(14f, 22f), color = c.ink, textAlign = TextAlign.Center)
            Row(Modifier.padding(top = 8.dp).defaultMinSize(minHeight = 44.dp), horizontalArrangement = Arrangement.spacedBy(22.dp)) {
                val u = card
                if (u != null) {
                    Num(dezhcode.asotas.core.level(u.games, u.wins).lv.fd(), "سطح")
                    Num(u.games.fa(), "بازی")
                    Num(u.wins.fa(), "برد")
                }
            }
        }
        Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(20.dp)).background(c.surfaceSunk)) {
            if (!s.fromChat) Act("chat", "پیام بده") { vm.closeSheet(); vm.social.openChat(f.person.uid) }
            Act("pad", "دعوت به بازی") { vm.openSheet(Sheet.Invite(f.person)) }
            Act("userX", "حذف از رفیقا", bad = true) {
                vm.openSheet(Sheet.Confirm("از رفیقات حذفش کنی؟", "${f.person.name} از لیست رفیقات حذف می‌شه و دیگه نمی‌تونید به هم پیام بدید", "حذف کن") {
                    vm.social.remove(f.person) { if (s.fromChat) vm.social.closeChat() }
                })
            }
            Act("ban", "بلاک", bad = true) {
                vm.openSheet(Sheet.Confirm("بلاک کنی؟", "${f.person.name} دیگه نمی‌تونه پیدات کنه یا درخواست بفرسته یا پیام بده", "بلاک کن") {
                    vm.social.block(f.person) { if (s.fromChat) vm.social.closeChat() }
                })
            }
        }
    }
}

@Composable
private fun Num(v: String, label: String) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(v, style = rokh(18f, 24f), color = Aso.c.ink)
        Text(label, style = peyda(12f, 18f), color = Aso.c.inkMuted)
    }
}

@Composable
private fun Act(icon: String, text: String, bad: Boolean = false, onClick: () -> Unit) {
    val col = if (bad) Aso.c.danger else Aso.c.ink
    Row(Modifier.fillMaxWidth().defaultMinSize(minHeight = 52.dp).press(.99f, onClick = onClick).padding(horizontal = 16.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(14.dp)) {
        Ic(icon, size = 22.dp, tint = col)
        Text(text, style = peyda(15f, 22f, 700), color = col)
    }
    HorizontalDivider(color = Aso.c.line)
}

// ---------- دعوت به بازی ----------
@Composable
private fun InviteSheet(vm: AppViewModel, s: Sheet.Invite) {
    val c = Aso.c
    var busy by remember { mutableStateOf(false) }
    AsoSheet(vm::closeSheet, "دعوت ${s.person.name} به بازی") {
        Text("یه میز آزاد ساخته می‌شه و دعوتش تو چت و تلگرام به رفیقت می‌رسه", style = peyda(14f, 23f), color = c.inkMuted)
        listOf("hokm", "ludo", "football", "billiard", "divar", "snakes").chunked(3).forEach { row ->
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                row.forEach { id ->
                    val g = game(id) ?: return@forEach
                    Column(
                        Modifier.weight(1f).clip(RoundedCornerShape(18.dp)).background(c.surfaceSunk)
                            .press(enabled = !busy) { busy = true; vm.social.invite(s.person, id) { vm.closeSheet() }.invokeOnCompletion { busy = false } }
                            .padding(horizontal = 6.dp, vertical = 12.dp),
                        horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(6.dp),
                    ) {
                        GameThumb(id, 56.dp, 16.dp)
                        Text(g.title, style = peyda(15f, 22f, 800), color = c.ink)
                        Text(g.sub.substringBefore(" · "), style = peyda(12f, 18f), color = c.inkMuted, maxLines = 1)
                    }
                }
            }
        }
    }
}

// ---------- پنجرهٔ تأیید ----------
@Composable
private fun ConfirmDialog(vm: AppViewModel, s: Sheet.Confirm) {
    val c = Aso.c
    AlertDialog(
        onDismissRequest = vm::closeSheet, containerColor = c.surface,
        title = { Text(s.title, style = rokh(20f, 28f), color = c.ink, textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth()) },
        text = { Text(s.text, style = peyda(13f, 21f), color = c.inkMuted, textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth()) },
        confirmButton = {
            Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Btn(s.ok, { vm.closeSheet(); s.run() }, Modifier.fillMaxWidth(), kind = BtnKind.Danger)
                Btn("بیخیال", vm::closeSheet, Modifier.fillMaxWidth(), kind = BtnKind.Light)
            }
        },
    )
}

// ---------- خرید میز یا ورق ----------
@Composable
private fun BuySheet(vm: AppViewModel, s: Sheet.Buy) {
    val c = Aso.c
    val it = s.item
    val have = vm.balance ?: 0L
    val st = vm.shop.styles
    AsoSheet(vm::closeSheet, it.name) {
        SkinPreview(it.kind, it.look, st?.table ?: "a", st?.cards ?: "a", Modifier.fillMaxWidth().height(190.dp), big = true)
        Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(16.dp)).background(c.surfaceSunk).padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            ReceiptRow("قیمت") { Amount(it.price) }
            ReceiptRow("سکه‌ت بعد از خرید") { Amount((have - it.price).coerceAtLeast(0), ink = true) }
            ReceiptRow("مدت") { Text("برای همیشه", style = peyda(14.5f, 22f, 800), color = c.ink) }
        }
        if (have < it.price) {
            Text("سکه‌ت کمه داش با جایزهٔ روزانه و برد رتبه‌ای جمعش کن", style = peyda(13f, 20f, 700), color = c.danger, textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth())
        }
        Btn("بخرش", { vm.shop.buy(it) { vm.closeSheet() } }, Modifier.fillMaxWidth(), kind = BtnKind.Gold, enabled = have >= it.price && !vm.shop.busy)
    }
}

@Composable
private fun ReceiptRow(label: String, value: @Composable () -> Unit) {
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Text(label, style = peyda(14.5f, 22f), color = Aso.c.inkMuted, modifier = Modifier.weight(1f))
        value()
    }
}

/** مبلغ سکه (.amount) */
@Composable
fun Amount(n: Long, ink: Boolean = false, size: Float = 14.5f) {
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
        Coin((size * 1.25f).dp)
        Text(n.fa(), style = peyda(size, size * 1.5f, 800), color = if (ink) Aso.c.ink else Aso.c.coinText)
    }
}

// ---------- «درباره من» ----------
@Composable
private fun BioSheet(vm: AppViewModel) {
    val c = Aso.c
    var bio by remember { mutableStateOf(vm.me?.bio.orEmpty()) }
    AsoSheet(vm::closeSheet, "درباره من") {
        Text("یه جمله دربارهٔ خودت بنویس که رفیقات تو پروفایلت ببینن", style = peyda(12f, 18f), color = c.inkMuted)
        OutlinedTextField(bio, { bio = it.take(80) }, minLines = 3, placeholder = { Text("مثلاً عاشق حکم و دستای آخرِ نفس‌گیرم") },
            textStyle = peyda(15f, 24f), modifier = Modifier.fillMaxWidth())
        Text("${bio.length.fd()}/۸۰", style = peyda(12f, 18f), color = c.inkMuted, modifier = Modifier.fillMaxWidth().offset(y = (-10).dp), textAlign = TextAlign.End)
        Btn("ذخیره", { vm.profile.saveBio(bio) { b -> vm.setBio(b); vm.closeSheet() } }, Modifier.fillMaxWidth())
    }
}

// ---------- کاور پروفایل ----------
@Composable
private fun CoverSheet(vm: AppViewModel) {
    val c = Aso.c
    val cur = vm.me?.cover ?: "gc"
    AsoSheet(vm::closeSheet, "کاور پروفایل") {
        val shape = RoundedCornerShape(18.dp)
        Column(
            Modifier.fillMaxWidth().clip(shape).background(c.surfaceSunk).then(if (cur == "gc") Modifier.lined(shape, 2.dp, c.acc) else Modifier)
                .press(.98f) { if (cur == "gc") vm.closeSheet() else vm.profile.setCover("gc") { vm.setCover("gc"); vm.closeSheet() } }.padding(8.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            Cover("gc", Modifier.fillMaxWidth().height(90.dp).clip(RoundedCornerShape(12.dp)), mark = true)
            Text("AsoTas", style = peyda(14f, 20f, 800), color = c.ink, modifier = Modifier.padding(horizontal = 4.dp))
            if (cur == "gc") Text("انتخاب شده", style = peyda(12f, 18f), color = c.success, modifier = Modifier.padding(horizontal = 4.dp))
        }
        Spacer(Modifier.height(0.dp))
        Text("کاورای تازه به‌زودی میان", style = peyda(12f, 18f), color = c.inkMuted, textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth())
    }
}

// ---------- اعلان ها (زنگ خانه): نوبت من، میز منتظر، درخواست دوستی، پیام تازه، پیام تاسی ----------
private data class Alert(val icon: String, val fg: Color, val bg: Color, val title: String, val sub: String, val go: (() -> Unit)?)

/** تعداد اعلان های تازه برای نشان زنگ (میز منتظر حساب نمی شود) */
fun alertCount(me: dezhcode.asotas.core.Me): Int =
    me.tables.count { it.kind == "playing" && it.myTurn } + me.requests.toInt() + me.unread.toInt()

@Composable
private fun NotificationsSheet(vm: AppViewModel) {
    val c = Aso.c
    val me = vm.me
    val list = buildList {
        me?.tables?.forEach { t ->
            val g = game(t.game)
            if (t.kind == "playing" && t.myTurn) add(Alert("clock", c.acc, c.accTint, "نوبت توئه تو ${g?.title.orEmpty()}", "برگرد سر میز تا وقتت نسوخته") { vm.closeSheet(); vm.openTable(t) })
            else if (t.kind == "lobby") add(Alert("users", Color(0xFF1F6B3B), Color(0xFFE3F1E8), "میز ${g?.title.orEmpty()} منتظرته", "${t.found.fd()} از ${t.need.fd()} نفر نشستن") { vm.closeSheet(); vm.openTable(t) })
        }
        if ((me?.requests ?: 0) > 0) add(Alert("userAdd", c.acc, c.accTint, "${me!!.requests.fd()} درخواست دوستی تازه", "یه سر به تب درخواست‌ها بزن") { vm.closeSheet(); vm.selectTab(dezhcode.asotas.Tab.FRIENDS) })
        if ((me?.unread ?: 0) > 0) add(Alert("chat", c.acc, c.accTint, "${me!!.unread.fd()} پیام نخونده", "رفیقات برات پیام فرستادن") { vm.closeSheet(); vm.selectTab(dezhcode.asotas.Tab.FRIENDS) })
        if (!me?.notice.isNullOrBlank()) add(Alert("bell", c.inkMuted, c.surfaceSunk, "پیام از طرف تاسی", me!!.notice, null))
    }
    AsoSheet(vm::closeSheet, "اعلان‌ها") {
        if (list.isEmpty()) {
            Text("فعلاً خبری نیست داش هر وقت نوبتت شد یا یه میز منتظرت بود اینجا می‌بینی", style = peyda(12f, 18f), color = c.inkMuted,
                textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth())
        }
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            list.forEach { a ->
                Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(22.dp)).background(c.surfaceSunk)
                    .then(if (a.go != null) Modifier.press(.99f, onClick = a.go) else Modifier).padding(horizontal = 12.dp, vertical = 10.dp),
                    verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    Box(Modifier.size(42.dp).clip(RoundedCornerShape(14.dp)).background(a.bg), contentAlignment = Alignment.Center) { Ic(a.icon, size = 21.dp, tint = a.fg) }
                    Column(Modifier.weight(1f)) {
                        Text(a.title, style = peyda(14f, 21f, 800), color = c.ink)
                        Text(a.sub, style = peyda(12f, 18f), color = c.inkMuted)
                    }
                    if (a.go != null) Ic("fwd", size = 18.dp, tint = c.inkMuted)
                }
            }
        }
    }
}