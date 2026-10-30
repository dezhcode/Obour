package obour.gameclub.app;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

/** یادآوری جایزهٔ روزانه (زنگ AsoPushPlugin.remind)؛ بی اینترنت و بی سرور، روی خود گوشی. */
public class ReminderReceiver extends BroadcastReceiver {
    static final int ID = 4242;

    @Override
    public void onReceive(Context ctx, Intent in) {
        Notify.show(ctx, in.getStringExtra("title"), in.getStringExtra("body"), "", Notify.NEWS, "shop.html#daily", ID);
    }
}
