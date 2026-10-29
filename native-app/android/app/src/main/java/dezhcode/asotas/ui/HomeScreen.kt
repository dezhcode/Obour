package dezhcode.asotas.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import dezhcode.asotas.AppViewModel
import dezhcode.asotas.GAMES
import dezhcode.asotas.Game
import dezhcode.asotas.HomeState
import dezhcode.asotas.core.AccountKind
import dezhcode.asotas.core.Daily
import dezhcode.asotas.core.Me
import dezhcode.asotas.fa

@Composable
fun HomeScreen(vm: AppViewModel) {
    Box(
        Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .safeDrawingPadding(),
    ) {
        when (val s = vm.home) {
            HomeState.Loading -> CircularProgressIndicator(Modifier.align(Alignment.Center))
            is HomeState.Failed -> Failed(s.message, vm::refresh, Modifier.align(Alignment.Center))
            is HomeState.Ready -> Ready(s.me, vm)
        }
    }
}

@Composable
private fun Failed(message: String, retry: () -> Unit, modifier: Modifier) {
    Column(modifier.padding(24.dp), horizontalAlignment = Alignment.CenterHorizontally) {
        Text("😵", fontSize = 48.sp)
        Spacer(Modifier.height(12.dp))
        Text(message, textAlign = TextAlign.Center, style = MaterialTheme.typography.bodyLarge)
        Spacer(Modifier.height(16.dp))
        Button(onClick = retry) { Text("دوباره امتحان کن") }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun Ready(me: Me, vm: AppViewModel) {
    PullToRefreshBox(isRefreshing = false, onRefresh = vm::refresh, modifier = Modifier.fillMaxSize()) {
        Column(
            Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            Header(me)
            if (me.maintenance) Banner("داریم آپدیت می‌کنیم بعضی میزها چند دقیقه دیگه باز می‌شن")
            if (me.notice.isNotBlank()) Banner(me.notice)
            if (me.banned) Banner("شرمنده داش حسابت تو AsoTas بسته شده")
            DailyCard(me.daily, busy = vm.busy, claim = vm::claimDaily)
            Text("بازی‌ها", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Black)
            GAMES.chunked(2).forEach { row ->
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    row.forEach { g -> GameTile(g, Modifier.weight(1f)) { vm.gameSoon(g) } }
                }
            }
            AccountCard(me, login = vm::openLogin, logout = vm::logout)
        }
    }
}

@Composable
private fun Header(me: Me) {
    Card {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(
                Modifier
                    .size(56.dp)
                    .clip(CircleShape)
                    .background(Palette.Violet),
                contentAlignment = Alignment.Center,
            ) {
                Text(me.name.take(1).uppercase(), color = Color.White, fontSize = 24.sp, fontWeight = FontWeight.Black)
            }
            Column(
                Modifier
                    .weight(1f)
                    .padding(horizontal = 12.dp),
            ) {
                Text(me.name, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Black)
                Text(
                    "${me.games.fa()} بازی · ${me.wins.fa()} برد",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            Surface(shape = RoundedCornerShape(50), color = Palette.Coin) {
                Text(
                    "🪙 ${me.coins.fa()}",
                    color = Palette.CoinInk,
                    fontWeight = FontWeight.Black,
                    modifier = Modifier.padding(horizontal = 12.dp, vertical = 6.dp),
                )
            }
        }
    }
}

@Composable
private fun Banner(text: String) {
    Surface(shape = RoundedCornerShape(16.dp), color = Palette.SkyTint, modifier = Modifier.fillMaxWidth()) {
        Text(text, Modifier.padding(14.dp), color = Palette.SkyDeep)
    }
}

@Composable
private fun DailyCard(daily: Daily, busy: Boolean, claim: () -> Unit) {
    Card {
        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text("جایزهٔ روزانه", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Black)
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                daily.plan.forEachIndexed { i, coins ->
                    val day = i + 1L
                    val got = day <= daily.day
                    val today = !daily.claimed && day == daily.next
                    Surface(
                        shape = RoundedCornerShape(12.dp),
                        color = when {
                            got -> Palette.SuccessTint
                            today -> Palette.Coin
                            else -> Palette.GroundDeep
                        },
                        modifier = Modifier.weight(1f),
                    ) {
                        Column(Modifier.padding(vertical = 8.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                            Text("روز ${day.fa()}", fontSize = 11.sp, color = Palette.Muted)
                            Text(if (got) "✓" else coins.fa(), fontWeight = FontWeight.Black)
                        }
                    }
                }
            }
            Button(
                onClick = claim,
                enabled = !daily.claimed && !busy,
                modifier = Modifier.fillMaxWidth(),
                colors = ButtonDefaults.buttonColors(containerColor = Palette.Coin, contentColor = Palette.CoinInk),
            ) {
                Text(if (daily.claimed) "فردا دوباره سر بزن 😉" else "بگیرش", fontWeight = FontWeight.Black)
            }
        }
    }
}

@Composable
private fun GameTile(game: Game, modifier: Modifier, onClick: () -> Unit) {
    Surface(
        shape = RoundedCornerShape(20.dp),
        color = game.color,
        modifier = modifier
            .aspectRatio(1.4f)
            .clip(RoundedCornerShape(20.dp))
            .clickable(onClick = onClick),
    ) {
        Column(
            Modifier.padding(14.dp),
            verticalArrangement = Arrangement.SpaceBetween,
        ) {
            Text(game.emoji, fontSize = 30.sp)
            Text(game.title, color = Color.White, fontWeight = FontWeight.Black, fontSize = 17.sp)
        }
    }
}

@Composable
private fun AccountCard(me: Me, login: () -> Unit, logout: () -> Unit) {
    Card {
        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text("حساب", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Black)
            when (me.account.kind) {
                AccountKind.GUEST -> {
                    Text(
                        "الان مهمونی. با تلگرام یا ایمیل بیا تو تا بازیا و رفیقا و سکه‌هات همیشه بمونن",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    Button(onClick = login, modifier = Modifier.fillMaxWidth()) { Text("ورود به حساب") }
                }
                AccountKind.EMAIL, AccountKind.TELEGRAM -> {
                    Text(
                        if (me.account.kind == AccountKind.TELEGRAM) "با حساب تلگرامت وارد شدی ✈️"
                        else "با ایمیل ${me.account.email.orEmpty()} وارد شدی ✉️",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    OutlinedButton(onClick = logout, modifier = Modifier.fillMaxWidth()) { Text("خروج از حساب") }
                }
            }
        }
    }
}

@Composable
private fun Card(content: @Composable () -> Unit) {
    Surface(
        shape = RoundedCornerShape(24.dp),
        color = MaterialTheme.colorScheme.surface,
        shadowElevation = 1.dp,
        modifier = Modifier.fillMaxWidth(),
    ) {
        Box(Modifier.padding(16.dp)) { content() }
    }
}
