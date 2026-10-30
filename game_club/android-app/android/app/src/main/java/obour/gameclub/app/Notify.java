package obour.gameclub.app;

import android.Manifest;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.os.Build;

import androidx.core.app.NotificationCompat;
import androidx.core.app.NotificationManagerCompat;

import java.io.InputStream;
import java.net.URL;

/**
 * نوتیفیکیشن های گوشی AsoTas، همان دو کانال برنامهٔ native-app (Push.kt):
 * turn = نوبت بازی، دعوت، میز منتظر، درخواست و پیام رفیق؛ news = پاپ آپ پنل مدیریت و جایزهٔ روزانه.
 * لمس نوتیفیکیشن برنامه را با extra «page» باز می کند (AsoPushPlugin به صفحه ها می گوید کجا بروند).
 */
final class Notify {
    static final String TURN = "turn";
    static final String NEWS = "news";
    static final String PAGE = "page";

    private Notify() {}

    static void channels(Context ctx) {
        if (Build.VERSION.SDK_INT < 26) return;
        NotificationManager nm = ctx.getSystemService(NotificationManager.class);
        if (nm == null) return;
        NotificationChannel turn = new NotificationChannel(TURN, "نوبت بازی و دعوت", NotificationManager.IMPORTANCE_HIGH);
        turn.setDescription("وقتی نوبتت می‌شه، دعوتت می‌کنن یا میزت منتظرته");
        nm.createNotificationChannel(turn);
        NotificationChannel news = new NotificationChannel(NEWS, "پیام‌ها و جایزه‌ها", NotificationManager.IMPORTANCE_DEFAULT);
        news.setDescription("پیام‌های AsoTas و یادآوری جایزهٔ روزانه");
        nm.createNotificationChannel(news);
    }

    static boolean allowed(Context ctx) {
        return Build.VERSION.SDK_INT < 33
                || ctx.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED;
    }

    /** img نشانی عکس (پاپ آپ پنل)؛ این تابع را فایربیس در رشتهٔ پس زمینه صدا می زند، پس دانلود عکس اشکالی ندارد */
    static void show(Context ctx, String title, String body, String img, String channel, String page, int id) {
        channels(ctx);
        if (!allowed(ctx)) return;
        Intent open = new Intent(ctx, MainActivity.class)
                .addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_CLEAR_TOP)
                .putExtra(PAGE, page == null ? "" : page);
        PendingIntent pi = PendingIntent.getActivity(ctx, id, open,
                PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        String ch = NEWS.equals(channel) ? NEWS : TURN;
        NotificationCompat.Builder b = new NotificationCompat.Builder(ctx, ch)
                .setSmallIcon(R.drawable.ic_stat_asotas)
                .setColor(0xFFF5C451)
                .setContentTitle(title == null || title.isEmpty() ? "AsoTas" : title)
                .setContentText(body)
                .setStyle(new NotificationCompat.BigTextStyle().bigText(body))
                .setPriority(TURN.equals(ch) ? NotificationCompat.PRIORITY_HIGH : NotificationCompat.PRIORITY_DEFAULT)
                .setAutoCancel(true)
                .setContentIntent(pi);
        if (img != null && !img.isEmpty()) {
            try (InputStream in = new URL(img).openStream()) {
                Bitmap bmp = BitmapFactory.decodeStream(in);
                if (bmp != null) {
                    b.setLargeIcon(bmp).setStyle(new NotificationCompat.BigPictureStyle().bigPicture(bmp).setSummaryText(body));
                }
            } catch (Exception ignored) {
                // بی عکس
            }
        }
        try {
            NotificationManagerCompat.from(ctx).notify(id, b.build());
        } catch (SecurityException ignored) {
            // اجازه را همین الان پس گرفتند
        }
    }
}
