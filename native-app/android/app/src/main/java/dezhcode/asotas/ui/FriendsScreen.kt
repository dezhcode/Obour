package dezhcode.asotas.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.defaultMinSize
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import dezhcode.asotas.AppViewModel
import dezhcode.asotas.Sheet
import dezhcode.asotas.core.Friend
import dezhcode.asotas.core.Person
import dezhcode.asotas.fd
import dezhcode.asotas.game

// ---------- وضعیت آنلاین (social.js) ----------
fun lastSeen(t: Long): String {
    if (t <= 0) return "آفلاین"
    val m = ((System.currentTimeMillis() / 1000 - t) / 60.0).let { Math.round(it) }
    return when {
        m < 2 -> "همین الان"
        m < 60 -> "${m.fd()} دقیقه پیش"
        m < 1440 -> "${Math.round(m / 60.0).fd()} ساعت پیش"
        m < 2880 -> "دیروز"
        else -> "${Math.round(m / 1440.0).fd()} روز پیش"
    }
}

/** متن وضعیت و نوعش (play، on یا خالی) */
fun statusOf(online: Boolean, playing: String?, seen: Long): Pair<String, String> = when {
    playing != null -> "در حال بازی ${game(playing)?.title.orEmpty()}" to "play"
    online -> "آنلاین" to "on"
    else -> lastSeen(seen) to ""
}

@Composable
fun statusColor(kind: String): Color = when (kind) {
    "play" -> Aso.c.accDeep
    "on" -> Aso.c.success
    else -> Aso.c.inkMuted
}

/** آواتار با نقطهٔ وضعیت (.fr-av) */
@Composable
fun FriendFace(p: Person, kind: String, size: Dp = 46.dp, big: Boolean = false) {
    Box {
        Face(p.name, p.av, p.pic, size = size)
        val dot = when (kind) { "on" -> Aso.c.success; "play" -> Aso.c.gold; else -> Color(0xFFB5BBC8) }
        Box(
            Modifier.align(Alignment.BottomEnd).offset((-(if (big) 4 else 1)).dp, (-(if (big) 4 else 1)).dp)
                .size(if (big) 23.dp else 18.dp).clip(CircleShape).background(Aso.c.surface).padding(if (big) 2.5.dp else 2.5.dp)
                .clip(CircleShape).background(dot),
        )
    }
}

