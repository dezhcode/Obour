package dezhcode.asotas.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import dezhcode.asotas.AppViewModel
import dezhcode.asotas.R
import org.json.JSONArray

/** یک بخش راهنما (ساخته شده از help.html با tools/gen_help.py) */
private class HelpSection(val id: String, val title: String, val lead: List<String>, val steps: List<Triple<String, String, List<String>>>)

private fun loadHelp(ctx: android.content.Context): List<HelpSection> {
    val raw = ctx.resources.openRawResource(R.raw.help).bufferedReader(Charsets.UTF_8).use { it.readText() }
    val arr = JSONArray(raw)
    fun strings(a: JSONArray?) = List(a?.length() ?: 0) { a!!.getString(it) }
    return List(arr.length()) { i ->
        val s = arr.getJSONObject(i)
        val st = s.getJSONArray("steps")
        HelpSection(s.getString("id"), s.getString("title"), strings(s.optJSONArray("lead")),
            List(st.length()) { j -> st.getJSONObject(j).let { Triple(it.optString("icon", "info"), it.optString("title"), strings(it.optJSONArray("lines"))) } })
    }
}

/** راهنما (help.html): قانون هر بازی، قانون سکه و بازی بی‌کلک؛ focus = شناسهٔ بخش (hLudo، hClub، ...) */
@Composable
fun HelpScreen(vm: AppViewModel, focus: String) {
    val c = Aso.c
    val ctx = LocalContext.current
    val sections = remember { loadHelp(ctx) }
    val list = rememberLazyListState()
    BackHandler { vm.closeHelp() }
    LaunchedEffect(focus) {
        val i = sections.indexOfFirst { it.id == focus }
        if (i >= 0) list.scrollToItem(i)
    }
    Column(Modifier.fillMaxSize().background(c.ground).statusBarsPadding()) {
        Row(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp), verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            IconBtn("back", onClick = vm::closeHelp)
            Text("راهنما", style = rokh(24f, 32f), color = c.ink)
        }
        LazyColumn(state = list, modifier = Modifier.fillMaxSize().navigationBarsPadding(),
            contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 8.dp, bottom = 32.dp), verticalArrangement = Arrangement.spacedBy(24.dp)) {
            itemsIndexed(sections, key = { _, s -> s.id }) { _, s ->
                Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Text(s.title, style = rokh(17f, 26f), color = c.ink)
                    val shape = RoundedCornerShape(28.dp)
                    Column(Modifier.fillMaxWidth().clip(shape).background(c.surface).lined(shape).padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                        s.lead.forEach { Text(it, style = peyda(14f, 23f), color = c.ink) }
                        s.steps.forEachIndexed { i, (icon, title, lines) ->
                            if (i > 0 || s.lead.isNotEmpty()) HorizontalDivider(color = c.line)
                            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                                Box(Modifier.size(40.dp).clip(RoundedCornerShape(13.dp)).background(c.accTint), contentAlignment = Alignment.Center) {
                                    Ic(icon, size = 21.dp, tint = c.acc)
                                }
                                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                                    if (title.isNotEmpty()) Text(title, style = peyda(14.5f, 22f, 800), color = c.ink)
                                    lines.forEach { Text(it, style = peyda(13.5f, 22f), color = c.inkMuted) }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
