package dezhcode.asotas

import android.app.Application
import android.os.Build
import android.os.SystemClock
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import dezhcode.asotas.core.ApiException
import dezhcode.asotas.core.Client
import dezhcode.asotas.core.Friends
import dezhcode.asotas.core.Me
import dezhcode.asotas.core.NameCheck
import dezhcode.asotas.core.TableInfo
import dezhcode.asotas.core.TelegramState

sealed interface HomeState {
    data object Loading : HomeState
    data class Ready(val me: Me) : HomeState
    data class Failed(val message: String) : HomeState
}

/** برگهٔ ورود: انتخاب، ایمیل، کد ۶ رقمی، منتظر تأیید تلگرام */
sealed interface LoginStep {
    data object Closed : LoginStep
    data class Choose(val welcome: Boolean) : LoginStep
    data class Email(val prefill: String = "") : LoginStep
    data class Code(val email: String, val resendAt: Long) : LoginStep
    data class Telegram(val link: String, val failed: String? = null) : LoginStep
}

/** بخش های نوار پایین */
enum class Tab { HOME, FRIENDS, GAMES, SHOP, PROFILE }

/** پوسته مثل مینی اپ: خودکار (مثل گوشی)، روشن یا تیره */
enum class ThemeMode { AUTO, LIGHT, DARK }

class AppViewModel(app: Application) : AndroidViewModel(app) {
    private val client = Client(
        BuildConfig.SERVER_URL,
        app.noBackupFilesDir.absolutePath,
        Build.MODEL.orEmpty().ifBlank { "Android" },
    )
    private val prefs = app.getSharedPreferences("asotas", android.content.Context.MODE_PRIVATE)

    var home by mutableStateOf<HomeState>(HomeState.Loading)
        private set
    var tab by mutableStateOf(Tab.HOME)
        private set
    var theme by mutableStateOf(runCatching { ThemeMode.valueOf(prefs.getString("theme", null) ?: "AUTO") }.getOrDefault(ThemeMode.AUTO))
        private set
    var friends by mutableStateOf<Friends?>(null)
        private set
    /** کارت جایزهٔ روزانه در خانه: اگر امروز گرفته نشده بود (بعد از گرفتن همان جا می ماند) */
    var showDaily by mutableStateOf(false)
        private set
    var nameEdit by mutableStateOf(false)
        private set
    var login by mutableStateOf<LoginStep>(LoginStep.Closed)
        private set
    var busy by mutableStateOf(false)
        private set
    var loginMessage by mutableStateOf<String?>(null)
        private set
    val toasts = MutableSharedFlow<String>(extraBufferCapacity = 4)

    private var telegramJob: Job? = null

    /** موجودی سکه برای سربرگ ها */
    val balance: Long? get() = (home as? HomeState.Ready)?.me?.coins

    init {
        // بار اول: برگهٔ «خوش اومدی» (ورود یا «فعلاً مهمون می‌مونم»)
        if (!client.hasSession()) login = LoginStep.Choose(welcome = true)
        refresh()
    }

    private suspend fun <T> io(block: () -> T): T = withContext(Dispatchers.IO) { block() }

    private fun toast(text: String) {
        toasts.tryEmit(text)
    }

    private fun update(change: (Me) -> Me) {
        (home as? HomeState.Ready)?.let { home = HomeState.Ready(change(it.me)) }
    }

    fun refresh() {
        viewModelScope.launch {
            val before = home
            if (before !is HomeState.Ready) home = HomeState.Loading
            home = try {
                val me = io { client.me() }
                if (before !is HomeState.Ready) showDaily = !me.daily.claimed
                HomeState.Ready(me)
            } catch (e: ApiException) {
                if (before is HomeState.Ready) {
                    toast(errorText(e))
                    before
                } else {
                    HomeState.Failed(errorText(e))
                }
            }
            loadFriends()
        }
    }

    private fun loadFriends() {
        viewModelScope.launch {
            friends = try { io { client.friends() } } catch (e: ApiException) { friends }
        }
    }

    fun selectTab(t: Tab) {
        tab = t
    }

    fun setTheme(m: ThemeMode) {
        theme = m
        prefs.edit().putString("theme", m.name).apply()
    }

    fun claimDaily() {
        if (busy || home !is HomeState.Ready) return
        viewModelScope.launch {
            busy = true
            try {
                val r = io { client.dailyClaim() }
                update { it.copy(coins = r.balance, daily = r.daily) }
                toast("+${r.coins.fa()} سکه ریخت تو کیفت 🎉")
            } catch (e: ApiException) {
                toast(errorText(e))
            } finally {
                busy = false
            }
        }
    }

