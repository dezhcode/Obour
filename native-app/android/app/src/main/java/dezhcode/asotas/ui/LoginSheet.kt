package dezhcode.asotas.ui

import android.os.SystemClock
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.SheetValue
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay
import dezhcode.asotas.AppViewModel
import dezhcode.asotas.LoginStep
import dezhcode.asotas.fa
import dezhcode.asotas.toLatinDigits

private val TelegramBlue = androidx.compose.ui.graphics.Color(0xFF229ED9)

/** برگهٔ ورود: تلگرام (لینک ربات و تأیید) یا ایمیل (کد ۶ رقمی)؛ همان روند مینی اپ در gc.js */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun LoginSheet(vm: AppViewModel, openLink: (String) -> Unit) {
    val step = vm.login
    if (step == LoginStep.Closed) return
    val welcome = step is LoginStep.Choose && step.welcome
    ModalBottomSheet(
        onDismissRequest = vm::closeLogin,
        sheetState = rememberModalBottomSheetState(
            skipPartiallyExpanded = true,
            // برگهٔ خوش آمد فقط با «فعلاً مهمون می‌مونم» بسته می شود
            confirmValueChange = { it != SheetValue.Hidden || !welcome },
        ),
    ) {
        Column(
            Modifier
                .fillMaxWidth()
                .padding(horizontal = 20.dp)
                .padding(bottom = 20.dp)
                .navigationBarsPadding(),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            when (step) {
                is LoginStep.Choose -> Choose(vm, step.welcome, openLink)
                is LoginStep.Email -> EmailStep(vm, step.prefill)
                is LoginStep.Code -> CodeStep(vm, step)
                is LoginStep.Telegram -> TelegramStep(vm, step, openLink)
                LoginStep.Closed -> Unit
            }
        }
    }
}

@Composable
private fun Title(text: String) {
    Text(text, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Black)
}

@Composable
private fun Lead(text: String) {
    Text(text, color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.bodyLarge)
}

@Composable
private fun Message(text: String?) {
    if (!text.isNullOrEmpty()) Text(text, color = MaterialTheme.colorScheme.error)
}

@Composable
private fun Choose(vm: AppViewModel, welcome: Boolean, openLink: (String) -> Unit) {
    Title(if (welcome) "خوش اومدی 👋" else "ورود به حساب")
    Lead("با تلگرام یا ایمیل بیا تو تا بازیا و رفیقا و سکه‌هات همیشه بمونن حتی اگه گوشیتو عوض کنی")
    Button(
        onClick = { vm.telegramStart(openLink) },
        enabled = !vm.busy,
        modifier = Modifier.fillMaxWidth(),
        colors = ButtonDefaults.buttonColors(containerColor = TelegramBlue),
    ) { Text("✈️  ورود با تلگرام") }
    OutlinedButton(onClick = { vm.emailStep() }, modifier = Modifier.fillMaxWidth()) { Text("✉️  ورود با ایمیل") }
    Message(vm.loginMessage)
    Text(
        "قبلاً تو ربات تلگرام AsoTas بازی کردی؟ با تلگرام بیا تا همون حساب بیاد",
        fontSize = 13.sp,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
    )
    if (welcome) {
        TextButton(onClick = vm::closeLogin, modifier = Modifier.fillMaxWidth()) { Text("فعلاً مهمون می‌مونم") }
    }
}

/** فیلد ایمیل و کد چپ به چپ است، حتی وسط صفحهٔ راست به چپ */
@Composable
private fun Ltr(content: @Composable () -> Unit) {
    CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr, content = content)
}

