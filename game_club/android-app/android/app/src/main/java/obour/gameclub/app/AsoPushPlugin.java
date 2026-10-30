package obour.gameclub.app;

import android.Manifest;
import android.app.AlarmManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.os.Build;

import com.getcapacitor.JSObject;
import com.getcapacitor.PermissionState;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import com.getcapacitor.annotation.Permission;
import com.getcapacitor.annotation.PermissionCallback;
import com.google.firebase.messaging.FirebaseMessaging;

/**
 * نوتیفیکیشن گوشی برای صفحه های برنامه (static/app.js: GCApp.push)، مثل برنامهٔ native-app:
 *  - register: اجازهٔ اندروید ۱۳، توکن فایربیس (سرور: POST /gc/api/push/token) و تاپیک all (پاپ آپ پنل)
 *  - remind / unremind: یادآوری جایزهٔ روزانه روی خود گوشی
 *  - رویداد open: کاربر نوتیفیکیشنی را لمس کرد؛ page صفحه ای است که باید باز شود
 * بی google-services.json فایربیس راه نمی افتد و register با کد no_firebase رد می شود (بقیه کار می کند).
 */
@CapacitorPlugin(name = "AsoPush", permissions = {
        @Permission(alias = "notifications", strings = {Manifest.permission.POST_NOTIFICATIONS})
})
public class AsoPushPlugin extends Plugin {

    @Override
    public void load() {
        Notify.channels(getContext());
        page(getActivity().getIntent());
    }

    @Override
    protected void handleOnNewIntent(Intent intent) {
        page(intent);
    }

    // نوتیفیکیشن فایربیس در پس زمینه: data.page در extra های همان intent است
    private void page(Intent in) {
        if (in == null) return;
        String p = in.getStringExtra(Notify.PAGE);
        if (p == null) return;
        in.removeExtra(Notify.PAGE);
        JSObject o = new JSObject();
        o.put("page", p);
        notifyListeners("open", o, true);
    }

    @PluginMethod
    public void register(PluginCall call) {
        if (Build.VERSION.SDK_INT >= 33 && getPermissionState("notifications") != PermissionState.GRANTED
                && !call.getBoolean("quiet", false)) {
            requestPermissionForAlias("notifications", call, "permDone");
            return;
        }
        token(call);
    }

    @PermissionCallback
    private void permDone(PluginCall call) {
        token(call);
    }

    private void token(PluginCall call) {
        final boolean allowed = Notify.allowed(getContext());
        FirebaseMessaging fm;
        try {
            fm = FirebaseMessaging.getInstance();
        } catch (IllegalStateException e) {
            call.reject("firebase is not configured", "no_firebase");
            return;
        }
        fm.subscribeToTopic("all");
        fm.getToken().addOnCompleteListener(t -> {
            if (!t.isSuccessful() || t.getResult() == null) {
                call.reject("no token", "failed");
                return;
            }
            JSObject o = new JSObject();
            o.put("token", t.getResult());
            o.put("allowed", allowed);
            call.resolve(o);
        });
    }

    private PendingIntent reminder(String title, String body) {
        Intent in = new Intent(getContext(), ReminderReceiver.class).putExtra("title", title).putExtra("body", body);
        return PendingIntent.getBroadcast(getContext(), ReminderReceiver.ID, in,
                PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
    }

    /** at: زمان (میلی ثانیه)؛ یادآوری قبلی جایش را می دهد. زنگ غیردقیق است و اجازهٔ جدا نمی خواهد. */
    @PluginMethod
    public void remind(PluginCall call) {
        Long at = call.getLong("at");
        if (at == null || at <= System.currentTimeMillis()) {
            call.reject("bad time", "failed");
            return;
        }
        AlarmManager am = (AlarmManager) getContext().getSystemService(Context.ALARM_SERVICE);
        if (am == null) {
            call.reject("no alarm", "failed");
            return;
        }
        am.set(AlarmManager.RTC_WAKEUP, at, reminder(call.getString("title", "AsoTas"), call.getString("body", "")));
        call.resolve();
    }

    @PluginMethod
    public void unremind(PluginCall call) {
        AlarmManager am = (AlarmManager) getContext().getSystemService(Context.ALARM_SERVICE);
        if (am != null) am.cancel(reminder("", ""));
        call.resolve();
    }
}
