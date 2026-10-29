package dezhcode.asotas.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
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
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Shadow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import dezhcode.asotas.AppViewModel
import dezhcode.asotas.GAMES
import dezhcode.asotas.Game

private val CATS = listOf(Triple("all", "همه", "pad"), Triple("card", "کارتی", "cards"), Triple("board", "تخته‌ای", "dice"), Triple("sport", "ورزشی", "ball"))

/** بازی ها (game_club/webapp/games.html): دسته ها و کارت پهن هر بازی در دنیای خودش */
@Composable
fun GamesScreen(vm: AppViewModel, bottom: Dp) {
    var cat by rememberSaveable { mutableStateOf("all") }
    Column(Modifier.fillMaxSize()) {
        TopBar("بازی‌ها", vm.balance, onCoins = { vm.selectTab(dezhcode.asotas.Tab.SHOP) }, Modifier.fillMaxWidth())
        Column(
            Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(PaddingValues(top = 8.dp, bottom = bottom + 24.dp)),
        ) {
            Row(
                Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()).padding(horizontal = 16.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                CATS.forEach { (id, label, icon) -> Cat(label, icon, id == cat) { cat = id } }
            }
            Column(Modifier.padding(start = 16.dp, end = 16.dp, top = 22.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
                GAMES.filter { cat == "all" || it.cat == cat }.forEach { GameCard(it) { vm.openGame(it) } }
            }
        }
    }
}

@Composable
private fun Cat(label: String, icon: String, on: Boolean, onClick: () -> Unit) {
    val c = Aso.c
    val shape = RoundedCornerShape(12.dp)
    Row(
        Modifier.height(40.dp).clip(shape).background(if (on) c.acc else c.surface)
            .then(if (on) Modifier else Modifier.lined(shape)).press(onClick = onClick).padding(horizontal = 14.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Ic(icon, size = 17.dp, tint = if (on) c.accInk else c.inkMuted)
        Text(label, style = peyda(13.5f, 20f, if (on) 800 else 700), color = if (on) c.accInk else c.ink)
    }
}

private val TitleShadow = Shadow(Color(0x4D000000), androidx.compose.ui.geometry.Offset(0f, 2f), 6f)

@Composable
private fun GameCard(game: Game, onClick: () -> Unit) {
    val shape = RoundedCornerShape(22.dp)
    val sh = GAME_SHADOW[game.id] ?: Color.Black
    Box(Modifier.fillMaxWidth().height(122.dp).press(.985f, onClick = onClick)) {
        Box(Modifier.matchParentSize().shadow(14.dp, shape, ambientColor = sh, spotColor = sh).clip(shape)) {
            GameBackground(game.id)
            // تیرگی از راست (زیر متن) به چپ
            Box(
                Modifier.matchParentSize().background(
                    Brush.horizontalGradient(
                        0f to Color(0xA8000000), .55f to Color(0x47000000), .82f to Color.Transparent,
                        startX = Float.POSITIVE_INFINITY, endX = 0f,
                    ),
                ),
            )
        }
        Column(
            Modifier.align(Alignment.CenterStart).fillMaxWidth(.62f).padding(horizontal = 16.dp, vertical = 14.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            Text(game.title, style = rokh(25f, 32f).copy(shadow = TitleShadow), color = Color.White)
            Text(game.desc, style = peyda(12f, 18f), color = Color.White.copy(alpha = .94f), maxLines = 2)
            Row(Modifier.padding(top = 4.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                game.facts.forEach { f ->
                    Row(
                        Modifier.height(24.dp).clip(RoundedCornerShape(8.dp)).background(Color.White.copy(alpha = .2f))
                            .padding(start = 7.dp, end = 8.dp),
                        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp),
                    ) {
                        Ic(f.icon, size = 13.dp, tint = Color.White)
                        Text(f.text, style = peyda(11.5f, 16f, 700), color = Color.White, maxLines = 1)
                    }
                }
            }
        }
        if (game.tag != null) {
            val hot = game.tag == "محبوب"
            Text(
                game.tag, style = peyda(11f, 22f, 800), color = if (hot) Aso.c.goldInk else Color(0xFF161922),
                modifier = Modifier.align(Alignment.BottomEnd).padding(12.dp).clip(RoundedCornerShape(8.dp))
                    .background(if (hot) Aso.c.gold else Color.White.copy(alpha = .94f)).padding(horizontal = 8.dp),
            )
        }
        GamesOuts(game.id)
    }
}