/** دوستان (friends.html): جستجو، دو تب «دوستان | درخواست‌ها»، آنلاین ها بالا */
@Composable
fun FriendsScreen(vm: AppViewModel, bottom: Dp) {
    val c = Aso.c
    var tab by rememberSaveable { mutableStateOf("friends") }
    var q by rememberSaveable { mutableStateOf("") }
    val data = vm.friends
    Column(Modifier.fillMaxSize()) {
        Row(
            Modifier.fillMaxWidth().background(c.ground.copy(alpha = .92f)).padding(horizontal = 16.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text("دوستان", style = rokh(24f, 32f), color = c.ink, modifier = Modifier.weight(1f))
            Row(
                Modifier.height(42.dp).clip(CircleShape).background(c.surface).lined(CircleShape).press { vm.openSheet(Sheet.AddFriend) }
                    .padding(start = 14.dp, end = 16.dp),
                verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                Ic("userAdd", size = 20.dp, tint = c.ink)
                Text("افزودن", style = peyda(14f, 20f, 800), color = c.ink)
            }
        }
        Column(
            Modifier.fillMaxSize().verticalScroll(rememberScrollState())
                .padding(PaddingValues(start = 16.dp, end = 16.dp, top = 8.dp, bottom = bottom + 24.dp)),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            if (tab == "friends") SearchBox(q) { q = it.lowercase().filter { ch -> ch.isLetterOrDigit() || ch == '_' } }
            Tabs(tab, data?.friends?.size, data?.incoming?.size ?: 0) { tab = it }
            if (data == null) {
                repeat(3) { Box(Modifier.fillMaxWidth().height(68.dp).clip(RoundedCornerShape(20.dp)).background(c.surfaceSunk)) }
                return@Column
            }
            if (tab == "friends") {
                val list = data.friends.filter { q.isEmpty() || it.person.name.contains(q) }
                val on = list.filter { it.online }
                val off = list.filter { !it.online }
                when {
                    data.friends.isEmpty() -> Empty("users", "هنوز رفیقی نداری", "رفیقاتو با یوزرنیمشون پیدا کن و با هم بازی کنید") {
                        Btn("افزودن دوست", { vm.openSheet(Sheet.AddFriend) }, icon = "userAdd")
                    }
                    list.isEmpty() -> Empty("search", "پیدا نشد", "بین رفیقات کسی با این اسم نیست")
                    else -> {
                        if (on.isNotEmpty()) Group("آنلاین", on.size) { on.forEach { FriendRow(it, vm) } }
                        if (off.isNotEmpty()) Group("آفلاین", off.size) { off.forEach { FriendRow(it, vm) } }
                    }
                }
            } else {
                var any = false
                if (data.incoming.isNotEmpty()) {
                    any = true
                    Group("درخواست‌های تازه", data.incoming.size) { data.incoming.forEach { ReqRow(it, "in", vm) } }
                }
                if (data.outgoing.isNotEmpty()) {
                    any = true
                    Group("فرستادی", null) { data.outgoing.forEach { ReqRow(it, "out", vm) } }
                }
                if (data.blocked.isNotEmpty()) {
                    any = true
                    Group("بلاک شده‌ها", null) { data.blocked.forEach { ReqRow(it, "blk", vm) } }
                }
                if (!any) Empty("userAdd", "درخواستی نداری", "هر کی بخواد رفیقت بشه اینجا می‌بینیش")
            }
        }
    }
}

@Composable
private fun SearchBox(q: String, onChange: (String) -> Unit) {
    val c = Aso.c
    val shape = RoundedCornerShape(14.dp)
    Row(
        Modifier.fillMaxWidth().height(46.dp).clip(shape).background(c.surface).lined(shape).padding(horizontal = 14.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Ic("search", size = 20.dp, tint = c.inkMuted)
        Box(Modifier.weight(1f)) {
            if (q.isEmpty()) Text("بین رفیقات بگرد", style = peyda(14.5f, 22f), color = c.inkMuted)
            BasicTextField(q, onChange, singleLine = true, textStyle = peyda(14.5f, 22f).copy(color = c.ink), cursorBrush = SolidColor(c.acc),
                modifier = Modifier.fillMaxWidth())
        }
    }
}

@Composable
private fun Tabs(tab: String, friends: Int?, incoming: Int, onTab: (String) -> Unit) {
    val c = Aso.c
    Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(16.dp)).background(c.groundDeep).padding(4.dp), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
        for ((id, label) in listOf("friends" to "دوستان", "req" to "درخواست‌ها")) {
            val on = id == tab
            val shape = RoundedCornerShape(12.dp)
            Row(
                Modifier.weight(1f).height(40.dp).then(if (on) Modifier.shadow(1.dp, shape) else Modifier).clip(shape)
                    .background(if (on) c.surface else Color.Transparent).press { onTab(id) },
                horizontalArrangement = Arrangement.spacedBy(6.dp, Alignment.CenterHorizontally), verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(label, style = peyda(14f, 20f, if (on) 800 else 700), color = if (on) c.ink else c.inkMuted)
                if (id == "friends" && friends != null) Text(friends.fd(), style = peyda(14f, 20f, 700), color = c.inkMuted)
                if (id == "req" && incoming > 0) {
                    Text(incoming.fd(), style = peyda(11.5f, 20f, 800), color = Color.White,
                        modifier = Modifier.defaultMinSize(minWidth = 20.dp).clip(CircleShape).background(Color(0xFFF0465B)).padding(horizontal = 6.dp))
                }
            }
        }
    }
}

@Composable
private fun Group(title: String, n: Int?, rows: @Composable () -> Unit) {
    val c = Aso.c
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(Modifier.padding(horizontal = 4.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(title, style = peyda(13f, 20f, 800), color = c.inkMuted)
            if (n != null) {
                Text(n.fd(), style = peyda(11.5f, 20f, 800), color = c.ink,
                    modifier = Modifier.defaultMinSize(minWidth = 20.dp).clip(CircleShape).background(c.surfaceSunk).padding(horizontal = 6.dp))
            }
        }
        val shape = RoundedCornerShape(20.dp)
        Column(Modifier.fillMaxWidth().clip(shape).background(c.surface).lined(shape)) { rows() }
    }
}

