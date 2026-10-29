package dezhcode.asotas

import android.content.ActivityNotFoundException
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.runtime.LaunchedEffect
import androidx.lifecycle.viewmodel.compose.viewModel
import dezhcode.asotas.ui.AsoTasTheme
import dezhcode.asotas.ui.HomeScreen
import dezhcode.asotas.ui.LoginSheet

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            val vm: AppViewModel = viewModel()
            LaunchedEffect(vm) {
                vm.toasts.collect { Toast.makeText(this@MainActivity, it, Toast.LENGTH_SHORT).show() }
            }
            AsoTasTheme {
                HomeScreen(vm)
                LoginSheet(vm, openLink = ::openLink)
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