@Composable
private fun EmailStep(vm: AppViewModel, prefill: String) {
    var email by rememberSaveable { mutableStateOf(prefill) }
    val focus = remember { FocusRequester() }
    LaunchedEffect(Unit) { focus.requestFocus() }
    Title("ورود با ایمیل")
    Lead("ایمیلتو بزن تا یه کد ۶ رقمی برات بفرستیم")
    Ltr {
        OutlinedTextField(
            value = email,
            onValueChange = { email = it.trim() },
            singleLine = true,
            placeholder = { Text("you@gmail.com") },
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email, imeAction = ImeAction.Send, autoCorrectEnabled = false),
            keyboardActions = KeyboardActions(onSend = { vm.emailSend(email) }),
            modifier = Modifier
                .fillMaxWidth()
                .focusRequester(focus),
        )
    }
    Message(vm.loginMessage)
    Button(onClick = { vm.emailSend(email) }, enabled = email.isNotBlank() && !vm.busy, modifier = Modifier.fillMaxWidth()) {
        Text("بفرست کد")
    }
    TextButton(onClick = vm::openLogin, modifier = Modifier.fillMaxWidth()) { Text("برگشت") }
}

@Composable
private fun CodeStep(vm: AppViewModel, step: LoginStep.Code) {
    var code by rememberSaveable(step.email) { mutableStateOf("") }
    var left by remember { mutableLongStateOf(0L) }
    val focus = remember { FocusRequester() }
    LaunchedEffect(Unit) { focus.requestFocus() }
    LaunchedEffect(step.resendAt) {
        while (true) {
            left = ((step.resendAt - SystemClock.elapsedRealtime()) / 1000).coerceAtLeast(0)
            if (left == 0L) break
            delay(1000)
        }
    }
    Title("کد ورود")
    Lead("کد ۶ رقمی‌ای که به ${step.email} فرستادیم رو بزن")
    Ltr {
        OutlinedTextField(
            value = code,
            onValueChange = {
                code = it.toLatinDigits().filter(Char::isDigit).take(6)
                if (code.length == 6) vm.emailVerify(step.email, code)
            },
            singleLine = true,
            placeholder = { Text("••••••") },
            textStyle = MaterialTheme.typography.headlineSmall.copy(textAlign = TextAlign.Center, letterSpacing = 8.sp),
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword, imeAction = ImeAction.Done),
            modifier = Modifier
                .fillMaxWidth()
                .focusRequester(focus),
        )
    }
    Message(vm.loginMessage)
    Button(
        onClick = { vm.emailVerify(step.email, code) },
        enabled = code.length == 6 && !vm.busy,
        modifier = Modifier.fillMaxWidth(),
    ) { Text("بزن بریم") }
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
        TextButton(onClick = { vm.emailResend(step.email) }, enabled = left == 0L && !vm.busy) {
            Text(if (left > 0) "دوباره بفرست (${left.fa()})" else "دوباره بفرست")
        }
        TextButton(onClick = { vm.emailStep(step.email) }) { Text("ایمیلو اشتباه زدی؟") }
    }
    Text("ایمیل نیومد؟ پوشهٔ اسپم رو هم یه نگاه بنداز", fontSize = 13.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
}

@Composable
private fun TelegramStep(vm: AppViewModel, step: LoginStep.Telegram, openLink: (String) -> Unit) {
    Title("ورود با تلگرام")
    if (step.failed == null) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            CircularProgressIndicator(Modifier.size(22.dp), strokeWidth = 3.dp)
            Spacer(Modifier.size(10.dp))
            Text("منتظر تأیید تو تلگرامیم…", fontWeight = FontWeight.Bold)
        }
        Lead("تو ربات AsoTas «آره خودمم» رو بزن و برگرد همین‌جا خودش وارد می‌شی")
        Button(
            onClick = { openLink(step.link) },
            modifier = Modifier.fillMaxWidth(),
            colors = ButtonDefaults.buttonColors(containerColor = TelegramBlue),
        ) { Text("✈️  باز کردن تلگرام") }
    } else {
        Message(step.failed)
        Button(
            onClick = { vm.telegramStart(openLink) },
            enabled = !vm.busy,
            modifier = Modifier.fillMaxWidth(),
            colors = ButtonDefaults.buttonColors(containerColor = TelegramBlue),
        ) { Text("یه بار دیگه") }
    }
    Message(vm.loginMessage)
    Spacer(Modifier.height(2.dp))
    TextButton(onClick = vm::openLogin, modifier = Modifier.fillMaxWidth()) { Text("برگشت") }
}