@Composable
private fun FriendRow(f: Friend, vm: AppViewModel) {
    val c = Aso.c
    val (st, kind) = statusOf(f.online, f.playing, f.seen)
    Row(
        Modifier.fillMaxWidth().defaultMinSize(minHeight = 68.dp).padding(start = 14.dp, end = 10.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Row(
            Modifier.weight(1f).press(.98f) { vm.openSheet(Sheet.FriendCard(f)) }.padding(vertical = 6.dp),
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            FriendFace(f.person, kind)
            Column(Modifier.weight(1f)) {
                Text(f.person.name, style = peyda(15f, 22f, 800), color = c.ink, maxLines = 1, overflow = TextOverflow.Ellipsis)
                Text(st, style = peyda(12.5f, 18f), color = statusColor(kind), maxLines = 1)
            }
        }
        Box {
            RoundIc("chat", gold = false) { vm.social.openChat(f.person.uid) }
            if (f.unread > 0) Badge(f.unread.toInt().coerceAtMost(9), Modifier.align(Alignment.TopEnd).offset(2.dp, (-2).dp))
        }
        RoundIc("pad", gold = true) { vm.openSheet(Sheet.Invite(f.person)) }
    }
    HorizontalDivider(color = c.line, thickness = 1.dp)
}

@Composable
fun RoundIc(icon: String, gold: Boolean, size: Dp = 42.dp, onClick: () -> Unit) {
    val c = Aso.c
    Box(
        Modifier.size(size).clip(CircleShape).background(if (gold) c.acc else c.surface)
            .then(if (gold) Modifier else Modifier.lined(CircleShape)).press(.94f, onClick = onClick),
        contentAlignment = Alignment.Center,
    ) { Ic(icon, size = 21.dp, tint = if (gold) c.accInk else c.ink) }
}

@Composable
private fun ReqRow(p: Person, kind: String, vm: AppViewModel) {
    val c = Aso.c
    Row(
        Modifier.fillMaxWidth().defaultMinSize(minHeight = 68.dp).padding(start = 14.dp, end = 10.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Row(Modifier.weight(1f).press(.98f) { vm.openSheet(Sheet.AddFriend) }.padding(vertical = 6.dp),
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Face(p.name, p.av, p.pic, size = 46.dp)
            Column(Modifier.weight(1f)) {
                Text(p.name, style = peyda(15f, 22f, 800), color = c.ink, maxLines = 1, overflow = TextOverflow.Ellipsis)
                Text(when (kind) { "in" -> "می‌خواد رفیقت بشه"; "out" -> "منتظر جوابه"; else -> "بلاکش کردی" }, style = peyda(12.5f, 18f), color = c.inkMuted)
            }
        }
        when (kind) {
            "in" -> {
                RoundIc("close", gold = false) { vm.social.drop(p.uid) }
                Text("قبول", style = peyda(14f, 20f, 800), color = c.accInk,
                    modifier = Modifier.height(42.dp).clip(RoundedCornerShape(13.dp)).background(c.acc).press { vm.social.accept(p.uid) }.padding(horizontal = 16.dp, vertical = 11.dp))
            }
            "out" -> LiteBtn("لغو") { vm.social.drop(p.uid) }
            else -> LiteBtn("رفع بلاک") { vm.social.unblock(p.uid) }
        }
    }
    HorizontalDivider(color = c.line, thickness = 1.dp)
}

@Composable
private fun LiteBtn(text: String, onClick: () -> Unit) {
    val c = Aso.c
    val shape = RoundedCornerShape(13.dp)
    Text(text, style = peyda(13f, 18f, 800), color = c.ink,
        modifier = Modifier.height(40.dp).clip(shape).background(c.surface).lined(shape).press(onClick = onClick).padding(horizontal = 14.dp, vertical = 11.dp))
}

@Composable
fun Empty(icon: String, title: String, sub: String, action: (@Composable () -> Unit)? = null) {
    val c = Aso.c
    val shape = RoundedCornerShape(22.dp)
    Column(
        Modifier.fillMaxWidth().clip(shape).background(c.surface).lined(shape).padding(horizontal = 16.dp, vertical = 32.dp),
        horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Box(Modifier.size(64.dp).clip(CircleShape).background(c.accTint), contentAlignment = Alignment.Center) { Ic(icon, size = 30.dp, tint = c.acc) }
        Text(title, style = peyda(16f, 24f, 800), color = c.ink)
        Text(sub, style = peyda(13f, 21f), color = c.inkMuted, textAlign = androidx.compose.ui.text.style.TextAlign.Center)
        if (action != null) Box(Modifier.padding(top = 6.dp)) { action() }
    }
}
