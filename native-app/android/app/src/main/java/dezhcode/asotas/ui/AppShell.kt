package dezhcode.asotas.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.asPaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBars
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import dezhcode.asotas.AppViewModel
import dezhcode.asotas.HomeState
import dezhcode.asotas.Tab

/** پوستهٔ برنامه: بخش فعلی و نوار پایین (gc.css: .nav) */
@Composable
fun AppShell(vm: AppViewModel, openLink: (String) -> Unit) {
    val navBottom = WindowInsets.navigationBars.asPaddingValues().calculateBottomPadding()
    val bottom = navBottom + 64.dp
    BackHandler(enabled = vm.tab != Tab.HOME && vm.social.chat == null && vm.play.lobby == null && vm.play.playing == null && vm.help == null) { vm.selectTab(Tab.HOME) }
    Box(Modifier.fillMaxSize().background(Aso.c.ground)) {
        Box(Modifier.fillMaxSize().statusBarsPadding()) {
            when (vm.tab) {
                Tab.HOME -> HomeScreen(vm, bottom)
                Tab.GAMES -> GamesScreen(vm, bottom)
                Tab.FRIENDS -> FriendsScreen(vm, bottom)
                Tab.SHOP -> ShopScreen(vm, bottom)
                Tab.PROFILE -> ProfileScreen(vm, bottom)
            }
        }
        BottomNav(vm, Modifier.align(Alignment.BottomCenter))
        // لابی بازی، خود بازی و چت خصوصی روی همه چیز (بی نوار پایین)، مثل صفحه های جدای مینی اپ
        vm.play.lobby?.let { LobbyScreen(vm, it) }
        vm.play.playing?.let { if (it.game == "ludo") LudoScreen(vm, it.matchId) }
        vm.social.chat?.let { ChatScreen(vm, it) }
        vm.help?.let { HelpScreen(vm, it) }
        ToastHost(vm.toasts, Modifier.align(Alignment.BottomCenter).padding(bottom = bottom + 40.dp))
    }
    LoginSheet(vm, openLink)
    NameSheet(vm)
    SheetHost(vm)
    WaitingHost(vm)
}

private val NAV = listOf(Tab.HOME to ("خانه" to "home"), Tab.FRIENDS to ("دوستان" to "users"), Tab.GAMES to ("بازی‌ها" to ""),
    Tab.SHOP to ("فروشگاه" to "bag"), Tab.PROFILE to ("پروفایل" to "user"))

@Composable
private fun BottomNav(vm: AppViewModel, modifier: Modifier) {
    val c = Aso.c
    val me = (vm.home as? HomeState.Ready)?.me
    val line = c.line
    Row(
        modifier.fillMaxWidth()
            .background(c.surface.copy(alpha = .97f))
            .drawBehind { drawLine(line, Offset(0f, 0f), Offset(size.width, 0f), 1.dp.toPx()) }
            .navigationBarsPadding()
            .padding(horizontal = 8.dp, vertical = 6.dp),
        verticalAlignment = Alignment.Bottom,
    ) {
        NAV.forEach { (tab, info) ->
            val (label, icon) = info
            val on = vm.tab == tab
            Box(Modifier.weight(1f).height(52.dp).press(.92f) { vm.selectTab(tab) }, contentAlignment = Alignment.Center) {
                if (tab == Tab.GAMES) {
                    Dice(on, Modifier.align(Alignment.TopCenter).offset(y = (-30).dp))
                    Text(label, style = peyda(10.5f, 14f, if (on) 800 else 700), color = if (on) c.acc else c.ink,
                        modifier = Modifier.align(Alignment.BottomCenter).padding(bottom = 2.dp))
                } else {
                    if (on) {
                        Box(Modifier.align(Alignment.TopCenter).offset(y = (-6).dp).width(26.dp).height(3.dp)
                            .clip(RoundedCornerShape(bottomStart = 3.dp, bottomEnd = 3.dp)).background(c.acc))
                    }
                    Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(3.dp)) {
                        Ic(icon, size = 24.dp, tint = if (on) c.acc else c.inkMuted, stroke = if (on) 2.4f else 2.2f)
                        Text(label, style = peyda(10.5f, 14f, if (on) 800 else 700), color = if (on) c.acc else c.inkMuted, maxLines = 1)
                    }
                    if (tab == Tab.FRIENDS && me != null && me.requests + me.unread > 0) {
                        Badge((me.requests + me.unread).toInt(), Modifier.align(Alignment.TopCenter).offset(x = (-14).dp, y = 0.dp))
                    }
                }
            }
        }
    }
}

/** تاس سفید کج وسط نوار (.nav-play .np): خال ها همیشه تیره، در بخش فعلی آبی */
@Composable
private fun Dice(on: Boolean, modifier: Modifier) {
    val c = Aso.c
    val shape = RoundedCornerShape(16.dp)
    val edge = if (c.dark) Color(0xFFCDD3E0) else Color(0xFFE3E6EE)
    val ring = when {
        on -> c.acc
        c.dark -> Color.White.copy(alpha = .14f)
        else -> Color(0xFFE3E6EE)
    }
    Box(
        modifier.size(52.dp).rotate(-9f).shadow(10.dp, shape).clip(shape).background(if (on) Color(0xFFD8E2FA) else edge)
            .border(if (on || c.dark) 2.dp else 1.dp, ring, shape),
    ) {
        Box(Modifier.fillMaxSize().padding(bottom = 5.dp).clip(shape).background(Color.White).padding(11.dp)) {
            val pip = if (on) c.acc else Color(0xFF1C2235)
            Column(Modifier.fillMaxSize(), verticalArrangement = Arrangement.SpaceBetween) {
                for (row in 0..2) {
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                        for (col in 0..2) {
                            val show = (row + col) % 2 == 0 // پنج خال: چهار گوشه و وسط
                            Box(Modifier.size(7.5.dp).clip(CircleShape).background(if (show) pip else Color.Transparent))
                        }
                    }
                }
            }
        }
    }
}

/** بخشی که هنوز ساخته نشده: همان سربرگ و یک پیام */
@Composable
fun SoonScreen(vm: AppViewModel, title: String, icon: String, text: String, bottom: androidx.compose.ui.unit.Dp) {
    val c = Aso.c
    Column(Modifier.fillMaxSize()) {
        TopBar(title, vm.balance, onCoins = { vm.selectTab(Tab.SHOP) }, Modifier.fillMaxWidth())
        Column(
            Modifier.fillMaxSize().padding(start = 24.dp, end = 24.dp, bottom = bottom),
            verticalArrangement = Arrangement.Center, horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Box(Modifier.size(72.dp).clip(CircleShape).background(c.accTint), contentAlignment = Alignment.Center) { Ic(icon, size = 34.dp, tint = c.acc) }
            Spacer(Modifier.height(14.dp))
            Text("به‌زودی 🚧", style = rokh(21f, 30f), color = c.ink)
            Text(text, style = peyda(14f, 24f), color = c.inkMuted, modifier = Modifier.padding(top = 4.dp))
        }
    }
}
