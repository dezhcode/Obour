package obour.gameclub.app;

import android.graphics.Color;

import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

/**
 * رنگ پشت نوار وضعیت و نوار پایین گوشی (static/app.js: GCApp.bars) هم رنگ زمینهٔ صفحه.
 * وقتی صفحه زیر نوارها کشیده نمی شود، همین رنگ پنجره پشت آن ها دیده می شود.
 */
@CapacitorPlugin(name = "AsoUi")
public class AsoUiPlugin extends Plugin {
    @PluginMethod
    public void background(PluginCall call) {
        final int color;
        try {
            color = Color.parseColor(call.getString("color", "#F4F5F8"));
        } catch (IllegalArgumentException e) {
            call.reject("bad color", "failed");
            return;
        }
        getActivity().runOnUiThread(() -> {
            getActivity().getWindow().getDecorView().setBackgroundColor(color);
            call.resolve();
        });
    }
}
