package dezhcode.asotas.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.ExperimentalMaterial3Api
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
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp
import dezhcode.asotas.AppViewModel
import dezhcode.asotas.HomeState
import dezhcode.asotas.core.NameCheck
import dezhcode.asotas.nameErrorText
import kotlinx.coroutines.delay

/** برگهٔ یوزرنیم (gc.css: «برگهٔ یوزرنیم»): نوشتن، بررسی با سرور و پیشنهاد اگر گرفته شده */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun NameSheet(vm: AppViewModel) {
    if (!vm.nameEdit) return
    val c = Aso.c
    val current = (vm.home as? HomeState.Ready)?.me?.name.orEmpty()
    var name by remember { mutableStateOf(current) }
    var check by remember { mutableStateOf<NameCheck?>(null) }
    LaunchedEffect(name) {
        check = null
        if (name.isBlank() || name == current) return@LaunchedEffect
        delay(400)
        check = vm.checkName(name)
    }
    ModalBottomSheet(onDismissRequest = vm::closeNameEdit, sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
        containerColor = c.surface) {
        Column(Modifier.fillMaxWidth().padding(horizontal = 20.dp).padding(bottom = 20.dp).navigationBarsPadding(),
            verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text("یوزرنیمت", style = rokh(22f, 30f), color = c.ink)
            Text("حرف انگلیسی و عدد و _ ؛ بقیه با همین اسم پیدات می‌کنن", style = peyda(13f, 20f), color = c.inkMuted)
            CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
                OutlinedTextField(
                    value = name, onValueChange = { name = it.trim().take(16) }, singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Ascii, autoCorrectEnabled = false),
                    modifier = Modifier.fillMaxWidth(), textStyle = peyda(17f, 24f, 700),
                )
            }
            val err = check?.error
            when {
                err != null -> Text(nameErrorText(err), style = peyda(13f, 20f, 700), color = c.danger)
                check?.ok == true -> Text("این آزاده ✅", style = peyda(13f, 20f, 700), color = c.success)
            }
            val sug = check?.suggest.orEmpty()
            if (sug.isNotEmpty()) {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    sug.forEach { s ->
                        Text(s, style = peyda(13f, 20f, 800), color = c.accDeep,
                            modifier = Modifier.clip(CircleShape).background(c.accTint).press { name = s }.padding(horizontal = 12.dp, vertical = 8.dp))
                    }
                }
            }
            Btn("ذخیره", { vm.saveName(name) }, Modifier.fillMaxWidth(), enabled = !vm.busy && name.isNotBlank() && name != current && check?.ok != false)
        }
    }
}
