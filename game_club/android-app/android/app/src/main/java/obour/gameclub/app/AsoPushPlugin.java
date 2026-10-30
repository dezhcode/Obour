package obour.gameclub.app;

import android.Manifest;
import android.app.AlarmManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.ComponentName;
import android.content.Intent;
import android.net.Uri;
import android.os.Build;
import android.os.PowerManager;
import android.provider.Settings;

import androidx.core.app.NotificationManagerCompat;

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
 *  - status / openBattery / openAutostart / openNotify: برنامهٔ بسته نوتیفیکیشن بگیرد. شیائومی، هواوی، اوپو،
 *    ویوو و ... برنامهٔ بسته را کامل می بندند مگر «اجرای خودکار» و «باتری بدون محدودیت» روشن باشد
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

    // سازنده هایی که برنامهٔ بسته را می کشند و صفحهٔ «اجرای خودکار» دارند
    private static final String[][] AUTOSTART = {
            {"com.miui.securitycenter", "com.miui.permcenter.autostart.AutoStartManagementActivity"},
            {"com.huawei.systemmanager", "com.huawei.systemmanager.startupmgr.ui.StartupNormalAppListActivity"},
            {"com.huawei.systemmanager", "com.huawei.systemmanager.optimize.process.ProtectActivity"},
            {"com.coloros.safecenter", "com.coloros.safecenter.permission.startup.StartupAppListActivity"},
            {"com.oppo.safe", "com.oppo.safe.permission.startup.StartupAppListActivity"},
            {"com.vivo.permissionmanager", "com.vivo.permissionmanager.activity.BgStartUpManagerActivity"},
            {"com.iqoo.secure", "com.iqoo.secure.ui.phoneoptimize.AddWhiteListActivity"},
            {"com.letv.android.letvsafe", "com.letv.android.letvsafe.AutobootManageActivity"},
            {"com.asus.mobilemanager", "com.asus.mobilemanager.MainActivity"},
    };

    private Intent autostartIntent() {
        for (String[] c : AUTOSTART) {
            Intent in = new Intent().setComponent(new ComponentName(c[0], c[1])).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            if (in.resolveActivity(getContext().getPackageManager()) != null) return in;
        }
        return null;
    }

    private boolean batteryOk() {
        PowerManager pm = (PowerManager) getContext().getSystemService(Context.POWER_SERVICE);
        return pm == null || pm.isIgnoringBatteryOptimizations(getContext().getPackageName());
    }

    /** وضعیت: اجازهٔ نوتیفیکیشن، باتری بدون محدودیت، و اینکه گوشی صفحهٔ «اجرای خودکار» دارد */
    @PluginMethod
    public void status(PluginCall call) {
        JSObject o = new JSObject();
        o.put("maker", Build.MANUFACTURER == null ? "" : Build.MANUFACTURER.toLowerCase());
        o.put("notify", NotificationManagerCompat.from(getContext()).areNotificationsEnabled());
        o.put("battery", batteryOk());
        o.put("autostart", autostartIntent() != null);
        call.resolve(o);
    }

    private void open(PluginCall call, Intent... tries) {
        for (Intent in : tries) {
            if (in == null) continue;
            try {
                getActivity().startActivity(in.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
                call.resolve();
                return;
            } catch (Exception ignored) {
                // بعدی
            }
        }
        call.reject("no settings page", "failed");
    }

    private Intent appDetails() {
        return new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:" + getContext().getPackageName()));
    }

    @PluginMethod
    public void openBattery(PluginCall call) {
        Intent ask = new Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS, Uri.parse("package:" + getContext().getPackageName()));
        open(call, batteryOk() ? null : ask, new Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS), appDetails());
    }

    @PluginMethod
    public void openAutostart(PluginCall call) {
        open(call, autostartIntent(), appDetails());
    }

    @PluginMethod
    public void openNotify(PluginCall call) {
        Intent n = new Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS).putExtra(Settings.EXTRA_APP_PACKAGE, getContext().getPackageName());
        open(call, n, appDetails());
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
