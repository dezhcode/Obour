package dezhcode.asotas

import android.os.Build
import android.content.pm.PackageManager
import android.Manifest
import android.content.ActivityNotFoundException
import android.content.Intent
import android.graphics.Color
import android.net.Uri
import android.os.Bundle
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.SystemBarStyle
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.runtime.LaunchedEffect
import androidx.lifecycle.viewmodel.compose.viewModel
import dezhcode.asotas.ui.AppShell
import dezhcode.asotas.ui.AsoTasTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        // نوتیفیکیشن نوبت بازی و پاپ آپ ها: اندروید ۱۳ به بعد یک بار اجازه می خواهد
        Push.channels(this)
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 7)
        }
        setContent {
            val vm: AppViewModel = viewModel()
            val dark = when (vm.theme) {
                ThemeMode.AUTO -> isSystemInDarkTheme()
                ThemeMode.LIGHT -> false
                ThemeMode.DARK -> true
            }
            // آیکن های نوار وضعیت و ناوبری گوشی هم رنگ پوسته
            LaunchedEffect(dark) {
                val style = if (dark) SystemBarStyle.dark(Color.TRANSPARENT) else SystemBarStyle.light(Color.TRANSPARENT, Color.TRANSPARENT)
                enableEdgeToEdge(statusBarStyle = style, navigationBarStyle = style)
            }
            AsoTasTheme(dark) {
                AppShell(vm, openLink = ::openLink)
            }
        }
    }

    /** لینک t.me: اپ تلگرام اگر نصب است، وگرنه مرورگر */
    private fun openLink(url: String) {
        try {
            startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
        } catch (_: ActivityNotFoundException) {
            Toast.makeText(this, "تلگرام یا مرورگری روی گوشی پیدا نشد", Toast.LENGTH_LONG).show()
        }
    }
}
