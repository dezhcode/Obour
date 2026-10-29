package dezhcode.asotas

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import dezhcode.asotas.core.ApiException
import dezhcode.asotas.core.Client
import dezhcode.asotas.core.Lobby
import dezhcode.asotas.core.MatchView
import dezhcode.asotas.core.QueueState
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

/** برگهٔ انتظار: صف ناشناس یا میز دعوت (ludo-lobby.html: queueLoop و lobbyLoop) */
sealed interface Waiting {
    data class Queue(val game: String, val q: QueueState) : Waiting
    data class Table(val game: String, val matchId: String, val lobby: Lobby, val need: Int, val mode: String) : Waiting
}

/** بازی در جریان روی صفحه */
data class Playing(val game: String, val matchId: String)

/** حریف در لابی: آنلاین، دوستان (لینک دعوت) یا ربات */
enum class Who(val label: String, val icon: String, val desc: String, val go: String, val goIcon: String) {
    ONLINE("آنلاین", "globe", "با بازیکنای واقعی و ناشناس", "پیدا کردن حریف", "play"),
    FRIENDS("دوستان", "link", "لینک دعوت می‌سازی و واسه رفیقات می‌فرستی", "ساختن لینک دعوت", "link"),
    BOT("ربات", "bot", "تمرین همیشه آزاد و بی‌معطلی", "شروع با ربات", "play"),
}

/** لابی ها، صف، میز دعوت و شمارش معکوس؛ برای همهٔ بازی ها */
class PlayModel(private val scope: CoroutineScope, private val client: Client, private val toast: (String) -> Unit, private val refresh: () -> Unit) {
    /** لابی باز (شناسهٔ بازی) */
    var lobby by mutableStateOf<String?>(null)
        private set
    var waiting by mutableStateOf<Waiting?>(null)
        private set
    var countdown by mutableStateOf<Int?>(null)
        private set
    var playing by mutableStateOf<Playing?>(null)
        private set
    var busy by mutableStateOf(false)
        private set
    private var loop: Job? = null

    fun openLobby(game: String) {
        lobby = game
    }

    fun closeLobby() {
        lobby = null
    }

    fun closeGame() {
        playing = null
        refresh()
    }

    private fun stop() {
        loop?.cancel()
        loop = null
    }

    /** شروع از لابی: حریف و تنظیم میز (players، pawns، ...)؛ رتبه ای فقط با حریف آنلاین */
    fun start(game: String, who: Who, cfg: Map<String, Any>, ranked: Boolean) {
        if (busy) return
        val json = org.json.JSONObject(cfg).apply {
            put("mode", if (ranked && who == Who.ONLINE) "ranked" else "free")
            if (who == Who.BOT) put("solo", true)
        }.toString()
        scope.launch {
            busy = true
            try {
                when (who) {
                    Who.BOT -> {
                        val q = io { client.queueJoin(game, json) }
                        if (q.state == "matched" && q.matchId != null) go(game, q.matchId!!) else queueLoop(game, q)
                    }
                    Who.ONLINE -> queueLoop(game, io { client.queueJoin(game, json) })
                    Who.FRIENDS -> tableLoop(game, io { client.inviteCreate(game, json) }.matchId)
                }
                refresh()
            } catch (e: ApiException) {
                toast(errorText(e))
            } finally {
                busy = false
            }
        }
    }

    /** نشستن سر میز دعوت با کد (کارت دعوت در چت یا لینک) */
    fun join(game: String, code: String) {
        scope.launch {
            try {
                tableLoop(game, io { client.inviteJoin(game, code) })
            } catch (e: ApiException) {
                toast(errorText(e))
            }
        }
    }

    /** ادامهٔ میزی که الان دارم (خانه، میزای دیگه‌ت، کارت دعوت خودم) */
    fun resume(game: String, matchId: String?, kind: String) {
        scope.launch {
            try {
                when {
                    kind == "queue" -> queueLoop(game, io { client.queueStatus(game) })
                    matchId == null -> openLobby(game)
                    else -> {
                        val v = io { client.matchView(game, matchId, 0) }
                        when (v.status) {
                            "playing" -> playing = Playing(game, matchId)
                            "lobby" -> tableLoop(game, matchId)
                            else -> openLobby(game)
                        }
                    }
                }
            } catch (e: ApiException) {
                toast(errorText(e))
            }
        }
    }

