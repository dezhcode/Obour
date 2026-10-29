package dezhcode.asotas.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import dezhcode.asotas.AppViewModel
import dezhcode.asotas.HomeState
import dezhcode.asotas.Tab
import dezhcode.asotas.ThemeMode
import dezhcode.asotas.core.AccountKind
import dezhcode.asotas.fa
import dezhcode.asotas.fd

/** فروشگاه: فعلا جایزهٔ روزانه؛ طرح میز و ورق حکم در مرحلهٔ بعد (shop.html) */
@Composable
fun ShopScreen(vm: AppViewModel, bottom: Dp) {
    val me = (vm.home as? HomeState.Ready)?.me
    Column(Modifier.fillMaxSize()) {
        TopBar("فروشگاه", vm.balance, onCoins = {}, Modifier.fillMaxWidth())
        Column(
            Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(PaddingValues(start = 16.dp, end = 16.dp, top = 8.dp, bottom = bottom + 24.dp)),
            verticalArrangement = Arrangement.spacedBy(20.dp),
        ) {
            if (me != null) DailyCard(me.daily, vm.busy, vm::claimDaily)
            Soon("طرح میز و ورق حکم", "فروشگاه ظاهر تو مرحلهٔ بعد میاد")
        }
    }
}

/** پروفایل: کارنامه، حساب و ورود، پوسته (بخشی از profile.html؛ بقیه در مرحلهٔ بعد) */
@Composable
fun ProfileScreen(vm: AppViewModel, bottom: Dp) {
    val c = Aso.c
    val me = (vm.home as? HomeState.Ready)?.me
    Column(Modifier.fillMaxSize()) {
        TopBar("پروفایل", vm.balance, onCoins = { vm.selectTab(Tab.SHOP) }, Modifier.fillMaxWidth())
        if (me == null) return@Column
        Column(
            Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(PaddingValues(start = 16.dp, end = 16.dp, top = 8.dp, bottom = bottom + 24.dp)),
            verticalArrangement = Arrangement.spacedBy(20.dp),
        ) {
            AsoCard(Modifier.fillMaxWidth()) {
                Column(Modifier.fillMaxWidth(), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Face(me.name, me.av, me.pic, size = 84.dp)
                    Text(me.name, style = rokh(22f, 30f), color = c.ink)
                    if (me.bio.isNotBlank()) Text(me.bio, style = peyda(13f, 20f), color = c.inkMuted, textAlign = TextAlign.Center)
                    Row(Modifier.fillMaxWidth().padding(top = 8.dp), horizontalArrangement = Arrangement.SpaceEvenly) {
                        Stat(me.level.lv.fd(), "سطح")
                        Stat(me.games.fa(), "بازی")
                        Stat(me.wins.fa(), "برد")
                        Stat(me.coins.fa(), "سکه")
                    }
                    Btn("عوض کردن یوزرنیم", vm::openNameEdit, Modifier.padding(top = 8.dp), kind = BtnKind.Light, small = true, icon = "edit")
                }
            }
            Section("پوسته") {
                val seg = RoundedCornerShape(22.dp)
                Row(Modifier.fillMaxWidth().clip(seg).background(c.surfaceSunk).padding(5.dp), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    listOf(ThemeMode.AUTO to "خودکار", ThemeMode.LIGHT to "روشن", ThemeMode.DARK to "تیره").forEach { (m, label) ->
                        val on = vm.theme == m
                        val shape = RoundedCornerShape(16.dp)
                        Box(
                            Modifier.weight(1f).clip(shape).background(if (on) c.surface else androidx.compose.ui.graphics.Color.Transparent)
                                .then(if (on) Modifier.lined(shape) else Modifier).press { vm.chooseTheme(m) }.padding(vertical = 8.dp),
                            contentAlignment = Alignment.Center,
                        ) { Text(label, style = peyda(14f, 20f, 800), color = if (on) c.ink else c.inkMuted) }
                    }
                }
            }
            Section("حساب") {
                when (me.account.kind) {
                    AccountKind.GUEST -> {
                        Text("الان مهمونی. با تلگرام یا ایمیل بیا تو تا بازیا و رفیقا و سکه‌هات همیشه بمونن", style = peyda(13.5f, 22f), color = c.inkMuted)
                        Btn("ورود به حساب", vm::openLogin, Modifier.fillMaxWidth(), icon = "user")
                    }
                    AccountKind.EMAIL, AccountKind.TELEGRAM -> {
                        Text(
                            if (me.account.kind == AccountKind.TELEGRAM) "با حساب تلگرامت وارد شدی" else "با ایمیل ${me.account.email.orEmpty()} وارد شدی",
                            style = peyda(13.5f, 22f), color = c.inkMuted,
                        )
                        Btn("خروج از حساب", vm::logout, Modifier.fillMaxWidth(), kind = BtnKind.DangerSoft, icon = "exit")
                    }
                }
            }
        }
    }
}

@Composable
private fun Stat(value: String, label: String) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(value, style = peyda(18f, 26f, 800), color = Aso.c.ink)
        Text(label, style = peyda(12f, 18f), color = Aso.c.inkMuted)
    }
}

@Composable
private fun Section(title: String, content: @Composable () -> Unit) {
    AsoCard(Modifier.fillMaxWidth()) {
        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text(title, style = rokh(17f, 26f), color = Aso.c.ink)
            content()
        }
    }
}

@Composable
private fun Soon(title: String, text: String) {
    val c = Aso.c
    val shape = RoundedCornerShape(20.dp)
    Row(
        Modifier.fillMaxWidth().clip(shape).background(c.surfaceSunk).padding(14.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Ic("cards", size = 24.dp, tint = c.inkMuted)
        Column {
            Text(title, style = peyda(14f, 21f, 800), color = c.ink)
            Text(text, style = peyda(12f, 18f), color = c.inkMuted)
        }
    }
}
