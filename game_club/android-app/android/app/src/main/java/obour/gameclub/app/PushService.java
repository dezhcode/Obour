package obour.gameclub.app;

import androidx.annotation.NonNull;

import com.google.firebase.messaging.FirebaseMessagingService;
import com.google.firebase.messaging.RemoteMessage;

/**
 * نوتیفیکیشن فایربیس (game_club/push.py): وقتی برنامه بسته یا در پس زمینه است خود اندروید نشانش می دهد
 * (لمسش برنامه را با data.page باز می کند)؛ وقتی برنامه باز است اینجا ساخته می شود.
 */
public class PushService extends FirebaseMessagingService {
    @Override
    public void onNewToken(@NonNull String token) {
        // دفعهٔ بعد که صفحه ها register را صدا بزنند همین توکن به حساب کاربر فرستاده می شود
        getSharedPreferences("asotas", MODE_PRIVATE).edit().putString("push_token", token).apply();
    }

    @Override
    public void onMessageReceived(@NonNull RemoteMessage m) {
        RemoteMessage.Notification n = m.getNotification();
        if (n == null) return;
        String img = n.getImageUrl() == null ? "" : n.getImageUrl().toString();
        Notify.show(this, n.getTitle(), n.getBody() == null ? "" : n.getBody(), img,
                n.getChannelId() == null ? Notify.TURN : n.getChannelId(), m.getData().get(Notify.PAGE),
                (int) (System.currentTimeMillis() % 1_000_000));
    }
}