    private fun queueLoop(game: String, first: QueueState) {
        stop()
        loop = scope.launch {
            var q = first
            while (isActive) {
                when {
                    q.state == "matched" && q.matchId != null -> { waiting = null; go(game, q.matchId!!); return@launch }
                    q.state != "waiting" -> { waiting = null; return@launch }
                }
                waiting = Waiting.Queue(game, q)
                delay(1500)
                q = try { io { client.queueStatus(game) } } catch (e: ApiException) { toast(errorText(e)); q }
            }
        }
    }

    private fun tableLoop(game: String, matchId: String) {
        stop()
        loop = scope.launch {
            while (isActive) {
                val v: MatchView = try { io { client.matchView(game, matchId, 0) } } catch (e: ApiException) {
                    toast(errorText(e)); waiting = null; return@launch
                }
                when (v.status) {
                    "playing" -> { waiting = null; go(game, matchId); return@launch }
                    "cancelled" -> { waiting = null; toast("سازنده میزو بست"); refresh(); return@launch }
                }
                val l = v.lobby ?: run { waiting = null; return@launch }
                waiting = Waiting.Table(game, matchId, l, v.players.toInt(), v.mode)
                delay(1500)
            }
        }
    }

    fun fillWithBots() {
        val w = waiting
        scope.launch {
            try {
                when (w) {
                    is Waiting.Queue -> io { client.queueBots(w.game) }.let { if (it.state == "matched" && it.matchId != null) { stop(); waiting = null; go(w.game, it.matchId!!) } }
                    is Waiting.Table -> io { client.lobbyStart(w.game, w.matchId) }
                    null -> Unit
                }
            } catch (e: ApiException) {
                toast(errorText(e))
            }
        }
    }

    /** بی خیال صف / بلند شدن از میز / بستن میز */
    fun cancelWaiting() {
        val w = waiting ?: return
        stop()
        waiting = null
        scope.launch {
            try {
                when (w) {
                    is Waiting.Queue -> io { client.queueLeave(w.game) }
                    is Waiting.Table -> io { client.leaveMatch(w.game, w.matchId) }
                }
            } catch (e: ApiException) {
                toast(errorText(e))
            }
            refresh()
        }
    }

    /** «میز حاضره!» ۳، ۲، ۱ و بعد صفحهٔ بازی */
    private suspend fun go(game: String, matchId: String) {
        for (n in 3 downTo 1) {
            countdown = n
            delay(650)
        }
        countdown = null
        lobby = null
        playing = Playing(game, matchId)
    }
}

/** میز منچ باز (ludo.js): هر ۰٫۹ ثانیه میز از سرور؛ تاس و حرکت به سرور فرستاده می شود */
class LudoModel(private val client: Client, val matchId: String, private val toast: (String) -> Unit) {
    var view by mutableStateOf<MatchView?>(null)
        private set
    var acting by mutableStateOf(false)
        private set
    var failed by mutableStateOf<String?>(null)
        private set
    private val since: Long get() = view?.ludo?.seq ?: 0L

    suspend fun poll() {
        try {
            merge(io { client.matchView("ludo", matchId, since) })
        } catch (e: ApiException) {
            if (view == null) failed = errorText(e)
        }
    }

    /** رویدادها فقط از since به بعد می آیند؛ وضعیت همیشه کامل است */
    private fun merge(v: MatchView) {
        view = v
    }

    suspend fun act(action: String, k: Long? = null) {
        if (acting) return
        acting = true
        try {
            merge(io { client.act("ludo", matchId, action, k, since) })
        } catch (e: ApiException) {
            toast(errorText(e))
        } finally {
            acting = false
        }
    }

    suspend fun leave() {
        try { io { client.leaveMatch("ludo", matchId) } } catch (e: ApiException) { toast(errorText(e)) }
    }
}
