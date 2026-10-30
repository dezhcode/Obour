package dezhcode.asotas

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import dezhcode.asotas.core.ApiException
import dezhcode.asotas.core.Client
import dezhcode.asotas.core.DmMessage
import dezhcode.asotas.core.Friend
import dezhcode.asotas.core.Person
import dezhcode.asotas.core.Profile
import dezhcode.asotas.core.StyleItem
import dezhcode.asotas.core.Styles
import dezhcode.asotas.core.UserCard
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/** برگه ها و پنجره های روی صفحه (sheet() در gc.js) */
sealed interface Sheet {
    data object AddFriend : Sheet
    data class FriendCard(val friend: Friend, val fromChat: Boolean = false) : Sheet
    data class Invite(val person: Person) : Sheet
    data class Confirm(val title: String, val text: String, val ok: String, val run: () -> Unit) : Sheet
    data class Buy(val item: StyleItem) : Sheet
    data object Bio : Sheet
    data object Cover : Sheet
    data object Notifications : Sheet
}

internal suspend fun <T> io(block: () -> T): T = withContext(Dispatchers.IO) { block() }

/** گفتگوی خصوصی باز (chat.html) */
class ChatState(val uid: String) {
    var user by mutableStateOf<Friend?>(null)
    var relation by mutableStateOf("friend")
    var messages by mutableStateOf<List<DmMessage>>(emptyList())
    var failed by mutableStateOf<String?>(null)
    var sending by mutableStateOf(false)
}

/** دوستان و چت (friends.html، chat.html، social.js) */
class SocialModel(private val scope: CoroutineScope, private val client: Client, private val toast: (String) -> Unit, private val reload: () -> Unit) {
    var chat by mutableStateOf<ChatState?>(null)
        private set

    suspend fun find(name: String): UserCard? = try { io { client.friendFind(name) } } catch (e: ApiException) { null }

    suspend fun card(uid: String): UserCard? = try { io { client.friendUser(uid) } } catch (e: ApiException) { null }

    /** درخواست، قبول، لغو یا رفع بلاک از برگهٔ «افزودن دوست»؛ رابطهٔ تازه یا null */
    suspend fun act(action: String, uid: String): String? = try {
        val rel = io {
            when (action) {
                "req" -> client.friendRequest(uid)
                "acc" -> client.friendAccept(uid)
                "drop" -> client.friendDrop(uid)
                else -> client.friendBlock(uid, false)
            }
        }
        if (action == "req") toast(if (rel == "friend") "دمت گرم حالا رفیقید 🤝" else "درخواست دوستی رفت")
        if (action == "acc") toast("دمت گرم حالا رفیقید 🤝")
        reload()
        rel
    } catch (e: ApiException) {
        toast(errorText(e)); null
    }

    fun accept(uid: String) = scope.launch { act("acc", uid) }
    fun drop(uid: String) = scope.launch { act("drop", uid) }
    fun unblock(uid: String) = scope.launch { act("unblock", uid) }

    fun remove(f: Person, after: () -> Unit) = scope.launch {
        try { io { client.friendDrop(f.uid) }; toast("از رفیقات حذف شد"); reload(); after() } catch (e: ApiException) { toast(errorText(e)) }
    }

    fun block(f: Person, after: () -> Unit) = scope.launch {
        try { io { client.friendBlock(f.uid, true) }; toast("بلاک شد"); reload(); after() } catch (e: ApiException) { toast(errorText(e)) }
    }

    /** دعوت به بازی: میز آزاد ساخته می شود و کارتش در چت دوست می آید */
    fun invite(p: Person, game: String, done: () -> Unit) = scope.launch {
        try {
            val r = io { client.dmInvite(p.uid, game) }
            toast("دعوت ${game(r.game)?.title ?: ""} واسه ${p.name} رفت 🎲")
            done()
            chat?.takeIf { it.uid == p.uid }?.let { pull(it, first = false) }
        } catch (e: ApiException) {
            toast(errorText(e))
        }
    }

    // ---------- چت ----------
    fun openChat(uid: String) {
        chat = ChatState(uid)
    }

    fun closeChat() {
        chat = null
        reload()
    }

    /** پیام های تازه؛ بار اول همه */
    suspend fun pull(c: ChatState, first: Boolean) {
        try {
            val since = if (first) 0L else c.messages.lastOrNull()?.id ?: 0L
            val r = io { client.dm(c.uid, since) }
            c.user = r.user
            c.relation = r.relation
            c.messages = if (first) r.messages else c.messages + r.messages.filter { m -> c.messages.none { it.id == m.id } }
        } catch (e: ApiException) {
            if (first) c.failed = errorText(e)
        }
    }

    fun send(c: ChatState, text: String, done: () -> Unit) {
        val t = text.trim()
        if (t.isEmpty() || c.sending) return
        scope.launch {
            c.sending = true
            try {
                io { client.dmSend(c.uid, t) }
                done()
                pull(c, first = false)
            } catch (e: ApiException) {
                toast(errorText(e))
            } finally {
                c.sending = false
            }
        }
    }
}

/** میز و ورق حکم (shop.html) */
class ShopModel(private val scope: CoroutineScope, private val client: Client, private val toast: (String) -> Unit, private val setCoins: (Long) -> Unit) {
    var styles by mutableStateOf<Styles?>(null)
        private set
    var busy by mutableStateOf(false)
        private set

    fun load() = scope.launch {
        styles = try { io { client.styles() } } catch (e: ApiException) { styles }
    }

    fun use(id: String) = scope.launch {
        try { styles = io { client.styleUse(id) }; toast("حله انتخاب شد و بازی بعدی همینو می‌بینی") } catch (e: ApiException) { toast(errorText(e)) }
    }

    fun buy(item: StyleItem, done: () -> Unit) {
        if (busy) return
        scope.launch {
            busy = true
            try {
                val s = io { client.styleBuy(item.id) }
                styles = s
                setCoins(s.points)
                toast("${item.name} مال خودت شد 🎉")
                done()
            } catch (e: ApiException) {
                toast(errorText(e))
            } finally {
                busy = false
            }
        }
    }
}

/** کارنامه، «درباره من»، کاور و تنظیمات (profile.html) */
class ProfileModel(private val scope: CoroutineScope, private val client: Client, private val toast: (String) -> Unit) {
    var data by mutableStateOf<Profile?>(null)
        private set

    fun load() = scope.launch {
        data = try { io { client.profile() } } catch (e: ApiException) { data }
    }

    fun saveBio(bio: String, done: (String) -> Unit) = scope.launch {
        try { val b = io { client.saveProfile(bio, null) }; toast("حله ذخیره شد"); done(b) } catch (e: ApiException) { toast(errorText(e)) }
    }

    fun setCover(id: String, done: () -> Unit) = scope.launch {
        try { io { client.saveProfile(null, id) }; done() } catch (e: ApiException) { toast(errorText(e)) }
    }

    fun setSound(on: Boolean) = scope.launch { runCatching { io { client.setFlag("sound", on) } } }
}
