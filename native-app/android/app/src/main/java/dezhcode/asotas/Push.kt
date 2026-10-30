package dezhcode.asotas

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.BitmapFactory
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import java.net.URL

/**
 * نوتیفیکیشن گوشی (Firebase Cloud Messaging): نوبت بازی و پاپ آپ پنل مدیریت.
 * وقتی برنامه بسته یا در پس زمینه است خود اندروید نشانش می دهد؛ وقتی باز است اینجا ساخته می شود.
 */
class Push : FirebaseMessagingService() {
    override fun onNewToken(token: String) {
        // دفعهٔ بعد که برنامه باز شود به حساب همین کاربر فرستاده می شود (AppViewModel.registerPush)
        getSharedPreferences("asotas", MODE_PRIVATE).edit().putString("push_token", token).apply()
    }

    override fun onMessageReceived(m: RemoteMessage) {
        val n = m.notification ?: return
        show(this, n.title ?: "AsoTas", n.body.orEmpty(), n.imageUrl?.toString(), n.channelId ?: TURN)
    }

    companion object {
        const val TURN = "turn"
        const val NEWS = "news"

        /** دو کانال: نوبت بازی (فوری با صدا) و پیام ها و اطلاعیه ها */
        fun channels(ctx: Context) {
            if (Build.VERSION.SDK_INT < 26) return
            val nm = ctx.getSystemService(NotificationManager::class.java) ?: return
            nm.createNotificationChannel(NotificationChannel(TURN, "نوبت بازی", NotificationManager.IMPORTANCE_HIGH).apply {
                description = "وقتی نوبتت می‌شه یا میزت منتظرته"
            })
            nm.createNotificationChannel(NotificationChannel(NEWS, "پیام‌ها و اطلاعیه‌ها", NotificationManager.IMPORTANCE_DEFAULT).apply {
                description = "پیام‌ها و پاپ‌آپ‌های AsoTas"
            })
        }

        fun show(ctx: Context, title: String, body: String, img: String?, channel: String) {
            channels(ctx)
            if (Build.VERSION.SDK_INT >= 33 &&
                ctx.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) return
            val open = PendingIntent.getActivity(
                ctx, 0,
                Intent(ctx, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP),
                PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
            )
            val b = NotificationCompat.Builder(ctx, channel)
                .setSmallIcon(R.mipmap.ic_launcher)
                .setContentTitle(title)
                .setContentText(body)
                .setStyle(NotificationCompat.BigTextStyle().bigText(body))
                .setPriority(if (channel == TURN) NotificationCompat.PRIORITY_HIGH else NotificationCompat.PRIORITY_DEFAULT)
                .setAutoCancel(true)
                .setContentIntent(open)
            // عکس پاپ آپ (این تابع در رشتهٔ پس زمینهٔ فایربیس اجرا می شود)
            if (!img.isNullOrBlank()) {
                runCatching { URL(img).openStream().use { BitmapFactory.decodeStream(it) } }.getOrNull()?.let { bmp ->
                    b.setLargeIcon(bmp).setStyle(NotificationCompat.BigPictureStyle().bigPicture(bmp).setSummaryText(body))
                }
            }
            runCatching { NotificationManagerCompat.from(ctx).notify((System.currentTimeMillis() % 1_000_000).toInt(), b.build()) }
        }
    }
}