    fun openGame(game: Game) {
        toast("${game.title} به‌زودی تو برنامهٔ نیتیو میاد 🚧")
    }

    fun openTable(t: TableInfo) {
        game(t.game)?.let(::openGame)
    }

    fun soon(what: String) {
        toast("$what به‌زودی میاد 🚧")
    }

    // ---------- یوزرنیم ----------
    fun hideNameHint() {
        update { it.copy(nameHint = false) }
        viewModelScope.launch { runCatching { io { client.nameSeen() } } }
    }

    fun openNameEdit() {
        nameEdit = true
    }

    fun closeNameEdit() {
        nameEdit = false
    }

    /** بررسی یوزرنیم با سرور؛ خطای شبکه = نامعلوم (null) */
    suspend fun checkName(name: String): NameCheck? = try { io { client.nameCheck(name) } } catch (e: ApiException) { null }

    fun saveName(name: String) {
        if (busy) return
        viewModelScope.launch {
            busy = true
            try {
                val n = io { client.setName(name) }
                update { it.copy(name = n, nameHint = false) }
                nameEdit = false
                toast("حله یوزرنیمت شد $n ✅")
            } catch (e: ApiException) {
                toast(errorText(e))
            } finally {
                busy = false
            }
        }
    }

    // ---------- ورود ----------
    fun openLogin() {
        show(LoginStep.Choose(welcome = false))
    }

    fun closeLogin() {
        show(LoginStep.Closed)
    }

    fun emailStep(prefill: String = "") {
        show(LoginStep.Email(prefill))
    }

    private fun show(step: LoginStep) {
        telegramJob?.cancel()
        loginMessage = null
        busy = false
        login = step
    }

    fun emailSend(email: String) {
        val em = email.trim()
        if (em.isEmpty() || busy) return
        viewModelScope.launch {
            busy = true
            loginMessage = "داریم می‌فرستیم…"
            try {
                val r = io { client.loginEmailStart(em) }
                show(LoginStep.Code(r.email.ifEmpty { em }, SystemClock.elapsedRealtime() + r.resend.coerceAtLeast(1) * 1000))
            } catch (e: ApiException) {
                loginMessage = loginErrorText(e)
            } finally {
                busy = false
            }
        }
    }

    fun emailResend(email: String) {
        emailSend(email)
    }

    fun emailVerify(email: String, code: String) {
        if (code.length != 6 || busy) return
        viewModelScope.launch {
            busy = true
            loginMessage = "یه لحظه…"
            try {
                io { client.loginEmailVerify(email, code) }
                loggedIn()
            } catch (e: ApiException) {
                loginMessage = loginErrorText(e)
                val step = login
                // کد سوخت: دکمهٔ «دوباره بفرست» همین الان باز شود
                if (step is LoginStep.Code && e is ApiException.Server && e.code in setOf("code_tries", "code_expired")) {
                    login = step.copy(resendAt = 0)
                }
            } finally {
                busy = false
            }
        }
    }

    /** لینک ربات را باز می کند و هر ۲ ثانیه نتیجه را می پرسد تا در تلگرام «آره خودمم» زده شود */
    fun telegramStart(open: (String) -> Unit) {
        if (busy) return
        viewModelScope.launch {
            busy = true
            val start = try {
                io { client.loginTelegramStart() }
            } catch (e: ApiException) {
                loginMessage = loginErrorText(e)
                busy = false
                return@launch
            }
            show(LoginStep.Telegram(start.link))
            open(start.link)
            val until = SystemClock.elapsedRealtime() + start.ttl.coerceAtLeast(60) * 1000
            val fail = { text: String -> login = LoginStep.Telegram(start.link, failed = text) }
            telegramJob = launch {
                while (isActive) {
                    delay(2000)
                    val r = try {
                        io { client.loginTelegramCheck(start.poll) }
                    } catch (e: ApiException.Network) {
                        continue
                    } catch (e: ApiException) {
                        loginMessage = loginErrorText(e)
                        continue
                    }
                    when {
                        r.state == TelegramState.OK -> { loggedIn(); break }
                        r.state == TelegramState.DENIED -> { fail("ورود رد شد اگه اشتباهی بود یه بار دیگه بزن"); break }
                        r.state == TelegramState.EXPIRED || SystemClock.elapsedRealtime() > until -> {
                            fail("وقت این لینک تموم شد یه بار دیگه بزن"); break
                        }
                    }
                }
            }
        }
    }

    private fun loggedIn() {
        show(LoginStep.Closed)
        toast("حله وارد شدی ✅")
        home = HomeState.Loading
        refresh()
    }

    fun logout() {
        viewModelScope.launch {
            io { client.logout() }
            home = HomeState.Loading
            refresh()
        }
    }
}
